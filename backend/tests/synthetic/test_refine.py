"""D2: boundary refinement and hole detection on SYNTHETIC scenes with exact ground truth.

The coarse masks here are degraded ground truth standing in for a segmenter. They're a labelled
TEST BACKEND, not SAM 3.1 output; real SAM masks are evaluated separately with live calls.
"""

import cv2
import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon

from reforge.capture.calibration import RectifiedView, calibrate, rectify
from reforge.capture.mat import mat_layout
from reforge.errors import ReforgeError
from reforge.geometry.circle import fit_circle
from reforge.vision.refine import refine_profile
from tests.synthetic.scene import PartShape, hero_bracket, make_camera, render_view

LAYOUT = mat_layout("A4")


def _view(polygon: Polygon, *, value: int = 55, spots=(), tilt=(8, -5, 10), seed: int = 1) -> RectifiedView:
    camera = make_camera(LAYOUT, *tilt)
    image = render_view(LAYOUT, camera, parts=(PartShape(polygon, value),), spots=spots,
                        blur_sigma=0.8, noise_sigma=2.0, seed=seed)
    return rectify(image, calibrate(image))


def _rasterize(view: RectifiedView, polygon: Polygon, holes: bool = True) -> np.ndarray:
    mask = np.zeros(view.image.shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.round(view.mm_to_px(np.asarray(polygon.exterior.coords))).astype(np.int32)], 1)
    if holes:
        for ring in polygon.interiors:
            cv2.fillPoly(mask, [np.round(view.mm_to_px(np.asarray(ring.coords))).astype(np.int32)], 0)
    return mask


def _degrade(mask: np.ndarray, mode: str) -> np.ndarray:
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    if mode == "exact":
        return mask
    if mode == "dilated_1px":
        return cv2.dilate(mask, disk)
    if mode == "eroded_1px":
        return cv2.erode(mask, disk)
    if mode == "blocky_x2":
        small = cv2.resize(mask * 255, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        return (cv2.resize(small, mask.shape[::-1], interpolation=cv2.INTER_NEAREST) > 127).astype(np.uint8)
    raise ValueError(mode)


def _outer_errors_mm(profile, polygon: Polygon) -> np.ndarray:
    return shapely.distance(polygon.exterior, shapely.points(profile.outer.points_mm))


@pytest.mark.parametrize("mode", ["exact", "dilated_1px", "eroded_1px", "blocky_x2"])
def test_outer_boundary_is_sub_pixel_accurate(mode: str) -> None:
    truth = hero_bracket(LAYOUT)
    view = _view(truth)
    profile = refine_profile(view, _degrade(_rasterize(view, truth), mode))
    assert profile.refined
    errors = _outer_errors_mm(profile, truth)
    pixel = 1 / view.px_per_mm
    assert errors.mean() < 0.05, f"mean boundary error {errors.mean():.4f} mm (pixel {pixel:.3f} mm)"
    assert errors.max() < 0.15, f"max boundary error {errors.max():.4f} mm"
    assert profile.outer.area_mm2 == pytest.approx(truth.buffer(0).exterior.convex_hull.area, rel=0.05)


@pytest.mark.parametrize("filled", [False, True])
def test_holes_are_found_and_measured(filled: bool) -> None:
    """Holes come from colour, so they're found even when the coarse mask filled them in."""
    truth = hero_bracket(LAYOUT)
    view = _view(truth)
    profile = refine_profile(view, _rasterize(view, truth, holes=not filled))
    assert len(profile.holes) == 2
    fits = sorted((fit_circle(h.contour.points_mm) for h in profile.holes), key=lambda f: f.center[0])
    true_centres = sorted((ring.centroid.x, ring.centroid.y) for ring in (Polygon(r) for r in truth.interiors))
    for fit, centre in zip(fits, true_centres, strict=True):
        assert fit.diameter == pytest.approx(4.2, abs=0.05)
        assert np.hypot(fit.center[0] - centre[0], fit.center[1] - centre[1]) < 0.05
    assert all(h.mask_agrees is (not filled) for h in profile.holes)
    assert not any(h.glare_suspect for h in profile.holes)


@pytest.mark.parametrize("grow_px", [-2, 2, 3])
def test_holes_are_measured_by_colour_even_when_mask_holes_are_off(grow_px: int) -> None:
    """Live finding (2026-10-27): a SAM box-prompt mask kept the holes open, but its hole edges didn't line up with
    the true edges, and the narrow band clipped the edge. Hole geometry must come from colour, whatever the mask
    says."""
    truth = hero_bracket(LAYOUT)
    view = _view(truth)
    outer = _rasterize(view, truth, holes=False)
    holes = np.zeros_like(outer)
    for ring in truth.interiors:
        cv2.fillPoly(holes, [np.round(view.mm_to_px(np.asarray(ring.coords))).astype(np.int32)], 1)
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * abs(grow_px) + 1,) * 2)
    holes = cv2.dilate(holes, disk) if grow_px > 0 else cv2.erode(holes, disk)
    profile = refine_profile(view, (outer & ~holes.astype(bool)).astype(np.uint8))
    assert len(profile.holes) == 2
    for hole in profile.holes:
        fit = fit_circle(hole.contour.points_mm)
        assert fit.max_deviation < 0.08, f"hole edge distorted: max deviation {fit.max_deviation:.3f} mm"
        assert fit.diameter == pytest.approx(4.2, abs=0.05)
        assert hole.mask_agrees


def test_broken_outline_is_followed() -> None:
    truth = hero_bracket(LAYOUT, broken=True)
    view = _view(truth, seed=4)
    profile = refine_profile(view, _degrade(_rasterize(view, truth), "blocky_x2"))
    errors = _outer_errors_mm(profile, truth)
    assert errors.mean() < 0.05 and errors.max() < 0.2


def test_glare_highlight_is_flagged_not_trusted() -> None:
    truth = hero_bracket(LAYOUT)
    x0, y0, x1, y1 = LAYOUT.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    view = _view(truth, spots=((cx - 10, cy, 1.5, 255),))
    profile = refine_profile(view, _rasterize(view, truth))
    glare = [h for h in profile.holes if h.glare_suspect]
    assert len(glare) == 1
    assert not glare[0].mask_agrees  # the segmenter saw plastic there


def test_low_contrast_keeps_coarse_boundary_and_warns() -> None:
    truth = hero_bracket(LAYOUT)
    view = _view(truth, value=226)
    profile = refine_profile(view, _rasterize(view, truth))
    assert not profile.refined
    assert "PROFILE_LOW_CONTRAST" in {w.code for w in profile.warnings}


def test_empty_mask_is_a_typed_error() -> None:
    truth = hero_bracket(LAYOUT)
    view = _view(truth)
    with pytest.raises(ReforgeError) as info:
        refine_profile(view, np.zeros(view.image.shape[:2], np.uint8))
    assert info.value.code == "PROFILE_EMPTY_MASK"
