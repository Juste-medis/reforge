"""Closed-contour utilities."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d


def smooth_closed(points: np.ndarray, sigma: float, spacing: float) -> np.ndarray:
    """Gaussian smoothing along the arc length of a closed polyline, resampled every ``spacing``.

    Removes the per-point jitter of a traced edge (pixel noise), which otherwise sits at the extremes of the outline
    and inflates its bounding box. Known effect on the true shape: a circle of radius R shrinks by about
    sigma² / (2R), and a sharp corner is rounded over about 2 sigma.
    """
    p = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    closed = np.vstack([p, p[:1]])
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))])
    total = s[-1]
    n = max(int(np.ceil(total / spacing)), 16)
    u = np.arange(n) * (total / n)
    x, y = np.interp(u, s, closed[:, 0]), np.interp(u, s, closed[:, 1])
    k = sigma / (total / n)
    return np.column_stack([gaussian_filter1d(x, k, mode="wrap"), gaussian_filter1d(y, k, mode="wrap")])
