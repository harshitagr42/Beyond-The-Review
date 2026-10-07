from __future__ import annotations

import multiprocessing as mp
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import Settings
from app.repositories.base import JobRecord, ReviewRecord, ThemeRecord
from app.repositories.sqlite import SqliteRepository
from app.services.ml_engine.base import EngineContractMismatch, MLEngine
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event, setup_logging
from app.utils.output_guard import guard_text
from app.utils.progress import overall_percent, time_based_percent

log = get_logger("app.worker")


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_engine(settings: Settings) -> MLEngine:
    if settings.ml_engine == "local":
        from app.services.ml_engine.local_engine import LocalEngine

        return LocalEngine(settings.ml_engine_path)
    from app.services.ml_engine.mock_engine import MockEngine

    return MockEngine(sleep_s=settings.mock_progress_sleep)


class JobFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _delete_raw(path: Optional[str], keep: bool) -> None:
    if keep or not path:
        return
    p = Path(path)
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


def process_job(job: JobRecord, settings: Settings, repo: SqliteRepository, engine: MLEngine) -> None:
    from app.services.ingestion_service import clean_dataframe, parse_upload

    raw_deleted = False
    try:
        log_event(log, "job_started", job_id=job.id)
        repo.add_audit(job.id, utcnow(), "JOB_STARTED", {})
        kind_path = Path(job.raw_path or "")
        if not job.raw_path or not kind_path.exists():
            raise JobFailed("INTERRUPTED", "The uploaded file is no longer available.")

        df, received, mapping = parse_upload(kind_path, job.file_name, job.sheet, settings)
        repo.update_job(job.id, rows_received=received, stage="parsing", progress_percent=5)

        cleaned, dropped_empty, warnings = clean_dataframe(df, mapping, settings)
        dropped = dropped_empty
        analyzable = len(cleaned)
        if analyzable == 0:
            raise JobFailed("NO_VALID_REVIEWS", "No valid reviews remained after cleaning.")
        if analyzable < settings.min_rows:
            raise JobFailed("TOO_FEW_ROWS", f"At least {settings.min_rows} reviews are required.")
        if analyzable > settings.max_rows:
            raise JobFailed("TOO_MANY_ROWS", f"At most {settings.max_rows} reviews are allowed.")

        repo.update_job(
            job.id,
            rows_received=received,
            rows_dropped=dropped,
            dropped_reasons={"empty_text": dropped_empty},
            warnings=warnings,
        )

        weights = settings.stage_weights
        rps = repo.avg_rows_per_second()
        started = time.monotonic()
        saw_progress = {"v": False}

        def progress_cb(stage: str, fraction: float) -> None:
            saw_progress["v"] = True
            pct = overall_percent(weights, stage, fraction)
            repo.update_job(job.id, stage=stage, progress_percent=pct)

        try:
            result = engine.analyze(cleaned, progress_cb=progress_cb)
        except EngineContractMismatch as exc:
            raise JobFailed("ENGINE_CONTRACT_MISMATCH", str(exc)) from exc
        except Exception as exc:
            raise JobFailed("ENGINE_ERROR", "The analysis engine failed.") from exc

        if not saw_progress["v"]:
            elapsed = time.monotonic() - started
            expected = (analyzable / rps) if rps else None
            repo.update_job(
                job.id,
                stage="topics",
                progress_percent=time_based_percent(elapsed, expected),
            )

        repo.update_job(job.id, stage="persisting", progress_percent=overall_percent(weights, "persisting", 0.2))
        repo.add_audit(job.id, utcnow(), "PII_REDACTION_COMPLETED", {"pii_redacted": result.summary.get("pii_redacted_count")})

        engine_path = str(settings.ml_engine_path) if settings.ml_engine == "local" else (
            str(settings.ml_engine_path) if Path(settings.ml_engine_path).exists() else None
        )
        guard_hits = {"n": 0}

        def on_hit() -> None:
            guard_hits["n"] += 1

        reviews: list[ReviewRecord] = []
        for r in result.reviews:
            text = guard_text(r.text, engine_path, on_hit)
            reviews.append(
                ReviewRecord(
                    job_id=job.id,
                    row=r.row,
                    text=text,
                    sentiment_score=r.sentiment_score,
                    sentiment_label=r.sentiment_label,
                    theme_id=r.theme_id,
                    date=r.date,
                    rating=r.rating,
                )
            )
        if guard_hits["n"]:
            repo.add_audit(job.id, utcnow(), "OUTPUT_GUARD_HIT", {"count": guard_hits["n"]})

        unassigned = sum(1 for r in reviews if not r.theme_id)
        themes = [
            ThemeRecord(
                job_id=job.id,
                theme_id=t.id,
                general_class=t.general_class,
                name=t.name,
                count=t.count,
                sentiment=t.sentiment,
                sentiment_score=t.sentiment_score,
                representative_indices=list(t.representative_indices),
            )
            for t in result.themes
        ]

        warnings = list(warnings) + list(result.meta.get("warnings") or [])
        seconds = (result.meta.get("seconds") or {}).get("total") or (time.monotonic() - started)
        rps_val = (analyzable / float(seconds)) if seconds else None
        finished = utcnow()
        job.finished_at = finished
        job.rows_received = received
        job.rows_analyzed = analyzable
        job.rows_dropped = dropped
        job.dropped_reasons = {"empty_text": dropped_empty}
        job.warnings = warnings
        job.unassigned_count = unassigned

        repo.complete_job(
            job,
            result.summary,
            result.sentiment_breakdown,
            result.meta,
            themes,
            reviews,
            rps_val,
        )
        repo.add_audit(
            job.id,
            finished,
            "JOB_COMPLETED",
            {"seconds_total": seconds, "pii_redacted": result.summary.get("pii_redacted_count")},
        )
        log_event(log, "job_completed", job_id=job.id, rows=analyzable, seconds=seconds)
    except JobFailed as exc:
        repo.fail_job(job.id, utcnow(), exc.code, exc.message)
        repo.add_audit(job.id, utcnow(), "JOB_FAILED", {"code": exc.code})
        log_event(log, "job_failed", job_id=job.id, code=exc.code)
    except AppError as exc:
        repo.fail_job(job.id, utcnow(), exc.code, exc.message)
        repo.add_audit(job.id, utcnow(), "JOB_FAILED", {"code": exc.code})
    except Exception:
        log.exception("job_crash")
        repo.fail_job(job.id, utcnow(), "ENGINE_ERROR", "The analysis engine failed.")
        repo.add_audit(job.id, utcnow(), "JOB_FAILED", {"code": "ENGINE_ERROR"})
    finally:
        if not settings.keep_raw_uploads:
            _delete_raw(job.raw_path, False)
            raw_deleted = True
            repo.add_audit(job.id, utcnow(), "RAW_FILE_DELETED", {})
            repo.update_job(job.id, raw_path=None)


