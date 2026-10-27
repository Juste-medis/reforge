"""SAM result handling and Meta client guards. No network calls.

The SAM records here are SYNTHETIC fixtures built with meta-sam-parser's own types and encoder,
not recorded API output.
"""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from meta_sam_parser import SegmentationMask, SegmentationMaskBounds
from meta_sam_parser._mask_codec import _encode_raster  # private; test-only

from reforge.config import Settings
from reforge.errors import ReforgeError
from reforge.meta_api.client import Ledger, MetaClient, UsageRecord, estimate_cost
from reforge.vision.segment import masks_from_result, select_part


def _record(object_id: str, local: np.ndarray, left: int, top: int, conf: float | None = None):
    # The encoder's output already starts with the one_bit marker "!", which the decoder requires.
    payload = _encode_raster(local.astype(np.uint8).flatten().tolist(), local.shape[1], local.shape[0])
    return SimpleNamespace(
        kind="mask", object_id=object_id, confidence=conf,
        mask=SegmentationMask("one_bit", payload, local.shape[1], local.shape[0]),
        bounds=SegmentationMaskBounds(left=left, top=top, right=left + local.shape[1], bottom=top + local.shape[0]))


def test_box_local_masks_are_placed_in_the_frame() -> None:
    local = np.zeros((20, 30), bool)
    local[5:15, 5:25] = True
    (oid, full, conf), = masks_from_result(SimpleNamespace(records=(_record("7", local, 40, 10, 0.9),)), (100, 60))
    assert oid == "7" and conf == 0.9 and full.shape == (60, 100)
    assert full.sum() == local.sum() and full[15:25, 45:65].all()


def test_selection_skips_the_mat_and_border_objects() -> None:
    size = (100, 80)
    mat = np.ones((80, 100), bool)
    edge = np.zeros((80, 100), bool)
    edge[0:10, 0:50] = True
    part = np.zeros((80, 100), bool)
    part[30:50, 20:70] = True
    small = np.zeros((80, 100), bool)
    small[60:65, 10:15] = True
    oid, mask, _ = select_part([("mat", mat, 0.99), ("edge", edge, 0.9), ("part", part, 0.8), ("tiny", small, 0.95)])
    assert oid == "part" and mask is part
    with pytest.raises(ReforgeError) as info:
        select_part([("mat", mat, 0.99)])
    assert info.value.code == "SEG_NO_PART"
    assert size  # silence unused


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(_env_file=None, meta_model_api_key="test-key-not-real", reforge_data_dir=tmp_path, **kw)


def test_missing_key_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(ReforgeError) as info:
        MetaClient(Settings(_env_file=None, meta_model_api_key=None, reforge_data_dir=tmp_path))
    assert info.value.code == "META_KEY_MISSING"


def test_contributor_tier_needs_flag_and_own_data(tmp_path: Path) -> None:
    client = MetaClient(_settings(tmp_path))
    with pytest.raises(ReforgeError) as info:
        client.check_model("muse-spark-1.3-contributor", own_or_synthetic_data=True)
    assert info.value.code == "CONTRIBUTOR_TIER_BLOCKED"
    allowed = MetaClient(_settings(tmp_path, reforge_allow_contributor_tier=True))
    with pytest.raises(ReforgeError):
        allowed.check_model("muse-spark-1.3-contributor")  # user data: still blocked
    allowed.check_model("muse-spark-1.3-contributor", own_or_synthetic_data=True)
    client.check_model("muse-spark-1.3")


def test_daily_budget_guard(tmp_path: Path) -> None:
    client = MetaClient(_settings(tmp_path, reforge_daily_budget_usd=0.01))
    client.record(UsageRecord(stage="segmentation", model="sam-3.1", started_at=datetime.now(UTC).isoformat(),
                              latency_s=1.0, status="ok", images=3, cost_usd=estimate_cost("sam-3.1", images=3)))
    client.check_budget(0.0025)  # 0.0075 + 0.0025 = 0.01: allowed
    with pytest.raises(ReforgeError) as info:
        client.check_budget(0.003)
    assert info.value.code == "BUDGET_EXCEEDED"
    assert Ledger(tmp_path / "usage" / "ledger.jsonl").spent_today() == pytest.approx(0.0075)


def test_key_never_appears_in_ledger(tmp_path: Path) -> None:
    client = MetaClient(_settings(tmp_path))
    client.record(UsageRecord(stage="x", model="sam-3.1", started_at=datetime.now(UTC).isoformat(),
                              latency_s=0.1, status="ok"))
    assert "test-key-not-real" not in (tmp_path / "usage" / "ledger.jsonl").read_text()
    assert "test-key-not-real" not in repr(client.settings)
