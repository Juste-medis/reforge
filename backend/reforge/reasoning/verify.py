"""Geometric verification of an interpretation: the model's answer is evidence, not a decision.

- The chosen axis must exist and have measured support of at least ``MIN_AXIS_SUPPORT``.
- A segment picked as a fracture must *not* match its mirror image under that axis: a smooth edge that does is
  intact, and the pick is rejected. A pick the geometry finds smooth (not irregular) is kept with a warning.
- Irregular segments the model didn't pick, and an answer that contradicts itself, are reported.
Rejected items never reach the reconstruction; every note is shown to the user.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reforge.geometry.segments import SegmentedOutline
from reforge.geometry.symmetry import MirrorAxis, local_support
from reforge.reasoning.analysis import NONE_ID, PartAnalysis

MIN_AXIS_SUPPORT = 0.9
MAX_FRACTURE_MIRROR_SUPPORT = 0.6


@dataclass(frozen=True)
class Note:
    code: str
    message: str
    level: str  # "info" | "warning" | "rejected"


@dataclass(frozen=True)
class Verified:
    fracture_ids: tuple[str, ...]
    axis: MirrorAxis | None
    notes: tuple[Note, ...]


def verify(analysis: PartAnalysis, segmented: SegmentedOutline, axes: list[MirrorAxis],
           outline_mm: np.ndarray) -> Verified:
    notes: list[Note] = []
    axis = None
    if analysis.mirror_axis_id != NONE_ID:
        chosen = next((a for a in axes if a.axis_id == analysis.mirror_axis_id), None)
        if chosen is None:
            notes.append(Note("AXIS_UNKNOWN", f"{analysis.mirror_axis_id} is not a candidate axis.", "rejected"))
        elif chosen.support < MIN_AXIS_SUPPORT:
            notes.append(Note("AXIS_WEAK", f"{chosen.axis_id} has only {chosen.support:.0%} measured support "
                                           f"(needs {MIN_AXIS_SUPPORT:.0%}); no mirror reconstruction.", "rejected"))
        elif chosen.contradicted_by_holes:
            notes.append(Note("AXIS_HOLES", f"{chosen.axis_id} maps holes onto solid material "
                                            f"({chosen.hole_mismatches} against, {chosen.hole_matches} for).",
                              "rejected"))
        else:
            axis = chosen
            if (chosen.offset_ambiguity_mm or 0.0) > 0.5:
                notes.append(Note("AXIS_OFFSET_AMBIGUOUS",
                                  f"Nothing pins {chosen.axis_id} along the part: it can slide "
                                  f"{chosen.offset_ambiguity_mm:.1f} mm with the same support, so the rebuilt length "
                                  "is uncertain. Measure the original length or a feature on the broken side.",
                                  "warning"))
            if analysis.symmetry != "mirror":
                notes.append(Note("SYMMETRY_INCONSISTENT", f"An axis was chosen but symmetry is "
                                                           f"'{analysis.symmetry}'; the axis is used.", "warning"))
    elif analysis.symmetry == "mirror":
        notes.append(Note("AXIS_MISSING", "Mirror symmetry was claimed without choosing an axis.", "warning"))

    accepted: list[str] = []
    for sid in analysis.fracture_segment_ids:
        seg = segmented.by_id(sid)
        if axis is not None:
            matched = local_support(axis, segmented.span(seg), outline_mm)
            if matched > MAX_FRACTURE_MIRROR_SUPPORT:
                notes.append(Note("FRACTURE_MATCHES_MIRROR",
                                  f"{sid} matches its mirror image under {axis.axis_id} ({matched:.0%} of its length), "
                                  "so it looks intact: not treated as a fracture.", "rejected"))
                continue
        if seg.kind != "irregular":
            notes.append(Note("FRACTURE_SMOOTH", f"{sid} was picked as a fracture but the geometry sees a smooth "
                                                 f"{seg.kind} (fit residual {seg.fit_rms_mm:.3f} mm): please confirm.",
                              "warning"))
        accepted.append(sid)

    unpicked = [s.seg_id for s in segmented.segments
                if s.kind == "irregular" and s.seg_id not in analysis.fracture_segment_ids]
    if unpicked:
        notes.append(Note("FRACTURE_UNPICKED", f"{', '.join(unpicked)} look irregular but weren't picked as fracture "
                                               "edges; they're left as photographed.", "warning"))
    if analysis.is_broken and not accepted:
        notes.append(Note("NO_FRACTURE", "The part was called broken, but no fracture segment was accepted: nothing "
                                         "is reconstructed.", "warning"))
    if not analysis.is_broken and accepted:
        notes.append(Note("BROKEN_INCONSISTENT", "Fracture segments were picked although the part was called intact.",
                          "warning"))
    if accepted and axis is not None:
        notes.append(Note("CROSS_CHECK", f"Fracture {', '.join(accepted)} and axis {axis.axis_id} "
                                         f"(support {axis.support:.0%}) passed the geometric checks.", "info"))
    return Verified(tuple(accepted), axis, tuple(notes))
