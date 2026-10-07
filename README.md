# Feedback & Review Analyzer API

Production-grade REST API backend built with **Python 3.11+**, **FastAPI**, **Pydantic v2**, and **SQLite**, designed to ingest customer review files, process them through an orchestrated ML analysis engine, store scored results securely, and serve dashboard metrics to a modern web frontend.

---

## 1. Key Features

- **Decoupled Architecture:** Clean separation of concerns (Routers $\to$ Services $\to$ Repositories $\to$ SQLite).
- **Safe Worker Process Execution:** ML engine runs in a dedicated `spawn`-started worker process (FIFO execution, safe for Apple Silicon MPS GPU memory management).
- **Dual Engine Support:**
  - `mock`: Instant, deterministic, lightweight (zero PyTorch / model dependencies) for frontend development and CI.
  - `local`: In-process adapter connecting to `FeedbackAnalysisPipeline` in `feedback-analyzer/`.
- **Zero Raw PII Storage:** Raw review uploads are processed in private temporary storage, redacted in-memory, and deleted in a `finally` block immediately after job termination. Verification tests guarantee zero raw PII leaks into responses, logs, or databases.
- **Continuous Timeline Trends:** Weekly (ISO) and monthly sentiment buckets with continuous empty bucket padding for graphing without timeline gaps.
- **Lexical Verbatim Highlights:** Highlighting positive and negative valence keywords with accurate UTF-16 code unit offsets matching JavaScript string slicing.
- **Strict Error Envelope:** Uniform error contract across standard and framework exceptions: `{"error": "...", "code": "...", "details": {...}}`.

---

## 2. Setup & Installation

### 2.1 Prerequisites
- Python 3.11+ (recommended 3.11)
- `pip` and virtual environment tool

### 2.2 Create Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Running the Server

### 3.1 Running in Mock Mode (Fast, No Model Downloads)
Mock mode produces realistic sample output, stage-by-stage progress, and deterministic metrics without loading transformer weights.
```bash
cp .env.example .env
# Ensure ML_ENGINE=mock in .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Interactive API documentation will be available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 3.2 Running with Real Local ML Engine
To run the full local ML pipeline on Apple Silicon GPU (`mps`):
1. Install the ML engine dependencies (from `feedback-analyzer/requirements.txt`) into your environment.
2. Ensure models are present in `feedback-analyzer/model/`.
3. In `.env`:
   ```bash
   ML_ENGINE=local
   ML_ENGINE_PATH=./feedback-analyzer
   ```
4. Start single-worker Uvicorn:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
   ```

---

## 4. cURL Walkthrough

Follow this step-by-step walkthrough to test all core operations.

### Step 1: Health Check
Check that the server and analysis engine are online:
```bash
curl -s http://localhost:8000/api/v1/health | jq .
```
**Response (200 OK):**
```json
{
  "status": "ok",
  "engine": {
    "mode": "mock",
    "status": "ready",
    "device": "cpu"
  },
  "version": "1.0.0"
}
```

---

### Step 2: Download Sample Review CSV
Download the bundled demonstration CSV (containing ~500 synthetic reviews across 5 categories with fake PII):
```bash
curl -s -O -J http://localhost:8000/api/v1/reviews/sample
# Saved to sample_reviews.csv
```

---

### Step 3: Upload Review File
Upload the sample CSV for processing:
```bash
UPLOAD_RES=$(curl -s -X POST http://localhost:8000/api/v1/reviews/upload \
  -F "file=@sample_reviews.csv")

echo "$UPLOAD_RES" | jq .
JOB_ID=$(echo "$UPLOAD_RES" | jq -r .job_id)
```
**Response (202 Accepted):**
```json
{
  "job_id": "9f32b8ac-94d0-4221-825d-2b4777e38a5b",
  "status": "QUEUED",
  "created_at": "2026-10-07T05:00:00Z",
  "file": {
    "name": "sample_reviews.csv",
    "size_bytes": 45120
  },
  "status_url": "/api/v1/jobs/9f32b8ac-94d0-4221-825d-2b4777e38a5b/status"
}
```

---

### Step 4: Poll Job Status Until Completed
Poll status until `status == "COMPLETED"`:
```bash
curl -s "http://localhost:8000/api/v1/jobs/$JOB_ID/status" | jq .
```
**Response (200 OK):**
```json
{
  "job_id": "9f32b8ac-94d0-4221-825d-2b4777e38a5b",
  "status": "COMPLETED",
  "progress_percent": 100,
  "stage": null,
  "estimated_remaining_seconds": null,
  "queue_position": null,
  "created_at": "2026-10-07T05:00:00Z",
  "started_at": "2026-10-07T05:00:01Z",
  "finished_at": "2026-10-07T05:00:03Z",
  "rows": {
    "received": 500,
    "analyzed": 500,
    "dropped": 0
  },
  "warnings": [],
  "error": null
}
```

---

