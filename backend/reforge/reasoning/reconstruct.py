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
from reforge.geometry.symmetry import MirrorAxis, find_mirror_axes, local_support, mirror_gain_mm2, rescore
from reforge.reasoning.analysis import NONE_ID
from reforge.reasoning.interpret import GeometricInterpreter, Interpretation, InterpretationRequest
from reforge.reasoning.setofmark import render_set_of_mark
from reforge.reasoning.verify import MIN_AXIS_SUPPORT, Note, Verified, verify
from reforge.vision.refine import RefinedProfile

MIN_CANDIDATE_SUPPORT = 0.6
MIN_EVIDENCE_RATIO = 1.0  # outline (and holes) confirming the mirror, per mm of outline it invents
MIN_INVENTED_MM = 2.0  # below this the mirror maps the break onto itself: a rebuild that rebuilds nothing
MAX_UNEXPLAINED_ASYMMETRY = 0.35  # mirror-vs-part difference away from any fracture, per mm² the mirror would add
# next to the break: a real break concentrates the asymmetry; an intact real part's natural asymmetry spreads it
# (a real square gasket, 2026-11-03: 70 mm² away from its "rough" spots for 98 mm² next to them)
MAX_EXPOSED_FRACTURE_MM = 2.0  # or 10 % of the fracture: what the mirror may leave uncovered (junctions, roughness)
CANDIDATE_AXES = 4  # a square part has four mirror axes, all fully supported when one side is broken
MISMATCH_SUPPORT = 0.5  # a segment less than half-matching its mirror is break-like under that axis
MAX_BROKEN_FRACTION = 0.75  # a diameter cut mismatches most of the outline (gap-facing spans too)
MIN_BROKEN_MM = 4.0  # less mismatch than this is noise, not a break
MAX_BREAK_TRANSITIONS = 8  # ... and a break is local: at most this many good/bad transitions around the outline
# (a diameter cut mismatches two arcs — the gap side and its counterpart — so four; a wrong axis scatters dozens)


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
    if invented < MIN_INVENTED_MM:
        return ("AXIS_REBUILDS_NOTHING",
                f"The mirror about {a} invents only {invented:.1f} mm of outline: it maps the break onto itself "
                "instead of rebuilding the missing side. No mirror reconstruction with this axis.")
    added = completion.added_area_mm2
    unexplained = float(sum(r.area_mm2 for r in completion.regions if not r.filled))
    if added > 0 and unexplained > MAX_UNEXPLAINED_ASYMMETRY * added:
        return ("AXIS_ASYMMETRIC",
                f"The part differs from its mirror image about {a} by {unexplained:.0f} mm² away from any fracture, "
                f"against {added:.0f} mm² the mirror would add next to the break: it isn't symmetric enough about "
                f"{a} to tell a break from the part's own shape. No mirror reconstruction with this axis.")
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


MAX_BRIDGE_MM = 10.0  # smooth stretch a fracture may cross: a rough edge cut by the decomposer into rough and short
# smooth pieces (an arc of 3 mm, one tooth flank) is one break, not several (a chipped cog, 2026-11-03)
ROUGH_KINDS = ("irregular", "broken")


def _extend_fracture(fracture_ids: tuple[str, ...], segmented: SegmentedOutline) -> tuple[str, ...]:
    """The accepted fracture, grown along the outline over neighbouring rough segments and the short smooth
    stretches (at most ``MAX_BRIDGE_MM``) between rough ones. Never past a long smooth stretch, so an intact edge
    stays intact."""
    if not fracture_ids:
        return fracture_ids
    segs = segmented.segments
    n = len(segs)
    index = {s.seg_id: i for i, s in enumerate(segs)}
    chosen = {index[sid] for sid in fracture_ids if sid in index}
    grown = set(chosen)
    for start in sorted(chosen):
        for step in (1, -1):
            i, bridge = start, []
            while True:
                i = (i + step) % n
                if i in grown or len(grown) + len(bridge) >= n:
                    break
                if segs[i].kind in ROUGH_KINDS:
                    grown.update(bridge)
                    grown.add(i)
                    bridge = []
                    continue
                bridge.append(i)
                if sum(segs[j].length_mm for j in bridge) > MAX_BRIDGE_MM:
                    break
    return tuple(segs[i].seg_id for i in sorted(grown))


