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
mask filled them in. A candidate whose inside doesn't look like the mat paper around it and isn't round is doubted
rather than kept: a reflection on polished metal is as light as paper along the paper→part colour line, but it
isn't paper (synthetic composites, 2026-11-02: real holes ΔE p90 ≤ 3.1 and compactness ≥ 0.78; reflections and
engravings ΔE p90 ≥ 5.6 and mostly below 0.5).
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
HOLE_MAX_PAPER_DELTA_E = 5.0  # 90th percentile over the hole's core, lightness half-weighted (walls shade a hole)
HOLE_MIN_COMPACTNESS = 0.75  # 4πA/P²: 1 for a circle; a round hole that looks off-colour is still kept
HOLE_PAPER_RADIUS_MM = 15.0  # paper around the hole is the colour reference, so a lighting gradient doesn't count
BAND_SATURATION_FRACTION = 0.05
LOCAL_ABSTAIN_T = 0.4  # inside-vs-outside t step below which a band pixel keeps the segmenter's edge: with
# no local edge (white ceramic on white: ~0.05; metal on white: ~1.0) the contour would close through interior
# texture (stripes, print) instead of the true silhouette (bougie, 2026-11-04). Only sampled where the band spans
# >= 3 px: below that (soft thumbnails) the old behaviour stands, since the test itself is unresolved.


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
    paper_delta_e: float = 0.0  # 90th percentile ΔE of the hole's core from the paper around it
    compactness: float = 1.0
    background_word: str = "mat paper"  # ruler mode (no mat) says "background" instead

    @property
    def doubt(self) -> str | None:
        """Why this candidate may not be a through-hole, or None."""
        if self.glare_suspect:
            return (f"brighter than the {self.background_word}: possibly glare, not a hole, so it was left "
                    "out of the model")
        if self.paper_delta_e > HOLE_MAX_PAPER_DELTA_E and self.compactness < HOLE_MIN_COMPACTNESS:
            return (f"doesn't look like the {self.background_word} seen through the part "
                    f"(ΔE {self.paper_delta_e:.0f}) and isn't round: possibly a reflection or a mark, not a hole, "
                    "so it was left out of the model")
        return None


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
    on_mat: bool = True,
) -> RefinedProfile:
    image = view.image
    if image.ndim != 3:
        raise ReforgeError("IMAGE_INVALID", "Boundary refinement needs a colour (BGR) rectified view.")
    mask = np.asarray(coarse_mask).astype(bool)
    paper_word = "mat paper" if on_mat else "background"  # user-visible wording only; the math is identical
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
        raise ReforgeError("PROFILE_NO_BACKGROUND", f"Too little visible {paper_word} around the part.",
                           "Centre the part in the mat's free zone with space around it."
                           if on_mat else "Frame the whole part with space around it.")

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
            f"{'on the mat' if on_mat else 'on a plain background'}, so edges may be traced wrong. Painted, rusty, "
            "printed or multi-material parts aren't supported yet."))
    # Everything in the view that isn't mat paper, ignoring specks: the traced part should account for most of it.
    not_paper = (np.linalg.norm(lab - paper, axis=2) > NOT_PAPER_DELTA_E).astype(np.uint8)
    not_paper = cv2.morphologyEx(not_paper, cv2.MORPH_OPEN, _disk(max(1, int(round(0.5 * s)))))
    share = float(m8.sum()) / max(float(not_paper.sum()), 1.0)
    if share < MIN_PART_SHARE_OF_NOT_PAPER:
        warnings.append(ProfileWarning(
            "PROFILE_PARTIAL",
            f"The traced part covers only {share:.0%} of what isn't {paper_word}. Is the part one uniform colour, "
            f"alone {'on the mat' if on_mat else 'on a plain background'}? A multi-coloured or textured object is "
            "traced only in pieces."))
    refined = contrast >= MIN_CONTRAST_DELTA_E
    if refined:
        light = srgb_to_linear(image)
        paper_light = np.median(light[background], axis=0)
        direction = np.median(light[plastic], axis=0) - paper_light
        t = ((light - paper_light) @ direction) / float(direction @ direction)
    else:
        warnings.append(ProfileWarning(
            "PROFILE_LOW_CONTRAST",
            f"Part and {'mat' if on_mat else 'background'} differ by only ΔE {contrast:.1f}; the segmenter's "
            "boundary is kept unrefined. Use a contrasting background for light-coloured parts."))
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
    abstain = np.zeros(mask.shape, bool)
    if refined and band_px >= 3:  # needs a resolved band to sample across (see LOCAL_ABSTAIN_T)
        # Normals from the UNFILLED mask, so holes count as outside; outer boundary only (interior texture still
        # traces as hole candidates, honestly excluded as non-paper — abstaining inside would split real holes).
        signed = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5) - cv2.distanceTransform(
            (1 - mask.astype(np.uint8)).astype(np.uint8), cv2.DIST_L2, 5)
        gy, gx = np.gradient(signed.astype(np.float32))
        norm = np.hypot(gx, gy) + 1e-9
        yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]].astype(np.float32)
        nx, ny = gx / norm, gy / norm
        # Two reaches, min: a real edge step is visible at both scales, while interior texture (a printed
        # stripe 23 px inside the edge) spikes only the far reach — max would "refine" the edge onto the texture and
        # dive (live bougie finding, 2026-11-04: blue stripes read t~1, white ceramic t~0.34). Both reaches must agree.
        step = np.full(mask.shape, np.inf, np.float32)
        for reach in (float(band_px + 1), float(2 * band_px + 3)):
            xin = np.clip(xx + nx * reach, 0, mask.shape[1] - 1)
            yin = np.clip(yy + ny * reach, 0, mask.shape[1] - 1)
            xout = np.clip(xx - nx * reach, 0, mask.shape[1] - 1)
            yout = np.clip(yy - ny * reach, 0, mask.shape[0] - 1)
            tin = cv2.remap(t_clipped, xin, yin, cv2.INTER_LINEAR)
            tout = cv2.remap(t_clipped, xout, yout, cv2.INTER_LINEAR)
            step = np.minimum(step, np.abs(tin - tout))
        abstain = edge_band & (step < LOCAL_ABSTAIN_T)
        field[abstain] = m8[abstain].astype(np.float32)
        # A "hole" that leaks into an abstained outer span is no hole: it is part interior in disguise (white ceramic
        # reads t~0.34, paper-like, and touches the white background through the contrast-free edge). A real hole is
        # ringed by refined edge, so only components adjacent to the abstained OUTER band are filled; weak-arc and rim
        # holes survive (live bougie finding, 2026-11-04: the ceramic sea merged with the outline through the stripes).
        if hole_zone.any() and abstain.any():
            touch = cv2.dilate(hole_regions, _disk(1)).astype(bool) & abstain
            if touch.any():
                leak_labels = np.unique(
                    labels[cv2.dilate(touch.astype(np.uint8), _disk(2)).astype(bool) & (labels > 0)])
                for lab_id in leak_labels:
                    if not (labels == lab_id).any():
                        continue
                    fill = cv2.dilate((labels == lab_id).astype(np.uint8), kernel).astype(bool) & hole_zone
                    field[fill] = 1.0
                    hole_zone[fill] = False

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
    paper_bright = float(np.median(image.max(axis=2)[background]))
    yy, xx = np.nonzero(background)
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
        # Glare is relative to the paper: on a white studio backdrop (paper itself ≥250) a white hole interior is
        # expected, not a highlight — the absolute clause would doubt every true hole (live volant finding,
        # 2026-11-04: three real cutouts doubted as glare). It only applies on darker (mat) paper.
        glare = float(((lab[inside][:, 0] > paper[0] + 3 * paper_l_sigma)
                       | ((bright >= 250) & (paper_bright < 235))).mean()) > GLARE_FRACTION
        agrees = float((~mask[inside]).mean()) > 0.5
        core = cv2.erode(region, kernel).astype(bool)
        core = core if core.sum() >= 9 else inside
        cx, cy = view.mm_to_px(pts.mean(axis=0, keepdims=True))[0]
        near = (xx - cx) ** 2 + (yy - cy) ** 2 <= (HOLE_PAPER_RADIUS_MM * s) ** 2
        local = np.median(lab[yy[near], xx[near]], axis=0) if near.sum() >= MIN_BACKGROUND_PIXELS else paper
        diff = (lab[core] - local) * np.array([0.5, 1.0, 1.0], np.float32)
        paper_de = float(np.percentile(np.linalg.norm(diff, axis=1), 90))
        polygon = Polygon(pts)
        compact = float(4 * np.pi * polygon.area / polygon.length**2) if polygon.length > 0 else 0.0
        holes.append(HoleCandidate(f"H{len(holes)}", Contour(pts, areas[i]), agrees, glare, None, paper_de,
                                     compact, paper_word))

    coarse_edge = m8 - cv2.erode(m8, _disk(1))
    distance = cv2.distanceTransform((1 - coarse_edge).astype(np.uint8), cv2.DIST_L2, 5)
    outer_px = np.clip(np.round(view.mm_to_px(outer_raw.points_mm)).astype(int), 0,
                       np.array(mask.shape[::-1]) - 1)
    shift_px = distance[outer_px[:, 1], outer_px[:, 0]]
    kept = float(abstain[outer_px[:, 1], outer_px[:, 0]].mean()) if refined else 0.0
    if kept > 0.02:
        warnings.append(ProfileWarning(
            "PROFILE_PARTIALLY_UNREFINED",
            f"{kept:.0%} of the boundary kept the segmenter's edge: no local contrast there (a white region on a "
            f"white background), so sub-pixel refinement abstained instead of tracing interior texture. Those spans "
            f"are pixel-precise, not sub-pixel."))
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
    if sigma_px <= 0:
        # Texture swamps the edge: on a real stamped-metal part (2026-11-03) the plateau variance made the sum
        # negative (-0.37 mm). A spread can't be negative, so it's reported as unmeasured rather than as a number.
        return None
    return sigma_px / px_per_mm
