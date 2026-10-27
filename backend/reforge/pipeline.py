"""M1 pipeline: photo → calibration → segmentation → refined profile → PartSpec → solid → validated STL.

Every stage is timed for real and every measured quantity is reported with its evidence.
Reconstruction of missing geometry (symmetry) comes in M2. M1 builds exactly what was observed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from reforge.cad.build import build_part, write_stl
from reforge.cad.scad import emit_scad
from reforge.capture.calibration import RectifiedView, calibrate, rectify
from reforge.errors import ReforgeError
from reforge.geometry.circle import fit_circle
from reforge.spec.partspec import (
    MAX_POINTS,
    CircleHole,
    Evidence,
    Outline,
    OutlineRun,
    Param,
    PartSpec,
    PolygonHole,
    Status,
    mat_to_model,
)
from reforge.validation.mesh import summarize, validate_part
from reforge.vision.refine import RefinedProfile, refine_profile
from reforge.vision.segment import Segmentation

CALIPER_UNCERTAINTY_MM = 0.05  # default instrument + reading, 2σ; the user can override
ROUND_HOLE_MAX_DEVIATION_MM = 0.12
OVERLAY_MARGIN_MM = 8.0


class Segmenter(Protocol):
    method: str

    async def segment(self, view: RectifiedView) -> Segmentation: ...


def _simplify(points: np.ndarray, limit: int = MAX_POINTS) -> np.ndarray:
    tolerance = 0.002
    poly = Polygon(points)
    while len(points) > limit:
        tolerance *= 2
        points = np.asarray(poly.simplify(tolerance, preserve_topology=True).exterior.coords)[:-1]
    return points


def profile_to_spec(profile: RefinedProfile, thickness: Param) -> tuple[PartSpec, list[dict]]:
    """The observed profile as a PartSpec in the model frame, plus notes on anything left out."""
    outer = profile.outer.points_mm
    x0, y0 = outer.min(axis=0)
    x1, y1 = outer.max(axis=0)
    origin = ((x0 + x1) / 2, (y0 + y1) / 2)
    pts = np.asarray(orient(Polygon(mat_to_model(outer, origin)), 1.0).exterior.coords)[:-1]
    pts = _simplify(pts)
    notes: list[dict] = []
    holes: list[CircleHole | PolygonHole] = []
    for cand in profile.holes:
        if cand.glare_suspect:
            notes.append({"hole": cand.hole_id, "excluded": True, "status": Status.UNCERTAIN.value,
                          "reason": "brighter than the mat paper: possibly glare, not a hole; confirm to include"})
            continue
        hid = f"H{len(holes)}"
        fit = fit_circle(cand.contour.points_mm)
        agree = "segmenter agrees" if cand.mask_agrees else "found by colour only"
        if fit.max_deviation <= ROUND_HOLE_MAX_DEVIATION_MM:
            (cx, cy), = mat_to_model(np.array([fit.center]), origin)
            ev = (Evidence(kind="circle_fit", detail=f"rms {fit.rms:.3f} mm, max dev {fit.max_deviation:.3f} mm, "
                           f"{fit.n_points} edge points; {agree}"),)
            holes.append(CircleHole(id=hid, center_x=Param(value=cx, status=Status.OBSERVED, evidence=ev),
                                    center_y=Param(value=cy, status=Status.OBSERVED, evidence=ev),
                                    diameter=Param(value=fit.diameter, status=Status.OBSERVED, evidence=ev)))
        else:
            hp = np.asarray(orient(Polygon(mat_to_model(cand.contour.points_mm, origin)), 1.0).exterior.coords)[:-1]
            holes.append(PolygonHole(id=hid, points=tuple(map(tuple, _simplify(hp))), status=Status.OBSERVED,
                                     source=f"traced edge, not round (max dev {fit.max_deviation:.2f} mm); {agree}"))
    outline = Outline(points=tuple(map(tuple, pts)), runs=(OutlineRun(
        start=0, end=len(pts) - 1, status=Status.OBSERVED, source="calibrated photo, refined boundary"),))
    try:
        spec = PartSpec(outline=outline, holes=tuple(holes), thickness=thickness)
    except ValueError as exc:  # pydantic ValidationError subclasses ValueError
        raise ReforgeError("SPEC_INVALID", str(exc)[:600], "Check the photo and the segmentation.") from exc
    return spec, notes


def _overlay(view: RectifiedView, seg: Segmentation, profile: RefinedProfile) -> np.ndarray:
    out = view.image.copy()
    tint = out.copy()
    tint[seg.mask] = (0.6 * tint[seg.mask] + 0.4 * np.array([255, 140, 0])).astype(np.uint8)
    out = cv2.addWeighted(tint, 0.6, out, 0.4, 0)
    cv2.polylines(out, [np.round(view.mm_to_px(profile.outer.points_mm)).astype(np.int32)], True, (255, 90, 0), 1,
                  cv2.LINE_AA)
    for h in profile.holes:
        color = (0, 200, 255) if h.glare_suspect else (60, 220, 60)
        cv2.polylines(out, [np.round(view.mm_to_px(h.contour.points_mm)).astype(np.int32)], True, color, 1,
                      cv2.LINE_AA)
    # Crop to the part with a margin, so the outline is legible instead of a speck on the mat.
    px = view.mm_to_px(profile.outer.points_mm)
    margin = OVERLAY_MARGIN_MM * view.px_per_mm
    x0, y0 = np.floor(px.min(axis=0) - margin).astype(int)
    x1, y1 = np.ceil(px.max(axis=0) + margin).astype(int)
    h_img, w_img = out.shape[:2]
    return out[max(y0, 0):min(y1, h_img), max(x0, 0):min(x1, w_img)]


async def photo_to_stl(photo: Path, out_dir: Path, thickness_mm: float, segmenter: Segmenter, *,
                       bar_x_mm: float | None = None, bar_y_mm: float | None = None,
                       thickness_uncertainty_mm: float = CALIPER_UNCERTAINTY_MM, job_id: str | None = None) -> dict:
    timings: dict[str, float] = {}

    def lap(name: str, t0: float) -> float:
        timings[name] = round(time.perf_counter() - t0, 3)
        return time.perf_counter()

    t = time.perf_counter()
    image = cv2.imread(str(photo), cv2.IMREAD_COLOR)  # applies EXIF orientation
    if image is None:
        raise ReforgeError("IMAGE_INVALID", f"Could not read {photo.name} as an image.")
    t = lap("load", t)
    cal = calibrate(image, bar_x_mm=bar_x_mm, bar_y_mm=bar_y_mm)
    view = rectify(image, cal)
    t = lap("calibrate_rectify", t)
    seg = await segmenter.segment(view)
    t = lap("segment", t)
    profile = refine_profile(view, seg.mask)
    t = lap("refine", t)
    thickness = Param(value=thickness_mm, status=Status.MEASURED, uncertainty_mm=thickness_uncertainty_mm,
                      evidence=(Evidence(kind="caliper", detail="entered by the user"),))
    spec, notes = profile_to_spec(profile, thickness)
    part = build_part(spec)
    validation = summarize(validate_part(part, spec))
    t = lap("spec_build_validate", t)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_stl(part, out_dir / "model.stl")
    (out_dir / "model.scad").write_text(emit_scad(spec, job_id), encoding="utf-8")
    (out_dir / "spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    cv2.imwrite(str(out_dir / "overlay.png"), _overlay(view, seg, profile))
    lap("write", t)

    mesh = part.to_trimesh()
    (bx0, by0, bz0), (bx1, by1, bz1) = mesh.bounds
    report = {
        "job_id": job_id,
        "photo": photo.name,
        "milestone": "M1: observed geometry only (no reconstruction yet)",
        "calibration": {"page": cal.page, "markers": len(cal.marker_ids), "fit_rms_mm": round(cal.rms_mm, 4),
                        "loo_rms_mm": None if cal.loo_rms_mm is None else round(cal.loo_rms_mm, 4),
                        "px_per_mm": round(cal.px_per_mm, 2), "perspective_ratio": round(cal.perspective_ratio, 3),
                        "scale_correction": cal.scale_correction,
                        "warnings": [w.__dict__ for w in cal.warnings]},
        "segmentation": {"method": seg.method, "is_ai": seg.is_ai, "confidence": seg.confidence,
                         "latency_s": round(seg.latency_s, 3), "cost_usd": seg.cost_usd, "detail": seg.detail},
        "refinement": {"refined": profile.refined, "contrast_delta_e": round(profile.contrast_delta_e, 1),
                       "band_mm": round(profile.band_mm, 3),
                       "coarse_shift_mean_mm": round(profile.coarse_shift_mean_mm, 4),
                       "coarse_shift_max_mm": round(profile.coarse_shift_max_mm, 4),
                       "warnings": [w.__dict__ for w in profile.warnings]},
        "part": {"overall_mm": [round(bx1 - bx0, 3), round(by1 - by0, 3), round(bz1 - bz0, 3)],
                 "holes": [{"id": h.id, "kind": h.kind,
                            **({"diameter_mm": round(h.diameter.value, 3),
                                "center_mm": [round(h.center_x.value, 3), round(h.center_y.value, 3)]}
                               if isinstance(h, CircleHole) else {"source": h.source})} for h in spec.holes],
                 "excluded_candidates": notes, "unresolved": spec.unresolved()},
        "validation": validation,
        "timings_s": timings,
        "outputs": ["model.stl", "model.scad", "spec.json", "overlay.png", "report.json"],
        "disclaimer": "A reconstruction, not a verified replacement part. Not for safety-critical use.",
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
