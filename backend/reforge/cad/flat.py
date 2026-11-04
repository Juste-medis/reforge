"""Flat-pattern exports of a PartSpec, for cutting rather than printing: DXF (laser, waterjet, CNC router) and SVG at
1:1 in millimetres (cutting plotters, laser software). A gasket or a shim is cut from sheet, not printed.

Both carry the outline and the holes with the PartSpec's fit compensation applied (``outline_offset_mm`` grows or
shrinks the outline, ``hole_offset_mm`` is added to every hole's diameter), exactly as the solid is built. Only numbers
formatted here and sanitised comment text reach the files. Coordinates are the model frame (x right, y up), mm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from shapely.geometry import Polygon

from reforge.spec.partspec import CircleHole, PartSpec

_SAFE = re.compile(r"[^A-Za-z0-9 .,:;()±%/+\-_=]")


@dataclass(frozen=True)
class FlatPattern:
    outline: np.ndarray  # (n, 2), counter-clockwise, compensated
    circles: list[tuple[str, float, float, float]]  # (id, x, y, diameter), compensated
    shapes: list[tuple[str, np.ndarray]]  # non-round holes: (id, ring), compensated


def flat_pattern(spec: PartSpec) -> FlatPattern:
    outline = spec.outline.polygon
    if spec.fit.outline_offset_mm:
        outline = outline.buffer(spec.fit.outline_offset_mm, join_style="mitre")
    ring = np.asarray(outline.exterior.coords)[:-1]
    circles, shapes = [], []
    for hole in spec.holes:
        if isinstance(hole, CircleHole):
            circles.append((hole.id, hole.center_x.value, hole.center_y.value,
                            hole.diameter.value + spec.fit.hole_offset_mm))
        else:
            region = Polygon(hole.points)
            if spec.fit.hole_offset_mm:
                region = region.buffer(spec.fit.hole_offset_mm / 2, join_style="mitre")
            shapes.append((hole.id, np.asarray(region.exterior.coords)[:-1]))
    return FlatPattern(ring, circles, shapes)


def _comment(text: str) -> str:
    return _SAFE.sub("", text.replace("\n", " "))[:200]


def _header(spec: PartSpec, job_id: str | None) -> list[str]:
    return [f"RE-FORGE AI flat pattern, PartSpec v1{', job ' + _comment(job_id) if job_id else ''}, generated "
            f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            "Units: millimetres. A reconstruction, not a verified replacement part. Not for safety-critical use.",
            f"Fit compensation: holes {spec.fit.hole_offset_mm:+.3f} mm on diameter, outline "
            f"{spec.fit.outline_offset_mm:+.3f} mm.",
            f"Thickness to cut from: {spec.thickness.value:.3f} mm ({spec.thickness.status.value})."]


def emit_dxf(spec: PartSpec, job_id: str | None = None) -> str:
    """AutoCAD R12 (AC1009) ASCII: closed POLYLINEs and CIRCLEs on layers OUTLINE and HOLES, the most widely read
    DXF dialect in cutting software."""
    pattern = flat_pattern(spec)
    out: list[str] = []

    def group(code: int, value: str | float) -> None:
        out.extend([str(code), f"{value:.6f}" if isinstance(value, float) else str(value)])

    for line in _header(spec, job_id):
        group(999, line)
    group(0, "SECTION")
    group(2, "HEADER")
    group(9, "$ACADVER")
    group(1, "AC1009")
    group(9, "$INSUNITS")
    group(70, 4)  # millimetres
    group(0, "ENDSEC")
    group(0, "SECTION")
    group(2, "TABLES")
    group(0, "TABLE")
    group(2, "LAYER")
    group(70, 2)
    for name, colour in (("OUTLINE", 7), ("HOLES", 1)):
        group(0, "LAYER")
        group(2, name)
        group(70, 0)
        group(62, colour)
        group(6, "CONTINUOUS")
    group(0, "ENDTAB")
    group(0, "ENDSEC")
    group(0, "SECTION")
    group(2, "ENTITIES")

    def polyline(points: np.ndarray, layer: str) -> None:
        group(0, "POLYLINE")
        group(8, layer)
        group(66, 1)
        group(70, 1)  # closed
        for x, y in points:
            group(0, "VERTEX")
            group(8, layer)
            group(10, float(x))
            group(20, float(y))
            group(30, 0.0)
        group(0, "SEQEND")
        group(8, layer)

    polyline(pattern.outline, "OUTLINE")
    for _, x, y, d in pattern.circles:
        group(0, "CIRCLE")
        group(8, "HOLES")
        group(10, float(x))
        group(20, float(y))
        group(30, 0.0)
        group(40, float(d / 2))
    for _, ring in pattern.shapes:
        polyline(ring, "HOLES")
    group(0, "ENDSEC")
    group(0, "EOF")
    return "\n".join(out) + "\n"


def emit_svg(spec: PartSpec, job_id: str | None = None, margin_mm: float = 2.0) -> str:
    """SVG at true size: width and height in mm, a viewBox in mm, y flipped so the part isn't mirrored. Cut lines are
    0.1 mm hairlines (red for holes, black for the outline), the convention most cutters read."""
    pattern = flat_pattern(spec)
    pts = np.vstack([pattern.outline] + [r for _, r in pattern.shapes]
                    + [np.array([[x - d / 2, y - d / 2], [x + d / 2, y + d / 2]]) for _, x, y, d in pattern.circles])
    x0, y0 = pts.min(axis=0) - margin_mm
    x1, y1 = pts.max(axis=0) + margin_mm
    w, h = x1 - x0, y1 - y0

    def path(ring: np.ndarray) -> str:
        return "M " + " L ".join(f"{x - x0:.4f} {y1 - y:.4f}" for x, y in ring) + " Z"

    comments = "".join(f"<!-- {line} -->\n" for line in _header(spec, job_id))
    body = [f'<path d="{path(pattern.outline)}" fill="none" stroke="#000000" stroke-width="0.1"/>']
    body += [f'<circle cx="{x - x0:.4f}" cy="{y1 - y:.4f}" r="{d / 2:.4f}" fill="none" stroke="#ff0000" '
             f'stroke-width="0.1"/>' for _, x, y, d in pattern.circles]
    body += [f'<path d="{path(ring)}" fill="none" stroke="#ff0000" stroke-width="0.1"/>' for _, ring in pattern.shapes]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + comments
            + f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.4f}mm" height="{h:.4f}mm" '
              f'viewBox="0 0 {w:.4f} {h:.4f}">\n  ' + "\n  ".join(body) + "\n</svg>\n")
