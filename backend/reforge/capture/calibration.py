"""Photo calibration against the printed mat: markers → homography → metric mat frame.

Everything here is measured, never estimated by a model. Each result carries its own
residuals, so the Confidence Engine can use them as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from reforge.capture.mat import ARUCO_DICTIONARY, MARKERS_PER_MAT, MatLayout, mat_layout, pages_for_ids
from reforge.capture.photometry import linear_to_srgb, srgb_to_linear
from reforge.errors import ReforgeError

MIN_MARKERS = 4
RANSAC_THRESHOLD_MM = 1.0
CORNER_BIAS_ITERATIONS = 4
SCALE_CORRECTION_RANGE = (0.9, 1.1)

# Warning thresholds. They are conservative starting points, to be revisited with real photos.
WARN_RESIDUAL_MM = 0.15
WARN_MIN_PX_PER_MM = 6.0
WARN_PERSPECTIVE_RATIO = 1.25
WARN_CLIPPED_BACKGROUND_FRACTION = 0.5  # glare on the part itself is checked at segmentation, where the mask is known
WARN_HULL_FRACTION = 0.4


@dataclass(frozen=True)
class CalibrationWarning:
    code: str
    message: str


@dataclass(frozen=True)
class MarkerDetection:
    marker_id: int
    corners_px: np.ndarray  # (4, 2), ArUco order


@dataclass(frozen=True)
class Calibration:
    page: str
    image_size: tuple[int, int]  # (width, height)
    homography: np.ndarray  # image px → mat mm, print-scale correction included
    marker_ids: tuple[int, ...]
    rms_mm: float  # fit residual over all corners used
    max_mm: float
    loo_rms_mm: float | None  # leave-one-marker-out prediction RMS; None with fewer than 5 markers
    px_per_mm: float  # native resolution at the free-zone centre
    perspective_ratio: float  # max/min local resolution over the free-zone corners; 1.0 = parallel
    scale_correction: tuple[float, float]  # (x, y) factors from the caliper-checked bars
    warnings: tuple[CalibrationWarning, ...] = field(default=())
    # The marker correspondences behind the fit, per marker (n, 4, 2): de-biased image px and nominal mat mm.
    points_px: np.ndarray | None = field(default=None, repr=False)
    points_mm: np.ndarray | None = field(default=None, repr=False)
    # How far inside the true corners the detector put them, along each marker's diagonal (px); fitted jointly
    # with the homography. Edge blur in linear light pulls sub-pixel corners about 0.9 px inwards (simulated
    # 2026-10-27); a print's dot gain pushes them out.
    corner_bias_px: float = 0.0

    @property
    def mm_to_px(self) -> np.ndarray:
        """Physical mat mm → image px."""
        return np.linalg.inv(self.homography)

    def image_to_mat(self, points_px: np.ndarray) -> np.ndarray:
        return _apply(self.homography, points_px)

    def mat_to_image(self, points_mm: np.ndarray) -> np.ndarray:
        return _apply(np.linalg.inv(self.homography), points_mm)

    @property
    def layout(self) -> MatLayout:
        return mat_layout(self.page)


@dataclass(frozen=True)
class RectifiedView:
    """A top-down metric resampling of part of the mat: pixel (u, v) ↔ mm (x0 + u/s, y0 + v/s)."""

    image: np.ndarray
    px_per_mm: float
    origin_mm: tuple[float, float]

    def px_to_mm(self, points_px: np.ndarray) -> np.ndarray:
        pts = np.asarray(points_px, dtype=np.float64).reshape(-1, 2)
        return pts / self.px_per_mm + np.asarray(self.origin_mm)

    def mm_to_px(self, points_mm: np.ndarray) -> np.ndarray:
        pts = np.asarray(points_mm, dtype=np.float64).reshape(-1, 2)
        return (pts - np.asarray(self.origin_mm)) * self.px_per_mm


def _apply(h: np.ndarray, points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, h).reshape(-1, 2)


def _gray(image: np.ndarray) -> np.ndarray:
    if image is None or image.ndim not in (2, 3) or image.size == 0:
        raise ReforgeError("IMAGE_INVALID", "The image is empty or has an unsupported shape.")
    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _detector() -> cv2.aruco.ArucoDetector:
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementMaxIterations = 50
    params.cornerRefinementMinAccuracy = 0.01
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO_DICTIONARY), params)


def detect_markers(image: np.ndarray, page: str | None = None) -> tuple[MatLayout, list[MarkerDetection]]:
    """Find mat markers. With ``page=None`` the page is inferred from the marker IDs."""
    corners, ids, _ = _detector().detectMarkers(_gray(image))
    found = [] if ids is None else [
        (int(i), c.reshape(4, 2).astype(np.float64)) for i, c in zip(ids.flatten(), corners, strict=True)
    ]
    if page is None:
        pages = pages_for_ids({i for i, _ in found})
        if not pages:
            raise ReforgeError(
                "CAL_MARKERS_INSUFFICIENT", "No calibration markers were found.",
                "Photograph the part on the printed Re-Forge mat with the whole mat in view.",
            )
        if len(pages) > 1:
            raise ReforgeError(
                "CAL_LAYOUT_AMBIGUOUS", "Markers from more than one mat type are visible.",
                "Use a single printed mat (A4 or Letter) per photo.",
            )
        page = pages[0]
    layout = mat_layout(page)
    keep: dict[int, np.ndarray] = {}
    for marker_id, c in found:
        if marker_id in layout.marker_ids and marker_id not in keep:
            keep[marker_id] = c
    return layout, [MarkerDetection(i, keep[i]) for i in sorted(keep)]


def scale_correction_from_bars(measured_x_mm: float | None, measured_y_mm: float | None) -> tuple[float, float]:
    """Per-axis print-scale factors from caliper readings of the two 100 mm check bars."""
    factors = []
    for measured in (measured_x_mm, measured_y_mm):
        if measured is None:
            factors.append(1.0)
            continue
        factor = float(measured) / 100.0
        lo, hi = SCALE_CORRECTION_RANGE
        if not np.isfinite(factor) or not lo <= factor <= hi:
            raise ReforgeError(
                "CAL_SCALE_OUT_OF_RANGE",
                f"A check bar measured {measured} mm, more than 10 % from 100 mm.",
                "The mat was probably printed with 'fit to page'. Reprint at 100 % (actual size).",
            )
        factors.append(factor)
    return factors[0], factors[1]


def _fit(src_px: np.ndarray, dst_mm: np.ndarray) -> np.ndarray | None:
    h, _ = cv2.findHomography(src_px, dst_mm, 0)
    return h


def _diagonals(corners_px: np.ndarray) -> np.ndarray:
    """Unit vectors from each marker's centre to its corners, (n, 4, 2)."""
    out = corners_px - corners_px.mean(axis=1, keepdims=True)
    return out / np.linalg.norm(out, axis=2, keepdims=True)


