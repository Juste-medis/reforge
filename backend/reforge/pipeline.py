"""M1 pipeline: photo → calibration → segmentation → refined profile → height correction → PartSpec → solid → STL.

Every stage is timed for real and every measured quantity is reported with its evidence.
Reconstruction of missing geometry (symmetry) comes in M2. M1 builds exactly what was observed: the photographed
silhouette, corrected for the part's own height (its top face is closer to the camera than the mat).
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from reforge.cad.build import build_part, write_stl
from reforge.cad.scad import emit_scad
from reforge.capture.calibration import RectifiedView, calibrate, rectify
from reforge.capture.pose import FULL_FRAME_DIAGONAL_MM, estimate_pose, focal_35mm_from_exif
from reforge.errors import ReforgeError
from reforge.geometry.circle import fit_circle
from reforge.geometry.completion import Completion
from reforge.geometry.height import correct_height
from reforge.reasoning.interpret import GeometricInterpreter
from reforge.reasoning.reconstruct import Reconstruction, reconstruct
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
MIN_TRACE_SHARE = 0.2  # below this the trace is a fragment of something else: refuse before any model call
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


def _signed_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _outline_in_model_frame(points_mat: np.ndarray, origin: tuple[float, float],
                            runs: list[tuple[int, int, Status, str]]) -> Outline:
    """Mat → model frame, counter-clockwise, with run indices remapped exactly if the order has to be reversed."""
    pts = mat_to_model(points_mat, origin)
    if _signed_area(pts) < 0:
        n = len(pts)
        pts = pts[::-1]
        runs = [(n - 1 - end, n - 1 - start, status, source) for start, end, status, source in reversed(runs)]
    return Outline(points=tuple(map(tuple, pts)), runs=tuple(
        OutlineRun(start=a, end=b, status=status, source=source[:120]) for a, b, status, source in runs))


def profile_to_spec(profile: RefinedProfile, thickness: Param, completion: Completion | None = None
                    ) -> tuple[PartSpec, list[dict]]:
    """The footprint as a PartSpec in the model frame, plus notes on anything left out.

    With a ``completion``, the outline is the mirror-completed one with its provenance runs, and mirrored holes that
    land in the added material are included as INFERRED."""
    outer = completion.points if completion is not None else profile.outer.points_mm
    x0, y0 = outer.min(axis=0)
    x1, y1 = outer.max(axis=0)
    origin = ((x0 + x1) / 2, (y0 + y1) / 2)
    if completion is None:
        pts = np.asarray(orient(Polygon(mat_to_model(outer, origin)), 1.0).exterior.coords)[:-1]
        pts = _simplify(pts)
        outline = Outline(points=tuple(map(tuple, pts)), runs=(OutlineRun(
            start=0, end=len(pts) - 1, status=Status.OBSERVED, source="calibrated photo, refined boundary"),))
    else:
        outline = _outline_in_model_frame(outer, origin, [(r.start, r.end, Status(r.status), r.source)
                                                          for r in completion.runs])
    notes: list[dict] = []
    holes: list[CircleHole | PolygonHole] = []
    sigma = profile.edge_sigma_mm or 0.0
    for cand in profile.holes:
        if cand.glare_suspect:
            notes.append({"hole": cand.hole_id, "excluded": True, "status": Status.UNCERTAIN.value,
                          "reason": "brighter than the mat paper: possibly glare, not a hole; confirm to include"})
            continue
        hid = f"H{len(holes)}"
        fit = cand.fit or fit_circle(cand.contour.points_mm)
        agree = "segmenter agrees" if cand.mask_agrees else "found by colour only"
        if fit.max_deviation <= ROUND_HOLE_MAX_DEVIATION_MM:
            (cx, cy), = mat_to_model(np.array([fit.center]), origin)
            model = "through-thickness circle fit (parallax model)" if cand.fit else "circle fit"
            # The traced edge of a blurred hole sits σ²/(2R) inside it (curvature bias of the iso-contour).
            curvature = sigma**2 / (2 * fit.radius)
            fit = replace(fit, radius=fit.radius + curvature)
            ev = (Evidence(kind="circle_fit", detail=f"{model}: rms {fit.rms:.3f} mm, max dev {fit.max_deviation:.3f} "
                           f"mm, {fit.n_points} edge points; blur-curvature correction +{2 * curvature:.4f} mm on Ø "
                           f"(edge σ {sigma:.3f} mm); {agree}"),)
            holes.append(CircleHole(id=hid, center_x=Param(value=cx, status=Status.OBSERVED, evidence=ev),
                                    center_y=Param(value=cy, status=Status.OBSERVED, evidence=ev),
                                    diameter=Param(value=fit.diameter, status=Status.OBSERVED, evidence=ev)))
        else:
            hp = np.asarray(orient(Polygon(mat_to_model(cand.contour.points_mm, origin)), 1.0).exterior.coords)[:-1]
            holes.append(PolygonHole(id=hid, points=tuple(map(tuple, _simplify(hp))), status=Status.OBSERVED,
                                     source=f"traced edge, not round (max dev {fit.max_deviation:.2f} mm); {agree}"))
    for inferred in completion.inferred_holes if completion is not None else ():
        (cx, cy), = mat_to_model(np.array([inferred.center]), origin)
        radius = inferred.radius + sigma**2 / (2 * inferred.radius)
        ev = (Evidence(kind="mirror", detail=f"mirror of {inferred.source_hole_id} about {completion.axis.axis_id} "
                                             f"(support {completion.axis.support:.0%}); lands in the added material"),)
        holes.append(CircleHole(id=f"H{len(holes)}", center_x=Param(value=cx, status=Status.INFERRED, evidence=ev),
                                center_y=Param(value=cy, status=Status.INFERRED, evidence=ev),
                                diameter=Param(value=2 * radius, status=Status.INFERRED, evidence=ev)))
    try:
        spec = PartSpec(outline=outline, holes=tuple(holes), thickness=thickness)
    except ValueError as exc:  # pydantic ValidationError subclasses ValueError
        raise ReforgeError("SPEC_INVALID", str(exc)[:600], "Check the photo and the segmentation.") from exc
    return spec, notes


PROVENANCE_COLOURS = {"OBSERVED": (255, 230, 0), "INFERRED": (200, 60, 200), "UNCERTAIN": (40, 40, 230)}  # BGR


OVERLAY_WIDTH_PX = 1400


def _overlay(view: RectifiedView, seg: Segmentation, profile: RefinedProfile, footprint: RefinedProfile,
             completion: Completion | None = None) -> np.ndarray:
    """Segmentation tint, photographed outline (blue) and holes (green), and the height-corrected footprint (cyan):
    the footprint sits inside the photographed outline wherever the top edge was seen. With a mirror completion, the
    final outline is drawn thicker, coloured by provenance (magenta INFERRED, red UNCERTAIN), with the axis dashed.

    The view is cropped to the part and enlarged to about ``OVERLAY_WIDTH_PX`` before drawing, so lines stay sharp."""
    extent = profile.outer.points_mm if completion is None else np.vstack([profile.outer.points_mm, completion.points])
    px = view.mm_to_px(extent)
    margin = OVERLAY_MARGIN_MM * view.px_per_mm
    h_img, w_img = view.image.shape[:2]
    x0, y0 = np.maximum(np.floor(px.min(axis=0) - margin).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(px.max(axis=0) + margin).astype(int), [w_img, h_img])
    k = max(1.0, OVERLAY_WIDTH_PX / max(x1 - x0, 1))
    crop = cv2.resize(view.image[y0:y1, x0:x1], None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    mask = cv2.resize(seg.mask[y0:y1, x0:x1].astype(np.uint8), (crop.shape[1], crop.shape[0]),
                      interpolation=cv2.INTER_NEAREST).astype(bool)

    def to_px(points_mm: np.ndarray) -> np.ndarray:
        return np.round((view.mm_to_px(points_mm) - [x0, y0]) * k).astype(np.int32)

    tint = crop.copy()
    tint[mask] = (0.6 * tint[mask] + 0.4 * np.array([255, 140, 0])).astype(np.uint8)
    out = cv2.addWeighted(tint, 0.6, crop, 0.4, 0)
    thin, thick = max(1, int(round(k * 0.6))), max(2, int(round(k * 1.2)))
    cv2.polylines(out, [to_px(profile.outer.points_mm)], True, (255, 90, 0), thin, cv2.LINE_AA)
    for h in profile.holes:
        color = (0, 200, 255) if h.glare_suspect else (60, 220, 60)
        cv2.polylines(out, [to_px(h.contour.points_mm)], True, color, thin, cv2.LINE_AA)
    for contour in (footprint.outer, *(h.contour for h in footprint.holes)):
        cv2.polylines(out, [to_px(contour.points_mm)], True, (255, 230, 0), thin, cv2.LINE_AA)
    if completion is not None:
        closed = np.vstack([completion.points, completion.points[:1]])
        for run in completion.runs:
            cv2.polylines(out, [to_px(closed[run.start:run.end + 2])], False, PROVENANCE_COLOURS[run.status], thick,
                          cv2.LINE_AA)
        for hole in completion.inferred_holes:
            c = to_px(np.array([hole.center]))[0]
            cv2.circle(out, tuple(int(v) for v in c), int(round(hole.radius * view.px_per_mm * k)),
                       PROVENANCE_COLOURS["INFERRED"], thick, cv2.LINE_AA)
        axis = completion.axis
        ends = to_px(np.array([np.asarray(axis.point) + t * axis.direction for t in (-60.0, 60.0)])).astype(float)
        for t in np.arange(0.0, 1.0, 0.03):
            a, b = ends[0] + (ends[1] - ends[0]) * t, ends[0] + (ends[1] - ends[0]) * min(t + 0.015, 1.0)
            cv2.line(out, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), (90, 90, 90), thin,
                     cv2.LINE_AA)
    return out


def _reconstruction_report(recon: Reconstruction) -> dict:
    interp, c = recon.interpretation, recon.completion
    completion = None
    if c is not None:
        closed = np.vstack([c.points, c.points[:1]])
        completion = {
            "axis": c.axis.axis_id, "added_area_mm2": round(c.added_area_mm2, 2),
            "inferred_u_mm_2sigma": round(c.inferred_uncertainty_mm(), 4),
            "extent_mm": _extent(c.points),
            "regions": [{"area_mm2": round(r.area_mm2, 2), "filled": r.filled, "reason": r.reason} for r in c.regions],
            "inferred_holes": [{"from": h.source_hole_id, "center_mm": [round(v, 3) for v in h.center],
                                "diameter_mm": round(2 * h.radius, 3)} for h in c.inferred_holes],
            "hole_checks": [{"hole": h.hole_id, "mirror_partner": h.partner_id,
                             "center_distance_mm": round(h.center_distance_mm, 4),
                             "diameter_difference_mm": round(h.diameter_difference_mm, 4)} for h in c.hole_checks],
            "asymmetric_holes": list(c.asymmetric_holes),
            "runs": [{"status": r.status, "source": r.source, "length_mm": round(float(np.linalg.norm(
                np.diff(closed[r.start:r.end + 2], axis=0), axis=1).sum()), 2)} for r in c.runs],
        }
    return {
        "interpretation": {"method": interp.method, "is_ai": interp.is_ai, "latency_s": round(interp.latency_s, 3),
                           "cost_usd": round(interp.cost_usd, 6), "detail": interp.detail,
                           "fallback_reason": recon.fallback_reason, "analysis": interp.analysis.model_dump()},
        "verification": [n.__dict__ for n in recon.verified.notes],
        "segments": [{"id": s.seg_id, "kind": s.kind, "length_mm": round(s.length_mm, 2), "pieces": s.pieces,
                      "fit_rms_mm": round(s.fit_rms_mm, 4)} for s in recon.segmented.segments],
        "axes": [{"id": a.axis_id, "angle_deg": round(a.angle_deg, 4), "support": round(a.support, 4),
                  "inlier_rms_mm": round(a.inlier_rms_mm, 4), "holes_matched": a.hole_matches,
                  "holes_contradicting": a.hole_mismatches, "angle_sigma_deg": a.angle_sigma_deg,
                  "offset_sigma_mm": a.offset_sigma_mm, "offset_ambiguity_mm": a.offset_ambiguity_mm,
                  "sources": list(a.sources)} for a in recon.axes],
        "completion": completion,
    }


def _extent(points_mm: np.ndarray) -> list[float]:
    return [round(float(v), 3) for v in np.ptp(points_mm, axis=0)]


async def photo_to_stl(photo: Path, out_dir: Path, thickness_mm: float, segmenter: Segmenter, *,
                       bar_x_mm: float | None = None, bar_y_mm: float | None = None,
                       thickness_uncertainty_mm: float = CALIPER_UNCERTAINTY_MM, job_id: str | None = None,
                       focal_35mm: float | None = None, interpreter=None) -> dict:
    """``focal_35mm`` is the photo's EXIF focal length (35 mm equivalent). When it isn't given, it's read from the
    photo file itself; uploads pass it explicitly because they're re-encoded without metadata.

    ``interpreter`` reads the part for the reconstruction: ``SparkInterpreter`` (Muse Spark) or, by default, the
    ``GeometricInterpreter`` rule (not AI)."""
    interpreter = interpreter or GeometricInterpreter()
    timings: dict[str, float] = {}

    def lap(name: str, t0: float) -> float:
        timings[name] = round(time.perf_counter() - t0, 3)
        return time.perf_counter()

    t = time.perf_counter()
    image = cv2.imread(str(photo), cv2.IMREAD_COLOR)  # applies EXIF orientation
    if image is None:
        raise ReforgeError("IMAGE_INVALID", f"Could not read {photo.name} as an image.")
    if focal_35mm is None:
        focal_35mm = focal_35mm_from_exif(photo.read_bytes())
    t = lap("load", t)
    cal = calibrate(image, bar_x_mm=bar_x_mm, bar_y_mm=bar_y_mm)
    view = rectify(image, cal)
    t = lap("calibrate_rectify", t)
    seg = await segmenter.segment(view)
    t = lap("segment", t)
    profile = refine_profile(view, seg.mask)
    t = lap("refine", t)
    if profile.trace_share is not None and profile.trace_share < MIN_TRACE_SHARE:
        raise ReforgeError(
            "TRACE_PARTIAL",
            f"The traced outline covers only {profile.trace_share:.0%} of what's on the mat, so it's a fragment of a "
            "larger or multi-coloured object, not a part outline. No model was built.",
            "Photograph one flat, single-colour part alone in the mat's free zone.")
    pose = estimate_pose(cal, focal_35mm)
    height = correct_height(profile, pose, thickness_mm, round_max_deviation_mm=ROUND_HOLE_MAX_DEVIATION_MM)
    t = lap("pose_height", t)
    recon = await reconstruct(view, height.profile, interpreter, thickness_mm=thickness_mm)
    t = lap("interpret_reconstruct", t)
    analysis = recon.interpretation.analysis
    if analysis.family != "extruded_profile":
        # Building a flat extrusion of a pipe, say, would be a confident-looking hallucination: refuse instead.
        raise ReforgeError(
            "FAMILY_UNSUPPORTED",
            f"{recon.interpretation.method} reads this as {analysis.object_name!r} "
            f"({analysis.family.replace('_', ' ')}): {analysis.family_reason}"[:400],
            "RE-FORGE rebuilds flat parts of uniform thickness, photographed from above on the mat. No model was "
            "built.")
    thickness = Param(value=thickness_mm, status=Status.MEASURED, uncertainty_mm=thickness_uncertainty_mm,
                      evidence=(Evidence(kind="caliper", detail="entered by the user"),))
    spec, notes = profile_to_spec(height.profile, thickness, recon.completion)
    part = build_part(spec)
    validation = summarize(validate_part(part, spec))
    t = lap("spec_build_validate", t)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_stl(part, out_dir / "model.stl")
    (out_dir / "model.scad").write_text(emit_scad(spec, job_id), encoding="utf-8")
    (out_dir / "spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    cv2.imwrite(str(out_dir / "overlay.png"), _overlay(view, seg, profile, height.profile, recon.completion))
    cv2.imwrite(str(out_dir / "setofmark.png"), recon.marked_bgr)
    lap("write", t)

    mesh = part.to_trimesh()
    (bx0, by0, bz0), (bx1, by1, bz1) = mesh.bounds
    report = {
        "job_id": job_id,
        "photo": photo.name,
        "milestone": "D4: measured geometry, height-corrected; mirror reconstruction of a broken part",
        "calibration": {"page": cal.page, "markers": len(cal.marker_ids), "fit_rms_mm": round(cal.rms_mm, 4),
                        "corner_bias_px": round(cal.corner_bias_px, 3),
                        "loo_rms_mm": None if cal.loo_rms_mm is None else round(cal.loo_rms_mm, 4),
                        "px_per_mm": round(cal.px_per_mm, 2), "perspective_ratio": round(cal.perspective_ratio, 3),
                        "scale_correction": cal.scale_correction,
                        "warnings": [w.__dict__ for w in cal.warnings]},
        "segmentation": {"method": seg.method, "is_ai": seg.is_ai, "confidence": seg.confidence,
                         "latency_s": round(seg.latency_s, 3), "cost_usd": seg.cost_usd, "detail": seg.detail},
        "refinement": {"refined": profile.refined, "contrast_delta_e": round(profile.contrast_delta_e, 1),
                       "edge_sigma_mm": None if profile.edge_sigma_mm is None else round(profile.edge_sigma_mm, 4),
                       "band_mm": round(profile.band_mm, 3),
                       "coarse_shift_mean_mm": round(profile.coarse_shift_mean_mm, 4),
                       "coarse_shift_max_mm": round(profile.coarse_shift_max_mm, 4),
                       "warnings": [w.__dict__ for w in profile.warnings]},
        "pose": {"focal_source": pose.focal_source, "focal_px": round(pose.focal_px, 1),
                 "focal_35mm": round(pose.focal_px / np.hypot(*cal.image_size) * FULL_FRAME_DIAGONAL_MM, 1),
                 "focal_rel_sigma": round(pose.focal_rel_sigma, 4), "exif_focal_35mm": pose.exif_focal_35mm,
                 "camera_height_mm": round(pose.height_mm, 1), "camera_height_sigma_mm": round(pose.height_sigma_mm, 1),
                 "nadir_mm": [round(v, 1) for v in pose.nadir_mm], "nadir_sigma_mm": round(pose.nadir_sigma_mm, 1),
                 "warnings": [w.__dict__ for w in pose.warnings]},
        "height_correction": {"magnification": round(height.magnification, 6),
                              "photographed_extent_mm": _extent(profile.outer.points_mm),
                              "footprint_extent_mm": _extent(height.profile.outer.points_mm),
                              "max_shift_mm": round(height.max_shift_mm, 3),
                              "u_persp_mm_2sigma": round(height.u_persp_mm, 3),
                              "occlusion_bound_mm": round(height.occlusion_bound_mm, 3)},
        "part": {"overall_mm": [round(bx1 - bx0, 3), round(by1 - by0, 3), round(bz1 - bz0, 3)],
                 "overall_status": Status.INFERRED.value if recon.completion else Status.OBSERVED.value,
                 "holes": [{"id": h.id, "kind": h.kind,
                            "status": (h.diameter.status if isinstance(h, CircleHole) else h.status).value,
                            **({"diameter_mm": round(h.diameter.value, 3),
                                "center_mm": [round(h.center_x.value, 3), round(h.center_y.value, 3)]}
                               if isinstance(h, CircleHole) else {"source": h.source})} for h in spec.holes],
                 "excluded_candidates": notes, "unresolved": spec.unresolved()},
        "validation": validation,
        "timings_s": timings,
        "reconstruction": _reconstruction_report(recon),
        "outputs": ["model.stl", "model.scad", "spec.json", "overlay.png", "setofmark.png", "report.json"],
        "disclaimer": "A reconstruction, not a verified replacement part. Not for safety-critical use.",
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
