from __future__ import annotations

import json
import logging
from pathlib import Path
from fastapi.testclient import TestClient

from app.utils.highlighting import highlight_text, py_to_utf16
from tests.conftest import make_csv, sample_rows, wait_job


def test_governance_metrics_shape_and_audit(client, tmp_path):
    csv_path = make_csv(tmp_path / "gov.csv", sample_rows(15))
    with csv_path.open("rb") as fh:
        job_id = client.post("/api/v1/reviews/upload", files={"file": ("gov.csv", fh, "text/csv")}).json()["job_id"]
    wait_job(client, job_id)

    r = client.get("/api/v1/governance/metrics", params={"job_id": job_id})
    assert r.status_code == 200
    gov = r.json()

    assert gov["job_id"] == job_id
    assert gov["pii"]["raw_text_stored"] is False
    assert set(gov["pii"]["tags"]) == {"[EMAIL_REDACTED]", "[PHONE_REDACTED]", "[PII_REDACTED]"}
    assert gov["models"]["external_data_egress"] is False
    assert gov["models"]["llm_assist"] == "off"

    events = [e["event"] for e in gov["audit_log"]]
    assert "UPLOAD_RECEIVED" in events
    assert "JOB_STARTED" in events
    assert "PII_REDACTION_COMPLETED" in events
    assert "JOB_COMPLETED" in events
    assert "RAW_FILE_DELETED" in events


def test_no_pii_leak_in_responses_db_and_logs(client, tmp_path, caplog):
    caplog.set_level(logging.INFO)

    secret_email = "test_user_supersecret_42@private-domain.org"
    secret_phone = "415-555-0199"
    secret_ssn = "987-65-4321"
    secret_card = "4111 1111 1111 9999"
    secret_ip = "192.168.1.189"

    secrets = [secret_email, secret_phone, secret_ssn, secret_card, secret_ip]

    reviews_with_pii = [
        (f"Please contact me at {secret_email} regarding this issue.", "2026-08-01", 1),
        (f"Call support line {secret_phone} immediately.", "2026-08-02", 2),
        (f"My invoice has SSN {secret_ssn} displayed.", "2026-08-03", 1),
        (f"Card {secret_card} was charged twice.", "2026-08-04", 1),
        (f"Connected from IP {secret_ip} when it failed.", "2026-08-05", 2),
    ] + sample_rows(10)

    csv_path = make_csv(tmp_path / "pii_reviews.csv", reviews_with_pii)
    with csv_path.open("rb") as fh:
        job_id = client.post("/api/v1/reviews/upload", files={"file": ("pii_reviews.csv", fh, "text/csv")}).json()["job_id"]
    wait_job(client, job_id)

    # 1. Assert secrets not in any API response
    summary_text = client.get("/api/v1/analytics/summary", params={"job_id": job_id}).text
    breakdown_text = client.get("/api/v1/analytics/sentiment-breakdown", params={"job_id": job_id}).text
    themes_text = client.get("/api/v1/themes", params={"job_id": job_id}).text
    gov_text = client.get("/api/v1/governance/metrics", params={"job_id": job_id}).text
    status_text = client.get(f"/api/v1/jobs/{job_id}/status").text

    themes = client.get("/api/v1/themes", params={"job_id": job_id}).json()["themes"]
    verbatims_text = ""
    for t in themes:
        verbatims_text += client.get(f"/api/v1/themes/{t['id']}/verbatims", params={"job_id": job_id, "limit": 100}).text

    all_api_output = " ".join([summary_text, breakdown_text, themes_text, gov_text, status_text, verbatims_text])
    for s in secrets:
        assert s not in all_api_output, f"Secret {s} leaked in API responses!"

    # 2. Assert secrets not in database
    repo = client.app.state.repo
    with repo._write_lock:
        conn = repo._connect()
        # Check reviews_scored
        rows = conn.execute("SELECT text FROM reviews_scored WHERE job_id = ?", (job_id,)).fetchall()
        for r in rows:
            for s in secrets:
                assert s not in r["text"], f"Secret {s} leaked in database reviews_scored!"

        # Check job_results
        result_row = conn.execute("SELECT * FROM job_results WHERE job_id = ?", (job_id,)).fetchone()
        result_blob = json.dumps([result_row["summary"], result_row["sentiment_breakdown"], result_row["meta"]])
        for s in secrets:
            assert s not in result_blob, f"Secret {s} leaked in database job_results!"

        # Check audit_events
        audit_rows = conn.execute("SELECT details FROM audit_events WHERE job_id = ?", (job_id,)).fetchall()
        for ar in audit_rows:
            for s in secrets:
                assert s not in ar["details"], f"Secret {s} leaked in audit_events!"

    # 3. Assert secrets not in captured log output
    log_text = caplog.text
    for s in secrets:
        assert s not in log_text, f"Secret {s} leaked in logs!"


def test_highlighting_offsets_with_emoji_and_astral_characters():
    # Emoji: "🎉" is 1 char in Python, but 2 code units in UTF-16
    # "💔" is also 2 code units in UTF-16
    text = "🎉 App crashed right after launch! 💔"
    highlights = highlight_text(text)
    assert len(highlights) > 0

    # Ensure start and end indices accurately locate the word in JavaScript-style UTF-16
    # In Python, text.encode('utf-16-le') simulates UTF-16 code units:
    encoded_16 = text.encode("utf-16-le")
    for h in highlights:
        start_unit = h["start"]
        end_unit = h["end"]
        # Slice UTF-16 bytes (each code unit is 2 bytes)
        sliced_bytes = encoded_16[start_unit * 2 : end_unit * 2]
        decoded = sliced_bytes.decode("utf-16-le")
        assert decoded == h["term"], f"Offset mismatch: expected '{h['term']}', got '{decoded}'"