def _fit_debiased(corners_px: np.ndarray, corners_mm: np.ndarray) -> tuple[np.ndarray | None, float]:
    """Homography plus a shared corner bias along the marker diagonals, fitted jointly.

    A sub-pixel corner detector sees a blurred black square slightly smaller (or, with printer dot gain, larger)
    than it is, the same amount in pixels on every marker. That's symmetric about each marker's centre, so it
    barely moves the homography, but it dominates the residuals unless it's modelled.
    """
    unit = _diagonals(corners_px)
    bias, h = 0.0, None
    for _ in range(CORNER_BIAS_ITERATIONS):
        h = _fit((corners_px + bias * unit).reshape(-1, 2), corners_mm.reshape(-1, 2))
        if h is None:
            return None, bias
        predicted = _apply(np.linalg.inv(h), corners_mm.reshape(-1, 2)).reshape(corners_px.shape)
        bias = float(np.mean(np.sum((predicted - corners_px) * unit, axis=2)))
    return h, bias


def _local_px_per_mm(mm_to_px: np.ndarray, point_mm: tuple[float, float]) -> float:
    """sqrt(|det J|) of the mm→px homography at ``point_mm``: the local linear resolution."""
    x, y = point_mm
    g = mm_to_px
    w = g[2, 0] * x + g[2, 1] * y + g[2, 2]
    u = (g[0, 0] * x + g[0, 1] * y + g[0, 2]) / w
    v = (g[1, 0] * x + g[1, 1] * y + g[1, 2]) / w
    jac = np.array([
        [(g[0, 0] - g[2, 0] * u) / w, (g[0, 1] - g[2, 1] * u) / w],
        [(g[1, 0] - g[2, 0] * v) / w, (g[1, 1] - g[2, 1] * v) / w],
    ])
    return float(np.sqrt(abs(np.linalg.det(jac))))


