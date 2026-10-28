"""Height (parallax) correction for a flat part of known thickness h.

Through the mat-plane homography, the part's horizontal slice at height z appears scaled by H / (H - z) about the
nadir N, where H is the camera height. The photo shows the union of the slices for scales s ∈ [1, m], with
m = H / (H - h): walls facing away from the nadir show the enlarged top edge, walls facing it the bottom edge.
Simulated on an 80 x 28 x 3 mm bracket (2026-10-27): length +0.61 mm from 40 cm, +1.09 mm from 25 cm.

Inverse, along each ray from N: a photographed interval [A, B] of the part comes from the footprint interval
[A, B/m]. Equivalently, a point x belongs to the footprint iff the whole radial segment from x to its top-face image
N + m(x - N) lies inside the photographed outline O, so the footprint is the intersection of O scaled by every factor
in [1/m, 1]. In closed form: (O ∩ scale(O, 1/m)) minus the trapezoids that O's boundary edges sweep between scales
1/m and 1. The two-copy formula alone (PLAN v0.4) is exact only when every ray crosses the outline once; at a
U-shaped notch it left 0.55 mm spurious corners (unit test, 2026-10-27).

- Round through-holes: paper shows only where the line of sight clears both the bottom opening D(c, r) and the top
  opening, which appears as D(N + m(c - N), m·r). Fitting that intersection model recovers c and r; a plain circle
  fit sees a lens, up to 0.67 mm too small in the same simulation.
- Other holes: the dual formula, V ∪ scale(V, 1/m) plus the sweep of V's boundary, exact for holes that every ray
  from N crosses once (any convex hole).

Single-view limit: along a ray, a gap shorter than (m - 1)·distance is hidden behind the top face, so it can't be
seen at all. Near a concave corner the rays that clip the corner see such gaps; the corrected footprint keeps that
zone as material (it's the largest footprint consistent with the photo). For a U-shaped notch 90 mm from the nadir,
seen from 25 cm, the zone was a 0.94 x 0.55 mm triangle, as the geometry predicts. ``occlusion_bound_mm`` bounds
its size; a second viewpoint resolves it. Not modelled: draft angles and chamfers.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import least_squares
from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from reforge.capture.pose import CameraPose
from reforge.errors import ReforgeError
from reforge.geometry.circle import CircleFit, fit_circle
from reforge.vision.refine import Contour, HoleCandidate, RefinedProfile

CIRCLE_POINTS = 256


@dataclass(frozen=True)
class HeightCorrection:
    profile: RefinedProfile  # the footprint: what to build
    magnification: float  # m = H / (H - h), the top face's apparent scale
    max_shift_mm: float  # Hausdorff distance between the photographed outline and the footprint
    u_persp_mm: float  # 2σ uncertainty of the correction at the part, from the pose uncertainty
    occlusion_bound_mm: float  # largest gap the part's own height can hide from this viewpoint: (m - 1)·distance


def _largest(shape) -> Polygon:
    if shape.is_empty:
        raise ReforgeError("HEIGHT_CORRECTION_FAILED", "The height correction removed the whole outline.",
                           "Check the thickness value.")
    return shape if shape.geom_type == "Polygon" else max(shape.geoms, key=lambda g: g.area)


def _sweep(region: Polygon, nadir: tuple[float, float], m: float):
    """The union of the trapezoids that the region's boundary edges sweep under scales from 1/m to 1 about N."""
    n = np.asarray(nadir, dtype=np.float64)
    quads = []
    for ring in (region.exterior, *region.interiors):
        pts = np.asarray(ring.coords)
        inner = n + (pts - n) / m
        for i in range(len(pts) - 1):
            quad = Polygon([pts[i], pts[i + 1], inner[i + 1], inner[i]]).buffer(0)
            if not quad.is_empty:
                quads.append(quad)
    return unary_union(quads)


def correct_outline(points_mm: np.ndarray, nadir: tuple[float, float], m: float) -> np.ndarray:
    seen = Polygon(points_mm).buffer(0)
    both = seen.intersection(affinity.scale(seen, 1 / m, 1 / m, origin=(*nadir, 0.0)))
    footprint = _largest(both.difference(_sweep(seen, nadir, m)))
    return np.asarray(orient(footprint, 1.0).exterior.coords)[:-1]


