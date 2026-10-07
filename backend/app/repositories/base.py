from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class JobRecord:
    id: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    file_name: str = ""
    file_size: int = 0
    file_sha256: str = ""
    sheet: Optional[str] = None
    raw_path: Optional[str] = None
    progress_percent: int = 0
    stage: Optional[str] = None
    rows_received: Optional[int] = None
    rows_analyzed: Optional[int] = None
    rows_dropped: Optional[int] = None
    dropped_reasons: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    unassigned_count: int = 0


@dataclass
class ThemeRecord:
    job_id: str
    theme_id: str
    general_class: str
    name: str
    count: int
    sentiment: str
    sentiment_score: float
    representative_indices: list[int] = field(default_factory=list)


@dataclass
class ReviewRecord:
    job_id: str
    row: int
    text: str
    sentiment_score: float
    sentiment_label: str
    theme_id: Optional[str]
    date: Optional[str]
    rating: Optional[float]


class Repository(ABC):
    @abstractmethod
    def init(self) -> None: ...

    @abstractmethod
    def create_job(self, job: JobRecord) -> None: ...

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[JobRecord]: ...

    @abstractmethod
    def list_jobs_by_status(self, status: str) -> list[JobRecord]: ...

    @abstractmethod
    def queued_count(self) -> int: ...

    @abstractmethod
    def queue_position(self, job_id: str) -> Optional[int]: ...

    @abstractmethod
    def update_job(self, job_id: str, **fields: Any) -> None: ...

    @abstractmethod
    def claim_next_queued(self, started_at: str) -> Optional[JobRecord]: ...

    @abstractmethod
    def fail_job(self, job_id: str, finished_at: str, code: str, message: str) -> None: ...

    @abstractmethod
    def complete_job(
        self,
        job: JobRecord,
        summary: dict[str, Any],
        sentiment_breakdown: dict[str, Any],
        meta: dict[str, Any],
        themes: list[ThemeRecord],
        reviews: list[ReviewRecord],
        rows_per_second: Optional[float],
    ) -> None: ...

    @abstractmethod
    def get_result(self, job_id: str) -> Optional[dict[str, Any]]: ...

    @abstractmethod
    def list_themes(self, job_id: str) -> list[ThemeRecord]: ...

    @abstractmethod
    def get_theme(self, job_id: str, theme_id: str) -> Optional[ThemeRecord]: ...

    @abstractmethod
    def count_reviews(
        self,
        job_id: str,
        theme_id: Optional[str] = None,
        sentiment: Optional[str] = None,
        unassigned: bool = False,
    ) -> int: ...

    @abstractmethod
    def list_reviews(
        self,
        job_id: str,
        *,
        theme_id: Optional[str] = None,
        sentiment: Optional[str] = None,
        sort: str = "most_negative",
        limit: int = 20,
        offset: int = 0,
        rows: Optional[list[int]] = None,
    ) -> list[ReviewRecord]: ...

    @abstractmethod
    def reviews_with_dates(self, job_id: str, theme_id: Optional[str] = None) -> list[ReviewRecord]: ...

    @abstractmethod
    def sentiment_label_counts(self, job_id: str) -> dict[str, int]: ...

    @abstractmethod
    def add_audit(self, job_id: Optional[str], timestamp: str, event: str, details: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_audit(self, job_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete_job(self, job_id: str) -> None: ...

    @abstractmethod
    def jobs_older_than(self, cutoff_iso: str) -> list[JobRecord]: ...

    @abstractmethod
    def avg_rows_per_second(self) -> Optional[float]: ...

    @abstractmethod
    def processing_jobs(self) -> list[JobRecord]: ...
