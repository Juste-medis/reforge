"""AT-2 (live): the production SAM 3.1 path on a SYNTHETIC photo. Real API calls, about $0.0025 each.

Run with:  uv run pytest -m live tests/live -s
"""

import asyncio
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from reforge.capture.calibration import calibrate, rectify
from reforge.config import Settings
from reforge.meta_api.client import MetaClient
from reforge.pipeline import photo_to_stl
from reforge.vision.segment import SamSegmenter, colour_candidate
from tests.synthetic.test_pipeline import _asymmetric_photo

pytestmark = pytest.mark.live


@pytest.fixture
def client(tmp_path: Path) -> MetaClient:
    settings = Settings(reforge_data_dir=tmp_path / "data")  # key from the repo-root .env
    if settings.meta_model_api_key is None:
        pytest.skip("META_MODEL_API_KEY is not configured")
    return MetaClient(settings)


def _click_on_part(photo: Path) -> tuple[int, int]:
    """Where a user would click: a pixel well inside the part, in rectified-view coordinates."""
    image = cv2.imread(str(photo))
    mask = colour_candidate(rectify(image, calibrate(image)))
    inner = cv2.erode(mask.astype(np.uint8), np.ones((9, 9), np.uint8))
    ys, xs = np.nonzero(inner)
    i = int(np.argmin(np.hypot(xs - xs.mean(), ys - ys.mean())))
    return int(xs[i]), int(ys[i])


@pytest.mark.parametrize("mode", ["auto", "click"])
def test_sam_pipeline_end_to_end(client: MetaClient, tmp_path: Path, mode: str) -> None:
    photo = _asymmetric_photo(tmp_path / "photo.png")
    point = _click_on_part(photo) if mode == "click" else None
    segmenter = SamSegmenter(client, point_px=point, job_id="live")
    report = asyncio.run(photo_to_stl(photo, tmp_path / "out", 3.02, segmenter, job_id="live"))
    seg = report["segmentation"]
    print(json.dumps({"mode": mode, "segmentation": seg, "refinement": report["refinement"],
                      "part": report["part"], "timings_s": report["timings_s"]}, indent=2, default=str))
    assert seg["method"] == "sam-3.1" and seg["is_ai"] is True
    assert seg["detail"]["prompt"] == ("point" if mode == "click" else "box")
    assert report["validation"]["valid"], report["validation"]["errors"]
    length, width, _ = report["part"]["overall_mm"]
    assert length == pytest.approx(80, abs=0.1) and width == pytest.approx(28, abs=0.1)
    holes = report["part"]["holes"]
    assert len(holes) == 2 and all(abs(h["diameter_mm"] - 4.2) < 0.05 for h in holes)

    ledger = [json.loads(line) for line in (tmp_path / "data" / "usage" / "ledger.jsonl").read_text().splitlines()]
    assert all(r["model"] == "sam-3.1" and r["status"] == "ok" and r["latency_s"] > 0 for r in ledger)
    assert sum(r["cost_usd"] for r in ledger) == pytest.approx(seg["cost_usd"])
