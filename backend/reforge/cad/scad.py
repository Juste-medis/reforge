"""Deterministic OpenSCAD export of a PartSpec: an editable, parametric file with provenance comments.

Only numbers (formatted here) and sanitised comment text ever reach the output.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from reforge.cad.build import circle_segments
from reforge.spec.partspec import CircleHole, Param, PartSpec

_SAFE_COMMENT = re.compile(r"[^A-Za-z0-9 .,:;()±%/+\-_=]")


def _comment(text: str) -> str:
    return _SAFE_COMMENT.sub("", text.replace("\n", " "))[:160]


def _num(value: float) -> str:
    return f"{value:.4f}"


def _describe(param: Param) -> str:
    unc = f" ±{param.uncertainty_mm:.3f} mm" if param.uncertainty_mm is not None else ""
    ev = "; ".join(f"{e.kind}: {e.detail}" for e in param.evidence)
    return _comment(f"{param.status.value}{unc}" + (f" ({ev})" if ev else ""))


def emit_scad(spec: PartSpec, job_id: str | None = None) -> str:
    lines = [
        "// RE-FORGE AI reconstruction. PartSpec v1"
        + (f", job {_comment(job_id)}" if job_id else "")
        + f", generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "// A reconstruction, not a verified replacement part. Not for safety-critical use.",
        "// Model frame: millimetres, x right, y up, z up from the print bed.",
        "",
        f"thickness = {_num(spec.thickness.value)}; // {_describe(spec.thickness)}",
        f"hole_comp = {_num(spec.fit.hole_offset_mm)}; // added to every hole diameter (printer compensation)",
        f"outline_offset = {_num(spec.fit.outline_offset_mm)}; // grows (+) or shrinks (-) the outline",
    ]
    for hole in spec.holes:
        if isinstance(hole, CircleHole):
            lines += [
                f"{hole.id}_x = {_num(hole.center_x.value)}; // {_describe(hole.center_x)}",
                f"{hole.id}_y = {_num(hole.center_y.value)}; // {_describe(hole.center_y)}",
                f"{hole.id}_d = {_num(hole.diameter.value)}; // {_describe(hole.diameter)}",
            ]
        else:
            pts = ", ".join(f"[{_num(x)}, {_num(y)}]" for x, y in hole.points)
            lines.append(f"{hole.id}_points = [{pts}]; // {hole.status.value} ({_comment(hole.source)})")
    runs = "; ".join(f"points {r.start}-{r.end} {r.status.value} ({_comment(r.source)})" for r in spec.outline.runs)
    lines.append(f"// outline: {len(spec.outline.points)} points; {_comment(runs)}")
    points = ", ".join(f"[{_num(x)}, {_num(y)}]" for x, y in spec.outline.points)
    lines += [f"outline = [{points}];", "", "difference() {",
              "  linear_extrude(height = thickness) offset(delta = outline_offset) polygon(outline);"]
    for hole in spec.holes:
        if isinstance(hole, CircleHole):
            fn = circle_segments(hole.diameter.value / 2)
            lines.append(f"  translate([{hole.id}_x, {hole.id}_y, -1]) "
                         f"cylinder(d = {hole.id}_d + hole_comp, h = thickness + 2, $fn = {fn});")
        else:
            lines.append(f"  translate([0, 0, -1]) linear_extrude(height = thickness + 2) "
                         f"offset(delta = hole_comp / 2) polygon({hole.id}_points);")
    lines.append("}")
    return "\n".join(lines) + "\n"
