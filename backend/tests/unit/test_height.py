"""Height (parallax) correction on exact silhouettes.

The 'photographed' region of a prism is computed exactly: in mat coordinates its top face is the footprint scaled
by m about the nadir, and the silhouette is the union of bottom, top and wall faces.
"""

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from reforge.capture.pose import CameraPose
from reforge.errors import ReforgeError
from reforge.geometry.circle import fit_circle
from reforge.geometry.height import correct_height, correct_outline, fit_hole_through_thickness
from reforge.vision.refine import Contour, HoleCandidate, RefinedProfile

THICKNESS = 3.0
HOLES = ((-30.0, 0.0), (30.0, 0.0))


def _bracket() -> Polygon:
    plate = box(-40, -14, 40, 14).buffer(-4, quad_segs=32).buffer(4, quad_segs=32)
    for x, y in HOLES:
        plate = plate.difference(Point(x, y).buffer(2.1, quad_segs=128))
    return plate


def _seen(part: Polygon, nadir: tuple[float, float], m: float) -> Polygon:
    top = affinity.scale(part, m, m, origin=(*nadir, 0.0))
    faces = [part, top]
    for bottom_ring, top_ring in zip([part.exterior, *part.interiors], [top.exterior, *top.interiors], strict=True):
        b, t = np.asarray(bottom_ring.coords), np.asarray(top_ring.coords)
        faces += [Polygon([b[i], b[i + 1], t[i + 1], t[i]]).buffer(0) for i in range(len(b) - 1)]
    return unary_union([f for f in faces if not f.is_empty])


def _pose(height: float, nadir: tuple[float, float], height_sigma: float = 0.0, nadir_sigma: float = 0.0):
    return CameraPose(focal_px=3000.0, focal_rel_sigma=0.0, focal_source="exif", exif_focal_35mm=26.0,
                      homography_focal_px=None, homography_rel_sigma=None, centre_mm=(*nadir, -height),
                      height_mm=height, height_sigma_mm=height_sigma, nadir_mm=nadir, nadir_sigma_mm=nadir_sigma,
                      warnings=())


CASES = [(250.0, (0.0, 0.0)), (250.0, (50.0, 30.0)), (400.0, (-120.0, 80.0)), (750.0, (10.0, -5.0))]


@pytest.mark.parametrize(("height", "nadir"), CASES)
def test_outline_footprint_is_recovered(height: float, nadir: tuple[float, float]) -> None:
    truth = Polygon(_bracket().exterior)
    m = height / (height - THICKNESS)
    seen = Polygon(_seen(truth, nadir, m).exterior)
    farthest = max(np.hypot(x - nadir[0], y - nadir[1]) for x, y in truth.exterior.coords)
    assert seen.hausdorff_distance(truth) > 0.5 * (m - 1) * farthest  # the bias being corrected
    corrected = Polygon(correct_outline(np.asarray(seen.exterior.coords)[:-1], nadir, m))
    assert corrected.hausdorff_distance(truth) < 0.002


@pytest.mark.parametrize(("height", "nadir"), [(250.0, (0.0, 0.0)), (250.0, (70.0, 40.0)), (250.0, (0.0, -60.0))])
def test_non_convex_outline_is_recovered_up_to_the_occluded_corners(height: float, nadir: tuple[float, float]) -> None:
    """A U-shaped clip: a 10 mm deep notch whose walls face both towards and away from the nadir.

    Near the notch's concave corners, rays that clip the corner see a gap shorter than (m - 1)·distance, which the
    top face hides: no single photo can see it. The footprint must lose no real material, and any extra material
    must sit within that theoretical zone around a concave corner.
    """
    truth = box(-30, -15, 30, 15).difference(box(-8, -15.1, 8, -5))
    m = height / (height - THICKNESS)
    seen = Polygon(_seen(truth, nadir, m).exterior)
    corrected = Polygon(correct_outline(np.asarray(seen.exterior.coords)[:-1], nadir, m))
    assert truth.difference(corrected).area < 1e-4
    corners = [(-8.0, -5.0), (8.0, -5.0)]
    for piece in getattr(extra := corrected.difference(truth), "geoms", [extra]):
        if piece.area < 1e-9:  # floating-point slivers along shared edges
            continue
        for x, y in np.asarray(piece.exterior.coords):
            reach = min(np.hypot(x - cx, y - cy) for cx, cy in corners)
            bound = (m - 1) * max(np.hypot(cx - nadir[0], cy - nadir[1]) for cx, cy in corners)
            assert reach <= bound + 1e-6


