"""App examples from the user's own part photos (``tmp/wanteds/``): cut out, placed at a stated size on the
rendered mat, "photographed" by the test harness's simulated phone camera. These are SYNTHETIC COMPOSITES, not real
photos; every size, thickness and break below is recorded in the truth file with its basis.

Run from ``backend/``:
    uv run python -m tools.make_wanted_samples generate --out ../tmp/wanted_parts/composites
    uv run python -m tools.make_wanted_samples evaluate --out ../tmp/wanted_parts/composites [--live]

Parts (user-provided photos, kept in gitignored ``tmp/wanteds/``):
- ``sprocket``: a real 21-tooth chain sprocket, stamped 06A21 (visible in the photo). The photo was shot at
  ~38° off vertical, so it is first dewarped (affine stretch of the tip ellipse back to a circle); without that,
  perspective alone breaks the bore's concentricity past what any axis search can pin. Placed at 70 mm outside
  diameter (a 06A chain has a 9.525 mm pitch, so a 21-tooth sprocket's pitch diameter is 63.9 mm and its outside
  diameter about 69.7 mm). Thickness CHOSEN 5.0 mm. The bore is cut at the fitted disk centre (a turned bore is
  concentric; only its radius comes from the visible opening). One side is snapped off along a rough fracture
  (teeth missing), rebuilt by mirror.
- ``carrier``: a real cast-iron automotive hub carrier (bearing bore plus bolt holes), intact, measured as
  photographed. Long side CHOSEN 140 mm, thickness CHOSEN 8.0 mm. The bolt holes are dark discs in the photo's opaque
  alpha; each compact dark disc fully inside the part is cut as the through-hole it is (verified on the overlay).
- ``heart``: a real flat metal trinket (a heart, engraved) from the user's mat photo IMG_1066, intact and with
  its right lobe-tip chipped off (rebuilt by mirror). MEASURED 51.8 mm wide (caliper, tmp/coeur_a_mesurer.jpg);
  the height follows the photo's aspect (shot slightly off vertical). Thickness CHOSEN 3.0 mm.
- ``key``: a real flat key from the user's mat photo IMG_1069, intact (teeth traced as photographed, ring hole
  fitted round). Long side CHOSEN 55 mm, thickness CHOSEN 2.0 mm. NOT bundled: Spark's family verdict flips
  between runs and SAM undershoots the teeth by 0.9 mm (EVALUATION).
- ``sprocket`` again: a second digital break (another seed) of the same 06A21 photo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import struct
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from reforge.capture.photometry import srgb_to_linear
from reforge.geometry.contour import smooth_closed
from tools.make_test_photos import (
    CENTRE,
    Placed,
    _apply,
    _describe,
    _extrapolate,
    _jpeg,
    _reflect,
    _rings,
    _similarity,
    render,
)
from tools.make_test_photos import Case as PhotoCase

LABEL = ("SYNTHETIC COMPOSITE for the app examples: a user-provided photo of a real part placed on a rendered mat, "
         "shot by a simulated phone camera. Not a real photo.")
SRC = Path("../tmp/wanteds")
SRC2 = Path("../tmp/realphotos.2")  # the user's own mat photos (heart, key)
SRC3 = Path("../tmp/realpictures")  # more of the user's mat photos (second heart shot)
SRC4 = Path("../tmp/realpicts")  # vendor-style product shots the user dropped in (no mat, no scale)
PART_PX = 40  # source pixels of padding kept around the part for texture extrapolation


def _tip_points(mask: np.ndarray) -> np.ndarray:
    """Local radius maxima of the outer contour (the teeth tips), in source pixels."""
    contours, _ = cv2.findContours((mask * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)
    centroid = contour.mean(axis=0)
    radii = np.hypot(*(contour - centroid).T)
    return np.array([contour[i] for i in range(len(contour))
                     if radii[i] == radii[max(0, i - 8):i + 9].max()])


def dewarp_tilt(image_bgr: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Undo the photo's tilt (the sprocket was shot at ~38°): the tips lie on a circle, imaged as an ellipse, so
    stretching the minor axis back (PCA of the tips, no angle-convention traps) restores the top-down view this
    pipeline's flat footprint needs. Returns (image, mask, record) with the disk centre in dewarped pixels."""
    tips = _tip_points(mask)
    use = np.ones(len(tips), bool)
    for tol in (0.25, 0.12, 0.06, 0.06, 0.06):  # reweighted PCA: the reflection sheen corrupts some tips,
        centred = tips[use] - tips[use].mean(axis=0)  # so the tolerance tightens and the fit is redone
        sigma, axes = np.linalg.svd(centred, full_matrices=False)[1:]  # PC1 = major axis
        spread = float(np.sqrt(len(tips[use]) / 2))  # uniform ring samples: sigma = semi-axis * spread
        a, b = float(sigma[0]) / spread, float(sigma[1]) / spread
        phi = np.arctan2(centred @ axes[1], centred @ axes[0])
        expect = a * b / np.hypot(b * np.cos(phi), a * np.sin(phi))
        resid = np.abs(np.hypot(*centred.T) - expect) / expect
        full = np.ones(len(tips))
        full[np.nonzero(use)[0]] = resid
        use = full < tol
        if use.sum() < 10:  # never collapse: keep the 10 best
            use = np.zeros(len(tips), bool)
            use[np.argsort(full)[:10]] = True
    centred = tips[use] - tips[use].mean(axis=0)
    sigma, axes = np.linalg.svd(centred, full_matrices=False)[1:]
    major, minor = axes[0], axes[1]
    ratio = float(sigma[1] / sigma[0])
    rot = np.stack([major, minor])
    stretch = rot.T @ np.diag([1.0, 1.0 / ratio]) @ rot
    centre = tips[use].mean(axis=0)
    warp = np.column_stack([stretch, centre - stretch @ centre])
    h, w = mask.shape
    flat = cv2.warpAffine(image_bgr, warp, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    grown = cv2.warpAffine((mask * 255).astype(np.uint8), warp, (w, h), flags=cv2.INTER_NEAREST,
                           borderValue=0)
    record = {"tilt_deg": round(float(np.degrees(np.arccos(ratio))), 1), "minor_major_ratio": round(ratio, 4),
              "tip_points": len(tips), "tip_inliers": int(use.sum()),
              "disk_centre_px": [round(float(v), 1) for v in warp @ np.append(centre, 1.0)]}
    check = _tip_points((grown > 128).astype(np.uint8))
    centred_check = check - check.mean(axis=0)
    check_sigma = np.linalg.svd(centred_check, full_matrices=False)[1]
    record["dewarped_tip_axis_ratio"] = round(float(check_sigma[1] / check_sigma[0]), 4)
    record["dewarped_tip_radius_px"] = {"mean": round(float(np.hypot(*centred_check.T).mean()), 1)}
    return flat, (grown > 128).astype(np.uint8), record


def sprocket_mask(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """(mask, image, info): the tilt-corrected part mask (uint8 0/1) with the bore cut at the disk centre: a
    lathe-turned bore is concentric with the blank, while the photo's tilted opening is not, so the centre comes
    from the fitted disk and only the radius from the visible opening (white crescent plus dark bore wall)."""
    from tools.make_test_photos import cut_out

    mask = cut_out(image_bgr, "largest:0").astype(np.uint8)
    flat, grown, warp_info = dewarp_tilt(image_bgr, mask)
    gray = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
    ys, xs = np.nonzero(grown)
    centroid = np.array([xs.mean(), ys.mean()])
    radius = float(np.median(np.hypot(xs - centroid[0], ys - centroid[1])))
    yy, xx = np.mgrid[0:grown.shape[0], 0:grown.shape[1]]
    near = np.hypot(xx - centroid[0], yy - centroid[1]) < 0.35 * radius
    opening = (((gray > 170) | (gray < 95)) & (grown > 0) & near).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(opening)
    if n < 2:
        raise ValueError("sprocket bore opening not found")
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    pts = np.column_stack(np.nonzero(lab == biggest)[::-1]).astype(np.float32)
    (_, _), r = cv2.minEnclosingCircle(pts)
    cx, cy = warp_info["disk_centre_px"]
    bore = np.zeros_like(grown)
    cv2.circle(bore, (int(round(cx)), int(round(cy))), int(round(r)) + 1, 1, -1)
    # The cut runs through mixed texture (bore wall, crescent, bright metal), which would wobble the traced edge;
    # a real bore rim is uniform machined metal, so paint that ring (documented here, invisible in practice).
    yy, xx = np.mgrid[0:flat.shape[0], 0:flat.shape[1]].astype(np.float32)
    dist = np.hypot(xx - cx, yy - cy)
    clean = flat[(dist > r + 12) & (dist < r + 30) & (grown > 0)]
    metal = np.median(clean.reshape(-1, 3), axis=0)
    flat[(dist < r + 10).astype(bool)] = metal
    info = {"dewarp": warp_info, "bore_centre_px": [cx, cy], "bore_centre_basis": "fitted disk centre (concentric)",
            "bore_radius_px": round(float(r), 1),
            "bore_rim_paint": {"colour_bgr": [round(float(v), 1) for v in metal], "radius_px": round(float(r) + 10, 1)},
            "opening_pixels": int((lab == biggest).sum()),
            "part_pixels": int(grown.sum())}
    return (grown & (1 - bore)).astype(np.uint8), flat, info


def carrier_mask(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """(mask, bgr, info): the photo's own alpha as the outline (the big bore is already a hole in it), plus one cut
    disc per compact dark disc fully inside the part: the bolt through-holes the alpha kept opaque."""
    bgr = rgba[:, :, :3].copy()
    mask = (rgba[:, :, 3] > 128).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (lab == biggest).astype(np.uint8)
    holes = (1 - mask).astype(np.uint8)
    hn, hl, hs, _ = cv2.connectedComponentsWithStats(holes)
    h, w = mask.shape
    bore = np.zeros_like(mask)
    for i in range(1, hn):
        x, y, cw, ch, area = hs[i]
        if x > 0 and y > 0 and x + cw < w and y + ch < h and area > 0.02 * mask.sum():
            bore[hl == i] = 1
    value = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    inside = cv2.erode(mask, np.ones((7, 7), np.uint8))
    # Bolt openings are dark pits: grow each local minimum adaptively (a fixed threshold merges the smaller
    # openings into the casting's shadow masses, and Hough finds mostly phantom circles in the texture).
    from scipy.ndimage import minimum_filter

    pits = ((value == minimum_filter(value, size=15)) & (value < 60) & (inside > 0)).astype(np.uint8)
    _, pit_lab, _, pit_centres = cv2.connectedComponentsWithStats(pits)
    h, w = mask.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cuts = []
    for i in range(1, pit_lab.max() + 1):
        sx, sy = int(pit_centres[i][0]), int(pit_centres[i][1])
        flood = value.copy()
        cv2.floodFill(flood, np.zeros((h + 2, w + 2), np.uint8), (sx, sy), 255, loDiff=25, upDiff=25,
                      flags=4)
        region = ((flood == 255) & (value < 90)).astype(np.uint8)
        area = int(region.sum())
        if not (80 < area < 1500) or (region & (1 - inside)).any():
            continue
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        per = cv2.arcLength(contours[0], True)
        compact = 4 * np.pi * cv2.contourArea(contours[0]) / (per * per) if per > 0 else 0.0
        r = float(np.sqrt(area / np.pi))
        ys, xs = np.nonzero(region)
        cx, cy = float(xs.mean()), float(ys.mean())
        dist = np.hypot(xx - cx, yy - cy)
        ring = value[(dist >= r) & (dist < r + 6) & (mask > 0)]
        contrast = float(ring.mean() - value[int(round(cy)), int(round(cx))]) if ring.size else -1.0
        if compact < 0.55 or contrast <= 20:
            continue
        if any(abs(cx - c["centre_px"][0]) < 12 and abs(cy - c["centre_px"][1]) < 12 for c in cuts):
            continue  # same opening twice
        cuts.append({"centre_px": [round(cx, 1), round(cy, 1)], "radius_px": round(r, 1),
                     "area_px": area, "compactness": round(compact, 2), "rim_contrast": round(contrast, 1)})
        cv2.circle(mask, (int(round(cx)), int(round(cy))), int(round(r)), 0, -1)
    info = {"bolt_holes_cut": cuts, "bore_pixels": int(bore.sum()), "part_pixels": int(mask.sum()),
            "note": "three bolt through-holes cut; smaller dark recesses left as texture"}
    return mask, bgr, info


def _mat_centre_crop(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The dark part in the middle of a user mat photo: Otsu on the centre window (the markers live near the
    edges), closed, largest component. Returns (crop_bgr, mask)."""
    h, w = image_bgr.shape[:2]
    x0, y0, x1, y1 = int(w * 0.28), int(h * 0.30), int(w * 0.72), int(h * 0.62)
    crop = image_bgr[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (th == 0).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(dark)
    big = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])
    return crop, (lab == big).astype(np.uint8)


def heart_mask(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """(mask, crop, info): the engraved heart, interior specks (engraving glints) filled — the heart has no holes."""
    crop, comp = _mat_centre_crop(image_bgr)
    inv = 1 - comp
    n2, lab2, stats2, _ = cv2.connectedComponentsWithStats(inv)
    outside = max(range(1, n2), key=lambda i: stats2[i, cv2.CC_STAT_AREA])
    filled = 0
    for i in range(1, n2):
        if i != outside:
            filled += 1
            comp[lab2 == i] = 1
    ys, xs = np.nonzero(comp)
    info = {"bbox_px": [int(xs.max() - xs.min()), int(ys.max() - ys.min())],
            "interior_specks_filled": filled, "part_pixels": int(comp.sum())}
    return comp, crop, info


def _white_bg_cutout(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Dark part on a white product-shot background: Otsu, closed, largest component. Returns (crop, mask)."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = cv2.morphologyEx((th == 0).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(dark)
    big = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])
    return image_bgr, (lab == big).astype(np.uint8)


def key_mask(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """(mask, crop, info): the key, teeth traced as photographed; the ring hole (its shadowed rim reads dark,
    only the bright centre opens) completed to the fitted disk — a punched ring hole is round."""
    crop, comp = _mat_centre_crop(image_bgr)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(cv2.medianBlur(gray, 5), cv2.HOUGH_GRADIENT, 1, 200, param1=100, param2=20,
                               minRadius=20, maxRadius=60)
    info = {"hough_circles": None if circles is None else np.round(circles[0], 1).tolist(),
            "part_pixels": int(comp.sum())}
    if circles is not None:
        contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        filled = np.zeros_like(comp)
        cv2.drawContours(filled, [max(contours, key=cv2.contourArea)], -1, 1, -1)
        for cand in np.round(circles[0]).astype(int):
            x, y, r = (int(v) for v in cand)
            if 0 <= y < comp.shape[0] and 0 <= x < comp.shape[1] and filled[y, x] > 0:
                cv2.circle(comp, (x, y), r, 0, -1)  # the centre may sit on the opening or the dark rim alike
                info["ring_hole_px"] = [x, y, r]
                break
    return comp, crop, info


def place_custom(image_bgr: np.ndarray, mask: np.ndarray, length_mm: float, rotate_deg: float) -> Placed:
    """``place_photo`` for a caller-supplied mask (same geometry and texture path)."""
    ys, xs = np.nonzero(mask)
    pad = PART_PX
    bx0, by0 = max(xs.min() - pad, 0), max(ys.min() - pad, 0)
    bx1, by1 = min(xs.max() + pad, image_bgr.shape[1]), min(ys.max() + pad, image_bgr.shape[0])
    crop, mcrop = image_bgr[by0:by1, bx0:bx1], mask[by0:by1, bx0:bx1]
    outer, holes = _rings(mcrop)
    centre = outer.mean(axis=0)
    _, (rw, rh), rect_angle = cv2.minAreaRect(outer.astype(np.float32))
    long_px = max(rw, rh)
    angle = (90.0 - rect_angle if rw >= rh else -rect_angle) + rotate_deg
    src_to_mm = _similarity(length_mm / long_px, angle, centre, CENTRE)
    spacing = 0.12
    sigma = max(1.5 * length_mm / long_px, 0.03)
    rings = [smooth_closed(_apply(src_to_mm, r), sigma, spacing) for r in (outer, *holes)]
    polygon = orient(Polygon(rings[0], rings[1:]).buffer(0), 1.0)
    trusted = cv2.erode(mcrop, np.ones((9, 9), np.uint8))
    texture = _extrapolate(srgb_to_linear(crop), trusted)
    return Placed(polygon, texture, src_to_mm)


def snap_disc(poly: Polygon, seed: int, through: tuple[float, float] | None = None) -> tuple[Polygon, Polygon, dict]:
    """Break a disc-like part like ``snap_side`` does elongated ones: best mirror axis anywhere (teeth repeat every
    360/21 deg, so a sweep finds a tooth axis), exact symmetrisation, then a rough side fracture. Returns
    (broken, intact, record). ``through`` pins the axis point (the fitted disk centre): the area centroid can sit
    off-centre on a photo outline and would turn the bore into a lens."""
    through = through or (poly.centroid.x, poly.centroid.y)
    best = (0.0, 0.0)
    for angle in np.arange(0.0, 180.0, 0.25):
        mirrored = _reflect(poly, angle, through)
        iou = poly.intersection(mirrored).area / poly.union(mirrored).area
        if iou > best[1]:
            best = (float(angle), float(iou))
    angle = best[0]
    sym = poly.intersection(_reflect(poly, angle, through))
    intact = orient(max(getattr(sym, "geoms", [sym]), key=lambda g: g.area), 1.0)
    a = np.radians(angle)
    u, v = np.array([np.cos(a), np.sin(a)]), np.array([-np.sin(a), np.cos(a)])
    c = np.array(through)
    pts = np.asarray(intact.exterior.coords) - c
    along, across = pts @ u, pts @ v
    rng = np.random.default_rng(seed)
    side = rng.choice([-1.0, 1.0])
    half = across.max() if side > 0 else -across.min()
    span = np.arange(along.min() - 5, along.max() + 5, 0.25)
    amp = 0.02 * (along.max() - along.min())
    meander = sum(amp * k * np.sin(2 * np.pi * span / (wl * (along.max() - along.min())) + rng.uniform(0, 2 * np.pi))
                  for k, wl in ((1.0, 0.45), (0.5, 0.17), (0.25, 0.07)))
    offset = 0.45 * half + meander + gaussian_filter1d(rng.normal(0.0, 0.1, len(span)), 1.0)
    line = [c + s * u + side * o * v for s, o in zip(span, offset, strict=True)]
    far = [c + span[-1] * u + side * 3 * half * v, c + span[0] * u + side * 3 * half * v]
    cut = Polygon([*line, *far]).buffer(0)
    broken = intact.difference(cut)
    broken = max(getattr(broken, "geoms", [broken]), key=lambda g: g.area)
    record = {"mirror_axis_deg": round(angle, 2), "photo_outline_mirror_iou": round(best[1], 4),
              "intact_outline": "the photo outline intersected with its mirror image",
              "removed_area_mm2": round(intact.area - broken.area, 2), "seed": seed}
    return orient(broken, 1.0), intact, record


def _relabel(jpeg: bytes) -> bytes:
    """Swap the EXIF description for this script's label (``_jpeg`` stamps the test set's)."""
    import io

    exif = Image.open(io.BytesIO(jpeg)).getexif()
    exif[0x010E] = LABEL
    payload = b"Exif\x00\x00" + exif.tobytes()
    app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    pos, out = 2, bytearray(b"\xff\xd8")
    while pos < len(jpeg):
        marker = jpeg[pos:pos + 2]
        if marker == b"\xff\xda":
            out += app1 + jpeg[pos:]
            break
        length = struct.unpack(">H", jpeg[pos + 2:pos + 4])[0]
        segment = jpeg[pos:pos + 2 + length]
        if not (marker == b"\xff\xe1" and segment[4:10] == b"Exif\x00\x00"):
            out += segment
        pos += 2 + length
    return bytes(out)


def _save_preview(path: Path, image_bgr: np.ndarray, mask: np.ndarray, extra: list | None = None) -> None:
    over = image_bgr.copy()
    over[mask == 0] = (over[mask == 0] * 0.45).astype(np.uint8)
    edge = cv2.Canny((mask * 255).astype(np.uint8), 50, 150)
    over[edge > 0] = (0, 0, 255)
    for (cx, cy, r) in extra or []:
        cv2.circle(over, (int(round(cx)), int(round(cy))), int(round(r)), (255, 0, 0), 2)
    cv2.imwrite(str(path), over)


def generate(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    jobs = []

    sprocket_img = cv2.imread(str(SRC / "Image collée (3).png"), cv2.IMREAD_COLOR)
    sprocket_msk, sprocket_flat, bore_info = sprocket_mask(sprocket_img)
    _save_preview(out / "sprocket_mask.png", sprocket_flat, sprocket_msk,
                  [(bore_info["bore_centre_px"][0], bore_info["bore_centre_px"][1], bore_info["bore_radius_px"])])
    placed = place_custom(sprocket_flat, sprocket_msk, 70.0, 0.0)
    ys, xs = np.nonzero(sprocket_msk)  # src_to_mm speaks crop pixels: same crop as place_custom
    crop_c = np.array(bore_info["bore_centre_px"]) - [max(xs.min() - PART_PX, 0), max(ys.min() - PART_PX, 0)]
    disk_mat = _apply(placed.src_to_mm, np.array([crop_c]))[0]
    placed.polygon, placed.intact, placed.symmetry = snap_disc(placed.polygon, 11, through=(disk_mat[0], disk_mat[1]))
    jobs.append(("sprocket_broken", placed, 5.0, (3.0, -2.0, 1.0), 200,
                 {"source_file": "tmp/wanteds/Image collée (3).png",
                  "what": "a real 21-tooth chain sprocket, stamped 06A21 (mark visible in the photo)",
                  "size_basis": "CHOSEN 70.0 mm outside diameter: a 06A chain's 9.525 mm pitch gives a 21-tooth "
                                "pitch diameter of 63.9 mm and an outside diameter of about 69.7 mm",
                  "thickness_basis": "CHOSEN 5.0 mm, a plausible single-sprocket thickness",
                  "bore": bore_info}))
    intact = place_custom(sprocket_flat, sprocket_msk, 70.0, 25.0)  # same sprocket, whole, another pose
    jobs.append(("sprocket_intact", intact, 5.0, (-3.0, 2.0, 0.5), 202,
                 {"source_file": "tmp/wanteds/Image collée (3).png",
                  "what": "the same real 21-tooth chain sprocket (06A21), intact: nothing to rebuild",
                  "size_basis": "CHOSEN 70.0 mm outside diameter (same basis as the broken one)",
                  "thickness_basis": "CHOSEN 5.0 mm, a plausible single-sprocket thickness",
                  "bore": bore_info}))

    carrier_rgba = cv2.imread(str(SRC / "Image collée (5).png"), cv2.IMREAD_UNCHANGED)
    carrier_msk, carrier_bgr, carrier_info = carrier_mask(carrier_rgba)
    _save_preview(out / "carrier_mask.png", carrier_bgr, carrier_msk,
                  [(c["centre_px"][0], c["centre_px"][1], c["radius_px"]) for c in carrier_info["bolt_holes_cut"]])
    placed_c = place_custom(carrier_bgr, carrier_msk, 140.0, 8.0)
    jobs.append(("carrier_intact", placed_c, 8.0, (-2.0, 3.0, 0.0), 201,
                 {"source_file": "tmp/wanteds/Image collée (5).png",
                  "what": "a real cast-iron automotive hub carrier (bearing bore plus bolt holes), intact",
                  "size_basis": "CHOSEN 140.0 mm long side (no marking to derive it from)",
                  "thickness_basis": "CHOSEN 8.0 mm, a plausible bracket thickness",
                  "holes": carrier_info}))

    heart_img = cv2.imread(str(SRC2 / "IMG_1066.jpeg"), cv2.IMREAD_COLOR)
    heart_msk, heart_crop, heart_info = heart_mask(heart_img)
    _save_preview(out / "heart_mask.png", heart_crop, heart_msk, [])
    placed_h = place_custom(heart_crop, heart_msk, 51.8, -10.0)
    jobs.append(("heart_intact", placed_h, 3.0, (2.0, -2.0, 1.0), 203,
                 {"source_file": "tmp/realphotos.2/IMG_1066.jpeg",
                  "what": "a real flat metal heart (engraved trinket), intact: nothing to rebuild",
                  "size_basis": "MEASURED 51.8 mm wide (caliper, tmp/coeur_a_mesurer.jpg); the height follows the "
                                "photo's aspect (shot slightly off vertical)",
                  "thickness_basis": "CHOSEN 3.0 mm, a plausible trinket thickness",
                  "mask": heart_info}))
    from tools.make_commons_samples import chip_rim as _chip
    from tools.make_test_photos import mirror_axis as _maxis

    _hang, _hiou = _maxis(placed_h.polygon, 90.0, span_deg=45.0)
    _hc0 = (placed_h.polygon.centroid.x, placed_h.polygon.centroid.y)
    _hsym = placed_h.polygon.union(_reflect(placed_h.polygon, _hang, _hc0))
    _hintact = orient(max(getattr(_hsym, "geoms", [_hsym]), key=lambda g: g.area), 1.0)
    placed_h.polygon = _hintact  # the real trinket is hand-finished (±1 mm); the blank (union with its mirror,
    # as cast) is the symmetric truth an intersection would undersize against the measured rebuild
    hc = _hintact.centroid
    _hpts = np.asarray(_hintact.exterior.coords)
    _htip = _hpts[_hpts[:, 0].argmax()]
    _hang2 = float(np.degrees(np.arctan2(_htip[1] - hc.y, _htip[0] - hc.x)))
    heart_broken, heart_record = _chip(_hintact, (hc.x, hc.y), _hang2, 21.0, seed=31, roughness_mm=0.3)
    heart_record["symmetrised"] = {"mirror_axis_deg": round(_hang, 2), "photo_outline_mirror_iou": round(_hiou, 4)}
    placed_hb = place_custom(heart_crop, heart_msk, 51.8, -10.0)
    placed_hb.polygon, placed_hb.intact, placed_hb.symmetry = heart_broken, _hintact, heart_record
    jobs.append(("heart_broken", placed_hb, 3.0, (-2.0, 2.0, -1.0), 204,
                 {"source_file": "tmp/realphotos.2/IMG_1066.jpeg",
                  "what": "the same metal heart with its right lobe-tip chipped off, rebuilt by mirror",
                  "size_basis": "MEASURED 51.8 mm wide intact (same basis as the intact one)",
                  "thickness_basis": "CHOSEN 3.0 mm",
                  "break": "a ragged chip off the right lobe-tip", "mask": heart_info}))

    heart2_img = cv2.imread(str(SRC3 / "IMG_1061.jpeg"), cv2.IMREAD_COLOR)
    heart2_msk, heart2_crop, heart2_info = heart_mask(heart2_img)
    _save_preview(out / "heart2_mask.png", heart2_crop, heart2_msk, [])
    placed_h2 = place_custom(heart2_crop, heart2_msk, 51.8, 12.0)
    from tools.make_test_photos import mirror_axis as _maxis2

    _h2ang, _h2iou = _maxis2(placed_h2.polygon, 90.0, span_deg=45.0)
    _h2c = (placed_h2.polygon.centroid.x, placed_h2.polygon.centroid.y)
    _h2sym = placed_h2.polygon.union(_reflect(placed_h2.polygon, _h2ang, _h2c))
    placed_h2.polygon = orient(max(getattr(_h2sym, "geoms", [_h2sym]), key=lambda g: g.area), 1.0)
    heart2_info["symmetrised"] = {"mirror_axis_deg": round(_h2ang, 2), "photo_outline_mirror_iou": round(_h2iou, 4)}
    jobs.append(("heart2_intact", placed_h2, 3.0, (-3.0, -2.0, 1.5), 207,
                 {"source_file": "tmp/realpictures/IMG_1061.jpeg",
                  "what": "the same metal heart from the user's second mat photo, intact",
                  "size_basis": "MEASURED 51.8 mm wide (same trinket, same caliper as the first heart shot)",
                  "thickness_basis": "CHOSEN 3.0 mm",
                  "mask": heart2_info}))
    _h2i = placed_h2.polygon  # already symmetrised (union with mirror, as cast): the intact truth
    _h2c = _h2i.centroid
    _h2pts = np.asarray(_h2i.exterior.coords)
    _h2tip = _h2pts[_h2pts[:, 0].argmin()]  # the LEFT lobe-tip: variety with heart_broken's right chip
    _h2ang3 = float(np.degrees(np.arctan2(_h2tip[1] - _h2c.y, _h2tip[0] - _h2c.x)))
    heart2_broken, h2_record = _chip(_h2i, (_h2c.x, _h2c.y), _h2ang3, 21.0, seed=37, roughness_mm=0.3)
    h2_record["symmetrised"] = heart2_info["symmetrised"]
    placed_h2b = place_custom(heart2_crop, heart2_msk, 51.8, 12.0)
    placed_h2b.polygon, placed_h2b.intact, placed_h2b.symmetry = heart2_broken, _h2i, h2_record
    jobs.append(("heart2_broken", placed_h2b, 3.0, (3.0, 2.0, -1.5), 210,
                 {"source_file": "tmp/realpictures/IMG_1061.jpeg",
                  "what": "the same metal heart from the second mat photo, left lobe-tip chipped off",
                  "size_basis": "MEASURED 51.8 mm wide intact (same basis as the intact one)",
                  "thickness_basis": "CHOSEN 3.0 mm",
                  "break": "a ragged chip off the left lobe-tip", "mask": heart2_info}))

    key_img = cv2.imread(str(SRC2 / "IMG_1069.jpeg"), cv2.IMREAD_COLOR)
    key_msk, key_crop, key_info = key_mask(key_img)
    _save_preview(out / "key_mask.png", key_crop, key_msk,
                  [tuple(key_info["ring_hole_px"])] if "ring_hole_px" in key_info else [])
    placed_k = place_custom(key_crop, key_msk, 55.0, 15.0)
    jobs.append(("key_intact", placed_k, 2.0, (3.0, 2.0, 0.5), 205,
                 {"source_file": "tmp/realphotos.2/IMG_1069.jpeg",
                  "what": "a real flat key, intact: teeth traced as photographed, ring hole fitted round",
                  "size_basis": "CHOSEN 55.0 mm long, a plausible key; the photo has no ruler",
                  "thickness_basis": "CHOSEN 2.0 mm, a plausible key-blade thickness",
                  "mask": key_info}))

    panel_img = cv2.imread(str(SRC4 / "filtre-bmw-alpina.png"), cv2.IMREAD_COLOR)
    panel_crop, panel_msk = _white_bg_cutout(panel_img)
    _save_preview(out / "panel_mask.png", panel_crop, panel_msk, [])
    placed_p = place_custom(panel_crop, panel_msk, 150.0, 5.0)
    from tools.make_test_photos import mirror_axis as _maxis3

    _pang, _piou = _maxis3(placed_p.polygon, 0.0, span_deg=45.0)
    _pc = (placed_p.polygon.centroid.x, placed_p.polygon.centroid.y)
    _psym = placed_p.polygon.union(_reflect(placed_p.polygon, _pang, _pc))
    placed_p.polygon = orient(max(getattr(_psym, "geoms", [_psym]), key=lambda g: g.area), 1.0)
    jobs.append(("panel_intact", placed_p, 30.0, (2.0, 2.0, -0.5), 208,
                 {"source_file": "tmp/realpicts/filtre-bmw-alpina.png",
                  "what": "a pleated panel air filter (rectangle, symmetrised as made: the product shot is angled)",
                  "size_basis": "CHOSEN 150.0 mm long side (product shot, no scale; a small panel filter)",
                  "thickness_basis": "CHOSEN 30.0 mm, a plausible panel depth",
                  "symmetrised": {"mirror_axis_deg": round(_pang, 2), "photo_outline_mirror_iou": round(_piou, 4)}}))

    fob_img = cv2.imread(str(SRC4 / "M Modecar Coque de clé.png"), cv2.IMREAD_COLOR)
    _fh, _fw = fob_img.shape[:2]
    blade_crop, blade_msk = _white_bg_cutout(fob_img[:, : int(_fw * 0.38)])
    _save_preview(out / "blade_mask.png", blade_crop, blade_msk, [])
    placed_b = place_custom(blade_crop, blade_msk, 50.0, -8.0)
    jobs.append(("blade_intact", placed_b, 2.5, (-2.0, -2.0, 1.0), 209,
                 {"source_file": "tmp/realpicts/M Modecar Coque de clé.png (blade cropped out, fob excluded)",
                  "what": "an uncut key blade (blank), intact: no bitting, no holes",
                  "size_basis": "CHOSEN 50.0 mm long (product shot, no scale; a plausible blade)",
                  "thickness_basis": "CHOSEN 2.5 mm, a plausible blade thickness"}))

    placed_r2 = place_custom(sprocket_flat, sprocket_msk, 70.0, -15.0)  # same sprocket, another break
    ys2, xs2 = np.nonzero(sprocket_msk)
    crop_c2 = np.array(bore_info["bore_centre_px"]) - [max(xs2.min() - PART_PX, 0), max(ys2.min() - PART_PX, 0)]
    disk_mat2 = _apply(placed_r2.src_to_mm, np.array([crop_c2]))[0]
    placed_r2.polygon, placed_r2.intact, placed_r2.symmetry = snap_disc(
        placed_r2.polygon, 12, through=(disk_mat2[0], disk_mat2[1]))
    jobs.append(("sprocket_broken_r2", placed_r2, 5.0, (-2.0, -3.0, -0.5), 206,
                 {"source_file": "tmp/wanteds/Image collée (3).png",
                  "what": "the same real 21-tooth chain sprocket (06A21) with another side snapped off",
                  "size_basis": "CHOSEN 70.0 mm outside diameter (same basis as the broken one)",
                  "thickness_basis": "CHOSEN 5.0 mm",
                  "bore": bore_info}))

    for name, placed_p, thickness, tilt, seed, provenance in jobs:
        case = PhotoCase(name, provenance["what"], thickness, tilt=tilt)
        image, camera = render(case, placed_p, seed=seed)
        _jpeg(image, out / f"{name}.jpg")
        (out / f"{name}.jpg").write_bytes(_relabel((out / f"{name}.jpg").read_bytes()))
        truth = {"label": LABEL, "provenance": provenance, "thickness_to_enter_mm": thickness, "camera": camera,
                 "footprint": _describe(placed_p.polygon),
                 "intact_footprint": None if placed_p.intact is None else _describe(placed_p.intact),
                 "break": placed_p.symmetry or None}
        (out / f"{name}.truth.json").write_text(json.dumps(truth, indent=1))
        print(f"{name}: {truth['footprint']['overall_mm']} mm, {len(truth['footprint']['holes'])} holes"
              + (", broken" if placed_p.symmetry else ""))


async def _run(out: Path, live: bool) -> None:
    from reforge.config import Settings
    from reforge.errors import ReforgeError
    from reforge.meta_api.client import MetaClient
    from reforge.pipeline import photo_to_stl
    from reforge.reasoning.interpret import GeometricInterpreter, SparkInterpreter
    from reforge.vision.segment import ClassicalSegmenter, SamSegmenter

    client = MetaClient(Settings()) if live else None
    for name in ("sprocket_broken", "sprocket_intact", "carrier_intact", "heart_intact", "heart_broken",
                 "heart2_intact", "heart2_broken", "key_intact", "sprocket_broken_r2", "panel_intact", "blade_intact"):
        truth = json.loads((out / f"{name}.truth.json").read_text())
        seg = SamSegmenter(client, job_id=f"wanted-{name}") if live else ClassicalSegmenter()
        interp = SparkInterpreter(client, job_id=f"wanted-{name}") if live else GeometricInterpreter()
        result_dir = out / "results" / ("live" if live else "offline") / name
        try:
            report = await photo_to_stl(out / f"{name}.jpg", result_dir, truth["thickness_to_enter_mm"], seg,
                                        job_id=f"wanted-{name}", interpreter=interp)
        except ReforgeError as exc:
            print(json.dumps({"case": name, "outcome": exc.code, "message": exc.message[:200]}))
            continue
        recon = report["reconstruction"]
        reference = truth["intact_footprint"] or truth["footprint"]
        length, width, _ = report["part"]["overall_mm"]
        analysis = recon["interpretation"].get("analysis") or {}
        print(json.dumps({"case": name, "outcome": "model", "valid": report["validation"]["valid"],
                          "overall_mm": [length, width], "truth_mm": reference["overall_mm"],
                          "holes": len(report["part"]["holes"]), "truth_holes": len(reference["holes"]),
                          "rebuilt": recon["completion"] is not None, "object": analysis.get("object_name"),
                          "family": analysis.get("family"),
                          "cost_usd": round(report["segmentation"]["cost_usd"]
                                            + recon["interpretation"]["cost_usd"], 4)}))


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
        asyncio.run(_run(args.out, args.live))


if __name__ == "__main__":
    main()
