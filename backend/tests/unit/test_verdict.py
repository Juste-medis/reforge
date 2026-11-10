"""The second verdict: artifact checks, replay score, fingerprints and staleness."""

import json
from pathlib import Path

import trimesh
from shapely.geometry import box

from reforge.validation.verdict import fingerprint, freshness, replay_score, sha256_file, validate_artifacts

BOX = (10.0, 20.0, 3.0)


def _job_dir(tmp_path: Path, *, size: tuple[float, float, float] = BOX, name: str = "job") -> Path:
    out = tmp_path / name
    out.mkdir()
    trimesh.creation.box(extents=size).export(out / "model.stl")
    (out / "spec.json").write_text(json.dumps({"outline": {}, "thickness": 3.0}))
    (out / "photo.jpg").write_bytes(b"\xff\xd8" + b"photo" * 100)
    (out / "overlay.png").write_bytes(b"\x89PNG" + b"overlay" * 100)
    return out


def test_replay_score_is_exact_on_known_polygons() -> None:
    assert replay_score(box(0, 0, 10, 10), box(0, 0, 10, 10))["coverage"] == 1.0
    assert replay_score(box(0, 0, 10, 10), box(0, 0, 10, 10))["iou"] == 1.0
    # Built extends past measured (a rebuild): coverage stays 1, IoU drops honestly.
    s = replay_score(box(0, 0, 10, 10), box(0, 0, 20, 10))
    assert s["coverage"] == 1.0 and s["iou"] == 0.5
    assert replay_score(box(0, 0, 10, 10), box(50, 50, 60, 60))["coverage"] == 0.0


def test_fingerprint_hashes_files_and_marks_missing_as_none(tmp_path: Path) -> None:
    out = _job_dir(tmp_path)
    fp = fingerprint(out)
    assert fp["model.stl"] == sha256_file(out / "model.stl") and len(fp["model.stl"]) == 64
    assert fp["mask.png"] is None  # not written in this fixture
    assert fingerprint(out) == fingerprint(out)  # deterministic


def test_sound_artifacts_validate_verified(tmp_path: Path) -> None:
    out = _job_dir(tmp_path)
    verdict = validate_artifacts(out, expected_size_mm=BOX, photo_sha256="abc123")
    assert verdict["artifact_status"] == "verified"
    assert verdict["photo_sha256"] == "abc123"
    assert all(r["status"] == "pass" for r in verdict["rows"])
    assert json.loads((out / "validation.json").read_text())["artifact_status"] == "verified"


def test_corrupt_stl_fails_the_verdict(tmp_path: Path) -> None:
    out = _job_dir(tmp_path)
    (out / "model.stl").write_text("not a mesh")
    verdict = validate_artifacts(out, expected_size_mm=BOX, photo_sha256=None)
    assert verdict["artifact_status"] == "failed"
    assert any(r["check"] == "stl_loads" and r["status"] == "fail" for r in verdict["rows"])


def test_missing_file_fails_and_wrong_size_fails(tmp_path: Path) -> None:
    out = _job_dir(tmp_path)
    (out / "overlay.png").unlink()
    verdict = validate_artifacts(out, expected_size_mm=BOX, photo_sha256=None)
    assert verdict["artifact_status"] == "failed"
    assert any(r["check"] == "files_present" and "overlay.png" in r["detail"] for r in verdict["rows"])
    out = _job_dir(tmp_path, name="job2")
    verdict = validate_artifacts(out, expected_size_mm=(10.0, 20.0, 4.0), photo_sha256=None)
    assert verdict["artifact_status"] == "failed"
    assert any(r["check"] == "bbox_matches_report" and r["status"] == "fail" for r in verdict["rows"])


def test_freshness_detects_changed_gone_and_missing(tmp_path: Path) -> None:
    out = _job_dir(tmp_path)
    assert freshness(out)["state"] == "missing"
    validate_artifacts(out, expected_size_mm=BOX, photo_sha256=None)
    assert freshness(out) == {"state": "current", "changed": []}
    with (out / "model.stl").open("ab") as fh:
        fh.write(b"\x00")
    assert freshness(out) == {"state": "stale", "changed": ["model.stl (changed)"]}
    (out / "overlay.png").unlink()
    assert freshness(out)["changed"] == ["model.stl (changed)", "overlay.png (gone)"]
