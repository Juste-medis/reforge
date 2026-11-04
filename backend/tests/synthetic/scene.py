"""Synthetic camera views of the mat with exact ground truth (TEST HARNESS, not real photos).

World frame = physical mat frame: x right, y down along the page, z into the table, in mm. The camera sits at z < 0.

Physics modelled (since 2026-10-27): parts are prisms with a real height, so their top face shows parallax; pixels
integrate and lenses blur *linear light*, which is then sRGB-encoded. Not modelled: shadows, lens distortion,
sharpening halos, phone tone curves other than sRGB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from reforge.capture.mat import MatLayout, fill_polygon_exact, render_layout
from reforge.capture.photometry import linear_to_srgb, srgb_to_linear


@dataclass(frozen=True)
class PartShape:
    """A part lying on the mat: a shapely polygon in physical mat mm, extruded ``height_mm`` up from the paper.

    ``height_mm = 0`` is a print on the paper itself, with no parallax.
    """

    polygon: Polygon
    value: int = 55  # grey level of the plastic
    height_mm: float = 0.0


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


def broken_bracket(layout: MatLayout, *, seed: int = 0, offset_mm: tuple[float, float] = (0.0, 0.0),
                   break_x_mm: float = 36.0) -> Polygon:
    """The hero bracket with its right end snapped off along a rough fracture, as plastic breaks: a millimetre-scale
    meander plus sub-millimetre roughness (random, reproducible by ``seed``). The right hole stays intact."""
    from scipy.ndimage import gaussian_filter1d

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    rng = np.random.default_rng(seed)
    y = np.arange(-16.0, 16.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((1.0, 13.0), (0.5, 5.0), (0.25, 2.1)))
    x = break_x_mm + meander + gaussian_filter1d(rng.normal(0.0, 0.15, len(y)), 1.0)
    cut = Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)), (cx + 60, cy + 16), (cx + 60, cy - 16)])
    return hero_bracket(layout, offset_mm=offset_mm).difference(cut)


def bumper_bracket(layout: MatLayout, *, offset_mm: tuple[float, float] = (0.0, 0.0)) -> Polygon:
    """A 94×30 mm bumper mounting bracket: a 64×26 mm body with a Ø30 mounting ear at each end, one Ø5.0 hole
    per ear, 64 mm apart. Mirror-symmetric about both centre lines, like a stamped OEM guide bracket."""

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    body = box(cx - 32, cy - 13, cx + 32, cy + 13).union(Point(cx - 32, cy).buffer(15, quad_segs=48)).union(
        Point(cx + 32, cy).buffer(15, quad_segs=48))
    plate = body.buffer(-2, quad_segs=16).buffer(2, quad_segs=16)
    for dx in (-32, 32):
        plate = plate.difference(Point(cx + dx, cy).buffer(2.5, quad_segs=64))
    return plate


def broken_bumper_bracket(layout: MatLayout, *, seed: int = 0, offset_mm: tuple[float, float] = (0.0, 0.0),
                          break_x_mm: float = 38.0) -> Polygon:
    """The bumper bracket with its right ear snapped off along a rough fracture (the meander model of
    ``broken_bracket``). The right hole stays intact."""
    from scipy.ndimage import gaussian_filter1d

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    rng = np.random.default_rng(seed)
    y = np.arange(-17.0, 17.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((1.0, 13.0), (0.5, 5.0), (0.25, 2.1)))
    x = break_x_mm + meander + gaussian_filter1d(rng.normal(0.0, 0.15, len(y)), 1.0)
    cut = Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)), (cx + 60, cy + 17), (cx + 60, cy - 17)])
    return bumper_bracket(layout, offset_mm=offset_mm).difference(cut)


def mounting_flange(layout: MatLayout) -> Polygon:
    """A 56 mm square mounting flange, corner radius 6 mm: a Ø24 bore and four Ø6.5 holes on a 44 mm square,
    like a flat thermostat-flange blank."""
    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    plate = box(cx - 28, cy - 28, cx + 28, cy + 28).buffer(-6, quad_segs=16).buffer(6, quad_segs=16)
    plate = plate.difference(Point(cx, cy).buffer(12, quad_segs=64))
    for dx in (-22, 22):
        for dy in (-22, 22):
            plate = plate.difference(Point(cx + dx, cy + dy).buffer(3.25, quad_segs=64))
    return plate


def broken_mounting_flange(layout: MatLayout, *, seed: int = 2) -> Polygon:
    """The mounting flange with its right side snapped off 16 mm from the bore's centre: both right-hand holes are
    lost and the bore survives."""
    from scipy.ndimage import gaussian_filter1d

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rng = np.random.default_rng(seed)
    y = np.arange(-33.0, 33.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((1.0, 13.0), (0.5, 5.0), (0.25, 2.1)))
    x = 16.0 + meander + gaussian_filter1d(rng.normal(0.0, 0.15, len(y)), 1.0)
    cut = Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)), (cx + 60, cy + 33), (cx + 60, cy - 33)])
    return mounting_flange(layout).difference(cut)


def adjuster_link(layout: MatLayout) -> Polygon:
    """An 80×20 mm slotted adjuster link: a 24×6.5 mm centre slot and two Ø6.5 holes 60 mm apart, like a
    headlight-aiming link."""
    from shapely.geometry import LineString

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    body = LineString([(cx - 30, cy), (cx + 30, cy)]).buffer(10, quad_segs=32)
    slot = LineString([(cx - 12, cy), (cx + 12, cy)]).buffer(3.25, quad_segs=32)
    link = body.difference(slot)
    for dx in (-30, 30):
        link = link.difference(Point(cx + dx, cy).buffer(3.25, quad_segs=64))
    return link


def broken_link(layout: MatLayout, *, seed: int = 0, offset_mm: tuple[float, float] = (0.0, 0.0)) -> Polygon:
    """The adjuster link with its right ear-tip snapped off along a rough fracture (the meander model of
    ``broken_bracket``), past the slot and the right hole: both survive to pin the mirror."""
    from scipy.ndimage import gaussian_filter1d

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    rng = np.random.default_rng(seed)
    y = np.arange(-12.0, 12.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((1.0, 13.0), (0.5, 5.0), (0.25, 2.1)))
    x = 35.0 + meander + gaussian_filter1d(rng.normal(0.0, 0.15, len(y)), 1.0)
    cut = Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)), (cx + 60, cy + 12), (cx + 60, cy - 12)])
    return adjuster_link(layout).difference(cut)


def shim(layout: MatLayout, *, offset_mm: tuple[float, float] = (0.0, 0.0)) -> Polygon:
    """A 64×40 mm rectangular shim, corner radius 3 mm, with two Ø5 holes 44 mm apart, like a flat alignment
    shim."""
    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    plate = box(cx - 32, cy - 20, cx + 32, cy - 20 + 40).buffer(-3, quad_segs=16).buffer(3, quad_segs=16)
    for dx in (-22, 22):
        plate = plate.difference(Point(cx + dx, cy).buffer(2.5, quad_segs=64))
    return plate


def broken_shim(layout: MatLayout, *, seed: int = 1, offset_mm: tuple[float, float] = (0.0, 0.0)) -> Polygon:
    """The shim with its right end snapped off along a rough fracture (the meander model of ``broken_bracket``),
    past the right hole: both holes survive to pin the mirror."""
    from scipy.ndimage import gaussian_filter1d

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    rng = np.random.default_rng(seed)
    y = np.arange(-22.0, 22.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((1.0, 13.0), (0.5, 5.0), (0.25, 2.1)))
    x = 27.0 + meander + gaussian_filter1d(rng.normal(0.0, 0.15, len(y)), 1.0)
    cut = Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)), (cx + 60, cy + 22), (cx + 60, cy - 22)])
    return shim(layout, offset_mm=offset_mm).difference(cut)


def guitar_pick(layout: MatLayout, *, offset_mm: tuple[float, float] = (0.0, 0.0)) -> Polygon:
    """A 26 × 30 mm teardrop, mirror-symmetric about the vertical line through the free-zone centre; no holes."""
    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2 + offset_mm[0], (y0 + y1) / 2 + offset_mm[1]
    return Point(cx, cy + 4).buffer(13, quad_segs=64).union(Point(cx, cy - 13).buffer(1.5, quad_segs=32)).convex_hull


def broken_pick(layout: MatLayout, *, seed: int = 0) -> Polygon:
    """The guitar pick with one side snapped off along its length (5.8 mm from the axis, meandering): the break
    runs along the mirror axis instead of across it, so little of the symmetry survives."""
    from scipy.ndimage import gaussian_filter1d

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rng = np.random.default_rng(seed)
    y = np.arange(-20.0, 20.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((0.6, 13.0), (0.3, 5.0), (0.15, 2.1)))
    x = 5.8 + meander + gaussian_filter1d(rng.normal(0.0, 0.1, len(y)), 1.0)
    cut = Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)), (cx + 30, cy + 20), (cx + 30, cy - 20)])
    return guitar_pick(layout).difference(cut)


def flange(layout: MatLayout) -> Polygon:
    """A 50 mm square flange, corner radius 6 mm: a Ø22 bore and four Ø5.5 holes on a 38 mm square."""
    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    plate = box(cx - 25, cy - 25, cx + 25, cy + 25).buffer(-6, quad_segs=16).buffer(6, quad_segs=16)
    plate = plate.difference(Point(cx, cy).buffer(11, quad_segs=64))
    for dx in (-19, 19):
        for dy in (-19, 19):
            plate = plate.difference(Point(cx + dx, cy + dy).buffer(2.75, quad_segs=64))
    return plate


def broken_flange(layout: MatLayout, *, seed: int = 2) -> Polygon:
    """The flange with its right side snapped off 14 mm from the bore's centre: both right-hand holes are lost.
    Only the bore pins the vertical mirror axis; the square's diagonals are real symmetries that rebuild only part
    of the break."""
    from scipy.ndimage import gaussian_filter1d

    x0, y0, x1, y1 = layout.free_zone_mm
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rng = np.random.default_rng(seed)
    y = np.arange(-30.0, 30.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((1.0, 13.0), (0.5, 5.0), (0.25, 2.1)))
    x = 14.0 + meander + gaussian_filter1d(rng.normal(0.0, 0.15, len(y)), 1.0)
    cut = Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)), (cx + 60, cy + 30), (cx + 60, cy - 30)])
    return flange(layout).difference(cut)


@dataclass(frozen=True)
class VirtualCamera:
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    size: tuple[int, int]  # (width, height)

    @property
    def plane_to_image(self) -> np.ndarray:
        """Homography from physical mat-plane mm (z = 0) to image pixels."""
        return self.plane_to_image_at(0.0)

    def plane_to_image_at(self, height_mm: float) -> np.ndarray:
        """Homography from the horizontal plane ``height_mm`` above the mat (z = -height) to image pixels."""
        return self.K @ np.column_stack([self.R[:, 0], self.R[:, 1], self.t - height_mm * self.R[:, 2]])

    @property
    def centre_mm(self) -> np.ndarray:
        """Camera centre in the mat frame; z < 0 is above the table."""
        return -self.R.T @ self.t

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


def _map(h: np.ndarray, points: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(np.asarray(points, np.float64).reshape(-1, 1, 2), h).reshape(-1, 2)


def _map_polygon(polygon: Polygon, h: np.ndarray) -> Polygon:
    return Polygon(_map(h, np.asarray(polygon.exterior.coords)[:-1]),
                   [_map(h, np.asarray(r.coords)[:-1]) for r in polygon.interiors])


def silhouette_px(part: PartShape, camera: VirtualCamera) -> Polygon:
    """The image region the part covers. A solid's image is the union of its faces' images, so this is exact for a
    prism: bottom face, top face, and one wall quad per outline or hole edge."""
    bottom = camera.plane_to_image
    if part.height_mm <= 0:
        return _map_polygon(part.polygon, bottom)
    top = camera.plane_to_image_at(part.height_mm)
    faces = [_map_polygon(part.polygon, bottom), _map_polygon(part.polygon, top)]
    for ring in (part.polygon.exterior, *part.polygon.interiors):
        pts = np.asarray(ring.coords)
        b, t = _map(bottom, pts), _map(top, pts)
        for i in range(len(pts) - 1):
            wall = Polygon([b[i], b[i + 1], t[i + 1], t[i]]).buffer(0)
            if not wall.is_empty:
                faces.append(wall)
    shape = unary_union(faces)
    return shape if shape.geom_type == "Polygon" else max(shape.geoms, key=lambda g: g.area)


def silhouette_mm(part: PartShape, camera: VirtualCamera) -> Polygon:
    """The part's image region mapped back through the mat-plane homography: what a perfect segmenter returns."""
    return _map_polygon(silhouette_px(part, camera), np.linalg.inv(camera.plane_to_image))


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
    optics: Literal["linear", "encoded"] = "linear",
) -> np.ndarray:
    """Render the mat as the camera sees it. ``physical_scale`` simulates a mis-scaled print.

    ``parts`` are prisms standing on the paper; their holes show the paper. ``spots`` are
    (x_mm, y_mm, radius_mm, grey) discs drawn on top, for example a glare highlight.

    ``optics="linear"`` blends coverage and blurs in linear light, as a sensor and a lens do, then encodes to
    sRGB. ``optics="encoded"`` blends encoded values: the harness before 2026-10-27, kept to measure its bias.
    """
    if optics not in ("linear", "encoded"):
        raise ValueError(f"unknown optics model {optics!r}")
    linear = optics == "linear"
    nominal_to_px = camera.plane_to_image @ np.diag([physical_scale, physical_scale, 1.0])
    image = render_layout(layout, nominal_to_px, camera.size, paper=paper, linear_light=linear)

    def rings(polygon_px: Polygon) -> list[np.ndarray]:
        return [np.asarray(polygon_px.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in polygon_px.interiors]

    for part in parts:  # exact coverage: part geometry is metrology ground truth
        fill_polygon_exact(image, rings(silhouette_px(part, camera)), part.value, linear_light=linear)
    for x, y, r, value in spots:
        spot = _map_polygon(Point(x, y).buffer(r, quad_segs=32), camera.plane_to_image)
        fill_polygon_exact(image, rings(spot), value, linear_light=linear)
    for marker_id in occlude_ids:
        m = layout.marker(marker_id)
        pad = 3.0
        quad = np.array([[m.x_mm - pad, m.y_mm - pad], [m.x_mm + m.size_mm + pad, m.y_mm - pad],
                         [m.x_mm + m.size_mm + pad, m.y_mm + m.size_mm + pad],
                         [m.x_mm - pad, m.y_mm + m.size_mm + pad]])
        px = cv2.perspectiveTransform(quad.reshape(-1, 1, 2), nominal_to_px).reshape(-1, 2)
        cv2.fillPoly(image, [np.round(px).astype(np.int32)], 120)
    if blur_sigma > 0:
        if linear:
            image = linear_to_srgb(cv2.GaussianBlur(srgb_to_linear(image), (0, 0), blur_sigma))
        else:
            image = cv2.GaussianBlur(image, (0, 0), blur_sigma)
    if noise_sigma > 0:
        rng = np.random.default_rng(seed)
        image = np.clip(image + rng.normal(0, noise_sigma, image.shape), 0, 255).astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
