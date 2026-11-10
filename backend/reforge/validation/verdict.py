"""The second verdict, on the artifacts themselves (the video2urdf ``validation.py`` pattern, adapted).

``validation.mesh`` checks the in-memory part before it is written; this module checks what was actually handed out:
the STL reloads from disk, the reloaded mesh is sound, and its dimensions match the report. The verdict lands in
``validation.json`` next to ``report.json``, with a sha256 fingerprint of every artifact, so a later change to the
files shows the validation as stale (``freshness()``) instead of silently describing something else.

Statuses: ``verified`` (every row passed), ``needs_review`` (warnings only), ``failed`` (an error row).
``replay_score`` is the overlay check (the video2urdf ``replay.py`` pattern, for one still frame): how much of the
measured outline the built footprint covers, and their IoU. For an intact part both are ~1; for a rebuilt part the
built outline legitimately extends past the measured one, so coverage (not IoU) is the headline number.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import trimesh
from shapely.geometry import Polygon

BBOX_TOL_MM = 0.01  # disk STL vs the in-memory mesh: same bytes, same bounds
FINGERPRINTED = ("model.stl", "spec.json", "photo.jpg", "overlay.png", "mask.png", "setofmark.png")


@dataclass(frozen=True)
class Row:
    name: str
    status: Literal["pass", "warn", "fail"]
    detail: str


def sha256_file(path: Path) -> str | None:
    """A file's sha256, or None when it is missing or unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def fingerprint(base: Path, names: tuple[str, ...] = FINGERPRINTED) -> dict[str, str | None]:
    """Relative name -> sha256 for the artifacts that make up the result."""
    return {name: sha256_file(base / name) for name in names}


def replay_score(measured: Polygon, built: Polygon) -> dict[str, float]:
    """Coverage of the measured outline by the built footprint, and their IoU, in mm²."""
    measured_area = float(measured.area)
    built_area = float(built.area)
    inter = float(measured.intersection(built).area)
    union = measured_area + built_area - inter
    coverage = inter / measured_area if measured_area else 0.0
    return {"measured_area_mm2": round(measured_area, 2), "built_area_mm2": round(built_area, 2),
            "coverage": round(coverage, 4), "iou": round(inter / union, 4) if union else 0.0}


def validate_artifacts(out_dir: Path, *, expected_size_mm: tuple[float, float, float],
                       photo_sha256: str | None) -> dict:
    """Check the written artifacts, write ``validation.json`` into ``out_dir``, and return it.

    ``expected_size_mm`` is the in-memory mesh's (x, y, z) extent: the check reloads the STL from disk and compares,
    so a truncated write or a report that drifted from the file is caught here, not by the user.
    """
    rows: list[Row] = []

    def add(name: str, status: Literal["pass", "warn", "fail"], detail: str) -> None:
        rows.append(Row(name, status, detail))

    missing = [n for n in ("model.stl", "spec.json", "photo.jpg", "overlay.png") if not (out_dir / n).is_file()]
    if missing:
        add("files_present", "fail", f"missing: {', '.join(missing)}")
    else:
        add("files_present", "pass", "model.stl, spec.json, photo.jpg, overlay.png")
    try:
        disk = trimesh.load(out_dir / "model.stl", force="mesh")
        if not isinstance(disk, trimesh.Trimesh):
            raise ValueError(f"loaded {type(disk).__name__}, not a mesh")
        if disk.bounds is None or len(disk.faces) == 0:
            raise ValueError("loaded an empty mesh")
        add("stl_loads", "pass", f"{len(disk.faces)} triangles reloaded from disk")
    except Exception as exc:  # noqa: BLE001 - the row must record any loader failure, not raise
        disk = None
        add("stl_loads", "fail", f"the STL on disk does not load: {exc}")
    if disk is not None:
        sound = bool(disk.is_watertight) and float(disk.volume) > 0
        add("stl_sound", "pass" if sound else "fail",
            f"watertight={bool(disk.is_watertight)}, volume={float(disk.volume):.3f} mm³")
        got = tuple(round(float(b[1] - b[0]), 4) for b in disk.bounds.T)
        err = max(abs(g - e) for g, e in zip(got, expected_size_mm, strict=True))
        add("bbox_matches_report", "pass" if err < BBOX_TOL_MM else "fail",
            f"reloaded {got[0]:.3f} × {got[1]:.3f} × {got[2]:.3f} mm vs report "
            f"{expected_size_mm[0]:.3f} × {expected_size_mm[1]:.3f} × {expected_size_mm[2]:.3f} mm")
    try:
        spec = json.loads((out_dir / "spec.json").read_text(encoding="utf-8"))
        add("spec_parses", "pass" if isinstance(spec, dict) and "outline" in spec else "warn",
            "spec.json parses" + ("" if isinstance(spec, dict) and "outline" in spec else " but has no outline"))
    except (OSError, json.JSONDecodeError) as exc:
        add("spec_parses", "warn", f"spec.json unreadable: {exc}")

    fails = [r.name for r in rows if r.status == "fail"]
    warns = [r.name for r in rows if r.status == "warn"]
    status = "failed" if fails else "needs_review" if warns else "verified"
    reasons = [f"{r.name}: {r.detail}" for r in rows if r.status != "pass"]
    verdict = {"artifact_status": status, "reasons": reasons,
               "rows": [{"check": r.name, "status": r.status, "detail": r.detail} for r in rows],
               "files": fingerprint(out_dir), "photo_sha256": photo_sha256,
               "validated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    (out_dir / "validation.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    return verdict


def read(out_dir: Path) -> dict | None:
    try:
        return json.loads((out_dir / "validation.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def freshness(out_dir: Path, validation: dict | None = None) -> dict:
    """Is validation.json still about the files on disk? ``current`` / ``stale`` / ``missing``, and what changed."""
    if validation is None:
        validation = read(out_dir)
    if not validation:
        return {"state": "missing", "changed": []}
    changed = []
    for name, was in (validation.get("files") or {}).items():
        now = sha256_file(out_dir / name)
        if now != was:
            changed.append(name + (" (gone)" if now is None and was is not None else " (changed)"))
    return {"state": "stale" if changed else "current", "changed": changed}
