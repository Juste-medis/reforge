"""The PartAnalysis contract and its geometric verification.

Model answers here are HAND-WRITTEN FIXTURES (labelled), not Muse Spark output: they exercise validation and
verification. Live model behaviour is tested in tests/live/test_spark_live.py.
"""

from dataclasses import replace

import numpy as np
import pytest
from shapely.geometry import Polygon

from reforge.capture.mat import mat_layout
from reforge.errors import ReforgeError
from reforge.geometry.segments import segment_outline
from reforge.geometry.symmetry import find_mirror_axes
from reforge.reasoning.analysis import build_schema, parse_analysis
from reforge.reasoning.verify import verify
from tests.synthetic.scene import broken_bracket

SEGS, AXES, HOLES = ["S0", "S1", "S2"], ["A0", "A1"], ["H0", "H1"]


def _walk(node, depth=1):
    yield node, depth
    for child in (node.get("properties") or {}).values():
        yield from _walk(child, depth + 1)
    if "items" in node:
        yield from _walk(node["items"], depth + 1)


def test_schema_stays_inside_the_verified_strict_subset() -> None:
    schema = build_schema(SEGS, AXES, HOLES)
    text = str(schema)
    assert "anyOf" not in text and "allOf" not in text and "oneOf" not in text
    for node, depth in _walk(schema):
        assert depth <= 10
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert sorted(node["required"]) == sorted(node["properties"])
    assert schema["properties"]["fracture_segment_ids"]["items"]["enum"] == SEGS
    assert schema["properties"]["mirror_axis_id"]["enum"] == [*AXES, "none"]


def test_schema_with_no_holes_keeps_valid_enums() -> None:
    schema = build_schema(SEGS, [], [])
    assert schema["properties"]["holes"]["items"]["properties"]["hole_id"]["enum"] == ["none"]
    assert schema["properties"]["mirror_axis_id"]["enum"] == ["none"]


FIXTURE = {  # HAND-WRITTEN FIXTURE, not a model answer
    "object_name": "mounting bracket", "family": "extruded_profile", "family_reason": "flat plate",
    "is_broken": True, "fracture_segment_ids": ["S1", "S1"], "fracture_reason": "jagged right end",
    "symmetry": "mirror", "mirror_axis_id": "A1", "symmetry_reason": "left end mirrors the right",
    "holes": [{"hole_id": "H0", "role": "mounting"}, {"hole_id": "H0", "role": "unknown"},
              {"hole_id": "H1", "role": "mounting"}],
    "missing_features": [{"description": "rounded corners of the right end", "near_segment_ids": ["S1"]}],
    "required_measurements": [{"kind": "hole_diameter", "target_id": "H0", "why": "screw fit"}],
}


def test_valid_answer_is_parsed_and_normalised() -> None:
    analysis = parse_analysis({**FIXTURE, "fracture_reason": "x" * 1000}, SEGS, AXES, HOLES)
    assert analysis.fracture_segment_ids == ("S1",)
    assert [h.hole_id for h in analysis.holes] == ["H0", "H1"]
    assert len(analysis.fracture_reason) == 300


@pytest.mark.parametrize("bad", [
    {"fracture_segment_ids": ["S9"]},
    {"mirror_axis_id": "A7"},
    {"holes": [{"hole_id": "H5", "role": "mounting"}]},
    {"required_measurements": [{"kind": "hole_diameter", "target_id": "H9", "why": "x"}]},
    {"family": "spaceship"},
    {"extra_field": 1},
])
def test_answer_outside_the_request_is_rejected(bad: dict) -> None:
    with pytest.raises(ReforgeError) as info:
        parse_analysis({**FIXTURE, **bad}, SEGS, AXES, HOLES)
    assert info.value.code == "INTERPRETATION_INVALID"


def test_invalid_json_is_a_typed_error() -> None:
    with pytest.raises(ReforgeError):
        parse_analysis("{not json", SEGS, AXES, HOLES)


@pytest.fixture(scope="module")
def broken():
    layout = mat_layout("A4")
    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    holes = [("H0", (cx - 30, cy), 2.1), ("H1", (cx + 30, cy), 2.1)]
    pts = np.asarray(Polygon(broken_bracket(layout, seed=0).exterior).segmentize(0.1).exterior.coords)[:-1]
    so = segment_outline(pts)
    irregular = [s.seg_id for s in so.segments if s.kind == "irregular"]
    axes = find_mirror_axes(so.points, holes, exclude_mm=np.concatenate([so.span(so.by_id(i)) for i in irregular]))
    lengthwise = next(a for a in axes if abs((a.angle_deg - 90.0 + 90) % 180 - 90) < 0.1)
    return so, axes, lengthwise, irregular


def _analysis(so, axes, **changes):
    data = {**FIXTURE, "fracture_segment_ids": [], "mirror_axis_id": "none", **changes}
    return parse_analysis(data, [s.seg_id for s in so.segments], [a.axis_id for a in axes], HOLES)


def test_correct_answer_passes_the_cross_check(broken) -> None:
    so, axes, lengthwise, irregular = broken
    result = verify(_analysis(so, axes, fracture_segment_ids=irregular, mirror_axis_id=lengthwise.axis_id),
                    so, axes, so.points)
    assert result.axis == lengthwise and result.fracture_ids == tuple(irregular)
    assert [n.code for n in result.notes] == ["CROSS_CHECK"]


def test_intact_edge_called_a_fracture_is_rejected(broken) -> None:
    so, axes, lengthwise, irregular = broken
    longest = max(so.segments, key=lambda s: s.length_mm).seg_id  # a long straight moulded edge
    result = verify(_analysis(so, axes, fracture_segment_ids=[*irregular, longest], mirror_axis_id=lengthwise.axis_id),
                    so, axes, so.points)
    assert longest not in result.fracture_ids
    assert any(n.code == "FRACTURE_MATCHES_MIRROR" and n.level == "rejected" for n in result.notes)


def test_weak_axis_is_rejected_and_unpicked_fracture_reported(broken) -> None:
    so, axes, lengthwise, irregular = broken
    weak = [replace(a, support=0.5) if a.axis_id == lengthwise.axis_id else a for a in axes]
    result = verify(_analysis(so, weak, fracture_segment_ids=irregular[:1], mirror_axis_id=lengthwise.axis_id),
                    so, weak, so.points)
    assert result.axis is None
    codes = {n.code for n in result.notes}
    assert "AXIS_WEAK" in codes and "FRACTURE_UNPICKED" in codes
