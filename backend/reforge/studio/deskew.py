"""Deskew a perspective photo of a rectangular part (the Studio's "flatten" step).

A panel filter shot at 30° can never mirror-match: the far side is foreshortened, so no 2D axis fits (the
BMW panel refused at 5252 mm² unexplained vs 685 mm² added). But a rectangle photographed in perspective is a
known warp: with the part's four corners and its measured length × width, a homography returns the top-down
view, at an exactly known scale. The rectified photo then runs as a normal ruler-mode job.

Honesty notes: the rectangle assumption and the corner positions come from the user (the Studio shows the
rectified preview for approval before any job runs). The torn corner is estimated — its neighbourhood stays
excluded as fracture anyway. The mirror gate still judges the result: a wrong aspect ratio rectifies to a
non-symmetric shape and refuses, so the gate validates the entered size.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from reforge.errors import ReforgeError

MAX_LONG_SIDE_PX = 1600  # the rectified photo's resolution cap


@dataclass(frozen=True)
class DeskewResult:
    image_bgr: np.ndarray  # the top-down view, length_mm × width_mm, plus the margin
    px_per_mm: float  # exact, by construction
    corners_px: tuple[tuple[float, float], ...]  # TL, TR, BR, BL as used
    margin_px: tuple[int, int] = (0, 0)  # flat-background padding around the part's quad


def order_corners(corners: np.ndarray) -> np.ndarray:
    """Four image points in TL, TR, BR, BL order (the standard sum/difference split)."""
    pts = np.asarray(corners, dtype=np.float64).reshape(-1, 2)
    if len(pts) != 4 or len({tuple(np.round(p, 3)) for p in pts}) != 4:
        raise ReforgeError("DESKEW_BAD_CORNERS", f"Need 4 distinct corners, got {len(pts)}.",
                           "Click the part's four corners: the rectangle's corners, in any order.")
    centre = pts.mean(axis=0)
    cyclic = pts[np.argsort(np.arctan2(pts[:, 1] - centre[1], pts[:, 0] - centre[0]))]
    start = int(np.argmin(cyclic.sum(axis=1)))  # the top-left-most corner (ties: any — output just rotates)
    ordered = np.array([cyclic[(start + i) % 4] for i in range(4)])
    diag1, diag2 = ordered[2] - ordered[0], ordered[3] - ordered[1]
    area = float(abs(diag1[0] * diag2[1] - diag1[1] * diag2[0]) / 2)
    if area < 100.0:
        raise ReforgeError("DESKEW_BAD_CORNERS", "The four corners cover almost no area.",
                           "Click the part's four corners, spread over the whole part.")
    return ordered


def deskew_quad(image_bgr: np.ndarray, corners: np.ndarray, length_mm: float, width_mm: float,
                margin: float = 0.25) -> DeskewResult:
    """Warp the quad to a top-down ``length_mm`` × ``width_mm`` view. ``corners`` in any order; the long image
    side carries ``length_mm`` (so corner order never swaps the sides by accident). ``margin`` pads the output
    with flat background (sampled from the photo's corners), so the part keeps a background to segment from;
    the homography — and the exact scale — is unchanged, only the canvas grows."""
    if not (np.isfinite(length_mm) and np.isfinite(width_mm)) or min(length_mm, width_mm) <= 0:
        raise ReforgeError("DESKEW_BAD_SIZE", f"L×W must be positive mm (got {length_mm}×{width_mm}).",
                           "Measure the intact part's length and width with a ruler or caliper.")
    if max(length_mm, width_mm) > 5000:
        raise ReforgeError("DESKEW_BAD_SIZE", f"L×W looks wrong ({length_mm}×{width_mm} mm).",
                           "Measure the intact part's length and width with a ruler or caliper.")
    ordered = order_corners(corners)
    long_mm, short_mm = max(length_mm, width_mm), min(length_mm, width_mm)
    quad_sides = [float(np.linalg.norm(ordered[(i + 1) % 4] - ordered[i])) for i in range(4)]
    long_px = max(quad_sides)
    # The output follows the source density (no invented pixels), capped; the long side carries long_mm.
    px_per_mm = max(min(MAX_LONG_SIDE_PX / long_mm, long_px / long_mm), 0.5)
    landscape = (quad_sides[0] + quad_sides[2]) >= (quad_sides[1] + quad_sides[3])
    long_px = max(8, int(round(long_mm * px_per_mm)))
    short_px = max(8, int(round(long_px * short_mm / long_mm)))  # square pixels, exact aspect
    w_px, h_px = (long_px, short_px) if landscape else (short_px, long_px)
    dst = np.array([[0, 0], [w_px - 1, 0], [w_px - 1, h_px - 1], [0, h_px - 1]], dtype=np.float64)
    matrix = cv2.getPerspectiveTransform(ordered.astype(np.float32), dst.astype(np.float32))
    mx, my = int(round(w_px * margin)), int(round(h_px * margin))
    big = np.array([[-mx, -my], [w_px - 1 + mx, -my], [w_px - 1 + mx, h_px - 1 + my], [-mx, h_px - 1 + my]])
    inv = np.linalg.inv(matrix)
    src = (inv @ np.concatenate([big, np.ones((4, 1))], axis=1).T).T
    src = src[:, :2] / src[:, 2:3]
    matrix2 = cv2.getPerspectiveTransform(src.astype(np.float32),
                                          (big + [mx, my]).astype(np.float32))
    corners_px = image_bgr[np.array([5, -6])[:, None], np.array([5, -6])]
    bg = tuple(float(v) for v in np.median(corners_px.reshape(-1, 3), axis=0))
    warped = cv2.warpPerspective(image_bgr, matrix2, (w_px + 2 * mx, h_px + 2 * my), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=bg)
    exact = ((w_px - 1) / long_mm) if landscape else ((h_px - 1) / long_mm)
    return DeskewResult(warped, float(exact),
                        tuple((float(x), float(y)) for x, y in ordered), (mx, my))
