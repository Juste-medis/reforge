"""App examples from freely licensed photos of real parts (Wikimedia Commons), placed on the rendered mat.

Each source is a real photo of a real part, published under a licence that allows reuse (CC BY-SA or public domain),
credited in ``assets/samples/CREDITS.md`` and in the app. The part is cut out, its perspective corrected, sized from
a stated basis, optionally broken along a rough fracture, and "photographed" on the rendered mat by the test harness's
simulated phone camera. So every example is a SYNTHETIC COMPOSITE with an exact ground truth: the true outline is the
one this script placed.

Source (downloaded once into the gitignored ``tmp/commons/src2/`` during the licence research):
- ``Gasket01.jpg`` by Miya.m, CC BY-SA 3.0: three real gaskets lying on one sheet of paper, shot slightly off
  vertical. The round flange gasket's outline ellipse fixes the tilt (an affine stretch of 2.7 % turns it back into a
  circle). The photo has no ruler, so the scale is CHOSEN: the flange gasket at Ø100 mm, the outside diameter of a
  JIS B 2404 10K 20A full-face gasket. At that scale its bolt holes measure 15.5 mm (the standard's are 15) and its
  bolt circle 71.7 mm (the standard's is 75): a stated sizing basis, not an identification. The square gasket on the
  same sheet takes the same scale.

Rejected while preparing (see ``docs/EVALUATION.md``, 2026-11-03 night): a public-domain 18-tooth track cog shot at an
angle (its side walls would have joined the outline), and a bicycle sprocket on graph paper whose grid was too faint to
measure the scale from. Copper head gaskets from racing engines were too large for the A4 mat at their real size.

    cd backend && uv run python -m tools.make_commons_samples generate --out ../tmp/commons/composites
    cd backend && uv run python -m tools.make_commons_samples evaluate --out ../tmp/commons/composites [--live]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

import cv2
import numpy as np

from reforge.config import REPO_ROOT
from tools.make_test_photos import Case as PhotoCase
from tools.make_test_photos import _describe, _jpeg, render
from tools.make_wanted_samples import place_custom

SRC = REPO_ROOT / "tmp" / "commons" / "src2"
COG_OD_MM = 12.7 * (0.6 + 1 / math.tan(math.radians(180 / 18)))  # ½-inch chain pitch, 18 teeth: 79.65 mm
SQUARE_HALF_STEP = 110.0  # half the darkness step from the paper (about 7) to the black gasket (about 220)
JIS_10K_20A = {"outside_mm": 100.0, "bolt_circle_mm": 75.0, "bolt_holes_mm": 15.0, "bore_mm": 27.0}

SOURCES = {
    "gasket01": {"file": "0_Gasket01_jpg.jpg", "title": "Gasket01.jpg", "author": "Miya.m",
                 "licence": "CC BY-SA 3.0", "licence_url": "https://creativecommons.org/licenses/by-sa/3.0/",
                 "page": "https://commons.wikimedia.org/wiki/File:Gasket01.jpg"},
    "cog": {"file": "2_Fixed_gear_cog_jpg.jpg", "title": "Fixed gear cog.jpg", "author": "John Reaves",
            "licence": "Public domain", "licence_url": "https://commons.wikimedia.org/wiki/File:Fixed_gear_cog.jpg",
            "page": "https://commons.wikimedia.org/wiki/File:Fixed_gear_cog.jpg"},
    "pakking": {"file": "1_Pakking_jpg.jpg", "title": "1 Pakking.jpg", "author": "Michiel1972",
                "licence": "CC BY-SA 3.0", "licence_url": "https://creativecommons.org/licenses/by-sa/3.0/",
                "page": "https://commons.wikimedia.org/wiki/File:1_Pakking.jpg"},
}


def _label(source: dict, what: str) -> str:
    return (f"SYNTHETIC COMPOSITE: a real photo of {what} ({source['title']} by {source['author']}, "
            f"{source['licence']}, Wikimedia Commons), cut out and placed on a rendered Re-Forge mat at a stated size, "
            "shot by a simulated phone camera. Not a real photo of the mat.")


def _paper_model(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """How far each pixel is from the local paper: (darkness, chroma)."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    light = lab[..., 0]
    paper = cv2.GaussianBlur(cv2.morphologyEx(light, cv2.MORPH_CLOSE,
                                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (121, 121))), (0, 0), 25)
    return paper - light, np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)