def _attempt(verified: Verified, segmented: SegmentedOutline, outline: np.ndarray,
             holes: list[tuple[str, tuple[float, float], float]],
             exclusions: dict[str, list]) -> tuple[Completion | None, Verified]:
    """The mirror completion a verified reading allows, or None with the reason added to its notes."""
    if verified.axis is None or not verified.fracture_ids:
        return None, verified
    extended = _extend_fracture(verified.fracture_ids, segmented)
    if extended != verified.fracture_ids:
        added = [sid for sid in extended if sid not in verified.fracture_ids]
        verified = replace(verified, fracture_ids=extended, notes=verified.notes + (Note(
            "FRACTURE_EXTENDED", f"The accepted fracture continues over {', '.join(added)}: rough segments beside "
                                 "it, and the short smooth stretches between them, are one break.", "info"),))
    spans = [segmented.span(segmented.by_id(sid)) for sid in verified.fracture_ids]
    spans += [segmented.span(s) for s in exclusions.get(verified.axis.axis_id, [])]
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
    if completion.asymmetric_holes:
        missing = ", ".join(sorted(completion.asymmetric_holes))
        verified = replace(verified, notes=verified.notes + (Note(
            "HOLES_UNPAIRED",
            f"{missing}: no mirror partner under {axis.axis_id} — lost in the break and not inferred. "
            "Measure the missing holes before printing.", "warning"),))
    return completion, verified


def _rule_axis(axes: list[MirrorAxis], rebuild_ok: dict[str, bool], outline: np.ndarray) -> MirrorAxis | None:
    """The axis the geometric rule would choose (``GeometricInterpreter``): well supported, no hole against it, a
    trial rebuild that covers the break; then the most holes matched and the most material rebuilt."""
    trusted = [a for a in axes if a.support >= MIN_AXIS_SUPPORT and not a.contradicted_by_holes
               and rebuild_ok.get(a.axis_id, False)]
    return max(trusted, key=lambda a: (a.hole_matches, mirror_gain_mm2(a, outline), a.support), default=None)


def _break_arc(axis: MirrorAxis, segmented: SegmentedOutline, outline: np.ndarray) -> list:
    """The segments that look like a local break under ``axis`` (each matching its mirror less than
    ``MISMATCH_SUPPORT``), or []. Under a true axis the mismatch is the gap side plus its counterpart (a diameter
    cut mismatches two arcs, four transitions); under a wrong axis it scatters around the outline."""
    bad = [i for i, s in enumerate(segmented.segments)
           if local_support(axis, segmented.span(s), outline) < MISMATCH_SUPPORT]
    total_mm = sum(s.length_mm for s in segmented.segments)
    bad_mm = sum(segmented.segments[i].length_mm for i in bad)
    if not bad or bad_mm < MIN_BROKEN_MM or bad_mm > MAX_BROKEN_FRACTION * total_mm:
        return []
    n = len(segmented.segments)
    is_bad = [i in set(bad) for i in range(n)]
    transitions = sum(1 for i in range(n) if is_bad[i] != is_bad[(i + 1) % n])
    if transitions > MAX_BREAK_TRANSITIONS:
        return []
    return [segmented.segments[i] for i in bad]


def _mirror_pass(segmented: SegmentedOutline, outline: np.ndarray,
               holes: list[tuple[str, tuple[float, float], float]],
               axes: list[MirrorAxis]) -> tuple[SegmentedOutline, list[MirrorAxis], dict[str, list], dict[str, list]]:
    """Let each mirror re-decide what is broken: a local mismatch becomes the exclusion the axis is re-measured
    with, so a big break's true axis reaches its honest support (scored exclusion-free first, a sprocket's true axis
    sits at 0.39). Returns the re-labelled outline, the axes that stay in, each axis's exclusion spans (also used
    when the accepted reading is re-measured before completing), and each axis's rough-mismatch segment ids (its own
    fracture evidence: a diagonal's mismatch is not the vertical's). Axes stay out below ``MIN_CANDIDATE_SUPPORT``
    or contradicted by holes after re-measuring (lost holes stop contradicting once the break excludes them).
    Never downgrades."""
    if not axes:
        return segmented, axes, {}, {}
    rescored: list[tuple[MirrorAxis, list]] = []
    for axis in axes:
        current, bad = axis, _break_arc(axis, segmented, outline)
        for _ in range(3):  # EM to a fixed point: a better axis reclassifies fewer intact spans as break
            if not bad:
                break
            exclude = np.concatenate([segmented.span(s) for s in bad])  # bad only: intact "irregular" teeth
            # tips must count as confirming evidence, not hide in the exclusion
            measured = rescore(current, outline, holes, exclude)
            if measured.support < current.support - 1e-9:
                break
            current = measured
            new_bad = _break_arc(current, segmented, outline)
            if {s.seg_id for s in new_bad} == {s.seg_id for s in bad}:
                bad = new_bad
                break
            bad = new_bad
        rescored.append((current, bad))
    rescored.sort(key=lambda t: (-t[0].support, -t[0].matched_mm))
    top, top_bad = rescored[0]
    if top_bad:
        bad_ids = {b.seg_id for b in top_bad}

        def rekind(seg_id: str, kind: str) -> str:
            # Rough and mirror-mismatching: break. A smooth mismatch (a moulded notch, an intact span facing the
            # gap) keeps its kind: from one outline, only roughness tells designed asymmetry from a clean snap,
            # and the decomposer already merges smooth stretches between rough ones into the break.
            if seg_id in bad_ids and kind == "irregular":
                return "broken"
            if kind == "irregular":
                return kind if seg_id in bad_ids else "pattern"
            return kind

        segmented = replace(segmented, segments=tuple(
            replace(s, kind=rekind(s.seg_id, s.kind)) for s in segmented.segments))
    kept = [(a, bad) for a, bad in rescored
            if a.support >= MIN_CANDIDATE_SUPPORT and not a.contradicted_by_holes]
    rough = {a.axis_id: [s.seg_id for s in bad if s.kind == "irregular"] for a, bad in kept}
    return segmented, [a for a, _ in kept], {a.axis_id: bad for a, bad in kept}, rough


