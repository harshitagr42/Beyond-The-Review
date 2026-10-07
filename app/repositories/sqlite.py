from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from app.repositories.base import JobRecord, Repository, ReviewRecord, ThemeRecord

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_sha256 TEXT NOT NULL,
    sheet TEXT,
    raw_path TEXT,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    rows_received INTEGER,
    rows_analyzed INTEGER,
    rows_dropped INTEGER,
    dropped_reasons TEXT NOT NULL DEFAULT '{}',
    warnings TEXT NOT NULL DEFAULT '[]',
    error_code TEXT,
    error_message TEXT,
    unassigned_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_results (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    sentiment_breakdown TEXT NOT NULL,
    meta TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS themes (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    theme_id TEXT NOT NULL,
    general_class TEXT NOT NULL,
    name TEXT NOT NULL,
    count INTEGER NOT NULL,
    sentiment TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    representative_indices TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (job_id, theme_id)
);

CREATE TABLE IF NOT EXISTS reviews_scored (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    row INTEGER NOT NULL,
    text TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    sentiment_label TEXT NOT NULL,
    theme_id TEXT,
    date TEXT,
    rating REAL,
    PRIMARY KEY (job_id, row)
);

CREATE INDEX IF NOT EXISTS idx_reviews_theme_sent
    ON reviews_scored (job_id, theme_id, sentiment_score);
CREATE INDEX IF NOT EXISTS idx_reviews_date
    ON reviews_scored (job_id, date);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    timestamp TEXT NOT NULL,
    event TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS throughput (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    rows_per_second REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _json(value: Any) -> str:
    return json.dumps(value)


def _load_json(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    return json.loads(raw)


def _job_from_row(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        file_name=row["file_name"],
        file_size=row["file_size"],
        file_sha256=row["file_sha256"],
        sheet=row["sheet"],
        raw_path=row["raw_path"],
        progress_percent=row["progress_percent"],
        stage=row["stage"],
        rows_received=row["rows_received"],
        rows_analyzed=row["rows_analyzed"],
        rows_dropped=row["rows_dropped"],
        dropped_reasons=_load_json(row["dropped_reasons"], {}),
        warnings=_load_json(row["warnings"], []),
        error_code=row["error_code"],
        error_message=row["error_message"],
        unassigned_count=row["unassigned_count"] or 0,
    )


def _review_from_row(row: sqlite3.Row) -> ReviewRecord:
    return ReviewRecord(
        job_id=row["job_id"],
        row=row["row"],
        text=row["text"],
        sentiment_score=row["sentiment_score"],
        sentiment_label=row["sentiment_label"],
        theme_id=row["theme_id"],
        date=row["date"],
        rating=row["rating"],
    )


class SqliteRepository(Repository):
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._write_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def init(self) -> None:
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()

    def create_job(self, job: JobRecord) -> None:
        with self._write_lock:
            conn = self._connect()
            conn.execute(
                """INSERT INTO jobs (
                    id, status, created_at, started_at, finished_at, file_name, file_size,
                    file_sha256, sheet, raw_path, progress_percent, stage, rows_received,
                    rows_analyzed, rows_dropped, dropped_reasons, warnings, error_code,
                    error_message, unassigned_count
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.id,
                    job.status,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    job.file_name,
                    job.file_size,
                    job.file_sha256,
                    job.sheet,
                    job.raw_path,
                    job.progress_percent,
                    job.stage,
                    job.rows_received,
                    job.rows_analyzed,
                    job.rows_dropped,
                    _json(job.dropped_reasons),
                    _json(job.warnings),
                    job.error_code,
                    job.error_message,
                    job.unassigned_count,
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        conn = self._connect()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(row) if row else None

    def list_jobs_by_status(self, status: str) -> list[JobRecord]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC", (status,)
        ).fetchall()
        return [_job_from_row(r) for r in rows]

    def queued_count(self) -> int:
        conn = self._connect()
        row = conn.execute("SELECT COUNT(*) AS n FROM jobs WHERE status = 'QUEUED'").fetchone()
        return int(row["n"])

    def queue_position(self, job_id: str) -> Optional[int]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT id FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC"
        ).fetchall()
        for i, r in enumerate(rows):
            if r["id"] == job_id:
                return i
        return None

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        mapping = {
            "dropped_reasons": lambda v: _json(v),
            "warnings": lambda v: _json(v),
        }
        cols = []
        vals = []
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            vals.append(mapping[k](v) if k in mapping else v)
        vals.append(job_id)
        with self._write_lock:
            conn = self._connect()
            conn.execute(f"UPDATE jobs SET {', '.join(cols)} WHERE id = ?", vals)
            conn.commit()

    def claim_next_queued(self, started_at: str) -> Optional[JobRecord]:
        with self._write_lock:
            conn = self._connect()
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                """UPDATE jobs SET status = 'PROCESSING', started_at = ?, stage = 'parsing',
                   progress_percent = 1 WHERE id = ? AND status = 'QUEUED'""",
                (started_at, row["id"]),
            )
            conn.commit()
            return self.get_job(row["id"])

    def fail_job(self, job_id: str, finished_at: str, code: str, message: str) -> None:
        self.update_job(
            job_id,
            status="FAILED",
            finished_at=finished_at,
            error_code=code,
            error_message=message,
            progress_percent=0,
        )

    def complete_job(
        self,
        job: JobRecord,
        summary: dict[str, Any],
        sentiment_breakdown: dict[str, Any],
        meta: dict[str, Any],
        themes: list[ThemeRecord],
        reviews: list[ReviewRecord],
        rows_per_second: Optional[float],
    ) -> None:
        with self._write_lock:
            conn = self._connect()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO job_results (job_id, summary, sentiment_breakdown, meta) VALUES (?,?,?,?)",
                (job.id, _json(summary), _json(sentiment_breakdown), _json(meta)),
            )
            conn.executemany(
                """INSERT INTO themes (job_id, theme_id, general_class, name, count, sentiment,
                   sentiment_score, representative_indices) VALUES (?,?,?,?,?,?,?,?)""",
                [
                    (
                        t.job_id,
                        t.theme_id,
                        t.general_class,
                        t.name,
                        t.count,
                        t.sentiment,
                        t.sentiment_score,
                        _json(t.representative_indices),
                    )
                    for t in themes
                ],
            )
            conn.executemany(
                """INSERT INTO reviews_scored (job_id, row, text, sentiment_score, sentiment_label,
                   theme_id, date, rating) VALUES (?,?,?,?,?,?,?,?)""",
                [
                    (
                        r.job_id,
                        r.row,
                        r.text,
                        r.sentiment_score,
                        r.sentiment_label,
                        r.theme_id,
                        r.date,
                        r.rating,
                    )
                    for r in reviews
                ],
            )
            conn.execute(
                """UPDATE jobs SET status = 'COMPLETED', finished_at = ?, progress_percent = 100,
                   stage = NULL, rows_received = ?, rows_analyzed = ?, rows_dropped = ?,
                   dropped_reasons = ?, warnings = ?, unassigned_count = ?, error_code = NULL,
                   error_message = NULL WHERE id = ?""",
                (
                    job.finished_at,
                    job.rows_received,
                    job.rows_analyzed,
                    job.rows_dropped,
                    _json(job.dropped_reasons),
                    _json(job.warnings),
                    job.unassigned_count,
                    job.id,
                ),
            )
            if rows_per_second is not None:
                conn.execute(
                    "INSERT INTO throughput (job_id, rows_per_second, created_at) VALUES (?,?,?)",
                    (job.id, rows_per_second, job.finished_at),
                )
            conn.commit()

    def get_result(self, job_id: str) -> Optional[dict[str, Any]]:
        conn = self._connect()
        row = conn.execute("SELECT * FROM job_results WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        return {
            "summary": json.loads(row["summary"]),
            "sentiment_breakdown": json.loads(row["sentiment_breakdown"]),
            "meta": json.loads(row["meta"]),
        }

    def list_themes(self, job_id: str) -> list[ThemeRecord]:
        conn = self._connect()
        rows = conn.execute("SELECT * FROM themes WHERE job_id = ?", (job_id,)).fetchall()
        return [
            ThemeRecord(
                job_id=r["job_id"],
                theme_id=r["theme_id"],
                general_class=r["general_class"],
                name=r["name"],
                count=r["count"],
                sentiment=r["sentiment"],
                sentiment_score=r["sentiment_score"],
                representative_indices=_load_json(r["representative_indices"], []),
            )
            for r in rows
        ]

    def get_theme(self, job_id: str, theme_id: str) -> Optional[ThemeRecord]:
        conn = self._connect()
        r = conn.execute(
            "SELECT * FROM themes WHERE job_id = ? AND theme_id = ?", (job_id, theme_id)
        ).fetchone()
        if not r:
            return None
        return ThemeRecord(
            job_id=r["job_id"],
            theme_id=r["theme_id"],
            general_class=r["general_class"],
            name=r["name"],
            count=r["count"],
            sentiment=r["sentiment"],
            sentiment_score=r["sentiment_score"],
            representative_indices=_load_json(r["representative_indices"], []),
        )

    def count_reviews(
        self,
        job_id: str,
        theme_id: Optional[str] = None,
        sentiment: Optional[str] = None,
        unassigned: bool = False,
    ) -> int:
        sql = "SELECT COUNT(*) AS n FROM reviews_scored WHERE job_id = ?"
        args: list[Any] = [job_id]
        if unassigned:
            sql += " AND theme_id IS NULL"
        elif theme_id is not None:
            sql += " AND theme_id = ?"
            args.append(theme_id)
        if sentiment:
            sql += " AND sentiment_label = ?"
            args.append(sentiment)
        row = self._connect().execute(sql, args).fetchone()
        return int(row["n"])

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
    ) -> list[ReviewRecord]:
        sql = "SELECT * FROM reviews_scored WHERE job_id = ?"
        args: list[Any] = [job_id]
        if theme_id is not None:
            sql += " AND theme_id = ?"
            args.append(theme_id)
        if sentiment:
            sql += " AND sentiment_label = ?"
            args.append(sentiment)
        if rows is not None:
            if not rows:
                return []
            placeholders = ",".join("?" * len(rows))
            sql += f" AND row IN ({placeholders})"
            args.extend(rows)
        if sort == "most_positive":
            sql += " ORDER BY sentiment_score DESC, row ASC"
        elif sort == "recent":
            sql += " ORDER BY (date IS NULL) ASC, date DESC, row DESC"
        else:
            sql += " ORDER BY sentiment_score ASC, row ASC"
        sql += " LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        found = self._connect().execute(sql, args).fetchall()
        return [_review_from_row(r) for r in found]

    def reviews_with_dates(self, job_id: str, theme_id: Optional[str] = None) -> list[ReviewRecord]:
        sql = "SELECT * FROM reviews_scored WHERE job_id = ?"
        args: list[Any] = [job_id]
        if theme_id is not None:
            sql += " AND theme_id = ?"
            args.append(theme_id)
        found = self._connect().execute(sql, args).fetchall()
        return [_review_from_row(r) for r in found]

    def sentiment_label_counts(self, job_id: str) -> dict[str, int]:
        rows = self._connect().execute(
            "SELECT sentiment_label, COUNT(*) AS n FROM reviews_scored WHERE job_id = ? GROUP BY sentiment_label",
            (job_id,),
        ).fetchall()
        return {r["sentiment_label"]: int(r["n"]) for r in rows}

    def add_audit(self, job_id: Optional[str], timestamp: str, event: str, details: dict[str, Any]) -> None:
        with self._write_lock:
            conn = self._connect()
            conn.execute(
                "INSERT INTO audit_events (job_id, timestamp, event, details) VALUES (?,?,?,?)",
                (job_id, timestamp, event, _json(details)),
            )
            conn.commit()

    def list_audit(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._connect().execute(
            "SELECT timestamp, event, details FROM audit_events WHERE job_id = ? ORDER BY id ASC",
            (job_id,),
        ).fetchall()
        return [
            {"timestamp": r["timestamp"], "event": r["event"], "details": json.loads(r["details"])}
            for r in rows
        ]

    def delete_job(self, job_id: str) -> None:
        with self._write_lock:
            conn = self._connect()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM reviews_scored WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM themes WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM job_results WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()

    def jobs_older_than(self, cutoff_iso: str) -> list[JobRecord]:
        rows = self._connect().execute(
            "SELECT * FROM jobs WHERE created_at < ?", (cutoff_iso,)
        ).fetchall()
        return [_job_from_row(r) for r in rows]

    def avg_rows_per_second(self) -> Optional[float]:
        row = self._connect().execute(
            "SELECT AVG(rows_per_second) AS a FROM (SELECT rows_per_second FROM throughput ORDER BY id DESC LIMIT 5)"
        ).fetchone()
        if row is None or row["a"] is None:
            return None
        return float(row["a"])

    def processing_jobs(self) -> list[JobRecord]:
        return self.list_jobs_by_status("PROCESSING")