def _part_mask(image: np.ndarray, seed_xy: tuple[int, int], dark_t: float, chroma_t: float,
               min_hole_px: int) -> np.ndarray:
    """The part under ``seed_xy``: its filled outer contour, minus the large paper-coloured regions inside it
    (the through-holes). Small paper-like specks inside are texture, not holes."""
    dark, chroma = _paper_model(image)
    ink = ((dark > dark_t) | (chroma > chroma_t)).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    x, y = seed_xy
    around = [i for i in range(1, n) if stats[i, 0] <= x < stats[i, 0] + stats[i, 2]
              and stats[i, 1] <= y < stats[i, 1] + stats[i, 3]]
    if not around:
        raise SystemExit(f"no part around {seed_xy}")
    label = max(around, key=lambda i: stats[i, cv2.CC_STAT_AREA])  # the part whose box holds the seed (even in a bore)
    comp = (labels == label).astype(np.uint8)
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(comp)
    cv2.drawContours(filled, [max(contours, key=cv2.contourArea)], -1, 1, -1)
    # Inside the outline, whatever isn't the part's material is a hole: large regions of it are the through-holes,
    # small specks are texture. Opening then closing smooths each hole's edge at the photo's own resolution.
    material = cv2.morphologyEx(comp, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    voids = ((filled > 0) & (material == 0)).astype(np.uint8)
    voids = cv2.morphologyEx(cv2.morphologyEx(voids, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)), cv2.MORPH_CLOSE,
                             np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(voids)
    mask = filled.copy()
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_hole_px:
            region = (labels == i).astype(np.uint8)
            contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(mask, contours, -1, 0, -1)  # a hole is its whole outline: no islands inside
    return mask


def chip_rim(poly, centre: tuple[float, float], angle_deg: float, keep_radius_mm: float, seed: int,
             roughness_mm: float = 0.5):
    """Break teeth off a disc-like part: everything beyond a rough chord at ``keep_radius_mm`` from the centre,
    centred on ``angle_deg``. Returns (broken, record). Unlike a diameter snap it takes no hole with it, so the
    missing material is teeth only: the commonest damage on a real sprocket."""
    from scipy.ndimage import gaussian_filter1d
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient

    rng = np.random.default_rng(seed)
    a = math.radians(angle_deg)
    u, v = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
    c = np.asarray(centre)
    span = np.arange(-30.0, 30.0001, 0.2)
    rough = (0.6 * np.sin(2 * np.pi * span / 9.0 + rng.uniform(0, 2 * np.pi))
             + gaussian_filter1d(rng.normal(0.0, roughness_mm, len(span)), 1.2))
    line = [c + (keep_radius_mm + r) * u + t * v for t, r in zip(span, rough, strict=True)]
    far = [c + 3 * keep_radius_mm * u + span[-1] * v, c + 3 * keep_radius_mm * u + span[0] * v]
    cut = Polygon([*line, *far]).buffer(0)
    broken = poly.difference(cut)
    broken = max(getattr(broken, "geoms", [broken]), key=lambda g: g.area)
    return orient(broken, 1.0), {"chip_angle_deg": angle_deg, "keep_radius_mm": keep_radius_mm, "seed": seed,
                                 "removed_area_mm2": round(poly.area - broken.area, 2)}


def _round_off(mask: np.ndarray, max_radial_spread: float = 0.03) -> tuple[np.ndarray, list[dict]]:
    """Redraw each near-circular ring (the outline, a hole) as its fitted circle. Die-cut gasket holes are round; the
    cut-out's pixel-level bites are mask noise, not the part, and would make the composite's truth rougher than the
    part. Returns the new mask and what was redrawn."""
    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = np.zeros_like(mask)
    done: list[dict] = []
    order = sorted(range(len(contours)), key=lambda i: hier[0][i][3] >= 0)  # outer rings first, then holes
    for i in order:
        c = contours[i]
        area = cv2.contourArea(c)
        hole = bool(hier[0][i][3] >= 0)
        m = cv2.moments(c)
        if not m["m00"]:
            continue
        x, y = m["m10"] / m["m00"], m["m01"] / m["m00"]
        radii = np.hypot(c[:, 0, 0] - x, c[:, 0, 1] - y)
        spread = float(radii.std() / radii.mean())  # a pixel-stepped circle: about 1 %; a tooth or a slot: far more
        if spread <= max_radial_spread:
            r = math.sqrt(area / math.pi)
            cv2.circle(out, (int(round(x * 16)), int(round(y * 16))), int(round(r * 16)), 0 if hole else 1, -1,
                       cv2.LINE_AA, shift=4)
            done.append({"hole": hole, "centre_px": [round(x, 1), round(y, 1)], "radius_px": round(r, 2),
                         "radial_spread": round(spread, 4)})
        else:
            cv2.drawContours(out, [c], -1, 0 if hole else 1, -1)
    return (out > 0).astype(np.uint8), done


def _fray(broken, intact, seed: int, depth_mm: float = 0.6, step_mm: float = 0.5):
    """Make a torn fibre gasket's edge look torn: jitter only the new edge (where ``broken`` departs from ``intact``)
    by up to ``depth_mm``, at fibre scale. A snapped plastic part's meander alone is too smooth for compressed fibre."""
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient

    rng = np.random.default_rng(seed)
    ring = np.asarray(broken.exterior.coords)[:-1]
    edge = intact.exterior
    dense = []
    for a, b in zip(ring, np.roll(ring, -1, axis=0), strict=True):
        n = max(1, int(np.ceil(np.hypot(*(b - a)) / step_mm)))
        dense.extend(a + (b - a) * t for t in np.arange(n) / n)
    dense = np.asarray(dense)
    from shapely import distance, points

    on_tear = distance(edge, points(dense)) > 0.05  # not on the original outline: the fracture
    centroid = np.asarray(broken.centroid.coords[0])
    out = dense.copy()
    jitter = np.convolve(rng.normal(0.0, depth_mm, len(dense)), np.ones(3) / 3, mode="same")
    radial = (dense - centroid) / np.linalg.norm(dense - centroid, axis=1, keepdims=True)
    out[on_tear] += radial[on_tear] * jitter[on_tear, None]
    frayed = Polygon(out, [np.asarray(r.coords) for r in broken.interiors]).buffer(0)
    frayed = max(getattr(frayed, "geoms", [frayed]), key=lambda g: g.area)
    return orient(frayed, 1.0), {"depth_mm": depth_mm, "step_mm": step_mm, "tear_points": int(on_tear.sum())}


def _circle_fit(points: np.ndarray, iterations: int = 4, clip_px: float = 3.0) -> tuple[np.ndarray, float]:
    """Least-squares circle, refitted without the points more than ``clip_px`` off it (a reflection, a bite)."""
    pts = points.astype(float)
    for _ in range(iterations):
        a = np.column_stack([2 * pts[:, 0], 2 * pts[:, 1], np.ones(len(pts))])
        cx, cy, c = np.linalg.lstsq(a, (pts**2).sum(axis=1), rcond=None)[0]
        r = math.sqrt(c + cx**2 + cy**2)
        keep = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r) <= clip_px
        if keep.sum() < 12 or keep.all():
            break
        pts = pts[keep]
    return np.array([cx, cy]), r


