"""End to end on SYNTHETIC photos of a 3 mm thick part: parallax is real here, so the height correction must work.

Segmented by the classical fallback (a TEST BACKEND, not SAM 3.1). Camera heights follow from the lens: the mat
fills the frame at about 35 cm with a 1x phone lens, 76 cm at 2x, 1 m at 3x.
"""

import asyncio
from pathlib import Path

import cv2
import numpy as np
import pytest

from reforge.capture.mat import mat_layout
from reforge.capture.pose import FULL_FRAME_DIAGONAL_MM
from reforge.pipeline import photo_to_stl
from reforge.vision.segment import ClassicalSegmenter
from tests.synthetic.scene import PartShape, hero_bracket, make_camera, render_view

LAYOUT = mat_layout("A4")
THICKNESS = 3.0

# (lens focal px for a 2400 x 1800 frame, camera tilt, part offset on the mat, EXIF focal or None, expected source)
CASES = {
    "1x-flat-exif": (1900.0, (0, 0, 0), (0, 0), "exif", "exif"),
    "1x-tilted-no-exif": (1900.0, (12, 0, 0), (25, -15), None, "homography"),
    "2x-tilted-exif": (3800.0, (8, -5, 10), (-20, 10), "exif", "exif+homography"),
    "3x-flat-exif": (5700.0, (0, 0, 0), (10, 5), "exif", "exif"),
}


def _run(tmp_path: Path, focal: float, tilt, offset, exif) -> dict:
    camera = make_camera(LAYOUT, *tilt, focal_px=focal)
    part = PartShape(hero_bracket(LAYOUT, offset_mm=offset), height_mm=THICKNESS)
    photo = tmp_path / "photo.png"
    cv2.imwrite(str(photo), render_view(LAYOUT, camera, parts=(part,), blur_sigma=0.8, noise_sigma=2.0, seed=11))
    # A real EXIF value is a rounded integer in mm (35 mm equivalent).
    f35 = round(focal / np.hypot(*camera.size) * FULL_FRAME_DIAGONAL_MM) if exif else None
    return asyncio.run(photo_to_stl(photo, tmp_path / "out", THICKNESS, ClassicalSegmenter(), job_id="h",
                                    focal_35mm=f35))


@pytest.mark.parametrize("case", list(CASES))
def test_thick_part_is_measured_at_its_true_size(tmp_path: Path, case: str) -> None:
    focal, tilt, offset, exif, source = CASES[case]
    report = _run(tmp_path, focal, tilt, offset, exif)
    assert report["validation"]["valid"], report["validation"]["errors"]
    assert report["pose"]["focal_source"] == source
    assert not report["pose"]["warnings"]

    photographed = report["height_correction"]["photographed_extent_mm"]
    assert photographed[0] - 80.0 > 0.15, "the photo must show the parallax being corrected"

    length, width, _ = report["part"]["overall_mm"]
    assert length == pytest.approx(80.0, abs=0.05)
    assert width == pytest.approx(28.0, abs=0.05)
    holes = report["part"]["holes"]
    assert [h["kind"] for h in holes] == ["circle", "circle"]
    for h in holes:
        assert h["diameter_mm"] == pytest.approx(4.2, abs=0.05)
    xs = sorted(h["center_mm"][0] for h in holes)
    assert xs[1] - xs[0] == pytest.approx(60.0, abs=0.05)


def test_missing_focal_on_a_parallel_view_is_flagged(tmp_path: Path) -> None:
    report = _run(tmp_path, 1900.0, (0, 0, 0), (0, 0), None)
    assert report["pose"]["focal_source"] == "prior"
    assert [w["code"] for w in report["pose"]["warnings"]] == ["POSE_FOCAL_ASSUMED"]
