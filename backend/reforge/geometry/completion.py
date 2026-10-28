"""Mirror completion of a broken footprint, with the provenance of every part of the completed outline.

Only the mirror image's extra material that touches an accepted fracture is added. Elsewhere, a difference between a
side and its mirror is real asymmetry (a designed notch, say): it's reported, not filled. A mirrored hole is added
only if it lands entirely inside added material, with no observed hole already there.

Provenance, point by point along the completed outline: on the photographed outline → OBSERVED; on the mirrored
outline inside added material → INFERRED (mirror of the named segments about the named axis); a photographed
fracture edge left on the outline, or a junction between the two → UNCERTAIN.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from reforge.geometry.contour import resample_closed
from reforge.geometry.segments import SegmentedOutline
from reforge.geometry.symmetry import TAU_MM, MirrorAxis

MIN_COMPONENT_MM2 = 0.5
OPENING_MM = 0.1  # drops slivers between a side and its slightly imperfect mirror
CLOSING_MM = 0.05  # seals hairline gaps along the fracture after the union
RUN_SPACING_MM = 0.25
ON_EDGE_MM = 0.05


@dataclass(frozen=True)
class Region:
    polygon: Polygon
    area_mm2: float
    filled: bool
    reason: str


@dataclass(frozen=True)
class InferredHole:
    source_hole_id: str
    center: tuple[float, float]
    radius: float


@dataclass(frozen=True)
class HoleCheck:
    hole_id: str
    partner_id: str
    center_distance_mm: float  # between the mirrored centre and the partner's centre
    diameter_difference_mm: float


@dataclass(frozen=True)
class Run:
    start: int
    end: int  # inclusive
    status: str  # "OBSERVED" | "INFERRED" | "UNCERTAIN"
    source: str


@dataclass(frozen=True)
class Completion:
    axis: MirrorAxis
    points: np.ndarray  # completed outline, (n, 2), counter-clockwise
    runs: tuple[Run, ...]
    regions: tuple[Region, ...]
    inferred_holes: tuple[InferredHole, ...]
    hole_checks: tuple[HoleCheck, ...]
    asymmetric_holes: tuple[str, ...]  # holes whose mirror lands on solid, hole-free material

    @property
    def added_area_mm2(self) -> float:
        return float(sum(r.area_mm2 for r in self.regions if r.filled))

    def inferred_uncertainty_mm(self) -> float:
        """2σ for mirrored geometry, before adding the source edge's own uncertainty (PLAN §6.6): the mirror's
        inlier RMS, the axis angle error times the lever arm to the added material, and twice the axis offset
        error (a reflection doubles it)."""
        a = self.axis
        lever = max((float(np.abs((np.asarray(r.polygon.exterior.coords) - a.point) @ a.normal).max())
                     for r in self.regions if r.filled), default=0.0)
        angle = np.radians(a.angle_sigma_deg or 0.0) * lever
        return float(2 * np.sqrt(a.inlier_rms_mm**2 + angle**2 + (2 * (a.offset_sigma_mm or 0.0))**2))


def _components(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    return [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]


def _segment_names(ids: list[str]) -> str:
    unique = list(dict.fromkeys(ids))
    if len(unique) <= 2:
        return "/".join(unique)
    return f"{unique[0]}…{unique[-1]}"


def complete_by_mirror(outline_mm: np.ndarray, holes: list[tuple[str, tuple[float, float], float]],
                       axis: MirrorAxis, fracture_ids: list[str], segmented: SegmentedOutline) -> Completion:
    """``outline_mm`` is the footprint that ``segmented`` was built from; ``fracture_ids`` are accepted segments."""
    observed = Polygon(outline_mm).buffer(0)
    mirror = Polygon(axis.reflect(outline_mm)).buffer(0)
    spans = [segmented.span(segmented.by_id(sid)) for sid in fracture_ids]
    fracture = MultiLineString([LineString(sp) for sp in spans if len(sp) >= 2]) if spans else None
    extra = mirror.difference(observed).buffer(-OPENING_MM, join_style="mitre").buffer(OPENING_MM, join_style="mitre")
    fracture_ids = sorted(fracture_ids, key=lambda sid: int(sid[1:]))
    regions = []
    for comp in sorted(_components(extra), key=lambda g: -g.area):
        if comp.area < MIN_COMPONENT_MM2:
            continue
        touches = fracture is not None and comp.distance(fracture) <= TAU_MM
        reason = (f"mirror of the intact side, next to the fracture ({_segment_names(fracture_ids)})" if touches
                  else "real asymmetry (not next to a fracture): reported, not filled")
        regions.append(Region(comp, float(comp.area), touches, reason))

    filled = [r.polygon for r in regions if r.filled]
    merged = unary_union([observed, *filled]).buffer(CLOSING_MM, join_style="mitre").buffer(-CLOSING_MM,
                                                                                           join_style="mitre")
    outline = max(_components(merged), key=lambda g: g.area)
    outline = orient(Polygon(outline.exterior), 1.0)
    pts = resample_closed(np.asarray(outline.exterior.coords)[:-1], RUN_SPACING_MM)

    # Provenance of every point.
    on_photo = shapely.distance(observed.exterior, shapely.points(pts)) <= ON_EDGE_MM
    on_mirror = shapely.distance(mirror.exterior, shapely.points(pts)) <= ON_EDGE_MM
    on_fracture = (shapely.distance(fracture, shapely.points(pts)) <= ON_EDGE_MM if fracture is not None
                   else np.zeros(len(pts), dtype=bool))
    in_added = np.zeros(len(pts), dtype=bool)
    for poly in filled:
        in_added |= shapely.distance(poly, shapely.points(pts)) <= ON_EDGE_MM
    labels = segmented.labels()
    seg_tree = cKDTree(segmented.points)
    source_seg = labels[seg_tree.query(axis.reflect(pts))[1]]

    keys: list[tuple[str, str]] = []
    for i in range(len(pts)):
        if on_photo[i] and not on_fracture[i]:
            keys.append(("OBSERVED", "calibrated photo, refined boundary"))
        elif on_photo[i]:
            keys.append(("UNCERTAIN", "fracture edge left on the outline (not covered by the mirror)"))
        elif on_mirror[i] and in_added[i]:
            keys.append(("INFERRED", segmented.segments[source_seg[i]].seg_id))
        else:
            keys.append(("UNCERTAIN", "junction between photographed and mirrored edges"))
    runs = _runs(keys, axis)

    hole_checks, inferred, asymmetric = [], [], []
    for hid, centre, radius in holes:
        image = axis.reflect(np.asarray(centre))[0]
        partner = min(holes, key=lambda h: float(np.hypot(h[1][0] - image[0], h[1][1] - image[1])))
        distance = float(np.hypot(partner[1][0] - image[0], partner[1][1] - image[1]))
        if distance <= max(TAU_MM, 0.25 * radius):
            hole_checks.append(HoleCheck(hid, partner[0], distance, 2 * abs(partner[2] - radius)))
        elif any(poly.contains(Point(image).buffer(radius)) for poly in filled):
            inferred.append(InferredHole(hid, (float(image[0]), float(image[1])), float(radius)))
        elif observed.contains(Point(image)):
            asymmetric.append(hid)
    return Completion(axis, pts, runs, tuple(regions), tuple(inferred), tuple(hole_checks), tuple(asymmetric))


def _runs(keys: list[tuple[str, str]], axis: MirrorAxis) -> tuple[Run, ...]:
    """Consecutive points with the same status form a run; INFERRED runs name their mirrored source segments."""
    runs: list[Run] = []
    start = 0
    for i in range(1, len(keys) + 1):
        if i < len(keys) and keys[i][0] == keys[start][0] and (keys[i][0] == "INFERRED" or keys[i] == keys[start]):
            continue
        status = keys[start][0]
        if status == "INFERRED":
            source = (f"mirror of {_segment_names([k[1] for k in keys[start:i]])} about {axis.axis_id} "
                      f"(support {axis.support:.0%})")
        else:
            source = keys[start][1]
        runs.append(Run(start, i - 1, status, source))
        start = i
    return tuple(runs)
