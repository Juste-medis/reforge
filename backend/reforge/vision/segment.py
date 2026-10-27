"""Part segmentation on the rectified mat view.

``SamSegmenter`` calls SAM 3.1 through the Meta Model API. ``ClassicalSegmenter`` is a labelled,
non-AI fallback (colour distance from the mat) used when the API is unavailable and in offline tests.
The method that produced a mask always travels with it, so a fallback result is never shown as SAM output.

Either way, the mask is coarse by design: ``reforge.vision.refine`` locates the edges.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

import cv2
import numpy as np
from meta_sam_parser import (
    FramePrompt,
    PromptBox,
    PromptObject,
    PromptPoint,
    build_object_prompt,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)

from reforge.capture.calibration import RectifiedView
from reforge.errors import ReforgeError
from reforge.meta_api.client import MetaClient, Timer, UsageRecord, estimate_cost, map_api_error

MAX_SAM_SIDE_PX = 2048
MAX_PART_FRACTION = 0.6  # larger "objects" are the mat itself
BOX_PAD_MM = 1.0


@dataclass(frozen=True)
class Segmentation:
    mask: np.ndarray  # bool, view-sized
    method: str  # "sam-3.1" or "classical-fallback"
    is_ai: bool
    confidence: float | None = None
    latency_s: float = 0.0
    cost_usd: float = 0.0
    detail: dict = field(default_factory=dict)


def _touches_border(mask: np.ndarray) -> bool:
    return bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())


def colour_candidate(view: RectifiedView) -> np.ndarray | None:
    """The largest region that differs in colour from the mat paper and stays clear of the view border.

    It's not AI: colour distance from the paper, an Otsu threshold, then morphology. Returns None if nothing qualifies.
    """
    lab = cv2.cvtColor(view.image.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)
    h, w = lab.shape[:2]
    rim = max(3, int(0.03 * min(h, w)))
    frame = np.zeros((h, w), bool)
    frame[:rim], frame[-rim:], frame[:, :rim], frame[:, -rim:] = True, True, True, True
    paper = np.median(lab[frame], axis=0)
    distance = np.linalg.norm(lab - paper, axis=2)
    scaled = np.clip(distance * (255.0 / max(float(distance.max()), 1e-6)), 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = max(otsu * float(distance.max()) / 255.0, 10.0)
    fg = (distance > threshold).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * max(1, int(0.25 * view.px_per_mm)) + 1,) * 2)
    fg = cv2.morphologyEx(cv2.morphologyEx(fg, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    best, best_area = 0, 0
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area > best_area and area < MAX_PART_FRACTION * h * w and not _touches_border(labels == label):
            best, best_area = label, area
    return labels == best if best else None


def box_around(mask: np.ndarray, pad_px: int) -> tuple[int, int, int, int]:
    """Half-open (left, top, right, bottom) around ``mask``, padded and clipped to the image."""
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    return (max(int(xs.min()) - pad_px, 0), max(int(ys.min()) - pad_px, 0),
            min(int(xs.max()) + 1 + pad_px, w), min(int(ys.max()) + 1 + pad_px, h))


class ClassicalSegmenter:
    """Labelled non-AI fallback: the colour candidate itself."""

    method = "classical-fallback"

    async def segment(self, view: RectifiedView) -> Segmentation:
        mask = colour_candidate(view)
        if mask is None:
            raise ReforgeError("SEG_NO_PART", "No part was found on the mat.",
                               "Place the part inside the corner marks, away from the markers.")
        return Segmentation(mask, self.method, is_ai=False,
                            detail={"note": "classical fallback (not AI): colour distance from the mat paper"})


def _png_data_url(image: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ReforgeError("IMAGE_ENCODE_FAILED", "Could not encode the image for the segmenter.")
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


def masks_from_result(result, size: tuple[int, int]) -> list[tuple[str, np.ndarray, float | None]]:
    """Box-local SAM rasters → full-size boolean masks, as (object_id, mask, confidence)."""
    width, height = size
    out = []
    for rec in result.records:
        if rec.kind != "mask":
            continue
        raster = np.frombuffer(decode_mask_to_raster(rec.mask), np.uint8).reshape(rec.mask.height, rec.mask.width)
        b = rec.bounds
        left, top = int(round(b.left)), int(round(b.top))
        right, bottom = int(round(b.right)), int(round(b.bottom))
        bw, bh = right - left, bottom - top
        if bw <= 0 or bh <= 0:
            continue
        if (rec.mask.width, rec.mask.height) != (bw, bh):
            raster = cv2.resize(raster, (bw, bh), interpolation=cv2.INTER_NEAREST)
        full = np.zeros((height, width), bool)
        x0, y0, x1, y1 = max(left, 0), max(top, 0), min(right, width), min(bottom, height)
        full[y0:y1, x0:x1] = raster[y0 - top:y1 - top, x0 - left:x1 - left] > 0
        out.append((rec.object_id, full, rec.confidence))
    return out


def select_part(candidates: list[tuple[str, np.ndarray, float | None]]) -> tuple[str, np.ndarray, float | None]:
    """The part is the largest instance that isn't the mat: it doesn't touch the border or fill the view."""
    usable = [c for c in candidates
              if c[1].any() and not _touches_border(c[1]) and c[1].mean() < MAX_PART_FRACTION]
    if not usable:
        raise ReforgeError("SEG_NO_PART", "SAM 3.1 returned no usable part instance.",
                           "Click on the part to give a point prompt, or try another noun phrase.")
    return max(usable, key=lambda c: (int(c[1].sum()), c[2] or 0.0))


class SamSegmenter:
    """SAM 3.1 via the Meta Model API.

    Prompt order, chosen from live measurements on 2026-10-27 (docs/EVALUATION.md):
    1. A user click becomes a point prompt.
    2. Otherwise, a box prompt around the local colour candidate. On the mat this was confident (0.99, IoU 0.994),
       while text prompts returned 0 instances on the same view.
    3. Otherwise (no candidate, or an empty box result), the noun phrase.
    SAM always produces the mask. The colour candidate only says where to look, and the report records the prompt.
    """

    method = "sam-3.1"

    def __init__(self, client: MetaClient, prompt: str = "plastic part", point_px: tuple[int, int] | None = None,
                 job_id: str | None = None) -> None:
        self.client = client
        self.prompt = prompt
        self.point_px = point_px
        self.job_id = job_id

    async def _call(self, model: str, image: np.ndarray, text: str, kind: str) -> list:
        self.client.check_budget(estimate_cost(model, images=1))
        content = [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": _png_data_url(image)}]
        result, error = None, None
        with Timer() as timer:
            try:
                stream = await self.client.sdk.responses.create(
                    model=model, input=[{"role": "user", "content": content}], stream=True,
                    metadata={"include_confidence": "true"})
                result = await parse_responses_stream(stream, image_segmentation_format()).final_result()
            except Exception as exc:  # timeouts, auth, network, refusals: typed and recorded below
                error = exc
        cost = estimate_cost(model, images=1) if result is not None else 0.0
        self.client.record(UsageRecord(stage="segmentation", model=model, started_at=timer.started_at,
                                       latency_s=round(timer.elapsed, 3), status="ok" if error is None else
                                       map_api_error(error).code, job_id=self.job_id, images=1, cost_usd=cost,
                                       extra={"prompt_kind": kind}))
        self._latency += timer.elapsed
        self._cost += cost
        if error is not None:
            raise map_api_error(error) from error
        return masks_from_result(result, (image.shape[1], image.shape[0]))

    async def segment(self, view: RectifiedView) -> Segmentation:
        model = self.client.settings.reforge_model_segmentation
        self.client.check_model(model)
        self._latency, self._cost = 0.0, 0.0
        image = view.image
        h, w = image.shape[:2]
        scale = min(1.0, MAX_SAM_SIDE_PX / max(h, w))
        sent = cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) \
            if scale < 1.0 else image
        sh, sw = sent.shape[:2]

        attempts: list[dict] = []
        candidates: list = []
        if self.point_px is not None:
            px, py = self.point_px
            text = build_object_prompt(size=(sw, sh), objects=[PromptObject(id=1, prompts=[
                FramePrompt(frame=0, points=[PromptPoint(x=int(px * scale), y=int(py * scale))])])])
            candidates = await self._call(model, sent, text, "point")
            attempts.append({"prompt": "point", "source": "user click", "instances": len(candidates)})
        else:
            proposal = colour_candidate(view)
            if proposal is not None:
                left, top, right, bottom = box_around(proposal, pad_px=max(2, round(BOX_PAD_MM * view.px_per_mm)))
                box = PromptBox(int(left * scale), int(top * scale), min(int(np.ceil(right * scale)), sw),
                                min(int(np.ceil(bottom * scale)), sh))
                text = build_object_prompt(size=(sw, sh), objects=[PromptObject(id=1, prompts=[
                    FramePrompt(frame=0, box=box)])])
                candidates = await self._call(model, sent, text, "box")
                attempts.append({"prompt": "box", "source": "colour candidate on the mat (not AI)",
                                 "box_px": [box.left, box.top, box.right, box.bottom], "instances": len(candidates)})
            if not candidates:
                candidates = await self._call(model, sent, self.prompt, "text")
                attempts.append({"prompt": "text", "source": f"noun phrase {self.prompt!r}",
                                 "instances": len(candidates)})

        object_id, mask, confidence = select_part(candidates)
        if scale < 1.0:
            mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
        return Segmentation(mask, self.method, is_ai=True, confidence=confidence, latency_s=self._latency,
                            cost_usd=self._cost, detail={"object_id": object_id, "attempts": attempts,
                                                         "prompt": attempts[-1]["prompt"], "sent_size": [sw, sh]})
