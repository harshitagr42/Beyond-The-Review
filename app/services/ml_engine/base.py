from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pandas as pd

ProgressCb = Callable[[str, float], None]


@dataclass
class ThemeResult:
    id: str
    general_class: str
    name: str
    count: int
    sentiment: str
    sentiment_score: float
    sample_verbatims: list[dict[str, Any]] = field(default_factory=list)
    representative_indices: list[int] = field(default_factory=list)


@dataclass
class ReviewResult:
    row: int
    text: str
    sentiment_score: float
    sentiment_label: str
    theme_id: Optional[str]
    date: Optional[str]
    rating: Optional[float]


@dataclass
class AnalysisResult:
    summary: dict[str, Any]
    sentiment_breakdown: dict[str, int]
    themes: list[ThemeResult]
    reviews: list[ReviewResult]
    meta: dict[str, Any]


class MLEngine(ABC):
    @abstractmethod
    def analyze(self, df: pd.DataFrame, progress_cb: Optional[ProgressCb] = None) -> AnalysisResult: ...

    @abstractmethod
    def info(self) -> dict[str, Any]: ...

    @abstractmethod
    def status(self) -> str: ...


class EngineContractMismatch(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "ENGINE_CONTRACT_MISMATCH"


def result_from_dict(payload: dict[str, Any]) -> AnalysisResult:
    if "reviews" not in payload:
        raise EngineContractMismatch(
            "ENGINE_CONTRACT_MISMATCH: engine output is missing reviews[]. "
            "The backend requires per-review rows; refusing to limp along."
        )
    themes = []
    for t in payload.get("themes") or []:
        themes.append(
            ThemeResult(
                id=str(t["id"]),
                general_class=str(t.get("general_class") or "Other"),
                name=str(t.get("name") or ""),
                count=int(t.get("count") or 0),
                sentiment=str(t.get("sentiment") or "Neutral"),
                sentiment_score=float(t.get("sentiment_score") or 0),
                sample_verbatims=list(t.get("sample_verbatims") or []),
                representative_indices=[int(i) for i in (t.get("representative_indices") or [])],
            )
        )
    reviews = []
    for r in payload["reviews"]:
        date_val = r.get("date")
        if date_val is not None:
            date_val = str(date_val)[:10]
        rating = r.get("rating")
        reviews.append(
            ReviewResult(
                row=int(r["row"]),
                text=str(r.get("text") or ""),
                sentiment_score=float(r.get("sentiment_score") or 0),
                sentiment_label=str(r.get("sentiment_label") or "Neutral"),
                theme_id=r.get("theme_id"),
                date=date_val,
                rating=None if rating is None or (isinstance(rating, float) and rating != rating) else float(rating),
            )
        )
    return AnalysisResult(
        summary=dict(payload.get("summary") or {}),
        sentiment_breakdown=dict(payload.get("sentiment_breakdown") or {}),
        themes=themes,
        reviews=reviews,
        meta=dict(payload.get("meta") or {}),
    )
