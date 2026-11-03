"""Confidence Engine: the error budget's terms, and how they combine (PLAN §6.6)."""

import math

import numpy as np
import pytest

from reforge.spec.confidence import (
    SCALE_REL_ASSUMED,
    SCALE_REL_CHECKED,
    build_budget,
    min_rect_mm,
    with_mirror,
)


def _budget(**kw):
    args = {"fit_rms_mm": 0.2, "loo_rms_mm": 0.25, "bars_checked": 0, "px_per_mm": 10.0, "refined": True,
            "u_persp_2sigma_mm": 0.1}
    return build_budget(**(args | kw))


def test_length_combines_the_stated_terms_root_sum_square() -> None:
    b = _budget()
    est = b.length(100.0)
    terms = {t.name: t.sigma_mm for t in est.terms}
    assert terms["calibration"] == pytest.approx(math.sqrt(2) * 0.25)  # leave-one-out RMS, at both ends
    assert terms["print scale"] == pytest.approx(SCALE_REL_ASSUMED * 100.0)
    assert terms["edges"] == pytest.approx(math.sqrt(2) * 0.05)  # half a pixel at 10 px/mm
    assert terms["height correction"] == pytest.approx(0.05)
    assert est.u_mm == pytest.approx(2 * math.sqrt(sum(v**2 for v in terms.values())))


def test_checking_both_bars_shrinks_the_scale_term_and_says_so() -> None:
    unchecked, one, both = _budget(), _budget(bars_checked=1), _budget(bars_checked=2)
    assert unchecked.scale_rel == one.scale_rel == SCALE_REL_ASSUMED and both.scale_rel == SCALE_REL_CHECKED
    assert "not caliper-checked" in unchecked.scale_basis
    assert "only one bar" in one.scale_basis
    assert "checked with a caliper" in both.scale_basis
    assert both.length(80).u_mm < unchecked.length(80).u_mm


def test_fit_rms_stands_in_when_leave_one_out_is_unavailable() -> None:
    b = _budget(loo_rms_mm=None)
    assert b.u_cal_mm == 0.2 and "too few markers" in b.cal_basis


def test_an_unrefined_edge_is_less_certain() -> None:
    assert _budget(refined=False).u_edge_mm > _budget(refined=True).u_edge_mm


def test_a_hole_diameter_leaves_out_the_low_frequency_calibration_error() -> None:
    est = _budget().diameter(5.0, fit_rms_mm=0.02, n_points=400)
    assert {t.name for t in est.terms} == {"print scale", "edges", "circle fit"}
    assert est.u_mm < _budget().length(5.0).u_mm


def test_mirrored_geometry_adds_the_mirror_to_its_source() -> None:
    source = _budget().diameter(5.0, 0.02, 400)
    inferred = with_mirror(source, mirror_u_2sigma_mm=0.06, axis_id="A1")
    assert inferred.terms[-1].name == "mirror" and "A1" in inferred.terms[-1].basis
    assert inferred.u_mm == pytest.approx(math.hypot(source.u_mm, 0.06))


@pytest.mark.parametrize("angle", [0.0, 30.0, 90.0, 147.0])
def test_caliper_style_size_ignores_the_parts_orientation(angle: float) -> None:
    a = np.radians(angle)
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    rect = np.array([[-35, -9], [35, -9], [35, 9], [-35, 9]], float) @ rot.T + [12.0, -4.0]
    length, width, measured_angle = min_rect_mm(rect)
    assert length == pytest.approx(70.0) and width == pytest.approx(18.0)
    assert min(abs(measured_angle - angle % 180), 180 - abs(measured_angle - angle % 180)) < 1e-6
