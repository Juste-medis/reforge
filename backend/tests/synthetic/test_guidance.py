"""Studio guidance: the user steers axis/fracture/family, geometry still judges. SYNTHETIC photos, TEST BACKENDS."""

import asyncio
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from reforge.capture.mat import mat_layout
from reforge.errors import ReforgeError
from reforge.geometry.symmetry import asserted_axis
from reforge.pipeline import photo_to_stl
from reforge.reasoning.analysis import parse_analysis
from reforge.reasoning.interpret import Interpretation
from reforge.reasoning.reconstruct import Guidance
from reforge.vision.segment import ClassicalSegmenter, Segmentation
from tests.synthetic.scene import PartShape, broken_bracket, hero_bracket, make_camera, render_view
from tests.synthetic.test_pipeline import _asymmetric_photo

LAYOUT = mat_layout("A4")


def _photo(path: Path, part, seed: int = 3) -> Path:
    camera = make_camera(LAYOUT, 4, -3, 8)
    cv2.imwrite(str(path), render_view(LAYOUT, camera, parts=(PartShape(part, height_mm=3.0),), blur_sigma=0.8,
                                       noise_sigma=2.0, seed=seed))
    return path


def _codes(report) -> list[str]:
    return [n["code"] for n in report["reconstruction"]["verification"]]


def test_guided_rebuild_uses_user_axis_and_fracture(tmp_path: Path) -> None:
    photo = _photo(tmp_path / "photo.png", broken_bracket(LAYOUT, seed=0))
    plain = asyncio.run(photo_to_stl(photo, tmp_path / "plain", 3.0, ClassicalSegmenter(), job_id="g0"))
    assert plain["reconstruction"]["completion"] is not None
    segs = [s["id"] for s in plain["reconstruction"]["segments"] if s["kind"] in ("irregular", "broken")]
    assert segs, "the break must show as irregular segments"

    guided = asyncio.run(photo_to_stl(
        photo, tmp_path / "guided", 3.0, ClassicalSegmenter(), job_id="g1",
        guidance=Guidance(axis_id=plain["reconstruction"]["completion"]["axis"], fracture_ids=tuple(segs),
                          note="studio test")))
    assert guided["reconstruction"]["completion"] is not None
    assert "USER_GUIDED" in _codes(guided)
    assert guided["reconstruction"]["guided"]["axis_id"] == plain["reconstruction"]["completion"]["axis"]
    assert guided["reconstruction"]["guided"]["note"] == "studio test"


def test_unknown_guided_ids_fail_fast(tmp_path: Path) -> None:
    photo = _asymmetric_photo(tmp_path / "photo.png")
    with pytest.raises(ReforgeError) as exc:
        asyncio.run(photo_to_stl(photo, tmp_path / "o1", 3.02, ClassicalSegmenter(), job_id="g2",
                                 guidance=Guidance(axis_id="A99")))
    assert exc.value.code == "GUIDE_UNKNOWN_AXIS"
    with pytest.raises(ReforgeError) as exc:
        asyncio.run(photo_to_stl(photo, tmp_path / "o2", 3.02, ClassicalSegmenter(), job_id="g3",
                                 guidance=Guidance(axis_id="none", fracture_ids=("S99",))))
    assert exc.value.code == "GUIDE_UNKNOWN_SEGMENT"
    with pytest.raises(ReforgeError) as exc:
        asyncio.run(photo_to_stl(photo, tmp_path / "o3", 3.02, ClassicalSegmenter(), job_id="g4",
                                 guidance=Guidance(axis_id="none", fracture_ids=("S0",), exclude_ids=("S0",))))
    assert exc.value.code == "GUIDE_CONFLICT"


class _PipeReader:
    """A stub interpreter that reads everything as a 3D pipe: the family gate must refuse it."""

    async def interpret(self, req) -> Interpretation:
        analysis = parse_analysis(
            {"object_name": "pipe", "family": "revolved", "family_reason": "round, stubbed",
             "is_broken": False, "fracture_segment_ids": [], "fracture_reason": "stubbed",
             "symmetry": "none", "mirror_axis_id": "none", "symmetry_reason": "stubbed", "holes": [],
             "missing_features": [], "required_measurements": []},
            req.seg_ids, req.axis_ids, req.hole_ids)
        return Interpretation(analysis=analysis, method="stub-pipe", is_ai=False, latency_s=0.0, cost_usd=0.0,
                              detail={})


def test_family_override_asserts_flat_and_labels_it(tmp_path: Path) -> None:
    photo = _asymmetric_photo(tmp_path / "photo.png")
    with pytest.raises(ReforgeError) as exc:
        asyncio.run(photo_to_stl(photo, tmp_path / "o1", 3.02, ClassicalSegmenter(), job_id="g4",
                                 interpreter=_PipeReader()))
    assert exc.value.code == "FAMILY_UNSUPPORTED"
    assert (tmp_path / "o1" / "reconstruction.json").is_file()  # the Studio's candidates survive the refusal
    assert (tmp_path / "o1" / "mask.png").is_file()

    forced = asyncio.run(photo_to_stl(
        photo, tmp_path / "o2", 3.02, ClassicalSegmenter(), job_id="g5", interpreter=_PipeReader(),
        guidance=Guidance(family_override=True, note="I know this is flat")))
    assert forced["validation"]["valid"]
    assert forced["family_overridden"] is True
    assert "USER_GUIDED" in _codes(forced)
    assert "flat model of a part" in json.dumps(forced["reconstruction"]["verification"])


