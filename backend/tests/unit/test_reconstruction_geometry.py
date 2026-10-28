"""D4 geometry on exact outlines: segments, mirror axes and completion against the intact part (ground truth)."""

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import Point, Polygon, box

from reforge.capture.mat import mat_layout
from reforge.geometry.completion import complete_by_mirror
from reforge.geometry.segments import segment_outline
from reforge.geometry.symmetry import find_mirror_axes
from tests.synthetic.scene import broken_bracket, hero_bracket

LAYOUT = mat_layout("A4")
X0, Y0, X1, Y1 = LAYOUT.free_zone_mm
CX, CY = (X0 + X1) / 2, (Y0 + Y1) / 2
HOLES = [("H0", (CX - 30, CY), 2.1), ("H1", (CX + 30, CY), 2.1)]


def _outline(poly: Polygon, noise: float = 0.0, seed: int = 0) -> np.ndarray:
    pts = np.asarray(Polygon(poly.exterior).segmentize(0.1).exterior.coords)[:-1]
    return pts + np.random.default_rng(seed).normal(0, noise, pts.shape) if noise else pts


def _irregular(so) -> list:
    return [s for s in so.segments if s.kind == "irregular"]


def _offset_from(axis, point) -> float:
    return float(abs((np.asarray(point) - np.asarray(axis.point)) @ axis.normal))


@pytest.mark.parametrize("noise", [0.0, 0.01])
def test_intact_outline_is_lines_and_arcs(noise: float) -> None:
    so = segment_outline(_outline(hero_bracket(LAYOUT), noise))
    assert not _irregular(so)
    lines = sorted(s.length_mm for s in so.segments if s.kind == "line")
    assert lines[-1] == pytest.approx(72.0, abs=1.5) and lines[-2] == pytest.approx(72.0, abs=1.5)


@pytest.mark.parametrize("seed", [0, 3, 7])
def test_fracture_is_found_where_the_part_broke(seed: int) -> None:
    so = segment_outline(_outline(broken_bracket(LAYOUT, seed=seed), 0.01, seed))
    irregular = _irregular(so)
    assert irregular
    assert all(s.midpoint_mm[0] - CX > 32.0 for s in irregular), "irregular segments only along the break"
    assert sum(s.length_mm for s in irregular) > 20.0  # the 28 mm-wide break, meandering


def test_intact_part_has_both_mirror_axes() -> None:
    axes = find_mirror_axes(_outline(hero_bracket(LAYOUT)), HOLES)
    for angle in (90.0, 0.0):
        axis = next(a for a in axes if abs((a.angle_deg - angle + 90) % 180 - 90) < 0.01)
        assert axis.support > 0.99 and axis.hole_matches == 2 and not axis.contradicted_by_holes
        assert _offset_from(axis, (CX, CY)) < 0.01


@pytest.mark.parametrize(("seed", "rotation", "noise"), [(0, 0.0, 0.0), (5, -37.0, 0.01), (2, 61.0, 0.01)])
def test_broken_part_axis_is_pinned_by_the_holes(seed: int, rotation: float, noise: float) -> None:
    part = affinity.rotate(broken_bracket(LAYOUT, seed=seed), rotation, origin=(CX, CY))
    holes = [(h, tuple(np.asarray(affinity.rotate(Point(c), rotation, origin=(CX, CY)).coords)[0]), r)
             for h, c, r in HOLES]
    pts = _outline(part, noise, seed)
    so = segment_outline(pts)
    axes = find_mirror_axes(pts, holes, exclude_mm=np.concatenate([so.span(s) for s in _irregular(so)]))
    lengthwise = (90.0 + rotation) % 180.0
    axis = next(a for a in axes if abs((a.angle_deg - lengthwise + 90) % 180 - 90) < 0.05)
    assert axis.support > 0.99 and axis.hole_matches == 2
    assert _offset_from(axis, (CX, CY)) < 0.02
    assert axis.offset_ambiguity_mm <= 0.5
    # Any other vertical-ish candidate that slid along the part must be contradicted by the holes.
    for other in axes:
        if other is not axis and abs((other.angle_deg - lengthwise + 90) % 180 - 90) < 1.0:
            assert other.contradicted_by_holes


