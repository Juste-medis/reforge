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
from reforge.geometry.bridging import complete_by_bridge
from reforge.geometry.completion import Completion, complete_by_mirror
from reforge.geometry.segments import SegmentedOutline, segment_outline
from reforge.geometry.symmetry import (
    MirrorAxis,
    asserted_axis,
    find_mirror_axes,
    local_support,
    mirror_gain_mm2,
    rescore,
)
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


@dataclass(frozen=True)
class Guidance:
    """Human-in-the-loop: the Studio user's choices. The interpreter still names the part and judges the family;
    the geometric verification still judges the axis and the fracture — guidance steers, it never bypasses a check.
    ``family_override`` is the one explicit bypass: the user asserts a flat model of a non-flat reading, and the
    report carries that assertion."""
    axis_id: str | None = None  # a candidate id (A0…), or None/"none" for no axis
    assert_angle_deg: float | None = None  # or: a user-asserted axis (U0) at this angle…
    assert_point_mm: tuple[float, float] | None = None  # …through this point (the centroid when None)
    fracture_ids: tuple[str, ...] = ()
    exclude_ids: tuple[str, ...] = ()  # outline spans the user marked as designed asymmetry (a spark plug's side
    # electrode, an engraving): kept as photographed, and their mirror never counts for or against the axis
    damage_hole_ids: tuple[str, ...] = ()  # observed holes the user marked as damage (interior voids, not holes)
    source_hole_ids: tuple[str, ...] | None = None  # or: exactly which holes to mirror from (None = auto)
    family_override: bool = False
    note: str = ""


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
    unexplained = float(sum(r.area_mm2 for r in completion.regions if not r.filled and not r.echo))
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


