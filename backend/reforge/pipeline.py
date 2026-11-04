"""The pipeline: photo → calibration → segmentation → refined profile → height correction → interpretation and mirror
reconstruction → PartSpec → solid → STL, OpenSCAD and report.

Every stage is timed for real, and reported as it starts and ends through ``progress`` (the UI's stage list shows
exactly these events, never a simulated progress). Every measured quantity is reported with its evidence and, from
the Confidence Engine (``reforge.spec.confidence``), a modelled 2σ uncertainty.

CPU-heavy stages run in a worker thread so the server keeps answering (status polls, health) during a job.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from reforge.cad.build import build_part, write_stl
from reforge.cad.flat import emit_dxf, emit_svg
from reforge.cad.scad import emit_scad
from reforge.capture.calibration import (
    RULER_READING_REL,
    RULER_TILT_REL,
    RectifiedView,
    calibrate,
    rectify,
    ruler_calibration,
)
from reforge.capture.pose import FULL_FRAME_DIAGONAL_MM, estimate_pose, focal_35mm_from_exif, ruler_pose
from reforge.errors import ReforgeError
from reforge.geometry.circle import fit_circle
from reforge.geometry.completion import Completion
from reforge.geometry.height import HeightCorrection, correct_height
from reforge.reasoning.interpret import GeometricInterpreter
from reforge.reasoning.reconstruct import Reconstruction, reconstruct
from reforge.spec.confidence import (
    CALIPER_U_MM,
    MODEL_NOTE,
    ErrorBudget,
    Estimate,
    Term,
    build_budget,
    min_rect_mm,
    with_mirror,
)
from reforge.spec.partspec import (
    MAX_POINTS,
    MIN_WALL_MM,
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

CALIPER_UNCERTAINTY_MM = CALIPER_U_MM  # default instrument + reading, 2σ; the user can override
MIN_TRACE_SHARE = 0.2  # below this the trace is a fragment of something else: refuse before any model call
ROUND_HOLE_MAX_DEVIATION_MM = 0.12
OVERLAY_MARGIN_MM = 8.0
# The stages, in order, as reported to ``progress`` and in ``timings_s``.
STAGES = ("load", "calibrate_rectify", "segment", "refine", "pose_height", "interpret_reconstruct",
          "spec_build_validate", "write")
Progress = Callable[[str, str, float | None], None]  # (stage, "running" | "done", seconds when done)


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


def _buildable(outline: Outline, holes: list[CircleHole | PolygonHole]
               ) -> tuple[list[CircleHole | PolygonHole], list[dict]]:
    """The holes a solid can be built with: inside the outline with ``MIN_WALL_MM`` of wall, and that far apart.
    The others are left out and reported UNCERTAIN, rather than failing the whole spec. Larger holes are kept first."""
    body = Polygon(outline.points).buffer(0).buffer(-MIN_WALL_MM, join_style="mitre")
    kept: list[CircleHole | PolygonHole] = []
    notes: list[dict] = []
    for hole in sorted(holes, key=lambda h: -h.disc().area):
        disc = hole.disc()
        if not body.contains(disc):
            reason = f"less than {MIN_WALL_MM} mm of wall to the outline: left out; check the photo"
        elif any(disc.distance(k.disc()) < MIN_WALL_MM for k in kept):
            reason = f"less than {MIN_WALL_MM} mm from another hole: left out; check the photo"
        else:
            kept.append(hole)
            continue
        notes.append({"hole": hole.id, "excluded": True, "status": Status.UNCERTAIN.value, "reason": reason})
    order = {h.id: i for i, h in enumerate(holes)}
    return sorted(kept, key=lambda h: order[h.id]), notes


def profile_to_spec(profile: RefinedProfile, thickness: Param, completion: Completion | None = None,
                    budget: ErrorBudget | None = None) -> tuple[PartSpec, list[dict], dict[str, dict[str, Estimate]]]:
    """The footprint as a PartSpec in the model frame, plus notes on anything left out.

    With a ``completion``, the outline is the mirror-completed one with its provenance runs, and mirrored holes that
    land in the added material are included as INFERRED. With a ``budget``, every hole parameter carries its 2σ
    uncertainty (an INFERRED hole adds the mirror's own to its source hole's), and the third value holds each built
    hole's estimates, term by term, for the report."""
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
    source_u: dict[str, tuple[Estimate, Estimate]] = {}  # profile hole id → (diameter, centre) estimates
    estimates: dict[str, dict[str, Estimate]] = {}  # spec hole id → estimates

    def u(estimate: Estimate | None) -> float | None:
        return None if estimate is None else round(estimate.u_mm, 4)

    for cand in profile.holes:
        if cand.doubt:
            notes.append({"hole": cand.hole_id, "excluded": True, "status": Status.UNCERTAIN.value,
                          "reason": cand.doubt})
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
            d_est = budget.diameter(fit.diameter, fit.rms, fit.n_points) if budget else None
            c_est = budget.length(float(np.hypot(cx, cy))) if budget else None
            if d_est is not None and c_est is not None:
                source_u[cand.hole_id] = (d_est, c_est)
                estimates[hid] = {"diameter": d_est, "center": c_est}
            holes.append(CircleHole(
                id=hid, center_x=Param(value=cx, status=Status.OBSERVED, uncertainty_mm=u(c_est), evidence=ev),
                center_y=Param(value=cy, status=Status.OBSERVED, uncertainty_mm=u(c_est), evidence=ev),
                diameter=Param(value=fit.diameter, status=Status.OBSERVED, uncertainty_mm=u(d_est), evidence=ev)))
        else:
            hp = np.asarray(orient(Polygon(mat_to_model(cand.contour.points_mm, origin)), 1.0).exterior.coords)[:-1]
            holes.append(PolygonHole(id=hid, points=tuple(map(tuple, _simplify(hp))), status=Status.OBSERVED,
                                     source=f"traced edge, not round (max dev {fit.max_deviation:.2f} mm); {agree}"))
    for inferred in completion.inferred_holes if completion is not None else ():
        (cx, cy), = mat_to_model(np.array([inferred.center]), origin)
        radius = inferred.radius + sigma**2 / (2 * inferred.radius)
        ev = (Evidence(kind="mirror", detail=f"mirror of {inferred.source_hole_id} about {completion.axis.axis_id} "
                                             f"(support {completion.axis.support:.0%}); lands in the added material"),)
        d_est = c_est = None
        if inferred.source_hole_id in source_u:
            mirror = completion.inferred_uncertainty_mm()
            d_src, c_src = source_u[inferred.source_hole_id]
            d_est = with_mirror(d_src, mirror, completion.axis.axis_id)
            c_est = with_mirror(c_src, mirror, completion.axis.axis_id)
            estimates[f"H{len(holes)}"] = {"diameter": d_est, "center": c_est}
        holes.append(CircleHole(
            id=f"H{len(holes)}", center_x=Param(value=cx, status=Status.INFERRED, uncertainty_mm=u(c_est), evidence=ev),
            center_y=Param(value=cy, status=Status.INFERRED, uncertainty_mm=u(c_est), evidence=ev),
            diameter=Param(value=2 * radius, status=Status.INFERRED, uncertainty_mm=u(d_est), evidence=ev)))
    holes, dropped = _buildable(outline, holes)
    notes += dropped
    try:
        spec = PartSpec(outline=outline, holes=tuple(holes), thickness=thickness)
    except ValueError as exc:  # pydantic ValidationError subclasses ValueError
        raise ReforgeError("SPEC_INVALID", str(exc)[:600], "Check the photo and the segmentation.") from exc
    return spec, notes, estimates


