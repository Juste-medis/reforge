"""Least-squares circle fitting for through-holes and arcs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CircleFit:
    center: tuple[float, float]
    radius: float
    rms: float  # RMS radial residual, same units as the input
    max_deviation: float  # max |radial residual|; a roundness indicator
    n_points: int

    @property
    def diameter(self) -> float:
        return 2.0 * self.radius


def fit_circle(points: np.ndarray, iterations: int = 20) -> CircleFit:
    """Algebraic (Kåsa) start refined by Gauss–Newton on the geometric distance.

    The geometric step removes the algebraic fit's bias on short or noisy arcs.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        raise ValueError("a circle needs at least 3 points")
    x, y = pts[:, 0], pts[:, 1]
    a = np.column_stack([x, y, np.ones_like(x)])
    b = x**2 + y**2
    (c0, c1, c2), *_ = np.linalg.lstsq(a, b, rcond=None)
    cx, cy = c0 / 2, c1 / 2
    r = float(np.sqrt(max(c2 + cx**2 + cy**2, 0.0)))
    for _ in range(iterations):
        dx, dy = x - cx, y - cy
        d = np.hypot(dx, dy)
        d[d == 0] = 1e-12
        residual = d - r
        jac = np.column_stack([-dx / d, -dy / d, -np.ones_like(d)])
        step, *_ = np.linalg.lstsq(jac, -residual, rcond=None)
        cx, cy, r = cx + step[0], cy + step[1], r + step[2]
        if np.abs(step).max() < 1e-10:
            break
    residual = np.hypot(x - cx, y - cy) - r
    return CircleFit((float(cx), float(cy)), float(r), float(np.sqrt(np.mean(residual**2))),
                     float(np.abs(residual).max()), len(pts))
