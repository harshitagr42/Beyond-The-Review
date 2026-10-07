from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient

from app.schemas.analytics import AnalyticsSummary
from tests.conftest import make_csv, sample_rows, wait_job


def _upload_and_complete(client: TestClient, tmp_path: Path, n: int = 40) -> str:
    csv_path = make_csv(tmp_path / f"job_{n}.csv", sample_rows(n))
    with csv_path.open("rb") as fh:
        j = client.post("/api/v1/reviews/upload", files={"file": (csv_path.name, fh, "text/csv")}).json()["job_id"]
    wait_job(client, j)
    return j


def test_contract_analytics_summary_exact_schema(client, tmp_path):
    job_id = _upload_and_complete(client, tmp_path, 30)
    r = client.get("/api/v1/analytics/summary", params={"job_id": job_id})
    assert r.status_code == 200
    data = r.json()

    # Validate against strict Pydantic model (extra='forbid')
    validated = AnalyticsSummary.model_validate(data)
    assert validated.summary.total_reviews == 30
    assert validated.summary.overall_sentiment in {"Positive Trend", "Negative Trend", "Mixed Trend"}
    assert -100 <= validated.summary.net_sentiment_score <= 100
    assert validated.summary.drift_status != ""
    assert validated.sentiment_breakdown.positive + validated.sentiment_breakdown.neutral + validated.sentiment_breakdown.negative == 100
    assert len(validated.themes) <= 10  # default DASHBOARD_THEME_LIMIT

    # Every verbatim id has format v{row}
    for theme in validated.themes:
        for sv in theme.sample_verbatims:
            assert sv.id.startswith("v")
            int(sv.id[1:])  # must be integer row


def test_verbatim_cross_reference_with_themes(client, tmp_path):
    job_id = _upload_and_complete(client, tmp_path, 35)

    summary = client.get("/api/v1/analytics/summary", params={"job_id": job_id}).json()
    for t in summary["themes"]:
        theme_id = t["id"]
        # Fetch all verbatims for this theme
        verb_resp = client.get(f"/api/v1/themes/{theme_id}/verbatims", params={"job_id": job_id, "limit": 100}).json()
        all_verb_ids = {v["id"] for v in verb_resp["verbatims"]}
        for sv in t["sample_verbatims"]:
            assert sv["id"] in all_verb_ids, f"Verbatim {sv['id']} from summary not found in /themes/{theme_id}/verbatims"


def test_sentiment_breakdown_counts_and_percentages(client, tmp_path):
    job_id = _upload_and_complete(client, tmp_path, 30)
    r = client.get("/api/v1/analytics/sentiment-breakdown", params={"job_id": job_id})
    assert r.status_code == 200
    body = r.json()

    sb = body["sentiment_breakdown"]
    assert sb["positive"] + sb["neutral"] + sb["negative"] == 100

    counts = body["counts"]
    total = counts["positive"] + counts["neutral"] + counts["negative"] + counts["strongly_negative"]
    assert total == body["total_reviews"] == 30


def test_trends_weekly_and_monthly_with_continuous_axis(client, tmp_path):
    # Rows spanning across weeks and months
    rows = [
        ("Review one", "2026-07-06", 5),
        ("Review two", "2026-07-10", 4),
        ("Review three", "2026-07-27", 1),  # gap between week 28 and week 31
        ("Review four", "2026-08-15", 3),
        ("Review five", "2026-09-02", 5),
    ] + [("Filler review", "2026-08-01", 3) for _ in range(10)]

    csv_path = make_csv(tmp_path / "trends_span.csv", rows)
    with csv_path.open("rb") as fh:
        j = client.post("/api/v1/reviews/upload", files={"file": ("trends_span.csv", fh, "text/csv")}).json()["job_id"]
    wait_job(client, j)

    # Weekly
    r_week = client.get("/api/v1/analytics/trends", params={"job_id": j, "interval": "weekly"})
    assert r_week.status_code == 200
    week_data = r_week.json()
    assert week_data["interval"] == "weekly"
    assert week_data["timezone"] == "UTC"
    assert len(week_data["data"]) >= 3

    # Check for empty buckets with review_count: 0 and null scores
    empty_weeks = [p for p in week_data["data"] if p["review_count"] == 0]
    assert len(empty_weeks) > 0
    for ew in empty_weeks:
        assert ew["average_sentiment_score"] is None
        assert ew["net_sentiment_score"] is None
        assert ew["low_sample"] is True

    # Monthly
    r_month = client.get("/api/v1/analytics/trends", params={"job_id": j, "interval": "monthly"})
    assert r_month.status_code == 200
    month_data = r_month.json()
    assert month_data["interval"] == "monthly"
    labels = [p["period_label"] for p in month_data["data"]]
    assert "2026-07" in labels
    assert "2026-08" in labels
    assert "2026-09" in labels


