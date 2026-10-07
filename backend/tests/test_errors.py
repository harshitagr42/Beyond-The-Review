from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.job_service import utcnow
from tests.conftest import make_csv, sample_rows, wait_job


def _upload(client: TestClient, name: str, content: bytes, content_type: str = "text/csv"):
    return client.post(
        "/api/v1/reviews/upload",
        files={"file": (name, io.BytesIO(content), content_type)},
    )


def test_error_invalid_file_format_extension(client):
    r = _upload(client, "document.pdf", b"%PDF-1.4...", "application/pdf")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "INVALID_FILE_FORMAT"
    assert "details" in body


def test_error_invalid_file_format_spoofed_csv_zip(client):
    # .csv filename but starts with zip magic bytes
    r = _upload(client, "spoof.csv", b"PK\x03\x04fakecontent", "text/csv")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "INVALID_FILE_FORMAT"


def test_error_empty_file_zero_bytes(client):
    r = _upload(client, "empty.csv", b"", "text/csv")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "EMPTY_FILE"


def test_error_empty_file_blank_text(client):
    r = _upload(client, "blank.csv", b"   \n\n  \n", "text/csv")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "EMPTY_FILE"


def test_error_unreadable_file_corrupt_xlsx(client):
    # Starts with PK\x03\x04 but is truncated/corrupt zip
    r = _upload(client, "corrupt.xlsx", b"PK\x03\x04corrupteddata", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "UNREADABLE_FILE"


def test_error_unauthorized(settings_factory):
    settings = settings_factory(api_key="my-super-secret-key")
    app = create_app(settings)
    with TestClient(app) as client:
        # Missing key
        r = client.get("/api/v1/health")
        assert r.status_code == 401
        assert r.json()["code"] == "UNAUTHORIZED"

        # Wrong key
        r = client.get("/api/v1/health", headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401
        assert r.json()["code"] == "UNAUTHORIZED"

        # Correct key
        r = client.get("/api/v1/health", headers={"X-API-Key": "my-super-secret-key"})
        assert r.status_code == 200


def test_error_job_not_found(client):
    random_id = "11111111-2222-3333-4444-555555555555"
    r = client.get(f"/api/v1/jobs/{random_id}/status")
    assert r.status_code == 404
    assert r.json()["code"] == "JOB_NOT_FOUND"

    r = client.get("/api/v1/analytics/summary", params={"job_id": random_id})
    assert r.status_code == 404
    assert r.json()["code"] == "JOB_NOT_FOUND"


def test_error_theme_not_found(client, tmp_path):
    csv_path = make_csv(tmp_path / "valid.csv", sample_rows(15))
    with csv_path.open("rb") as fh:
        j = client.post("/api/v1/reviews/upload", files={"file": ("valid.csv", fh, "text/csv")}).json()["job_id"]
    wait_job(client, j)

    r = client.get(f"/api/v1/themes/theme-nonexistent/verbatims", params={"job_id": j})
    assert r.status_code == 404
    assert r.json()["code"] == "THEME_NOT_FOUND"

    r = client.get("/api/v1/analytics/trends", params={"job_id": j, "interval": "weekly", "theme_id": "theme-nonexistent"})
    assert r.status_code == 404
    assert r.json()["code"] == "THEME_NOT_FOUND"


def test_error_job_not_ready_and_job_active(settings_factory, tmp_path):
    # Set sleep so job stays in processing
    settings = settings_factory(mock_progress_sleep=1.0)
    app = create_app(settings)
    with TestClient(app) as client:
        csv_path = make_csv(tmp_path / "slow.csv", sample_rows(20))
        with csv_path.open("rb") as fh:
            j = client.post("/api/v1/reviews/upload", files={"file": ("slow.csv", fh, "text/csv")}).json()["job_id"]

        import time
        # Wait until job enters PROCESSING
        deadline = time.time() + 5.0
        while time.time() < deadline:
            st = client.get(f"/api/v1/jobs/{j}/status").json()
            if st["status"] == "PROCESSING":
                break
            time.sleep(0.05)
        assert st["status"] == "PROCESSING"

        r = client.get("/api/v1/analytics/summary", params={"job_id": j})
        assert r.status_code == 409
        assert r.json()["code"] == "JOB_NOT_READY"
        assert "status" in r.json()["details"]

        # Try deleting active job while it is PROCESSING
        del_r = client.delete(f"/api/v1/jobs/{j}")
        assert del_r.status_code == 409
        assert del_r.json()["code"] == "JOB_ACTIVE"

        wait_job(client, j)


def test_error_job_failed_access(client, tmp_path):
    # 2 rows is below MIN_ROWS=5
    csv_path = make_csv(tmp_path / "too_few.csv", sample_rows(2))
    with csv_path.open("rb") as fh:
        j = client.post("/api/v1/reviews/upload", files={"file": ("too_few.csv", fh, "text/csv")}).json()["job_id"]
    st = wait_job(client, j)
    assert st["status"] == "FAILED"
    assert st["error"]["code"] == "TOO_FEW_ROWS"

    r = client.get("/api/v1/analytics/summary", params={"job_id": j})
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "JOB_FAILED"
    assert body["details"]["code"] == "TOO_FEW_ROWS"


def test_error_file_too_large(settings_factory):
    settings = settings_factory(max_file_size=500)  # 500 bytes limit
    app = create_app(settings)
    with TestClient(app) as client:
        big_content = b"review_text,date,rating\n" + b"Great app!," * 100
        r = _upload(client, "big.csv", big_content)
        assert r.status_code == 413
        assert r.json()["code"] == "FILE_TOO_LARGE"


def test_error_missing_column(client):
    # Missing review_text
    r = _upload(client, "missing_text.csv", b"title,body_info,rating\ngood,nice,5\n")
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "MISSING_COLUMN"
    assert "review_text" in body["details"]["missing"]

    # Missing date when require_date_column is True
    r = _upload(client, "missing_date.csv", b"review_text,rating\ngreat,5\n")
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "MISSING_COLUMN"
    assert "date" in body["details"]["missing"]


def test_error_validation_parameters(client, tmp_path):
    csv_path = make_csv(tmp_path / "valid.csv", sample_rows(15))
    with csv_path.open("rb") as fh:
        j = client.post("/api/v1/reviews/upload", files={"file": ("valid.csv", fh, "text/csv")}).json()["job_id"]
    wait_job(client, j)

    # Missing job_id
    r = client.get("/api/v1/analytics/summary")
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

    # Non-UUID job_id
    r = client.get("/api/v1/analytics/summary", params={"job_id": "not-a-uuid"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

    # Bad interval
    r = client.get("/api/v1/analytics/trends", params={"job_id": j, "interval": "yearly"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

    # Bad themes sort
    r = client.get("/api/v1/themes", params={"job_id": j, "sort": "invalid_sort"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

    # Bad page (< 1)
    r = client.get("/api/v1/themes/theme-1/verbatims", params={"job_id": j, "page": 0})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

    # Bad limit (> 100)
    r = client.get("/api/v1/themes/theme-1/verbatims", params={"job_id": j, "limit": 105})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

    # Bad verbatim sort
    r = client.get("/api/v1/themes/theme-1/verbatims", params={"job_id": j, "sort": "random_order"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

    # Bad verbatim sentiment label
    r = client.get("/api/v1/themes/theme-1/verbatims", params={"job_id": j, "sentiment": "SuperHappy"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_error_no_date_data(settings_factory, tmp_path):
    settings = settings_factory(require_date_column=False)
    app = create_app(settings)
    with TestClient(app) as client:
        # Reviews without date column
        rows = [("App crashed several times", "", 1) for _ in range(12)]
        csv_path = make_csv(tmp_path / "nodate.csv", rows)
        with csv_path.open("rb") as fh:
            j = client.post("/api/v1/reviews/upload", files={"file": ("nodate.csv", fh, "text/csv")}).json()["job_id"]
        wait_job(client, j)

        r = client.get("/api/v1/analytics/trends", params={"job_id": j, "interval": "weekly"})
        assert r.status_code == 422
        assert r.json()["code"] == "NO_DATE_DATA"


def test_error_queue_full(settings_factory, tmp_path):
    settings = settings_factory(queue_max_size=1, mock_progress_sleep=1.0)
    app = create_app(settings)
    with TestClient(app) as client:
        csv1 = make_csv(tmp_path / "q1.csv", sample_rows(12))
        csv2 = make_csv(tmp_path / "q2.csv", sample_rows(12))
        csv3 = make_csv(tmp_path / "q3.csv", sample_rows(12))

        with csv1.open("rb") as fh:
            j1 = client.post("/api/v1/reviews/upload", files={"file": ("q1.csv", fh, "text/csv")}).json()["job_id"]
        with csv2.open("rb") as fh:
            client.post("/api/v1/reviews/upload", files={"file": ("q2.csv", fh, "text/csv")})
        # Queue max size is 1, so third upload should be rejected with 429
        with csv3.open("rb") as fh:
            r3 = client.post("/api/v1/reviews/upload", files={"file": ("q3.csv", fh, "text/csv")})
        assert r3.status_code == 429
        assert r3.json()["code"] == "QUEUE_FULL"


def test_error_engine_unavailable(client, monkeypatch):
    # Simulate worker engine failing
    worker = client.app.state.worker
    monkeypatch.setattr(worker, "engine_status", lambda: {"status": "failed", "mode": "mock", "device": None})

    r = _upload(client, "test.csv", b"review_text,date,rating\ngreat app,2026-08-01,5\n")
    assert r.status_code == 503
    assert r.json()["code"] == "ENGINE_UNAVAILABLE"


def test_framework_error_shapes(client):
    # 404 unmapped route
    r = client.get("/api/v1/non_existent_route")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "NOT_FOUND"
    assert "error" in body
    assert "details" in body

    # 405 Method Not Allowed
    r = client.post("/api/v1/health")
    assert r.status_code == 405
    body = r.json()
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert "error" in body
    assert "details" in body