# BGR, matching the UI's evidence palette: blue measured from the photo, ember rebuilt, red uncertain.
PROVENANCE_COLOURS = {"OBSERVED": (235, 99, 37), "INFERRED": (12, 65, 194), "UNCERTAIN": (28, 28, 185)}
DOUBTED_HOLE_COLOUR = (0, 170, 245)  # amber: a hole candidate left out
AXIS_COLOUR = (70, 60, 50)
HALO_COLOUR = (255, 255, 255)


OVERLAY_WIDTH_PX = 1400


def _overlay(view: RectifiedView, profile: RefinedProfile, footprint: RefinedProfile,
             completion: Completion | None = None) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float]]:
    """The rectified photo of the part, cropped and enlarged to about ``OVERLAY_WIDTH_PX`` (so lines stay sharp), and
    the same crop with what was measured drawn on it. Both share one framing, so the UI can compare them.

    Drawn: the rebuilt material (ember hatch); the photographed outline (thin white); the built footprint, which
    is height-corrected and so sits just inside the photographed outline, coloured by provenance (blue measured from
    the photo, ember rebuilt by the mirror, red uncertain), with a white halo for contrast on dark parts; the holes
    (blue, ember when mirrored, amber when left out); and the mirror axis, dashed."""
    extent = profile.outer.points_mm if completion is None else np.vstack([profile.outer.points_mm, completion.points])
    px = view.mm_to_px(extent)
    margin = OVERLAY_MARGIN_MM * view.px_per_mm
    h_img, w_img = view.image.shape[:2]
    x0, y0 = np.maximum(np.floor(px.min(axis=0) - margin).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(px.max(axis=0) + margin).astype(int), [w_img, h_img])
    k = max(1.0, OVERLAY_WIDTH_PX / max(x1 - x0, 1))
    crop = cv2.resize(view.image[y0:y1, x0:x1], None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)

    def to_px(points_mm: np.ndarray) -> np.ndarray:
        return np.round((view.mm_to_px(points_mm) - [x0, y0]) * k).astype(np.int32)

    out = crop.copy()
    if completion is not None:  # the rebuilt material: ember, translucent and hatched
        layer = out.copy()
        hatch = np.zeros(out.shape[:2], np.uint8)
        step = max(10, out.shape[1] // 90)
        for x in range(-out.shape[0], out.shape[1], step):
            cv2.line(hatch, (x, out.shape[0]), (x + out.shape[0], 0), 255, max(2, step // 4), cv2.LINE_AA)
        for region in (r for r in completion.regions if r.filled):
            area = np.zeros(out.shape[:2], np.uint8)
            cv2.fillPoly(area, [to_px(np.asarray(region.polygon.exterior.coords))], 255, cv2.LINE_AA)
            layer[area > 0] = PROVENANCE_COLOURS["INFERRED"]
            out = np.where(((area > 0) & (hatch > 0))[..., None], layer, out)
            out = np.where((area > 0)[..., None], cv2.addWeighted(out, 0.72, layer, 0.28, 0), out)
    thin = max(2, OVERLAY_WIDTH_PX // 700)
    thick = max(3, OVERLAY_WIDTH_PX // 360)
    halo = thick + max(3, OVERLAY_WIDTH_PX // 500)

    def line(points: np.ndarray, colour: tuple[int, int, int], closed: bool = True, width: int = thick) -> None:
        cv2.polylines(out, [points], closed, HALO_COLOUR, width + (halo - thick), cv2.LINE_AA)
        cv2.polylines(out, [points], closed, colour, width, cv2.LINE_AA)

    cv2.polylines(out, [to_px(profile.outer.points_mm)], True, HALO_COLOUR, thin, cv2.LINE_AA)
    for h in profile.holes:
        if h.doubt:
            pts = to_px(h.contour.points_mm)
            for i in range(0, len(pts), 6):  # dotted: left out of the model
                cv2.polylines(out, [pts[i:i + 3]], False, DOUBTED_HOLE_COLOUR, thick, cv2.LINE_AA)
    if completion is None:
        line(to_px(footprint.outer.points_mm), PROVENANCE_COLOURS["OBSERVED"])
    else:
        closed = np.vstack([completion.points, completion.points[:1]])
        for run in completion.runs:
            line(to_px(closed[run.start:run.end + 2]), PROVENANCE_COLOURS[run.status], closed=False)
        for hole in completion.inferred_holes:
            c = to_px(np.array([hole.center]))[0]
            r = int(round(hole.radius * view.px_per_mm * k))
            cv2.circle(out, tuple(int(v) for v in c), r, (238, 240, 242), -1, cv2.LINE_AA)  # a hole: see-through
            cv2.circle(out, tuple(int(v) for v in c), r, HALO_COLOUR, halo, cv2.LINE_AA)
            cv2.circle(out, tuple(int(v) for v in c), r, PROVENANCE_COLOURS["INFERRED"], thick, cv2.LINE_AA)
        axis = completion.axis
        ends = to_px(np.array([np.asarray(axis.point) + t * axis.direction for t in (-60.0, 60.0)])).astype(float)
        for t in np.arange(0.0, 1.0, 0.03):
            a, b = ends[0] + (ends[1] - ends[0]) * t, ends[0] + (ends[1] - ends[0]) * min(t + 0.015, 1.0)
            cv2.line(out, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), AXIS_COLOUR, thick,
                     cv2.LINE_AA)
    for h in footprint.holes:
        if not h.doubt:
            line(to_px(h.contour.points_mm), PROVENANCE_COLOURS["OBSERVED"])
    return crop, out, (float(x0), float(y0), float(k))


def _texture(view: RectifiedView, crop: np.ndarray, frame: tuple[float, float, float], footprint: RefinedProfile,
             completion: Completion | None, seg: Segmentation) -> dict:
    """How ``photo.jpg`` maps onto the model, for a photo-textured 3D preview: pixel (u, v) = u0 + a·x + b·y, v0 +
    c·x + d·y for a model-frame point (x, y) in mm. Also the photographed footprint in the model frame (the rebuilt
    material is what lies outside it) and the part's median colour, measured on the photo."""
    x0, y0, k = frame
    outer = completion.points if completion is not None else footprint.outer.points_mm
    ox, oy = (outer.min(axis=0) + outer.max(axis=0)) / 2  # the model origin, as in profile_to_spec
    s = view.px_per_mm
    vx, vy = view.origin_mm
    u0 = k * ((ox - vx) * s - x0)
    v0 = k * ((oy - vy) * s - y0)
    photographed = Polygon(mat_to_model(footprint.outer.points_mm, (ox, oy))).buffer(0).simplify(0.05)
    inside = cv2.erode(seg.mask.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    colour = np.median(view.image[inside], axis=0) if inside.any() else np.array([180, 180, 180])
    b, g, r = (int(round(c)) for c in colour)
    # The texture for the 3D preview: the photo where the part was photographed, ember wherever it wasn't (the rebuilt
    # material), decided per pixel against the photographed outline, so no triangle can smear one into the other.
    ring = np.round((view.mm_to_px(footprint.outer.points_mm) - [x0, y0]) * k).astype(np.int32)
    seen = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(seen, [ring], 255, cv2.LINE_AA)
    ember = np.zeros_like(crop)
    ember[:] = (137, 176, 242)  # BGR of the UI's rebuilt tint
    alpha = (seen.astype(np.float32) / 255.0)[..., None]
    texture_image = np.clip(crop * alpha + ember * (1 - alpha), 0, 255).astype(np.uint8)
    return {"image": "texture.jpg", "texture_bgr": texture_image, "size_px": [int(crop.shape[1]), int(crop.shape[0])],
            "u": [round(u0, 3), round(k * s, 6), 0.0], "v": [round(v0, 3), 0.0, round(-k * s, 6)],
            "photographed_outline_mm": [[round(float(x), 3), round(float(y), 3)]
                                        for x, y in np.asarray(photographed.exterior.coords)[:-1]],
            "colour_hex": f"#{r:02x}{g:02x}{b:02x}"}


def _reconstruction_report(recon: Reconstruction) -> dict:
    interp, c = recon.interpretation, recon.completion
    completion = None
    if c is not None:
        closed = np.vstack([c.points, c.points[:1]])
        completion = {
            "axis": c.axis.axis_id, "added_area_mm2": round(c.added_area_mm2, 2),
            "inferred_outline_mm": round(c.inferred_length_mm, 2), "confirmed_mm": round(c.confirmed_mm, 2),
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
                  "inlier_rms_mm": round(a.inlier_rms_mm, 4), "outline_confirming_mm": round(a.matched_mm, 1),
                  "holes_matched": a.hole_matches,
                  "holes_contradicting": a.hole_mismatches, "angle_sigma_deg": a.angle_sigma_deg,
                  "offset_sigma_mm": a.offset_sigma_mm, "offset_ambiguity_mm": a.offset_ambiguity_mm,
                  "sources": list(a.sources)} for a in recon.axes],
        "completion": completion,
    }


def _extent(points_mm: np.ndarray) -> list[float]:
    return [round(float(v), 3) for v in np.ptp(points_mm, axis=0)]


def _dimension(dim_id: str, label: str, value: float, status: str, estimate: Estimate | None,
               u_mm: float | None = None) -> dict:
    u = estimate.u_mm if estimate is not None else u_mm
    return {"id": dim_id, "label": label, "value_mm": round(value, 3), "status": status,
            "u_mm": None if u is None else round(u, 3),
            "dominant": estimate.dominant if estimate is not None else None,
            "terms": [t.to_dict() for t in estimate.terms] if estimate is not None else []}


def _confidence_report(spec: PartSpec, budget: ErrorBudget, completion: Completion | None,
                       estimates: dict[str, dict[str, Estimate]]) -> tuple[dict, dict]:
    """The part's caliper-style size (smallest enclosing rectangle) and every dimension with its 2σ estimate."""
    length, width, angle = min_rect_mm(np.asarray(spec.outline.points))
    status = Status.INFERRED.value if completion is not None else Status.OBSERVED.value

    def size(value: float) -> Estimate:
        est = budget.length(value)
        return with_mirror(est, completion.inferred_uncertainty_mm(), completion.axis.axis_id) if completion else est

    dims = [_dimension("length", "Length", length, status, size(length)),
            _dimension("width", "Width", width, status, size(width)),
            _dimension("thickness", "Thickness", spec.thickness.value, spec.thickness.status.value,
                       Estimate((Term("caliper", (spec.thickness.uncertainty_mm or CALIPER_U_MM) / 2,
                                      "your caliper reading (instrument + reading)"),)))]
    for hole in spec.holes:
        if isinstance(hole, CircleHole):
            est = estimates.get(hole.id, {})
            dims.append(_dimension(f"{hole.id}.diameter", f"Hole {hole.id} Ø", hole.diameter.value,
                                   hole.diameter.status.value, est.get("diameter"), hole.diameter.uncertainty_mm))
            dims.append(_dimension(f"{hole.id}.position", f"Hole {hole.id} position",
                                   float(np.hypot(hole.center_x.value, hole.center_y.value)),
                                   hole.center_x.status.value, est.get("center"), hole.center_x.uncertainty_mm))
        else:
            dims.append({"id": f"{hole.id}.shape", "label": f"Hole {hole.id} (traced shape)", "value_mm": None,
                         "status": hole.status.value, "u_mm": None, "dominant": None, "terms": [],
                         "note": "a non-round hole is built as traced; its edge carries the outline's uncertainty"})
    size_mm = {"length": round(length, 3), "width": round(width, 3), "thickness": round(spec.thickness.value, 3),
               "angle_deg": round(angle, 2), "basis": "smallest rectangle around the built outline (caliper-style)"}
    return size_mm, {"note": MODEL_NOTE, "budget": budget.to_dict(), "dimensions": dims}


async def photo_to_stl(photo: Path, out_dir: Path, thickness_mm: float, segmenter: Segmenter, *,
                       bar_x_mm: float | None = None, bar_y_mm: float | None = None,
                       thickness_uncertainty_mm: float = CALIPER_UNCERTAINTY_MM, job_id: str | None = None,
                       focal_35mm: float | None = None, interpreter=None, progress: Progress | None = None,
                       known_length_mm: float | None = None) -> dict:
    """``focal_35mm`` is the photo's EXIF focal length (35 mm equivalent). When it isn't given, it's read from the
    photo file itself; uploads pass it explicitly because they're re-encoded without metadata.

    ``interpreter`` reads the part for the reconstruction: ``SparkInterpreter`` (Muse Spark) or, by default, the
    ``GeometricInterpreter`` rule (not AI). ``progress`` is called as each of ``STAGES`` starts and ends.

    ``known_length_mm`` is ruler mode: no mat. The photo must show the part from above on a plain background, and
    the value must be the part's longest side in mm, measured with a ruler or caliper. The outline's longest
    pixel side carries that length; tilt is assumed within ~10° of top-down and covered by a widened uncertainty.
    Ruler mode never attempts the markers, even if a mat happens to be visible."""
    interpreter = interpreter or GeometricInterpreter()
    timings: dict[str, float] = {}
    current: dict[str, object] = {}

    def begin(name: str) -> None:
        current.update(name=name, t0=time.perf_counter())
        if progress is not None:
            progress(name, "running", None)

    def end() -> None:
        name = str(current["name"])
        timings[name] = round(time.perf_counter() - float(current["t0"]), 3)
        if progress is not None:
            progress(name, "done", timings[name])

    begin("load")
    image = await asyncio.to_thread(cv2.imread, str(photo), cv2.IMREAD_COLOR)  # applies EXIF orientation
    if image is None:
        raise ReforgeError("IMAGE_INVALID", f"Could not read {photo.name} as an image.")
    if focal_35mm is None:
        focal_35mm = focal_35mm_from_exif(photo.read_bytes())
    end()
    ruler = known_length_mm is not None
    if ruler and (not np.isfinite(known_length_mm) or known_length_mm <= 0):
        raise ReforgeError("RULER_LENGTH_INVALID", f"Enter the measured length in mm (got {known_length_mm}).",
                           "Ruler mode needs the part's longest side, measured with a ruler or caliper.")
    if ruler:
        # Ruler mode: segment first in pixels (the outline's longest side carries the entered length), then scale.
        # The segmentation mask is scale-free; only the morphology kernels assume a scale, and refinement re-derives
        # every boundary with the true one.
        begin("segment")
        seg = await segmenter.segment(RectifiedView(image=image, px_per_mm=1.0, origin_mm=(0.0, 0.0)))
        end()
        begin("calibrate_rectify")

        def _scale() -> tuple:
            ys, xs = np.nonzero(seg.mask)
            span_px = float(max(xs.max() - xs.min(), ys.max() - ys.min())) if len(xs) else 0.0
            cal = ruler_calibration((image.shape[1], image.shape[0]), span_px / known_length_mm, known_length_mm)
            return cal, RectifiedView(image=image, px_per_mm=cal.px_per_mm, origin_mm=(0.0, 0.0))

        cal, view = await asyncio.to_thread(_scale)
        end()
    else:
        begin("calibrate_rectify")

        def _calibrate() -> tuple:
            cal = calibrate(image, bar_x_mm=bar_x_mm, bar_y_mm=bar_y_mm)
            return cal, rectify(image, cal)

        cal, view = await asyncio.to_thread(_calibrate)
        end()
        begin("segment")
        seg = await segmenter.segment(view)
        end()
    begin("refine")
    profile = await asyncio.to_thread(refine_profile, view, seg.mask, on_mat=not ruler)
    end()
    if profile.trace_share is not None and profile.trace_share < MIN_TRACE_SHARE:
        where = "on the mat" if not ruler else "in the photo"
        raise ReforgeError(
            "TRACE_PARTIAL",
            f"The traced outline covers only {profile.trace_share:.0%} of what's {where}, so it's a fragment of a "
            "larger or multi-coloured object, not a part outline. No model was built.",
            "Photograph one flat, single-colour part alone in the mat's free zone."
            if not ruler else "Photograph one flat, single-colour part alone on a plain background.")
    begin("pose_height")

    def _pose_height() -> tuple:
        pose = estimate_pose(cal, focal_35mm)
        return pose, correct_height(profile, pose, thickness_mm, round_max_deviation_mm=ROUND_HOLE_MAX_DEVIATION_MM)

    def _ruler_pose_height() -> tuple:
        # No height correction: the scale already lives at the part's top face, and for a flat part that face IS
        # the footprint (up to tilt). The unknown tilt and the thickness parallax go into the uncertainty instead.
        pts = profile.outer.points_mm
        centre = (float(pts[:, 0].mean()), float(pts[:, 1].mean()))
        extent = float(max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])))
        pose = ruler_pose(focal_35mm, cal.image_size, cal.px_per_mm, centre, extent, thickness_mm)
        radial = float(np.hypot(pts[:, 0] - centre[0], pts[:, 1] - centre[1]).max())
        parallax = thickness_mm / pose.height_mm * radial
        u_2sigma = 2.0 * float(np.hypot(RULER_TILT_REL * extent, parallax))
        height = HeightCorrection(profile=profile, magnification=1.0, max_shift_mm=0.0, u_persp_mm=u_2sigma,
                                  occlusion_bound_mm=float(parallax))
        return pose, height

    pose, height = await asyncio.to_thread(_ruler_pose_height if ruler else _pose_height)
    end()
    begin("interpret_reconstruct")
    recon = await reconstruct(view, height.profile, interpreter, thickness_mm=thickness_mm)
    end()
    analysis = recon.interpretation.analysis
    if analysis.family != "extruded_profile":
        # Building a flat extrusion of a pipe, say, would be a confident-looking hallucination: refuse instead.
        raise ReforgeError(
            "FAMILY_UNSUPPORTED",
            f"{recon.interpretation.method} reads this as {analysis.object_name!r} "
            f"({analysis.family.replace('_', ' ')}): {analysis.family_reason}"[:400],
            "RE-FORGE rebuilds flat parts of uniform thickness, photographed from above on the mat. No model was "
            "built." if not ruler else
            "RE-FORGE rebuilds flat parts of uniform thickness, photographed from above. No model was built.")
    begin("spec_build_validate")
    thickness = Param(value=thickness_mm, status=Status.MEASURED, uncertainty_mm=thickness_uncertainty_mm,
                      evidence=(Evidence(kind="caliper", detail="entered by the user"),))
    budget = build_budget(fit_rms_mm=cal.rms_mm, loo_rms_mm=cal.loo_rms_mm,
                          bars_checked=(bar_x_mm is not None) + (bar_y_mm is not None), px_per_mm=cal.px_per_mm,
                          refined=profile.refined, u_persp_2sigma_mm=height.u_persp_mm,
                          ruler_reading_rel=RULER_READING_REL if ruler else None,
                          persp_basis="top-down assumed, no mat: tilt, thickness parallax and pose in one term"
                          if ruler else None)

    def _build() -> tuple:
        spec, notes, estimates = profile_to_spec(height.profile, thickness, recon.completion, budget)
        part = build_part(spec)
        return spec, notes, estimates, part, summarize(validate_part(part, spec))

    spec, notes, estimates, part, validation = await asyncio.to_thread(_build)
    end()
    begin("write")

    def _write() -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_stl(part, out_dir / "model.stl")
        (out_dir / "model.scad").write_text(emit_scad(spec, job_id), encoding="utf-8")
        (out_dir / "model.dxf").write_text(emit_dxf(spec, job_id), encoding="utf-8")
        (out_dir / "model.svg").write_text(emit_svg(spec, job_id), encoding="utf-8")
        (out_dir / "spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        crop, overlay, frame = _overlay(view, profile, height.profile, recon.completion)
        texture.update(_texture(view, crop, frame, height.profile, recon.completion, seg))
        cv2.imwrite(str(out_dir / "texture.jpg"), texture.pop("texture_bgr"), [cv2.IMWRITE_JPEG_QUALITY, 86])
        cv2.imwrite(str(out_dir / "photo.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
        cv2.imwrite(str(out_dir / "overlay.png"), overlay)
        cv2.imwrite(str(out_dir / "setofmark.png"), recon.marked_bgr)

    texture: dict = {}
    await asyncio.to_thread(_write)
    end()

    mesh = part.to_trimesh()
    (bx0, by0, bz0), (bx1, by1, bz1) = mesh.bounds
    size_mm, confidence = _confidence_report(spec, budget, recon.completion, estimates)
    report = {
        "job_id": job_id,
        "photo": photo.name,
        "milestone": "D5: measured geometry, height-corrected; mirror reconstruction; modelled 2σ for every dimension",
        "calibration": {"mode": "ruler" if ruler else "mat", "page": cal.page, "markers": len(cal.marker_ids),
                        "known_length_mm": known_length_mm, "fit_rms_mm": round(cal.rms_mm, 4),
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
                 "size_mm": size_mm,
                 "holes": [{"id": h.id, "kind": h.kind,
                            "status": (h.diameter.status if isinstance(h, CircleHole) else h.status).value,
                            **({"diameter_mm": round(h.diameter.value, 3),
                                "diameter_u_mm": h.diameter.uncertainty_mm,
                                "center_mm": [round(h.center_x.value, 3), round(h.center_y.value, 3)]}
                               if isinstance(h, CircleHole) else {"source": h.source})} for h in spec.holes],
                 "excluded_candidates": notes, "unresolved": spec.unresolved()},
        "confidence": confidence,
        "texture": texture,
        "validation": validation,
        "timings_s": timings,
        "reconstruction": _reconstruction_report(recon),
        "outputs": ["model.stl", "model.scad", "model.dxf", "model.svg", "spec.json", "photo.jpg", "texture.jpg",
                    "overlay.png", "setofmark.png", "report.json"],
        "disclaimer": "A reconstruction, not a verified replacement part. Not for safety-critical use.",
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