def test_trends_theme_filter(client, tmp_path):
    job_id = _upload_and_complete(client, tmp_path, 30)
    themes = client.get("/api/v1/themes", params={"job_id": job_id}).json()["themes"]
    t0_id = themes[0]["id"]

    r = client.get("/api/v1/analytics/trends", params={"job_id": job_id, "interval": "weekly", "theme_id": t0_id})
    assert r.status_code == 200
    points = r.json()["data"]
    total_reviews_in_theme = sum(p["review_count"] for p in points)
    assert total_reviews_in_theme == themes[0]["count"]


def test_themes_sorting_options(client, tmp_path):
    job_id = _upload_and_complete(client, tmp_path, 35)

    # Priority sort: priority_score desc, ties by count desc
    r_pri = client.get("/api/v1/themes", params={"job_id": job_id, "sort": "priority"})
    assert r_pri.status_code == 200
    th_pri = r_pri.json()["themes"]
    pri_scores = [t["priority_score"] for t in th_pri]
    assert pri_scores == sorted(pri_scores, reverse=True)

    # Volume sort: count desc
    r_vol = client.get("/api/v1/themes", params={"job_id": job_id, "sort": "volume"})
    assert r_vol.status_code == 200
    th_vol = r_vol.json()["themes"]
    counts = [t["count"] for t in th_vol]
    assert counts == sorted(counts, reverse=True)

    # Severity sort: most negative sentiment_score first (ascending)
    r_sev = client.get("/api/v1/themes", params={"job_id": job_id, "sort": "severity"})
    assert r_sev.status_code == 200
    th_sev = r_sev.json()["themes"]
    sent_scores = [t["sentiment_score"] for t in th_sev]
    assert sent_scores == sorted(sent_scores)


def test_themes_general_classes_filter(client, tmp_path):
    job_id = _upload_and_complete(client, tmp_path, 35)
    r = client.get("/api/v1/themes", params={"job_id": job_id})
    assert r.status_code == 200
    body = r.json()

    assert len(body["general_classes"]) >= 1
    g_name = body["general_classes"][0]["name"]

    # Filter by this general class
    r_filter = client.get("/api/v1/themes", params={"job_id": job_id, "general_class": g_name})
    assert r_filter.status_code == 200
    for t in r_filter.json()["themes"]:
        assert t["general_class"] == g_name


def test_verbatims_pagination_and_sorting(client, tmp_path):
    job_id = _upload_and_complete(client, tmp_path, 40)
    themes = client.get("/api/v1/themes", params={"job_id": job_id}).json()["themes"]
    t0_id = themes[0]["id"]
    t0_count = themes[0]["count"]

    # Page 1 with limit 2
    p1 = client.get(f"/api/v1/themes/{t0_id}/verbatims", params={"job_id": job_id, "page": 1, "limit": 2}).json()
    assert p1["page"] == 1
    assert p1["limit"] == 2
    assert p1["total"] == t0_count
    assert len(p1["verbatims"]) <= 2

    # Page beyond last returns empty list
    beyond = client.get(f"/api/v1/themes/{t0_id}/verbatims", params={"job_id": job_id, "page": 9999, "limit": 20}).json()
    assert beyond["verbatims"] == []

    # Sort most_negative
    r_neg = client.get(f"/api/v1/themes/{t0_id}/verbatims", params={"job_id": job_id, "sort": "most_negative", "limit": 10}).json()
    scores_neg = [v["sentiment_score"] for v in r_neg["verbatims"]]
    assert scores_neg == sorted(scores_neg)

    # Sort most_positive
    r_pos = client.get(f"/api/v1/themes/{t0_id}/verbatims", params={"job_id": job_id, "sort": "most_positive", "limit": 10}).json()
    scores_pos = [v["sentiment_score"] for v in r_pos["verbatims"]]
    assert scores_pos == sorted(scores_pos, reverse=True)

    # Sentiment filtering
    r_sent = client.get(f"/api/v1/themes/{t0_id}/verbatims", params={"job_id": job_id, "sentiment": "Positive", "limit": 10}).json()
    for v in r_sent["verbatims"]:
        assert v["sentiment"] == "Positive"
