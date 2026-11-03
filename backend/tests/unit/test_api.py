"""API: hardened upload → background pipeline → downloadable outputs. Uses the classical TEST BACKEND, not SAM."""

import io
import json
import time
from pathlib import Path

import cv2
import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from reforge.api.app import create_app
from reforge.api.jobs import JobRegistry
from reforge.config import Settings
from reforge.errors import ReforgeError
from reforge.pipeline import STAGES
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


def test_a_failed_job_keeps_its_request_and_error(client: TestClient, tmp_path: Path) -> None:
    ok, buf = cv2.imencode(".png", (128 * (cv2.getGaussianKernel(1, 1) * 0 + 1)).astype("uint8").repeat(300, 0)
                           .repeat(300, 1))
    response = _post(client, buf.tobytes(), thickness_mm="1.5")
    assert response.status_code == 422
    job_id = response.json()["job_id"]
    job_dir = tmp_path / "data" / "jobs" / job_id
    request = json.loads((job_dir / "request.json").read_text())
    assert request["segmenter"] == "classical" and request["interpreter"] == "geometric"
    assert request["thickness_mm"] == 1.5
    error = json.loads((job_dir / "error.json").read_text())
    assert error["code"] == response.json()["error"]["code"] == "CAL_MARKERS_INSUFFICIENT"
    assert client.get(f"/api/jobs/{job_id}/error.json").status_code == 404  # kept for diagnosis, never served


@pytest.mark.parametrize("path", ["/api/jobs/../../etc/passwd", "/api/jobs/zzzzzzzzzzzz/model.stl",
                                  "/api/jobs/0123456789ab/input.png", "/api/jobs/0123456789ab/model.stl"])
