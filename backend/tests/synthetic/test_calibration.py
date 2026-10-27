"""AT-1: calibration on SYNTHETIC mat views (rendered, exact ground truth; not real photos).

Pass condition from PLAN §10: scale error < 0.2 % across tilt 0–25°, noise, blur and partial
occlusion; fewer than 4 markers raises CAL_MARKERS_INSUFFICIENT instead of crashing.
"""

import numpy as np
import pytest

from reforge.capture.calibration import calibrate, rectify, scale_correction_from_bars
from reforge.capture.mat import mat_layout
from reforge.errors import ReforgeError
from tests.synthetic.scene import make_camera, render_view

MAX_SCALE_ERROR = 0.002  # AT-1


def _free_zone_points(layout, n: int = 6, scale: float = 1.0) -> np.ndarray:
    x0, y0, x1, y1 = layout.free_zone_mm
    xs, ys = np.meshgrid(np.linspace(x0, x1, n), np.linspace(y0, y1, n))
    return np.column_stack([xs.ravel(), ys.ravel()]) * scale


def _hundred_mm_pairs(layout, scale: float = 1.0) -> list[tuple[np.ndarray, np.ndarray]]:
    """Point pairs 100 mm apart (physically): horizontal, vertical and diagonal, inside the free zone."""
    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    d = 100 / np.sqrt(2)
    pairs = [((cx - 50, cy), (cx + 50, cy)), ((cx, cy - 50), (cx, cy + 50)),
             ((cx - d / 2, cy - d / 2), (cx + d / 2, cy + d / 2))]
    return [(np.array(a) * scale, np.array(b) * scale) for a, b in pairs]


def _scale_errors(cal, camera, layout, scale: float = 1.0) -> list[float]:
    errors = []
    for a, b in _hundred_mm_pairs(layout, scale):
        measured = cal.image_to_mat(camera.project(np.vstack([a, b])))
        true = float(np.linalg.norm(b - a))
        errors.append(abs(float(np.linalg.norm(measured[1] - measured[0])) - true) / true)
    return errors


CASES = [  # tilt_x, tilt_y, roll (degrees)
    (0, 0, 0),
    (10, 0, 5),
    (0, 18, -10),
    (20, 12, 30),
    (25, 0, 90),
    (17.7, 17.7, 0),  # 25° combined tilt
]


@pytest.mark.parametrize(("tilt_x", "tilt_y", "roll"), CASES)
def test_scale_error_within_at1(tilt_x: float, tilt_y: float, roll: float) -> None:
    layout = mat_layout("A4")
    camera = make_camera(layout, tilt_x, tilt_y, roll)
    image = render_view(layout, camera, blur_sigma=0.8, noise_sigma=2.0, seed=int(tilt_x * 7 + tilt_y))
    cal = calibrate(image)
    assert cal.page == "A4"
    assert len(cal.marker_ids) == 12
    assert max(_scale_errors(cal, camera, layout)) < MAX_SCALE_ERROR
    truth = _free_zone_points(layout)
    point_error = np.linalg.norm(cal.image_to_mat(camera.project(truth)) - truth, axis=1).max()
    assert point_error < 0.25, f"max free-zone point error {point_error:.3f} mm"
    assert cal.loo_rms_mm is not None and cal.loo_rms_mm >= 0.0


def test_partial_occlusion_still_meets_at1() -> None:
    layout = mat_layout("A4")
    camera = make_camera(layout, 12, -8, 15)
    image = render_view(layout, camera, blur_sigma=0.8, noise_sigma=2.0, occlude_ids=(0, 1, 5, 9, 10))
    cal = calibrate(image)
    assert len(cal.marker_ids) == 7
    assert "CAL_PARTIAL_MARKERS" in {w.code for w in cal.warnings}
    assert max(_scale_errors(cal, camera, layout)) < MAX_SCALE_ERROR


def test_fewer_than_four_markers_is_a_typed_error() -> None:
    layout = mat_layout("A4")
    camera = make_camera(layout)
    image = render_view(layout, camera, occlude_ids=tuple(range(9)))
    with pytest.raises(ReforgeError) as info:
        calibrate(image)
    assert info.value.code == "CAL_MARKERS_INSUFFICIENT"
    assert info.value.hint