def test_asserted_pivot_steers_the_axis_line() -> None:
    square = np.array([[-5.0, -5.0], [5.0, -5.0], [5.0, 5.0], [-5.0, 5.0]])
    axis = asserted_axis(0.0, square, point=np.array([0.0, 2.0]))
    assert axis.axis_id == "U0" and axis.angle_deg == pytest.approx(0.0)
    assert axis.reflect(np.array([[5.0, 0.0]]))[0] == pytest.approx([5.0, 4.0])  # the line y = 2
    default = asserted_axis(90.0, square)
    assert default.reflect(np.array([[3.0, 1.0]]))[0] == pytest.approx([-3.0, 1.0])  # x = 0, the centroid


def test_guided_sources_build_exactly_those(tmp_path: Path) -> None:
    photo = _photo(tmp_path / "photo.png", broken_bracket(LAYOUT, seed=0))
    plain = asyncio.run(photo_to_stl(photo, tmp_path / "plain", 3.0, ClassicalSegmenter(), job_id="gs0"))
    assert plain["reconstruction"]["completion"] is not None
    ids = [h["id"] for h in plain["reconstruction"]["all_holes"]]
    assert len(ids) == 2
    segs = [s["id"] for s in plain["reconstruction"]["segments"] if s["kind"] in ("irregular", "broken")]

    guided = asyncio.run(photo_to_stl(
        photo, tmp_path / "guided", 3.0, ClassicalSegmenter(), job_id="gs1",
        guidance=Guidance(axis_id=plain["reconstruction"]["completion"]["axis"], fracture_ids=tuple(segs),
                          source_hole_ids=(ids[0],))))
    assert guided["reconstruction"]["completion"] is not None
    assert "USER_GUIDED" in _codes(guided)
    assert [h["id"] for h in guided["part"]["holes"]] == ["H0"]  # renumbered: exactly one built
    assert all(h["status"] == "OBSERVED" for h in guided["part"]["holes"])  # no duplicate inferred
    note = next(n["message"] for n in guided["reconstruction"]["verification"] if n["code"] == "USER_GUIDED")
    assert "Exact build list" in note and "Left out" in note and ids[0] in note and ids[1] in note


def _streak_photo(path: Path) -> Path:
    """The hero bracket with a light streak the pipeline doubts (a reflection, not a hole)."""
    x0, y0, x1, y1 = LAYOUT.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    streak = tuple((cx - 14 + 0.5 * k, cy + 4, 1.0, 180) for k in range(13))
    camera = make_camera(LAYOUT, 4, -3, 8)
    cv2.imwrite(str(path), render_view(LAYOUT, camera, parts=(PartShape(hero_bracket(LAYOUT), height_mm=3.0),),
                                       spots=streak, blur_sigma=0.8, noise_sigma=2.0, seed=3))
    return path


def test_trusted_doubted_source_is_built_and_labelled(tmp_path: Path) -> None:
    photo = _streak_photo(tmp_path / "photo.png")
    plain = asyncio.run(photo_to_stl(photo, tmp_path / "plain", 3.0, ClassicalSegmenter(), job_id="gt0"))
    holes = [(h["id"], h["doubted"]) for h in plain["reconstruction"]["all_holes"]]
    assert len(holes) == 3 and sum(d for _, d in holes) == 1
    doubted = next(hid for hid, d in holes if d)
    assert len(plain["part"]["holes"]) == 2  # auto: the doubted streak stays out

    guided = asyncio.run(photo_to_stl(
        photo, tmp_path / "guided", 3.0, ClassicalSegmenter(), job_id="gt1",
        guidance=Guidance(source_hole_ids=tuple(hid for hid, _ in holes), note="that streak is a real slot")))
    assert "USER_GUIDED" in _codes(guided)
    assert len(guided["part"]["holes"]) == 3
    assert all(h["status"] == "OBSERVED" for h in guided["part"]["holes"])
    trusted = [n for n in guided["part"]["excluded_candidates"] if n.get("trusted")]
    assert len(trusted) == 1 and trusted[0]["hole"] == doubted and "overruled by you" in trusted[0]["reason"]
    note = next(n["message"] for n in guided["reconstruction"]["verification"] if n["code"] == "USER_GUIDED")
    assert "Every observed hole is in the build list" in note


def test_mask_reuse_keeps_segmentation(tmp_path: Path) -> None:
    photo = _photo(tmp_path / "photo.png", hero_bracket(LAYOUT))
    first = asyncio.run(photo_to_stl(photo, tmp_path / "o1", 3.0, ClassicalSegmenter(), job_id="g6"))
    reuse = Segmentation(mask=cv2.imread(str(tmp_path / "o1" / "mask.png"), cv2.IMREAD_GRAYSCALE) > 127,
                         method="reused-classical-fallback", is_ai=False)
    second = asyncio.run(photo_to_stl(photo, tmp_path / "o2", 3.0, ClassicalSegmenter(), job_id="g7",
                                      guidance=Guidance(note="replay"), reuse_segmentation=reuse))
    assert second["segmentation"]["method"] == "reused-classical-fallback"
    assert second["part"]["overall_mm"] == pytest.approx(first["part"]["overall_mm"], abs=1e-6)