def _extend_fracture(fracture_ids: tuple[str, ...], segmented: SegmentedOutline,
                     blocked: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The accepted fracture, grown along the outline over neighbouring rough segments and the short smooth
    stretches (at most ``MAX_BRIDGE_MM``) between rough ones. Never past a long smooth stretch, so an intact edge
    stays intact — and never onto ``blocked`` (user-excluded asymmetry) spans."""
    if not fracture_ids:
        return fracture_ids
    segs = segmented.segments
    n = len(segs)
    index = {s.seg_id: i for i, s in enumerate(segs)}
    chosen = {index[sid] for sid in fracture_ids if sid in index}
    stop = {index[sid] for sid in blocked if sid in index}
    grown = set(chosen)
    for start in sorted(chosen):
        for step in (1, -1):
            i, bridge = start, []
            while True:
                i = (i + step) % n
                if i in grown or i in stop or len(grown) + len(bridge) >= n:
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
             exclusions: dict[str, list], *, damage: tuple = (), traced: tuple = (),
             judge_holes: list | None = None, observed_holes: list | None = None,
             observed_traced: tuple | None = None,
             exclude_ids: tuple[str, ...] = ()) -> tuple[Completion | None, Verified]:
    """The mirror completion a verified reading allows, or None with the reason added to its notes.

    With explicit Studio sources, ``holes``/``traced`` are the build list, while ``judge_holes`` (every fitted
    hole) still judges the axis and ``observed_holes``/``observed_traced`` block duplicate mirrors."""
    holes_only = bool(damage) and not verified.fracture_ids
    if verified.axis is None or (not verified.fracture_ids and not holes_only):
        return None, verified
    extended = _extend_fracture(verified.fracture_ids, segmented, exclude_ids)
    if extended != verified.fracture_ids:
        added = [sid for sid in extended if sid not in verified.fracture_ids]
        verified = replace(verified, fracture_ids=extended, notes=verified.notes + (Note(
            "FRACTURE_EXTENDED", f"The accepted fracture continues over {', '.join(added)}: rough segments beside "
                                 "it, and the short smooth stretches between them, are one break.", "info"),))
    spans = [segmented.span(segmented.by_id(sid)) for sid in verified.fracture_ids]
    spans += [segmented.span(s) for s in exclusions.get(verified.axis.axis_id, [])]
    # User-excluded asymmetry never counts for or against the axis: not in support either (a thread helix is
    # genuinely phase-shifted; the area gate still sees its slivers, and the other gates still apply).
    spans += [segmented.span(segmented.by_id(sid)) for sid in exclude_ids]
    asserted = verified.axis.axis_id == "U0"
    axis = rescore(verified.axis, outline, judge_holes if judge_holes is not None else holes,
                   np.concatenate(spans) if spans else None, damage=damage, refine=not asserted)
    if axis.contradicted_by_holes or (axis.support < MIN_AXIS_SUPPORT and not asserted):
        reason = (f"{axis.axis_id} maps holes onto solid material: the holes disprove it."
                  if axis.contradicted_by_holes else
                  f"With the accepted fracture left out, {axis.axis_id} drops to {axis.support:.0%} "
                  "support: no mirror reconstruction.")
        return None, replace(verified, axis=None, notes=verified.notes + (Note("AXIS_WEAK", reason, "rejected"),))
    completion = complete_by_mirror(outline, holes, axis, list(verified.fracture_ids), segmented,
                                    damage=damage, traced=traced, observed_holes=observed_holes,
                                    observed_traced=observed_traced, exclude_ids=list(exclude_ids))
    fracture_mm = sum(segmented.by_id(sid).length_mm for sid in verified.fracture_ids)
    problem = _rebuild_problem(completion, fracture_mm)
    if problem is not None and not (holes_only and completion.inferred_holes
                                    and problem[0] == "AXIS_REBUILDS_NOTHING"):
        return None, replace(verified, axis=None, notes=verified.notes + (Note(*problem, "rejected"),))
    if holes_only and problem is not None:
        verified = replace(verified, notes=verified.notes + (Note(
            "HOLES_ONLY", f"Outline intact: {len(completion.inferred_holes)} holes inferred by mirror into the "
                          "marked damage, nothing added to the outline.", "info"),))
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
               axes: list[MirrorAxis], damage: tuple = ()
               ) -> tuple[SegmentedOutline, list[MirrorAxis], dict[str, list], dict[str, list]]:
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
            measured = rescore(current, outline, holes, exclude, damage=damage)
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


def _holes(profile: RefinedProfile, exclude: tuple[str, ...] = ()
           ) -> list[tuple[str, tuple[float, float], float]]:
    return [(c.hole_id, c.fit.center, c.fit.radius)
            for c in profile.holes if c.fit is not None and not c.doubt and c.hole_id not in exclude]


def _guided_note(guidance: Guidance, analysis, observed_ids: tuple[str, ...]) -> str:
    axis = analysis.mirror_axis_id if analysis.mirror_axis_id != NONE_ID else "no axis"
    frac = ", ".join(analysis.fracture_segment_ids) or "no fracture segments"
    note = f"Rebuilt along your axis ({axis}) with your fracture ({frac}): the geometric checks still applied."
    if guidance.assert_angle_deg is not None and guidance.assert_point_mm is not None:
        x, y = guidance.assert_point_mm
        note += f" Axis through your point ({x:.1f}, {y:.1f}) mm."
    if guidance.exclude_ids:
        note += (f" {', '.join(guidance.exclude_ids)} marked by you as designed asymmetry: kept as photographed, "
                 "their mirror never counted for or against the axis.")
    if guidance.damage_hole_ids:
        note += (f" {', '.join(guidance.damage_hole_ids)} marked by you as damage, not holes: dropped from the "
                 "model, mirrors into them inferred.")
    if guidance.source_hole_ids is not None:
        left_out = [hid for hid in observed_ids if hid not in guidance.source_hole_ids]
        if left_out:
            note += (f" Exact build list: {', '.join(guidance.source_hole_ids)}. Left out of the model "
                     f"(still shown dotted): {', '.join(left_out)}.")
        else:
            note += " Every observed hole is in the build list."
    if guidance.family_override:
        note += (" You overrode the family reading: this is a flat model of a part the AI did not read as flat — "
                 "an approximation, not a measured replacement.")
    if guidance.note:
        note += f" Your note: {guidance.note}"
    return note


async def reconstruct(view: RectifiedView, footprint: RefinedProfile, interpreter, *, thickness_mm: float,
                      guidance: Guidance | None = None) -> Reconstruction:
    segmented = segment_outline(footprint.outer.points_mm)
    outline = segmented.points
    by_hole = {c.hole_id: c for c in footprint.holes}
    sources = None
    if guidance is not None:
        unknown_holes = [hid for hid in (*guidance.damage_hole_ids, *(guidance.source_hole_ids or ()))
                         if hid not in by_hole]
        if unknown_holes:
            raise ReforgeError("GUIDE_UNKNOWN_HOLE", f"{', '.join(unknown_holes)}: no such hole in this photo.",
                               "Pick holes from the listed ids (the Studio shows every hole with its size).")
        conflict = set(guidance.damage_hole_ids) & set(guidance.source_hole_ids or ())
        if conflict:
            raise ReforgeError("GUIDE_CONFLICT", f"{', '.join(sorted(conflict))}: damage and source at once.",
                               "A hole is either damage to drop or a source to mirror from, not both.")
        if guidance.source_hole_ids is not None:
            sources = tuple(dict.fromkeys(guidance.source_hole_ids))
    damage_ids = tuple(dict.fromkeys(guidance.damage_hole_ids)) if guidance is not None else ()
    damage_rings = tuple(np.asarray(by_hole[hid].contour.points_mm) for hid in damage_ids)
    traced_display = tuple((c.hole_id, np.asarray(c.contour.points_mm))
                           for c in footprint.holes if c.fit is None)
    if sources is None:
        traced = tuple((c.hole_id, np.asarray(c.contour.points_mm))
                       for c in footprint.holes
                       if c.fit is None and not c.doubt and c.hole_id not in damage_ids)
        holes = _holes(footprint, exclude=damage_ids)
        judge, observed, observed_traced = None, None, None
    else:  # explicit sources: the user's eyes pick what gets mirrored, but what exists still judges — the
        # contradiction check sees every fitted hole (mirrors into them block duplicates), and so does the
        # occupancy test, through ``observed``. Only the build list itself is exactly the confirmed holes.
        traced = tuple((c.hole_id, np.asarray(c.contour.points_mm))
                       for c in footprint.holes
                       if c.fit is None and c.hole_id in sources and c.hole_id not in damage_ids)
        holes = [(c.hole_id, c.fit.center, c.fit.radius)
                 for c in footprint.holes
                 if c.fit is not None and c.hole_id in sources and c.hole_id not in damage_ids]
        auto = _holes(footprint, exclude=damage_ids)
        judge = auto + [h for h in holes if h[0] not in {a[0] for a in auto}]
        observed = [(c.hole_id, c.fit.center, c.fit.radius)
                    for c in footprint.holes if c.fit is not None and c.hole_id not in damage_ids]
        observed_traced = tuple((c.hole_id, np.asarray(c.contour.points_mm))
                                for c in footprint.holes
                                if c.fit is None and c.hole_id not in damage_ids)
    # Discovery always sees every fitted hole: the user's build list must not hide candidates (one hole alone
    # gives no pair bisector, so picking a single source would otherwise lose the true axis).
    discover = _holes(footprint, exclude=damage_ids)
    shown = observed if observed is not None else holes
    # No exclusion here: "irregular" kinds are unreliable on patterned outlines (gear teeth read as fracture and
    # would let wrong axes reach 100 % on the remnant). No support or hole-contradiction filter either: a big break
    # caps every support (a sprocket's true axis at 0.40), and lost holes only stop contradicting it once the break
    # is known. The mirror pass re-measures with honest exclusion and filters afterwards.
    axes = find_mirror_axes(outline, discover, keep=CANDIDATE_AXES, damage=damage_rings)
    segmented, axes, exclusions, rough = _mirror_pass(segmented, outline, discover, axes, damage_rings)
    if guidance is not None and guidance.assert_angle_deg is not None:
        if not np.isfinite(guidance.assert_angle_deg):
            raise ReforgeError("GUIDE_BAD_ANGLE", f"{guidance.assert_angle_deg} is not an angle in degrees.",
                               "Assert the mirror axis as an angle in degrees (0–180, 90 is vertical).")
        point = None
        if guidance.assert_point_mm is not None:
            point = np.asarray(guidance.assert_point_mm, dtype=np.float64)
            if point.shape != (2,) or not np.isfinite(point).all():
                raise ReforgeError("GUIDE_BAD_POINT", f"{guidance.assert_point_mm} is not a point in mm.",
                                   "Assert the axis pivot as an (x, y) point in millimetres, in the photo frame.")
        axes = [*axes, asserted_axis(float(guidance.assert_angle_deg) % 180.0, outline,
                                     judge if judge is not None else holes, damage_rings, point=point)]
    rebuild_ok = {}
    for a in axes:
        own = rough.get(a.axis_id, [])
        own_mm = sum(segmented.by_id(sid).length_mm for sid in own)
        rebuild_ok[a.axis_id] = bool(own) and _rebuild_problem(
            complete_by_mirror(outline, discover, a, own, segmented), own_mm) is None
    context, marked = render_set_of_mark(view, segmented, axes, shown, traced=traced_display)
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
        "holes": [{"id": hid, "diameter_mm": round(2 * r, 2)} for hid, _, r in shown],
        "all_holes": [{"id": c.hole_id, "kind": "circle" if c.fit is not None else "traced",
                       "area_mm2": round(float(c.contour.area_mm2), 1),
                       "centre_mm": [round(float(c.contour.points_mm[:, 0].mean()), 1),
                                     round(float(c.contour.points_mm[:, 1].mean()), 1)],
                       "doubted": c.doubt is not None} for c in footprint.holes],
        "mirror_axes": [{"id": a.axis_id, "direction_deg": round(a.angle_deg, 1), "support": round(a.support, 3),
                         "holes_matched": a.hole_matches, "holes_contradicting": a.hole_mismatches,
                         "outline_confirming_mm": round(a.matched_mm, 1),
                         "mirror_would_add_mm2": round(mirror_gain_mm2(a, outline), 1)} for a in axes],
    }
    request = InterpretationRequest(context, marked, facts, [s.seg_id for s in segmented.segments],
                                    [a.axis_id for a in axes], [h[0] for h in shown],
                                    {s.seg_id: s.kind for s in segmented.segments}, rebuild_ok,
                                    {aid: tuple(sids) for aid, sids in rough.items()})
    fallback_reason = None
    try:
        interpretation = await interpreter.interpret(request)
    except ReforgeError as exc:
        fallback_reason = exc.to_dict()
        interpretation = await GeometricInterpreter().interpret(request)

    analysis = interpretation.analysis
    if guidance is not None:
        known_axes = {a.axis_id for a in axes}
        known_segs = {s.seg_id for s in segmented.segments}
        if guidance.axis_id not in (None, "", "none", NONE_ID) and guidance.axis_id not in known_axes:
            raise ReforgeError("GUIDE_UNKNOWN_AXIS", f"{guidance.axis_id} is not a candidate axis of this photo.",
                               "Pick one of the listed axes (the set-of-mark image shows them).")
        unknown_segs = [sid for sid in (*guidance.fracture_ids, *guidance.exclude_ids)
                          if sid not in known_segs]
        if unknown_segs:
            raise ReforgeError("GUIDE_UNKNOWN_SEGMENT", f"{', '.join(unknown_segs)}: no such outline segment.",
                               "Pick segments from the listed ids (the set-of-mark image shows them).")
        conflict = set(guidance.fracture_ids) & set(guidance.exclude_ids)
        if conflict:
            raise ReforgeError("GUIDE_CONFLICT",
                               f"{', '.join(sorted(conflict))}: fracture and excluded asymmetry at once.",
                               "A span is either the break to rebuild or designed asymmetry to keep, not both.")
        axis_id = NONE_ID if guidance.axis_id in (None, "", "none") else guidance.axis_id
        if guidance.assert_angle_deg is not None:  # an asserted angle wins over a picked candidate
            axis_id = "U0"
        analysis = analysis.model_copy(update={
            "mirror_axis_id": axis_id, "symmetry": "mirror" if axis_id != NONE_ID else analysis.symmetry,
            "fracture_segment_ids": tuple(dict.fromkeys(guidance.fracture_ids)),
            "is_broken": bool(guidance.fracture_ids or axis_id != NONE_ID or damage_ids)})
        interpretation = replace(interpretation, detail={**interpretation.detail, "guided": {
            "axis_id": None if axis_id == NONE_ID else axis_id,
            "assert_angle_deg": guidance.assert_angle_deg, "assert_point_mm": guidance.assert_point_mm,
            "fracture_ids": list(analysis.fracture_segment_ids),
            "exclude_ids": list(dict.fromkeys(guidance.exclude_ids)), "damage_hole_ids": list(damage_ids),
            "source_hole_ids": list(sources) if sources is not None else None,
            "family_override": guidance.family_override, "note": guidance.note}})
    holes_only = bool(damage_ids) and not analysis.fracture_segment_ids
    if analysis.mirror_axis_id == "U0" and analysis.fracture_segment_ids:
        # The asserted axis was scored knowing nothing of the break: re-measure it with the picked fracture
        # excluded, like the mirror pass does for discovered axes — mirrors of holes lost in the break land
        # nearest the fracture and stop contradicting it (a crankshaft pulley's three lost holes, 2026-11-04).
        u0 = next((a for a in axes if a.axis_id == "U0"), None)
        if u0 is not None:
            known = {s.seg_id for s in segmented.segments}
            spans = [segmented.span(segmented.by_id(sid)) for sid in analysis.fracture_segment_ids if sid in known]
            if guidance is not None:
                spans += [segmented.span(segmented.by_id(sid)) for sid in guidance.exclude_ids if sid in known]
            rescored = rescore(u0, outline, judge if judge is not None else holes,
                               np.concatenate(spans) if spans else None, damage=damage_rings, refine=False)
            axes = [rescored if a.axis_id == "U0" else a for a in axes]
    verified = verify(analysis, segmented, axes, outline, holes_only=holes_only)
    if guidance is not None:
        notes = list(verified.notes)
        observed_ids = tuple(hid for hid in by_hole if hid not in damage_ids)
        notes.append(Note("USER_GUIDED", _guided_note(guidance, analysis, observed_ids), "info"))
        if verified.fracture_ids and verified.axis is None:
            notes.append(Note("GUIDE_NO_AXIS", "Fracture segments were picked but no axis: nothing is reconstructed.",
                              "warning"))
        verified = replace(verified, notes=tuple(notes))
    completion, verified = _attempt(verified, segmented, outline, holes, exclusions, damage=damage_rings,
                                      traced=traced, judge_holes=judge, observed_holes=observed,
                                      observed_traced=observed_traced,
                                      exclude_ids=guidance.exclude_ids if guidance is not None else ())
    if (completion is None and guidance is None and interpretation.is_ai and analysis.is_broken
            and analysis.fracture_segment_ids):
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
    if completion is None and verified.fracture_ids:
        # Last resort, no mirror involved: close the break by extending the intact edges beside it. The bridge's
        # own gates judge every span; a span they refuse stays as photographed.
        bridged, bridge_notes = complete_by_bridge(outline, segmented, list(verified.fracture_ids))
        if bridged is not None:
            completion = bridged
            kept = tuple(n for n in verified.notes if n.code != "GUIDE_NO_AXIS")
            verified = replace(verified, notes=kept + tuple(Note(*b) for b in bridge_notes))
        elif bridge_notes:
            code, message, _ = bridge_notes[0]
            verified = replace(verified, notes=verified.notes + (Note(code, message, "info"),))
    return Reconstruction(segmented, tuple(axes), context, marked, facts, interpretation, fallback_reason, verified,
                          completion)
