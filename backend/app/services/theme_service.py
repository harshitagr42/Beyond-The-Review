from __future__ import annotations

import math
from typing import Optional

from app.config import Settings
from app.repositories.base import Repository, ReviewRecord, ThemeRecord
from app.schemas.common import VerbatimSample
from app.schemas.themes import (
    GeneralClassFacet,
    ThemeListItem,
    ThemesResponse,
    ThemeSummary,
    VerbatimItem,
    VerbatimsResponse,
)
from app.services.job_service import JobService
from app.utils.errors import AppError
from app.utils.highlighting import highlight_text
from app.utils.output_guard import guard_text

SENTIMENT_LABELS = {"Positive", "Neutral", "Negative", "Strongly Negative"}
SORTS = {"priority", "volume", "severity"}
VERBATIM_SORTS = {"most_negative", "most_positive", "recent"}


def priority_score(count: int, sentiment_score: float) -> float:
    return round(count * max(0.0, -float(sentiment_score)), 4)


def sample_verbatims(
    repo: Repository,
    job_id: str,
    theme: ThemeRecord,
    engine_path: Optional[str],
    limit: int = 5,
) -> list[VerbatimSample]:
    reviews: list[ReviewRecord] = []
    if theme.representative_indices:
        reviews = repo.list_reviews(
            job_id, theme_id=theme.theme_id, rows=theme.representative_indices, limit=max(limit, len(theme.representative_indices)), offset=0
        )
        by_row = {r.row: r for r in reviews}
        ordered = [by_row[i] for i in theme.representative_indices if i in by_row]
        reviews = ordered[:limit]
    if not reviews:
        reviews = repo.list_reviews(job_id, theme_id=theme.theme_id, sort="most_negative", limit=limit, offset=0)
    out = []
    for r in reviews[:limit]:
        text = guard_text(r.text, engine_path)
        out.append(VerbatimSample(id=f"v{r.row}", text=text, sentiment=r.sentiment_label))
    return out


class ThemeService:
    def __init__(self, repo: Repository, jobs: JobService, settings: Settings) -> None:
        self.repo = repo
        self.jobs = jobs
        self.settings = settings

    def _engine_path(self) -> Optional[str]:
        p = self.settings.ml_engine_path
        return str(p) if p.exists() else None

    def list_themes(self, job_id: str, sort: str = "priority", general_class: Optional[str] = None) -> ThemesResponse:
        job_id = self.jobs.require_job_id(job_id)
        job = self.jobs.require_completed(job_id)
        if sort not in SORTS:
            raise AppError(422, "VALIDATION_ERROR", "sort must be priority, volume, or severity.")
        themes = self.repo.list_themes(job_id)
        total_reviews = job.rows_analyzed or 0
        items: list[ThemeListItem] = []
        class_counts: dict[str, int] = {}
        for t in themes:
            class_counts[t.general_class] = class_counts.get(t.general_class, 0) + t.count
            if general_class and t.general_class != general_class:
                continue
            pct = round((t.count / total_reviews) * 100.0, 1) if total_reviews else 0.0
            items.append(
                ThemeListItem(
                    rank=0,
                    id=t.theme_id,
                    general_class=t.general_class,
                    name=t.name,
                    count=t.count,
                    percentage=pct,
                    sentiment=t.sentiment,
                    sentiment_score=t.sentiment_score,
                    priority_score=priority_score(t.count, t.sentiment_score),
                    sample_verbatims=sample_verbatims(self.repo, job_id, t, self._engine_path()),
                )
            )
        if sort == "volume":
            items.sort(key=lambda x: (-x.count, x.id))
        elif sort == "severity":
            items.sort(key=lambda x: (x.sentiment_score, -x.count, x.id))
        else:
            items.sort(key=lambda x: (-x.priority_score, -x.count, x.id))
        for i, item in enumerate(items, start=1):
            item.rank = i
        facets = [
            GeneralClassFacet(name=k, count=v)
            for k, v in sorted(class_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        return ThemesResponse(
            job_id=job_id,
            total_themes=len(themes),
            unassigned_count=job.unassigned_count,
            general_classes=facets,
            themes=items,
        )

    def verbatims(
        self,
        theme_id: str,
        job_id: str,
        page: int = 1,
        limit: int = 20,
        sentiment: Optional[str] = None,
        sort: str = "most_negative",
    ) -> VerbatimsResponse:
        job_id = self.jobs.require_job_id(job_id)
        self.jobs.require_completed(job_id)
        if page < 1 or limit < 1 or limit > 100:
            raise AppError(422, "VALIDATION_ERROR", "page must be >= 1 and limit must be between 1 and 100.")
        if sort not in VERBATIM_SORTS:
            raise AppError(422, "VALIDATION_ERROR", "sort must be most_negative, most_positive, or recent.")
        if sentiment and sentiment not in SENTIMENT_LABELS:
            raise AppError(422, "VALIDATION_ERROR", "sentiment must be one of the four sentiment labels.")
        theme = self.repo.get_theme(job_id, theme_id)
        if theme is None:
            raise AppError(404, "THEME_NOT_FOUND", "Theme not found for this job.")
        total = self.repo.count_reviews(job_id, theme_id=theme_id, sentiment=sentiment)
        total_pages = max(1, math.ceil(total / limit)) if total else 1
        offset = (page - 1) * limit
        rows = self.repo.list_reviews(
            job_id, theme_id=theme_id, sentiment=sentiment, sort=sort, limit=limit, offset=offset
        )
        engine_path = self._engine_path()
        items = []
        for r in rows:
            text = guard_text(r.text, engine_path)
            items.append(
                VerbatimItem(
                    id=f"v{r.row}",
                    text=text,
                    sentiment=r.sentiment_label,
                    sentiment_score=r.sentiment_score,
                    date=r.date,
                    rating=r.rating,
                    highlights=highlight_text(text),
                )
            )
        return VerbatimsResponse(
            job_id=job_id,
            theme=ThemeSummary(id=theme.theme_id, name=theme.name, general_class=theme.general_class, count=theme.count),
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
            verbatims=items,
        )