def worker_loop(env: dict[str, str], wakeup: Any, stop: Any, status: Any) -> None:
    os.environ.update(env)
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    setup_logging(settings.log_level)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    repo = SqliteRepository(settings.sqlite_path)
    repo.init()
    status["status"] = "loading"
    status["mode"] = settings.ml_engine
    status["device"] = None
    try:
        engine = create_engine(settings)
        info = engine.info()
        status["status"] = engine.status()
        status["device"] = info.get("device")
        status["mode"] = settings.ml_engine
        log_event(log, "engine_ready", mode=settings.ml_engine, device=info.get("device"))
    except EngineContractMismatch as exc:
        status["status"] = "failed"
        status["error"] = str(exc)
        log_event(log, "engine_contract_mismatch")
        engine = None
    except Exception as exc:
        status["status"] = "failed"
        status["error"] = type(exc).__name__
        log.exception("engine_load_failed")
        engine = None

    while not stop.is_set():
        try:
            wakeup.get(timeout=0.4)
        except Exception:
            pass
        if engine is None:
            continue
        while True:
            job = repo.claim_next_queued(utcnow())
            if job is None:
                break
            process_job(job, settings, repo, engine)


def _env_payload(settings: Settings) -> dict[str, str]:
    return {
        "PORT": str(settings.port),
        "CORS_ORIGIN": settings.cors_origin,
        "MAX_FILE_SIZE": str(settings.max_file_size),
        "MIN_ROWS": str(settings.min_rows),
        "MAX_ROWS": str(settings.max_rows),
        "REQUIRE_DATE_COLUMN": str(settings.require_date_column).lower(),
        "DATA_DIR": str(settings.data_dir),
        "DATABASE_URL": settings.database_url,
        "KEEP_RAW_UPLOADS": str(settings.keep_raw_uploads).lower(),
        "JOB_RETENTION_DAYS": str(settings.job_retention_days),
        "JOB_TIMEOUT_SECONDS": str(settings.job_timeout_seconds),
        "WORKER_CONCURRENCY": str(settings.worker_concurrency),
        "QUEUE_MAX_SIZE": str(settings.queue_max_size),
        "DASHBOARD_THEME_LIMIT": str(settings.dashboard_theme_limit),
        "TREND_LOW_SAMPLE": str(settings.trend_low_sample),
        "API_KEY": settings.api_key,
        "LOG_LEVEL": settings.log_level,
        "ML_ENGINE": settings.ml_engine,
        "ML_ENGINE_PATH": str(settings.ml_engine_path),
        "MOCK_PROGRESS_SLEEP": str(settings.mock_progress_sleep),
    }


class WorkerSupervisor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ctx = mp.get_context("spawn")
        self.wakeup = self.ctx.Queue()
        self.stop = self.ctx.Event()
        self.manager = self.ctx.Manager()
        self.status = self.manager.dict()
        self.status.update({"status": "loading", "mode": settings.ml_engine, "device": None})
        self.processes: list[mp.Process] = []

    def start(self) -> None:
        n = self.settings.worker_concurrency
        env = _env_payload(self.settings)
        for _ in range(n):
            p = self.ctx.Process(target=worker_loop, args=(env, self.wakeup, self.stop, self.status), daemon=True)
            p.start()
            self.processes.append(p)
        self.notify()

    def notify(self) -> None:
        try:
            self.wakeup.put_nowait("job")
        except Exception:
            pass

    def engine_status(self) -> dict[str, Any]:
        return {
            "mode": self.status.get("mode", self.settings.ml_engine),
            "status": self.status.get("status", "loading"),
            "device": self.status.get("device"),
        }

    def restart(self) -> None:
        for p in self.processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=5)
                if p.is_alive():
                    p.kill()
        self.processes.clear()
        self.stop.clear()
        self.start()

    def stop_all(self) -> None:
        self.stop.set()
        self.notify()
        for p in self.processes:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
        self.processes.clear()
        try:
            self.manager.shutdown()
        except Exception:
            pass
