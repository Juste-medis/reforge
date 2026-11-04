"""Reshape: the Studio's outline editor backend (drag the borders, rebuild at will).

The editor shows the built outline over ``photo.jpg``; the user drags it and the photo comes back with a new
outer boundary. This module converts the edited photo pixels back to view millimetres and validates the new
outline. The pipeline then rebuilds from it like from any measured outline — the geometry still judges — and
the report records the edit (``report["reshaped"]``) plus an ``OUTLINE_RESHAPED`` verification note, so a
hand-drawn edge never passes for a photographed one.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon

from reforge.errors import ReforgeError

MIN_POINTS = 8  # a closed outline with fewer points is a sketch, not a part edge
MAX_POINTS = 8000  # same cap as the spec: the editor sends the outline it was shown, simplified
MIN_AREA_MM2 = 1.0
CARRY_TOL_MM = 1.0  # a redrawn span still means the picked break when it lies this close to it
CARRY_COVER = 0.5  # fraction of a redrawn span that must lie near the picked break to inherit it


def photo_px_to_view_mm(outline_px: np.ndarray, frame: dict, px_per_mm: float,
                        origin_mm: tuple[float, float]) -> np.ndarray:
    """Photo pixels (``photo.jpg``) → view millimetres, inverting the overlay crop.

    ``frame`` is the job's ``frame.json`` (``x0``, ``y0``, ``k``); ``px_per_mm``/``origin_mm`` come from the
    parent report's calibration (exact values, not the rounded display ones).
    """
    pts = np.asarray(outline_px, dtype=np.float64).reshape(-1, 2)
    if len(pts) < MIN_POINTS or len(pts) > MAX_POINTS or not np.isfinite(pts).all():
        raise ReforgeError("RESHAPE_INVALID", f"Need {MIN_POINTS}–{MAX_POINTS} finite outline points.",
                           "Drag the outline in the Studio and try again.")
    k = float(frame["k"])
    view_px = pts / k + np.array([float(frame["x0"]), float(frame["y0"])])
    return view_px / float(px_per_mm) + np.array(origin_mm, dtype=np.float64)


def validate_outline(outline_mm: np.ndarray, parent_area_mm2: float) -> dict:
    """The edited outline must be a valid polygon inside the photo; the mirror gates judge the rest."""
    pts = np.asarray(outline_mm, dtype=np.float64).reshape(-1, 2)
    poly = Polygon(pts).buffer(0)
    if poly.is_empty or poly.geom_type != "Polygon":
        raise ReforgeError("RESHAPE_INVALID", "The redrawn outline crosses itself or has no inside.",
                           "Drag the borders without crossing them: one closed outline around the part.")
    area = float(poly.area)
    if area < MIN_AREA_MM2:
        raise ReforgeError("RESHAPE_INVALID", "The redrawn outline is too small to be the part.",
                           "Keep the outline around the part you photographed.")
    if parent_area_mm2 > 0 and (area > 25.0 * parent_area_mm2 or area < parent_area_mm2 / 25.0):
        raise ReforgeError("RESHAPE_INVALID", "The redrawn outline is far from the photographed one.",
                           "Reshape the outline you were shown; for another part, start a new repair.")
    return {"area_mm2": round(area, 2)}


def carry_span_picks(parent_ids: tuple[str, ...], parent_segmented, edited_mm: np.ndarray) -> tuple[str, ...]:
    """Re-picks by geometry: the redraw renumbers every span, so a picked break is carried to the redrawn spans
    lying where the picked spans were (≥ half within 1 mm). When the user redrew the break away, nothing is
    carried — the new outline is judged as drawn."""
    from scipy.spatial import cKDTree

    from reforge.geometry.segments import segment_outline

    if not parent_ids:
        return ()
    known = {s.seg_id for s in parent_segmented.segments}
    picked = [parent_segmented.span(parent_segmented.by_id(sid)) for sid in parent_ids if sid in known]
    if not picked:
        return ()
    tree = cKDTree(np.vstack(picked))
    carried: list[str] = []
    edited_seg = segment_outline(np.asarray(edited_mm, dtype=np.float64).reshape(-1, 2))
    for span in edited_seg.segments:
        pts = edited_seg.span(span)
        if float((tree.query(pts)[0] <= CARRY_TOL_MM).mean()) >= CARRY_COVER:
            carried.append(span.seg_id)
    return tuple(carried)


def parent_segmentation(input_path, mask: np.ndarray, request: dict):
    """The parent's segmented outline in view mm, recomputed deterministically (same photo, mask, calibration)."""
    import cv2

    from reforge.capture.calibration import RectifiedView, calibrate, rectify, ruler_calibration
    from reforge.geometry.segments import segment_outline
    from reforge.vision.refine import refine_profile

    image = cv2.imread(str(input_path))
    if image is None:
        raise ReforgeError("JOB_NOT_FOUND", "The parent photo is unreadable.",
                           "Run the photo once more, then reshape the new analysis.")
    known = request.get("known_length_mm")
    if known is not None or request.get("deskew_px_per_mm") is not None:
        ys, xs = np.nonzero(mask)
        span = float(max(xs.max() - xs.min(), ys.max() - ys.min()))
        scale = float(request["deskew_px_per_mm"]) if request.get("deskew_px_per_mm") else span / float(known)
        cal = ruler_calibration((image.shape[1], image.shape[0]), scale, float(known or 0.0) or None)
        view = RectifiedView(image=image, px_per_mm=cal.px_per_mm, origin_mm=(0.0, 0.0))
        on_mat = False
    else:
        cal = calibrate(image)
        view = rectify(image, cal)
        on_mat = True
    if mask.shape != view.image.shape[:2]:
        raise ReforgeError("RESHAPE_NO_PARENT", "The parent segmentation doesn't match its photo.",
                           "Run the photo once more, then reshape the new analysis.")
    return segment_outline(refine_profile(view, mask, on_mat=on_mat).outer.points_mm)