def _hull_area(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    return float(cv2.contourArea(cv2.convexHull(points.astype(np.float32))))


def calibrate(
    image: np.ndarray,
    page: str | None = None,
    bar_x_mm: float | None = None,
    bar_y_mm: float | None = None,
) -> Calibration:
    """Calibrate one photo of the mat.

    ``bar_x_mm`` and ``bar_y_mm`` are the user's caliper readings of the printed 100 mm bars.
    Without them the print scale is assumed exact; the Confidence Engine then reports that
    assumption as an uncertainty.
    """
    gray = _gray(image)
    layout, detections = detect_markers(gray, page)
    if len(detections) < MIN_MARKERS:
        raise ReforgeError(
            "CAL_MARKERS_INSUFFICIENT",
            f"Only {len(detections)} of {MARKERS_PER_MAT} mat markers were found; at least {MIN_MARKERS} are needed.",
            "Keep the whole mat in frame, avoid covering markers with your hand, and reduce glare.",
        )

    src = np.concatenate([d.corners_px for d in detections])
    dst = np.concatenate([layout.marker(d.marker_id).corners_mm() for d in detections])
    h_ransac, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_THRESHOLD_MM)
    warnings: list[CalibrationWarning] = []
    if h_ransac is None:
        raise ReforgeError("CAL_HOMOGRAPHY_FAILED", "The mat geometry could not be fitted.", "Retake the photo.")
    inliers = inlier_mask.reshape(-1, 4).all(axis=1)
    if not inliers.all():
        dropped = [d.marker_id for d, ok in zip(detections, inliers, strict=True) if not ok]
        warnings.append(CalibrationWarning("CAL_MARKERS_REJECTED", f"Inconsistent markers ignored: {dropped}."))
        detections = [d for d, ok in zip(detections, inliers, strict=True) if ok]
        if len(detections) < MIN_MARKERS:
            raise ReforgeError(
                "CAL_MARKERS_INSUFFICIENT",
                f"Only {len(detections)} consistent markers remain; at least {MIN_MARKERS} are needed.",
                "Make sure the mat lies flat and is not folded.",
            )
        src = np.concatenate([d.corners_px for d in detections])
        dst = np.concatenate([layout.marker(d.marker_id).corners_mm() for d in detections])

    corners_px, corners_mm = src.reshape(-1, 4, 2), dst.reshape(-1, 4, 2)
    h_nominal, corner_bias = _fit_debiased(corners_px, corners_mm)
    if h_nominal is None:
        raise ReforgeError("CAL_HOMOGRAPHY_FAILED", "The mat geometry could not be fitted.", "Retake the photo.")
    debiased = corners_px + corner_bias * _diagonals(corners_px)
    errors = np.linalg.norm(_apply(h_nominal, debiased.reshape(-1, 2)) - dst, axis=1)

    loo_rms: float | None = None
    if len(detections) >= 5:
        loo_errors = []
        for k in range(len(detections)):
            rest = np.arange(len(detections)) != k
            h_k, bias_k = _fit_debiased(corners_px[rest], corners_mm[rest])
            if h_k is not None:
                held_out = corners_px[k] + bias_k * _diagonals(corners_px[k:k + 1])[0]
                loo_errors.append(np.linalg.norm(_apply(h_k, held_out) - corners_mm[k], axis=1))
        if loo_errors:
            loo_rms = float(np.sqrt(np.mean(np.concatenate(loo_errors) ** 2)))

    sx, sy = scale_correction_from_bars(bar_x_mm, bar_y_mm)
    homography = np.diag([sx, sy, 1.0]) @ h_nominal
    mm_to_px = np.linalg.inv(homography)

    x0, y0, x1, y1 = layout.free_zone_mm
    fz = [(x0 * sx, y0 * sy), (x1 * sx, y0 * sy), (x1 * sx, y1 * sy), (x0 * sx, y1 * sy)]
    centre = ((x0 + x1) / 2 * sx, (y0 + y1) / 2 * sy)
    px_per_mm = _local_px_per_mm(mm_to_px, centre)
    corner_res = [_local_px_per_mm(mm_to_px, p) for p in fz]
    perspective_ratio = max(corner_res) / min(corner_res)

    rms = float(np.sqrt(np.mean(errors**2)))
    if len(detections) < 8:
        warnings.append(CalibrationWarning(
            "CAL_PARTIAL_MARKERS", f"{len(detections)} of {MARKERS_PER_MAT} markers used; accuracy may be reduced."))
    if rms > WARN_RESIDUAL_MM:
        warnings.append(CalibrationWarning(
            "CAL_HIGH_RESIDUAL", f"Marker fit residual {rms:.3f} mm. Is the mat flat and the photo sharp?"))
    if px_per_mm < WARN_MIN_PX_PER_MM:
        warnings.append(CalibrationWarning(
            "CAL_LOW_RESOLUTION", f"{px_per_mm:.1f} px/mm at the part; move closer or zoom in."))
    if perspective_ratio > WARN_PERSPECTIVE_RATIO:
        warnings.append(CalibrationWarning(
            "CAL_STRONG_TILT", f"Resolution varies {perspective_ratio:.2f}x across the mat; hold the phone parallel."))
    used = np.array([layout.marker(d.marker_id).center_mm for d in detections])
    every = np.array([m.center_mm for m in layout.markers])
    if _hull_area(used) < WARN_HULL_FRACTION * _hull_area(every):
        warnings.append(CalibrationWarning(
            "CAL_MARKERS_CLUSTERED", "Detected markers cover a small part of the mat; geometry is extrapolated."))

    zone = cv2.perspectiveTransform(np.array(fz, np.float64).reshape(-1, 1, 2), mm_to_px)
    mask = np.zeros(gray.shape, np.uint8)
    cv2.fillPoly(mask, [np.round(zone).astype(np.int32)], 1)
    if mask.any():
        bright = image.max(axis=2) if image.ndim == 3 else image
        clipped = float((bright[mask > 0] >= 254).mean())
        if clipped > WARN_CLIPPED_BACKGROUND_FRACTION:
            warnings.append(CalibrationWarning(
                "CAL_OVEREXPOSED",
                f"{clipped:.0%} of the mat background is clipped to pure white. Lower the exposure so light-coloured "
                "parts and glare stay visible."))

    return Calibration(
        page=layout.page,
        image_size=(gray.shape[1], gray.shape[0]),
        homography=homography,
        marker_ids=tuple(d.marker_id for d in detections),
        rms_mm=rms,
        max_mm=float(errors.max()),
        loo_rms_mm=loo_rms,
        px_per_mm=px_per_mm,
        perspective_ratio=perspective_ratio,
        scale_correction=(sx, sy),
        warnings=tuple(warnings),
        points_px=debiased,
        points_mm=corners_mm,
        corner_bias_px=corner_bias,
    )


