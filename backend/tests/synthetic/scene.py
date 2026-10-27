"""Synthetic camera views of the mat with exact ground truth (TEST HARNESS, not real photos).

World frame = physical mat frame: x right, y down along the page, z into the table, in mm.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from shapely.geometry import Point, Polygon, box

from reforge.capture.mat import MatLayout, fill_polygon_exact, render_layout


@dataclass(frozen=True)
class PartShape:
    """A flat part lying on the mat (height ignored), as a shapely polygon in physical mat mm."""

    polygon: Polygon
    value: int = 55  # grey level of the plastic


def hero_bracket(layout: MatLayout, *, broken: bool = False, offset_mm: tuple[float, float] = (0.0, 0.0)) -> Polygon:
    """A flat 80×28 mm bracket, corner radius 4 mm, with two Ø4.2 mm holes 60 mm apart.

    With ``broken=True``, a jagged fracture removes the right end (the right hole stays intact).
    """
    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    plate = box(cx - 40, cy - 14, cx + 40, cy + 14).buffer(-4, quad_segs=32).buffer(4, quad_segs=32)
    for dx in (-30, 30):
        plate = plate.difference(Point(cx + dx, cy).buffer(2.1, quad_segs=64))
    if broken:
        cut = Polygon([(cx + 34, cy - 20), (cx + 50, cy - 20), (cx + 50, cy + 20), (cx + 36.5, cy + 20),
                       (cx + 37.8, cy + 9), (cx + 35.2, cy + 3), (cx + 38.1, cy - 4), (cx + 35.6, cy - 11)])
        plate = plate.difference(cut)
    return plate


@dataclass(frozen=True)
class VirtualCamera:
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    size: tuple[int, int]  # (width, height)

    @property
    def plane_to_image(self) -> np.ndarray:
        """Homography from physical mat-plane mm (z = 0) to image pixels."""
        return self.K @ np.column_stack([self.R[:, 0], self.R[:, 1], self.t])

    def project(self, points_mm: np.ndarray) -> np.ndarray:
        pts = np.asarray(points_mm, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.plane_to_image).reshape(-1, 2)


def _rotation(tilt_x_deg: float, tilt_y_deg: float, roll_deg: float) -> np.ndarray:
    ax, ay, az = np.radians([tilt_x_deg, tilt_y_deg, roll_deg])
    rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    return rz @ rx @ ry


def make_camera(
    layout: MatLayout,
    tilt_x_deg: float = 0.0,
    tilt_y_deg: float = 0.0,
    roll_deg: float = 0.0,
    *,
    size: tuple[int, int] = (2400, 1800),
    focal_px: float = 1900.0,
    fill: float = 0.92,
    physical_scale: float = 1.0,
) -> VirtualCamera:
    """A pinhole camera aimed at the mat centre, as close as possible while the page stays in frame."""
    w, h = size
    k = np.array([[focal_px, 0, w / 2], [0, focal_px, h / 2], [0, 0, 1.0]])
    r = _rotation(tilt_x_deg, tilt_y_deg, roll_deg)
    pw, ph = layout.width_mm * physical_scale, layout.height_mm * physical_scale
    centre = np.array([pw / 2, ph / 2, 0.0])
    forward = r.T @ np.array([0.0, 0.0, 1.0])
    page = np.array([[0, 0], [pw, 0], [pw, ph], [0, ph]], dtype=np.float64)
    margin_x, margin_y = w * (1 - fill) / 2, h * (1 - fill) / 2
    for distance in np.arange(150.0, 3000.0, 5.0):
        t = -r @ (centre - distance * forward)
        cam = VirtualCamera(k, r, t, size)
        depth = (r @ np.column_stack([page, np.zeros(4)]).T).T[:, 2] + t[2]
        if np.any(depth <= 0):
            continue
        px = cam.project(page)
        if (px[:, 0].min() >= margin_x and px[:, 0].max() <= w - margin_x
                and px[:, 1].min() >= margin_y and px[:, 1].max() <= h - margin_y):
            return cam
    raise ValueError("no camera distance keeps the page in frame")


def render_view(
    layout: MatLayout,
    camera: VirtualCamera,
    *,
    physical_scale: float = 1.0,
    paper: int = 235,
    blur_sigma: float = 0.0,
    noise_sigma: float = 0.0,
    occlude_ids: tuple[int, ...] = (),
    parts: tuple[PartShape, ...] = (),
    spots: tuple[tuple[float, float, float, int], ...] = (),
    seed: int = 0,
) -> np.ndarray:
    """Render the mat as the camera sees it. ``physical_scale`` simulates a mis-scaled print.

    ``parts`` are drawn flat on the paper; their holes show the paper. ``spots`` are
    (x_mm, y_mm, radius_mm, grey) discs drawn on top, for example a glare highlight.
    """
    nominal_to_px = camera.plane_to_image @ np.diag([physical_scale, physical_scale, 1.0])
    image = render_layout(layout, nominal_to_px, camera.size, paper=paper)

    def rings_px(polygon: Polygon) -> list[np.ndarray]:
        rings = [np.asarray(polygon.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in polygon.interiors]
        return [camera.project(r) for r in rings]

    for part in parts:  # exact coverage: part geometry is metrology ground truth
        fill_polygon_exact(image, rings_px(part.polygon), part.value)
    for x, y, r, value in spots:
        fill_polygon_exact(image, rings_px(Point(x, y).buffer(r, quad_segs=32)), value)
    for marker_id in occlude_ids:
        m = layout.marker(marker_id)
        pad = 3.0
        quad = np.array([[m.x_mm - pad, m.y_mm - pad], [m.x_mm + m.size_mm + pad, m.y_mm - pad],
                         [m.x_mm + m.size_mm + pad, m.y_mm + m.size_mm + pad],
                         [m.x_mm - pad, m.y_mm + m.size_mm + pad]])
        px = cv2.perspectiveTransform(quad.reshape(-1, 1, 2), nominal_to_px).reshape(-1, 2)
        cv2.fillPoly(image, [np.round(px).astype(np.int32)], 120)
    if blur_sigma > 0:
        image = cv2.GaussianBlur(image, (0, 0), blur_sigma)
    if noise_sigma > 0:
        rng = np.random.default_rng(seed)
        image = np.clip(image + rng.normal(0, noise_sigma, image.shape), 0, 255).astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
