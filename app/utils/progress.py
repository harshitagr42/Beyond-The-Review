from __future__ import annotations

from typing import Optional


STAGE_ORDER = [
    "parsing",
    "pii_redaction",
    "sentiment",
    "embeddings",
    "topics",
    "validation",
    "drift",
    "persisting",
]


def overall_percent(weights: dict[str, float], stage: str, fraction: float) -> int:
    total = sum(weights.values()) or 1.0
    done = 0.0
    for name in STAGE_ORDER:
        w = weights.get(name, 0.0)
        if name == stage:
            done += w * max(0.0, min(1.0, fraction))
            break
        done += w
    pct = int(round(100.0 * done / total))
    return max(0, min(99, pct))


def time_based_percent(elapsed_seconds: float, expected_seconds: Optional[float]) -> int:
    if not expected_seconds or expected_seconds <= 0:
        return min(95, max(1, int(elapsed_seconds)))
    pct = int(round(95.0 * min(1.0, elapsed_seconds / expected_seconds)))
    return max(1, min(95, pct))