def rectify(
    image: np.ndarray,
    calibration: Calibration,
    px_per_mm: float | None = None,
    region_mm: tuple[float, float, float, float] | None = None,
) -> RectifiedView:
    """Resample ``region_mm`` (default: the free zone) to a top-down metric image.

    The default resolution follows the photo's native resolution, so no detail is invented. Interpolation runs in
    linear light, so resampling doesn't shift edges the way blending sRGB-encoded values would.
    """
    if region_mm is None:
        x0, y0, x1, y1 = calibration.layout.free_zone_mm
        sx, sy = calibration.scale_correction
        region_mm = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
    x0, y0, x1, y1 = region_mm
    if px_per_mm is None:
        px_per_mm = float(np.clip(np.floor(calibration.px_per_mm * 2) / 2, 4.0, 20.0))
    to_out = np.array([[px_per_mm, 0, -x0 * px_per_mm], [0, px_per_mm, -y0 * px_per_mm], [0, 0, 1.0]])
    size = (int(round((x1 - x0) * px_per_mm)), int(round((y1 - y0) * px_per_mm)))
    image_to_out = to_out @ calibration.homography
    # Only the photo pixels the region maps from are converted to linear light.
    w, h = size
    src = _apply(np.linalg.inv(image_to_out), np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float64))
    cx0, cy0 = np.clip(np.floor(src.min(axis=0)).astype(int) - 4, 0, None)
    cx1 = int(np.clip(np.ceil(src[:, 0].max()) + 5, cx0 + 1, image.shape[1]))
    cy1 = int(np.clip(np.ceil(src[:, 1].max()) + 5, cy0 + 1, image.shape[0]))
    cx0, cy0 = min(int(cx0), cx1 - 1), min(int(cy0), cy1 - 1)
    crop = np.ascontiguousarray(image[cy0:cy1, cx0:cx1])
    if crop.dtype != np.uint8:
        raise ReforgeError("IMAGE_INVALID", "Rectification expects an 8-bit photo.")
    from_crop = image_to_out @ np.array([[1, 0, cx0], [0, 1, cy0], [0, 0, 1.0]])
    out = cv2.warpPerspective(srgb_to_linear(crop), from_crop, size, flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return RectifiedView(linear_to_srgb(out), px_per_mm, (x0, y0))
