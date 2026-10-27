"""The Re-Forge calibration mat.

One layout definition drives both the printable PDF and the detector, so the geometry the
detector assumes is, by construction, the geometry that was printed.

Mat frame: origin at the page's top-left corner, x to the right, y down, in millimetres.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ARUCO_DICTIONARY = cv2.aruco.DICT_4X4_50
LAYOUT_VERSION = 1
MARGIN_MM = 8.0  # keeps markers clear of typical printer margins
MARKER_MM = 18.0
GAP_MM = 8.0  # strip between markers and free zone; holds the check bars
CHECK_BAR_MM = 100.0
TICK_MM = 4.0
LINE_MM = 0.2

PAGES_MM: dict[str, tuple[float, float]] = {"A4": (210.0, 297.0), "Letter": (215.9, 279.4)}
ID_BASE: dict[str, int] = {"A4": 0, "Letter": 12}
MARKERS_PER_MAT = 12


@dataclass(frozen=True)
class MarkerPlacement:
    marker_id: int
    x_mm: float  # top-left corner
    y_mm: float
    size_mm: float

    def corners_mm(self) -> np.ndarray:
        """Corners in ArUco order: top-left, top-right, bottom-right, bottom-left."""
        x, y, s = self.x_mm, self.y_mm, self.size_mm
        return np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], dtype=np.float64)

    @property
    def center_mm(self) -> tuple[float, float]:
        return (self.x_mm + self.size_mm / 2, self.y_mm + self.size_mm / 2)


@dataclass(frozen=True)
class CheckBar:
    """A printed bar whose end-tick centres are ``nominal_mm`` apart before printing."""

    axis: str  # "x" (horizontal) or "y" (vertical)
    start_mm: tuple[float, float]
    end_mm: tuple[float, float]
    nominal_mm: float = CHECK_BAR_MM


@dataclass(frozen=True)
class MatLayout:
    page: str
    version: int
    width_mm: float
    height_mm: float
    markers: tuple[MarkerPlacement, ...]
    free_zone_mm: tuple[float, float, float, float]  # x0, y0, x1, y1
    check_bars: tuple[CheckBar, ...]

    @property
    def marker_ids(self) -> frozenset[int]:
        return frozenset(m.marker_id for m in self.markers)

    def marker(self, marker_id: int) -> MarkerPlacement:
        for m in self.markers:
            if m.marker_id == marker_id:
                return m
        raise KeyError(marker_id)

    @property
    def title(self) -> str:
        return f"RE-FORGE calibration mat {self.page} v{self.version}"


def mat_layout(page: str = "A4") -> MatLayout:
    """Twelve markers around the page edge, clockwise from the top-left corner."""
    if page not in PAGES_MM:
        raise ValueError(f"unknown page {page!r}; expected one of {sorted(PAGES_MM)}")
    w, h = PAGES_MM[page]
    left, right = MARGIN_MM, w - MARGIN_MM - MARKER_MM
    top, bottom = MARGIN_MM, h - MARGIN_MM - MARKER_MM
    xs = np.linspace(left, right, 4)
    ys = np.linspace(top, bottom, 4)
    positions = (
        [(x, top) for x in xs]
        + [(right, y) for y in ys[1:3]]
        + [(x, bottom) for x in xs[::-1]]
        + [(left, y) for y in ys[2:0:-1]]
    )
    base = ID_BASE[page]
    markers = tuple(
        MarkerPlacement(base + i, float(x), float(y), MARKER_MM) for i, (x, y) in enumerate(positions)
    )
    inner = MARGIN_MM + MARKER_MM + GAP_MM
    strip = MARGIN_MM + MARKER_MM + GAP_MM / 2
    bars = (
        CheckBar("x", (w / 2 - CHECK_BAR_MM / 2, strip), (w / 2 + CHECK_BAR_MM / 2, strip)),
        CheckBar("y", (strip, h / 2 - CHECK_BAR_MM / 2), (strip, h / 2 + CHECK_BAR_MM / 2)),
    )
    return MatLayout(page, LAYOUT_VERSION, w, h, markers, (inner, inner, w - inner, h - inner), bars)


def pages_for_ids(ids: set[int]) -> list[str]:
    """Pages whose markers appear among ``ids``. IDs belonging to no mat are ignored."""
    return [p for p in PAGES_MM if ids & mat_layout(p).marker_ids]


def marker_cells(marker_id: int) -> np.ndarray:
    """The marker's 6x6 cell grid including its one-cell border; 1 means black."""
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICTIONARY)
    image = cv2.aruco.generateImageMarker(dictionary, marker_id, 6)
    return (image < 128).astype(np.uint8)


