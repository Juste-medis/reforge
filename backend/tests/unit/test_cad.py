"""AT-4: PartSpec → solid → STL, with validation. Deterministic; no model output is executed."""

from pathlib import Path

import numpy as np
import pytest
import trimesh

from reforge.cad.build import build_part, write_stl
from reforge.cad.scad import emit_scad
from reforge.spec.partspec import parse_spec
from reforge.validation.mesh import summarize, validate_part
from tests.unit.specs import bracket_dict, rounded_rect, spec_dict


def _errors(spec) -> list[str]:
    return summarize(validate_part(build_part(spec), spec))["errors"]


def test_bracket_builds_and_validates() -> None:
    spec = parse_spec(bracket_dict(thickness=3.02))
    part = build_part(spec)
    report = summarize(validate_part(part, spec))
    assert report["valid"], report["errors"]
    mesh = part.to_trimesh()
    assert (2 - mesh.euler_number) // 2 == 2  # genus 2: two through-holes
    analytic = (rounded_rect(80, 28, 4).area - 2 * np.pi * 2.1**2) * 3.02
    assert mesh.volume == pytest.approx(analytic, rel=5e-4)  # polygonal circles: chord error ≤ 0.005 mm
    assert mesh.bounds == pytest.approx(np.array([[-40, -14, 0], [40, 14, 3.02]]), abs=1e-6)


def test_stl_round_trip(tmp_path: Path) -> None:
    spec = parse_spec(bracket_dict())
    part = build_part(spec)
    path = write_stl(part, tmp_path / "model.stl")
    loaded = trimesh.load(path, file_type="stl")
    assert loaded.is_watertight
    assert loaded.volume == pytest.approx(part.to_trimesh().volume, rel=1e-6)


def test_hole_compensation_enlarges_holes() -> None:
    base = build_part(parse_spec(bracket_dict())).to_trimesh().volume
    comp = build_part(parse_spec(bracket_dict(fit={"hole_offset_mm": 0.2}))).to_trimesh().volume
    expected_loss = 2 * np.pi * ((2.2) ** 2 - 2.1**2) * 3.0
    assert base - comp == pytest.approx(expected_loss, rel=2e-3)


def test_outline_offset_grows_the_part() -> None:
    spec = parse_spec(bracket_dict(fit={"outline_offset_mm": 0.2}))
    bounds = build_part(spec).to_trimesh().bounds
    assert bounds[1][:2] - bounds[0][:2] == pytest.approx(np.array([80.4, 28.4]), abs=1e-3)
    assert not _errors(spec)


def test_concave_500_point_outline_is_watertight() -> None:
    a = np.linspace(0, 2 * np.pi, 500, endpoint=False)
    r = 30 + 8 * np.cos(7 * a)
    spec = parse_spec(spec_dict(np.column_stack([r * np.cos(a), r * np.sin(a)]), [("H0", 0, 0, 6.0)]))
    assert not _errors(spec)


def test_clockwise_outline_builds_the_same_solid() -> None:
    ccw = parse_spec(bracket_dict())
    data = bracket_dict()
    data["outline"]["points"] = data["outline"]["points"][::-1]
    cw = parse_spec(data)
    assert build_part(cw).to_trimesh().volume == pytest.approx(build_part(ccw).to_trimesh().volume, rel=1e-9)


def test_printability_warnings() -> None:
    thin_arm = np.array([[-20, -5], [20, -5], [20, 5], [0.25, 5], [0.25, 25], [-0.25, 25], [-0.25, 5], [-20, 5]])
    report = summarize(validate_part(build_part(parse_spec(spec_dict(thin_arm, [("H0", -12, 0, 0.8)]))),
                                     parse_spec(spec_dict(thin_arm, [("H0", -12, 0, 0.8)]))))
    assert report["valid"]  # warnings don't block
    assert "min_wall_thickness" in report["warnings"] and "H0_printable_diameter" in report["warnings"]


def test_scad_is_parametric_and_sanitised() -> None:
    data = bracket_dict()
    data["thickness"]["evidence"] = [{"kind": "caliper", "detail": "3 readings\n}; module evil() {"}]
    text = emit_scad(parse_spec(data), job_id="job-1")
    assert "thickness = 3.0000; // MEASURED ±0.020 mm" in text
    assert "H0_d = 4.2000;" in text and "cylinder(d = H1_d + hole_comp" in text
    comment_lines = [line for line in text.splitlines() if "caliper" in line]
    assert comment_lines and all("{" not in line and "}" not in line for line in comment_lines)
    assert text.count("{") == text.count("}") == 1  # only the single difference() block