def test_no_mat_in_image_is_a_typed_error() -> None:
    with pytest.raises(ReforgeError) as info:
        calibrate(np.full((900, 1200, 3), 128, np.uint8))
    assert info.value.code == "CAL_MARKERS_INSUFFICIENT"


def test_invalid_image_is_a_typed_error() -> None:
    with pytest.raises(ReforgeError) as info:
        calibrate(np.zeros((0, 0), np.uint8))
    assert info.value.code == "IMAGE_INVALID"


def test_print_scale_correction_from_check_bars() -> None:
    """A mat printed at 97 % gives 3 % errors until the caliper-measured bars correct it."""
    layout = mat_layout("A4")
    s = 0.97
    camera = make_camera(layout, 8, 5, 0, physical_scale=s)
    image = render_view(layout, camera, physical_scale=s, blur_sigma=0.8, noise_sigma=2.0)
    uncorrected = calibrate(image)
    assert min(_scale_errors(uncorrected, camera, layout, scale=s)) > 0.025
    corrected = calibrate(image, bar_x_mm=100 * s, bar_y_mm=100 * s)
    assert corrected.scale_correction == pytest.approx((s, s))
    assert max(_scale_errors(corrected, camera, layout, scale=s)) < MAX_SCALE_ERROR


def test_out_of_range_bar_reading_is_rejected() -> None:
    with pytest.raises(ReforgeError) as info:
        scale_correction_from_bars(85.0, None)
    assert info.value.code == "CAL_SCALE_OUT_OF_RANGE"
    assert scale_correction_from_bars(None, 100.4) == pytest.approx((1.0, 1.004))


def test_letter_mat_is_recognised() -> None:
    layout = mat_layout("Letter")
    camera = make_camera(layout, 5, 5, 0)
    cal = calibrate(render_view(layout, camera, blur_sigma=0.8, noise_sigma=2.0))
    assert cal.page == "Letter"
    assert max(_scale_errors(cal, camera, layout)) < MAX_SCALE_ERROR


def test_perspective_ratio_tracks_tilt() -> None:
    layout = mat_layout("A4")
    flat = calibrate(render_view(layout, make_camera(layout)))
    tilted = calibrate(render_view(layout, make_camera(layout, 25, 0, 0)))
    assert flat.perspective_ratio == pytest.approx(1.0, abs=0.01)
    assert tilted.perspective_ratio > flat.perspective_ratio + 0.05


def test_overexposed_mat_background_warns() -> None:
    layout = mat_layout("A4")
    camera = make_camera(layout)
    normal = calibrate(render_view(layout, camera, paper=235))
    clipped = calibrate(render_view(layout, camera, paper=255))
    assert "CAL_OVEREXPOSED" not in {w.code for w in normal.warnings}
    assert "CAL_OVEREXPOSED" in {w.code for w in clipped.warnings}


def test_rectified_view_is_metric() -> None:
    """Rectify the whole page and re-detect the markers: each corner must land where its mm says."""
    layout = mat_layout("A4")
    camera = make_camera(layout, 15, -10, 20)
    image = render_view(layout, camera, blur_sigma=0.8, noise_sigma=2.0)
    cal = calibrate(image)
    view = rectify(image, cal, px_per_mm=6.0, region_mm=(0.0, 0.0, layout.width_mm, layout.height_mm))
    assert view.image.shape[:2] == (round(layout.height_mm * 6), round(layout.width_mm * 6))
    from reforge.capture.calibration import detect_markers

    _, detections = detect_markers(view.image)
    assert len(detections) >= 10
    deviations = np.concatenate(
        [view.px_to_mm(d.corners_px) - layout.marker(d.marker_id).corners_mm() for d in detections]
    )
    # No systematic offset: a convention or origin bug would show as a shared shift of ~0.1 mm.
    assert np.abs(deviations.mean(axis=0)).max() < 0.02, f"systematic offset {deviations.mean(axis=0)} mm"
    centres = [np.abs(view.px_to_mm(d.corners_px).mean(axis=0) - np.array(layout.marker(d.marker_id).center_mm)).max()
               for d in detections]
    assert max(centres) < 0.1, f"worst marker-centre deviation {max(centres):.3f} mm"
    assert np.abs(deviations).max() < 0.4  # per-corner jitter at ~4 px/mm native: a gross-error guard only
    round_trip = view.px_to_mm(view.mm_to_px(np.array([[50.0, 70.0]])))
    assert round_trip == pytest.approx(np.array([[50.0, 70.0]]))
