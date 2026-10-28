"""Mirror-symmetry search on a part's footprint, with measured support and a bootstrap uncertainty.

Candidates come from equal-diameter hole pairs (their perpendicular bisector), the principal axes of the outline,
and a 2° sweep in which each direction's offset is the mode of the midpoints of point pairs facing each other.

Scoring reflects the outline and the holes, and reports them separately. A mirror image that lands within τ of the
(non-fracture) outline is a match; one whose nearest outline point is on a suspected fracture is *no evidence*,
since the material there is missing or damaged; anything else is a mismatch. *Support* = matches / (matches +
mismatches), over the outline only. A hole whose mirror centre lands on a hole of the same diameter is a hole match;
one that lands on intact material or outside the part is a hole mismatch. An axis that more holes contradict than
confirm is ranked last and never used.

Why holes are kept apart: on a part with a broken end, the long straight edges can't fix where the axis sits along
them, and the intact end lands where material is missing (no evidence). A vertical axis 3.4 mm off then kept 93 %
of a mixed score and rebuilt the bracket 6.9 mm too long (pipeline run on a synthetic photo, 2026-10-28). Only the
holes pin the axis there, and ``offset_ambiguity_mm`` reports how far it could slide where nothing pins it.

Refinement is ICP-like: a point p and the outline point q nearest its mirror image are partners, so the midpoints
(p + q)/2 lie on the axis, as do the midpoints of matched hole pairs (weighted); the axis is their weighted
total-least-squares line. A block bootstrap over the outline pairs gives the angle and offset uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

from reforge.geometry.contour import resample_closed

TAU_MM = 0.3
SWEEP_STEP_DEG = 2.0
SAMPLE_MM = 0.5
DENSE_MM = 0.05
ICP_ITERATIONS = 30
BOOTSTRAP_ROUNDS = 64
BLOCK_POINTS = 20
DUPLICATE_ANGLE_DEG = 2.0
DUPLICATE_OFFSET_MM = 1.0
HOLE_WEIGHT = 20.0  # in the axis fit only: a matched hole pair's midpoint counts as this many outline midpoints


@dataclass(frozen=True)
class MirrorAxis:
    axis_id: str
    point: tuple[float, float]  # the axis point nearest the outline's centroid
    angle_deg: float  # direction of the axis line, in [0, 180)
    support: float
    inlier_rms_mm: float
    sources: tuple[str, ...]
    hole_matches: int = 0  # holes whose mirror lands on a hole of the same diameter
    hole_mismatches: int = 0
    offset_ambiguity_mm: float | None = None  # how far the axis slides with support within 1 % and no hole lost

    @property
    def contradicted_by_holes(self) -> bool:
        return self.hole_mismatches > self.hole_matches
    angle_sigma_deg: float | None = None  # 1σ, block bootstrap
    offset_sigma_mm: float | None = None  # 1σ, perpendicular, at the centroid

    @property
    def direction(self) -> np.ndarray:
        a = np.radians(self.angle_deg)
        return np.array([np.cos(a), np.sin(a)])

    @property
    def normal(self) -> np.ndarray:
        a = np.radians(self.angle_deg)
        return np.array([-np.sin(a), np.cos(a)])

    def reflect(self, points: np.ndarray) -> np.ndarray:
        p = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        n = self.normal
        return p - 2.0 * np.outer((p - np.asarray(self.point)) @ n, n)


def _axis(point: np.ndarray, direction: np.ndarray, centroid: np.ndarray, sources: tuple[str, ...]) -> MirrorAxis:
    d = direction / np.linalg.norm(direction)
    if d[1] < 0 or (abs(d[1]) < 1e-12 and d[0] < 0):
        d = -d
    foot = point + ((centroid - point) @ d) * d
    angle = float(np.degrees(np.arctan2(d[1], d[0]))) % 180.0
    return MirrorAxis("A?", (float(foot[0]), float(foot[1])), angle, 0.0, 0.0, sources)


@dataclass(frozen=True)
class _Outline:
    samples: np.ndarray  # every SAMPLE_MM, fracture excluded: the points that get reflected
    tree: cKDTree  # over the whole outline every DENSE_MM
    dense: np.ndarray
    dense_fracture: np.ndarray  # bool per dense point: on a suspected fracture
    polygon: Polygon
    holes: list[tuple[str, np.ndarray, float]]
    centroid: np.ndarray


def _prepare(outline_mm: np.ndarray, holes: list[tuple[str, tuple[float, float], float]] | None,
             exclude: np.ndarray | None) -> _Outline:
    samples = resample_closed(outline_mm, SAMPLE_MM)
    dense = resample_closed(outline_mm, DENSE_MM)
    centroid = samples.mean(axis=0)
    dense_fracture = np.zeros(len(dense), dtype=bool)
    if exclude is not None and len(exclude):
        fracture = cKDTree(np.asarray(exclude).reshape(-1, 2))
        samples = samples[fracture.query(samples)[0] > SAMPLE_MM]
        dense_fracture = fracture.query(dense)[0] <= SAMPLE_MM
    polygon = Polygon(outline_mm).buffer(0)
    shapely.prepare(polygon)
    hole_list = [(hid, np.asarray(c, dtype=np.float64), float(r)) for hid, c, r in holes or []]
    return _Outline(samples, cKDTree(dense), dense, dense_fracture, polygon, hole_list, centroid)


def _hole_pairs(axis: MirrorAxis, o: _Outline) -> tuple[list[tuple[np.ndarray, np.ndarray]], int]:
    """Matched (centre, partner centre) pairs, and how many holes contradict the axis."""
    pairs, mismatches = [], 0
    for _, centre, radius in o.holes:
        image = axis.reflect(centre)[0]
        partner = min(o.holes, key=lambda h: float(np.linalg.norm(h[1] - image)))
        if (np.linalg.norm(partner[1] - image) <= TAU_MM
                and abs(partner[2] - radius) <= max(0.05, 0.03 * max(radius, partner[2]))):
            pairs.append((centre, partner[1]))
        elif not o.dense_fracture[o.tree.query(image)[1]]:
            mismatches += 1
    return pairs, mismatches


def _score(axis: MirrorAxis, o: _Outline) -> MirrorAxis:
    dist, idx = o.tree.query(axis.reflect(o.samples))
    fracture = o.dense_fracture[idx]
    match = (dist <= TAU_MM) & ~fracture
    mismatch = ~match & ~fracture  # landing nearest a fracture is no evidence either way
    hole_pairs, hole_mismatches = _hole_pairs(axis, o)
    good, bad = int(match.sum()), int(mismatch.sum())
    support = float(good / max(good + bad, 1))
    rms = float(np.sqrt(np.mean(dist[match] ** 2))) if match.any() else float("inf")
    return replace(axis, support=support, inlier_rms_mm=rms, hole_matches=len(hole_pairs),
                   hole_mismatches=hole_mismatches)


def _pairs(axis: MirrorAxis, o: _Outline) -> tuple[np.ndarray, np.ndarray]:
    """(sample points, partners) of the matched outline pairs under ``axis``."""
    dist, idx = o.tree.query(axis.reflect(o.samples))
    keep = (dist <= TAU_MM) & ~o.dense_fracture[idx]
    return o.samples[keep], o.dense[idx[keep]]


def _tls_axis(p: np.ndarray, q: np.ndarray, centroid: np.ndarray, sources: tuple[str, ...],
              anchors: list[tuple[np.ndarray, np.ndarray]] = ()) -> MirrorAxis | None:
    mid = (p + q) / 2
    weights = np.ones(len(mid))
    if anchors:
        mid = np.vstack([mid, [(a + b) / 2 for a, b in anchors]])
        weights = np.concatenate([weights, np.full(len(anchors), HOLE_WEIGHT)])
    if len(mid) < 4:
        return None
    centre = (mid * weights[:, None]).sum(axis=0) / weights.sum()
    direction = np.linalg.svd((mid - centre) * np.sqrt(weights)[:, None], full_matrices=False)[2][0]
    return _axis(centre, direction, centroid, sources)


def _refine(axis: MirrorAxis, o: _Outline) -> MirrorAxis:
    current = _score(axis, o)
    for _ in range(ICP_ITERATIONS):
        p, q = _pairs(current, o)
        nxt = _tls_axis(p, q, o.centroid, current.sources, _hole_pairs(current, o)[0])
        if nxt is None:
            break
        nxt = _score(nxt, o)
        moved = abs(nxt.angle_deg - current.angle_deg) + float(np.linalg.norm(np.subtract(nxt.point, current.point)))
        if nxt.support + 1e-9 < current.support and nxt.inlier_rms_mm >= current.inlier_rms_mm:
            break
        current = nxt
        if moved < 1e-7:
            break
    return current


def _bootstrap(axis: MirrorAxis, o: _Outline, rng: np.random.Generator) -> MirrorAxis:
    p, q = _pairs(axis, o)
    anchors = _hole_pairs(axis, o)[0]
    n_blocks = len(p) // BLOCK_POINTS
    if n_blocks < 4:
        return axis
    angles, offsets = [], []
    for _ in range(BOOTSTRAP_ROUNDS):
        picks = rng.integers(0, n_blocks, n_blocks)
        idx = np.concatenate([np.arange(b * BLOCK_POINTS, (b + 1) * BLOCK_POINTS) for b in picks])
        boot = _tls_axis(p[idx], q[idx], o.centroid, axis.sources, anchors)
        if boot is None:
            continue
        delta = (boot.angle_deg - axis.angle_deg + 90.0) % 180.0 - 90.0
        angles.append(delta)
        offsets.append(float((np.asarray(boot.point) - np.asarray(axis.point)) @ axis.normal))
    if len(angles) < BOOTSTRAP_ROUNDS // 2:
        return axis
    return replace(axis, angle_sigma_deg=float(np.std(angles)), offset_sigma_mm=float(np.std(offsets)))


def _sweep(o: _Outline) -> list[MirrorAxis]:
    pts = resample_closed(o.samples, 2.0)  # about 100-200 points: pairwise midpoints stay cheap
    found = []
    for angle in np.arange(0.0, 180.0, SWEEP_STEP_DEG):
        a = np.radians(angle)
        u, n = np.array([np.cos(a), np.sin(a)]), np.array([-np.sin(a), np.cos(a)])
        t, s = pts @ u, pts @ n
        i, j = np.triu_indices(len(pts), k=1)
        facing = np.abs(t[i] - t[j]) <= 1.0
        if facing.sum() < 4:
            continue
        mids = (s[i][facing] + s[j][facing]) / 2
        bins = np.arange(mids.min() - 0.25, mids.max() + 0.5, 0.5)
        hist, edges = np.histogram(mids, bins=bins)
        peak = int(np.argmax(hist))
        near = mids[np.abs(mids - (edges[peak] + 0.25)) <= 0.5]
        offset = float(np.median(near))
        found.append(_axis(offset * n, u, o.centroid, ("sweep",)))
    return found


def find_mirror_axes(outline_mm: np.ndarray, holes: list[tuple[str, tuple[float, float], float]] | None = None, *,
                     exclude_mm: np.ndarray | None = None, keep: int = 3, seed: int = 0) -> list[MirrorAxis]:
    """The best mirror axes of a footprint, refined and ranked by support then RMS, with ids A0, A1, …

    ``holes`` are (id, centre, radius). ``exclude_mm`` are points (a suspected fracture) left out of the support.
    """
    o = _prepare(outline_mm, holes, exclude_mm)
    candidates: list[MirrorAxis] = []
    for k, (id_a, ca, ra) in enumerate(holes or []):
        for id_b, cb, rb in (holes or [])[k + 1:]:
            if abs(ra - rb) <= max(0.05, 0.03 * max(ra, rb)):
                ca_, cb_ = np.asarray(ca), np.asarray(cb)
                chord = cb_ - ca_
                candidates.append(_axis((ca_ + cb_) / 2, np.array([-chord[1], chord[0]]), o.centroid,
                                        (f"hole pair {id_a}/{id_b}",)))
    centred = o.samples - o.centroid
    for direction in np.linalg.svd(centred, full_matrices=False)[2]:
        candidates.append(_axis(o.centroid, direction, o.centroid, ("principal axis",)))
    candidates += _sweep(o)

    scored = sorted((_score(c, o) for c in candidates), key=_rank)
    refined: list[MirrorAxis] = []
    for cand in scored:
        if len(refined) >= keep + 2:
            break
        r = _refine(cand, o)
        twin = next((x for x in refined if _same(x, r)), None)
        if twin is None:
            refined.append(r)
        else:  # keep every source that led to the same axis: agreement is evidence
            merged = tuple(dict.fromkeys(twin.sources + r.sources))
            refined[refined.index(twin)] = replace(twin, sources=merged)
    refined.sort(key=_rank)
    rng = np.random.default_rng(seed)
    return [replace(_bootstrap(a, o, rng), axis_id=f"A{i}", offset_ambiguity_mm=_ambiguity(a, o))
            for i, a in enumerate(refined[:keep])]


def _ambiguity(axis: MirrorAxis, o: _Outline) -> float:
    """Width of the offset range around ``axis`` that keeps its support (within 0.01) and its hole matches."""
    best = axis.support
    ok = []
    for shift in np.arange(-5.0, 5.0001, 0.1):
        moved = _score(replace(axis, point=tuple(np.asarray(axis.point) + shift * axis.normal)), o)
        ok.append(moved.support >= best - 0.01 and moved.hole_matches >= axis.hole_matches)
    ok = np.asarray(ok)
    centre = len(ok) // 2
    lo = hi = centre
    while lo > 0 and ok[lo - 1]:
        lo -= 1
    while hi < len(ok) - 1 and ok[hi + 1]:
        hi += 1
    return float((hi - lo) * 0.1)


def _rank(axis: MirrorAxis) -> tuple:
    return (axis.contradicted_by_holes, -axis.support, axis.inlier_rms_mm)


def _same(a: MirrorAxis, b: MirrorAxis) -> bool:
    d_angle = abs((a.angle_deg - b.angle_deg + 90.0) % 180.0 - 90.0)
    d_offset = abs(float((np.asarray(b.point) - np.asarray(a.point)) @ a.normal))
    return d_angle <= DUPLICATE_ANGLE_DEG and d_offset <= DUPLICATE_OFFSET_MM


def local_support(axis: MirrorAxis, points_mm: np.ndarray, outline_mm: np.ndarray) -> float:
    """Fraction of ``points_mm`` (part of the outline) whose mirror image lands within τ of the outline."""
    tree = cKDTree(resample_closed(outline_mm, DENSE_MM))
    dist, _ = tree.query(axis.reflect(points_mm))
    return float((dist <= TAU_MM).mean()) if len(dist) else 0.0


def rescore(axis: MirrorAxis, outline_mm: np.ndarray, holes: list[tuple[str, tuple[float, float], float]] | None,
            exclude_mm: np.ndarray | None, *, seed: int = 0) -> MirrorAxis:
    """``axis`` refined and re-measured with a different set of excluded (fracture) points; its id is kept."""
    o = _prepare(outline_mm, holes, exclude_mm)
    refined = _refine(axis, o)
    if not _same(axis, refined):  # refinement wandered off: keep the given axis, re-measured
        refined = _score(axis, o)
    return replace(_bootstrap(refined, o, np.random.default_rng(seed)), axis_id=axis.axis_id, sources=axis.sources,
                   offset_ambiguity_mm=_ambiguity(refined, o))


def mirror_gain_mm2(axis: MirrorAxis, outline_mm: np.ndarray) -> float:
    """Area the mirror image would add to the footprint, with no assumption about where the part broke."""
    observed = Polygon(outline_mm).buffer(0)
    mirror = Polygon(axis.reflect(outline_mm)).buffer(0)
    return float(mirror.difference(observed).buffer(-0.1, join_style="mitre").buffer(0.1, join_style="mitre").area)