def cog_mask(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """The 18-tooth cog, cleaned of what the angled photo adds: (dewarped image, mask, record).

    GrabCut separates the brass from its tan backdrop. The outline's ellipse sets the tilt correction. The photo shows
    the teeth's side walls along one side; intersecting the toothed outline with its 17 rotations by 20° (the tooth
    pitch) about its centre keeps exactly the face common to every tooth. The bore is the circle fitted to the
    backdrop seen through the centre, a reflection on its wall clipped out; the twelve lightening holes (30° apart)
    are redrawn at their mean fitted radius on their mean bolt circle, at their fitted phase."""
    small = cv2.resize(image, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    gc = np.full((sh, sw), cv2.GC_PR_FGD, np.uint8)
    gc[:12], gc[-12:], gc[:, :12], gc[:, -12:] = cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
    gc[lab[..., 0] > 190] = cv2.GC_FGD
    yy, xx = np.mgrid[:sh, :sw]
    gc[(xx - sw / 2) ** 2 + (yy - sh / 2) ** 2 < (0.14 * sw) ** 2] = cv2.GC_PR_BGD  # the bore
    bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
    cv2.grabCut(small, gc, None, bgd, fgd, 8, cv2.GC_INIT_WITH_MASK)
    fg = cv2.resize(np.isin(gc, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8), (image.shape[1], image.shape[0]),
                    interpolation=cv2.INTER_NEAREST)
    outer0 = _outer(fg)
    warped, warp, affine = _dewarp(image, outer0, return_affine=True)
    fgw = cv2.warpAffine(fg, affine, (warped.shape[1], warped.shape[0]), flags=cv2.INTER_NEAREST)
    outline = _outer(fgw)
    solid = np.zeros_like(fgw)
    cv2.drawContours(solid, [outline], -1, 1, -1)
    # 1. The twelve lightening-hole openings in the face (backdrop plus the holes' shaded walls, darker than brass).
    light = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)[..., 0]
    face = cv2.erode(solid, np.ones((25, 25), np.uint8))
    seen = ((face > 0) & (light < 175)).astype(np.uint8)
    seen = cv2.morphologyEx(cv2.morphologyEx(seen, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)), cv2.MORPH_CLOSE,
                            np.ones((9, 9), np.uint8))
    n2, labels2, stats2, _ = cv2.connectedComponentsWithStats(seen)
    span = math.sqrt(solid.sum() / math.pi)  # the part's equivalent radius
    found = []
    for i in range(1, n2):
        area = int(stats2[i, cv2.CC_STAT_AREA])
        if not math.pi * (0.05 * span) ** 2 <= area <= math.pi * (0.15 * span) ** 2:
            continue
        found.append(_circle_fit(_outer((labels2 == i).astype(np.uint8))[:, 0, :]))
    radii = np.array([r for _, r in found])
    close = np.abs(radii - np.median(radii)) <= 0.15 * np.median(radii)
    keep = [c for (c, _), ok in zip(found, close, strict=True) if ok]
    centres = np.array(keep)
    # 2. The true centre: the circle through the hole centres (on the top face, so free of parallax).
    centre_xy, pcd_r = _circle_fit(centres, clip_px=40.0)
    centre = (float(centre_xy[0]), float(centre_xy[1]))
    teeth = solid.copy()
    for k in range(1, 18):
        rot = cv2.getRotationMatrix2D(centre, 20.0 * k, 1.0)
        teeth &= cv2.warpAffine(solid, rot, (solid.shape[1], solid.shape[0]), flags=cv2.INTER_NEAREST)
    # 3. The bore's radius from the backdrop seen through it (its centre is the part's).
    voids = ((solid > 0) & (fgw == 0)).astype(np.uint8)
    n, labels = cv2.connectedComponents(voids)
    bore_label = labels[int(centre[1]), int(centre[0])]
    _, bore_r = _circle_fit(_outer((labels == bore_label).astype(np.uint8))[:, 0, :])
    bore_c = centre_xy
    angles = np.degrees(np.arctan2(centres[:, 1] - bore_c[1], centres[:, 0] - bore_c[0]))
    phase = float(np.degrees(np.angle(np.mean(np.exp(1j * np.radians(angles * 12)))))) / 12
    hole_r = float(np.median(radii))
    mask = teeth.copy()
    cv2.circle(mask, (int(round(bore_c[0] * 16)), int(round(bore_c[1] * 16))), int(round(bore_r * 16)), 0, -1,
               cv2.LINE_AA, shift=4)
    for k in range(12):
        a = math.radians(phase + 30.0 * k)
        x, y = bore_c[0] + pcd_r * math.cos(a), bore_c[1] + pcd_r * math.sin(a)
        cv2.circle(mask, (int(round(x * 16)), int(round(y * 16))), int(round(hole_r * 16)), 0, -1, cv2.LINE_AA,
                   shift=4)
    # The photo's own openings are darker than brass where the redrawn circles don't cover them (their walls and
    # shadows): repaint those pixels from the surrounding brass, so the composite's holes are exactly its truth's.
    openings = cv2.dilate(((solid > 0) & ((light < 175) | (fgw == 0))).astype(np.uint8), np.ones((9, 9), np.uint8))
    repaint = ((openings > 0) & (mask > 0)).astype(np.uint8)
    warped = cv2.inpaint(warped, repaint, 9, cv2.INPAINT_TELEA)
    record = {"dewarp": warp, "teeth": "outline intersected with its 17 rotations by 20 deg (the tooth pitch)",
              "repainted_px": int(repaint.sum()),
              "centre": "the circle through the lightening-hole centres (top face, no parallax)",
              "bore_radius_px": round(bore_r, 1), "lightening_holes_found": int(len(centres)),
              "lightening_hole_radius_px": round(hole_r, 1), "bolt_circle_radius_px": round(pcd_r, 1),
              "hole_radius_spread_px": round(float(np.std(radii[close])), 2),
              "kept_of_photo_outline": round(float(teeth.sum() / max(solid.sum(), 1)), 3)}
    return warped, (mask > 0).astype(np.uint8), record


