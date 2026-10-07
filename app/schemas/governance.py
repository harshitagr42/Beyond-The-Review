from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PiiBlock(BaseModel):
    total_redacted: int
    by_type: dict[str, int]
    tags: list[str]
    raw_text_stored: bool


class ValidationBlock(BaseModel):
    display: str
    overall_accuracy: Optional[float] = None
    sentiment_accuracy: Optional[float] = None
    tier1_topic_accuracy: Optional[float] = None
    sentiment_recall_by_class: dict[str, float] = Field(default_factory=dict)
    n: Optional[int] = None
    dataset: Optional[str] = None
    caveat: str


class DriftBlock(BaseModel):
    display: Optional[str] = None
    status: Optional[str] = None
    psi: Optional[float] = None
    centroid_cosine_distance: Optional[float] = None
    baseline_source: Optional[str] = None
    baseline_size: Optional[int] = None


class ModelsBlock(BaseModel):
    device: Optional[str] = None
    sentiment_backend: Optional[str] = None
    tier1_backend: Optional[str] = None
    tier2_backends: list[str] = Field(default_factory=list)
    embeddings: Optional[str] = None
    llm_assist: str = "off"
    external_data_egress: bool = False


class DataQualityBlock(BaseModel):
    rows_received: Optional[int] = None
    rows_analyzed: Optional[int] = None
    rows_dropped: Optional[int] = None
    dropped_reasons: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    timestamp: str
    event: str
    details: dict[str, Any] = Field(default_factory=dict)


class GovernanceMetrics(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
                "pii": {
                    "total_redacted": 1420,
                    "by_type": {
                        "email": 310,
                        "phone": 540,
                        "credit_card": 90,
                        "ssn": 120,
                        "ip_address": 100,
                        "person": 0,
                    },
                    "tags": ["[EMAIL_REDACTED]", "[PHONE_REDACTED]", "[PII_REDACTED]"],
                    "raw_text_stored": False,
                },
                "validation": {
                    "display": "78.0%",
                    "overall_accuracy": 0.78,
                    "sentiment_accuracy": 0.65,
                    "tier1_topic_accuracy": 0.91,
                    "sentiment_recall_by_class": {"Positive": 0.77, "Neutral": 0.93, "Negative": 0.35},
                    "n": 100,
                    "dataset": "embedded-100-row synthetic set",
                    "caveat": "Measured on a small synthetic set; indicative only, not real-world accuracy.",
                },
                "drift": {
                    "display": "Low (0.03)",
                    "status": "Low",
                    "psi": 0.03,
                    "centroid_cosine_distance": 0.01,
                    "baseline_source": "file:baseline_embeddings.npz",
                    "baseline_size": 10000,
                },
                "models": {
                    "device": "mps",
                    "sentiment_backend": "roberta",
                    "tier1_backend": "zero-shot",
                    "tier2_backends": ["bertopic"],
                    "embeddings": "sentence-transformers/all-MiniLM-L6-v2",
                    "llm_assist": "off",
                    "external_data_egress": False,
                },
                "data_quality": {
                    "rows_received": 10250,
                    "rows_analyzed": 10000,
                    "rows_dropped": 250,
                    "dropped_reasons": {"empty_text": 250},
                    "warnings": [],
                },
                "audit_log": [
                    {
                        "timestamp": "2026-10-07T05:00:00Z",
                        "event": "UPLOAD_RECEIVED",
                        "details": {"file_name": "reviews.csv", "size_bytes": 1234567, "sha256": "abc"},
                    }
                ],
            }
        }
    )

    job_id: str
    pii: PiiBlock
    validation: ValidationBlock
    drift: DriftBlock
    models: ModelsBlock
    data_quality: DataQualityBlock
    audit_log: list[AuditEvent]
