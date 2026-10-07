# Feedback & Review Analyzer - Frontend API Contract (v2)

This document provides a frontend-oriented specification for interacting with the Feedback & Review Analyzer REST API service.

- **Base URL:** `/api/v1`
- **Authentication:** Optional `X-API-Key` header (only when `API_KEY` is configured on the backend).
- **CORS:** Allowed for `http://localhost:3000` (configurable), exposing headers `Location`, `Content-Disposition`, and `X-Request-ID`.
- **Request Tracing:** The server accepts or generates `X-Request-ID` and returns it on all responses.

---

## 1. Core Data Models & Enums

### 1.1 Sentiment Labels (Four Values)
Across all endpoints (themes, individual verbatims, sample verbatims), sentiment labels are strictly one of:
1. `"Positive"`
2. `"Neutral"`
3. `"Negative"`
4. `"Strongly Negative"`

### 1.2 Overall Sentiment
In summary metrics, `overall_sentiment` is one of:
- `"Positive Trend"`
- `"Neutral Trend"` / `"Mixed Trend"`
- `"Negative Trend"`

### 1.3 Net Sentiment Score (NSS)
A float or integer between `-100.0` and `+100.0` representing net sentiment score calculated as `(positive - negative) / total * 100`.

### 1.4 Drift Status Variants
`drift_status` is a display string produced by the ML engine:
- `"Baseline initialized"`: Reported on the very first analysis run when no prior baseline embeddings existed.
- `"Low (0.03)"`: Normal drift level with PSI metric.
- `"Moderate (0.15)"`: Moderate distribution shift.
- `"High (0.28)"`: Significant distribution shift.
- `"Unavailable ..."`: Reported when saved baseline was produced by an incompatible embedding model.

### 1.5 PII Redaction Tags
The engine replaces sensitive entities in verbatim review text with exact tags:
- `[EMAIL_REDACTED]`
- `[PHONE_REDACTED]`
- `[PII_REDACTED]` (replaces Credit Card numbers, SSNs, IP addresses)

### 1.6 Verbatim IDs
Verbatim IDs consistently follow the format:
- `v{row}` (e.g. `v12`, `v874`), where `row` is the review's zero-based row index in the analyzed batch. Sample verbatims in `/analytics/summary` share the exact same IDs as verbatims returned by `/themes/{theme_id}/verbatims`.

---

## 2. API Endpoints

### 2.1 Health Check
`GET /api/v1/health`

Returns service and worker ML engine readiness.

**Response `200 OK`:**
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
- `engine.mode`: `"mock"` | `"local"`
- `engine.status`: `"loading"` | `"ready"` | `"failed"`
- `engine.device`: `"mps"` | `"cpu"` | `null`

---

### 2.2 Download Sample Reviews File
`GET /api/v1/reviews/sample`

Downloads a bundled synthetic CSV file (~500 reviews, spanning ~90 days, covering all 5 categories with mixed sentiment and fake PII).

**Response `200 OK`:**
- `Content-Type: text/csv`
- `Content-Disposition: attachment; filename="sample_reviews.csv"`

---

### 2.3 Upload Reviews File
`POST /api/v1/reviews/upload`

Uploads a `.csv` or `.xlsx` file for analysis. Synchronously validates file extension, file size, readability, and header mapping. Asynchronously queues the job for background execution.

**Request:** `multipart/form-data`
- `file` (required): File binary (`.csv` or `.xlsx`)
- `sheet` (optional): Sheet name if `.xlsx` (defaults to first sheet)

**Response `202 Accepted`:**
- Header `Location: /api/v1/jobs/{job_id}/status`
```json
{
  "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
  "status": "QUEUED",
  "created_at": "2026-10-07T05:00:00Z",
  "file": {
    "name": "reviews.csv",
    "size_bytes": 1234567
  },
  "status_url": "/api/v1/jobs/3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e/status"
}
```

---

### 2.4 Poll Job Status
`GET /api/v1/jobs/{job_id}/status`

Returns job execution lifecycle state, progress percent, stage, and row counts.

**Response `200 OK`:**
```json
{
  "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
  "status": "PROCESSING",
  "progress_percent": 42,
  "stage": "sentiment",
  "estimated_remaining_seconds": 95,
  "queue_position": null,
  "created_at": "2026-10-07T05:00:00Z",
  "started_at": "2026-10-07T05:00:02Z",
  "finished_at": null,
  "rows": {
    "received": 10250,
    "analyzed": null,
    "dropped": null
  },
  "warnings": [],
  "error": null
}
```
- `status`: Strictly one of `"QUEUED"`, `"PROCESSING"`, `"COMPLETED"`, `"FAILED"`.
- `progress_percent`: `0..100` (reaches `100` only on `"COMPLETED"`).
- `stage`: Current pipeline stage (`"parsing"`, `"pii_redaction"`, `"sentiment"`, `"embeddings"`, `"topics"`, `"validation"`, `"drift"`, `"persisting"`), or `null`.
- `estimated_remaining_seconds`: `null` until at least one job has completed to measure machine throughput.
- `queue_position`: 0-indexed position while `"QUEUED"`, otherwise `null`.
- `error`: `{ "code": "...", "message": "..." }` when `status == "FAILED"`, otherwise `null`.

