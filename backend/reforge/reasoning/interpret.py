"""Interpretation of a part from its Set-of-Mark images: Muse Spark (AI), or a geometric rule (not AI).

Muse Spark sees the photographed part and the marked view, plus measured facts: segment lengths, hole diameters, and
each candidate axis's support and the material its mirror image would add. It is *not* told which segments the
geometry finds irregular, so its fracture picks are an independent judgement that ``reasoning.verify`` checks.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

import cv2
import numpy as np

from reforge.errors import ReforgeError
from reforge.meta_api.client import MetaClient, Timer, UsageRecord, estimate_cost, map_api_error
from reforge.reasoning.analysis import NONE_ID, PartAnalysis, build_schema, parse_analysis

BUDGET_ESTIMATE_USD = 0.02  # two images of about 1600 px plus a short answer; checked before every call
MIN_AXIS_SUPPORT = 0.9

INSTRUCTIONS = """You are the interpretation stage of a tool that rebuilds broken plastic parts for 3D printing.
Geometry is measured separately with calibrated metrology, so never estimate dimensions.

Image 1 is everything in the calibration mat's free zone, photographed from above.
Image 2 is a close-up of the outline that was traced, with marks: coloured outline segments labelled S0, S1, ...;
candidate mirror axes drawn as dashed lines labelled A0, A1, ...; and through-holes labelled H0, H1, .... Answer only
with the ids shown. The facts include how much of what's on the mat the trace covers, and how uniform its colour is:
if the trace is only part of a larger object, or the object isn't a flat plate of uniform thickness (a pipe, a
knob, a 3D shape), say so with the family and its reason.

1. object_name: what the object is, in a few words.
2. family: extruded_profile for a flat plate of uniform thickness (holes allowed); else revolved, multi_view or
   unsupported.
3. is_broken and fracture_segment_ids: a fracture edge is a jagged, irregular edge where material broke away;
   moulded edges are smooth straight lines and arcs. List every segment that is a fracture edge.
4. symmetry and mirror_axis_id: the symmetry the intact part had. For a broken part, choose the axis whose mirror
   image rebuilds the missing material: the facts give each axis's measured support and how much material its
   mirror would add. Use "unsure" and "none" when you can't tell.
5. holes: a role for each hole.
6. missing_features: features the break removed, in words, with the nearest segment ids.
7. required_measurements: up to 8 caliper measurements that would most improve the reconstruction, most important
   first.
