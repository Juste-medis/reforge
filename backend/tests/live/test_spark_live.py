"""Live D4: SAM 3.1 segments and Muse Spark interprets a SYNTHETIC photo of a broken 3 mm bracket (standard tier).

Opt-in (``pytest -m live``); about $0.016 per run (one SAM call, one Spark call). Spark is not told which segments
the geometry finds irregular, so its fracture picks are an independent judgement checked against the geometry.
"""

import asyncio
import json
from pathlib import Path

import cv2
import pytest

from reforge.capture.mat import mat_layout
from reforge.config import Settings
from reforge.meta_api.client import MetaClient
from reforge.pipeline import photo_to_stl
from reforge.reasoning.interpret import SparkInterpreter
from reforge.vision.segment import SamSegmenter
from tests.synthetic.scene import PartShape, broken_bracket, make_camera, render_view

pytestmark = pytest.mark.live
LAYOUT = mat_layout("A4")


def test_spark_reads_the_break_and_the_part_is_rebuilt(tmp_path: Path) -> None:
    photo = tmp_path / "broken.png"
    camera = make_camera(LAYOUT, 6, -4, 12)
    part = PartShape(broken_bracket(LAYOUT, seed=0), height_mm=3.0)
    cv2.imwrite(str(photo), render_view(LAYOUT, camera, parts=(part,), blur_sigma=0.8, noise_sigma=2.0, seed=4))
    client = MetaClient(Settings(reforge_data_dir=tmp_path / "data"))
    report = asyncio.run(photo_to_stl(photo, tmp_path / "out", 3.0, SamSegmenter(client, job_id="live-d4"),
                                      job_id="live-d4", interpreter=SparkInterpreter(client, job_id="live-d4")))
    recon = report["reconstruction"]
    interp = recon["interpretation"]
    assert interp["method"] == "muse-spark-1.3" and interp["is_ai"] and interp["fallback_reason"] is None
    analysis = interp["analysis"]
    assert analysis["is_broken"] and analysis["symmetry"] == "mirror"
    irregular = {s["id"] for s in recon["segments"] if s["kind"] == "irregular"}
    picked = set(analysis["fracture_segment_ids"])
    assert len(picked & irregular) >= len(irregular) // 2, (picked, irregular)
    assert not any(n["level"] == "rejected" for n in recon["verification"]), recon["verification"]

    completion = recon["completion"]
    assert completion is not None and completion["added_area_mm2"] > 80
    length, width, _ = report["part"]["overall_mm"]
    assert length == pytest.approx(80.0, abs=0.1) and width == pytest.approx(28.0, abs=0.1)
    assert report["validation"]["valid"]

    ledger = [json.loads(line) for line in (tmp_path / "data" / "usage" / "ledger.jsonl").read_text().splitlines()]
    spark = [r for r in ledger if r["stage"] == "interpretation"]
    assert len(spark) == 1 and spark[0]["status"] == "ok" and spark[0]["input_tokens"] > 0 and spark[0]["cost_usd"] > 0
    assert any(r["model"] == "sam-3.1" for r in ledger)