def _holes(profile: RefinedProfile) -> list[tuple[str, tuple[float, float], float]]:
    return [(c.hole_id, c.fit.center, c.fit.radius) for c in profile.holes if c.fit is not None and not c.doubt]


async def reconstruct(view: RectifiedView, footprint: RefinedProfile, interpreter, *, thickness_mm: float,
                      ) -> Reconstruction:
    segmented = segment_outline(footprint.outer.points_mm)
    outline = segmented.points
    holes = _holes(footprint)
    # No exclusion here: "irregular" kinds are unreliable on patterned outlines (gear teeth read as fracture and
    # would let wrong axes reach 100 % on the remnant). No support or hole-contradiction filter either: a big break
    # caps every support (a sprocket's true axis at 0.40), and lost holes only stop contradicting it once the break
    # is known. The mirror pass re-measures with honest exclusion and filters afterwards.
    axes = find_mirror_axes(outline, holes, keep=CANDIDATE_AXES)
    segmented, axes, exclusions, rough = _mirror_pass(segmented, outline, holes, axes)
    rebuild_ok = {}
    for a in axes:
        own = rough.get(a.axis_id, [])
        own_mm = sum(segmented.by_id(sid).length_mm for sid in own)
        rebuild_ok[a.axis_id] = bool(own) and _rebuild_problem(
            complete_by_mirror(outline, holes, a, own, segmented), own_mm) is None
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
                                    {s.seg_id: s.kind for s in segmented.segments}, rebuild_ok,
                                    {aid: tuple(sids) for aid, sids in rough.items()})
    fallback_reason = None
    try:
        interpretation = await interpreter.interpret(request)
    except ReforgeError as exc:
        fallback_reason = exc.to_dict()
        interpretation = await GeometricInterpreter().interpret(request)

    analysis = interpretation.analysis
    verified = verify(analysis, segmented, axes, outline)
    completion, verified = _attempt(verified, segmented, outline, holes, exclusions)
    if completion is None and interpretation.is_ai and analysis.is_broken and analysis.fracture_segment_ids:
        alternative = _rule_axis(axes, rebuild_ok, outline)
        if alternative is not None and alternative.axis_id != analysis.mirror_axis_id:
            retry = verify(analysis.model_copy(update={"mirror_axis_id": alternative.axis_id,
                                                       "fracture_segment_ids": tuple(
                                                           rough.get(alternative.axis_id, ())) or
                                                       analysis.fracture_segment_ids}),
                           segmented, axes, outline)
            second, retry = _attempt(retry, segmented, outline, holes, exclusions)
            if second is not None:
                chosen = analysis.mirror_axis_id
                why = (f"{chosen} can't rebuild this break (see above)" if chosen != NONE_ID
                       else "no axis was chosen")
                completion = second
                note = Note("AXIS_CORRECTED", f"Axis corrected by geometry: {why}. {alternative.axis_id} (support "
                                              f"{alternative.support:.0%}, {alternative.hole_matches} hole(s) matched) "
                                              "rebuilds it, with geometry's own fracture evidence under it.",
                            "warning")
                kept = tuple(n for n in verified.notes if n.code != "NO_FRACTURE")
                verified = replace(retry, notes=kept + (note,) + tuple(n for n in retry.notes if n not in kept))
    return Reconstruction(segmented, tuple(axes), context, marked, facts, interpretation, fallback_reason, verified,
                          completion)
