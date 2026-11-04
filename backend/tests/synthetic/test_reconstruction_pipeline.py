"""D4 end to end on SYNTHETIC photos: a broken 3 mm bracket is photographed, measured and rebuilt by mirror symmetry.

Segmentation is the classical fallback and interpretation the geometric rule: both are TEST BACKENDS, not AI. The
Muse Spark path is tested live in tests/live/test_spark_live.py.
"""

import asyncio
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import trimesh

from reforge.capture.mat import mat_layout
from reforge.errors import ReforgeError
from reforge.pipeline import photo_to_stl
from reforge.vision.segment import ClassicalSegmenter
from tests.synthetic.scene import (
    PartShape,
    broken_bracket,
    broken_flange,
    broken_pick,
    hero_bracket,
    make_camera,
    render_view,
)

LAYOUT = mat_layout("A4")


def _photo(tmp_path: Path, polygon, seed: int = 4, height_mm: float = 3.0) -> Path:
    camera = make_camera(LAYOUT, 6, -4, 12)
    path = tmp_path / "photo.png"
    cv2.imwrite(str(path), render_view(LAYOUT, camera, parts=(PartShape(polygon, height_mm=height_mm),),
                                       blur_sigma=0.8, noise_sigma=2.0, seed=seed))
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


@pytest.mark.parametrize("seed", [0, 1, 3])
def test_a_side_broken_pick_is_not_rebuilt_from_too_little_evidence(tmp_path: Path, seed: int) -> None:
    """A teardrop snapped along its length keeps little of its symmetry: several axes then reach 100 % support on
    what is left. Before the evidence rule, the geometric rule rebuilt these 28–31 mm wide instead of 26 mm
    (measured 2026-11-02). Now no material is invented, and the report says why. The same check applied to a model's
    choice is tested in tests/unit/test_reasoning_contract.py."""
    report = asyncio.run(photo_to_stl(_photo(tmp_path, broken_pick(LAYOUT, seed=seed), height_mm=0.8),
                                      tmp_path / "out", 0.8, ClassicalSegmenter(), job_id="pick"))
    recon = report["reconstruction"]
    assert recon["completion"] is None
    # The geometric rule now declines up front (its trial rebuilds fail the same checks a model's choice must pass).
    assert "trial rebuild" in recon["interpretation"]["analysis"]["symmetry_reason"]
    width, length, _ = report["part"]["overall_mm"]
    assert width < 21.0 and length == pytest.approx(31.5, abs=0.1)  # the broken pick as photographed


def test_rebuilt_bracket_is_confirmed_by_more_outline_than_it_invents(tmp_path: Path) -> None:
    report = asyncio.run(photo_to_stl(_photo(tmp_path, broken_bracket(LAYOUT, seed=0)), tmp_path / "out", 3.0,
                                      ClassicalSegmenter(), job_id="evidence"))
    completion = report["reconstruction"]["completion"]
    assert completion["confirmed_mm"] > 3 * completion["inferred_outline_mm"] > 0


def test_broken_flange_is_rebuilt_with_the_holes_the_break_took(tmp_path: Path) -> None:
    """Only the bore pins the vertical axis (its partners were lost), and the square's diagonals are real symmetries
    too. Before 2026-11-02 the vertical axis wasn't even a candidate; then a diagonal was chosen, leaving a corner
    missing; then the axis came out 0.37° off (rebuilt 0.25 mm too large)."""
    report = asyncio.run(photo_to_stl(_photo(tmp_path, broken_flange(LAYOUT)), tmp_path / "out", 3.0,
                                      ClassicalSegmenter(), job_id="flange"))
    completion = report["reconstruction"]["completion"]
    assert completion is not None
    length, width, _ = report["part"]["overall_mm"]
    assert length == pytest.approx(50.0, abs=0.06) and width == pytest.approx(50.0, abs=0.06)
    x0, y0, x1, y1 = LAYOUT.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    inferred = sorted(tuple(h["center_mm"]) for h in completion["inferred_holes"])
    assert len(inferred) == 2
    # Measured 2026-11-02: 0.058 mm, against a mirror-only 2σ of 0.031 mm. That U leaves out the source hole's own
    # error, which the Confidence Engine (D5) adds; until then the bound here is absolute.
    for (x, y), (tx, ty) in zip(inferred, [(cx + 19, cy - 19), (cx + 19, cy + 19)], strict=True):
        assert np.hypot(x - tx, y - ty) <= 0.1
    assert all(h["diameter_mm"] == pytest.approx(5.5, abs=0.05) for h in completion["inferred_holes"])
    assert report["validation"]["valid"]