### Step 5: Dashboard Summary
Get high-level summary KPIs and top ranked themes:
```bash
curl -s "http://localhost:8000/api/v1/analytics/summary?job_id=$JOB_ID" | jq .
```
**Response (200 OK):**
```json
{
  "summary": {
    "total_reviews": 500,
    "overall_sentiment": "Negative Trend",
    "net_sentiment_score": -18,
    "pii_redacted_count": 48,
    "model_validation_accuracy": "78.0%",
    "drift_status": "Low (0.03)"
  },
  "sentiment_breakdown": {
    "positive": 25,
    "neutral": 20,
    "negative": 55
  },
  "themes": [
    {
      "id": "theme-1",
      "general_class": "Streaming/Playback",
      "name": "Pause Button Frozen During Video Playback",
      "count": 120,
      "sentiment": "Strongly Negative",
      "sentiment_score": -0.82,
      "sample_verbatims": [
        {
          "id": "v12",
          "text": "Whenever I tap pause on a stream the whole app freezes. Reach me at [EMAIL_REDACTED]",
          "sentiment": "Negative"
        }
      ]
    }
  ]
}
```

---

### Step 6: Sentiment Breakdown Details
```bash
curl -s "http://localhost:8000/api/v1/analytics/sentiment-breakdown?job_id=$JOB_ID" | jq .
```
**Response (200 OK):**
```json
{
  "job_id": "9f32b8ac-94d0-4221-825d-2b4777e38a5b",
  "sentiment_breakdown": {
    "positive": 25,
    "neutral": 20,
    "negative": 55
  },
  "counts": {
    "positive": 125,
    "neutral": 100,
    "negative": 190,
    "strongly_negative": 85
  },
  "total_reviews": 500
}
```

---

### Step 7: Themes Ranking & Filtering
Retrieve themes sorted by priority, volume, or severity:
```bash
curl -s "http://localhost:8000/api/v1/themes?job_id=$JOB_ID&sort=priority" | jq .
```
**Response (200 OK):**
```json
{
  "job_id": "9f32b8ac-94d0-4221-825d-2b4777e38a5b",
  "total_themes": 8,
  "unassigned_count": 41,
  "general_classes": [
    { "name": "Streaming/Playback", "count": 180 },
    { "name": "Billing & Subscriptions", "count": 120 }
  ],
  "themes": [
    {
      "rank": 1,
      "id": "theme-1",
      "general_class": "Streaming/Playback",
      "name": "Pause Button Frozen During Video Playback",
      "count": 120,
      "percentage": 24.0,
      "sentiment": "Strongly Negative",
      "sentiment_score": -0.82,
      "priority_score": 98.4,
      "sample_verbatims": [
        { "id": "v12", "text": "...", "sentiment": "Negative" }
      ]
    }
  ]
}
```

---

### Step 8: Paginated Verbatims & Highlights
View verbatims for `theme-1` with lexical sentiment highlights:
```bash
curl -s "http://localhost:8000/api/v1/themes/theme-1/verbatims?job_id=$JOB_ID&page=1&limit=5&sort=most_negative" | jq .
```
**Response (200 OK):**
```json
{
  "job_id": "9f32b8ac-94d0-4221-825d-2b4777e38a5b",
  "theme": {
    "id": "theme-1",
    "name": "Pause Button Frozen During Video Playback",
    "general_class": "Streaming/Playback",
    "count": 120
  },
  "page": 1,
  "limit": 5,
  "total": 120,
  "total_pages": 24,
  "verbatims": [
    {
      "id": "v12",
      "text": "App crashed right when I tapped Pay Now.",
      "sentiment": "Negative",
      "sentiment_score": -0.71,
      "date": "2026-08-14",
      "rating": 2,
      "highlights": [
        {
          "start": 4,
          "end": 11,
          "polarity": "negative",
          "term": "crashed"
        }
      ]
    }
  ]
}
```

---

### Step 9: Trends Timeline
Get weekly timeline data:
```bash
curl -s "http://localhost:8000/api/v1/analytics/trends?job_id=$JOB_ID&interval=weekly" | jq .
```
**Response (200 OK):**
```json
{
  "job_id": "9f32b8ac-94d0-4221-825d-2b4777e38a5b",
  "interval": "weekly",
  "timezone": "UTC",
  "excluded_without_date": 0,
  "data": [
    {
      "period_start": "2026-07-06",
      "period_label": "2026-W28",
      "review_count": 42,
      "average_sentiment_score": -0.21,
      "net_sentiment_score": -17.5,
      "positive": 10,
      "neutral": 12,
      "negative": 20,
      "low_sample": false
    }
  ]
}
```

---

### Step 10: Governance & Compliance Metrics
Inspect model configurations, PII audit counts, and data quality logs:
```bash
curl -s "http://localhost:8000/api/v1/governance/metrics?job_id=$JOB_ID" | jq .
```

---

### Step 11: Delete Job
Clean up job and all associated database records:
```bash
curl -i -s -X DELETE "http://localhost:8000/api/v1/jobs/$JOB_ID"
```
**Response:** `HTTP/1.1 204 No Content`

---

## 5. Running the Test Suite

The test suite runs against `MockEngine` without loading heavy transformer weights:
```bash
pytest -v
```

To run with coverage or test specific domains:
```bash
pytest tests/test_errors.py
pytest tests/test_analytics_and_themes.py
pytest tests/test_governance_and_security.py
pytest tests/test_system_and_recovery.py
```