def marker_black_rects(marker: MarkerPlacement, seam_mm: float = 0.0) -> Iterator[tuple[float, ...]]:
    """Black areas as (x, y, w, h) rectangles in mm: one per horizontal run of black cells.

    ``seam_mm`` extends each run downward into the next row (never past the marker's outer edge),
    so rasterisers don't leave hairline seams between rows. The outer geometry is unchanged.
    """
    cells = marker_cells(marker.marker_id)
    n = cells.shape[0]
    cell = marker.size_mm / n
    for r in range(n):
        c = 0
        while c < n:
            if not cells[r, c]:
                c += 1
                continue
            start = c
            while c < n and cells[r, c]:
                c += 1
            extra = seam_mm if r < n - 1 else 0.0
            yield (marker.x_mm + start * cell, marker.y_mm + r * cell, (c - start) * cell, cell + extra)


def write_mat_pdf(layout: MatLayout, path: Path) -> Path:
    """Write the printable mat. It must be printed at 100 % ("actual size")."""
    from fpdf import FPDF

    pdf = FPDF(unit="mm", format=(layout.width_mm, layout.height_mm))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.set_title(layout.title)
    pdf.set_creator("RE-FORGE AI")
    pdf.add_page()

    pdf.set_fill_color(0, 0, 0)
    for marker in layout.markers:
        for x, y, w, h in marker_black_rects(marker, seam_mm=0.03):
            pdf.rect(x, y, w, h, style="F")

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(LINE_MM)
    for bar in layout.check_bars:
        (x0, y0), (x1, y1) = bar.start_mm, bar.end_mm
        pdf.line(x0, y0, x1, y1)
        for x, y in (bar.start_mm, bar.end_mm):
            if bar.axis == "x":
                pdf.line(x, y - TICK_MM / 2, x, y + TICK_MM / 2)
            else:
                pdf.line(x - TICK_MM / 2, y, x + TICK_MM / 2, y)

    pdf.set_font("Helvetica", size=5.5)
    pdf.set_text_color(0, 0, 0)
    bar_x, bar_y = layout.check_bars
    pdf.text(bar_x.end_mm[0] + 2.0, bar_x.end_mm[1] + 0.7, "100 mm (X)")
    # Rotated label left of the vertical bar's midpoint, which falls between the two left-column markers.
    label = "100 mm (Y)"
    lx = bar_y.start_mm[0] - 1.0
    ly = (bar_y.start_mm[1] + bar_y.end_mm[1]) / 2 + pdf.get_string_width(label) / 2
    with pdf.rotation(90, lx, ly):
        pdf.text(lx, ly, label)

    # Light corner marks show where to place the part without adding edges inside the free zone.
    x0, y0, x1, y1 = layout.free_zone_mm
    pdf.set_draw_color(150, 150, 150)
    pdf.set_line_width(0.3)
    arm = 6.0
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        pdf.line(cx, cy, cx + dx * arm, cy)
        pdf.line(cx, cy, cx, cy + dy * arm)

    caption = (
        f"{layout.title}  |  print at 100% (actual size), keep it flat  |  "
        "caliper-check both 100 mm bars between tick centres"
    )
    pdf.set_font("Helvetica", size=5.5)
    pdf.set_text_color(60, 60, 60)
    width = pdf.get_string_width(caption)
    pdf.text(layout.width_mm / 2 - width / 2, y1 + GAP_MM / 2 + 0.7, caption)

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path