@pytest.mark.parametrize(("height", "nadir"), CASES)
def test_round_hole_is_recovered_by_the_two_disc_model(height: float, nadir: tuple[float, float]) -> None:
    m = height / (height - THICKNESS)
    seen = _seen(_bracket(), nadir, m)
    for ring in seen.interiors:
        pts = np.asarray(ring.coords)[:-1]
        fit = fit_hole_through_thickness(pts, nadir, m)
        true = min(HOLES, key=lambda c: np.hypot(fit.center[0] - c[0], fit.center[1] - c[1]))
        assert fit.diameter == pytest.approx(4.2, abs=0.002)
        assert np.hypot(fit.center[0] - true[0], fit.center[1] - true[1]) < 0.002
        assert fit.max_deviation < 0.01
        naive = fit_circle(pts)
        assert 4.2 - naive.diameter > 0.03  # what an uncorrected circle fit reports: the lens is too small


def test_non_round_hole_is_recovered_up_to_its_occluded_corner() -> None:
    """A square through-hole (not round, so no circle model): the dual set formula recovers it, except where rays
    only clip a corner and see no paper at all. The correction must never enlarge a hole (that would remove
    material the part has), and what it misses must sit within the occlusion bound of a corner."""
    height, nadir = 250.0, (60.0, 25.0)
    m = height / (height - THICKNESS)
    truth = box(-30, -15, 30, 15).difference(box(-21, -3, -15, 3))
    seen = _seen(truth, nadir, m).segmentize(0.05)  # refined contours are dense: about one point per pixel
    result = correct_height(_profile(seen), _pose(height, nadir), THICKNESS, round_max_deviation_mm=0.12)
    (hole,) = result.profile.holes
    assert hole.fit is None
    true_hole, found = box(-21, -3, -15, 3), Polygon(hole.contour.points_mm)
    assert found.difference(true_hole).area < 1e-6
    assert found.bounds == pytest.approx(true_hole.bounds, abs=0.002)
    missed = true_hole.difference(found)
    corners = list(true_hole.exterior.coords)[:-1]
    bound = (m - 1) * max(np.hypot(cx - nadir[0], cy - nadir[1]) for cx, cy in corners)
    for x, y in (c for g in getattr(missed, "geoms", [missed]) if g.area > 1e-9 for c in g.exterior.coords):
        assert min(np.hypot(x - cx, y - cy) for cx, cy in corners) <= bound + 1e-6
    assert Polygon(seen.interiors[0]).hausdorff_distance(true_hole) > 0.5  # uncorrected, for comparison


def _profile(seen: Polygon) -> RefinedProfile:
    outer = np.asarray(seen.exterior.coords)[:-1]
    holes = tuple(HoleCandidate(f"H{i}", Contour(np.asarray(r.coords)[:-1][::-1], Polygon(r).area), True, False)
                  for i, r in enumerate(seen.interiors))
    return RefinedProfile(outer=Contour(outer, Polygon(outer).area), holes=holes, band_mm=0.3, contrast_delta_e=60.0,
                          coarse_shift_mean_mm=0.0, coarse_shift_max_mm=0.0, refined=True, warnings=())


def test_correct_height_returns_the_buildable_footprint() -> None:
    height, nadir = 250.0, (50.0, 30.0)
    seen = _seen(_bracket(), nadir, height / (height - THICKNESS))
    result = correct_height(_profile(seen), _pose(height, nadir, 7.5, 7.0), THICKNESS, round_max_deviation_mm=0.12)
    x0, y0, x1, y1 = Polygon(result.profile.outer.points_mm).bounds
    assert (x1 - x0, y1 - y0) == pytest.approx((80.0, 28.0), abs=0.002)
    fits = sorted((h.fit for h in result.profile.holes), key=lambda f: f.center[0])
    for fit, (cx, cy) in zip(fits, HOLES, strict=True):
        assert fit.diameter == pytest.approx(4.2, abs=0.002)
        assert np.hypot(fit.center[0] - cx, fit.center[1] - cy) < 0.002
    assert result.magnification == pytest.approx(250 / 247)
    farthest = max(np.hypot(x - 50.0, y - 30.0) for x, y in seen.exterior.coords)
    assert result.max_shift_mm == pytest.approx(farthest * (1 - 247 / 250), rel=0.02)  # the far corner moves most
    # 2σ, first order: the 7 mm nadir error moves far-facing edges by (m - 1)·7 = 0.085 mm, and the 7.5 mm
    # camera-height error scales the 1.2 mm correction by 3 %: 2·hypot(0.085, 0.037) = 0.19 mm.
    assert result.u_persp_mm == pytest.approx(2 * np.hypot((250 / 247 - 1) * 7.0, farthest * 3 * 7.5 / 247**2),
                                              rel=0.01)
    assert result.occlusion_bound_mm == pytest.approx(result.max_shift_mm, rel=0.02)


def test_thickness_beyond_the_camera_is_a_typed_error() -> None:
    seen = _seen(_bracket(), (0.0, 0.0), 1.01)
    with pytest.raises(ReforgeError) as info:
        correct_height(_profile(seen), _pose(250.0, (0.0, 0.0)), 300.0, round_max_deviation_mm=0.12)
    assert info.value.code == "HEIGHT_CORRECTION_FAILED"
