"""Metrology-grade part boundary from a coarse mask, on the rectified mat view.

The segmenter (SAM 3.1 in production) decides *what* the part is. This module decides *where* its edges
are, to sub-pixel precision, using the known mat background. The coarse mask only bounds the search:
the boundary can move at most ``band_mm`` from it, so a shadow or reflection can't drag it far.

Edge model: each pixel's *linear-light* colour is projected onto the line from the paper colour to the part
colour. A pixel that integrates a fraction b of plastic and 1 - b of paper then has t = b exactly, and for a
symmetric blur the true edge is where t = 0.5. Thresholding sRGB-encoded or Lab values instead puts a dark
part's edge 0.4–1.1 px inside the true edge (simulated 2026-10-27). Lab is kept for the colour distance (ΔE)
and glare tests, which are perceptual questions.
Through-holes are paper seen through the part, so they're found from colour, even when the coarse
mask filled them in.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from shapely.geometry import Point, Polygon
from skimage.measure import find_contours

from reforge.capture.calibration import RectifiedView
from reforge.capture.photometry import srgb_to_linear
from reforge.errors import ReforgeError
from reforge.geometry.circle import CircleFit
from reforge.geometry.contour import smooth_closed

MIN_CONTRAST_DELTA_E = 12.0
MAX_PART_COLOUR_SPREAD_DELTA_E = 15.0  # 75th percentile of the part pixels' ΔE from the part's median colour
NOT_PAPER_DELTA_E = 20.0
MIN_PART_SHARE_OF_NOT_PAPER = 0.5
MIN_BACKGROUND_PIXELS = 500
GLARE_FRACTION = 0.3
BAND_SATURATION_FRACTION = 0.05


@dataclass(frozen=True)
class Contour:
    points_mm: np.ndarray  # (N, 2) closed polyline; the first point is not repeated
    area_mm2: float

    @property
    def polygon(self) -> Polygon:
        return Polygon(self.points_mm)


@dataclass(frozen=True)
class HoleCandidate:
    hole_id: str
    contour: Contour
    mask_agrees: bool  # the coarse mask also excludes this region
    glare_suspect: bool  # brighter than the paper: possibly a highlight, not a hole
    fit: CircleFit | None = None  # set by the height correction for round holes; otherwise fit ``contour``


@dataclass(frozen=True)
class ProfileWarning:
    code: str
    message: str


@dataclass(frozen=True)
class RefinedProfile:
    outer: Contour
    holes: tuple[HoleCandidate, ...]
    band_mm: float
    contrast_delta_e: float  # colour distance between part and paper (CIE Lab)
    coarse_shift_mean_mm: float  # how far refinement moved the coarse boundary
    coarse_shift_max_mm: float
    refined: bool  # False if contrast was too low and the coarse boundary was kept
    warnings: tuple[ProfileWarning, ...]
    outer_raw: Contour | None = None  # the traced edge before smoothing: evidence, and the input for roughness
    # Edge spread measured on the photo (Gaussian-equivalent σ, mm). A blurred curve's 0.5 iso-contour sits σ²/(2R)
    # towards its centre of curvature, so a hole of radius R traces that much too small.
    edge_sigma_mm: float | None = None
    colour_spread_delta_e: float | None = None  # 75th percentile ΔE of the part's pixels from its median colour
    trace_share: float | None = None  # traced part area / everything in the view that isn't mat paper


def _disk(radius_px: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius_px + 1, 2 * radius_px + 1))


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """The mask with every enclosed hole filled, as uint8."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros(mask.shape, np.uint8)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    return filled | mask.astype(np.uint8)