class _DiagonalInterpreter:
    """Chooses a diagonal axis of the broken flange and the break segments as the fracture (TEST BACKEND)."""

    is_ai = True
    method = "diagonal-test-backend"
    direction_deg = 45.0  # modulo 90°: either diagonal

    def pick(self, axes: list[dict]) -> str:
        return next(a["id"] for a in axes if abs((a["direction_deg"] - self.direction_deg + 45) % 90 - 45) < 1.0)

    async def interpret(self, request):
        from reforge.reasoning.analysis import PartAnalysis
        from reforge.reasoning.interpret import Interpretation

        diagonal = self.pick(request.facts["mirror_axes"])
        data = {"object_name": "flange", "family": "extruded_profile", "family_reason": "flat plate",
                "is_broken": True, "fracture_segment_ids": [k for k, v in request.segment_kinds.items()
                                                            if v in ("irregular", "broken")],
                "fracture_reason": "", "symmetry": "mirror", "mirror_axis_id": diagonal, "symmetry_reason": "",
                "holes": [], "missing_features": [], "required_measurements": []}
        analysis = PartAnalysis.model_validate(data, context={"seg_ids": request.seg_ids, "axis_ids": request.axis_ids,
                                                              "hole_ids": request.hole_ids})
        return Interpretation(analysis, self.method, True, 0.0, 0.0, {})


class _CrosswiseInterpreter(_DiagonalInterpreter):
    """Chooses the flange's top-bottom axis: a real symmetry, but it maps the right-hand break onto itself, as Muse
    Spark did live on 2026-11-03 (TEST BACKEND)."""

    method = "crosswise-test-backend"

    def pick(self, axes: list[dict]) -> str:
        return next(a["id"] for a in axes if min(a["direction_deg"] % 180, 180 - a["direction_deg"] % 180) < 1.0)


@pytest.mark.parametrize("interpreter", [_DiagonalInterpreter(), _CrosswiseInterpreter()],
                         ids=["diagonal", "crosswise"])
def test_an_axis_that_cant_rebuild_the_break_is_rejected_then_corrected_by_geometry(tmp_path: Path,
                                                                                   interpreter) -> None:
    report = asyncio.run(photo_to_stl(_photo(tmp_path, broken_flange(LAYOUT)), tmp_path / "out", 3.0,
                                      ClassicalSegmenter(), job_id="axis", interpreter=interpreter))
    recon = report["reconstruction"]
    notes = {n["code"]: n for n in recon["verification"]}
    rejected = {n["code"] for n in recon["verification"] if n["level"] == "rejected"}
    assert rejected & {"AXIS_PARTIAL", "FRACTURE_MATCHES_MIRROR"}  # the reading's own axis still fails, and says why
    assert "AXIS_CORRECTED" in notes and notes["AXIS_CORRECTED"]["level"] == "warning"
    assert "NO_FRACTURE" not in notes  # superseded: something is reconstructed
    completion = recon["completion"]
    assert completion is not None and completion["axis"] != recon["interpretation"]["analysis"]["mirror_axis_id"]
    assert completion["added_area_mm2"] > 400
    assert len(completion["inferred_holes"]) == 2  # the two bolt holes the break took
    assert all(h["diameter_mm"] == pytest.approx(5.5, abs=0.05) for h in completion["inferred_holes"])
    assert report["validation"]["valid"]


class _NotBrokenInterpreter(_DiagonalInterpreter):
    """Says the flange is intact (TEST BACKEND): geometry must not override that and rebuild anything."""

    async def interpret(self, request):
        result = await super().interpret(request)
        analysis = result.analysis.model_copy(update={"is_broken": False, "fracture_segment_ids": (),
                                                      "mirror_axis_id": "none"})
        return type(result)(analysis, result.method, True, 0.0, 0.0, {})


def test_geometry_doesnt_rebuild_what_the_reading_calls_intact(tmp_path: Path) -> None:
    report = asyncio.run(photo_to_stl(_photo(tmp_path, broken_flange(LAYOUT)), tmp_path / "out", 3.0,
                                      ClassicalSegmenter(), job_id="intact", interpreter=_NotBrokenInterpreter()))
    assert report["reconstruction"]["completion"] is None
    assert "AXIS_CORRECTED" not in {n["code"] for n in report["reconstruction"]["verification"]}
