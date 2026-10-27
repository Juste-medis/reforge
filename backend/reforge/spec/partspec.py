"""PartSpec: the typed, validated geometric description that everything downstream compiles from.

AI components may *propose* edits to a PartSpec, but only through this schema plus semantic validation.
No model output is ever executed.

Coordinates: the **model frame**. Millimetres, x right, y up, z up toward the camera. The outline is the
part as seen from above. (The mat frame has y pointing down, which would mirror the part, so convert
with ``mat_to_model``.)
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from shapely.geometry import Point, Polygon

from reforge.errors import ReforgeError

MAX_POINTS = 2000
MAX_COORD_MM = 500.0
MIN_WALL_MM = 0.4


class Status(StrEnum):
    MEASURED = "MEASURED"  # caliper reading or user-confirmed calibration
    OBSERVED = "OBSERVED"  # computed from calibrated image evidence
    INFERRED = "INFERRED"  # derived from a stated rule (symmetry, design intent) with measured support
    UNCERTAIN = "UNCERTAIN"  # no adequate evidence; blocks export until resolved


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(_Strict):
    kind: str = Field(min_length=1, max_length=40)
    detail: str = Field(max_length=300)


class Param(_Strict):
    value: float
    status: Status
    uncertainty_mm: float | None = Field(default=None, ge=0)  # 2σ; None until the Confidence Engine sets it
    evidence: tuple[Evidence, ...] = ()

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be finite")
        return v


class OutlineRun(_Strict):
    start: int = Field(ge=0)  # inclusive point indices
    end: int = Field(ge=0)
    status: Status
    source: str = Field(max_length=120)


class Outline(_Strict):
    points: tuple[tuple[float, float], ...] = Field(min_length=3, max_length=MAX_POINTS)
    runs: tuple[OutlineRun, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Outline:
        for x, y in self.points:
            if not (math.isfinite(x) and math.isfinite(y)) or max(abs(x), abs(y)) > MAX_COORD_MM:
                raise ValueError(f"outline coordinates must be finite and within ±{MAX_COORD_MM} mm")
        expected = 0
        for run in self.runs:
            if run.start != expected or run.end < run.start:
                raise ValueError("outline runs must cover every point once, in order")
            expected = run.end + 1
        if expected != len(self.points):
            raise ValueError("outline runs must cover every point once, in order")
        return self

    @property
    def polygon(self) -> Polygon:
        return Polygon(self.points)


class CircleHole(_Strict):
    kind: Literal["circle"] = "circle"
    id: str = Field(pattern=r"^H\d{1,3}$")
    center_x: Param
    center_y: Param
    diameter: Param

    def disc(self, hole_offset_mm: float = 0.0) -> Polygon:
        return Point(self.center_x.value, self.center_y.value).buffer(
            (self.diameter.value + hole_offset_mm) / 2, quad_segs=64)


class PolygonHole(_Strict):
    """A non-circular through-hole (slot, D-hole), traced from the photo."""

    kind: Literal["polygon"] = "polygon"
    id: str = Field(pattern=r"^H\d{1,3}$")
    points: tuple[tuple[float, float], ...] = Field(min_length=3, max_length=MAX_POINTS)
    status: Status
    source: str = Field(max_length=120)

    def disc(self, hole_offset_mm: float = 0.0) -> Polygon:
        """The hole region, grown by half the compensation (it acts on width, like a diameter)."""
        return Polygon(self.points).buffer(hole_offset_mm / 2, join_style="mitre")


Hole = Annotated[CircleHole | PolygonHole, Field(discriminator="kind")]


class FitCompensation(_Strict):
    """Printer compensation. ``hole_offset_mm`` is added to every hole diameter;
    ``outline_offset_mm`` grows (positive) or shrinks the outline."""

    hole_offset_mm: float = Field(default=0.0, ge=-1.0, le=1.0)
    outline_offset_mm: float = Field(default=0.0, ge=-1.0, le=1.0)


class PartSpec(_Strict):
    schema_version: Literal[1] = 1
    units: Literal["mm"] = "mm"
    family: Literal["extruded_profile"] = "extruded_profile"
    outline: Outline
    holes: tuple[Hole, ...] = ()
    thickness: Param
    fit: FitCompensation = FitCompensation()

    @model_validator(mode="after")
    def _semantics(self) -> PartSpec:
        if not 0.4 <= self.thickness.value <= 200.0:
            raise ValueError("thickness must be between 0.4 and 200 mm")
        outline = self.outline.polygon
        if not outline.is_valid:
            raise ValueError("outline must be a simple, non-self-intersecting polygon")
        if outline.area < 1.0:
            raise ValueError("outline area must be at least 1 mm²")
        body = outline.buffer(self.fit.outline_offset_mm, join_style="mitre")
        ids = [h.id for h in self.holes]
        if len(set(ids)) != len(ids):
            raise ValueError("hole ids must be unique")
        discs = []
        for hole in self.holes:
            if isinstance(hole, CircleHole):
                d = hole.diameter.value + self.fit.hole_offset_mm
                if not 0.5 <= d <= 200.0:
                    raise ValueError(f"{hole.id}: compensated diameter {d:.3f} mm is outside 0.5–200 mm")
            else:
                for x, y in hole.points:
                    if not (math.isfinite(x) and math.isfinite(y)) or max(abs(x), abs(y)) > MAX_COORD_MM:
                        raise ValueError(f"{hole.id}: coordinates must be finite and within ±{MAX_COORD_MM} mm")
                if not Polygon(hole.points).is_valid or Polygon(hole.points).area < 0.2:
                    raise ValueError(f"{hole.id}: must be a simple polygon of at least 0.2 mm²")
            disc = hole.disc(self.fit.hole_offset_mm)
            if not body.buffer(-MIN_WALL_MM).contains(disc):
                raise ValueError(f"{hole.id}: must lie inside the outline with at least {MIN_WALL_MM} mm of wall")
            for other_id, other in discs:
                if disc.distance(other) < MIN_WALL_MM:
                    raise ValueError(f"{hole.id} and {other_id} must be at least {MIN_WALL_MM} mm apart")
            discs.append((hole.id, disc))
        return self

    def unresolved(self) -> list[str]:
        """Everything still UNCERTAIN. Export is blocked until this list is empty or explicitly accepted."""
        items = [f"outline[{r.start}:{r.end}]" for r in self.outline.runs if r.status is Status.UNCERTAIN]
        if self.thickness.status is Status.UNCERTAIN:
            items.append("thickness")
        for h in self.holes:
            if isinstance(h, PolygonHole):
                if h.status is Status.UNCERTAIN:
                    items.append(h.id)
                continue
            for name in ("center_x", "center_y", "diameter"):
                if getattr(h, name).status is Status.UNCERTAIN:
                    items.append(f"{h.id}.{name}")
        return items


def parse_spec(data: dict) -> PartSpec:
    """Validate untrusted input (UI edits, AI proposals) into a PartSpec, or raise a typed error."""
    try:
        return PartSpec.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'spec'}: {e['msg']}" for e in exc.errors())
        raise ReforgeError("SPEC_INVALID", problems[:1000], "Correct the highlighted values.") from exc


def mat_to_model(points_mm: np.ndarray, origin_mm: tuple[float, float]) -> np.ndarray:
    """Mat frame (y down) → model frame (y up), relative to ``origin_mm``.

    With z pointing up from the table, the mat frame is left-handed. Negating y gives the right-handed
    model frame, so the extruded solid has the real part's handedness, not its mirror image.
    """
    pts = np.asarray(points_mm, dtype=np.float64).reshape(-1, 2) - np.asarray(origin_mm)
    return np.column_stack([pts[:, 0], -pts[:, 1]])