Keep every reason under 40 words."""


@dataclass(frozen=True)
class InterpretationRequest:
    context_bgr: np.ndarray
    marked_bgr: np.ndarray
    facts: dict
    seg_ids: list[str]
    axis_ids: list[str]
    hole_ids: list[str]
    segment_kinds: dict[str, str] = field(default_factory=dict)  # for the geometric rule only; never sent to a model


@dataclass(frozen=True)
class Interpretation:
    analysis: PartAnalysis
    method: str
    is_ai: bool
    latency_s: float
    cost_usd: float
    detail: dict


def _png_data_url(image: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ReforgeError("IMAGE_INVALID", "Could not encode the Set-of-Mark image.")
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


class SparkInterpreter:
    is_ai = True

    def __init__(self, client: MetaClient, *, model: str | None = None, reasoning_effort: str = "low",
                 job_id: str | None = None) -> None:
        self.client = client
        self.model = model or client.settings.reforge_model_reasoning
        self.reasoning_effort = reasoning_effort
        self.job_id = job_id

    @property
    def method(self) -> str:
        return self.model

    async def interpret(self, req: InterpretationRequest) -> Interpretation:
        self.client.check_model(self.model)
        self.client.check_budget(BUDGET_ESTIMATE_USD)
        schema = build_schema(req.seg_ids, req.axis_ids, req.hole_ids)
        user = [
            {"type": "text", "text": "Measured facts (JSON):\n" + json.dumps(req.facts, indent=1)},
            {"type": "image_url", "image_url": {"url": _png_data_url(req.context_bgr)}},
            {"type": "image_url", "image_url": {"url": _png_data_url(req.marked_bgr)}},
        ]
        record = {"stage": "interpretation", "model": self.model, "job_id": self.job_id, "images": 2}
        with Timer() as timer:
            try:
                resp = await self.client.sdk.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "developer", "content": INSTRUCTIONS}, {"role": "user", "content": user}],
                    response_format={"type": "json_schema",
                                     "json_schema": {"name": "part_analysis", "strict": True, "schema": schema}},
                    reasoning_effort=self.reasoning_effort,
                )
            except Exception as exc:  # recorded, then re-raised as a typed error without request details
                error = map_api_error(exc)
                self.client.record(UsageRecord(started_at=timer.started_at, latency_s=0.0, status=error.code,
                                               **record))
                raise error from exc
        usage = resp.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        details = getattr(usage, "completion_tokens_details", None) if usage else None
        reasoning = int(getattr(details, "reasoning_tokens", 0) or 0)
        cost = estimate_cost(self.model, input_tokens=tokens_in, output_tokens=tokens_out)
        choice = resp.choices[0]
        status = "ok"
        try:
            analysis = parse_analysis(choice.message.content or "", req.seg_ids, req.axis_ids, req.hole_ids)
        except ReforgeError as exc:
            status = exc.code
            raise
        finally:
            self.client.record(UsageRecord(started_at=timer.started_at, latency_s=timer.elapsed, status=status,
                                           input_tokens=tokens_in, output_tokens=tokens_out, reasoning_tokens=reasoning,
                                           cost_usd=cost, extra={"reasoning_effort": self.reasoning_effort},
                                           **record))
        return Interpretation(analysis, self.model, True, timer.elapsed, cost, {
            "reasoning_effort": self.reasoning_effort, "finish_reason": choice.finish_reason,
            "images_px": [list(req.context_bgr.shape[1::-1]), list(req.marked_bgr.shape[1::-1])],
            "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out, "reasoning_tokens": reasoning}})


class GeometricInterpreter:
    """A fixed geometric rule standing in for the model: labelled not AI everywhere it appears."""

    is_ai = False
    method = "geometric-rule"

    async def interpret(self, req: InterpretationRequest) -> Interpretation:
        fracture = [sid for sid in req.seg_ids if req.segment_kinds.get(sid) == "irregular"]
        axes = {a["id"]: a for a in req.facts.get("mirror_axes", [])}
        usable = [aid for aid in req.axis_ids
                  if axes[aid]["support"] >= MIN_AXIS_SUPPORT and axes[aid]["holes_contradicting"] == 0]
        # Every usable axis is already well supported; among them, the most holes matched, then the most material
        # the mirror rebuilds (a crosswise axis maps the break onto itself and rebuilds almost nothing).
        axis = max(usable, key=lambda aid: (axes[aid]["holes_matched"], axes[aid]["mirror_would_add_mm2"],
                                            axes[aid]["support"])) if fracture and usable else NONE_ID
        data = {
            "object_name": "part", "family": "extruded_profile",
            "family_reason": "geometric rule: a single top-view outline is always treated as an extruded profile",
            "is_broken": bool(fracture), "fracture_segment_ids": fracture,
            "fracture_reason": "geometric rule: segments made of many short pieces (irregular)",
            "symmetry": "mirror" if axis != NONE_ID else "unsure", "mirror_axis_id": axis,
            "symmetry_reason": "geometric rule: a well-supported axis; most holes matched, then most material rebuilt",
            "holes": [{"hole_id": h, "role": "unknown"} for h in req.hole_ids],
            "missing_features": [],
            "required_measurements": [{"kind": "thickness", "target_id": NONE_ID, "why": "sets the extrusion"}]
            + [{"kind": "hole_diameter", "target_id": h, "why": "fit-critical"} for h in req.hole_ids][:7],
        }
        analysis = PartAnalysis.model_validate(data, context={"seg_ids": req.seg_ids, "axis_ids": req.axis_ids,
                                                              "hole_ids": req.hole_ids})
        return Interpretation(analysis, self.method, False, 0.0, 0.0, {})
