from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd

from app.config import Settings
from app.utils.column_mapping import map_columns
from app.utils.errors import AppError
from app.utils.file_parsing import extension_ok, peek_headers, sniff_kind, validate_headers, read_dataframe
from app.utils.time_buckets import parse_date


async def stream_upload_to_disk(upload, dest: Path, max_size: int) -> tuple[int, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    size = 0
    try:
        with dest.open("wb") as fh:
            while True:
                chunk = await upload.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_size:
                    raise AppError(413, "FILE_TOO_LARGE", "The uploaded file exceeds the maximum allowed size.")
                hasher.update(chunk)
                fh.write(chunk)
    except AppError:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise AppError(400, "EMPTY_FILE", "The file is empty.")
    return size, hasher.hexdigest()


def fast_validate_upload(path: Path, filename: str, settings: Settings, sheet: Optional[str] = None) -> None:
    if not extension_ok(filename):
        raise AppError(400, "INVALID_FILE_FORMAT", "Invalid file format. Only .csv and .xlsx supported.")
    kind = sniff_kind(path, filename)
    headers = peek_headers(path, kind, sheet)
    validate_headers(headers, settings.require_date_column)


def parse_upload(path: Path, filename: str, sheet: Optional[str], settings: Settings) -> tuple[pd.DataFrame, int, dict]:
    kind = sniff_kind(path, filename)
    df = read_dataframe(path, kind, sheet)
    received = int(len(df))
    mapping = map_columns([str(c) for c in df.columns])
    from app.utils.column_mapping import required_missing

    missing = required_missing(mapping, settings.require_date_column)
    if missing:
        raise AppError(
            422,
            "MISSING_COLUMN",
            "Required column(s) are missing.",
            {"missing": missing, "found": [str(c) for c in df.columns]},
        )
    return df, received, mapping


def clean_dataframe(df: pd.DataFrame, mapping: dict, settings: Settings) -> tuple[pd.DataFrame, int, list[str]]:
    text_col = mapping["review_text"]
    date_col = mapping.get("date")
    rating_col = mapping.get("rating")
    out = pd.DataFrame()
    out["review_text"] = df[text_col].fillna("").astype(str).str.strip()
    empty_mask = out["review_text"] == ""
    dropped = int(empty_mask.sum())
    out = out.loc[~empty_mask].copy()
    warnings: list[str] = []

    if date_col:
        raw_dates = df.loc[~empty_mask, date_col]
        parsed = []
        unparseable = 0
        nonempty = 0
        for val in raw_dates.tolist():
            if val is None or (isinstance(val, float) and pd.isna(val)) or str(val).strip() == "":
                parsed.append(pd.NaT)
                continue
            nonempty += 1
            d = parse_date(val)
            if d is None:
                unparseable += 1
                parsed.append(pd.NaT)
            else:
                parsed.append(pd.Timestamp(d))
        out["date"] = parsed
        if nonempty and unparseable / nonempty > 0.5:
            warnings.append("More than 50% of date values could not be parsed and were treated as missing.")
    if rating_col:
        out["rating"] = pd.to_numeric(df.loc[~empty_mask, rating_col], errors="coerce")

    out = out.reset_index(drop=True)
    return out, dropped, warnings


def sweep_orphaned_uploads(uploads_dir: Path, max_age_seconds: int = 3600) -> int:
    if not uploads_dir.exists():
        return 0
    import time as _time

    now = _time.time()
    removed = 0
    for p in uploads_dir.iterdir():
        if not p.is_file():
            continue
        age = now - p.stat().st_mtime
        if age > max_age_seconds:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed
