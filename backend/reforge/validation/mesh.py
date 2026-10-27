"""Mesh, topology, consistency and printability checks. A valid STL is not proof of a working part."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reforge.cad.build import BuiltPart
from reforge.spec.partspec import CircleHole, PartSpec

FDM_MIN_WALL_MM = 0.8
FDM_MIN_HOLE_MM = 1.0


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    severity: Literal["error", "warning"] = "error"


def validate_part(part: BuiltPart, spec: PartSpec) -> list[Check]:
    mesh = part.to_trimesh()
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str, severity: Literal["error", "warning"] = "error") -> None:
        checks.append(Check(name, bool(ok), detail, severity))

    add("non_empty", len(mesh.faces) > 0, f"{len(mesh.faces)} triangles")
    add("watertight", mesh.is_watertight, "every edge is shared by exactly two triangles")
    add("consistent_winding", mesh.is_winding_consistent, "triangle normals are consistently oriented")
    add("positive_volume", mesh.volume > 0, f"volume {mesh.volume:.3f} mm³ (normals point outward)")
    bodies = int(mesh.body_count)
    add("single_body", bodies == 1, f"{bodies} connected bodies")
    genus = (2 - int(mesh.euler_number)) // 2
    add("genus_matches_holes", genus == len(spec.holes),
        f"surface genus {genus} vs {len(spec.holes)} through-hole(s) in the spec")
    expected = part.profile_area_mm2 * spec.thickness.value
    rel = abs(mesh.volume - expected) / expected if expected else float("inf")
    add("volume_matches_profile", rel < 1e-6, f"mesh {mesh.volume:.4f} vs profile × thickness {expected:.4f} mm³")
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds
    poly = spec.outline.polygon.buffer(spec.fit.outline_offset_mm, join_style="mitre")
    px0, py0, px1, py1 = poly.bounds
    bbox_err = max(abs(x0 - px0), abs(y0 - py0), abs(x1 - px1), abs(y1 - py1), abs(z0), abs(z1 - spec.thickness.value))
    add("bbox_matches_spec", bbox_err < 0.01, f"max bounding-box deviation {bbox_err:.5f} mm")
    areas = mesh.area_faces
    add("no_degenerate_triangles", float(areas.min()) > 1e-10, f"smallest triangle {float(areas.min()):.2e} mm²")

    solid_2d = poly
    for hole in spec.holes:
        if isinstance(hole, CircleHole):
            d = hole.diameter.value + spec.fit.hole_offset_mm
            add(f"{hole.id}_printable_diameter", d >= FDM_MIN_HOLE_MM,
                f"{hole.id} Ø{d:.2f} mm (FDM guideline ≥ {FDM_MIN_HOLE_MM} mm)", "warning")
        solid_2d = solid_2d.difference(hole.disc(spec.fit.hole_offset_mm))
    # Morphological opening with a disc of the minimum wall's diameter removes anything thinner than the
    # wall. Sharp corners lose about 0.03 mm² each, hence the 1 mm² allowance.
    half = FDM_MIN_WALL_MM / 2
    thin = solid_2d.area - solid_2d.buffer(-half).buffer(half).area
    add("min_wall_thickness", thin < 1.0, f"{thin:.2f} mm² of the profile is thinner than {FDM_MIN_WALL_MM} mm",
        "warning")
    return checks


def summarize(checks: list[Check]) -> dict[str, object]:
    errors = [c.name for c in checks if not c.passed and c.severity == "error"]
    warnings = [c.name for c in checks if not c.passed and c.severity == "warning"]
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "checks": [c.__dict__ for c in checks]}
