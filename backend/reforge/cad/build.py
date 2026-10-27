"""PartSpec → solid, with manifold3d (in-process, guaranteed-manifold booleans). No code is generated or run."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, FillRule, JoinType, Manifold

from reforge.spec.partspec import CircleHole, PartSpec

CHORD_ERROR_MM = 0.005


def circle_segments(radius_mm: float, chord_error_mm: float = CHORD_ERROR_MM) -> int:
    """Polygon segments that keep the maximum chord deviation below ``chord_error_mm``."""
    if radius_mm <= chord_error_mm:
        return 32
    n = math.ceil(math.pi / math.acos(1.0 - chord_error_mm / radius_mm))
    return int(min(max(n, 32), 720))


@dataclass(frozen=True)
class BuiltPart:
    solid: Manifold
    profile_area_mm2: float  # area of the cross-section actually extruded

    @property
    def vertices(self) -> np.ndarray:
        return np.asarray(self.solid.to_mesh().vert_properties)[:, :3].astype(np.float64)

    @property
    def faces(self) -> np.ndarray:
        return np.asarray(self.solid.to_mesh().tri_verts).astype(np.int64)

    def to_trimesh(self) -> trimesh.Trimesh:
        mesh = self.solid.to_mesh()
        return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=False)


def profile_cross_section(spec: PartSpec) -> CrossSection:
    outline = CrossSection([np.asarray(spec.outline.points, dtype=np.float64)], FillRule.EvenOdd)
    if spec.fit.outline_offset_mm:
        outline = outline.offset(spec.fit.outline_offset_mm, JoinType.Miter, 4.0)
    for hole in spec.holes:
        if isinstance(hole, CircleHole):
            radius = (hole.diameter.value + spec.fit.hole_offset_mm) / 2
            disc = CrossSection.circle(radius, circle_segments(radius)).translate(
                (hole.center_x.value, hole.center_y.value))
        else:
            disc = CrossSection([np.asarray(hole.points, dtype=np.float64)], FillRule.EvenOdd)
            if spec.fit.hole_offset_mm:
                disc = disc.offset(spec.fit.hole_offset_mm / 2, JoinType.Miter, 4.0)
        outline = outline - disc
    return outline


def build_part(spec: PartSpec) -> BuiltPart:
    profile = profile_cross_section(spec)
    return BuiltPart(Manifold.extrude(profile, spec.thickness.value), float(profile.area()))


def write_stl(part: BuiltPart, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    part.to_trimesh().export(path, file_type="stl")
    return path
