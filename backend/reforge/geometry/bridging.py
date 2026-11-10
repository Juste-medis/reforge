"""Smooth-bridge completion: rebuild a break by extending the intact edges beside it.

When no mirror axis rebuilds the break (an asymmetric part, or the other side is gone too), each accepted fracture
span is closed by extending its two intact neighbours — fitted lines, or an arc's end tangent — to their
intersection (a corner), or straight across when the neighbours are collinear (a nick in a straight edge). No
priors, no guessing: the bridge stands only when the geometry allows it, and everything it adds is INFERRED with a
2σ from the neighbours' fit residuals.

Gates (each failure is a named reason, and the span stays as photographed):
- neighbours: both kind ``line`` or ``arc``, at least ``BRIDGE_MIN_NEIGHBOUR_MM`` long, fitting within
  ``BRIDGE_MAX_FIT_RMS_MM`` (a wavy neighbour proves nothing about where the edge was heading);
- corner: the extensions meet at 20–160°, forward of both span ends, within ``BRIDGE_MAX_REACH_MM`` and four gap
  lengths (a far meeting point is an extrapolation, not a measurement);
- outside: the bridge never cuts photographed material (a splayed fragment stays, the bridge is refused instead),
  and the completed outline still contains the photographed one;
- small: each bridge adds at most 5 % of the outline area and 500 mm² (a bridge closes a break, it doesn't invent
  a part).
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient

from reforge.geometry.circle import fit_circle
from reforge.geometry.completion import (
    MIN_COMPONENT_MM2,
    ON_EDGE_MM,
    RUN_SPACING_MM,
    Completion,
    Region,
    Run,
)
from reforge.geometry.contour import resample_closed
from reforge.geometry.segments import SegmentedOutline

BRIDGE_MAX_FIT_RMS_MM = 0.15
BRIDGE_MIN_NEIGHBOUR_MM = 5.0
BRIDGE_MIN_ANGLE_DEG = 20.0
BRIDGE_MAX_ANGLE_DEG = 160.0
BRIDGE_COLLINEAR_DEG = 8.0  # below this the neighbours are one straight edge: bridge straight across
BRIDGE_MAX_REACH_MM = 30.0
BRIDGE_MAX_REACH_GAPS = 4.0
BRIDGE_MAX_AREA_FRAC = 0.05
BRIDGE_MAX_AREA_MM2 = 500.0
BRIDGE_OUTSIDE_TOL_MM = 0.1
BRIDGE_CONTAIN_TOL_MM2 = 0.5


def _fit_ray(span: np.ndarray, at_end: bool) -> tuple[np.ndarray, np.ndarray, float] | None:
    """A ray (origin, unit direction, fit RMS) extending ``span`` past its fracture-side end.

    ``at_end``: the fracture touches the span's last point (predecessor) rather than its first (successor). Lines
    fit by SVD; arcs contribute their end tangent (a rounded shoulder still says where the edge was heading).
    """
    if len(span) < 3:
        return None
    anchor = span[-1] if at_end else span[0]
    centre = span.mean(axis=0)
    direction = np.linalg.svd(span - centre, full_matrices=False)[2][0]
    dev = np.abs((span - centre) @ np.array([-direction[1], direction[0]]))
    line_rms = float(np.sqrt(np.mean(dev**2)))
    rms, tangent = line_rms, direction
    if len(span) >= 5:
        fit = fit_circle(span)
        if 0.3 <= fit.radius <= 1000.0:
            radial = np.abs(np.linalg.norm(span - np.asarray(fit.center), axis=1) - fit.radius)
            if float(radial.max()) < float(dev.max()):
                radial_at = anchor - np.asarray(fit.center)
                tangent = np.array([-radial_at[1], radial_at[0]]) / (np.linalg.norm(radial_at) + 1e-12)
                rms = float(np.sqrt(np.mean(radial**2)))
    # Orient from the neighbour's far end toward the gap.
    if float(tangent @ (anchor - span[0 if at_end else -1])) < 0:
        tangent = -tangent
    return anchor, tangent / (np.linalg.norm(tangent) + 1e-12), rms


def _groups(fracture_idx: set[int], n: int) -> list[list[int]]:
    """Maximal runs of consecutive fracture segments along the outline (wrapping around the end)."""
    if not fracture_idx:
        return []
    order = sorted(fracture_idx)
    runs, run = [], [order[0]]
    for i in order[1:]:
        if i == run[-1] + 1:
            run.append(i)
        else:
            runs.append(run)
            run = [i]
    runs.append(run)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == n - 1:
        runs[0] = runs.pop() + runs[0]
    return runs


def complete_by_bridge(outline_mm: np.ndarray, segmented: SegmentedOutline,
                       fracture_ids: list[str]) -> tuple[Completion | None, list[tuple[str, str, str]]]:
    """Close accepted fracture spans by extending their intact neighbours. Returns the completion (method
    ``"bridge"``, no axis) and accept notes, or None with one rejection reason per span group."""
    notes: list[tuple[str, str, str]] = []
    by_id = {s.seg_id: i for i, s in enumerate(segmented.segments)}
    idx = sorted({by_id[sid] for sid in fracture_ids if sid in by_id})
    if not idx:
        return None, [("BRIDGE_NO_SPAN", "No accepted fracture span to bridge.", "info")]
    n = len(segmented.segments)
    observed = Polygon(np.asarray(outline_mm, dtype=float)).buffer(0)
    if observed.is_empty or not observed.is_valid:
        return None, [("BRIDGE_BAD_OUTLINE", "The photographed outline is not a usable polygon.", "info")]
    area_cap = min(BRIDGE_MAX_AREA_FRAC * observed.area, BRIDGE_MAX_AREA_MM2)

    groups = _groups(set(idx), n)
    # (group, bridge polyline, source, u_2sigma, evidence_mm, added-area estimate)
    bridges: list[tuple[list[int], np.ndarray, str, float, float, float]] = []
    for group in groups:
        # Short smooth bits between the break and the clean edges are transition, not evidence: absorb them
        # (the mirror path's FRACTURE_EXTENDED, same idea), so the bridge stands on full-length edges. The span
        # stays contiguous in walk order (mod n), possibly wrapping around the outline end.
        span = list(group)
        while len(span) < n - 1:
            grew = False
            pred_idx, succ_idx = (span[0] - 1) % n, (span[-1] + 1) % n
            if pred_idx == span[-1] or succ_idx == span[0]:
                break
            for idx, side in ((pred_idx, "pred"), (succ_idx, "succ")):
                nxt = segmented.segments[idx]
                if nxt.kind in ("line", "arc") and nxt.length_mm < BRIDGE_MIN_NEIGHBOUR_MM:
                    span.insert(0, idx) if side == "pred" else span.append(idx)
                    grew = True
            if not grew:
                break
        first, last = span[0], span[-1]
        pred, succ = segmented.segments[(first - 1) % n], segmented.segments[(last + 1) % n]
        names = f"S{first}…S{last}" if len(span) > 1 else f"S{first}"
        if (first - 1) % n in span or (last + 1) % n in span:
            notes.append(("BRIDGE_ABSORB", f"{names}: the break runs into its own neighbours: kept as "
                                           "photographed.", "info"))
            continue
        if pred.kind not in ("line", "arc") or succ.kind not in ("line", "arc"):
            notes.append(("BRIDGE_NEIGHBOUR", f"{names}: the spans beside the break are not clean lines or arcs "
                                              f"({pred.seg_id} {pred.kind}, {succ.seg_id} {succ.kind}), so there is "
                                              "no edge to extend.", "info"))
            continue
        if pred.length_mm < BRIDGE_MIN_NEIGHBOUR_MM or succ.length_mm < BRIDGE_MIN_NEIGHBOUR_MM:
            notes.append(("BRIDGE_SHORT", f"{names}: the neighbouring edges are too short "
                                          f"({pred.length_mm:.1f}/{succ.length_mm:.1f} mm) to say where the edge was "
                                          "heading.", "info"))
            continue
        fit_a = _fit_ray(segmented.span(pred), at_end=True)
        fit_b = _fit_ray(segmented.span(succ), at_end=False)
        if fit_a is None or fit_b is None:
            notes.append(("BRIDGE_FIT", f"{names}: a neighbouring edge has too few points to fit.", "info"))
            continue
        (p0, da, rms_a), (p1, db, rms_b) = fit_a, fit_b
        if max(rms_a, rms_b) > BRIDGE_MAX_FIT_RMS_MM:
            notes.append(("BRIDGE_FIT", f"{names}: the neighbouring edges wobble too much (fit RMS "
                                        f"{rms_a:.3f}/{rms_b:.3f} mm) to extend with confidence.", "info"))
            continue
        gap = float(np.linalg.norm(p1 - p0))
        angle = float(np.degrees(np.arccos(float(np.clip(da @ db, -1.0, 1.0)))))
        # The rays point into the gap from opposite sides: 180° is one straight edge (a nick), 0° would be
        # two parallel steps (the chord then cuts material and BRIDGE_CUTS refuses it).
        if angle <= BRIDGE_COLLINEAR_DEG or angle >= 180.0 - BRIDGE_COLLINEAR_DEG:
            poly, u, kind = np.array([p0, p1]), 2.0 * (rms_a + rms_b), "straight across the nick"
        else:
            if not (BRIDGE_MIN_ANGLE_DEG <= angle <= BRIDGE_MAX_ANGLE_DEG):
                notes.append(("BRIDGE_ANGLE", f"{names}: the extended edges meet at {angle:.0f}°, too "
                                              "shallow or too sharp for a believable corner.", "info"))
                continue
            cross = float(da[0] * db[1] - da[1] * db[0])
            s = float(((p1 - p0)[0] * db[1] - (p1 - p0)[1] * db[0]) / cross) if abs(cross) >= 1e-9 else -1.0
            corner = p0 + s * da
            if s < -BRIDGE_OUTSIDE_TOL_MM or float((corner - p1) @ db) < -BRIDGE_OUTSIDE_TOL_MM:
                notes.append(("BRIDGE_BEHIND", f"{names}: the extended edges meet behind the break, not past "
                                               "it: no corner.", "info"))
                continue
            reach = max(float(np.linalg.norm(corner - p0)), float(np.linalg.norm(corner - p1)))
            if reach > min(BRIDGE_MAX_REACH_MM, BRIDGE_MAX_REACH_GAPS * max(gap, 1.0)):
                notes.append(("BRIDGE_REACH", f"{names}: the implied corner is {reach:.1f} mm away: an "
                                              "extrapolation, not a measurement.", "info"))
                continue
            poly = np.array([p0, corner, p1])
            u = 2.0 * (rms_a + rms_b) / max(np.sin(np.radians(angle)), 0.2)
            kind = f"corner at {angle:.0f}°"
        samples = np.vstack([np.linspace(poly[i], poly[i + 1], 12, endpoint=False)
                             for i in range(len(poly) - 1)] + [poly[-1:]])
        cut = [s for s in samples if observed.contains(shapely.points(s)) and
               shapely.distance(observed.exterior, shapely.points(s)) > BRIDGE_OUTSIDE_TOL_MM]
        if cut:
            notes.append(("BRIDGE_CUTS", f"{names}: the {kind} would cut through photographed material: kept "
                                         "as photographed.", "info"))
            continue
        estimate = _added_estimate(poly, observed)
        if estimate > area_cap:
            notes.append(("BRIDGE_AREA", f"{names}: the {kind} would add {estimate:.0f} mm² (cap {area_cap:.0f}): "
                                         "a bridge closes a break, it doesn't invent a part.", "info"))
            continue
        bridges.append((span, poly, f"smooth bridge of {pred.seg_id}/{succ.seg_id} ({kind})", float(u),
                        float(pred.length_mm + succ.length_mm), float(estimate)))

    if not bridges:
        return None, notes or [("BRIDGE_NONE", "No fracture span could be bridged.", "info")]
    return _assemble(outline_mm, segmented, observed, bridges, notes)


def _added_estimate(poly: np.ndarray, observed: Polygon) -> float:
    """How much the bridge plausibly adds: the triangle/chord it spans, outside the photographed outline."""
    if len(poly) == 2:  # a chord: thicken it by the tolerance so a hairline sliver still measures
        return float(LineString(poly).buffer(BRIDGE_OUTSIDE_TOL_MM).difference(observed).area)
    return float(Polygon(poly).difference(observed).area)


def _assemble(outline_mm: np.ndarray, segmented: SegmentedOutline, observed: Polygon,
              bridges: list[tuple[list[int], np.ndarray, str, float, float, float]],
              notes: list[tuple[str, str, str]]) -> tuple[Completion | None, list[tuple[str, str, str]]]:
    """Splice the bridge polylines into the outline (each fracture group's points are replaced by its bridge)."""
    n = len(segmented.segments)
    by_first = {tuple(g): b for g, *b in bridges}
    bridged = {i for g, *_ in bridges for i in g}
    # A group wrapping around the outline end is walked contiguously by rotating the start past it.
    start = 0
    for g, *_ in bridges:
        if g[0] > g[-1]:
            start = (g[-1] + 1) % n
    points = segmented.points
    closed = np.vstack([points, points[:1]])
    out: list[np.ndarray] = []
    i = start
    for _ in range(n):
        seg = segmented.segments[i]
        group = next((g for g, *_ in bridges if g[0] == i), None)
        if group is None:
            if i not in bridged:
                out.append(closed[seg.start:seg.end + 2])
        else:
            poly = by_first[tuple(group)][0]
            out.append(poly[:-1])  # the bridge end is the next span's start
        i = (i + 1) % n
    completed = np.vstack(out)
    keep = np.ones(len(completed), bool)
    keep[1:] = np.linalg.norm(np.diff(completed, axis=0), axis=1) > 1e-9
    merged = Polygon(completed[keep]).buffer(0)
    if merged.is_empty or not merged.is_valid:
        return None, notes + [("BRIDGE_INVALID", "The spliced outline is not a usable polygon.", "info")]
    geoms = [g for g in getattr(merged, "geoms", [merged]) if g.geom_type == "Polygon" and not g.is_empty]
    outline = orient(Polygon(max(geoms, key=lambda g: g.area).exterior), 1.0)
    if observed.difference(outline).area > BRIDGE_CONTAIN_TOL_MM2:
        return None, notes + [("BRIDGE_CUTS", "The spliced outline drops photographed material: kept as "
                                              "photographed.", "info")]
    pts = resample_closed(np.asarray(outline.exterior.coords)[:-1], RUN_SPACING_MM)

    photo_pts = shapely.points(pts)
    on_photo = shapely.distance(observed.exterior, photo_pts) <= ON_EDGE_MM
    frac_lines = []
    for g, *_ in bridges:
        spans = [segmented.span(segmented.segments[j]) for j in g]
        frac_lines.append(LineString(np.vstack([s[:-1] for s in spans[:-1]] + [spans[-1]])))
    on_fracture = np.zeros(len(pts), dtype=bool)
    for line in frac_lines:
        on_fracture |= shapely.distance(line, photo_pts) <= ON_EDGE_MM
    near: list[str] = [""] * len(pts)
    on_bridge = np.zeros(len(pts), dtype=bool)
    for _, poly, source, _, _, _ in bridges:
        hit = shapely.distance(LineString(poly), photo_pts) <= ON_EDGE_MM
        on_bridge |= hit
        for j in np.flatnonzero(hit):
            near[j] = source
    keys: list[tuple[str, str]] = []
    for j in range(len(pts)):
        if on_photo[j] and not on_fracture[j]:
            keys.append(("OBSERVED", "calibrated photo, refined boundary"))
        elif on_bridge[j]:
            keys.append(("INFERRED", near[j]))
        elif on_fracture[j]:
            keys.append(("UNCERTAIN", "fracture edge left on the outline (not covered by the bridge)"))
        else:
            keys.append(("UNCERTAIN", "junction between photographed and bridged edges"))
    runs = _bridge_runs(keys)
    regions: list[Region] = []
    added = outline.difference(observed)
    sources = [(LineString(b[1]), b[2]) for b in bridges]
    for comp in sorted(getattr(added, "geoms", [added]), key=lambda g: -g.area):
        if comp.geom_type != "Polygon" or comp.is_empty or comp.area < MIN_COMPONENT_MM2:
            continue
        c = shapely.points(np.array([comp.centroid.x, comp.centroid.y]))
        source = min(sources, key=lambda t: shapely.distance(t[0], c))[1]
        regions.append(Region(comp, float(comp.area), True, source))
    if not regions:
        return None, notes + [("BRIDGE_NOTHING", "The bridges add no material: kept as photographed.", "info")]
    accept = [("BRIDGE", f"{b[2]}: {len(b[0])} span(s) closed, "
                         f"{float(sum(r.area_mm2 for r in regions)):.1f} mm² added.", "info") for b in bridges]
    confirmed = float(sum(b[4] for b in bridges))
    u = max(float(b[3]) for b in bridges)
    return (Completion(None, pts, tuple(runs), tuple(regions), (), (), (), confirmed, "bridge", u),
            notes + accept)


def _bridge_runs(keys: list[tuple[str, str]]) -> tuple[Run, ...]:
    """Consecutive points with the same status form a run (bridge sources are full sentences already)."""
    runs: list[Run] = []
    start = 0
    for i in range(1, len(keys) + 1):
        if i < len(keys) and keys[i] == keys[start]:
            continue
        runs.append(Run(start, i - 1, keys[start][0], keys[start][1]))
        start = i
    return tuple(runs)