def _dewarp(image: np.ndarray, contour: np.ndarray, return_affine: bool = False):
    """Undo the photo's tilt with the affine that turns a round part's outline ellipse back into a circle."""
    (cx, cy), (a1, a2), angle = cv2.fitEllipse(contour)
    major, minor = max(a1, a2), min(a1, a2)
    theta = math.radians(angle if a1 < a2 else angle + 90)  # direction of the minor axis
    u = np.array([math.cos(theta), math.sin(theta)])
    stretch = major / minor
    m = np.eye(2) + (stretch - 1) * np.outer(u, u)
    t = np.array([cx, cy]) - m @ np.array([cx, cy])
    affine = np.hstack([m, t[:, None]])
    h, w = image.shape[:2]
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], float) @ m.T + t
    x0, y0 = np.floor(corners.min(axis=0)).astype(int)
    x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
    affine[:, 2] -= [x0, y0]
    out = cv2.warpAffine(image, affine, (int(x1 - x0), int(y1 - y0)), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REPLICATE)
    info = {"ellipse_axes_px": [round(major, 1), round(minor, 1)], "stretch": round(stretch, 4),
            "minor_axis_deg": round(math.degrees(theta) % 180, 1)}
    return (out, info, affine) if return_affine else (out, info)


def _outer(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(contours, key=cv2.contourArea)


def _holes(mask: np.ndarray) -> list[tuple[float, float, float]]:
    """(cx, cy, diameter) of each hole, in pixels, largest first."""
    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c, h in zip(contours, hier[0], strict=True):
        if h[3] >= 0 and cv2.contourArea(c) > 50:
            (x, y), r = cv2.minEnclosingCircle(c)
            out.append((x, y, 2 * math.sqrt(cv2.contourArea(c) / math.pi)))
    return sorted(out, key=lambda t: -t[2])


def generate(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    jobs = []

    # --- Gasket01: the flange gasket fixes the scale, the square gasket takes it --------------------------------
    raw = cv2.imread(str(SRC / SOURCES["gasket01"]["file"]))
    flange0 = _part_mask(raw, (1300, 1450), dark_t=16, chroma_t=7.5, min_hole_px=4000)
    sheet, warp = _dewarp(raw, _outer(flange0))
    flange = _part_mask(sheet, _seed(flange0, warp, raw, sheet), dark_t=16, chroma_t=7.5, min_hole_px=4000)
    flange, rounded = _round_off(flange)
    _preview(out / "flange_mask.jpg", sheet, flange)
    (fx, fy), _ = cv2.minEnclosingCircle(_outer(flange))
    _, (w_px, h_px), _ = cv2.minAreaRect(_outer(flange))
    od_px = (w_px + h_px) / 2
    holes = _holes(flange)
    bolts = holes[1:5]
    pcd_px = 2 * float(np.mean([math.hypot(x - fx, y - fy) for x, y, _ in bolts]))
    mm_per_px = JIS_10K_20A["outside_mm"] / od_px
    scale = {"method": "CHOSEN: the flange gasket at Ø100 mm (JIS B 2404 10K 20A outside diameter)",
             "photo_bolt_circle_ratio": round(pcd_px / od_px, 3),
             "standard_bolt_circle_ratio": JIS_10K_20A["bolt_circle_mm"] / JIS_10K_20A["outside_mm"],
             "photo_bolt_holes_mm_at_that_scale": round(float(np.mean([d for _, _, d in bolts])) * mm_per_px, 2),
             "standard_bolt_holes_mm": JIS_10K_20A["bolt_holes_mm"], "mm_per_px": round(mm_per_px, 5),
             "dewarp": warp}
    print("gasket01 scale:", json.dumps(scale))

    # The flange gasket only sets the scale. As an example it fails honestly: pale green fibre on white paper (ΔE
    # about 24) leaves its hole edges too rough to fit as circles, so a torn copy can't be rebuilt (EVALUATION).

    # Black rubber on white paper: the edge is where the darkness crosses half of the paper-to-rubber step, not where
    # it first departs from the paper (that would make a light fringe part of the gasket).
    square = _part_mask(sheet, _seed_in(sheet, (515, 440), warp, raw), dark_t=SQUARE_HALF_STEP, chroma_t=255,
                        min_hole_px=1500)
    _preview(out / "square_mask.jpg", sheet, square)
    _, (sw, sh), _ = cv2.minAreaRect(_outer(square))
    square_mm = max(sw, sh) * mm_per_px
    jobs.append(("square_gasket", place_custom(sheet, square, square_mm, 12.0), 1.0, (-3.0, 2.0, 0.5), 312,
                 {"source": "gasket01", "what": "a real square gasket with a round bore and eight passages",
                  "size_basis": f"{square_mm:.1f} mm long side, from the same photo's scale, which is CHOSEN: "
                                "the round flange gasket beside it on the same sheet at Ø100 mm (the outside "
                                "diameter of a JIS B 2404 10K 20A full-face gasket); the photo has no ruler",
                  "thickness_basis": "CHOSEN 1.0 mm", "scale": scale}))
    # --- A broken square gasket was tried and dropped (EVALUATION, 2026-11-04 day) --------------------------------
    # A corner tear takes a whole traced passage: the diagonal mirror fires (support 100 %) but traced holes don't
    # pair, so the passage never comes back (half-inferred rebuild, rightly unshipped). And every hole-free chip is
    # at most 2.4 mm deep (the passages blanket the part), which drowns in the rubber grain live (AXIS_WEAK). Files
    # removed.
    for _stale in ("square_broken",):
        (out / f"{_stale}.jpg").unlink(missing_ok=True)
        (out / f"{_stale}.truth.json").unlink(missing_ok=True)

    # --- Same sheet: the green round flange gasket (blue tried and dropped) --------------------------------
    # The blue ring was tried and dropped: a white reflection streak fragments its mask (an extra void plus a merged
    # round hole), and inpainting it would idealise real hole edges. EVALUATION.
    # The green flange gasket (the scale anchor itself, Ø100 mm): pale fibre, so every hole edge stays rough and
    # the holes are traced, never fitted as circles.
    _, (gw, gh), _ = cv2.minAreaRect(_outer(flange))
    green_mm = max(gw, gh) * mm_per_px
    jobs.append(("green_gasket", place_custom(sheet, flange, green_mm, 18.0), 1.0, (-2.0, -3.0, -0.5), 316,
                 {"source": "gasket01", "what": "a real green fibre flange gasket: bore plus four bolt holes",
                  "size_basis": f"{green_mm:.1f} mm outside diameter (the JIS-anchor gasket itself)",
                  "thickness_basis": "CHOSEN 1.0 mm", "scale": scale}))

    # --- The 18-tooth cog: size from the chain standard --------------------------------------------------------
    cog_img, cog, cog_info = cog_mask(cv2.imread(str(SRC / SOURCES["cog"]["file"])))
    _preview(out / "cog_mask.jpg", cog_img, cog)
    placed_cog = place_custom(cog_img, cog, COG_OD_MM, 0.0)
    c = placed_cog.polygon.centroid
    placed_cog.intact = placed_cog.polygon
    # Four teeth chipped with realistic raggedness (roughness 0.5 mm). The teeth are detected and filled, but
    # ~10 mm of ragged chip edge stays exactly-uncovered, so the rebuild is honestly declined (EVALUATION): small
    # ragged chips are below the mirror's exact-cover ability. Smoothing the chip is backwards — the break then
    # matches its mirror and turns invisible instead of rebuildable.
    placed_cog.polygon, placed_cog.symmetry = chip_rim(placed_cog.polygon, (c.x, c.y), 200.0, 33.0, seed=7)
    jobs.append(("cog_broken", placed_cog, 3.0, (2.0, 3.0, -1.0), 313,
                 {"source": "cog", "what": "a real 18-tooth chain cog, stamped 1/8 x 18T",
                  "size_basis": f"{COG_OD_MM:.2f} mm outside diameter, from the chain standard: ½-inch pitch, "
                                "18 teeth, p·(0.6 + cot(180°/18))",
                  "thickness_basis": "CHOSEN 3.0 mm, typical of a ⅛-inch cog",
                  "break": "four teeth broken off digitally, along a rough chord that takes no hole",
                  "cleaning": cog_info}))

    # --- The beige Pakking: tried and dropped -----------------------------------------------------------------------
    # The right lobe (oblong port plus three bolt holes) was game but never cleared live: mirrored into a full
    # gasket, the doubled shadow reads as background (SAM, 20 mm short); placed alone, its straight cut edge
    # reads as a cropped photo (Spark FAMILY_UNSUPPORTED). EVALUATION. Files removed.
    for _stale in ("beige_pakking", "beige_chipped"):
        (out / f"{_stale}.jpg").unlink(missing_ok=True)
        (out / f"{_stale}.truth.json").unlink(missing_ok=True)

    for name, placed_p, thickness, tilt, seed, provenance in jobs:
        source = SOURCES[provenance["source"]]
        case = PhotoCase(name, provenance["what"], thickness, tilt=tilt)
        image, camera = render(case, placed_p, seed=seed)
        path = out / f"{name}.jpg"
        _jpeg(image, path)
        truth = {"label": _label(source, provenance["what"]), "source": source, "provenance": provenance,
                 "thickness_to_enter_mm": thickness, "camera": camera, "footprint": _describe(placed_p.polygon),
                 "intact_footprint": None if placed_p.intact is None else _describe(placed_p.intact),
                 "break": placed_p.symmetry or None}
        (out / f"{name}.truth.json").write_text(json.dumps(truth, indent=1))
        ref = truth["intact_footprint"] or truth["footprint"]
        print(f"{name}: {truth['footprint']['overall_mm']} mm photographed, {ref['overall_mm']} mm intact, "
              f"{len(truth['footprint']['holes'])} holes photographed / {len(ref['holes'])} intact")


def _preview(path: Path, image: np.ndarray, mask: np.ndarray) -> None:
    over = image.copy()
    over[mask == 0] = (over[mask == 0] * 0.4).astype(np.uint8)
    over[cv2.Canny(mask * 255, 50, 150) > 0] = (0, 0, 255)
    cv2.imwrite(str(path), cv2.resize(over, None, fx=0.5, fy=0.5))


def _seed(mask_before: np.ndarray, warp: dict, raw: np.ndarray, sheet: np.ndarray) -> tuple[int, int]:
    ys, xs = np.nonzero(mask_before)
    return _seed_in(sheet, (int(np.median(xs)), int(np.median(ys))), warp, raw, on_part=mask_before)


def _seed_in(sheet: np.ndarray, xy_raw: tuple[int, int], warp: dict, raw: np.ndarray,
             on_part: np.ndarray | None = None) -> tuple[int, int]:
    """Map a raw-image point (a part's centre) into the dewarped sheet."""
    h, w = raw.shape[:2]
    theta = math.radians(warp["minor_axis_deg"])
    u = np.array([math.cos(theta), math.sin(theta)])
    m = np.eye(2) + (warp["stretch"] - 1) * np.outer(u, u)
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], float) @ m.T
    p = m @ np.asarray(xy_raw, float) - corners.min(axis=0)
    return int(round(p[0])), int(round(p[1]))


