"""Camera pose from one mat photo: focal length, camera centre, height above the mat and nadir.

The mat-plane homography G (mat mm → image px) equals K·[r1 r2 t] up to scale. With square pixels, no skew and a
centred principal point, the constraints r1·r2 = 0 and |r1| = |r2| give the focal length, provided the view is
tilted enough. A photo's EXIF focal length (35 mm equivalent) gives it otherwise, and the two cross-check each other.
Knowing K, the camera centre follows.

Why it matters: the part's top face is h mm above the mat, so the mat-plane homography sees it enlarged about the
nadir by H / (H - h). Correcting that (``reforge.geometry.height``) needs H and the nadir, each with an uncertainty.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np

from reforge.capture.calibration import Calibration
from reforge.errors import ReforgeError

FULL_FRAME_DIAGONAL_MM = float(np.hypot(36.0, 24.0))
PRIOR_FOCAL_35MM = 26.0  # a typical phone main camera; used only when nothing better exists, and flagged
PRIOR_REL_SIGMA = 0.25  # 1σ: covers main cameras (≈ 22-30 mm), not zoom lenses
EXIF_REL_SIGMA = 0.03  # 1σ: nominal focal length, focus breathing at 25-75 cm, rounding of the 35 mm value
HOMOGRAPHY_FLOOR_REL_SIGMA = 0.01  # 1σ model error: principal point and pixel-shape assumptions
HOMOGRAPHY_USABLE_REL_SIGMA = 0.15  # beyond this the view is too parallel to measure the focal length
PRINCIPAL_POINT_REL_SIGMA = 0.01  # 1σ, as a fraction of the image diagonal
MISMATCH_SIGMAS = 3.0
BOOTSTRAP_ROUNDS = 64


@dataclass(frozen=True)
class PoseWarning:
    code: str
    message: str


@dataclass(frozen=True)
class CameraPose:
    focal_px: float
    focal_rel_sigma: float  # 1σ, relative
    focal_source: str  # "exif+homography" | "exif" | "homography" | "prior"
    exif_focal_35mm: float | None
    homography_focal_px: float | None
    homography_rel_sigma: float | None  # 1σ; None when the view is too parallel to measure it
    centre_mm: tuple[float, float, float]  # mat frame, z into the table: the camera has z < 0
    height_mm: float  # camera centre above the mat plane
    height_sigma_mm: float  # 1σ
    nadir_mm: tuple[float, float]  # the mat point directly below the camera centre
    nadir_sigma_mm: float  # 1σ, radial
    warnings: tuple[PoseWarning, ...]


def focal_35mm_from_exif(data: bytes) -> float | None:
    """The 35 mm-equivalent focal length from a photo's EXIF, or None. Nothing else is read."""
    from PIL import ExifTags, Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            value = image.getexif().get_ifd(ExifTags.IFD.Exif).get(ExifTags.Base.FocalLengthIn35mmFilm)
    except Exception:  # an unreadable or absent EXIF block is simply "no metadata"
        return None
    try:
        focal = float(value)
    except (TypeError, ValueError):
        return None
    return focal if 8.0 <= focal <= 400.0 else None


def focal_from_homography(mm_to_px: np.ndarray, image_size: tuple[int, int]) -> float | None:
    """Focal length in px from the two orthonormality constraints, or None if the view is too parallel."""
    w, h = image_size
    diag = float(np.hypot(w, h))
    to_unit = np.array([[1 / diag, 0, -(w - 1) / 2 / diag], [0, 1 / diag, -(h - 1) / 2 / diag], [0, 0, 1.0]])
    g = to_unit @ mm_to_px
    g = g / np.linalg.norm(g[:, :2])
    (a, b), (c, e), (p, q) = g[0, :2], g[1, :2], g[2, :2]
    # r1 ∝ (a/f, c/f, p) and r2 ∝ (b/f, e/f, q) in diagonal units. With w = 1/f², both constraints are linear in w.
    coef = np.array([a * b + c * e, a * a + c * c - b * b - e * e])
    rhs = np.array([p * q, p * p - q * q])
    denom = float(coef @ coef)
    if denom <= 0:
        return None
    inv_f2 = -float(coef @ rhs) / denom
    if not np.isfinite(inv_f2) or inv_f2 <= 0:
        return None
    return diag / float(np.sqrt(inv_f2))


def _homography_focal(cal: Calibration, rng: np.random.Generator) -> tuple[float | None, float | None]:
    """Focal length from the calibration and its bootstrap spread over markers (1σ, relative)."""
    f0 = focal_from_homography(cal.mm_to_px, cal.image_size)
    if f0 is None or cal.points_px is None or len(cal.points_px) < 5:
        return f0, None
    scale = np.diag([*cal.scale_correction, 1.0])
    n = len(cal.points_px)
    logs = []
    for _ in range(BOOTSTRAP_ROUNDS):
        pick = rng.integers(0, n, n)
        if len(set(pick.tolist())) < 4:
            continue
        hb, _ = cv2.findHomography(cal.points_px[pick].reshape(-1, 2), cal.points_mm[pick].reshape(-1, 2), 0)
        fb = None if hb is None else focal_from_homography(np.linalg.inv(scale @ hb), cal.image_size)
        logs.append(np.nan if fb is None else np.log(fb))
    logs = np.asarray(logs)
    if len(logs) < BOOTSTRAP_ROUNDS // 2 or np.isnan(logs).mean() > 0.1:
        return f0, None  # too parallel: the estimate isn't even defined in a sizeable share of resamples
    return f0, float(np.hypot(np.nanstd(logs), HOMOGRAPHY_FLOOR_REL_SIGMA))