def fill_polygon_exact(image: np.ndarray, rings_px: list[np.ndarray], value: int, factor: int = 8) -> None:
    """Composite ``value`` into ``image`` with area coverage from ``factor``× supersampling.

    ``rings_px[0]`` is the exterior and any further rings are holes, in pixel-centre coordinates.
    Unlike OpenCV's anti-aliased fill, which inflates shapes by about 0.5–1 px (measured 2026-10-26),
    this is unbiased. That matters wherever synthetic scenes serve as ground truth for metrology.

    The fine grid is filled with OpenCV's non-anti-aliased fill, which includes boundary pixels and so
    inflates every ring by half a fine pixel (measured: +0.0625 px at factor 8). Each ring is shrunk by
    exactly that amount first, which cancels the bias.
    """
    from shapely.geometry import Polygon as ShapelyPolygon

    allpts = np.concatenate(rings_px)
    x0 = max(int(np.floor(allpts[:, 0].min())) - 1, 0)
    y0 = max(int(np.floor(allpts[:, 1].min())) - 1, 0)
    x1 = min(int(np.ceil(allpts[:, 0].max())) + 2, image.shape[1])
    y1 = min(int(np.ceil(allpts[:, 1].max())) + 2, image.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    h, w = y1 - y0, x1 - x0
    fine = np.zeros((h * factor, w * factor), np.uint8)
    shift = 8
    for k, ring in enumerate(rings_px):
        origin = np.array([x0 - 0.5, y0 - 0.5])
        fine_ring = (ring - origin) * factor - 0.5
        shrunk = ShapelyPolygon(fine_ring).buffer(-0.5, join_style="mitre", mitre_limit=10.0)
        parts = [p for p in getattr(shrunk, "geoms", [shrunk]) if not p.is_empty]
        polys = [np.round(np.asarray(p.exterior.coords) * (1 << shift)).astype(np.int32) for p in parts]
        if polys:
            cv2.fillPoly(fine, polys, 1 if k == 0 else 0, cv2.LINE_8, shift)
    coverage = fine.reshape(h, factor, w, factor).mean(axis=(1, 3))
    region = image[y0:y1, x0:x1].astype(np.float32)
    image[y0:y1, x0:x1] = np.clip(np.round(region * (1 - coverage) + value * coverage), 0, 255).astype(np.uint8)


def render_layout(
    layout: MatLayout,
    mm_to_px: np.ndarray,
    size: tuple[int, int],
    *,
    paper: int = 235,
    ink: int = 25,
    background: int = 70,
) -> np.ndarray:
    """Draw the page and markers through a mm→px homography.

    Markers use exact area coverage, so their geometry is unbiased ground truth. The page edge uses
    OpenCV's faster anti-aliased fill; no measurement depends on it. Used for synthetic test scenes
    and previews. Check bars and text are not drawn.
    """
    width, height = size
    image = np.full((height, width), background, np.uint8)
    shift = 4

    def project(corners_mm: np.ndarray) -> np.ndarray:
        return cv2.perspectiveTransform(corners_mm.reshape(-1, 1, 2), mm_to_px).reshape(-1, 2)

    page = np.array([[0, 0], [layout.width_mm, 0], [layout.width_mm, layout.height_mm], [0, layout.height_mm]])
    cv2.fillPoly(image, [np.round(project(page.astype(np.float64)) * (1 << shift)).astype(np.int32)], paper,
                 cv2.LINE_AA, shift)
    for marker in layout.markers:
        cells = marker_cells(marker.marker_id)
        n = cells.shape[0]
        cell = marker.size_mm / n
        # One coverage pass per marker: the black square is the exterior and the white cells are holes,
        # so adjacent white cells leave no compositing seam.
        rings = [project(marker.corners_mm())]
        for r in range(n):
            for c in range(n):
                if not cells[r, c]:
                    x, y = marker.x_mm + c * cell, marker.y_mm + r * cell
                    rings.append(project(np.array([[x, y], [x + cell, y], [x + cell, y + cell], [x, y + cell]])))
        fill_polygon_exact(image, rings, ink)
    return image


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the printable Re-Forge calibration mat (PDF).")
    parser.add_argument("--page", choices=sorted(PAGES_MM), default="A4")
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args(argv)
    layout = mat_layout(args.page)
    out = args.output or Path(f"reforge-mat-{layout.page}-v{layout.version}.pdf")
    print(write_mat_pdf(layout, out))


if __name__ == "__main__":
    main()