def fit_hole_through_thickness(points_mm: np.ndarray, nadir: tuple[float, float], m: float) -> CircleFit:
    """Bottom-opening circle whose two-disc visibility region best matches the observed hole boundary."""
    p = np.asarray(points_mm, dtype=np.float64)
    n = np.asarray(nadir, dtype=np.float64)
    start = fit_circle(p)

    def residual(x: np.ndarray) -> np.ndarray:
        c, r = x[:2], x[2]
        return np.maximum(np.linalg.norm(p - c, axis=1) - r, np.linalg.norm(p - (n + m * (c - n)), axis=1) - m * r)

    # The observed lens sits between the two openings: start halfway back towards the bottom one.
    c0 = np.asarray(start.center) - (m - 1) / 2 * (np.asarray(start.center) - n)
    sol = least_squares(residual, np.array([*c0, start.radius]), method="trf", x_scale=1.0)
    res = residual(sol.x)
    return CircleFit(center=(float(sol.x[0]), float(sol.x[1])), radius=float(sol.x[2]),
                     rms=float(np.sqrt(np.mean(res**2))), max_deviation=float(np.abs(res).max()), n_points=len(p))


def _circle_contour(fit: CircleFit) -> Contour:
    a = np.linspace(0, 2 * np.pi, CIRCLE_POINTS, endpoint=False)
    pts = np.column_stack([fit.center[0] + fit.radius * np.cos(a), fit.center[1] - fit.radius * np.sin(a)])
    return Contour(pts, float(np.pi * fit.radius**2))  # negative signed area, like refined hole contours


def correct_height(profile: RefinedProfile, pose: CameraPose, thickness_mm: float, *,
                   round_max_deviation_mm: float) -> HeightCorrection:
    """The part's footprint from its photographed silhouette.

    Round holes get a parallax-aware circle fit, attached to the candidate; ``round_max_deviation_mm`` decides
    which holes count as round, as it does for uncorrected holes.
    """
    big_h = pose.height_mm
    if not 0 < thickness_mm < big_h:
        raise ReforgeError("HEIGHT_CORRECTION_FAILED", f"Thickness {thickness_mm} mm vs camera height {big_h:.0f} mm.")
    m = big_h / (big_h - thickness_mm)
    nadir = pose.nadir_mm
    outer_pts = correct_outline(profile.outer.points_mm, nadir, m)
    outer = Contour(outer_pts, float(Polygon(outer_pts).area))

    holes: list[HoleCandidate] = []
    for cand in profile.holes:
        fit = fit_hole_through_thickness(cand.contour.points_mm, nadir, m)
        if fit.max_deviation <= round_max_deviation_mm:
            holes.append(replace(cand, contour=_circle_contour(fit), fit=fit))
            continue
        seen = Polygon(cand.contour.points_mm).buffer(0)
        hole = _largest(unary_union([seen, affinity.scale(seen, 1 / m, 1 / m, origin=(*nadir, 0.0)),
                                     _sweep(seen, nadir, m)]))
        pts = np.asarray(orient(hole, -1.0).exterior.coords)[:-1]
        holes.append(replace(cand, contour=Contour(pts, float(hole.area)), fit=None))

    max_shift = float(Polygon(profile.outer.points_mm).hausdorff_distance(Polygon(outer_pts)))
    # 2σ of the displacement at the outline point farthest from the nadir: camera-height and nadir uncertainties,
    # first order.
    radial = np.linalg.norm(profile.outer.points_mm - np.asarray(nadir), axis=1)
    dm = thickness_mm * pose.height_sigma_mm / (big_h - thickness_mm) ** 2
    u_persp = 2 * float(np.hypot(radial.max() * dm, (m - 1) * pose.nadir_sigma_mm))
    corrected = replace(profile, outer=outer, holes=tuple(holes))
    return HeightCorrection(profile=corrected, magnification=float(m), max_shift_mm=max_shift, u_persp_mm=u_persp,
                            occlusion_bound_mm=float((m - 1) * radial.max()))
