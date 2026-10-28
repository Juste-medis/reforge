"""D4 end to end on SYNTHETIC photos: a broken 3 mm bracket is photographed, measured and rebuilt by mirror symmetry.

Segmentation is the classical fallback and interpretation the geometric rule: both are TEST BACKENDS, not AI. The
Muse Spark path is tested live in tests/live/test_spark_live.py.
"""

import asyncio
import json
from pathlib import Path

import cv2
import pytest
import trimesh

from reforge.capture.mat import mat_layout
from reforge.errors import ReforgeError
from reforge.pipeline import photo_to_stl
from reforge.vision.segment import ClassicalSegmenter
from tests.synthetic.scene import PartShape, broken_bracket, hero_bracket, make_camera, render_view

LAYOUT = mat_layout("A4")


def _photo(tmp_path: Path, polygon, seed: int = 4) -> Path:
    camera = make_camera(LAYOUT, 6, -4, 12)
    path = tmp_path / "photo.png"
    cv2.imwrite(str(path), render_view(LAYOUT, camera, parts=(PartShape(polygon, height_mm=3.0),), blur_sigma=0.8,
                                       noise_sigma=2.0, seed=seed))
    return path


@pytest.mark.parametrize("seed", [0, 3])
def test_broken_part_is_rebuilt_from_a_photo(tmp_path: Path, seed: int) -> None:
    out = tmp_path / "out"
    report = asyncio.run(photo_to_stl(_photo(tmp_path, broken_bracket(LAYOUT, seed=seed)), out, 3.0,
                                      ClassicalSegmenter(), job_id="d4"))
    recon = report["reconstruction"]
    assert recon["interpretation"]["method"] == "geometric-rule" and recon["interpretation"]["is_ai"] is False
    completion = recon["completion"]
    assert completion is not None
    assert completion["added_area_mm2"] > 80  # the missing end, about 4 mm x 28 mm
    length, width, _ = report["part"]["overall_mm"]
    assert length == pytest.approx(80.0, abs=0.1) and width == pytest.approx(28.0, abs=0.1)
    holes = report["part"]["holes"]
    assert [h["kind"] for h in holes] == ["circle", "circle"]
    assert all(abs(h["diameter_mm"] - 4.2) < 0.05 for h in holes)
    assert {r["status"] for r in completion["runs"]} >= {"OBSERVED", "INFERRED"}
    assert all(c["center_distance_mm"] < 0.1 for c in completion["hole_checks"])

    spec = json.loads((out / "spec.json").read_text())
    statuses = {run["status"] for run in spec["outline"]["runs"]}
    assert "INFERRED" in statuses
    assert report["validation"]["valid"], report["validation"]["errors"]
    assert trimesh.load(out / "model.stl").is_watertight
    assert (out / "setofmark.png").exists()


def test_intact_part_gets_no_reconstruction(tmp_path: Path) -> None:
    report = asyncio.run(photo_to_stl(_photo(tmp_path, hero_bracket(LAYOUT)), tmp_path / "out", 3.0,
                                      ClassicalSegmenter(), job_id="intact"))
    assert report["reconstruction"]["completion"] is None
    spec = json.loads((tmp_path / "out" / "spec.json").read_text())
    assert {run["status"] for run in spec["outline"]["runs"]} == {"OBSERVED"}


class _FailingInterpreter:
    """Stands in for a model call that times out (TEST BACKEND)."""

    is_ai = True
    method = "failing-test-backend"

    async def interpret(self, request):
        raise ReforgeError("META_TIMEOUT", "simulated timeout")


def test_model_failure_falls_back_to_the_geometric_rule_and_says_so(tmp_path: Path) -> None:
    report = asyncio.run(photo_to_stl(_photo(tmp_path, broken_bracket(LAYOUT, seed=0)), tmp_path / "out", 3.0,
                                      ClassicalSegmenter(), job_id="fb", interpreter=_FailingInterpreter()))
    interp = report["reconstruction"]["interpretation"]
    assert interp["method"] == "geometric-rule" and interp["is_ai"] is False
    assert interp["fallback_reason"]["code"] == "META_TIMEOUT"
    assert report["reconstruction"]["completion"] is not None


class _StripSegmenter:
    """Returns only a 5 mm strip of the part (TEST BACKEND), like a segmenter that latched onto one colour of a
    multi-coloured object: the 2026-10-28 collage of a rusty pipe on the mat was traced this way."""

    method = "strip-test-backend"

    async def segment(self, view):
        from reforge.vision.segment import Segmentation, colour_candidate

        mask = colour_candidate(view)
        x0 = int(mask.any(axis=0).argmax())
        strip = mask.copy()
        strip[:, : x0 + int(10 * view.px_per_mm)] = False
        strip[:, x0 + int(15 * view.px_per_mm):] = False
        return Segmentation(strip, self.method, False, None, 0.0, 0.0, {})


def test_a_partial_trace_is_refused_before_any_model_call(tmp_path: Path) -> None:
    with pytest.raises(ReforgeError) as info:
        asyncio.run(photo_to_stl(_photo(tmp_path, hero_bracket(LAYOUT)), tmp_path / "out", 3.0, _StripSegmenter(),
                                 interpreter=_FailingInterpreter()))
    assert info.value.code == "TRACE_PARTIAL"
    assert not (tmp_path / "out" / "model.stl").exists()


class _PipeInterpreter:
    """Answers like Muse Spark did on that collage once it saw the whole mat (TEST BACKEND, hand-written)."""

    is_ai = True
    method = "pipe-test-backend"

    async def interpret(self, request):
        from reforge.reasoning.analysis import PartAnalysis
        from reforge.reasoning.interpret import Interpretation

        data = {"object_name": "corroded steel pipe section", "family": "unsupported",
                "family_reason": "a 3D pipe, not a flat plate", "is_broken": True, "fracture_segment_ids": [],
                "fracture_reason": "", "symmetry": "unsure", "mirror_axis_id": "none", "symmetry_reason": "",
                "holes": [], "missing_features": [], "required_measurements": []}
        analysis = PartAnalysis.model_validate(data, context={"seg_ids": request.seg_ids, "axis_ids": request.axis_ids,
                                                              "hole_ids": request.hole_ids})
        return Interpretation(analysis, self.method, True, 0.0, 0.0, {})


def test_an_unsupported_object_is_refused_with_the_reason(tmp_path: Path) -> None:
    with pytest.raises(ReforgeError) as info:
        asyncio.run(photo_to_stl(_photo(tmp_path, hero_bracket(LAYOUT)), tmp_path / "out", 3.0, ClassicalSegmenter(),
                                 interpreter=_PipeInterpreter()))
    assert info.value.code == "FAMILY_UNSUPPORTED" and "corroded steel pipe" in info.value.message
    assert not (tmp_path / "out" / "model.stl").exists()
