"""Reshape: the Studio's outline editor. Run an analysis, drag its outline, rebuild from the redrawn edge."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reforge.api.app import create_app
from reforge.config import Settings
from tests.synthetic.test_pipeline import _asymmetric_photo


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, meta_model_api_key=None, reforge_data_dir=tmp_path / "data")
    return TestClient(create_app(settings))


@pytest.fixture(scope="module")
def photo_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return _asymmetric_photo(tmp_path_factory.mktemp("photo") / "photo.png").read_bytes()


def test_reshape_rebuilds_from_a_redrawn_outline(client: TestClient, photo_bytes: bytes,
                                                 tmp_path: Path) -> None:
    parent = client.post("/api/jobs", files={"photo": ("photo.png", photo_bytes, "image/png")},
                         data={"thickness_mm": "3.02", "segmenter": "classical", "wait": "true"})
    assert parent.status_code == 200, parent.text
    parent_id = parent.json()["job_id"]
    report = parent.json()["report"]

    # The editor's view: the built outline over photo.jpg, mapped through the report's texture frame.
    jobs = tmp_path / "data" / "jobs"
    spec = json.loads((jobs / parent_id / "spec.json").read_text())
    u, v = report["texture"]["u"], report["texture"]["v"]
    pts = spec["outline"]["points"]
    baseline_px = [[u[0] + u[1] * x + u[2] * y, v[0] + v[1] * x + v[2] * y] for x, y in pts]
    # A small outward drag on one span, like a user pulling the border.
    outline_px = [list(p) for p in baseline_px]
    n = len(outline_px)
    span = list(range(n // 3, n // 3 + max(4, n // 20)))
    for i in span:
        outline_px[i][0] += 3.0
        outline_px[i][1] += 2.0

    child = client.post(f"/api/jobs/{parent_id}/reshape",
                        json={"outline_px": outline_px, "baseline_px": baseline_px, "wait": True})
    assert child.status_code == 200, child.text
    body = child.json()
    assert body["job_id"] != parent_id
    reshaped = body["report"]["reshaped"]
    assert reshaped["from_job"] == parent_id
    assert reshaped["edited_points"] == len(span)  # exactly the dragged points
    assert reshaped["edit_max_mm"] == pytest.approx(3.6 / u[1], abs=0.01)  # the 3.6 px drag, in mm
    assert reshaped["max_move_mm"] > 0  # vs the photographed outline
    codes = [n["code"] for n in body["report"]["reconstruction"]["verification"]]
    assert "OUTLINE_RESHAPED" in codes  # the redrawn edge never passes for a photographed one
    assert (jobs / body["job_id"] / "frame.json").is_file()
    # The child rebuilt from the redrawn edge: same photo, slightly different part.
    assert body["report"]["part"]["size_mm"] != report["part"]["size_mm"]


def test_span_picks_follow_the_redraw_by_geometry() -> None:
    import numpy as np

    from reforge.geometry.segments import segment_outline
    from reforge.studio.reshape import carry_span_picks

    rng = np.random.default_rng(3)
    outline = np.array([[100, 0], [100, 50], [0, 50], [0, 0]], dtype=float)
    dense = np.vstack([np.linspace(outline[i], outline[(i + 1) % 4], 60, endpoint=False) for i in range(4)])
    parent = segment_outline(dense)
    right = tuple(s.seg_id for s in parent.segments if parent.span(s)[:, 0].mean() > 90.0)
    assert right  # the right side exists as spans
    # A redraw that wiggles the left side but keeps the right: the picks follow.
    edited = dense + np.vstack([rng.normal(0, 0.1, (120, 2)), np.zeros((120, 2))])
    carried = carry_span_picks(right, parent, edited)
    assert carried
    new = segment_outline(edited)
    for sid in carried:
        assert new.span(new.by_id(sid))[:, 0].mean() > 85.0
    # A redraw that erases the right side carries nothing.
    erased = dense.copy()
    erased[:, 0] = np.clip(erased[:, 0], 0, 40)
    assert carry_span_picks(right, parent, erased) == ()


def test_reshape_refuses_garbage(client: TestClient, photo_bytes: bytes, tmp_path: Path) -> None:
    parent = client.post("/api/jobs", files={"photo": ("photo.png", photo_bytes, "image/png")},
                         data={"thickness_mm": "3.02", "segmenter": "classical", "wait": "true"})
    assert parent.status_code == 200, parent.text
    parent_id = parent.json()["job_id"]
    bad = client.post(f"/api/jobs/{parent_id}/reshape", json={"outline_px": [[0, 0]] * 4})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "RESHAPE_INVALID"
    missing = client.post("/api/jobs/0123456789ab/reshape", json={"outline_px": [[0, 0]] * 8})
    assert missing.status_code == 404
