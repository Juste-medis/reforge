"""Deskew: a perspective quad back to a top-down rectangle at exact scale. No AI, deterministic."""

import cv2
import numpy as np
import pytest

from reforge.errors import ReforgeError
from reforge.studio.deskew import deskew_quad, order_corners

CORNERS = np.array([[120.0, 80.0], [520.0, 140.0], [470.0, 380.0], [90.0, 320.0]])  # a tilted quad


def _photo() -> np.ndarray:
    img = np.full((480, 640, 3), 255, np.uint8)
    cv2.fillConvexPoly(img, CORNERS.astype(np.int32), (30, 30, 30))
    return img


def test_deskew_returns_the_rectangle_at_exact_scale() -> None:
    result = deskew_quad(_photo(), CORNERS, 300.0, 200.0, margin=0.0)
    h, w = result.image_bgr.shape[:2]
    assert (w - 1) / 300.0 == pytest.approx(result.px_per_mm)
    # Square pixels up to fencepost rounding (<1 px over the frame; ruler uncertainty is orders above).
    assert (h - 1) / 200.0 == pytest.approx(result.px_per_mm, rel=0.005)
    assert result.image_bgr.mean() < 35.0  # the quad fills the frame: no background leaks in


def test_deskew_margin_keeps_background_and_scale() -> None:
    plain = deskew_quad(_photo(), CORNERS, 300.0, 200.0, margin=0.0)
    padded = deskew_quad(_photo(), CORNERS, 300.0, 200.0, margin=0.25)
    assert padded.px_per_mm == plain.px_per_mm  # the margin only grows the canvas
    mx, my = padded.margin_px
    assert (mx, my) == ((padded.image_bgr.shape[1] - plain.image_bgr.shape[1]) // 2,
                        (padded.image_bgr.shape[0] - plain.image_bgr.shape[0]) // 2)
    inner = padded.image_bgr[my:my + plain.image_bgr.shape[0], mx:mx + plain.image_bgr.shape[1]]
    assert np.abs(inner.astype(float) - plain.image_bgr.astype(float)).mean() < 1.0
    assert padded.image_bgr[:my // 2, :].mean() > 200.0  # flat sampled background on top


def test_deskew_ignores_corner_order() -> None:
    first = deskew_quad(_photo(), CORNERS, 300.0, 200.0)
    shuffled = deskew_quad(_photo(), CORNERS[[2, 0, 3, 1]], 300.0, 200.0)
    assert np.array_equal(first.image_bgr, shuffled.image_bgr)
    assert first.corners_px == shuffled.corners_px


def test_torn_corner_estimate_stays_close() -> None:
    """One corner off by 5 px (the user's estimate of a torn corner): the other three still land within 3 px
    of the frame corners, and the scale stays within 1 %."""
    exact = deskew_quad(_photo(), CORNERS, 300.0, 200.0, margin=0.0)
    off = CORNERS.copy()
    off[2] += (5.0, -5.0)
    approx = deskew_quad(_photo(), off, 300.0, 200.0, margin=0.0)
    assert approx.px_per_mm == pytest.approx(exact.px_per_mm, rel=0.01)
    h, w = approx.image_bgr.shape[:2]
    gray = cv2.cvtColor(approx.image_bgr, cv2.COLOR_BGR2GRAY)
    contour = max(cv2.findContours((gray < 128).astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
    got = cv2.boxPoints(cv2.minAreaRect(contour))
    want = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=float)
    dist = np.linalg.norm(got[:, None, :] - want[None, :, :], axis=2).min(axis=1)
    assert dist.max() < 3.0


def test_bad_corners_and_sizes_are_typed_errors() -> None:
    with pytest.raises(ReforgeError) as exc:
        order_corners(CORNERS[:3])
    assert exc.value.code == "DESKEW_BAD_CORNERS"
    with pytest.raises(ReforgeError) as exc:
        deskew_quad(_photo(), CORNERS, 0.0, 200.0)
    assert exc.value.code == "DESKEW_BAD_SIZE"
    with pytest.raises(ReforgeError) as exc:
        deskew_quad(_photo(), CORNERS, 300.0, 99999.0)
    assert exc.value.code == "DESKEW_BAD_SIZE"
