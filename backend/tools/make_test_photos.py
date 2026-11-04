"""Test photos for the app: real photos of flat parts, cut out, placed at a known size on the mat, and photographed by
the synthetic camera. These are SYNTHETIC COMPOSITES, not photos of the printed mat.

Run from `backend/`:
    uv run python -m tools.make_test_photos generate --sources ../tmp/tests/sources --out ../tmp/tests
    uv run python -m tools.make_test_photos evaluate --out ../tmp/tests [--segmenter sam --interpreter spark]

What is real and what is chosen:
- Each part's texture and outline come from a real stock photo (Unsplash License; author and page in each truth file).
- Its size, thickness, placement and any break are chosen here, so the footprint written to ``<name>.truth.json`` is
  exact ground truth for that image.
- The camera is the test harness's (`tests/synthetic/scene.py`: pinhole, parallax of the part's height, linear-light
  blur), plus colour, a mild illumination gradient, sensor noise, JPEG and an EXIF focal length.
- Not modelled: shadows, lens distortion, phone sharpening and tone curves. A real photo of a real part on the printed
  mat (AT-3) remains the only end-to-end validation.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import ExifTags, Image
from scipy.ndimage import gaussian_filter1d
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient

from reforge.capture.mat import mat_layout, polygon_coverage, render_layout
from reforge.capture.photometry import linear_to_srgb, srgb_to_linear
from reforge.geometry.contour import resample_closed, smooth_closed
from reforge.spec.partspec import mat_to_model
from tests.synthetic.scene import (
    PartShape,
    _map_polygon,
    adjuster_link,
    broken_bracket,
    broken_bumper_bracket,
    broken_flange,
    broken_link,
    broken_mounting_flange,
    broken_shim,
    bumper_bracket,
    flange,
    hero_bracket,
    make_camera,
    mounting_flange,
    shim,
    silhouette_px,
)

LAYOUT = mat_layout("A4")
X0, Y0, X1, Y1 = LAYOUT.free_zone_mm
CENTRE = ((X0 + X1) / 2, (Y0 + Y1) / 2)
SIZE = (3024, 4032)  # a 12 MP phone photo, held upright like the page
FOCAL_35MM = 52.0  # the 2× lens the capture protocol asks for (PLAN §5.2)
FOCAL_PX = FOCAL_35MM / float(np.hypot(36.0, 24.0)) * float(np.hypot(*SIZE))
WALL_SHADE = 0.45  # side walls in the shade of their own top edge, as linear-light fraction of the top colour
LABEL = "SYNTHETIC COMPOSITE for testing: stock photo of a part placed on a rendered mat; not a real photo"

# Unsplash License (https://unsplash.com/license): free to use and modify; attribution is not required but recorded.
SOURCES = {
    "A": ("Matt Artz", "https://unsplash.com/photos/pH6wLT6TVFc", "photo-1502068898470-ad70c83938be"),
    "B": ("Matt Artz", "https://unsplash.com/photos/lt2GzPlOAmc", "photo-1503791228404-a79884146f98"),
    "C": ("Matt Artz", "https://unsplash.com/photos/wbx3FeGOEQ0", "photo-1503791774117-08c379dd7f7c"),
    "D": ("Matt Artz", "https://unsplash.com/photos/pY_AZJfdbHQ", "photo-1503792243040-7ce7f5f06085"),
    "E": ("Everyday basics", "https://unsplash.com/photos/GJY1eAw6tn8", "photo-1584985429926-08867327d3a6"),
    "G": ("Robert Ruggiero", "https://unsplash.com/photos/wdfQR7FQk6g", "photo-1643730169397-a4bf0b10db5d"),
    "H": ("Ksenia Pixelesse", "https://unsplash.com/s/photos/guitar-pick-white-background",
          "photo-1745859526784-8bc52bf93438"),
}


@dataclass(frozen=True)
class Case:
    name: str
    what: str
    thickness_mm: float
    length_mm: float = 0.0  # longest side as placed; 0 keeps a synthetic polygon's own size
    source: str | None = None  # key of SOURCES; None for a synthetic polygon in a flat colour
    select: str = "largest:0"  # "largest:k" or "colour:red|green|blue|white"
    synthetic: str | None = None  # "bracket" or "bracket_broken:<seed>"
    colour_bgr: tuple[int, int, int] = (60, 60, 60)
    rotate_deg: float = 8.0
    tilt: tuple[float, float, float] = (3.0, -2.0, 1.0)
    break_seed: int | None = None  # snap off one side, parallel to the part's own mirror axis
    expect: str = "model"


CASES = (
    Case("01_pick_red", "red plastic guitar pick", 0.8, 30.0, "H", "colour:red", rotate_deg=12, tilt=(2, -3, 1)),
    Case("02_pick_blue", "blue plastic guitar pick", 0.8, 30.0, "H", "colour:blue", rotate_deg=-20, tilt=(-3, 2, 0)),
    Case("03_pick_green", "green plastic guitar pick", 0.8, 30.0, "H", "colour:green", rotate_deg=35, tilt=(4, 1, -2)),
    Case("04_pick_white", "white plastic guitar pick (low contrast on white paper: a hard case)", 0.8, 30.0, "H",
         "colour:white", rotate_deg=5, expect="hard: may be refused for low contrast"),
    Case("05_pick_red_broken", "red guitar pick with one side snapped off", 0.8, 30.0, "H", "colour:red",
         rotate_deg=-8, tilt=(-2, -2, 2), break_seed=1, expect="model, rebuilt by mirror"),
    Case("06_pick_green_broken", "green guitar pick with one side snapped off", 0.8, 30.0, "H", "colour:green",
         rotate_deg=15, tilt=(3, 3, -1), break_seed=4, expect="model, rebuilt by mirror"),
    Case("07_wrench_open", "double open-end spanner", 5.0, 150.0, "A", "largest:0", rotate_deg=6),
    Case("08_wrench_open_small", "smaller double open-end spanner", 4.5, 125.0, "A", "largest:1", rotate_deg=-14,
         tilt=(-4, 3, 2)),
    Case("09_wrench_s", "S-shaped open-end spanner", 4.0, 160.0, "B", "largest:0", rotate_deg=3, tilt=(2, 4, -1)),
    Case("10_wrench_open_c", "double open-end spanner, worn", 5.0, 145.0, "C", "largest:0", rotate_deg=-5,
         tilt=(5, -1, 0)),
    Case("11_key", "flat key with a ring hole", 2.0, 55.0, "D", "largest:0", rotate_deg=25, tilt=(-3, -3, 3)),
    Case("12_skeleton_key", "old skeleton key with an open bow", 3.0, 85.0, "E", "largest:0", rotate_deg=-10),
    Case("13_adjustable_wrench", "200 mm adjustable wrench with a hang hole (not uniform thickness)", 6.0, 200.0,
         "G", "largest:0", rotate_deg=4, tilt=(1, -4, 1), expect="model or FAMILY_UNSUPPORTED (thicker head)"),
    Case("14_bracket_blue", "rendered 80 × 28 mm bracket, two Ø4.2 holes", 3.0, synthetic="bracket",
         colour_bgr=(170, 90, 30), rotate_deg=0, tilt=(4, -3, 2)),
    Case("15_bracket_orange_broken", "rendered bracket with its right end snapped off", 3.0,
         synthetic="bracket_broken:0", colour_bgr=(30, 110, 230), rotate_deg=0, tilt=(-3, 4, -1),
         expect="model, rebuilt by mirror"),
    Case("16_bracket_black_broken", "rendered dark bracket, snapped off (seed 3)", 3.0,
         synthetic="bracket_broken:3", colour_bgr=(40, 40, 42), rotate_deg=0, tilt=(5, 2, 1),
         expect="model, rebuilt by mirror"),
    Case("17_washer_yellow", "rendered plastic washer, Ø30 / Ø12 mm", 2.0, synthetic="washer",
         colour_bgr=(30, 190, 235), rotate_deg=0, tilt=(-4, 3, 2)),
    Case("18_link_red", "rendered 70 × 18 mm link with a 20 × 6 mm slot and two Ø6 holes", 4.0, synthetic="link",
         colour_bgr=(45, 40, 190), rotate_deg=-30, tilt=(3, 4, -2)),
    Case("19_l_plate_green", "rendered L-shaped plate, 60 × 45 mm, three Ø4.5 holes", 3.0, synthetic="l_plate",
         colour_bgr=(80, 150, 40), rotate_deg=15, tilt=(5, -3, 1)),
    Case("20_flange_black_broken", "rendered 50 mm square flange; the break took two of its four holes", 3.0,
         synthetic="flange_broken:2", colour_bgr=(38, 36, 36), rotate_deg=0, tilt=(-3, -4, 2),
         expect="model, rebuilt by mirror with the two lost holes inferred"),
    Case("21_bumper_graphite_broken", "rendered 94 × 30 mm bumper bracket, graphite; right ear snapped off", 4.0,
         synthetic="bumper_broken:0", colour_bgr=(62, 60, 58), rotate_deg=0, tilt=(-3, 4, -1),
         expect="model, rebuilt by mirror"),
    Case("22_mflange_black_broken", "rendered 56 mm mounting flange; the break took two of its four holes", 5.0,
         synthetic="mflange_broken:2", colour_bgr=(38, 36, 36), rotate_deg=0, tilt=(-3, -4, 2),
         expect="model, rebuilt by mirror with the two lost holes inferred"),
    Case("23_alink_grey", "rendered 80 × 20 mm adjuster link with a 24 × 6.5 mm slot and two Ø6.5 holes", 5.0,
         synthetic="alink", colour_bgr=(75, 72, 70), rotate_deg=-30, tilt=(3, 4, -2)),
    Case("24_flange_grey", "rendered 50 mm square flange, Ø22 bore, four Ø5.5 holes", 3.0, synthetic="flange",
         colour_bgr=(110, 108, 105), rotate_deg=10, tilt=(2, -3, 1)),
    Case("25_mflange_steel", "rendered 56 mm mounting flange, Ø24 bore, four Ø6.5 holes", 5.0, synthetic="mflange",
         colour_bgr=(130, 128, 125), rotate_deg=-12, tilt=(-3, 2, 0)),
    Case("26_bumper_blue", "rendered 94 × 30 mm bumper bracket, two Ø5 holes", 4.0, synthetic="bumper",
         colour_bgr=(180, 60, 30), rotate_deg=20, tilt=(4, 1, -2)),
    Case("27_alink_red_broken", "rendered adjuster link with its right ear-tip snapped off", 5.0,
         synthetic="alink_broken:4", colour_bgr=(50, 45, 190), rotate_deg=0, tilt=(-3, 4, -1),
         expect="model, rebuilt by mirror"),
    Case("28_shim_steel", "rendered 64 × 40 mm alignment shim, two Ø5 holes", 1.0, synthetic="shim",
         colour_bgr=(140, 138, 135), rotate_deg=-25, tilt=(3, -4, 2)),
    Case("29_shim_grey_broken", "rendered alignment shim with its right end snapped off", 1.0,
         synthetic="shim_broken:5", colour_bgr=(100, 98, 95), rotate_deg=0, tilt=(-4, 3, 1),
         expect="model, rebuilt by mirror"),
    Case("30_washer_red_broken", "rendered washer with a rim segment snapped off past the bore", 2.0,
         synthetic="washer_broken:6", colour_bgr=(50, 45, 190), rotate_deg=0, tilt=(3, -4, 2),
         expect="model, rebuilt by mirror"),
    Case("31_link_yellow_broken", "rendered slotted link with its right ear-tip snapped off", 4.0,
         synthetic="link_broken:7", colour_bgr=(30, 190, 235), rotate_deg=0, tilt=(-2, 3, -1),
         expect="model, rebuilt by mirror"),
    Case("32_pulley_steel", "rendered crankshaft pulley, Ø130, Ø30 bore, four Ø8 bolts, four Ø6 lightening holes",
         8.0, synthetic="pulley", colour_bgr=(130, 128, 125), rotate_deg=10, tilt=(2, -3, 1)),
    Case("33_pulley_cast_broken", "rendered crankshaft pulley with a rim segment snapped off, taking one bolt hole "
         "and two lightening holes", 8.0, synthetic="pulley_broken:8", colour_bgr=(70, 68, 65), rotate_deg=0,
         tilt=(-3, 4, -1), expect="model, rebuilt by mirror with the three lost holes inferred"),
)


# --- cut-out ------------------------------------------------------------------------------------------------------

def _lab(image_bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    return lab


def cut_out(image_bgr: np.ndarray, select: str) -> np.ndarray:
    """The selected part's mask (uint8 0/1): colour distance from the photo's border colour, Otsu threshold."""
    h, w = image_bgr.shape[:2]
    lab = _lab(image_bgr)
    b = 20
    border = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3),
                             lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    de = np.linalg.norm(lab - bg, axis=2)
    de8 = cv2.GaussianBlur(np.clip(de * 2, 0, 255).astype(np.uint8), (5, 5), 0)
    _, mask = cv2.threshold(de8, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if bg[0] < 15:  # a black backdrop: dark, recessed metal is still far brighter than it
        mask = (de8 > 16).astype(np.uint8)
    k = max(5, int(0.004 * np.hypot(h, w)) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    comps = []
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if area > 0.002 * h * w and x > 1 and y > 1 and x + cw < w - 1 and y + ch < h - 1:
            comps.append((i, area, lab[labels == i].mean(axis=0)))
    kind, arg = select.split(":")
    if kind == "largest":
        chosen = sorted(comps, key=lambda c: -c[1])[int(arg)][0]
    else:
        tests = {"red": lambda m: m[1] > 30, "green": lambda m: m[1] < -20, "blue": lambda m: m[2] < -20,
                 "white": lambda m: m[0] > 75 and np.hypot(m[1], m[2]) < 15}
        (chosen,) = [i for i, _, m in comps if tests[arg](m)]
    part = (labels == chosen).astype(np.uint8)
    # Dark texture inside the part is not a hole: the real holes here are over 2 % of the part's area and compact,
    # where a key's grooves are long and thin.
    holes = (1 - part).astype(np.uint8)
    n, hl, hs, _ = cv2.connectedComponentsWithStats(holes)
    for i in range(1, n):
        x, y, cw, ch, area = hs[i]
        inside = x > 0 and y > 0 and x + cw < w and y + ch < h
        if not inside:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(np.column_stack(np.nonzero(hl == i)[::-1]).astype(np.float32))
        if area < 0.015 * part.sum() or max(rw, rh) > 4 * max(min(rw, rh), 1.0):
            part[hl == i] = 1
    if kind == "colour":  # the picks lie on wood: thin shadow tails join them, and their features are all wide
        part = cv2.morphologyEx(part, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(part)
        part = (labels == 1 + int(np.argmax(stats[1:, 4]))).astype(np.uint8)
    return part


def _rings(mask: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.0)
    binary = (soft > 0.5).astype(np.uint8)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    outer = max(range(len(contours)), key=lambda i: cv2.contourArea(contours[i]))
    holes = [contours[i] for i in range(len(contours)) if hierarchy[0][i][3] == outer]
    return contours[outer].reshape(-1, 2).astype(np.float64), [c.reshape(-1, 2).astype(np.float64) for c in holes]


def _extrapolate(image_lin: np.ndarray, trusted: np.ndarray) -> np.ndarray:
    """Push-pull fill: every pixel outside ``trusted`` takes the colour of the nearest trusted region."""
    w0 = trusted.astype(np.float32)
    cs, ws = [image_lin * w0[..., None]], [w0]
    while min(cs[-1].shape[:2]) > 8:
        cs.append(cv2.pyrDown(cs[-1]))
        ws.append(cv2.pyrDown(ws[-1]))
    est = cs[-1] / np.maximum(ws[-1], 1e-6)[..., None]
    for c, wt in zip(reversed(cs[:-1]), reversed(ws[:-1]), strict=True):
        up = cv2.pyrUp(est, dstsize=(c.shape[1], c.shape[0]))
        alpha = np.clip(wt * 4.0, 0.0, 1.0)[..., None]
        est = alpha * (c / np.maximum(wt, 1e-6)[..., None]) + (1 - alpha) * up
    return np.where(trusted[..., None] > 0, image_lin, est).astype(np.float32)


# --- placing a part -----------------------------------------------------------------------------------------------

@dataclass
class Placed:
    polygon: Polygon  # footprint in mat mm (ground truth)
    texture_lin: np.ndarray  # linear-light BGR float32
    src_to_mm: np.ndarray  # 3×3 similarity from texture pixels to mat mm
    intact: Polygon | None = None
    symmetry: dict = field(default_factory=dict)


def _similarity(scale: float, angle_deg: float, src_centre: np.ndarray, dst_centre: tuple[float, float]) -> np.ndarray:
    a = np.radians(angle_deg)
    r = scale * np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    t = np.asarray(dst_centre) - r @ src_centre
    return np.array([[r[0, 0], r[0, 1], t[0]], [r[1, 0], r[1, 1], t[1]], [0, 0, 1.0]])


def _apply(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ m[:2, :2].T + m[:2, 2]


def place_photo(case: Case, sources: Path) -> Placed:
    image = cv2.imread(str(sources / f"{case.source}.jpg"), cv2.IMREAD_COLOR)
    mask = cut_out(image, case.select)
    ys, xs = np.nonzero(mask)
    pad = 40
    bx0, by0 = max(xs.min() - pad, 0), max(ys.min() - pad, 0)
    bx1, by1 = min(xs.max() + pad, image.shape[1]), min(ys.max() + pad, image.shape[0])
    crop, mcrop = image[by0:by1, bx0:bx1], mask[by0:by1, bx0:bx1]
    outer, holes = _rings(mcrop)
    centre = outer.mean(axis=0)
    _, (rw, rh), rect_angle = cv2.minAreaRect(outer.astype(np.float32))
    long_px = max(rw, rh)
    # Long side along the mat's y axis, then the case's own rotation.
    angle = (90.0 - rect_angle if rw >= rh else -rect_angle) + case.rotate_deg
    src_to_mm = _similarity(case.length_mm / long_px, angle, centre, CENTRE)
    spacing = 0.12
    sigma = max(1.5 * case.length_mm / long_px, 0.03)
    rings = [smooth_closed(_apply(src_to_mm, r), sigma, spacing) for r in (outer, *holes)]
    polygon = orient(Polygon(rings[0], rings[1:]).buffer(0), 1.0)
    trusted = cv2.erode(mcrop, np.ones((9, 9), np.uint8))  # edge pixels mix in the backdrop
    texture = _extrapolate(srgb_to_linear(crop), trusted)
    return Placed(polygon, texture, src_to_mm)  # outline and texture share the crop's pixel frame


def _rendered(kind: str) -> Polygon:
    """Rendered plastic parts centred in the free zone (mm)."""
    cx, cy = CENTRE
    if kind == "washer":
        return Point(cx, cy).buffer(15, quad_segs=64).difference(Point(cx, cy).buffer(6, quad_segs=64))
    if kind == "link":
        body = LineString([(cx - 26, cy), (cx + 26, cy)]).buffer(9, quad_segs=32)
        slot = LineString([(cx - 7, cy), (cx + 7, cy)]).buffer(3, quad_segs=32)
        holes = [Point(cx + dx, cy).buffer(3, quad_segs=64) for dx in (-26, 26)]
        return body.difference(slot).difference(holes[0]).difference(holes[1])
    if kind == "pulley":
        # A small car's crankshaft pulley, Ø130: Ø30 bore, four Ø8 bolt holes on a Ø60 circle, four Ø6
        # lightening holes on a Ø96 circle. Mirror-symmetric about both centre lines, like the real part.
        disc = Point(cx, cy).buffer(65, quad_segs=128)
        pulley = disc.difference(Point(cx, cy).buffer(15, quad_segs=64))
        for dx, dy in ((30, 0), (-30, 0), (0, 30), (0, -30)):
            pulley = pulley.difference(Point(cx + dx, cy + dy).buffer(4, quad_segs=64))
        for dx, dy in ((33.9, 33.9), (-33.9, 33.9), (33.9, -33.9), (-33.9, -33.9)):
            pulley = pulley.difference(Point(cx + dx, cy + dy).buffer(3, quad_segs=64))
        return pulley
    if kind == "l_plate":
        plate = box(cx - 30, cy - 22.5, cx - 15, cy + 22.5).union(box(cx - 30, cy + 7.5, cx + 30, cy + 22.5))
        plate = plate.buffer(-3, quad_segs=16).buffer(3, quad_segs=16)
        for x, y in ((cx - 22.5, cy - 14), (cx - 22.5, cy + 15), (cx + 22, cy + 15)):
            plate = plate.difference(Point(x, y).buffer(2.25, quad_segs=64))
        return plate
    raise ValueError(kind)


def _meander_cut(cx: float, cy: float, x_keep: float, y_half: float, seed: int, x_far: float = 60.0) -> Polygon:
    """The rough chord of ``broken_shim`` (scene.py), for the CENTRE-rendered parts: everything past
    ``x_keep`` is removed. The caller keeps the cut clear of the holes; ``x_far`` must clear the part's edge
    or the rim cap survives as an island."""
    rng = np.random.default_rng(seed)
    y = np.arange(-y_half, y_half + 0.0001, 0.25)
    meander = sum(a * np.sin(2 * np.pi * y / wavelength + rng.uniform(0, 2 * np.pi))
                  for a, wavelength in ((1.0, 13.0), (0.5, 5.0), (0.25, 2.1)))
    x = x_keep + meander + gaussian_filter1d(rng.normal(0.0, 0.15, len(y)), 1.0)
    return Polygon([*((cx + xi, cy + yi) for xi, yi in zip(x, y, strict=True)),
                    (cx + x_far, cy + y_half), (cx + x_far, cy - y_half)])


def place_synthetic(case: Case) -> Placed:
    kind, _, seed = case.synthetic.partition(":")
    intact = None
    if kind in ("bracket", "bracket_broken"):
        poly = hero_bracket(LAYOUT) if kind == "bracket" else broken_bracket(LAYOUT, seed=int(seed))
        intact = hero_bracket(LAYOUT) if kind != "bracket" else None
    elif kind == "flange_broken":
        intact, poly = flange(LAYOUT), broken_flange(LAYOUT, seed=int(seed))
    elif kind in ("bumper", "bumper_broken"):
        poly = bumper_bracket(LAYOUT) if kind == "bumper" else broken_bumper_bracket(LAYOUT, seed=int(seed))
        intact = bumper_bracket(LAYOUT) if kind != "bumper" else None
    elif kind == "mflange_broken":
        intact, poly = mounting_flange(LAYOUT), broken_mounting_flange(LAYOUT, seed=int(seed))
    elif kind == "alink":
        poly = adjuster_link(LAYOUT)
    elif kind == "alink_broken":
        intact, poly = adjuster_link(LAYOUT), broken_link(LAYOUT, seed=int(seed))
    elif kind == "shim":
        poly = shim(LAYOUT)
    elif kind == "shim_broken":
        intact, poly = shim(LAYOUT), broken_shim(LAYOUT, seed=int(seed))
    elif kind == "flange":
        poly = flange(LAYOUT)
    elif kind == "mflange":
        poly = mounting_flange(LAYOUT)
    elif kind == "bumper":
        poly = bumper_bracket(LAYOUT)
    elif kind == "washer_broken":
        # Rim segment snapped off along a chord at cx + 8.5: the bore (r6) survives to pin the mirror.
        intact = _rendered("washer")
        poly = intact.difference(_meander_cut(CENTRE[0], CENTRE[1], 8.5, 16.0, int(seed)))
    elif kind == "link_broken":
        # Right ear-tip snapped off at cx + 31.5: both holes (at ±26) and the slot survive.
        intact = _rendered("link")
        poly = intact.difference(_meander_cut(CENTRE[0], CENTRE[1], 31.5, 10.0, int(seed)))
    elif kind == "pulley_broken":
        # Right rim segment snapped off at cx + 22: the bore survives to pin the mirror; the right bolt hole
        # (x 26–34) and both right lightening holes (x 31–37) are lost in the break and must come back by mirror.
        intact = _rendered("pulley")
        poly = intact.difference(_meander_cut(CENTRE[0], CENTRE[1], 22.0, 66.0, int(seed), 70.0))
    else:
        poly = _rendered(kind)
    poly = affinity.rotate(poly, case.rotate_deg, origin=CENTRE)
    intact = None if intact is None else affinity.rotate(intact, case.rotate_deg, origin=CENTRE)
    rng = np.random.default_rng(7)
    tex = np.full((64, 64, 3), case.colour_bgr, np.float32) + rng.normal(0, 2.0, (64, 64, 3))
    texture = srgb_to_linear(np.clip(tex, 0, 255).astype(np.uint8))
    x0, y0, x1, y1 = poly.bounds
    src_to_mm = np.array([[(x1 - x0 + 20) / 64, 0, x0 - 10], [0, (y1 - y0 + 20) / 64, y0 - 10], [0, 0, 1.0]])
    return Placed(orient(poly, 1.0), texture, src_to_mm, intact)


def _reflect(poly: Polygon, angle_deg: float, through: tuple[float, float]) -> Polygon:
    a = np.radians(angle_deg)
    d = np.array([np.cos(a), np.sin(a)])
    m = 2 * np.outer(d, d) - np.eye(2)
    t = np.asarray(through) - m @ np.asarray(through)
    return affinity.affine_transform(poly, [m[0, 0], m[0, 1], m[1, 0], m[1, 1], t[0], t[1]])


def mirror_axis(poly: Polygon, around_deg: float, span_deg: float = 15.0) -> tuple[float, float]:
    """The part's best mirror axis through its centroid within ``span_deg`` of ``around_deg``: (angle in degrees,
    IoU of the part with its reflection)."""
    through = (poly.centroid.x, poly.centroid.y)
    best = (0.0, 0.0)
    for angle in np.arange(around_deg - span_deg, around_deg + span_deg, 0.25):
        mirrored = _reflect(poly, angle, through)
        iou = poly.intersection(mirrored).area / poly.union(mirrored).area
        if iou > best[1]:
            best = (float(angle), float(iou))
    return best


def snap_side(poly: Polygon, seed: int) -> tuple[Polygon, Polygon, dict]:
    """Break off one side of the part along a rough fracture parallel to its lengthwise mirror axis, keeping the axis
    itself and the other side intact, so a mirror can rebuild what is missing (the meander model of
    ``broken_bracket``).

    A stock photo taken at an angle makes a symmetric part look slightly asymmetric, so the intact part is first made
    exactly symmetric (its intersection with its own mirror image), as the real part is. Returns (broken, intact)."""
    rect = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:3]
    sides = np.diff(rect, axis=0)
    long_side = max(sides, key=np.linalg.norm)
    angle, iou = mirror_axis(poly, float(np.degrees(np.arctan2(long_side[1], long_side[0]))))
    sym = poly.intersection(_reflect(poly, angle, (poly.centroid.x, poly.centroid.y)))
    poly = orient(max(getattr(sym, "geoms", [sym]), key=lambda g: g.area), 1.0)
    a = np.radians(angle)
    u, v = np.array([np.cos(a), np.sin(a)]), np.array([-np.sin(a), np.cos(a)])
    c = np.array([poly.centroid.x, poly.centroid.y])
    pts = np.asarray(poly.exterior.coords) - c
    along, across = pts @ u, pts @ v
    rng = np.random.default_rng(seed)
    side = rng.choice([-1.0, 1.0])
    half = (across.max() if side > 0 else -across.min())
    span = np.arange(along.min() - 5, along.max() + 5, 0.25)
    amp = 0.02 * (along.max() - along.min())
    meander = sum(amp * k * np.sin(2 * np.pi * span / (wl * (along.max() - along.min())) + rng.uniform(0, 2 * np.pi))
                  for k, wl in ((1.0, 0.45), (0.5, 0.17), (0.25, 0.07)))
    offset = 0.45 * half + meander + gaussian_filter1d(rng.normal(0.0, 0.1, len(span)), 1.0)
    line = [c + s * u + side * o * v for s, o in zip(span, offset, strict=True)]
    far = [c + span[-1] * u + side * 3 * half * v, c + span[0] * u + side * 3 * half * v]
    cut = Polygon([*line, *far]).buffer(0)
    broken = poly.difference(cut)
    broken = max(getattr(broken, "geoms", [broken]), key=lambda g: g.area)
    return orient(broken, 1.0), poly, {"mirror_axis_deg": round(angle, 2), "photo_outline_mirror_iou": round(iou, 4),
                                       "intact_outline": "the photo outline intersected with its mirror image",
                                       "removed_area_mm2": round(poly.area - broken.area, 2)}


# --- rendering ----------------------------------------------------------------------------------------------------

def _rings_px(polygon: Polygon) -> list[np.ndarray]:
    return [np.asarray(polygon.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in polygon.interiors]


def _paste(cov, box, shape_box) -> np.ndarray:
    (x0, y0, x1, y1), (bx0, by0, bx1, by1) = box, shape_box
    out = np.zeros((by1 - by0, bx1 - bx0), np.float32)
    out[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0] = cov
    return out


def render(case: Case, placed: Placed, seed: int) -> tuple[np.ndarray, dict]:
    cam = make_camera(LAYOUT, *case.tilt, size=SIZE, focal_px=FOCAL_PX)
    grey = render_layout(LAYOUT, cam.plane_to_image, cam.size, linear_light=True)
    scene = np.repeat(srgb_to_linear(grey)[..., None], 3, axis=2) * np.array([0.95, 1.0, 1.03], np.float32)

    part = PartShape(placed.polygon, height_mm=case.thickness_mm)
    sil = silhouette_px(part, cam)
    top = _map_polygon(placed.polygon, cam.plane_to_image_at(case.thickness_mm))
    sil_box, sil_cov = polygon_coverage(_rings_px(sil), scene.shape[:2])
    top_box, top_cov = polygon_coverage(_rings_px(top), scene.shape[:2])
    bx0, by0, bx1, by1 = sil_box
    top_cov = _paste(top_cov, top_box, sil_box)[:, :, None]
    sil_cov = sil_cov[:, :, None]

    src_to_img = cam.plane_to_image_at(case.thickness_mm) @ placed.src_to_mm
    to_box = np.array([[1, 0, -bx0], [0, 1, -by0], [0, 0, 1.0]]) @ src_to_img
    texture = placed.texture_lin
    out_per_src = np.sqrt(abs(np.linalg.det(src_to_img[:2, :2] / src_to_img[2, 2])))
    if out_per_src < 0.7:  # minify with area averaging first, then warp
        f = out_per_src / 0.7
        texture = cv2.resize(texture, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        to_box = to_box @ np.diag([1 / f, 1 / f, 1.0])
    top_colour = cv2.warpPerspective(texture, to_box, (bx1 - bx0, by1 - by0), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_REPLICATE)
    wall = np.median(placed.texture_lin.reshape(-1, 3), axis=0) * WALL_SHADE
    region = scene[by0:by1, bx0:bx1]
    walls = np.clip(sil_cov - top_cov, 0.0, 1.0)
    scene[by0:by1, bx0:bx1] = region * (1 - sil_cov) + top_colour * np.minimum(top_cov, sil_cov) + wall * walls

    h, w = scene.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / (w * w / 4 + h * h / 4)
    rng = np.random.default_rng(seed)
    ramp = rng.uniform(-0.04, 0.04, 2)
    light = 1.0 - 0.07 * r2 + ramp[0] * (xx / w - 0.5) + ramp[1] * (yy / h - 0.5)
    scene = cv2.GaussianBlur(scene * light[..., None], (0, 0), 0.9)
    encoded = linear_to_srgb(np.clip(scene, 0.0, 1.0)).astype(np.float32) + rng.normal(0, 1.5, scene.shape)
    camera = {"size_px": list(SIZE), "focal_px": round(FOCAL_PX, 1), "focal_35mm": FOCAL_35MM,
              "tilt_x_deg": case.tilt[0], "tilt_y_deg": case.tilt[1], "roll_deg": case.tilt[2],
              "height_above_mat_mm": round(float(-cam.centre_mm[2]), 1), "blur_sigma_px": 0.9, "noise_sigma": 1.5}
    return np.clip(np.round(encoded), 0, 255).astype(np.uint8), camera


def _jpeg(bgr: np.ndarray, path: Path) -> None:
    exif = Image.Exif()
    exif[ExifTags.Base.ImageDescription] = LABEL
    exif[ExifTags.Base.Software] = "RE-FORGE tools/make_test_photos.py"
    exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.FocalLengthIn35mmFilm] = int(FOCAL_35MM)
    buf = io.BytesIO()
    Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).save(buf, "JPEG", quality=92, exif=exif.tobytes())
    path.write_bytes(buf.getvalue())


def _describe(poly: Polygon) -> dict:
    x0, y0, x1, y1 = poly.bounds
    holes = []
    for ring in poly.interiors:
        hole = Polygon(ring)
        holes.append({"centre_mm": [round(hole.centroid.x, 3), round(hole.centroid.y, 3)],
                      "area_mm2": round(hole.area, 3),
                      "equivalent_diameter_mm": round(float(2 * np.sqrt(hole.area / np.pi)), 3)})
    return {"overall_mm": [round(x1 - x0, 3), round(y1 - y0, 3)], "area_mm2": round(poly.area, 2), "holes": holes,
            "outline_mm": np.round(resample_closed(np.asarray(poly.exterior.coords)[:-1], 0.25), 3).tolist()}


def generate(sources: Path, out: Path, only: list[str] | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for k, case in enumerate(CASES):
        if only and case.name not in only:
            continue
        placed = place_synthetic(case) if case.synthetic else place_photo(case, sources)
        if case.break_seed is not None:
            placed.polygon, placed.intact, placed.symmetry = snap_side(placed.polygon, case.break_seed)
        image, camera = render(case, placed, seed=100 + k)
        _jpeg(image, out / f"{case.name}.jpg")
        src = SOURCES.get(case.source) if case.source else None
        truth = {
            "label": LABEL, "case": asdict(case),
            "texture_source": None if src is None else {"author": src[0], "page": src[1], "cdn_id": src[2],
                                                        "licence": "Unsplash License"},
            "thickness_to_enter_mm": case.thickness_mm, "camera": camera,
            "footprint": _describe(placed.polygon),
            "intact_footprint": None if placed.intact is None else _describe(placed.intact),
            "break": placed.symmetry or None,
        }
        (out / f"{case.name}.truth.json").write_text(json.dumps(truth, indent=1))
        print(f"{case.name}: {truth['footprint']['overall_mm']} mm, {len(truth['footprint']['holes'])} holes"
              + (f", broken (removed {placed.symmetry.get('removed_area_mm2')} mm²)" if placed.symmetry else ""))


# --- evaluation ---------------------------------------------------------------------------------------------------

def _outline_distance(outline_model: np.ndarray, truth_mat: np.ndarray) -> tuple[float, float]:
    """(Hausdorff, 95th percentile of measured-to-truth distance) after centring both bounding boxes (the spec's
    model frame is bbox-centred, y up)."""
    import shapely

    a = np.asarray(outline_model, np.float64)
    b = mat_to_model(truth_mat, (0.0, 0.0))
    a = a - (a.min(axis=0) + a.max(axis=0)) / 2
    b = b - (b.min(axis=0) + b.max(axis=0)) / 2
    ring_a, ring_b = LineString([*a, a[0]]), LineString([*b, b[0]])
    to_truth = shapely.distance(ring_b, shapely.points(np.asarray(ring_a.segmentize(0.1).coords)))
    return float(ring_a.hausdorff_distance(ring_b)), float(np.percentile(to_truth, 95))


async def _evaluate(out: Path, segmenter_name: str, interpreter_name: str, only: list[str] | None) -> list[dict]:
    from reforge.config import Settings
    from reforge.errors import ReforgeError
    from reforge.meta_api.client import MetaClient
    from reforge.pipeline import photo_to_stl
    from reforge.reasoning.interpret import GeometricInterpreter, SparkInterpreter
    from reforge.vision.segment import ClassicalSegmenter, SamSegmenter

    client = MetaClient(Settings()) if "sam" in segmenter_name or interpreter_name == "spark" else None
    rows = []
    for case in CASES:
        if only and case.name not in only:
            continue
        truth = json.loads((out / f"{case.name}.truth.json").read_text())
        job = f"testset-{case.name}"
        seg = SamSegmenter(client, job_id=job) if segmenter_name == "sam" else ClassicalSegmenter()
        interp = SparkInterpreter(client, job_id=job) if interpreter_name == "spark" else GeometricInterpreter()
        result_dir = out / "results" / f"{segmenter_name}-{interpreter_name}" / case.name
        row = {"case": case.name, "expect": case.expect, "thickness_mm": case.thickness_mm}
        try:
            report = await photo_to_stl(out / f"{case.name}.jpg", result_dir, case.thickness_mm, seg, job_id=job,
                                        interpreter=interp)
        except ReforgeError as exc:
            rows.append({**row, "outcome": exc.code, "message": exc.message[:160]})
            continue
        spec = json.loads((result_dir / "spec.json").read_text())
        recon = report["reconstruction"]
        reference = truth["intact_footprint"] or truth["footprint"]
        length, width, _ = report["part"]["overall_mm"]
        analysis = recon["interpretation"].get("analysis") or {}
        row.update({
            "outcome": "model", "valid": report["validation"]["valid"],
            "overall_mm": [length, width], "truth_mm": reference["overall_mm"],
            "error_mm": [round(length - reference["overall_mm"][0], 3), round(width - reference["overall_mm"][1], 3)],
            "outline_mm": [round(v, 3) for v in _outline_distance(spec["outline"]["points"],
                                                                   np.asarray(reference["outline_mm"]))],
            "holes": len(report["part"]["holes"]), "truth_holes": len(reference["holes"]),
            "rebuilt": recon["completion"] is not None,
            "added_area_mm2": None if recon["completion"] is None else recon["completion"]["added_area_mm2"],
            "interpreter": recon["interpretation"]["method"], "object": analysis.get("object_name"),
            "family": analysis.get("family"), "segmenter": report["segmentation"]["method"],
            "notes": [n["code"] for n in recon["verification"] if n["level"] != "info"],
            "excluded_holes": len(report["part"].get("excluded_candidates", [])),
            "cost_usd": round(report["segmentation"]["cost_usd"] + recon["interpretation"]["cost_usd"], 4),
            "warnings": sorted({w["code"] for s in ("calibration", "refinement", "pose")
                                for w in report[s].get("warnings", [])}),
        })
        rows.append(row)
        print(json.dumps(row))
    return rows


def evaluate(out: Path, segmenter: str, interpreter: str, only: list[str] | None) -> None:
    rows = asyncio.run(_evaluate(out, segmenter, interpreter, only))
    path = out / "results" / f"{segmenter}-{interpreter}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1))
    print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--sources", type=Path, required=True)
    gen.add_argument("--out", type=Path, required=True)
    gen.add_argument("--only", nargs="*")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--out", type=Path, required=True)
    ev.add_argument("--segmenter", choices=["classical", "sam"], default="classical")
    ev.add_argument("--interpreter", choices=["geometric", "spark"], default="geometric")
    ev.add_argument("--only", nargs="*")
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.sources, args.out, args.only)
    else:
        evaluate(args.out, args.segmenter, args.interpreter, args.only)


if __name__ == "__main__":
    main()
