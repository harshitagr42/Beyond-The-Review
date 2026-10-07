from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 8000
    cors_origin: str = "http://localhost:3000"
    max_file_size: int = 104_857_600
    min_rows: int = 10
    max_rows: int = 100_000
    require_date_column: bool = True
    data_dir: Path = Path("./data_store")
    database_url: str = "sqlite:///./data_store/app.db"
    keep_raw_uploads: bool = False
    job_retention_days: int = 7
    job_timeout_seconds: int = 3600
    worker_concurrency: int = Field(
        default=1,
        description="Number of spawn worker processes. Raising this loads the ML engine once per worker and multiplies memory use.",
    )
    queue_max_size: int = 20
    dashboard_theme_limit: int = 10
    trend_low_sample: int = 10
    api_key: str = ""
    log_level: str = "INFO"
    ml_engine: Literal["mock", "local"] = "mock"
    ml_engine_path: Path = Path("../ml-engine")
    mock_progress_sleep: float = Field(
        default=0.05,
        description="Seconds to sleep per mock-engine stage (set 0 in tests).",
    )
    max_xlsx_uncompressed: int = 524_288_000
    stage_weight_parsing: float = 5
    stage_weight_pii: float = 5
    stage_weight_sentiment: float = 30
    stage_weight_embeddings: float = 15
    stage_weight_topics: float = 35
    stage_weight_validation: float = 2.5
    stage_weight_drift: float = 2.5
    stage_weight_persisting: float = 5

    @field_validator("worker_concurrency")
    @classmethod
    def _concurrency_at_least_one(cls, v: int) -> int:
        return max(1, v)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origin.split(",") if o.strip()]

    @property
    def api_key_required(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def sqlite_path(self) -> Path:
        url = self.database_url
        prefix = "sqlite:///"
        if url.startswith(prefix):
            raw = url[len(prefix) :]
            if raw.startswith("/") and not raw.startswith("///"):
                return Path(raw)
            return Path(raw)
        return self.data_dir / "app.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def stage_weights(self) -> dict[str, float]:
        return {
            "parsing": self.stage_weight_parsing,
            "pii_redaction": self.stage_weight_pii,
            "sentiment": self.stage_weight_sentiment,
            "embeddings": self.stage_weight_embeddings,
            "topics": self.stage_weight_topics,
            "validation": self.stage_weight_validation,
            "drift": self.stage_weight_drift,
            "persisting": self.stage_weight_persisting,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
