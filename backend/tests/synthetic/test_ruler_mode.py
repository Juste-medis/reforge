"""Ruler mode: no mat, scale from one user-measured length. SYNTHETIC photo, classical fallback (a TEST BACKEND)."""

import asyncio
from pathlib import Path

import cv2
import numpy as np
import pytest

from reforge.capture.mat import mat_layout
from reforge.errors import ReforgeError
from reforge.pipeline import photo_to_stl
from reforge.vision.segment import ClassicalSegmenter
from tests.synthetic.scene import hero_bracket

LAYOUT = mat_layout("A4")
PX_PER_MM = 10.0


def _matless_photo(path: Path) -> Path:
    """The 80 x 28 mm hero bracket drawn top-down on a blank background at exactly 10 px/mm: no mat, no markers,
    no perspective — the ruler contract (top-down + one measured length) and nothing else."""
    poly = hero_bracket(LAYOUT)
    x0, y0, x1, y1 = poly.bounds
    margin = 20.0
    w, h = int((x1 - x0 + 2 * margin) * PX_PER_MM), int((y1 - y0 + 2 * margin) * PX_PER_MM)

    def _px(pts: np.ndarray) -> np.ndarray:
        return np.round((pts - np.array([x0 - margin, y0 - margin])) * PX_PER_MM).astype(np.int32)

    canvas = np.full((h, w, 3), 235, np.uint8)
    cv2.fillPoly(canvas, [_px(np.asarray(poly.exterior.coords))], (70, 70, 70))
    for ring in poly.interiors:
        cv2.fillPoly(canvas, [_px(np.asarray(ring.coords))], (235, 235, 235))
    canvas = cv2.GaussianBlur(canvas, (0, 0), 0.8)
    rng = np.random.default_rng(11)
    canvas = np.clip(canvas.astype(np.float32) + rng.normal(0.0, 2.0, canvas.shape), 0, 255).astype(np.uint8)
    cv2.imwrite(str(path), canvas)
    return path


def test_no_mat_without_length_still_declines(tmp_path: Path) -> None:
    photo = _matless_photo(tmp_path / "photo.png")
    with pytest.raises(ReforgeError) as exc:
        asyncio.run(photo_to_stl(photo, tmp_path / "out", 3.0, ClassicalSegmenter(), job_id="ruler-decline"))
    assert exc.value.code == "CAL_MARKERS_INSUFFICIENT"


def test_ruler_mode_recovers_scale_without_mat(tmp_path: Path) -> None:
    photo = _matless_photo(tmp_path / "photo.png")
    report = asyncio.run(photo_to_stl(photo, tmp_path / "out", 3.0, ClassicalSegmenter(), known_length_mm=80.0,
                                      job_id="ruler"))

    assert report["validation"]["valid"], report["validation"]["errors"]
    assert report["calibration"]["mode"] == "ruler"
    assert report["calibration"]["markers"] == 0
    length, width, _ = report["part"]["overall_mm"]
    assert length == pytest.approx(80, abs=1.2) and width == pytest.approx(28, abs=1.2)
    codes = [w["code"] for w in report["calibration"]["warnings"]]
    assert any(c.startswith("RULER_") for c in codes), codes
    assert (tmp_path / "out" / "model.stl").is_file()
