"""API slice: hardened upload → pipeline → downloadable outputs. Uses the classical TEST BACKEND, not SAM."""

import io
from pathlib import Path

import cv2
import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

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


def _post(client: TestClient, data: bytes, name: str = "photo.png", **form) -> object:
    fields = {"thickness_mm": "3.02", "segmenter": "classical", **form}
    return client.post("/api/jobs", files={"photo": (name, data, "application/octet-stream")}, data=fields)


def test_health_reports_key_presence_only(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["meta_key_configured"] is False


def test_job_round_trip(client: TestClient, photo_bytes: bytes, tmp_path: Path) -> None:
    response = _post(client, photo_bytes)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report"]["validation"]["valid"]
    assert body["report"]["segmentation"]["is_ai"] is False
    stl = client.get(body["files"]["model.stl"])
    assert stl.status_code == 200
    mesh = trimesh.load(io.BytesIO(stl.content), file_type="stl")
    assert mesh.is_watertight
    assert client.get(body["files"]["overlay.png"]).headers["content-type"] == "image/png"
    stored = tmp_path / "data" / "jobs" / body["job_id"] / "input.png"
    assert stored.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_exif_gps_never_reaches_disk(client: TestClient, photo_bytes: bytes, tmp_path: Path) -> None:
    rgb = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (48.0, 15.0, 0.0)}  # GPSInfo: a fake location
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=95, exif=exif.tobytes())
    assert b"Exif" in buf.getvalue()
    body = _post(client, buf.getvalue(), "photo.jpg").json()
    stored = (tmp_path / "data" / "jobs" / body["job_id"] / "input.png").read_bytes()
    assert b"Exif" not in stored and b"GPS" not in stored


def test_non_image_is_rejected(client: TestClient) -> None:
    response = _post(client, b"#!/bin/sh\necho hi\n", "photo.png")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UPLOAD_NOT_IMAGE"


def test_oversized_upload_is_rejected(client: TestClient) -> None:
    response = _post(client, b"\xff" * (20 * 1024 * 1024 + 10))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_invalid_thickness_is_rejected(client: TestClient, photo_bytes: bytes) -> None:
    assert _post(client, photo_bytes, thickness_mm="0").status_code == 422


def test_sam_without_key_is_a_typed_error(client: TestClient, photo_bytes: bytes) -> None:
    response = _post(client, photo_bytes, segmenter="sam")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "META_KEY_MISSING"


def test_photo_without_mat_is_a_typed_error(client: TestClient) -> None:
    ok, buf = cv2.imencode(".png", (128 * (cv2.getGaussianKernel(1, 1) * 0 + 1)).astype("uint8").repeat(300, 0)
                           .repeat(300, 1))
    response = _post(client, buf.tobytes())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CAL_MARKERS_INSUFFICIENT"


@pytest.mark.parametrize("path", ["/api/jobs/../../etc/passwd", "/api/jobs/zzzzzzzzzzzz/model.stl",
                                  "/api/jobs/0123456789ab/input.png", "/api/jobs/0123456789ab/model.stl"])
def test_only_whitelisted_job_files_are_served(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404