async def _evaluate(out: Path, live: bool) -> None:
    from reforge.config import Settings
    from reforge.errors import ReforgeError
    from reforge.meta_api.client import MetaClient
    from reforge.pipeline import photo_to_stl
    from reforge.reasoning.interpret import GeometricInterpreter, SparkInterpreter
    from reforge.vision.segment import ClassicalSegmenter, SamSegmenter

    client = MetaClient(Settings()) if live else None
    for truth_path in sorted(out.glob("*.truth.json")):
        name = truth_path.name.removesuffix(".truth.json")
        truth = json.loads(truth_path.read_text())
        seg = SamSegmenter(client, job_id=f"commons-{name}") if live else ClassicalSegmenter()
        interp = SparkInterpreter(client, job_id=f"commons-{name}") if live else GeometricInterpreter()
        result_dir = out / "results" / ("live" if live else "offline") / name
        try:
            report = await photo_to_stl(out / f"{name}.jpg", result_dir, truth["thickness_to_enter_mm"], seg,
                                        job_id=f"commons-{name}", interpreter=interp)
        except ReforgeError as exc:
            print(json.dumps({"case": name, "outcome": exc.code, "message": exc.message[:200]}))
            continue
        recon = report["reconstruction"]
        ref = truth["intact_footprint"] or truth["footprint"]
        size = report["part"]["size_mm"]
        analysis = recon["interpretation"].get("analysis") or {}
        print(json.dumps({"case": name, "valid": report["validation"]["valid"],
                          "size_mm": [size["length"], size["width"]], "truth_bbox_mm": ref["overall_mm"],
                          "holes": [(h["kind"], h["status"], h.get("diameter_mm")) for h in report["part"]["holes"]],
                          "truth_holes": [h["equivalent_diameter_mm"] for h in ref["holes"]],
                          "rebuilt": recon["completion"] is not None,
                          "notes": [n["code"] for n in recon["verification"]],
                          "object": analysis.get("object_name"), "family": analysis.get("family"),
                          "cost_usd": round(report["segmentation"]["cost_usd"]
                                            + recon["interpretation"]["cost_usd"], 4),
                          "seconds": round(sum(report["timings_s"].values()), 1)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--out", type=Path, required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--out", type=Path, required=True)
    ev.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.out)
    else:
        asyncio.run(_evaluate(args.out, args.live))


if __name__ == "__main__":
    main()
