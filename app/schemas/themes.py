from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import VerbatimSample


class GeneralClassFacet(BaseModel):
    name: str
    count: int


class ThemeListItem(BaseModel):
    rank: int
    id: str
    general_class: str
    name: str
    count: int
    percentage: float
    sentiment: str
    sentiment_score: float
    priority_score: float
    sample_verbatims: list[VerbatimSample] = Field(default_factory=list)


class ThemesResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
                "total_themes": 25,
                "unassigned_count": 143,
                "general_classes": [{"name": "Billing & Subscriptions", "count": 3900}],
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
                            {
                                "id": "v12",
                                "text": "Charged twice for my monthly sub.",
                                "sentiment": "Negative",
                            }
                        ],
                    }
                ],
            }
        }
    )

    job_id: str
    total_themes: int
    unassigned_count: int
    general_classes: list[GeneralClassFacet]
    themes: list[ThemeListItem]


class ThemeSummary(BaseModel):
    id: str
    name: str
    general_class: str
    count: int


class HighlightSpan(BaseModel):
    start: int
    end: int
    polarity: str
    term: str


class VerbatimItem(BaseModel):
    id: str
    text: str
    sentiment: str
    sentiment_score: float
    date: Optional[str] = None
    rating: Optional[float] = None
    highlights: list[HighlightSpan] = Field(default_factory=list)


class VerbatimsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
                "theme": {
                    "id": "theme-1",
                    "name": "Charged Twice Monthly Subscription",
                    "general_class": "Billing & Subscriptions",
                    "count": 3420,
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
                        "highlights": [{"start": 4, "end": 11, "polarity": "negative", "term": "crashed"}],
                    }
                ],
            }
        }
    )

    job_id: str
    theme: ThemeSummary
    page: int
    limit: int
    total: int
    total_pages: int
    verbatims: list[VerbatimItem]
