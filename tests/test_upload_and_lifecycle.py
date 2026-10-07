from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_csv, sample_rows, wait_job


def _upload(client: TestClient, path: Path, sheet: str | None = None):
    data = {"sheet": sheet} if sheet else None
    with path.open("rb") as fh:
        return client.post("/api/v1/reviews/upload", files={"file": (path.name, fh, "text/csv")}, data=data)


def test_upload_happy_path_and_endpoints(client, tmp_path):
    csv_path = make_csv(tmp_path / "reviews.csv", sample_rows(30))
    r = _upload(client, csv_path)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "QUEUED"
    assert "job_id" in body
    assert r.headers.get("Location") == body["status_url"]
    job_id = body["job_id"]
    st = wait_job(client, job_id)
    assert st["status"] == "COMPLETED"
    assert st["progress_percent"] == 100
    assert st["queue_position"] is None
    assert st["rows"]["analyzed"] == 30

    summary = client.get("/api/v1/analytics/summary", params={"job_id": job_id})
    assert summary.status_code == 200
    payload = summary.json()
    assert set(payload) == {"summary", "sentiment_breakdown", "themes"}
    assert set(payload["summary"]) == {
        "total_reviews",
        "overall_sentiment",
        "net_sentiment_score",
        "pii_redacted_count",
        "model_validation_accuracy",
        "drift_status",
    }

    bd = client.get("/api/v1/analytics/sentiment-breakdown", params={"job_id": job_id})
    assert bd.status_code == 200
    counts = bd.json()["counts"]
    assert counts["positive"] + counts["neutral"] + counts["negative"] + counts["strongly_negative"] == 30

    themes = client.get("/api/v1/themes", params={"job_id": job_id})
    assert themes.status_code == 200
    t0 = themes.json()["themes"][0]
    ver = client.get(f"/api/v1/themes/{t0['id']}/verbatims", params={"job_id": job_id, "page": 1, "limit": 5})
    assert ver.status_code == 200
    trends = client.get("/api/v1/analytics/trends", params={"job_id": job_id, "interval": "weekly"})
    assert trends.status_code == 200
    gov = client.get("/api/v1/governance/metrics", params={"job_id": job_id})
    assert gov.status_code == 200
    deleted = client.delete(f"/api/v1/jobs/{job_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/jobs/{job_id}/status").status_code == 404


def test_two_uploads_queue_fifo(settings_factory, tmp_path):
    settings = settings_factory(mock_progress_sleep=0.12)
    application = create_app(settings)
    with TestClient(application) as client:
        csv1 = make_csv(tmp_path / "a.csv", sample_rows(20))
        csv2 = make_csv(tmp_path / "b.csv", sample_rows(20))
        j1 = _upload(client, csv1).json()["job_id"]
        j2 = _upload(client, csv2).json()["job_id"]
        s2 = client.get(f"/api/v1/jobs/{j2}/status").json()
        s1 = client.get(f"/api/v1/jobs/{j1}/status").json()
        # First should be processing (or already done if extremely fast); second queued or processing after
        if s1["status"] == "PROCESSING":
            assert s2["status"] == "QUEUED"
            assert s2["queue_position"] == 0
        wait_job(client, j1)
        wait_job(client, j2)
        assert client.get(f"/api/v1/jobs/{j1}/status").json()["status"] == "COMPLETED"
        assert client.get(f"/api/v1/jobs/{j2}/status").json()["status"] == "COMPLETED"


def test_raw_file_deleted_after_success(client, tmp_path, settings_factory):
    csv_path = make_csv(tmp_path / "ok.csv", sample_rows(12))
    job_id = _upload(client, csv_path).json()["job_id"]
    wait_job(client, job_id)
    uploads = list(client.app.state.settings.uploads_dir.glob("*"))
    assert uploads == []


def test_raw_file_deleted_after_failure(client, tmp_path):
    csv_path = make_csv(tmp_path / "few.csv", sample_rows(2))
    job_id = _upload(client, csv_path).json()["job_id"]
    st = wait_job(client, job_id)
    assert st["status"] == "FAILED"
    assert st["error"]["code"] == "TOO_FEW_ROWS"
    uploads = list(client.app.state.settings.uploads_dir.glob("*"))
    assert uploads == []


def test_progress_reaches_completed(client, tmp_path):
    csv_path = make_csv(tmp_path / "p.csv", sample_rows(15))
    job_id = _upload(client, csv_path).json()["job_id"]
    st = wait_job(client, job_id)
    assert st["progress_percent"] == 100
    assert st["status"] == "COMPLETED"


def test_sample_download(client):
    r = client.get("/api/v1/reviews/sample")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "sample_reviews.csv" in r.headers.get("content-disposition", "")
    assert b"review_text" in r.content