def test_only_whitelisted_job_files_are_served(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


# --- background jobs, examples, re-runs, printer compensation (classical TEST BACKEND, no AI) ---------------------




@pytest.fixture
def live_client(tmp_path: Path):
    """A client whose event loop outlives each request, so background jobs keep running between polls."""
    settings = Settings(_env_file=None, meta_model_api_key=None, reforge_data_dir=tmp_path / "data")
    with TestClient(create_app(settings)) as c:
        yield c


def _poll(client: TestClient, job_id: str, timeout_s: float = 120.0) -> dict:
    seen: set[str] = set()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        seen |= {s["id"] for s in body["stages"] if s["state"] in ("running", "done")}
        if body["state"] not in ("queued", "running"):
            body["_seen"] = seen
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_a_background_job_reports_its_real_stages_then_its_result(live_client: TestClient, photo_bytes: bytes
                                                                   ) -> None:
    response = _post(live_client, photo_bytes, wait="false")
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    body = _poll(live_client, job_id)
    assert body["state"] == "done", body.get("error")
    assert [s["id"] for s in body["stages"]] == list(STAGES)
    assert all(s["state"] == "done" and s["seconds"] >= 0 for s in body["stages"])
    report = body["result"]["report"]
    assert report["validation"]["valid"]
    dims = {d["id"]: d for d in report["confidence"]["dimensions"]}
    assert dims["thickness"]["status"] == "MEASURED" and dims["thickness"]["u_mm"] == pytest.approx(0.05)
    assert dims["length"]["u_mm"] > 0 and dims["length"]["terms"]
    assert "modelled" in report["confidence"]["note"]
    photo = live_client.get(body["result"]["files"]["photo.jpg"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"


def test_a_failed_background_job_says_why(live_client: TestClient) -> None:
    ok, buf = cv2.imencode(".png", (128 * (cv2.getGaussianKernel(1, 1) * 0 + 1)).astype("uint8").repeat(300, 0)
                           .repeat(300, 1))
    job_id = _post(live_client, buf.tobytes(), wait="false").json()["job_id"]
    body = _poll(live_client, job_id)
    assert body["state"] == "failed" and body["error"]["code"] == "CAL_MARKERS_INSUFFICIENT"
    assert body["error"]["hint"]


def test_status_of_unknown_or_interrupted_jobs(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/jobs/0123456789ab").status_code == 404
    assert client.get("/api/jobs/not-a-job").status_code == 404
    job_dir = tmp_path / "data" / "jobs" / "abcdefabcdef"
    job_dir.mkdir(parents=True)
    (job_dir / "request.json").write_text(json.dumps({"thickness_mm": 2.0, "segmenter": "classical"}))
    body = client.get("/api/jobs/abcdefabcdef").json()
    assert body["state"] == "interrupted" and body["error"]["code"] == "JOB_INTERRUPTED"
    assert body["request"]["thickness_mm"] == 2.0


def test_internal_error_details_stay_on_disk(client: TestClient, tmp_path: Path) -> None:
    job_dir = tmp_path / "data" / "jobs" / "abcdefabcde0"
    job_dir.mkdir(parents=True)
    (job_dir / "error.json").write_text(json.dumps({"code": "INTERNAL_ERROR", "message": "KeyError", "hint": None}))
    body = client.get("/api/jobs/abcdefabcde0").json()
    assert body["state"] == "failed" and "KeyError" not in json.dumps(body)


def test_exactly_one_photo_source_is_required(client: TestClient, photo_bytes: bytes) -> None:
    neither = client.post("/api/jobs", data={"thickness_mm": "3", "segmenter": "classical"})
    assert neither.status_code == 422 and neither.json()["error"]["code"] == "SOURCE_INVALID"
    both = _post(client, photo_bytes, sample="broken-bracket")
    assert both.status_code == 422 and both.json()["error"]["code"] == "SOURCE_INVALID"
    unknown = client.post("/api/jobs", data={"thickness_mm": "3", "segmenter": "classical", "sample": "nope"})
    assert unknown.json()["error"]["code"] == "SAMPLE_NOT_FOUND"
    gone = client.post("/api/jobs", data={"thickness_mm": "3", "segmenter": "classical", "from_job": "0123456789ab"})
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_examples_are_listed_labelled_and_runnable(client: TestClient) -> None:
    samples = client.get("/api/samples").json()
    assert {s["id"] for s in samples} >= {"broken-bracket", "broken-flange", "slotted-link"}
    for s in samples:
        assert s["kind"] == "synthetic" and "Not a real photo" in s["label"]
        assert client.get(s["thumb_url"]).headers["content-type"] == "image/jpeg"
    assert client.get("/api/samples/broken-bracket/../../.env").status_code == 404
    bracket = next(s for s in samples if s["id"] == "broken-bracket")
    response = client.post("/api/jobs", data={"thickness_mm": str(bracket["thickness_mm"]), "segmenter": "classical",
                                              "sample": "broken-bracket"})
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    size = report["part"]["size_mm"]
    # The rebuilt bracket against the intact part's known size (a synthetic image: exact truth).
    assert abs(size["length"] - bracket["truth"]["length_mm"]) < 0.2
    assert abs(size["width"] - bracket["truth"]["width_mm"]) < 0.2
    assert report["reconstruction"]["completion"] is not None
    status = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert status["request"]["sample"] == "broken-bracket" and status["request"]["sample_info"]["kind"] == "synthetic"


def test_a_job_can_be_run_again_from_its_stored_photo(client: TestClient, photo_bytes: bytes) -> None:
    first = _post(client, photo_bytes).json()
    again = client.post("/api/jobs", data={"thickness_mm": "2.5", "segmenter": "classical",
                                           "from_job": first["job_id"]})
    assert again.status_code == 200, again.text
    assert again.json()["job_id"] != first["job_id"]
    assert again.json()["report"]["part"]["overall_mm"][2] == pytest.approx(2.5)


def test_printer_compensation_rebuilds_and_revalidates(client: TestClient, photo_bytes: bytes) -> None:
    body = _post(client, photo_bytes).json()
    url = body["files"]["model.stl"]
    plain = trimesh.load(io.BytesIO(client.get(url).content), file_type="stl")
    loose = client.get(url, params={"hole_offset_mm": 0.3})
    assert loose.status_code == 200 and "holes+0.30" in loose.headers["content-disposition"]
    compensated = trimesh.load(io.BytesIO(loose.content), file_type="stl")
    assert compensated.is_watertight
    if body["report"]["part"]["holes"]:
        assert compensated.volume < plain.volume  # larger holes, less material
    scad = client.get(body["files"]["model.scad"], params={"hole_offset_mm": 0.3}).text
    assert "hole_comp = 0.3000;" in scad
    assert client.get(url, params={"hole_offset_mm": 5}).status_code == 422  # outside ±1 mm
    assert client.get(url, params={"outline_offset_mm": -1.0}).status_code in (200, 422)


def test_responses_carry_security_headers(client: TestClient) -> None:
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_the_queue_is_bounded() -> None:
    import asyncio

    async def scenario() -> None:
        registry = JobRegistry(max_running=1, max_waiting=1)
        gate = asyncio.Event()

        async def work(progress):
            await gate.wait()
            return {}

        registry.submit("aaaaaaaaaaaa", work)
        registry.submit("bbbbbbbbbbbb", work)
        with pytest.raises(ReforgeError) as exc:
            registry.check_capacity()
        assert exc.value.code == "SERVER_BUSY"
        gate.set()
        await asyncio.sleep(0.05)
        assert registry.get("aaaaaaaaaaaa").state == "done"
        registry.check_capacity()

    asyncio.run(scenario())
