from __future__ import annotations

from typing import Optional

REVIEW_TEXT_ALIASES = {
    "review_text",
    "review",
    "text",
    "content",
    "comment",
    "feedback",
    "body",
}
DATE_ALIASES = {"date", "created_at", "timestamp", "review_date"}
RATING_ALIASES = {"rating", "stars", "score"}


def _norm(name: str) -> str:
    return name.strip().lower()


def map_columns(headers: list[str]) -> dict[str, Optional[str]]:
    """Return canonical -> original header name (or None)."""
    found: dict[str, Optional[str]] = {"review_text": None, "date": None, "rating": None}
    for original in headers:
        key = _norm(str(original))
        if found["review_text"] is None and key in REVIEW_TEXT_ALIASES:
            found["review_text"] = original
        elif found["date"] is None and key in DATE_ALIASES:
            found["date"] = original
        elif found["rating"] is None and key in RATING_ALIASES:
            found["rating"] = original
    return found


def required_missing(mapping: dict[str, Optional[str]], require_date: bool) -> list[str]:
    missing: list[str] = []
    if mapping.get("review_text") is None:
        missing.append("review_text")
    if require_date and mapping.get("date") is None:
        missing.append("date")
    return missing