def test_axis_with_nothing_to_pin_it_is_reported_as_ambiguous() -> None:
    """A plate without holes, broken across its whole width: the rebuilt length isn't determined by the photo."""
    plate = box(CX - 40, CY - 14, CX + 40, CY + 14).buffer(-4, quad_segs=16).buffer(4, quad_segs=16)
    broken = plate.difference(Polygon(np.asarray(broken_bracket(LAYOUT, seed=1).exterior.coords)).symmetric_difference(
        Polygon(np.asarray(hero_bracket(LAYOUT).exterior.coords))).buffer(0.01))
    pts = _outline(max(getattr(broken, "geoms", [broken]), key=lambda g: g.area))
    so = segment_outline(pts)
    axes = find_mirror_axes(pts, [], exclude_mm=np.concatenate([so.span(s) for s in _irregular(so)]))
    vertical = next(a for a in axes if abs((a.angle_deg - 90.0 + 90) % 180 - 90) < 1.0)
    assert vertical.offset_ambiguity_mm > 0.5


def _complete(part: Polygon, holes=HOLES):
    pts = _outline(part)
    so = segment_outline(pts)
    fracture = [s.seg_id for s in _irregular(so)]
    axes = find_mirror_axes(so.points, holes, exclude_mm=np.concatenate([so.span(so.by_id(f)) for f in fracture]))
    axis = next(a for a in axes if abs((a.angle_deg - 90.0 + 90) % 180 - 90) < 0.05)
    return complete_by_mirror(so.points, holes, axis, fracture, so), so


def test_completion_rebuilds_the_intact_part_with_provenance() -> None:
    truth = Polygon(hero_bracket(LAYOUT).exterior)
    c, so = _complete(broken_bracket(LAYOUT, seed=0))
    assert Polygon(c.points).hausdorff_distance(truth) < 0.01
    statuses = {r.status for r in c.runs}
    assert statuses <= {"OBSERVED", "INFERRED", "UNCERTAIN"} and {"OBSERVED", "INFERRED"} <= statuses
    inferred = [r for r in c.runs if r.status == "INFERRED"]
    assert all("mirror of S" in r.source and c.axis.axis_id in r.source for r in inferred)
    uncertain = sum(r.end - r.start + 1 for r in c.runs if r.status == "UNCERTAIN")
    assert uncertain <= 4  # only the junction points where the mirror meets the break
    assert {(h.hole_id, h.partner_id) for h in c.hole_checks} == {("H0", "H1"), ("H1", "H0")}
    assert all(h.center_distance_mm < 0.01 for h in c.hole_checks)
    assert c.inferred_uncertainty_mm() < 0.1


def test_designed_asymmetry_is_reported_not_filled() -> None:
    notched = broken_bracket(LAYOUT, seed=1).difference(box(CX - 25, CY - 15, CX - 18, CY - 10))
    c, _ = _complete(notched)
    skipped = [r for r in c.regions if not r.filled]
    assert len(skipped) == 1 and "real asymmetry" in skipped[0].reason
    assert Polygon(c.points).intersection(box(CX - 25, CY - 14, CX - 18, CY - 10)).area < 0.5  # notch kept


def test_a_hole_lost_in_the_break_is_inferred_from_its_mirror() -> None:
    """The break takes the right end hole with it. A surviving symmetric pair of central holes pins the axis, so
    the left end hole's mirror image can stand in for the lost one (without that pin the axis could slide, which
    ``offset_ambiguity_mm`` reports)."""
    centre_pair = [("H1", (CX - 10, CY), 1.6), ("H2", (CX + 10, CY), 1.6)]
    lost = broken_bracket(LAYOUT, seed=2, break_x_mm=26.0)
    for _, (x, y), r in centre_pair:
        lost = lost.difference(Point(x, y).buffer(r, quad_segs=64))
    c, _ = _complete(lost, holes=[HOLES[0], *centre_pair])
    assert c.axis.offset_ambiguity_mm <= 0.5
    (hole,) = c.inferred_holes
    assert hole.source_hole_id == "H0"
    assert hole.radius == pytest.approx(2.1, abs=0.01)
    # The honest test: the reported 2σ covers the real error. Measured 2026-10-28: error 0.030 mm, U 0.043 mm. The
    # axis angle error (0.029°) was 4x its bootstrap σ, so U covers it through the RMS term: D5 replaces the
    # angle σ with a segment jackknife.
    assert np.hypot(hole.center[0] - (CX + 30), hole.center[1] - CY) <= c.inferred_uncertainty_mm()
