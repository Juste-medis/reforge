import numpy as np
import pytest

from reforge.geometry.circle import fit_circle


def _circle(cx: float, cy: float, r: float, start: float, stop: float, n: int, noise: float, seed: int = 0):
    rng = np.random.default_rng(seed)
    a = np.linspace(start, stop, n)
    pts = np.column_stack([cx + r * np.cos(a), cy + r * np.sin(a)])
    return pts + rng.normal(0, noise, pts.shape)


def test_full_circle_with_noise() -> None:
    fit = fit_circle(_circle(10.0, -4.0, 2.1, 0, 2 * np.pi, 200, 0.01))
    assert fit.center == pytest.approx((10.0, -4.0), abs=0.005)
    assert fit.diameter == pytest.approx(4.2, abs=0.005)
    assert fit.rms == pytest.approx(0.01, abs=0.004)


def test_short_arc_is_unbiased_after_geometric_refinement() -> None:
    fit = fit_circle(_circle(0.0, 0.0, 15.0, 0.2, 0.2 + np.pi / 2, 120, 0.02, seed=3))
    assert fit.radius == pytest.approx(15.0, abs=0.05)


def test_too_few_points() -> None:
    with pytest.raises(ValueError):
        fit_circle(np.array([[0.0, 0.0], [1.0, 0.0]]))
