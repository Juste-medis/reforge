"""One client for every Meta Model API call: timeouts, retries, a daily budget guard and a usage ledger.

Every real call is appended to ``data/usage/ledger.jsonl`` with its latency and estimated cost, so the
app can show real AI usage numbers and never spend past the configured budget.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from reforge.config import Settings, get_settings
from reforge.errors import ReforgeError

# USD, from dev.meta.ai/docs/pricing-rate-limits (read 2026-10-22). Estimates for the ledger only.
PRICES = {
    "muse-spark-1.3": (1.25e-6, 4.25e-6),
    "muse-spark-1.2": (1.25e-6, 4.25e-6),
    "muse-spark-1.1": (1.25e-6, 4.25e-6),
    "muse-spark-1.3-contributor": (0.10e-6, 0.20e-6),
    "muse-spark-1.2-contributor": (0.10e-6, 0.20e-6),
    "muse-wonder-1.0": (4.00e-6, 20.00e-6),
}
PER_IMAGE = {"sam-3.1": 0.0025, "muse-image-1.0": 0.01}


@dataclass
class UsageRecord:
    stage: str
    model: str
    started_at: str
    latency_s: float
    status: str  # "ok" or an error code
    job_id: str | None = None
    images: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    extra: dict = field(default_factory=dict)


def estimate_cost(model: str, images: int = 0, input_tokens: int = 0, output_tokens: int = 0) -> float:
    if model in PER_IMAGE:
        return PER_IMAGE[model] * images
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return input_tokens * price_in + output_tokens * price_out


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: UsageRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def spent_today(self) -> float:
        today = datetime.now(UTC).date().isoformat()
        return sum(r.get("cost_usd", 0.0) for r in self.records() if r.get("started_at", "").startswith(today))


class MetaClient:
    """Thin wrapper over the OpenAI SDK pointed at the Meta Model API."""

    def __init__(self, settings: Settings | None = None, ledger: Ledger | None = None) -> None:
        self.settings = settings or get_settings()
        key = self.settings.meta_model_api_key
        if key is None or not key.get_secret_value().strip():
            raise ReforgeError("META_KEY_MISSING", "No Meta Model API key is configured.",
                               "Copy .env.example to .env and set META_MODEL_API_KEY.")
        self.ledger = ledger or Ledger(self.settings.reforge_data_dir / "usage" / "ledger.jsonl")
        self.sdk = AsyncOpenAI(base_url=self.settings.meta_api_base_url, api_key=key.get_secret_value(),
                               timeout=self.settings.reforge_request_timeout_s, max_retries=3)

    def check_model(self, model: str, *, own_or_synthetic_data: bool = False) -> None:
        if model.endswith("-contributor") and not (self.settings.reforge_allow_contributor_tier
                                                     and own_or_synthetic_data):
            raise ReforgeError(
                "CONTRIBUTOR_TIER_BLOCKED",
                f"{model} may use submitted content to train Meta models.",
                "Contributor models are only allowed for synthetic or our own test images, with the flag enabled.")

    def check_budget(self, upcoming_usd: float) -> None:
        spent = self.ledger.spent_today()
        cap = self.settings.reforge_daily_budget_usd
        if spent + upcoming_usd > cap + 1e-12:
            raise ReforgeError("BUDGET_EXCEEDED",
                               f"Today's Meta API spend ${spent:.4f} would exceed the ${cap:.2f} cap.",
                               "Raise REFORGE_DAILY_BUDGET_USD or wait until tomorrow (UTC).")

    def record(self, record: UsageRecord) -> None:
        self.ledger.append(record)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def map_api_error(exc: Exception) -> ReforgeError:
    """Turn SDK failures into typed errors without echoing request headers (no key leakage)."""
    if isinstance(exc, APITimeoutError):
        return ReforgeError("META_TIMEOUT", "The Meta Model API did not answer in time.", "Try again.")
    if isinstance(exc, APIConnectionError):
        return ReforgeError("META_UNREACHABLE", "Could not reach the Meta Model API.", "Check the network.")
    if isinstance(exc, APIStatusError):
        code = {401: "META_AUTH", 403: "META_FORBIDDEN", 429: "META_RATE_LIMITED"}.get(exc.status_code,
                                                                                     f"META_HTTP_{exc.status_code}")
        return ReforgeError(code, f"Meta Model API returned HTTP {exc.status_code}.", None)
    return ReforgeError("META_ERROR", type(exc).__name__, None)


class Timer:
    def __enter__(self) -> Timer:
        self.started_at = now_iso()
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed = time.perf_counter() - self._t0
