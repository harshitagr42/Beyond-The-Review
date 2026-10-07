from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.config import Settings
from app.repositories.base import Repository
from app.schemas.analytics import (
    AnalyticsSummary,
    DashboardTheme,
    SentimentBreakdown,
    SentimentBreakdownResponse,
    SentimentCounts,
    SummaryBlock,
    TrendPoint,
    TrendsResponse,
)
from app.services.job_service import JobService
from app.services.theme_service import sample_verbatims
from app.utils.errors import AppError
from app.utils.time_buckets import bucket_key, iter_empty_range, parse_date, period_label


class AnalyticsService:
    def __init__(self, repo: Repository, jobs: JobService, settings: Settings) -> None:
        self.repo = repo
        self.jobs = jobs
        self.settings = settings

    def _engine_path(self) -> Optional[str]:
        p = self.settings.ml_engine_path
        return str(p) if p.exists() else None

    def summary(self, job_id: str) -> AnalyticsSummary:
        job_id = self.jobs.require_job_id(job_id)
        job = self.jobs.require_completed(job_id)
        result = self.repo.get_result(job_id)
        if result is None:
            raise AppError(404, "JOB_NOT_FOUND", "Job results were not found.")
        themes = self.repo.list_themes(job_id)
        ranked = sorted(
            themes,
            key=lambda t: (-(t.count * max(0.0, -t.sentiment_score)), -t.count, t.theme_id),
        )
        limit = self.settings.dashboard_theme_limit
        dash = []
        for t in ranked[:limit]:
            dash.append(
                DashboardTheme(
                    id=t.theme_id,
                    general_class=t.general_class,
                    name=t.name,
                    count=t.count,
                    sentiment=t.sentiment,
                    sentiment_score=t.sentiment_score,
                    sample_verbatims=sample_verbatims(self.repo, job.id, t, self._engine_path(), limit=5),
                )
            )
        s = result["summary"]
        b = result["sentiment_breakdown"]
        return AnalyticsSummary(
            summary=SummaryBlock(
                total_reviews=s["total_reviews"],
                overall_sentiment=s["overall_sentiment"],
                net_sentiment_score=s["net_sentiment_score"],
                pii_redacted_count=s["pii_redacted_count"],
                model_validation_accuracy=s["model_validation_accuracy"],
                drift_status=s["drift_status"],
            ),
            sentiment_breakdown=SentimentBreakdown(
                positive=int(b.get("positive", 0)),
                neutral=int(b.get("neutral", 0)),
                negative=int(b.get("negative", 0)),
            ),
            themes=dash,
        )

    def sentiment_breakdown(self, job_id: str) -> SentimentBreakdownResponse:
        job_id = self.jobs.require_job_id(job_id)
        job = self.jobs.require_completed(job_id)
        result = self.repo.get_result(job_id)
        if result is None:
            raise AppError(404, "JOB_NOT_FOUND", "Job results were not found.")
        b = result["sentiment_breakdown"]
        counts = self.repo.sentiment_label_counts(job_id)
        pos = counts.get("Positive", 0)
        neu = counts.get("Neutral", 0)
        neg = counts.get("Negative", 0)
        sneg = counts.get("Strongly Negative", 0)
        return SentimentBreakdownResponse(
            job_id=job_id,
            sentiment_breakdown=SentimentBreakdown(
                positive=int(b.get("positive", 0)),
                neutral=int(b.get("neutral", 0)),
                negative=int(b.get("negative", 0)),
            ),
            counts=SentimentCounts(positive=pos, neutral=neu, negative=neg, strongly_negative=sneg),
            total_reviews=job.rows_analyzed or result["summary"].get("total_reviews") or 0,
        )

    def trends(self, job_id: str, interval: str, theme_id: Optional[str] = None) -> TrendsResponse:
        job_id = self.jobs.require_job_id(job_id)
        self.jobs.require_completed(job_id)
        if interval not in {"weekly", "monthly"}:
            raise AppError(422, "VALIDATION_ERROR", "interval must be weekly or monthly.")
        if theme_id:
            if self.repo.get_theme(job_id, theme_id) is None:
                raise AppError(404, "THEME_NOT_FOUND", "Theme not found for this job.")
        rows = self.repo.reviews_with_dates(job_id, theme_id=theme_id)
        dated = []
        excluded = 0
        for r in rows:
            d = parse_date(r.date)
            if d is None:
                excluded += 1
            else:
                dated.append((d, r))
        if not dated:
            raise AppError(422, "NO_DATE_DATA", "No usable date values were found for this job.")

        buckets: dict = defaultdict(lambda: {"pos": 0, "neu": 0, "neg": 0, "scores": []})
        for d, r in dated:
            key = bucket_key(d, interval)
            b = buckets[key]
            if r.sentiment_label == "Positive":
                b["pos"] += 1
            elif r.sentiment_label == "Neutral":
                b["neu"] += 1
            else:
                b["neg"] += 1
            b["scores"].append(r.sentiment_score)

        first = min(buckets)
        last = max(buckets)
        points: list[TrendPoint] = []
        for start in iter_empty_range(first, last, interval):
            b = buckets.get(start)
            if not b or not b["scores"]:
                points.append(
                    TrendPoint(
                        period_start=start.isoformat(),
                        period_label=period_label(start, interval),
                        review_count=0,
                        average_sentiment_score=None,
                        net_sentiment_score=None,
                        positive=0,
                        neutral=0,
                        negative=0,
                        low_sample=True,
                    )
                )
                continue
            n = b["pos"] + b["neu"] + b["neg"]
            avg = round(sum(b["scores"]) / n, 2) if n else None
            nss = round((b["pos"] - b["neg"]) / n * 100, 1) if n else None
            points.append(
                TrendPoint(
                    period_start=start.isoformat(),
                    period_label=period_label(start, interval),
                    review_count=n,
                    average_sentiment_score=avg,
                    net_sentiment_score=nss,
                    positive=b["pos"],
                    neutral=b["neu"],
                    negative=b["neg"],
                    low_sample=n < self.settings.trend_low_sample,
                )
            )
        return TrendsResponse(
            job_id=job_id,
            interval=interval,
            timezone="UTC",
            excluded_without_date=excluded,
            data=points,
        )
