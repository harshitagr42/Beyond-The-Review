from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.config import Settings
from app.repositories.base import JobRecord, Repository
from app.schemas.jobs import JobError, JobRows, JobStatus, UploadAccepted
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event

log = get_logger("app.jobs")


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class JobService:
    def __init__(self, repo: Repository, settings: Settings, worker=None) -> None:
        self.repo = repo
        self.settings = settings
        self.worker = worker

    def create_from_upload(
        self,
        *,
        filename: str,
        size_bytes: int,
        sha256: str,
        raw_path: Path,
        sheet: Optional[str],
    ) -> UploadAccepted:
        engine = self.worker.engine_status() if self.worker else {"status": "ready"}
        if engine.get("status") == "failed":
            raw_path.unlink(missing_ok=True)
            raise AppError(503, "ENGINE_UNAVAILABLE", "The analysis engine is unavailable.")
        if self.repo.queued_count() >= self.settings.queue_max_size:
            raw_path.unlink(missing_ok=True)
            raise AppError(429, "QUEUE_FULL", "The analysis queue is full. Try again later.")

        job_id = str(uuid.uuid4())
        created = utcnow()
        job = JobRecord(
            id=job_id,
            status="QUEUED",
            created_at=created,
            file_name=filename,
            file_size=size_bytes,
            file_sha256=sha256,
            sheet=sheet,
            raw_path=str(raw_path),
            progress_percent=0,
            stage=None,
        )
        self.repo.create_job(job)
        self.repo.add_audit(
            job_id,
            created,
            "UPLOAD_RECEIVED",
            {"file_name": filename, "size_bytes": size_bytes, "sha256": sha256},
        )
        log_event(log, "job_queued", job_id=job_id, size_bytes=size_bytes)
        if self.worker:
            self.worker.notify()
        return UploadAccepted(
            job_id=job_id,
            status="QUEUED",
            created_at=created,
            file={"name": filename, "size_bytes": size_bytes},
            status_url=f"/api/v1/jobs/{job_id}/status",
        )

    def recover_on_startup(self) -> None:
        now = utcnow()
        for job in self.repo.processing_jobs():
            self.repo.fail_job(job.id, now, "INTERRUPTED", "The job was interrupted by a server restart.")
            self.repo.add_audit(job.id, now, "JOB_FAILED", {"code": "INTERRUPTED"})
            if job.raw_path and not self.settings.keep_raw_uploads:
                Path(job.raw_path).unlink(missing_ok=True)
                self.repo.add_audit(job.id, now, "RAW_FILE_DELETED", {})
                self.repo.update_job(job.id, raw_path=None)
        for job in self.repo.list_jobs_by_status("QUEUED"):
            if job.raw_path and Path(job.raw_path).exists():
                continue
            self.repo.fail_job(job.id, now, "INTERRUPTED", "The uploaded file is no longer available.")
            self.repo.add_audit(job.id, now, "JOB_FAILED", {"code": "INTERRUPTED"})

    def require_job_id(self, job_id: Optional[str]) -> str:
        if job_id is None or not str(job_id).strip():
            raise AppError(422, "VALIDATION_ERROR", "A valid job_id query parameter is required.")
        try:
            uuid.UUID(str(job_id))
        except ValueError as exc:
            raise AppError(422, "VALIDATION_ERROR", "job_id must be a UUID.") from exc
        return str(job_id)

    def get_job(self, job_id: str) -> JobRecord:
        job = self.repo.get_job(job_id)
        if job is None:
            raise AppError(404, "JOB_NOT_FOUND", "Job not found.")
        return job

    def require_completed(self, job_id: str) -> JobRecord:
        job = self.get_job(job_id)
        if job.status in {"QUEUED", "PROCESSING"}:
            raise AppError(
                409,
                "JOB_NOT_READY",
                "The job has not finished processing.",
                {"status": job.status, "progress_percent": job.progress_percent},
            )
        if job.status == "FAILED":
            raise AppError(
                409,
                "JOB_FAILED",
                "The job failed.",
                {"code": job.error_code, "message": job.error_message},
            )
        return job

    def status(self, job_id: str) -> JobStatus:
        job = self.get_job(job_id)
        queue_position = self.repo.queue_position(job_id) if job.status == "QUEUED" else None
        eta = None
        rps = self.repo.avg_rows_per_second()
        if rps and job.status == "PROCESSING":
            remaining_frac = max(0.0, 1.0 - (job.progress_percent or 0) / 100.0)
            rows = job.rows_received or 0
            if rows:
                eta = int(round((rows * remaining_frac) / rps))
        elif rps and job.status == "QUEUED":
            ahead = self.repo.queue_position(job_id) or 0
            eta = None  # still need a completed job; we have rps so could estimate queue wait — spec: null until one completed, then compute from throughput
            # For queued jobs, estimate remaining as current processing + this job if we know rows later.
            # Spec: computed from measured throughput of previously completed jobs. Return null until at least one completed.
            # If we have rps, we can return an estimate. For QUEUED without row count, still null-ish.
            if job.rows_received:
                eta = int(round(job.rows_received / rps))
        error = None
        if job.status == "FAILED" and job.error_code:
            error = JobError(code=job.error_code, message=job.error_message or "The job failed.")
        progress = job.progress_percent
        if job.status == "COMPLETED":
            progress = 100
        elif job.status == "QUEUED":
            progress = 0
        elif job.status == "FAILED":
            progress = job.progress_percent or 0
        return JobStatus(
            job_id=job.id,
            status=job.status,
            progress_percent=progress,
            stage=job.stage,
            estimated_remaining_seconds=eta,
            queue_position=queue_position,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            rows=JobRows(received=job.rows_received, analyzed=job.rows_analyzed, dropped=job.rows_dropped),
            warnings=list(job.warnings or []),
            error=error,
        )

    def delete(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job.status == "PROCESSING":
            raise AppError(409, "JOB_ACTIVE", "A job that is currently processing cannot be deleted.")
        if job.raw_path:
            Path(job.raw_path).unlink(missing_ok=True)
        self.repo.delete_job(job_id)
        self.repo.add_audit(job_id, utcnow(), "JOB_DELETED", {})
        log_event(log, "job_deleted", job_id=job_id)

    def expire_old_jobs(self) -> int:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=self.settings.job_retention_days)
        cutoff = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        n = 0
        for job in self.repo.jobs_older_than(cutoff):
            if job.status == "PROCESSING":
                continue
            if job.raw_path:
                Path(job.raw_path).unlink(missing_ok=True)
            self.repo.delete_job(job.id)
            self.repo.add_audit(job.id, utcnow(), "JOB_DELETED", {"reason": "retention"})
            n += 1
        return n

    def fail_timed_out(self) -> list[str]:
        now = datetime.now(timezone.utc)
        timed_out = []
        for job in self.repo.processing_jobs():
            if not job.started_at:
                continue
            started = parse_iso(job.started_at)
            if (now - started).total_seconds() > self.settings.job_timeout_seconds:
                self.repo.fail_job(job.id, utcnow(), "TIMEOUT", "The job exceeded the time limit.")
                self.repo.add_audit(job.id, utcnow(), "JOB_FAILED", {"code": "TIMEOUT"})
                if job.raw_path and not self.settings.keep_raw_uploads:
                    Path(job.raw_path).unlink(missing_ok=True)
                    self.repo.add_audit(job.id, utcnow(), "RAW_FILE_DELETED", {})
                timed_out.append(job.id)
        return timed_out
