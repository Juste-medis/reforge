"""D4 stage: footprint → segments and candidate axes → Set-of-Mark → interpretation → verification → mirror completion.

If the model call fails (budget, network, an invalid answer), the geometric rule takes over and the report says so:
the demo keeps working, and nothing pretends to be AI that isn't.

If the model's answer is verified but its mirror axis can't rebuild the break it found (an axis that maps the break
onto itself, say: a real symmetry of the part, but the wrong one), the axis the geometric rule would choose gets a
second chance. It must pass the same checks, with the model's own fracture picks re-verified under it, and the report
says the axis was corrected. The model's other judgements (what the part is, whether it is broken, where) stand.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from reforge.capture.calibration import RectifiedView
from reforge.errors import ReforgeError
from reforge.geometry.completion import Completion, complete_by_mirror
from reforge.geometry.segments import SegmentedOutline, segment_outline
from reforge.geometry.symmetry import MirrorAxis, find_mirror_axes, mirror_gain_mm2, rescore
from reforge.reasoning.analysis import NONE_ID
from reforge.reasoning.interpret import GeometricInterpreter, Interpretation, InterpretationRequest
from reforge.reasoning.setofmark import render_set_of_mark
from reforge.reasoning.verify import MIN_AXIS_SUPPORT, Note, Verified, verify
from reforge.vision.refine import RefinedProfile

MIN_CANDIDATE_SUPPORT = 0.6
MIN_EVIDENCE_RATIO = 1.0  # outline (and holes) confirming the mirror, per mm of outline it invents
MAX_EXPOSED_FRACTURE_MM = 2.0  # or 10 % of the fracture: what the mirror may leave uncovered (junctions, roughness)
CANDIDATE_AXES = 4  # a square part has four mirror axes, all fully supported when one side is broken


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


def _rebuild_problem(completion: Completion, fracture_mm: float) -> tuple[str, str] | None:
    """Why a mirror rebuild can't be trusted, as (code, message), or None. Applied to any interpreter's choice.

    Support is a fraction of what can be checked: with a long fracture little can be, and many axes reach 100 %
    (a guitar pick snapped along its length, 2026-11-02: three wrong axes did). And a mirror that is a real symmetry
    of the part can still rebuild only part of the break (a square flange's diagonal leaves a corner missing)."""
    a = completion.axis.axis_id
    confirmed, invented = completion.confirmed_mm, completion.inferred_length_mm
    if invented > 0 and confirmed < MIN_EVIDENCE_RATIO * invented:
        return ("AXIS_UNDERSUPPORTED",
                f"Only {confirmed:.0f} mm of outline and holes confirm {a}, less than the {invented:.0f} mm its mirror "
                "would rebuild: no mirror reconstruction. Too little of the part's symmetry survived the break to "
                "rebuild it safely; measure the missing side instead.")
    exposed = completion.exposed_fracture_mm
    if exposed > max(MAX_EXPOSED_FRACTURE_MM, 0.1 * fracture_mm):
        return ("AXIS_PARTIAL",
                f"The mirror about {a} rebuilds only part of the break: {exposed:.0f} mm of the {fracture_mm:.0f} mm "
                "fracture would stay uncovered. No mirror reconstruction with this axis.")
    return None


def _attempt(verified: Verified, segmented: SegmentedOutline, outline: np.ndarray,
             holes: list[tuple[str, tuple[float, float], float]]) -> tuple[Completion | None, Verified]:
    """The mirror completion a verified reading allows, or None with the reason added to its notes."""
    if verified.axis is None or not verified.fracture_ids:
        return None, verified
    spans = [segmented.span(segmented.by_id(sid)) for sid in verified.fracture_ids]
    axis = rescore(verified.axis, outline, holes, np.concatenate(spans))
    if axis.support < MIN_AXIS_SUPPORT or axis.contradicted_by_holes:
        return None, replace(verified, axis=None, notes=verified.notes + (Note(
            "AXIS_WEAK", f"With the accepted fracture left out, {axis.axis_id} drops to {axis.support:.0%} "
                         "support: no mirror reconstruction.", "rejected"),))
    completion = complete_by_mirror(outline, holes, axis, list(verified.fracture_ids), segmented)
    fracture_mm = sum(segmented.by_id(sid).length_mm for sid in verified.fracture_ids)
    problem = _rebuild_problem(completion, fracture_mm)
    if problem is not None:
        return None, replace(verified, axis=None, notes=verified.notes + (Note(*problem, "rejected"),))
    return completion, verified


def _rule_axis(axes: list[MirrorAxis], rebuild_ok: dict[str, bool], outline: np.ndarray) -> MirrorAxis | None:
    """The axis the geometric rule would choose (``GeometricInterpreter``): well supported, no hole against it, a
    trial rebuild that covers the break; then the most holes matched and the most material rebuilt."""
    trusted = [a for a in axes if a.support >= MIN_AXIS_SUPPORT and not a.contradicted_by_holes
               and rebuild_ok.get(a.axis_id, False)]
    return max(trusted, key=lambda a: (a.hole_matches, mirror_gain_mm2(a, outline), a.support), default=None)


def _holes(profile: RefinedProfile) -> list[tuple[str, tuple[float, float], float]]:
    return [(c.hole_id, c.fit.center, c.fit.radius) for c in profile.holes if c.fit is not None and not c.doubt]


async def reconstruct(view: RectifiedView, footprint: RefinedProfile, interpreter, *, thickness_mm: float,
                      ) -> Reconstruction:
    segmented = segment_outline(footprint.outer.points_mm)
    outline = segmented.points
    holes = _holes(footprint)
    irregular = [segmented.span(s) for s in segmented.segments if s.kind == "irregular"]
    axes = [a for a in find_mirror_axes(outline, holes, exclude_mm=np.concatenate(irregular) if irregular else None,
                                        keep=CANDIDATE_AXES)
            if a.support >= MIN_CANDIDATE_SUPPORT and not a.contradicted_by_holes]
    irregular_ids = [s.seg_id for s in segmented.segments if s.kind == "irregular"]
    irregular_mm = sum(s.length_mm for s in segmented.segments if s.kind == "irregular")
    rebuild_ok = {a.axis_id: _rebuild_problem(complete_by_mirror(outline, holes, a, irregular_ids, segmented),
                                              irregular_mm) is None for a in axes} if irregular_ids else {}
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
                         "outline_confirming_mm": round(a.matched_mm, 1),
                         "mirror_would_add_mm2": round(mirror_gain_mm2(a, outline), 1)} for a in axes],
    }
    request = InterpretationRequest(context, marked, facts, [s.seg_id for s in segmented.segments],
                                    [a.axis_id for a in axes], [h[0] for h in holes],
                                    {s.seg_id: s.kind for s in segmented.segments}, rebuild_ok)
    fallback_reason = None
    try:
        interpretation = await interpreter.interpret(request)
    except ReforgeError as exc:
        fallback_reason = exc.to_dict()
        interpretation = await GeometricInterpreter().interpret(request)

    analysis = interpretation.analysis
    verified = verify(analysis, segmented, axes, outline)
    completion, verified = _attempt(verified, segmented, outline, holes)
    if completion is None and interpretation.is_ai and analysis.is_broken and analysis.fracture_segment_ids:
        alternative = _rule_axis(axes, rebuild_ok, outline)
        if alternative is not None and alternative.axis_id != analysis.mirror_axis_id:
            retry = verify(analysis.model_copy(update={"mirror_axis_id": alternative.axis_id}), segmented, axes,
                           outline)
            second, retry = _attempt(retry, segmented, outline, holes)
            if second is not None:
                chosen = analysis.mirror_axis_id
                why = (f"{chosen} can't rebuild this break (see above)" if chosen != NONE_ID
                       else "no axis was chosen")
                completion = second
                note = Note("AXIS_CORRECTED", f"Axis corrected by geometry: {why}. {alternative.axis_id} (support "
                                              f"{alternative.support:.0%}, {alternative.hole_matches} hole(s) matched) "
                                              "rebuilds it, with the reading's fracture picks re-verified under it.",
                            "warning")
                kept = tuple(n for n in verified.notes if n.code != "NO_FRACTURE")
                verified = replace(retry, notes=kept + (note,) + tuple(n for n in retry.notes if n not in kept))
    return Reconstruction(segmented, tuple(axes), context, marked, facts, interpretation, fallback_reason, verified,
                          completion)
