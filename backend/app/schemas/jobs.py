from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import FileInfo


class UploadAccepted(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
                "status": "QUEUED",
                "created_at": "2026-10-07T05:00:00Z",
                "file": {"name": "reviews.csv", "size_bytes": 1234567},
                "status_url": "/api/v1/jobs/3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e/status",
            }
        }
    )

    job_id: str
    status: str
    created_at: str
    file: FileInfo
    status_url: str


class JobRows(BaseModel):
    received: Optional[int] = None
    analyzed: Optional[int] = None
    dropped: Optional[int] = None


class JobError(BaseModel):
    code: str
    message: str


class JobStatus(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "3f1c8a2e-4b91-4c77-9d12-7a8e0b1c2d3e",
                "status": "PROCESSING",
                "progress_percent": 42,
                "stage": "sentiment",
                "estimated_remaining_seconds": 95,
                "queue_position": None,
                "created_at": "2026-10-07T05:00:00Z",
                "started_at": "2026-10-07T05:00:02Z",
                "finished_at": None,
                "rows": {"received": 10250, "analyzed": None, "dropped": None},
                "warnings": [],
                "error": None,
            }
        }
    )

    job_id: str
    status: str
    progress_percent: int
    stage: Optional[str] = None
    estimated_remaining_seconds: Optional[int] = None
    queue_position: Optional[int] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    rows: JobRows
    warnings: list[str] = Field(default_factory=list)
    error: Optional[JobError] = None
