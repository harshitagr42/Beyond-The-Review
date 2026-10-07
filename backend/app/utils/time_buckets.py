from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nat", "none", "nan"}:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "")).date()
    except ValueError:
        return None


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def next_week(d: date) -> date:
    return d + timedelta(days=7)


def next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def period_label(start: date, interval: str) -> str:
    if interval == "weekly":
        iso = start.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return start.strftime("%Y-%m")


def bucket_key(d: date, interval: str) -> date:
    return week_start(d) if interval == "weekly" else month_start(d)


def iter_empty_range(start: date, end: date, interval: str) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur = next_week(cur) if interval == "weekly" else next_month(cur)
