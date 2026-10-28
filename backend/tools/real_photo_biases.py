"""Two real-photo biases, simulated exactly (`docs/EVALUATION.md`, 2026-10-27).

Run from `backend/`: `uv run python tools/real_photo_biases.py`.

1. Height parallax: a prism of thickness h seen by a pinhole camera at height H above the mat, measured through the
   mat-plane (z = 0) homography. A slice at height z projects onto z = 0 scaled about the nadir N by H / (H - z).
   "S∩S/m" is the two-copy correction first planned (PLAN v0.4); the pipeline now uses an exact one
   (`reforge.geometry.height`).
2. Edge threshold under the camera tone curve: optics blur linear light, the JPEG stores sRGB-encoded values.
   "harness" is the pre-2026-10-27 synthetic renderer, which blurred encoded values.
"""

import cv2
import numpy as np
from scipy.stats import norm
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from reforge.geometry.circle import fit_circle

HOLES = ((-30.0, 0.0), (30.0, 0.0))


def bracket() -> Polygon:
    plate = box(-40, -14, 40, 14).buffer(-4, quad_segs=32).buffer(4, quad_segs=32)
    for x, y in HOLES:
        plate = plate.difference(Point(x, y).buffer(2.1, quad_segs=128))
    return plate


def silhouette(part: Polygon, nadir: tuple[float, float], cam_h: float, h: float, n: int = 120) -> Polygon:
    m = cam_h / (cam_h - h)
    return unary_union([affinity.scale(part, s, s, origin=(*nadir, 0)) for s in np.linspace(1.0, m, n)])


def measure(poly: Polygon) -> dict:
    x0, y0, x1, y1 = poly.bounds
    holes = []
    for ring in poly.interiors:
        fit = fit_circle(np.asarray(ring.coords)[:-1])
        true = min(HOLES, key=lambda c: np.hypot(fit.center[0] - c[0], fit.center[1] - c[1]))
        holes.append((fit.diameter, float(np.hypot(fit.center[0] - true[0], fit.center[1] - true[1])),
                      fit.max_deviation))
    holes.sort(key=lambda t: t[0])
    return {"L": x1 - x0, "W": y1 - y0, "holes": holes}


def fmt(r: dict) -> str:
    hs = " | ".join(f"Ø{d:.3f} c+{c:.3f} dev{v:.3f}" for d, c, v in r["holes"])
    return f"L {r['L']:.3f}  W {r['W']:.3f}  || {hs}"


print("== 1. Height parallax: bracket 80 x 28 mm, holes Ø4.200 at x = ±30, thickness h = 3.0 mm ==")
part = bracket()
print("truth             ", fmt(measure(part)))
for cam_h in (250.0, 400.0, 500.0, 750.0):
    for nadir in ((0.0, 0.0), (50.0, 30.0)):
        obs = silhouette(part, nadir, cam_h, 3.0)
        m = cam_h / (cam_h - 3.0)
        corr = obs.intersection(affinity.scale(obs, 1 / m, 1 / m, origin=(*nadir, 0)))
        print(f"H {cam_h:4.0f} nadir {str(nadir):12s} observed  ", fmt(measure(obs)))
        print(f"{'':27s}S∩S/m      ", fmt(measure(corr)))

print("\n== 2. Edge threshold: t = 0.5 crossing in OpenCV Lab (as refine.py), black/grey part on white paper ==")
print("bias < 0: boundary sits inside the part (part measured smaller, holes larger), in pixels")


def srgb_encode(y):
    return np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(np.clip(y, 0, None), 1 / 2.4) - 0.055)


def srgb_decode(v):
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _step_integral(u: np.ndarray, sigma: float) -> np.ndarray:
    """∫ Φ(u/σ) du: integrating a Gaussian-blurred step over a pixel."""
    return u * norm.cdf(u / sigma) + sigma * norm.pdf(u / sigma)


def crossing(paper_v: int, part_v: int, sigma: float, domain: str, phase: float) -> float:
    xs = np.arange(-30, 31) + phase  # pixel centres; true edge at x = 0, part on the left
    frac_paper = _step_integral(xs + 0.5, sigma) - _step_integral(xs - 0.5, sigma)  # pixel-integrated blurred step
    if domain == "linear":  # real camera: optics blur radiance, then the tone curve encodes it
        yp, yq = srgb_decode(paper_v / 255), srgb_decode(part_v / 255)
        v = srgb_encode(yq + (yp - yq) * frac_paper) * 255
    else:  # current synthetic harness: blur applied to encoded values
        v = part_v + (paper_v - part_v) * frac_paper
    row = np.clip(np.round(v), 0, 255).astype(np.uint8)
    img = np.repeat(row[None, :, None], 3, axis=2)
    lab = cv2.cvtColor(img.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)[0]
    paper, prt = lab[-1], lab[0]
    d = prt - paper
    t = ((lab - paper) @ d) / (d @ d)
    i = int(np.nonzero((t[:-1] >= 0.5) & (t[1:] < 0.5))[0][0])
    return float(xs[i] + (t[i] - 0.5) / (t[i] - t[i + 1]))


def linearised_crossing(paper_v: int, part_v: int, sigma: float, phase: float) -> float:
    """Proposed fix: threshold the linear-light coverage instead of Lab."""
    xs = np.arange(-30, 31) + phase
    frac_paper = _step_integral(xs + 0.5, sigma) - _step_integral(xs - 0.5, sigma)
    yp, yq = srgb_decode(paper_v / 255), srgb_decode(part_v / 255)
    v = np.clip(np.round(srgb_encode(yq + (yp - yq) * frac_paper) * 255), 0, 255)
    y = srgb_decode(v / 255)
    t = (y - y[-1]) / (y[0] - y[-1])
    i = int(np.nonzero((t[:-1] >= 0.5) & (t[1:] < 0.5))[0][0])
    return float(xs[i] + (t[i] - 0.5) / (t[i] - t[i + 1]))


phases = np.linspace(0, 1, 16, endpoint=False)
for part_v in (30, 55, 120):
    for sigma in (0.6, 1.0, 1.5):
        enc = np.mean([crossing(235, part_v, sigma, "encoded", p) for p in phases])
        lin = np.mean([crossing(235, part_v, sigma, "linear", p) for p in phases])
        fix = np.mean([linearised_crossing(235, part_v, sigma, p) for p in phases])
        print(f"paper 235 / part {part_v:3d}  σ {sigma:.1f} px:  harness(encoded blur) {enc:+.3f} px   "
              f"real camera (linear blur) {lin:+.3f} px   linear-light threshold {fix:+.3f} px")