---

### 2.5 Analytics Dashboard Summary
`GET /api/v1/analytics/summary?job_id={job_id}`

Primary overview dashboard contract. Provides high-level KPIs, sentiment breakdown percentages, and top ranked themes (up to `DASHBOARD_THEME_LIMIT`, default 10).

**Response `200 OK`:**
```json
{
  "summary": {
    "total_reviews": 10000,
    "overall_sentiment": "Negative Trend",
    "net_sentiment_score": -18,
    "pii_redacted_count": 1420,
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
      "general_class": "Billing & Subscriptions",
      "name": "Charged Twice Monthly Subscription",
      "count": 3420,
      "sentiment": "Strongly Negative",
      "sentiment_score": -0.82,
      "sample_verbatims": [
        {
          "id": "v12",
          "text": "Charged twice for my monthly sub. Support email [EMAIL_REDACTED] hasn't replied.",
          "sentiment": "Negative"
        }
      ]
    }
  ]
}
```
*Note: In `sentiment_breakdown`, percentages are integers summing to 100, where `negative` includes strongly negative.*

---

### 2.6 Detailed Sentiment Breakdown & Absolute Counts
`GET /api/v1/analytics/sentiment-breakdown?job_id={job_id}`

Provides both percentages and absolute counts separated into all sentiment categories.

**Response `200 OK`:**
```json
{
  "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
  "sentiment_breakdown": {
    "positive": 25,
    "neutral": 20,
    "negative": 55
  },
  "counts": {
    "positive": 2500,
    "neutral": 2000,
    "negative": 3800,
    "strongly_negative": 1700
  },
  "total_reviews": 10000
}
```

---

### 2.7 Sentiment Trends Timeline
`GET /api/v1/analytics/trends?job_id={job_id}&interval=weekly|monthly[&theme_id={theme_id}]`

Returns a time-series of sentiment buckets for charting. Continuous axis: intermediate time periods with 0 reviews are included with `review_count: 0` and `null` scores.

**Parameters:**
- `interval`: `"weekly"` (ISO weeks starting Monday) or `"monthly"` (calendar months)
- `theme_id` (optional): Filter timeline to a specific theme

**Response `200 OK`:**
```json
{
  "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
  "interval": "weekly",
  "timezone": "UTC",
  "excluded_without_date": 12,
  "data": [
    {
      "period_start": "2026-07-06",
      "period_label": "2026-W28",
      "review_count": 112,
      "average_sentiment_score": -0.21,
      "net_sentiment_score": -17.5,
      "positive": 24,
      "neutral": 31,
      "negative": 57,
      "low_sample": false
    },
    {
      "period_start": "2026-07-13",
      "period_label": "2026-W29",
      "review_count": 0,
      "average_sentiment_score": null,
      "net_sentiment_score": null,
      "positive": 0,
      "neutral": 0,
      "negative": 0,
      "low_sample": true
    }
  ]
}
```
- `low_sample`: `true` if `review_count < 10` (useful to render muted or dashed data points).

---

### 2.8 Theme List & Ranking
`GET /api/v1/themes?job_id={job_id}[&sort=priority|volume|severity][&general_class={class}]`

Lists all dynamically discovered themes in the job (bounded to ~25).

**Parameters:**
- `sort`: `"priority"` (default, severity-weighted volume) | `"volume"` (count desc) | `"severity"` (most negative sentiment first)
- `general_class` (optional): Filter to a specific category facet

**Response `200 OK`:**
```json
{
  "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
  "total_themes": 25,
  "unassigned_count": 143,
  "general_classes": [
    { "name": "Billing & Subscriptions", "count": 3900 },
    { "name": "Streaming/Playback", "count": 3420 }
  ],
  "themes": [
    {
      "rank": 1,
      "id": "theme-1",
      "general_class": "Billing & Subscriptions",
      "name": "Charged Twice Monthly Subscription",
      "count": 3420,
      "percentage": 34.2,
      "sentiment": "Strongly Negative",
      "sentiment_score": -0.82,
      "priority_score": 2804.4,
      "sample_verbatims": [
        { "id": "v12", "text": "...", "sentiment": "Negative" }
      ]
    }
  ]
}
```

---

### 2.9 Paginated Theme Verbatims & Highlights
`GET /api/v1/themes/{theme_id}/verbatims?job_id={job_id}&page=1&limit=20[&sentiment=...][&sort=most_negative|most_positive|recent]`

Returns individual verbatims for a specific theme with lexical sentiment highlights.

**Parameters:**
- `page`: Integer $\ge 1$ (default 1)
- `limit`: Integer $1..100$ (default 20)
- `sort`: `"most_negative"` (default) | `"most_positive"` | `"recent"`
- `sentiment`: Filter by one of the 4 sentiment labels

