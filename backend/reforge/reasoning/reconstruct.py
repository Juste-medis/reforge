"""D4 stage: footprint → segments and candidate axes → Set-of-Mark → interpretation → verification → mirror completion.

If the model call fails (budget, network, an invalid answer), the geometric rule takes over and the report says so:
the demo keeps working, and nothing pretends to be AI that isn't.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from reforge.capture.calibration import RectifiedView
from reforge.errors import ReforgeError
from reforge.geometry.completion import Completion, complete_by_mirror
from reforge.geometry.segments import SegmentedOutline, segment_outline
from reforge.geometry.symmetry import MirrorAxis, find_mirror_axes, mirror_gain_mm2, rescore
from reforge.reasoning.interpret import GeometricInterpreter, Interpretation, InterpretationRequest
from reforge.reasoning.setofmark import render_set_of_mark
from reforge.reasoning.verify import MIN_AXIS_SUPPORT, Note, Verified, verify
from reforge.vision.refine import RefinedProfile

MIN_CANDIDATE_SUPPORT = 0.6


@dataclass(frozen=True)
class Reconstruction:
    segmented: SegmentedOutline
    axes: tuple[MirrorAxis, ...]
    context_bgr: np.ndarray
    marked_bgr: np.ndarray
    facts: dict
    interpretation: Interpretation
    fallback_reason: dict | None  # the typed error that sent us to the geometric rule, if any
    verified: Verified
    completion: Completion | None


def _holes(profile: RefinedProfile) -> list[tuple[str, tuple[float, float], float]]:
    return [(c.hole_id, c.fit.center, c.fit.radius) for c in profile.holes if c.fit is not None and not c.glare_suspect]


async def reconstruct(view: RectifiedView, footprint: RefinedProfile, interpreter, *, thickness_mm: float,
                      ) -> Reconstruction:
    segmented = segment_outline(footprint.outer.points_mm)
    outline = segmented.points
    holes = _holes(footprint)
    irregular = [segmented.span(s) for s in segmented.segments if s.kind == "irregular"]
    axes = [a for a in find_mirror_axes(outline, holes, exclude_mm=np.concatenate(irregular) if irregular else None)
            if a.support >= MIN_CANDIDATE_SUPPORT and not a.contradicted_by_holes]
    context, marked = render_set_of_mark(view, segmented, axes, holes)
    x0, y0 = outline.min(axis=0)
    x1, y1 = outline.max(axis=0)
    facts = {
        "units": "mm",
        "thickness_mm": round(thickness_mm, 3),
        "trace_share_of_objects_on_mat": None if footprint.trace_share is None else round(footprint.trace_share, 2),
        "part_colour_spread_delta_e": (None if footprint.colour_spread_delta_e is None
                                       else round(footprint.colour_spread_delta_e, 1)),
        "extent_mm": [round(float(x1 - x0), 2), round(float(y1 - y0), 2)],
        "segments": [{"id": s.seg_id, "length_mm": round(s.length_mm, 1)} for s in segmented.segments],
        "holes": [{"id": hid, "diameter_mm": round(2 * r, 2)} for hid, _, r in holes],
        "mirror_axes": [{"id": a.axis_id, "direction_deg": round(a.angle_deg, 1), "support": round(a.support, 3),
                         "holes_matched": a.hole_matches, "holes_contradicting": a.hole_mismatches,
                         "mirror_would_add_mm2": round(mirror_gain_mm2(a, outline), 1)} for a in axes],
    }
    request = InterpretationRequest(context, marked, facts, [s.seg_id for s in segmented.segments],
                                    [a.axis_id for a in axes], [h[0] for h in holes],
                                    {s.seg_id: s.kind for s in segmented.segments})
    fallback_reason = None
    try:
        interpretation = await interpreter.interpret(request)
    except ReforgeError as exc:
        fallback_reason = exc.to_dict()
        interpretation = await GeometricInterpreter().interpret(request)

    verified = verify(interpretation.analysis, segmented, axes, outline)
    completion = None
    if verified.axis is not None and verified.fracture_ids:
        spans = [segmented.span(segmented.by_id(sid)) for sid in verified.fracture_ids]
        axis = rescore(verified.axis, outline, holes, np.concatenate(spans))
        if axis.support >= MIN_AXIS_SUPPORT and not axis.contradicted_by_holes:
            completion = complete_by_mirror(outline, holes, axis, list(verified.fracture_ids), segmented)
        else:
            verified = replace(verified, axis=None, notes=verified.notes + (Note(
                "AXIS_WEAK", f"With the accepted fracture left out, {axis.axis_id} drops to {axis.support:.0%} "
                             "support: no mirror reconstruction.", "rejected"),))
    return Reconstruction(segmented, tuple(axes), context, marked, facts, interpretation, fallback_reason, verified,
                          completion)
