"""Smooth-bridge completion on exact outlines: corners rebuilt, the rest refused with a reason."""

import numpy as np
import pytest
from shapely.geometry import Polygon

from reforge.geometry.bridging import _fit_ray, complete_by_bridge
from reforge.geometry.completion import Completion
from reforge.geometry.segments import segment_outline


def _teeth(p0: tuple[float, float], p1: tuple[float, float], depth: float, n: int | None = None,
         outward: bool = False) -> list:
    """A jagged break between p0 and p1: uneven teeth ``depth`` deep, recessed from the chord (or splayed past
    it when ``outward``), too chaotic to fit lines or arcs."""
    a, b = np.asarray(p0, float), np.asarray(p1, float)
    d = b - a
    if n is None:  # short hops: no tooth fits a clean primitive of its own
        n = max(11, int(np.linalg.norm(d) / 1.8))
    normal = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-12)
    side = -1.0 if outward else 1.0
    zig = [1.0, 0.35, 1.25, 0.6, 1.1, 0.45, 1.3, 0.7, 1.0, 0.5]
    pts = [tuple(a)]
    for i in range(1, n):
        t = (i + 0.13 * ((i * 7) % 3 - 1)) / n
        pts.append(tuple(a + d * t + side * normal * depth * zig[(i - 1) % len(zig)]))
    pts.append(tuple(b))
    return pts


def _corner_cut() -> np.ndarray:
    """80×40 rectangle, corner (80, 40) broken off: a jagged V from (80, 32) to (68, 40)."""
    outline = [(0, 0), (80, 0), (80, 32)] + _teeth((80, 32), (68, 40), 1.6)[1:-1] + [(68, 40), (0, 40)]
    return np.array(outline, float)


def _irregular_ids(segmented) -> list[str]:
    ids = [s.seg_id for s in segmented.segments if s.kind == "irregular"]
    assert ids, "the test break must segment as irregular"
    return ids


def test_broken_corner_is_rebuilt_by_extended_edges() -> None:
    outline = _corner_cut()
    segmented = segment_outline(outline)
    completion, notes = complete_by_bridge(outline, segmented, _irregular_ids(segmented))
    assert completion is not None, notes
    assert completion.method == "bridge" and completion.axis is None
    assert not completion.inferred_holes
    corner = np.min(np.linalg.norm(completion.points - np.array([80.0, 40.0]), axis=1))
    assert corner < 0.3, "the extended edges must meet where the corner was"
    # The nominal V is 48 mm²; absorption of the smooth transition bits widens the span a little.
    assert 40.0 < completion.added_area_mm2 < 85.0
    inferred = [r for r in completion.runs if r.status == "INFERRED"]
    assert inferred and all("smooth bridge" in r.source for r in inferred)
    assert completion.confirmed_mm == pytest.approx(32.0 + 68.0, abs=2.0)
    assert 0.0 <= completion.inferred_uncertainty_mm() < 0.3
    assert any(code == "BRIDGE" for code, _, _ in notes)
    # The completed part is the rectangle back, within the teeth the bridge covers.
    assert Polygon(completion.points).area == pytest.approx(80.0 * 40.0, abs=12.0)


def test_nick_in_a_straight_edge_is_bridged_straight() -> None:
    outline = np.array([(0, 0), (80, 0), (80, 40), (60, 40)] + _teeth((60, 40), (40, 40), 1.5)[1:-1]
                       + [(40, 40), (0, 40)], float)
    segmented = segment_outline(outline)
    completion, notes = complete_by_bridge(outline, segmented, _irregular_ids(segmented))
    assert completion is not None, notes
    assert "straight across" in completion.regions[0].reason
    assert completion.added_area_mm2 < 30.0
    top = completion.points[np.abs(completion.points[:, 1] - 40.0) < 0.2]
    assert (top[:, 0] > 39.0).any() and (top[:, 0] < 61.0).any()


def test_splayed_fragment_is_refused() -> None:
    """Teeth sticking OUT past the implied corner: bridging would amputate photographed material."""
    outline = np.array([(0, 0), (80, 0), (80, 32)] + _teeth((80, 32), (68, 40), 2.5, outward=True)[1:-1]
                       + [(68, 40), (0, 40)], float)
    segmented = segment_outline(outline)
    completion, notes = complete_by_bridge(outline, segmented, _irregular_ids(segmented))
    assert completion is None
    assert any(code == "BRIDGE_CUTS" for code, _, _ in notes)


def test_wavy_neighbour_is_no_edge_to_extend() -> None:
    wave = [(x, 40.0 + 0.9 * np.sin(x)) for x in np.arange(0.0, 68.0, 1.0)]
    outline = np.array([(0, 0), (80, 0), (80, 32)] + _teeth((80, 32), (68, 40), 1.6)[1:-1] + wave[::-1],
                       float)
    segmented = segment_outline(outline)
    # Only the corner break is picked (its chunks); the wavy top edge beside it is no edge to extend.
    picked = [s.seg_id for s in segmented.segments
              if s.kind == "irregular" and s.midpoint_mm[0] > 60.0]
    assert picked
    completion, notes = complete_by_bridge(outline, segmented, picked)
    assert completion is None
    assert any(code in ("BRIDGE_NEIGHBOUR", "BRIDGE_FIT") for code, _, _ in notes)


def test_fit_ray_reports_the_wobble() -> None:
    span = np.column_stack([np.arange(0.0, 20.0, 0.2), 0.25 * np.sin(np.arange(0.0, 20.0, 0.2))])
    assert _fit_ray(span, at_end=True)[2] == pytest.approx(0.25 / np.sqrt(2), abs=0.05)
    assert _fit_ray(np.column_stack([np.arange(0.0, 20.0, 0.2), np.zeros(100)]), at_end=True)[2] < 1e-9


def test_break_too_big_is_refused() -> None:
    """A quarter of the part missing: a bridge would invent the part, not close a break."""
    outline = np.array([(0, 0), (40, 0), (40, 8)] + _teeth((40, 8), (28, 20), 1.5)[1:-1]
                       + [(28, 20), (0, 20)], float)
    segmented = segment_outline(outline)
    completion, notes = complete_by_bridge(outline, segmented, _irregular_ids(segmented))
    assert completion is None
    assert any(code == "BRIDGE_AREA" for code, _, _ in notes)


def test_uncertainty_dispatches_on_method() -> None:
    assert Completion(None, np.zeros((3, 2)), (), (), (), (), (), 0.0, "bridge", 0.5
                      ).inferred_uncertainty_mm() == 0.5