**Response `200 OK`:**
```json
{
  "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
  "theme": {
    "id": "theme-1",
    "name": "Charged Twice Monthly Subscription",
    "general_class": "Billing & Subscriptions",
    "count": 3420
  },
  "page": 1,
  "limit": 20,
  "total": 3420,
  "total_pages": 171,
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
*Highlight offsets:* `start` and `end` indices are in **UTF-16 code units**, so the frontend can slice JavaScript strings directly: `verbatim.text.slice(h.start, h.end)`.

---

### 2.10 Governance, Audit & Quality Metrics
`GET /api/v1/governance/metrics?job_id={job_id}`

Returns compliance data, redaction stats, model details, and the immutable job audit log.

**Response `200 OK`:**
```json
{
  "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
  "pii": {
    "total_redacted": 1420,
    "by_type": {
      "email": 310,
      "phone": 540,
      "credit_card": 90,
      "ssn": 120,
      "ip_address": 100,
      "person": 0
    },
    "tags": ["[EMAIL_REDACTED]", "[PHONE_REDACTED]", "[PII_REDACTED]"],
    "raw_text_stored": false
  },
  "validation": {
    "display": "78.0%",
    "overall_accuracy": 0.78,
    "sentiment_accuracy": 0.65,
    "tier1_topic_accuracy": 0.91,
    "sentiment_recall_by_class": {
      "Positive": 0.77,
      "Neutral": 0.93,
      "Negative": 0.35
    },
    "n": 100,
    "dataset": "embedded-100-row synthetic set",
    "caveat": "Measured on a small synthetic set; indicative only, not real-world accuracy."
  },
  "drift": {
    "display": "Low (0.03)",
    "status": "Low",
    "psi": 0.03,
    "centroid_cosine_distance": 0.01,
    "baseline_source": "file:baseline_embeddings.npz",
    "baseline_size": 10000
  },
  "models": {
    "device": "mps",
    "sentiment_backend": "roberta",
    "tier1_backend": "zero-shot",
    "tier2_backends": ["bertopic"],
    "embeddings": "sentence-transformers/all-MiniLM-L6-v2",
    "llm_assist": "off",
    "external_data_egress": false
  },
  "data_quality": {
    "rows_received": 10250,
    "rows_analyzed": 10000,
    "rows_dropped": 250,
    "dropped_reasons": {
      "empty_text": 250
    },
    "warnings": []
  },
  "audit_log": [
    {
      "timestamp": "2026-10-07T05:00:00Z",
      "event": "UPLOAD_RECEIVED",
      "details": { "file_name": "reviews.csv", "size_bytes": 1234567, "sha256": "..." }
    },
    { "timestamp": "2026-10-07T05:00:02Z", "event": "JOB_STARTED", "details": {} },
    { "timestamp": "2026-10-07T05:01:57Z", "event": "PII_REDACTION_COMPLETED", "details": { "pii_redacted": 1420 } },
    { "timestamp": "2026-10-07T05:01:57Z", "event": "JOB_COMPLETED", "details": { "seconds_total": 115.2, "pii_redacted": 1420 } },
    { "timestamp": "2026-10-07T05:01:57Z", "event": "RAW_FILE_DELETED", "details": {} }
  ]
}
```

---

### 2.11 Delete Job
`DELETE /api/v1/jobs/{job_id}`

Deletes a completed or failed job and all its stored records and raw file.

**Response `204 No Content`**
- If the job is currently processing: Returns `409 Conflict` (`JOB_ACTIVE`).

---

## 3. Standard Error Envelope

Every error returned by the API follows the exact shape:
```json
{
  "error": "Human-readable description sentence.",
  "code": "MACHINE_ERROR_CODE",
  "details": {}
}
```

### HTTP Error Codes Reference

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_FILE_FORMAT` | Unsupported extension or invalid file header |
| 400 | `EMPTY_FILE` | 0-byte file or no readable rows |
| 400 | `UNREADABLE_FILE` | Undecodable bytes or corrupt spreadsheet |
| 401 | `UNAUTHORIZED` | Missing or invalid `X-API-Key` |
| 404 | `JOB_NOT_FOUND` | Unknown job UUID |
| 404 | `THEME_NOT_FOUND` | Unknown theme ID for this job |
| 404 | `NOT_FOUND` | Unmapped endpoint route |
| 409 | `JOB_NOT_READY` | Requested results while job is `QUEUED` or `PROCESSING` |
| 409 | `JOB_FAILED` | Requested results on a `FAILED` job |
| 409 | `JOB_ACTIVE` | Attempted to delete a `PROCESSING` job |
| 413 | `FILE_TOO_LARGE` | Exceeded `MAX_FILE_SIZE` |
| 422 | `MISSING_COLUMN` | Missing required column (`review_text` or `date`) |
| 422 | `NO_DATE_DATA` | No usable date values found for timeline trends |
| 422 | `VALIDATION_ERROR` | Out of range query/body parameters |
| 429 | `QUEUE_FULL` | Job queue capacity reached |
| 500 | `INTERNAL_ERROR` | Unexpected server failure (no internal paths/traces leaked) |
| 503 | `ENGINE_UNAVAILABLE` | ML engine failed to initialize |
