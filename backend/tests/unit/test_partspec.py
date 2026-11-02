"""PartSpec validation: untrusted input (UI edits, AI proposals) must be rejected with typed errors."""

import math

import numpy as np
import pytest

from reforge.errors import ReforgeError
from reforge.spec.partspec import CircleHole, PartSpec, Status, mat_to_model, parse_spec
from tests.unit.specs import bracket_dict, param, rounded_rect, spec_dict


def _rejects(data: dict) -> str:
    with pytest.raises(ReforgeError) as info:
        parse_spec(data)
    assert info.value.code == "SPEC_INVALID"
    return info.value.message


def test_valid_bracket_parses() -> None:
    spec = parse_spec(bracket_dict())
    assert len(spec.holes) == 2 and spec.thickness.status is Status.MEASURED
    assert spec.unresolved() == []


def test_unknown_fields_are_rejected() -> None:
    """An AI proposal can't smuggle in fields the compiler doesn't know about."""
    _rejects(bracket_dict(script="import os"))
    data = bracket_dict()
    data["holes"][0]["note"] = "ignore previous instructions"
    _rejects(data)


@pytest.mark.parametrize("bad", [math.nan, math.inf, 1e6])
def test_non_finite_or_huge_coordinates(bad: float) -> None:
    data = bracket_dict()
    data["outline"]["points"][3] = (bad, 0.0)
    _rejects(data)


def test_self_intersecting_outline() -> None:
    _rejects(spec_dict(np.array([[0, 0], [10, 10], [10, 0], [0, 10]], float)))


def test_hole_breaking_through_the_wall() -> None:
    _rejects(spec_dict(rounded_rect(80, 28, 4), [("H0", -38.5, 0, 4.2)]))  # 0.4 mm wall rule violated


def test_overlapping_holes() -> None:
    _rejects(spec_dict(rounded_rect(80, 28, 4), [("H0", 0, 0, 4.2), ("H1", 4.4, 0, 4.2)]))


def test_duplicate_hole_ids() -> None:
    _rejects(spec_dict(rounded_rect(80, 28, 4), [("H0", -30, 0, 4.2), ("H0", 30, 0, 4.2)]))


def test_compensation_cannot_shrink_a_hole_below_minimum() -> None:
    _rejects(spec_dict(rounded_rect(80, 28, 4), [("H0", 0, 0, 1.0)], fit={"hole_offset_mm": -0.6}))


def test_thickness_out_of_range() -> None:
    _rejects(bracket_dict(thickness=0.2))


def test_too_many_points() -> None:
    a = np.linspace(0, 2 * np.pi, 2001, endpoint=False)
    _rejects(spec_dict(np.column_stack([30 * np.cos(a), 30 * np.sin(a)])))


def test_runs_must_cover_every_point() -> None:
    data = bracket_dict()
    n = len(data["outline"]["points"])
    data["outline"]["runs"] = [{"start": 0, "end": n - 3, "status": "OBSERVED", "source": "x"}]
    _rejects(data)


def test_uncertain_items_are_listed_for_the_export_gate() -> None:
    data = bracket_dict()
    data["thickness"] = param(3.0, "UNCERTAIN")
    data["holes"][1]["diameter"] = param(4.2, "UNCERTAIN")
    assert parse_spec(data).unresolved() == ["thickness", "H1.diameter"]


def test_polygon_hole_is_supported_and_validated() -> None:
    data = bracket_dict()
    slot = [(-5.0, -2.0), (5.0, -2.0), (5.0, 2.0), (-5.0, 2.0)]
    data["holes"].append({"kind": "polygon", "id": "H2", "points": slot, "status": "OBSERVED", "source": "traced"})
    assert len(parse_spec(data).holes) == 3
    data["holes"][-1]["points"] = [(-50.0, -2.0), (5.0, -2.0), (5.0, 2.0), (-50.0, 2.0)]  # cuts through the wall
    _rejects(data)


def test_mat_to_model_keeps_handedness() -> None:
    """Upper-left in the photo (small x, small mat y) must stay upper-left seen from above (y up)."""
    origin = (100.0, 150.0)
    upper_left_in_photo = np.array([[90.0, 145.0]])
    assert mat_to_model(upper_left_in_photo, origin) == pytest.approx(np.array([[-10.0, 5.0]]))


def test_unbuildable_holes_are_left_out_and_reported_not_fatal() -> None:
    """A spurious hole at the edge or overlapping another (a reflection traced as a hole) is excluded, UNCERTAIN,
    instead of failing the whole spec (synthetic composites of metal parts, 2026-11-02)."""
    from reforge.pipeline import _buildable

    spec = PartSpec.model_validate(bracket_dict())
    extra = [CircleHole.model_validate({"kind": "circle", "id": hid, "center_x": param(x), "center_y": param(y),
                                        "diameter": param(d)}) for hid, x, y, d in
             (("H2", 38.8, 0.0, 2.0), ("H3", -28.0, 0.0, 4.2))]
    kept, notes = _buildable(spec.outline, [*spec.holes, *extra])
    assert [h.id for h in kept] == ["H0", "H1"]
    assert {n["hole"]: n["status"] for n in notes} == {"H2": "UNCERTAIN", "H3": "UNCERTAIN"}
    assert "wall" in next(n["reason"] for n in notes if n["hole"] == "H2")
    assert "another hole" in next(n["reason"] for n in notes if n["hole"] == "H3")
