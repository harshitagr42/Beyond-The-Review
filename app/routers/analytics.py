from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_analytics
from app.schemas.analytics import AnalyticsSummary, SentimentBreakdownResponse, TrendsResponse
from app.schemas.common import ErrorBody
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

JOB_ERRORS = {
    401: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
}


@router.get("/summary", response_model=AnalyticsSummary, responses=JOB_ERRORS)
def analytics_summary(
    job_id: str = Query(..., description="Job UUID"),
    analytics: AnalyticsService = Depends(get_analytics),
) -> AnalyticsSummary:
    return analytics.summary(job_id)


@router.get("/sentiment-breakdown", response_model=SentimentBreakdownResponse, responses=JOB_ERRORS)
def sentiment_breakdown(
    job_id: str = Query(...),
    analytics: AnalyticsService = Depends(get_analytics),
) -> SentimentBreakdownResponse:
    return analytics.sentiment_breakdown(job_id)


@router.get("/trends", response_model=TrendsResponse, responses=JOB_ERRORS)
def trends(
    job_id: str = Query(...),
    interval: str = Query(..., description="weekly or monthly"),
    theme_id: Optional[str] = Query(None),
    analytics: AnalyticsService = Depends(get_analytics),
) -> TrendsResponse:
    return analytics.trends(job_id, interval, theme_id)
