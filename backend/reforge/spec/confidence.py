"""Confidence Engine (PLAN §6.6): a 2σ uncertainty for every reported dimension, from a stated error budget.

    U = 2·√(Σ termᵢ²)   with each term a 1σ contribution in mm, and its basis recorded next to it.

The terms come from what this photo measured, not from a fixed accuracy claim:
- **calibration**: the mat fit's leave-one-marker-out RMS (the fit RMS when too few markers allow it). It is applied
  at both ends of a length. On real prints it is mostly paper flatness, a low-frequency error, so it is left out of
  a hole's diameter (a few mm across).
- **print scale**: relative. Checked with a caliper on the printed 100 mm bars, it is the caliper's ±0.05 mm over
  100 mm. Unchecked, it is a stated assumption for a print at 100 % (one real print measured within 0.3 %,
  2026-11-03); a print scaled to fit the page breaks this assumption, which is why the UI asks for the bar check.
- **edges**: the boundary's localisation, per edge: half a pixel once refined against the mat background, more when
  the refinement couldn't run (low contrast).
- **circle fit**: a hole's radial residual over its edge points.
- **height correction**: the 1σ uncertainty of the parallax correction from the camera pose.
- **mirror** (INFERRED only): the reconstruction's own 2σ (axis inlier RMS, angle × lever arm, offset), added to the
  uncertainty of the source geometry it copies.

These are *modelled* uncertainties. Whether they cover the truth is checked against caliper readings on real parts
(coverage, ``docs/EVALUATION.md``); until enough parts are measured, every surface calls them estimates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Polygon

SCALE_REL_ASSUMED = 0.0025  # 1σ: print at 100 %, not caliper-checked
SCALE_REL_CHECKED = 0.00025  # 1σ: caliper ±0.05 mm (2σ) read on the 100 mm bar
EDGE_PX_REFINED = 0.5  # 1σ per edge
EDGE_PX_COARSE = 1.5
EDGE_MIN_MM = 0.03
CALIPER_U_MM = 0.05  # 2σ, instrument + reading
MODEL_NOTE = ("modelled 2σ from this photo's error budget (calibration, print scale, edges, height correction); "
              "coverage against caliper readings is still being measured on real parts")


@dataclass(frozen=True)
class Term:
    name: str
    sigma_mm: float  # 1σ contribution to this dimension
    basis: str

    def to_dict(self) -> dict:
        return {"name": self.name, "sigma_mm": round(self.sigma_mm, 4), "basis": self.basis}


@dataclass(frozen=True)
class Estimate:
    terms: tuple[Term, ...]

    @property
    def u_mm(self) -> float:
        """2σ."""
        return 2.0 * math.sqrt(sum(t.sigma_mm**2 for t in self.terms))

    @property
    def dominant(self) -> str:
        return max(self.terms, key=lambda t: t.sigma_mm).name if self.terms else ""


@dataclass(frozen=True)
class ErrorBudget:
    u_cal_mm: float
    cal_basis: str
    scale_rel: float
    scale_checked: bool
    u_edge_mm: float
    edge_basis: str
    u_persp_mm: float  # 1σ
    extra: dict = field(default_factory=dict)
    scale_basis_override: str | None = None  # ruler mode: the scale isn't a print scale
    persp_basis: str = "camera pose from the mat"

    @property
    def scale_basis(self) -> str:
        if self.scale_basis_override is not None:
            return self.scale_basis_override
        if self.scale_checked:
            return "print scale checked with a caliper on both 100 mm bars (±0.05 mm)"
        return (f"print scale assumed at 100 % (±{2 * self.scale_rel:.1%}, 2σ); "
                + ("only one bar was caliper-checked" if self.extra.get("bars_checked") == 1
                   else "not caliper-checked"))

    def length(self, length_mm: float) -> Estimate:
        return Estimate((
            Term("calibration", math.sqrt(2) * self.u_cal_mm, f"{self.cal_basis}, at both ends"),
            Term("print scale", self.scale_rel * length_mm, self.scale_basis),
            Term("edges", math.sqrt(2) * self.u_edge_mm, f"{self.edge_basis}, two edges"),
            Term("height correction", self.u_persp_mm, self.persp_basis),
        ))

    def diameter(self, diameter_mm: float, fit_rms_mm: float, n_points: int) -> Estimate:
        return Estimate((
            Term("print scale", self.scale_rel * diameter_mm, self.scale_basis),
            Term("edges", math.sqrt(2) * self.u_edge_mm, f"{self.edge_basis}, both sides of the hole"),
            Term("circle fit", 2.0 * fit_rms_mm / math.sqrt(max(n_points, 1)),
                 f"radial RMS {fit_rms_mm:.3f} mm over {n_points} edge points"),
        ))

    def to_dict(self) -> dict:
        return {"calibration_mm": round(self.u_cal_mm, 4), "calibration_basis": self.cal_basis,
                "scale_rel": self.scale_rel, "scale_checked": self.scale_checked, "scale_basis": self.scale_basis,
                "edge_mm": round(self.u_edge_mm, 4), "edge_basis": self.edge_basis,
                "height_mm": round(self.u_persp_mm, 4), **self.extra}


def build_budget(*, fit_rms_mm: float, loo_rms_mm: float | None, bars_checked: int, px_per_mm: float,
                 refined: bool, u_persp_2sigma_mm: float, ruler_reading_rel: float | None = None,
                 persp_basis: str | None = None) -> ErrorBudget:
    """The per-photo budget. ``bars_checked`` is how many of the two 100 mm bars the user read with a caliper: the
    scale counts as checked only with both, since each corrects one axis. ``ruler_reading_rel`` switches to ruler
    mode (no mat): no fit term, the entered length's relative uncertainty as the scale term."""
    if ruler_reading_rel is not None:
        u_cal, cal_basis = 0.0, "no mat was used: nothing fitted"
        scale_rel, scale_basis = ruler_reading_rel, (
            f"ruler: the entered length, read carefully (±{2 * ruler_reading_rel:.1%}, 2σ)")
    elif loo_rms_mm is not None:
        u_cal, cal_basis = loo_rms_mm, f"mat fit, leave-one-marker-out RMS {loo_rms_mm:.3f} mm"
        scale_rel, scale_basis = None, None
    else:
        u_cal, cal_basis = fit_rms_mm, f"mat fit RMS {fit_rms_mm:.3f} mm (too few markers for leave-one-out)"
        scale_rel, scale_basis = None, None
    checked = bars_checked >= 2
    edge_px = EDGE_PX_REFINED if refined else EDGE_PX_COARSE
    u_edge = max(edge_px / px_per_mm, EDGE_MIN_MM)
    edge_basis = (f"{edge_px} px at {px_per_mm:.1f} px/mm, " + ("refined boundary" if refined
                                                                 else "coarse boundary (refinement skipped)"))
    if scale_rel is None:
        scale_rel = SCALE_REL_CHECKED if checked else SCALE_REL_ASSUMED
    return ErrorBudget(u_cal_mm=float(u_cal), cal_basis=cal_basis,
                       scale_rel=scale_rel, scale_checked=checked,
                       u_edge_mm=float(u_edge), edge_basis=edge_basis, u_persp_mm=float(u_persp_2sigma_mm) / 2,
                       extra={"bars_checked": bars_checked}, scale_basis_override=scale_basis,
                       persp_basis=persp_basis or "camera pose from the mat")


