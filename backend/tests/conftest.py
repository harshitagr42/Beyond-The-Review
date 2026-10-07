from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture
def settings_factory(tmp_path, monkeypatch):
    def _make(**overrides) -> Settings:
        data_dir = tmp_path / "data"
        db = data_dir / "app.db"
        env = {
            "ML_ENGINE": "mock",
            "MOCK_PROGRESS_SLEEP": "0",
            "MIN_ROWS": "5",
            "REQUIRE_DATE_COLUMN": "true",
            "DATA_DIR": str(data_dir),
            "DATABASE_URL": f"sqlite:///{db}",
            "KEEP_RAW_UPLOADS": "false",
            "QUEUE_MAX_SIZE": "20",
            "LOG_LEVEL": "INFO",
            "API_KEY": "",
            "CORS_ORIGIN": "http://localhost:3000",
        }
        for k, v in env.items():
            monkeypatch.setenv(k, str(v))
        get_settings.cache_clear()
        kwargs = dict(
            ml_engine="mock",
            mock_progress_sleep=0.0,
            min_rows=5,
            require_date_column=True,
            data_dir=data_dir,
            database_url=f"sqlite:///{db}",
            keep_raw_uploads=False,
            queue_max_size=20,
            api_key="",
            cors_origin="http://localhost:3000",
            job_timeout_seconds=3600,
            worker_concurrency=1,
        )
        kwargs.update(overrides)
        return Settings(**kwargs)

    return _make


@pytest.fixture
def client(settings_factory):
    settings = settings_factory()
    application = create_app(settings)
    with TestClient(application) as c:
        _wait_engine(c)
        yield c


def _wait_engine(client: TestClient, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get("/api/v1/health")
        if r.status_code == 200 and r.json()["engine"]["status"] in {"ready", "failed"}:
            return
        time.sleep(0.05)


def wait_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/v1/jobs/{job_id}/status")
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in {"COMPLETED", "FAILED"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {last}")


def make_csv(path: Path, rows: list[tuple[str, str, str | int]]) -> Path:
    lines = ["review_text,date,rating"]
    for text, date, rating in rows:
        safe = '"' + str(text).replace('"', '""') + '"'
        lines.append(f"{safe},{date},{rating}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def sample_rows(n: int = 20, with_dates: bool = True) -> list[tuple[str, str, int]]:
    texts = [
        "The app crashed when I hit pause.",
        "Charged twice for my monthly subscription.",
        "Love the smooth playback and sharp picture.",
        "Search never finds the video I want.",
        "Pretty average experience overall.",
        "Battery drain is awful after the update.",
        "Refund came through within two days, thanks!",
        "Comment section never loads on live streams.",
    ]
    rows = []
    for i in range(n):
        date = f"2026-07-{(i % 28) + 1:02d}" if with_dates else ""
        rows.append((texts[i % len(texts)] + f" #{i}", date or "2026-08-01", (i % 5) + 1))
    return rows
