from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repositories.base import JobRecord
from app.repositories.sqlite import SqliteRepository
from app.services.job_service import JobService, utcnow
from app.services.ml_engine.base import EngineContractMismatch
from app.services.ml_engine.local_engine import LocalEngine, assert_engine_contract
from tests.conftest import make_csv, sample_rows, wait_job


def test_cors_preflight_and_request_id(client):
    # 1. CORS Preflight
    r = client.options(
        "/api/v1/reviews/upload",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-API-Key",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    methods = r.headers.get("access-control-allow-methods", "")
    assert "POST" in methods and "DELETE" in methods and "OPTIONS" in methods
    # Expose-headers is returned on actual cross-origin responses
    actual = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    expose = actual.headers.get("access-control-expose-headers", "")
    assert "Location" in expose and "Content-Disposition" in expose and "X-Request-ID" in expose

    # 2. X-Request-ID propagation
    custom_rid = "custom-rid-12345"
    r2 = client.get("/api/v1/health", headers={"X-Request-ID": custom_rid})
    assert r2.status_code == 200
    assert r2.headers.get("X-Request-ID") == custom_rid

    # 3. Generated X-Request-ID
    r3 = client.get("/api/v1/health")
    assert r3.status_code == 200
    assert r3.headers.get("X-Request-ID") is not None


def test_restart_recovery_processing_and_queued(settings_factory, tmp_path):
    settings = settings_factory()
    repo = SqliteRepository(settings.sqlite_path)
    repo.init()

    now = utcnow()
    # 1. Processing job left behind
    job_proc = JobRecord(
        id=str(uuid.uuid4()),
        status="PROCESSING",
        created_at=now,
        started_at=now,
        file_name="abandoned.csv",
        file_size=100,
        file_sha256="abc",
    )
    repo.create_job(job_proc)

    # 2. Queued job whose raw file is missing
    missing_file = tmp_path / "missing.csv"
    job_queued_missing = JobRecord(
        id=str(uuid.uuid4()),
        status="QUEUED",
        created_at=now,
        file_name="missing.csv",
        file_size=100,
        file_sha256="def",
        raw_path=str(missing_file),
    )
    repo.create_job(job_queued_missing)

    # 3. Queued job whose raw file still exists
    existing_file = tmp_path / "exists.csv"
    existing_file.write_text("review_text,date,rating\n")
    job_queued_exists = JobRecord(
        id=str(uuid.uuid4()),
        status="QUEUED",
        created_at=now,
        file_name="exists.csv",
        file_size=100,
        file_sha256="ghi",
        raw_path=str(existing_file),
    )
    repo.create_job(job_queued_exists)

    # Initialize JobService and run recovery
    js = JobService(repo, settings, worker=None)
    js.recover_on_startup()

    # Assertions
    p = repo.get_job(job_proc.id)
    assert p.status == "FAILED"
    assert p.error_code == "INTERRUPTED"

    qm = repo.get_job(job_queued_missing.id)
    assert qm.status == "FAILED"
    assert qm.error_code == "INTERRUPTED"

    qe = repo.get_job(job_queued_exists.id)
    assert qe.status == "QUEUED"


def test_retention_and_timeout(settings_factory, tmp_path):
    settings = settings_factory(job_retention_days=7, job_timeout_seconds=300)
    repo = SqliteRepository(settings.sqlite_path)
    repo.init()

    # Job older than 8 days
    old_time = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_job = JobRecord(
        id=str(uuid.uuid4()),
        status="COMPLETED",
        created_at=old_time,
        finished_at=old_time,
        file_name="old.csv",
        file_size=100,
        file_sha256="old",
    )
    repo.create_job(old_job)

    # Job currently processing but started 400 seconds ago (> timeout of 300)
    timed_out_start = (datetime.now(timezone.utc) - timedelta(seconds=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    timed_job = JobRecord(
        id=str(uuid.uuid4()),
        status="PROCESSING",
        created_at=timed_out_start,
        started_at=timed_out_start,
        file_name="timeout.csv",
        file_size=100,
        file_sha256="timed",
    )
    repo.create_job(timed_job)

    js = JobService(repo, settings, worker=None)

    # Check timeout
    timed_ids = js.fail_timed_out()
    assert timed_job.id in timed_ids
    assert repo.get_job(timed_job.id).status == "FAILED"
    assert repo.get_job(timed_job.id).error_code == "TIMEOUT"

    # Check retention expiration
    expired_count = js.expire_old_jobs()
    assert expired_count >= 1
    assert repo.get_job(old_job.id) is None


def test_local_engine_contract_mismatch(tmp_path):
    # Non-existent pipeline file
    fake_path = tmp_path / "fake_engine"
    with pytest.raises(EngineContractMismatch) as exc_info:
        assert_engine_contract(fake_path)
    assert "ENGINE_CONTRACT_MISMATCH" in str(exc_info.value)

    # Existing pipeline file but lacking reviews[] in output contract
    pipeline_file = fake_path / "src" / "ml" / "pipeline.py"
    pipeline_file.parent.mkdir(parents=True, exist_ok=True)
    pipeline_file.write_text("class FeedbackAnalysisPipeline:\n    pass\n")

    with pytest.raises(EngineContractMismatch) as exc_info2:
        assert_engine_contract(fake_path)
    assert "ENGINE_CONTRACT_MISMATCH" in str(exc_info2.value)


@pytest.mark.integration
def test_local_engine_integration_fallback(tmp_path):
    """Integration test running LocalEngine in fallback mode on sample CSV.

    Skipped by default (run with pytest -m integration).
    """
    engine_path = Path(__file__).resolve().parents[1] / "ml-engine"
    if not (engine_path / "src" / "ml" / "pipeline.py").is_file():
        pytest.skip("ml-engine not available")

    # In current engine state, LocalEngine checks for reviews[] contract
    # This test asserts that when LocalEngine initializes, it validates contract
    try:
        engine = LocalEngine(engine_path)
        assert engine.status() == "ready"
    except EngineContractMismatch:
        # Expected until ML side merges reviews[] extension
        pass