def with_mirror(estimate: Estimate, mirror_u_2sigma_mm: float, axis_id: str) -> Estimate:
    """An INFERRED quantity: the source geometry's uncertainty plus the mirror's own."""
    return Estimate(estimate.terms + (Term("mirror", mirror_u_2sigma_mm / 2,
                                           f"mirror about {axis_id}: axis RMS, angle × lever arm, offset"),))


def with_bridge(estimate: Estimate, bridge_u_2sigma_mm: float, source: str) -> Estimate:
    """A BRIDGED quantity: the source geometry's uncertainty plus the bridge's own."""
    return Estimate(estimate.terms + (Term("bridge", bridge_u_2sigma_mm / 2,
                                           f"smooth bridge ({source}): neighbours' fit residuals"),))


def min_rect_mm(points_mm: np.ndarray) -> tuple[float, float, float]:
    """Length ≥ width of the smallest rectangle around the outline, and its angle to the model x axis (degrees).

    This is what a caliper reads across the part, whatever its orientation on the mat."""
    rect = Polygon(np.asarray(points_mm, dtype=float)).minimum_rotated_rectangle
    c = np.asarray(rect.exterior.coords)[:4]
    e1, e2 = c[1] - c[0], c[2] - c[1]
    l1, l2 = float(np.hypot(*e1)), float(np.hypot(*e2))
    long_edge = e1 if l1 >= l2 else e2
    angle = round(math.degrees(math.atan2(long_edge[1], long_edge[0])), 2) % 180.0
    return max(l1, l2), min(l1, l2), angle