def _signed_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def refine_profile(
    view: RectifiedView,
    coarse_mask: np.ndarray,
    *,
    band_mm: float = 0.3,
    min_hole_area_mm2: float = 0.8,
    background_margin_mm: float = 2.0,
) -> RefinedProfile:
    image = view.image
    if image.ndim != 3:
        raise ReforgeError("IMAGE_INVALID", "Boundary refinement needs a colour (BGR) rectified view.")
    mask = np.asarray(coarse_mask).astype(bool)
    if mask.shape != image.shape[:2]:
        raise ReforgeError("PROFILE_MASK_SHAPE", f"Mask shape {mask.shape} != view shape {image.shape[:2]}.")
    if not mask.any():
        raise ReforgeError("PROFILE_EMPTY_MASK", "The segmentation mask is empty.",
                           "Click on the part to give the segmenter a point prompt.")

    s = view.px_per_mm
    band_px = max(2, int(np.ceil(band_mm * s)))
    kernel = _disk(band_px)
    # Geometry comes from the outline with its holes filled. Holes are then found by colour, whether or not the
    # segmenter left them open: a mask's hole edges can sit several pixels off the true edge (live SAM 3.1 finding,
    # 2026-10-27), and the narrow band would otherwise clip the real edge. The original mask is kept as evidence.
    m8 = _fill_holes(mask)
    dilated = cv2.dilate(m8, kernel).astype(bool)
    eroded = cv2.erode(m8, kernel).astype(bool)
    background = ~cv2.dilate(m8, _disk(max(band_px + 1, int(np.ceil(background_margin_mm * s))))).astype(bool)
    if background.sum() < MIN_BACKGROUND_PIXELS:
        raise ReforgeError("PROFILE_NO_BACKGROUND", "Too little visible mat around the part.",
                           "Centre the part in the mat's free zone with space around it.")

    image = image if image.dtype == np.uint8 else np.clip(image, 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(image.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)
    paper = np.median(lab[background], axis=0)
    solid = cv2.erode(mask.astype(np.uint8), kernel).astype(bool)  # plastic only, so holes don't bias the colour
    plastic = solid if solid.any() else mask
    part = np.median(lab[plastic], axis=0)
    contrast = float(np.linalg.norm(part - paper))
    warnings: list[ProfileWarning] = []

    spread = float(np.percentile(np.linalg.norm(lab[plastic] - part, axis=1), 75))
    if spread > MAX_PART_COLOUR_SPREAD_DELTA_E:
        warnings.append(ProfileWarning(
            "PROFILE_NONUNIFORM_COLOUR",
            f"The part isn't one uniform colour (spread ΔE {spread:.0f}): the edge model assumes a single-colour part "
            "on the mat, so edges may be traced wrong. Painted, rusty, printed or multi-material parts aren't "
            "supported yet."))
    # Everything in the view that isn't mat paper, ignoring specks: the traced part should account for most of it.
    not_paper = (np.linalg.norm(lab - paper, axis=2) > NOT_PAPER_DELTA_E).astype(np.uint8)
    not_paper = cv2.morphologyEx(not_paper, cv2.MORPH_OPEN, _disk(max(1, int(round(0.5 * s)))))
    share = float(m8.sum()) / max(float(not_paper.sum()), 1.0)
    if share < MIN_PART_SHARE_OF_NOT_PAPER:
        warnings.append(ProfileWarning(
            "PROFILE_PARTIAL",
            f"The traced part covers only {share:.0%} of what isn't mat paper. Is the part one uniform colour, alone "
            "on the mat? A multi-coloured or textured object is traced only in pieces."))
    refined = contrast >= MIN_CONTRAST_DELTA_E
    if refined:
        light = srgb_to_linear(image)
        paper_light = np.median(light[background], axis=0)
        direction = np.median(light[plastic], axis=0) - paper_light
        t = ((light - paper_light) @ direction) / float(direction @ direction)
    else:
        warnings.append(ProfileWarning(
            "PROFILE_LOW_CONTRAST",
            f"Part and mat differ by only ΔE {contrast:.1f}; the segmenter's boundary is kept unrefined. "
            "Use a contrasting background for light-coloured parts."))
        t = mask.astype(np.float32)

    # Through-hole seeds: paper-coloured regions well inside the part.
    min_hole_px = min_hole_area_mm2 * s * s
    seeds = (eroded & (t < 0.5)).astype(np.uint8)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(seeds, connectivity=8)
    hole_regions = np.zeros_like(seeds)
    for label in range(1, n_labels):
        if stats[label, cv2.CC_STAT_AREA] >= min_hole_px:
            hole_regions[labels == label] = 1
    hole_zone = cv2.dilate(hole_regions, kernel).astype(bool) & dilated

    field = np.zeros(mask.shape, np.float32)
    field[eroded] = 1.0
    edge_band = dilated & ~eroded
    t_clipped = np.clip(t, 0.0, 1.0).astype(np.float32)
    field[edge_band] = t_clipped[edge_band]
    field[hole_zone] = t_clipped[hole_zone]

    padded = np.pad(field, 1)
    contours = [c[:, ::-1] - 1.0 for c in find_contours(padded, 0.5)]  # (row, col) → (x, y) px
    edge_sigma_mm = _edge_sigma_mm(t, contours, s) if refined else None
    contours = [c[:-1] if np.allclose(c[0], c[-1]) else c for c in contours if len(c) >= 4]
    if not contours:
        raise ReforgeError("PROFILE_NO_CONTOUR", "No closed part boundary was found.", "Retake the photo.")

    in_mm = [view.px_to_mm(c) for c in contours]
    areas = [abs(_signed_area(c)) for c in in_mm]
    outer_idx = int(np.argmax(areas))
    outer_pts = in_mm[outer_idx]
    if _signed_area(outer_pts) < 0:
        outer_pts = outer_pts[::-1]
    outer_raw = Contour(outer_pts, areas[outer_idx])
    # One pixel of smoothing along the edge removes tracing jitter, which would otherwise inflate the extents.
    smooth = smooth_closed(outer_pts, sigma=1.0 / s, spacing=0.5 / s)
    outer = Contour(smooth, abs(_signed_area(smooth)))
    outer_poly = outer_raw.polygon.buffer(0)

    others = [i for i in range(len(in_mm)) if i != outer_idx and areas[i] >= min_hole_area_mm2]
    big_outside = [i for i in others if not outer_poly.contains(Point(in_mm[i].mean(axis=0)))]
    if big_outside:
        warnings.append(ProfileWarning(
            "PROFILE_MULTIPLE_REGIONS", f"{len(big_outside)} other region(s) ignored; only the largest part is used."))

    paper_l_sigma = 1.4826 * float(np.median(np.abs(lab[background][:, 0] - paper[0]))) + 1.0
    holes: list[HoleCandidate] = []
    for i in (i for i in others if i not in big_outside):
        pts = in_mm[i]
        if _signed_area(pts) > 0:
            pts = pts[::-1]
        region = np.zeros(mask.shape, np.uint8)
        cv2.fillPoly(region, [np.round(view.mm_to_px(pts)).astype(np.int32)], 1)
        inside = region.astype(bool)
        if not inside.any():
            continue
        bright = image.max(axis=2)[inside]
        glare = float(((lab[inside][:, 0] > paper[0] + 3 * paper_l_sigma) | (bright >= 250)).mean()) > GLARE_FRACTION
        agrees = float((~mask[inside]).mean()) > 0.5
        holes.append(HoleCandidate(f"H{len(holes)}", Contour(pts, areas[i]), agrees, glare))

    coarse_edge = m8 - cv2.erode(m8, _disk(1))
    distance = cv2.distanceTransform((1 - coarse_edge).astype(np.uint8), cv2.DIST_L2, 5)
    outer_px = np.clip(np.round(view.mm_to_px(outer_raw.points_mm)).astype(int), 0,
                       np.array(mask.shape[::-1]) - 1)
    shift_px = distance[outer_px[:, 1], outer_px[:, 0]]
    if refined and float((shift_px >= band_px - 0.5).mean()) > BAND_SATURATION_FRACTION:
        warnings.append(ProfileWarning(
            "PROFILE_BAND_SATURATED",
            "Parts of the boundary hit the refinement limit; the segmentation mask may be misaligned there."))

    return RefinedProfile(
        outer=outer,
        holes=tuple(holes),
        band_mm=band_px / s,
        contrast_delta_e=contrast,
        coarse_shift_mean_mm=float(shift_px.mean()) / s,
        coarse_shift_max_mm=float(shift_px.max()) / s,
        refined=refined,
        warnings=tuple(warnings),
        outer_raw=outer_raw,
        edge_sigma_mm=edge_sigma_mm,
        colour_spread_delta_e=spread,
        trace_share=share,
    )


def _edge_sigma_mm(t: np.ndarray, contours: list[np.ndarray], px_per_mm: float) -> float | None:
    """Gaussian-equivalent edge spread from ∫ t(1 - t) dn = σ / √π across a blurred step.

    Summed over every pixel near the traced edges and divided by their length, so no edge-normal sampling is needed.
    t is left unclipped: on a noisy plateau E[t(1 - t)] = -σ_t², negligible, whereas clipping would add a positive
    bias. The band is widened until it spans ±3σ, so heavy blur isn't truncated.
    """
    lines = np.zeros(t.shape, np.uint8)
    length = 0.0
    for c in contours:
        cv2.polylines(lines, [np.round(c).astype(np.int32)], True, 1)
        length += float(np.linalg.norm(np.diff(np.vstack([c, c[:1]]), axis=0), axis=1).sum())
    if length <= 0:
        return None
    distance = cv2.distanceTransform(1 - lines, cv2.DIST_L2, 5)
    sigma_px, half_width = 0.0, max(3.0, px_per_mm)  # start at ±1 mm
    for _ in range(4):
        vals = t[distance <= half_width]
        sigma_px = float(np.sqrt(np.pi) * float((vals * (1 - vals)).sum()) / length)
        if 3 * sigma_px <= half_width:
            break
        half_width = 3.5 * sigma_px
    return sigma_px / px_per_mm
