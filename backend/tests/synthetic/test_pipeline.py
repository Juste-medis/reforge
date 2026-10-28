"""M1 end to end on a SYNTHETIC photo, segmented by the classical fallback (a TEST BACKEND, not SAM 3.1)."""

import asyncio
import json
from pathlib import Path

import cv2
import pytest
import trimesh
from shapely.geometry import Point, Polygon, box

from reforge.capture.mat import mat_layout
from reforge.cli import main
from reforge.pipeline import photo_to_stl
from reforge.vision.segment import ClassicalSegmenter
from tests.synthetic.scene import PartShape, hero_bracket, make_camera, render_view

LAYOUT = mat_layout("A4")


def _asymmetric_photo(path: Path) -> Path:
    """The 3.02 mm thick hero bracket with a notch at the upper-left *as photographed*, to catch mirrored output."""
    x0, y0, x1, y1 = LAYOUT.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    part = hero_bracket(LAYOUT).difference(box(cx - 41, cy - 15, cx - 32, cy - 8))
    camera = make_camera(LAYOUT, 6, -4, 12)
    cv2.imwrite(str(path), render_view(LAYOUT, camera, parts=(PartShape(part, height_mm=3.02),), blur_sigma=0.8,
                                       noise_sigma=2.0, seed=7))
    return path


def test_photo_to_stl_end_to_end(tmp_path: Path) -> None:
    photo = _asymmetric_photo(tmp_path / "photo.png")
    out = tmp_path / "out"
    report = asyncio.run(photo_to_stl(photo, out, 3.02, ClassicalSegmenter(), job_id="t1"))

    assert report["validation"]["valid"], report["validation"]["errors"]
    assert report["segmentation"] == {**report["segmentation"], "method": "classical-fallback", "is_ai": False}
    length, width, thick = report["part"]["overall_mm"]
    assert length == pytest.approx(80, abs=0.1) and width == pytest.approx(28, abs=0.1)
    assert thick == pytest.approx(3.02, abs=1e-6)
    holes = report["part"]["holes"]
    assert [h["kind"] for h in holes] == ["circle", "circle"]
    assert all(abs(h["diameter_mm"] - 4.2) < 0.05 for h in holes)
    assert sorted(h["center_mm"][0] for h in holes) == pytest.approx([-30, 30], abs=0.1)
    assert set(report["timings_s"]) >= {"calibrate_rectify", "segment", "refine", "spec_build_validate"}
    for name in report["outputs"]:
        assert (out / name).exists()

    assert trimesh.load(out / "model.stl").is_watertight
    outline = Polygon(json.loads((out / "spec.json").read_text())["outline"]["points"])
    assert not outline.contains(Point(-36.5, 11.0)), "notch must be upper-left seen from above (not mirrored)"
    assert outline.contains(Point(-36.5, -11.0))


def test_cli_run_with_classical_backend(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    photo = _asymmetric_photo(tmp_path / "photo.png")
    code = main(["run", "--photo", str(photo), "--thickness", "3.0", "--segmenter", "classical",
                 "-o", str(tmp_path / "cli")])
    assert code == 0
    assert '"valid": true' in capsys.readouterr().out


def test_cli_reports_typed_error_for_a_photo_without_mat(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    blank = tmp_path / "blank.png"
    cv2.imwrite(str(blank), (255 * (0.5 + 0 * cv2.getGaussianKernel(3, 1))).astype("uint8").repeat(400, 0)
                .repeat(400, 1))
    assert main(["run", "--photo", str(blank), "--thickness", "3", "--segmenter", "classical"]) == 1
    assert "CAL_MARKERS_INSUFFICIENT" in capsys.readouterr().err
