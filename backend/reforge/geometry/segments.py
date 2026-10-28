"""Outline segments: numbered pieces for Set-of-Mark prompting, each with its geometric evidence.

A moulded outline is mostly lines and arcs. The footprint is decomposed into primitive pieces by recursive
splitting (wherever the best line or circle misses by more than a tolerance, split at the point farthest from the
chord), then adjacent pieces are merged back while one primitive still fits. A fracture shows up as a run of short
pieces. Segments S0…Sn group the pieces for labelling: every long piece is a segment of its own kind, and runs of
three or more short pieces become ``irregular`` segments of about ``IRREGULAR_SEGMENT_MM``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reforge.geometry.circle import fit_circle
from reforge.geometry.contour import resample_closed

SPACING_MM = 0.2
MIN_EPS_MM = 0.05  # a piece is a line or an arc if it fits within this (raised for noisy edges)
SHORT_PIECE_MM = 2.5  # pieces shorter than this are detail; three or more in a row are irregular
MIN_PIECE_MM = 0.6  # pieces are never split below this length
IRREGULAR_SEGMENT_MM = 8.0
CORNER_WINDOW_MM = 1.0


@dataclass(frozen=True)
class Piece:
    start: int  # indices into the closed, resampled outline; end is shared with the next piece's start
    end: int
    kind: str  # "line" | "arc"
    max_dev_mm: float
    length_mm: float


@dataclass(frozen=True)
class Segment:
    seg_id: str
    start: int  # first point index (inclusive)
    end: int  # last point index (inclusive); segments tile the outline in order
    kind: str  # "line" | "arc" | "irregular"
    length_mm: float
    pieces: int
    fit_rms_mm: float  # residual of the best single line or circle over the whole segment
    midpoint_mm: tuple[float, float]


@dataclass(frozen=True)
class SegmentedOutline:
    points: np.ndarray  # (n, 2), resampled every SPACING_MM, same orientation as the input, starting at a corner
    segments: tuple[Segment, ...]
    eps_mm: float

    def labels(self) -> np.ndarray:
        """The segment index of every point."""
        out = np.empty(len(self.points), dtype=np.int32)
        for i, seg in enumerate(self.segments):
            out[seg.start:seg.end + 1] = i
        return out

    def by_id(self, seg_id: str) -> Segment:
        for seg in self.segments:
            if seg.seg_id == seg_id:
                return seg
        raise KeyError(seg_id)

    def span(self, seg: Segment) -> np.ndarray:
        """The segment's points, including the next segment's first point so consecutive spans touch."""
        stop = seg.end + 2
        closed = np.vstack([self.points, self.points[:1]])
        return closed[seg.start:stop]


def _length(pts: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


def fit_primitive(pts: np.ndarray) -> tuple[str, float, float]:
    """(kind, max deviation, rms) of the better of a line and a circle through ``pts``."""
    centre = pts.mean(axis=0)
    normal = np.linalg.svd(pts - centre, full_matrices=False)[2][1]
    dev = np.abs((pts - centre) @ normal)
    best = ("line", float(dev.max()), float(np.sqrt(np.mean(dev**2))))
    if len(pts) >= 5:
        fit = fit_circle(pts)
        if 0.3 <= fit.radius <= 1000.0:
            dev_c = np.abs(np.linalg.norm(pts - np.asarray(fit.center), axis=1) - fit.radius)
            if dev_c.max() < best[1]:
                best = ("arc", float(dev_c.max()), float(np.sqrt(np.mean(dev_c**2))))
    return best


def _split(pts: np.ndarray, a: int, b: int, eps: float, out: list[Piece]) -> None:
    seg = pts[a:b + 1]
    length = _length(seg)
    kind, dev, _ = fit_primitive(seg)
    min_pts = int(round(MIN_PIECE_MM / SPACING_MM))
    if dev <= eps or length <= 2 * MIN_PIECE_MM or b - a < 2 * min_pts:
        out.append(Piece(a, b, kind, dev, length))
        return
    chord = seg[-1] - seg[0]
    norm = float(np.linalg.norm(chord))
    if norm < 1e-9:  # a closed loop: split at the point farthest from the start
        dist = np.linalg.norm(seg - seg[0], axis=1)
    else:
        u, rel = chord / norm, seg - seg[0]
        dist = np.abs(u[0] * rel[:, 1] - u[1] * rel[:, 0])
    dist[:min_pts] = -1
    dist[-min_pts:] = -1
    k = int(np.argmax(dist))
    _split(pts, a, a + k, eps, out)
    _split(pts, a + k, b, eps, out)


def _merge(pts: np.ndarray, pieces: list[Piece], eps: float) -> list[Piece]:
    merged = True
    while merged and len(pieces) > 1:
        merged = False
        for i in range(len(pieces) - 1):
            a, b = pieces[i], pieces[i + 1]
            kind, dev, _ = fit_primitive(pts[a.start:b.end + 1])
            if dev <= eps:
                pieces[i:i + 2] = [Piece(a.start, b.end, kind, dev, a.length_mm + b.length_mm)]
                merged = True
                break
    return pieces


def _decompose(closed: np.ndarray, eps: float) -> list[Piece]:
    pieces: list[Piece] = []
    _split(closed, 0, len(closed) - 1, eps, pieces)
    return _merge(closed, sorted(pieces, key=lambda p: p.start), eps)


def _corner_start(pts: np.ndarray) -> int:
    k = max(1, int(round(CORNER_WINDOW_MM / SPACING_MM)))
    before = pts - np.roll(pts, k, axis=0)
    after = np.roll(pts, -k, axis=0) - pts
    cos = np.sum(before * after, axis=1) / (np.linalg.norm(before, axis=1) * np.linalg.norm(after, axis=1) + 1e-12)
    return int(np.argmin(cos))


def segment_outline(points_mm: np.ndarray) -> SegmentedOutline:
    pts = resample_closed(points_mm, SPACING_MM)
    pts = np.roll(pts, -_corner_start(pts), axis=0)
    closed = np.vstack([pts, pts[:1]])
    eps = MIN_EPS_MM
    pieces = _decompose(closed, eps)
    if len(pieces) > 1 and fit_primitive(np.vstack([closed[pieces[-1].start:], closed[1:pieces[0].end + 1]]))[1] <= eps:
        # The start fell inside one primitive (mid-arc, say): restart at that primitive's beginning instead.
        pts = np.roll(pts, -pieces[-1].start, axis=0)
        closed = np.vstack([pts, pts[:1]])
        pieces = _decompose(closed, eps)
    long_rms = [fit_primitive(closed[p.start:p.end + 1])[2] for p in pieces if p.length_mm >= 10.0]
    if long_rms:  # noisy edges: widen the tolerance to four times the noise on the long, clean pieces
        noisy = max(MIN_EPS_MM, 4.0 * float(np.median(long_rms)))
        if noisy > 1.5 * eps:
            eps = noisy
            pieces = _decompose(closed, eps)

    groups: list[tuple[int, int, str, int]] = []  # (first piece, last piece, kind, n pieces)
    i = 0
    while i < len(pieces):
        if pieces[i].length_mm >= SHORT_PIECE_MM:
            groups.append((i, i, pieces[i].kind, 1))
            i += 1
            continue
        j = i
        while j < len(pieces) and pieces[j].length_mm < SHORT_PIECE_MM:
            j += 1
        if j - i < 3:  # a lone short piece (a small fillet, say) is not irregular
            groups += [(k, k, pieces[k].kind, 1) for k in range(i, j)]
        else:
            run_len = sum(p.length_mm for p in pieces[i:j])
            chunks = max(1, int(round(run_len / IRREGULAR_SEGMENT_MM)))
            bounds = np.linspace(i, j, chunks + 1).round().astype(int)
            groups += [(int(s), int(e) - 1, "irregular", int(e - s))
                       for s, e in zip(bounds[:-1], bounds[1:], strict=True) if e > s]
        i = j

    # A short smooth piece between two irregular ones is part of the same break.
    for k, (first, last, kind, count) in enumerate(groups):
        before, after = groups[k - 1][2], groups[(k + 1) % len(groups)][2]
        length = sum(p.length_mm for p in pieces[first:last + 1])
        if kind != "irregular" and before == after == "irregular" and length < 2 * SHORT_PIECE_MM:
            groups[k] = (first, last, "irregular", count)

    n = len(pts)
    segments: list[Segment] = []
    for idx, (first, last, kind, count) in enumerate(groups):
        start = pieces[first].start
        end = (pieces[last].end - 1) if last + 1 < len(pieces) else n - 1
        span = closed[start:end + 2]
        _, _, rms = fit_primitive(span)
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(span, axis=0), axis=1))])
        mid = int(np.searchsorted(cum, cum[-1] / 2))
        segments.append(Segment(f"S{idx}", start, end, kind, float(cum[-1]), count, rms,
                                (float(span[mid, 0]), float(span[mid, 1]))))
    return SegmentedOutline(pts, tuple(segments), eps)
