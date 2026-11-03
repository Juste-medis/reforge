"""Check a job's exported files for real: the STL is loaded as a mesh, and the OpenSCAD file is compiled by OpenSCAD
itself (its WASM build, ``tools/scad-check``) and compared with the STL. A download button is not evidence; this is.

    cd tools/scad-check && npm install          # once
    cd backend && uv run python -m tools.check_exports ../data/jobs/<id> [more job folders…] [--hole-offset 0.2]

With ``--hole-offset`` the files are fetched from a running API (``--api``), so the compensated rebuild is checked too.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import trimesh

from reforge.config import REPO_ROOT

SCAD2STL = REPO_ROOT / "tools" / "scad-check" / "scad2stl.mjs"


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("node not found: put Node ≥ 22 on PATH (docs/ENVIRONMENT.md)")
    return node


def check(job: Path, api: str | None, hole_offset: float) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        if hole_offset:
            assert api, "--api is needed with --hole-offset"
            for name in ("model.stl", "model.scad"):
                url = f"{api}/api/jobs/{job.name}/{name}?hole_offset_mm={hole_offset:.2f}"
                with urllib.request.urlopen(url) as resp:  # noqa: S310 (local API)
                    (tmp_dir / name).write_bytes(resp.read())
            stl_path, scad_path = tmp_dir / "model.stl", tmp_dir / "model.scad"
        else:
            stl_path, scad_path = job / "model.stl", job / "model.scad"
        ours = trimesh.load(stl_path, file_type="stl")
        out = tmp_dir / "from_scad.stl"
        run = subprocess.run([_node(), str(SCAD2STL), str(scad_path), str(out)], capture_output=True, text=True,
                             timeout=600, check=True)
        info = json.loads(run.stdout.strip().splitlines()[-1])
        theirs = trimesh.load(io.BytesIO(out.read_bytes()), file_type="stl")
    report = json.loads((job / "report.json").read_text())
    return {
        "job": job.name,
        "holes_in_spec": len(report["part"]["holes"]),
        "hole_offset_mm": hole_offset,
        "stl_watertight": bool(ours.is_watertight),
        "stl_volume_mm3": round(float(ours.volume), 3),
        "scad_compiled_ms": info["ms"],
        "scad_messages": info["messages"],
        "scad_watertight": bool(theirs.is_watertight),
        "scad_volume_mm3": round(float(theirs.volume), 3),
        "volume_rel_diff": float(abs(theirs.volume - ours.volume) / ours.volume),
        "bounds_max_diff_mm": float(abs(theirs.bounds - ours.bounds).max()),
        "genus_stl": int((2 - ours.euler_number) // 2),
        "genus_scad": int((2 - theirs.euler_number) // 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="+", type=Path)
    parser.add_argument("--api", default=None, help="base URL of a running API, for --hole-offset")
    parser.add_argument("--hole-offset", type=float, default=0.0)
    args = parser.parse_args()
    for job in args.jobs:
        print(json.dumps(check(job, args.api, args.hole_offset)))


if __name__ == "__main__":
    main()
