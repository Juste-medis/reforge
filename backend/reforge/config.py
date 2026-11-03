"""Typed configuration from the environment and the repo-root ``.env``. The key is never logged."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    meta_model_api_key: SecretStr | None = None
    meta_api_base_url: str = "https://api.meta.ai/v1"
    reforge_model_reasoning: str = "muse-spark-1.3"
    reforge_model_segmentation: str = "sam-3.1"
    reforge_model_image: str = "muse-image-1.0"
    # Contributor-tier content may be used to train Meta models: synthetic or our own test images only.
    reforge_allow_contributor_tier: bool = False
    reforge_daily_budget_usd: float = 5.0
    reforge_data_dir: Path = REPO_ROOT / "data"
    reforge_request_timeout_s: float = 90.0
    # Web server. 127.0.0.1 keeps it local; a container or a reverse proxy sets 0.0.0.0.
    reforge_host: str = "127.0.0.1"
    reforge_port: int = 8000
    reforge_max_running_jobs: int = 2
    reforge_max_queued_jobs: int = 8


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
