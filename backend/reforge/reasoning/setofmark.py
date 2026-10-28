"""Set-of-Mark images: the photographed part, and the same view with the marks the reasoning model answers in.

Outline segments S… are drawn in alternating colours with their label outside the part, candidate mirror axes A…
as dashed lines, and through-holes H… as circles. Labels are placed along the outward normal and pushed further out
when they would overlap, so every mark stays readable at the size sent to the model.
"""

from __future__ import annotations

import cv2
import numpy as np
from shapely.geometry import Point, Polygon

from reforge.capture.calibration import RectifiedView
from reforge.geometry.segments import SegmentedOutline
from reforge.geometry.symmetry import MirrorAxis

PALETTE = [(0, 120, 255), (200, 80, 0), (40, 170, 40), (190, 40, 190), (0, 170, 200), (40, 40, 220)]  # BGR
AXIS_COLOUR = (60, 60, 60)
HOLE_COLOUR = (0, 150, 230)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _label(img: np.ndarray, text: str, anchor: np.ndarray, colour: tuple[int, int, int],
           taken: list[tuple[int, int, int, int]], push: np.ndarray, scale: float) -> None:
    (tw, th), base = cv2.getTextSize(text, FONT, scale, 2)
    h, w = img.shape[:2]
    for step in range(6):
        cx, cy = anchor + push * step * (th + 8)
        x0 = int(np.clip(cx - tw / 2 - 5, 0, w - tw - 10))
        y0 = int(np.clip(cy - th / 2 - 5, 0, h - th - base - 10))
        box = (x0, y0, x0 + tw + 10, y0 + th + base + 10)
        if not any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in taken):
            break
    taken.append(box)
    cv2.rectangle(img, box[:2], box[2:], (255, 255, 255), -1)
    cv2.rectangle(img, box[:2], box[2:], colour, 2)
    cv2.putText(img, text, (box[0] + 5, box[3] - base - 5), FONT, scale, colour, 2, cv2.LINE_AA)


def render_set_of_mark(view: RectifiedView, segmented: SegmentedOutline, axes: list[MirrorAxis],
                       holes: list[tuple[str, tuple[float, float], float]], *, margin_mm: float = 12.0,
                       width_px: int = 1600) -> tuple[np.ndarray, np.ndarray]:
    """(context, marked close-up), both BGR. The context is the whole rectified view, so the model sees everything
    on the mat and can tell when the traced outline is only part of an object."""
    pts = segmented.points
    lo, hi = pts.min(axis=0) - margin_mm, pts.max(axis=0) + margin_mm
    (c0, r0), (c1, r1) = np.round(view.mm_to_px(np.array([lo, hi]))).astype(int)
    h_img, w_img = view.image.shape[:2]
    c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, w_img), min(r1, h_img)
    crop = view.image[r0:r1, c0:c1]
    scale = width_px / crop.shape[1]
    clean = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    context_scale = min(1.0, width_px / max(w_img, h_img))
    context = cv2.resize(view.image, None, fx=context_scale, fy=context_scale, interpolation=cv2.INTER_AREA)

    def to_px(mm: np.ndarray) -> np.ndarray:
        return (view.mm_to_px(np.asarray(mm).reshape(-1, 2)) - [c0, r0]) * scale

    marked = cv2.addWeighted(clean, 0.7, np.full_like(clean, 255), 0.3, 0)
    text_scale = max(0.6, marked.shape[1] / 1800)
    taken: list[tuple[int, int, int, int]] = []
    labels: list[tuple[str, np.ndarray, tuple[int, int, int], np.ndarray]] = []  # drawn last, on top of every line
    polygon = Polygon(pts).buffer(0)
    centre_px = to_px(np.asarray(polygon.centroid.coords))[0]
    height, width = marked.shape[:2]

    for axis in axes:
        p = to_px(np.asarray(axis.point))[0]
        d = to_px(np.asarray(axis.point) + axis.direction)[0] - p
        d = d / np.linalg.norm(d)
        span = np.hypot(width, height)
        a, b = p - d * span, p + d * span
        ok, a_i, b_i = cv2.clipLine((0, 0, width, height), tuple(int(v) for v in np.round(a)),
                                    tuple(int(v) for v in np.round(b)))
        if not ok:
            continue
        a_i, b_i = np.asarray(a_i, float), np.asarray(b_i, float)
        length = float(np.linalg.norm(b_i - a_i))
        for s0 in np.arange(0, length, 28.0):
            e = min(s0 + 16.0, length)
            cv2.line(marked, tuple(np.round(a_i + d * s0).astype(int)), tuple(np.round(a_i + d * e).astype(int)),
                     AXIS_COLOUR, 3, cv2.LINE_AA)
        labels.append((axis.axis_id, a_i + d * 40, AXIS_COLOUR, d))

    for i, (hole_id, centre, radius) in enumerate(holes):
        c = to_px(np.asarray(centre))[0]
        r_px = radius * view.px_per_mm * scale
        cv2.circle(marked, tuple(np.round(c).astype(int)), int(round(r_px)), HOLE_COLOUR, 3, cv2.LINE_AA)
        labels.append((hole_id, c + np.array([0, -r_px - 22]), HOLE_COLOUR,
                       np.array([0.0, -1.0]) if i % 2 == 0 else np.array([0.0, 1.0])))

    for i, seg in enumerate(segmented.segments):
        colour = PALETTE[i % len(PALETTE)]
        span = to_px(segmented.span(seg))
        cv2.polylines(marked, [np.round(span).astype(np.int32)], False, colour, 4, cv2.LINE_AA)
        cv2.circle(marked, tuple(np.round(span[0]).astype(int)), 5, (0, 0, 0), -1, cv2.LINE_AA)
        mid_mm = np.asarray(seg.midpoint_mm)
        tangent = segmented.span(seg)[-1] - segmented.span(seg)[0]
        normal = np.array([-tangent[1], tangent[0]]) / (np.linalg.norm(tangent) + 1e-12)
        if polygon.contains(Point(mid_mm + 0.5 * normal)):
            normal = -normal
        mid = to_px(mid_mm)[0]
        push = to_px(mid_mm + normal)[0] - mid
        if np.linalg.norm(push) > 0:
            push = push / np.linalg.norm(push)
        else:
            push = (mid - centre_px) / (np.linalg.norm(mid - centre_px) + 1e-12)
        labels.append((seg.seg_id, mid + push * 34, colour, push))

    for text, anchor, colour, push in labels:
        _label(marked, text, anchor, colour, taken, push, text_scale)

    legend = "S#: outline segments   A#: candidate mirror axes (dashed)   H#: through-holes"
    cv2.rectangle(marked, (0, height - 44), (width, height), (255, 255, 255), -1)
    cv2.putText(marked, legend, (12, height - 14), FONT, text_scale * 0.8, (20, 20, 20), 2, cv2.LINE_AA)
    return context, marked
