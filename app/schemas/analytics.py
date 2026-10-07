from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import VerbatimSample


class SummaryBlock(BaseModel):
    total_reviews: int
    overall_sentiment: str
    net_sentiment_score: float
    pii_redacted_count: int
    model_validation_accuracy: str
    drift_status: str


class SentimentBreakdown(BaseModel):
    positive: int
    neutral: int
    negative: int


class DashboardTheme(BaseModel):
    id: str
    general_class: str
    name: str
    count: int
    sentiment: str
    sentiment_score: float
    sample_verbatims: list[VerbatimSample] = Field(default_factory=list)


class AnalyticsSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "summary": {
                    "total_reviews": 10000,
                    "overall_sentiment": "Negative Trend",
                    "net_sentiment_score": -18,
                    "pii_redacted_count": 1420,
                    "model_validation_accuracy": "78.0%",
                    "drift_status": "Low (0.03)",
                },
                "sentiment_breakdown": {"positive": 25, "neutral": 20, "negative": 55},
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
                                "sentiment": "Negative",
                            }
                        ],
                    }
                ],
            }
        },
    )

    summary: SummaryBlock
    sentiment_breakdown: SentimentBreakdown
    themes: list[DashboardTheme]


class SentimentCounts(BaseModel):
    positive: int
    neutral: int
    negative: int
    strongly_negative: int


class SentimentBreakdownResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
                "sentiment_breakdown": {"positive": 25, "neutral": 20, "negative": 55},
                "counts": {"positive": 2500, "neutral": 2000, "negative": 3800, "strongly_negative": 1700},
                "total_reviews": 10000,
            }
        }
    )

    job_id: str
    sentiment_breakdown: SentimentBreakdown
    counts: SentimentCounts
    total_reviews: int


class TrendPoint(BaseModel):
    period_start: str
    period_label: str
    review_count: int
    average_sentiment_score: Optional[float] = None
    net_sentiment_score: Optional[float] = None
    positive: int
    neutral: int
    negative: int
    low_sample: bool


class TrendsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
                        "low_sample": False,
                    }
                ],
            }
        }
    )

    job_id: str
    interval: str
    timezone: str = "UTC"
    excluded_without_date: int
    data: list[TrendPoint]