def _centre(mm_to_px: np.ndarray, focal_px: float, principal: tuple[float, float]) -> np.ndarray:
    k = np.array([[focal_px, 0, principal[0]], [0, focal_px, principal[1]], [0, 0, 1.0]])
    m = np.linalg.solve(k, mm_to_px)
    lam = 2.0 / (np.linalg.norm(m[:, 0]) + np.linalg.norm(m[:, 1]))
    r1, r2, t = lam * m[:, 0], lam * m[:, 1], lam * m[:, 2]
    if t[2] < 0:  # the mat must be in front of the camera
        r1, r2, t = -r1, -r2, -t
    u, _, vt = np.linalg.svd(np.column_stack([r1, r2, np.cross(r1, r2)]))
    return -(u @ vt).T @ t


def estimate_pose(cal: Calibration, focal_35mm: float | None = None, *, seed: int = 0) -> CameraPose:
    """Camera pose for one calibrated photo. ``focal_35mm`` comes from the photo's EXIF, when it has one."""
    w, h = cal.image_size
    diag = float(np.hypot(w, h))
    warnings: list[PoseWarning] = []
    f_h, s_h = _homography_focal(cal, np.random.default_rng(seed))
    usable_h = f_h is not None and s_h is not None and s_h <= HOMOGRAPHY_USABLE_REL_SIGMA
    f_e = None if focal_35mm is None else focal_35mm / FULL_FRAME_DIAGONAL_MM * diag

    if f_e is not None and usable_h:
        gap = abs(np.log(f_h / f_e))
        if gap <= MISMATCH_SIGMAS * np.hypot(s_h, EXIF_REL_SIGMA):
            w_h, w_e = 1 / s_h**2, 1 / EXIF_REL_SIGMA**2
            focal = float(np.exp((w_h * np.log(f_h) + w_e * np.log(f_e)) / (w_h + w_e)))
            rel, source = float(1 / np.sqrt(w_h + w_e)), "exif+homography"
        else:
            focal, source = (f_h, "homography") if s_h < EXIF_REL_SIGMA else (f_e, "exif")
            rel = float(max(s_h if source == "homography" else EXIF_REL_SIGMA, gap))
            warnings.append(PoseWarning(
                "POSE_FOCAL_MISMATCH",
                f"The photo's metadata says {focal_35mm:.0f} mm (35 mm equivalent), but the mat's perspective implies "
                f"{f_h / diag * FULL_FRAME_DIAGONAL_MM:.0f} mm; using the {source} value with a widened uncertainty. "
                "Was the photo cropped or digitally zoomed?"))
    elif f_e is not None:
        focal, rel, source = f_e, EXIF_REL_SIGMA, "exif"
    elif usable_h:
        focal, rel, source = f_h, s_h, "homography"
    else:
        focal, rel, source = PRIOR_FOCAL_35MM / FULL_FRAME_DIAGONAL_MM * diag, PRIOR_REL_SIGMA, "prior"
        warnings.append(PoseWarning(
            "POSE_FOCAL_ASSUMED",
            "The photo has no focal-length metadata and is too parallel to the mat to measure it, so a typical "
            "phone lens is assumed: the height correction is uncertain, and wrong if a zoom lens was used. "
            "Upload the original photo file (not a screenshot or a messaging-app copy)."))

    pp = ((w - 1) / 2, (h - 1) / 2)
    g = cal.mm_to_px
    centre = _centre(g, focal, pp)
    if not np.all(np.isfinite(centre)) or centre[2] >= 0:
        raise ReforgeError("POSE_INVALID", "The camera position could not be recovered from the mat.",
                           "Retake the photo with the whole mat in view.")
    # First-order uncertainty of the centre from the focal length and principal point.
    d_pp = PRINCIPAL_POINT_REL_SIGMA * diag
    deltas = [(_centre(g, focal * np.exp(rel), pp) - _centre(g, focal * np.exp(-rel), pp)) / 2,
              (_centre(g, focal, (pp[0] + d_pp, pp[1])) - _centre(g, focal, (pp[0] - d_pp, pp[1]))) / 2,
              (_centre(g, focal, (pp[0], pp[1] + d_pp)) - _centre(g, focal, (pp[0], pp[1] - d_pp))) / 2]
    cov = sum(np.outer(d, d) for d in deltas)
    return CameraPose(
        focal_px=float(focal), focal_rel_sigma=float(rel), focal_source=source, exif_focal_35mm=focal_35mm,
        homography_focal_px=f_h, homography_rel_sigma=s_h if usable_h else None,
        centre_mm=tuple(float(v) for v in centre), height_mm=float(-centre[2]),
        height_sigma_mm=float(np.sqrt(cov[2, 2])), nadir_mm=(float(centre[0]), float(centre[1])),
        nadir_sigma_mm=float(np.sqrt(cov[0, 0] + cov[1, 1])), warnings=tuple(warnings))
