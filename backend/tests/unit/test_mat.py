"""Mat layout and printable PDF: the geometry the detector assumes must be the geometry printed."""

from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytest

from reforge.capture.calibration import calibrate, detect_markers
from reforge.capture.mat import (
    GAP_MM,
    MARGIN_MM,
    MARKERS_PER_MAT,
    TICK_MM,
    marker_cells,
    mat_layout,
    pages_for_ids,
    write_mat_pdf,
)

PAGES = ["A4", "Letter"]


def _boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _marker_box(m) -> tuple[float, float, float, float]:
    return (m.x_mm, m.y_mm, m.x_mm + m.size_mm, m.y_mm + m.size_mm)


def _bar_box(bar) -> tuple[float, float, float, float]:
    (x0, y0), (x1, y1) = bar.start_mm, bar.end_mm
    half = TICK_MM / 2
    return (min(x0, x1) - half, min(y0, y1) - half, max(x0, x1) + half, max(y0, y1) + half)


@pytest.mark.parametrize("page", PAGES)
def test_layout_geometry_is_consistent(page: str) -> None:
    layout = mat_layout(page)
    assert len(layout.markers) == MARKERS_PER_MAT
    assert len(layout.marker_ids) == MARKERS_PER_MAT
    boxes = [_marker_box(m) for m in layout.markers]
    for box in boxes:
        assert box[0] >= MARGIN_MM - 1e-9 and box[1] >= MARGIN_MM - 1e-9
        assert box[2] <= layout.width_mm - MARGIN_MM + 1e-9 and box[3] <= layout.height_mm - MARGIN_MM + 1e-9
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert not _boxes_overlap(a, b)
    zone = layout.free_zone_mm
    assert zone[2] - zone[0] > 130 and zone[3] - zone[1] > 200
    for box in boxes:
        assert not _boxes_overlap(box, zone)
    for bar in layout.check_bars:
        (x0, y0), (x1, y1) = bar.start_mm, bar.end_mm
        assert np.hypot(x1 - x0, y1 - y0) == pytest.approx(100.0)
        assert not _boxes_overlap(_bar_box(bar), zone)
        for box in boxes:
            assert not _boxes_overlap(_bar_box(bar), box)
    assert zone[0] - (MARGIN_MM + layout.markers[0].size_mm) == pytest.approx(GAP_MM)


def test_pages_use_disjoint_marker_ids() -> None:
    a4, letter = mat_layout("A4"), mat_layout("Letter")
    assert not a4.marker_ids & letter.marker_ids
    assert pages_for_ids({0, 5, 40}) == ["A4"]
    assert pages_for_ids({12, 13}) == ["Letter"]
    assert pages_for_ids({0, 12}) == ["A4", "Letter"]
    assert pages_for_ids({40, 41}) == []


def test_marker_cells_have_black_border() -> None:
    cells = marker_cells(7)
    assert cells.shape == (6, 6)
    assert cells[0].all() and cells[-1].all() and cells[:, 0].all() and cells[:, -1].all()


@pytest.mark.parametrize("page", PAGES)
def test_printed_pdf_matches_layout(page: str, tmp_path: Path) -> None:
    """Render the real PDF at 600 dpi and check page size and every marker position on it."""
    layout = mat_layout(page)
    path = write_mat_pdf(layout, tmp_path / "mat.pdf")
    assert path.read_bytes()[:5] == b"%PDF-"
    doc = pdfium.PdfDocument(str(path))
    try:
        assert len(doc) == 1
        pg = doc[0]
        w_pt, h_pt = pg.get_size()
        assert w_pt * 25.4 / 72 == pytest.approx(layout.width_mm, abs=0.01)
        assert h_pt * 25.4 / 72 == pytest.approx(layout.height_mm, abs=0.01)
        dpi = 600
        image = pg.render(scale=dpi / 72, grayscale=True).to_numpy()
    finally:
        doc.close()
    image = np.ascontiguousarray(image.reshape(image.shape[0], image.shape[1], -1)[:, :, 0])
    px_per_mm = dpi / 25.4

    found_layout, detections = detect_markers(image)
    assert found_layout.page == page
    assert {d.marker_id for d in detections} == set(layout.marker_ids)
    # Rasterisers (and printers) thicken black fills and snap edges to the pixel grid, so corners move
    # by up to about a pixel. Measured on 2026-10-26 for the Letter mat: the worst marker-centre deviation
    # was 0.109 / 0.046 / 0.014 mm at 300 / 600 / 1200 dpi. It tracks the pixel size, so it's
    # rasterisation, not PDF geometry. The tolerance is therefore 1.5 render pixels.
    # The +0.5 converts ArUco's pixel-centre coordinates to the renderer's pixel-edge coordinates.
    centre_dev = max(
        float(np.abs((d.corners_px.mean(axis=0) + 0.5) / px_per_mm - np.array(layout.marker(d.marker_id).center_mm))
              .max())
        for d in detections
    )
    tolerance = 1.5 / px_per_mm
    assert centre_dev < tolerance, f"worst marker-centre deviation {centre_dev:.4f} mm (> {tolerance:.4f} mm)"
    sides = [np.linalg.norm(np.roll(d.corners_px, -1, axis=0) - d.corners_px, axis=1).mean() / px_per_mm
             for d in detections]
    assert np.allclose(sides, layout.markers[0].size_mm, atol=0.03)

    cal = calibrate(image)
    assert cal.rms_mm < 0.05
    # A digital render has pure-white paper, so CAL_OVEREXPOSED is expected. No geometry warning may fire.
    assert not [w for w in cal.warnings if w.code not in {"CAL_OVEREXPOSED", "CAL_LOW_RESOLUTION"}]
