from __future__ import annotations

import hashlib
import random
import re
import time
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd

from app.services.ml_engine.base import AnalysisResult, MLEngine, ProgressCb, result_from_dict

STAGES = ("pii_redaction", "sentiment", "embeddings", "topics", "validation", "drift")

THEME_SPECS = [
    ("theme-1", "Streaming/Playback", "Pause Button Frozen During Video Playback", -0.82, "Strongly Negative"),
    ("theme-2", "Billing & Subscriptions", "Charged Twice Monthly Subscription", -0.71, "Negative"),
    ("theme-3", "Performance & Crashes", "App Crash After Splash Screen", -0.64, "Negative"),
    ("theme-4", "UI/UX & Navigation", "Confusing Menu Layout Search", 0.12, "Neutral"),
    ("theme-5", "Comments & Social", "Comment Section Never Loads", -0.45, "Negative"),
    ("theme-6", "Streaming/Playback", "Smooth Playback Sharp Picture", 0.74, "Positive"),
    ("theme-7", "Billing & Subscriptions", "Fair Pricing Easy Cancel", 0.61, "Positive"),
    ("theme-8", "Performance & Crashes", "Fast Stable Battery Life", 0.55, "Positive"),
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+?\d{1,3}[\s.\-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\w)"
)
SSN_RE = re.compile(r"(?<![\d-])\d{3}[- ]\d{2}[- ]\d{4}(?![\d-])")
CC_RE = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IN_PHONE_RE = re.compile(r"(?<![\w.])[6-9]\d{4}[\s\-]?\d{5}(?!\w)")


def _redact(text: str) -> tuple[str, dict[str, int]]:
    counts = {"email": 0, "phone": 0, "credit_card": 0, "ssn": 0, "ip_address": 0, "person": 0}

    def sub(pattern: re.Pattern[str], tag: str, key: str, s: str) -> str:
        def repl(_m: re.Match[str]) -> str:
            counts[key] += 1
            return tag

        return pattern.sub(repl, s)

    text = sub(EMAIL_RE, "[EMAIL_REDACTED]", "email", text)
    text = sub(SSN_RE, "[PII_REDACTED]", "ssn", text)
    text = sub(CC_RE, "[PII_REDACTED]", "credit_card", text)
    text = sub(IP_RE, "[PII_REDACTED]", "ip_address", text)
    text = sub(PHONE_RE, "[PHONE_REDACTED]", "phone", text)
    text = sub(IN_PHONE_RE, "[PHONE_REDACTED]", "phone", text)
    return text, counts


def _label_for(score: float) -> str:
    if score <= -0.75:
        return "Strongly Negative"
    if score < -0.15:
        return "Negative"
    if score <= 0.15:
        return "Neutral"
    return "Positive"


def _overall(nss: float) -> str:
    if nss > 10:
        return "Positive Trend"
    if nss < -10:
        return "Negative Trend"
    return "Mixed Trend"


def _percent_ints(pos: int, neu: int, neg: int) -> tuple[int, int, int]:
    total = pos + neu + neg
    if total == 0:
        return 0, 0, 0
    raw = [pos * 100.0 / total, neu * 100.0 / total, neg * 100.0 / total]
    floors = [int(r) for r in raw]
    rem = 100 - sum(floors)
    order = sorted(range(3), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:rem]:
        floors[i] += 1
    return floors[0], floors[1], floors[2]


class MockEngine(MLEngine):
    def __init__(self, sleep_s: float = 0.05) -> None:
        self.sleep_s = sleep_s
        self._status = "ready"
        self._info = {
            "engine": "mock",
            "version": "1.0.0",
            "device": "cpu",
            "backends": {
                "sentiment": "mock",
                "tier1": "mock",
                "tier2": ["mock"],
                "embeddings": "mock",
                "llm_assist": "off",
            },
        }

    def status(self) -> str:
        return self._status

    def info(self) -> dict[str, Any]:
        return dict(self._info)

    def analyze(self, df: pd.DataFrame, progress_cb: Optional[ProgressCb] = None) -> AnalysisResult:
        seed = 42 + int(len(df))
        rng = random.Random(seed)

        n_themes = 4 + (len(df) % 5)
        n_themes = min(8, max(4, n_themes))
        specs = THEME_SPECS[:n_themes]

        pii_total = {
            "email": 0,
            "phone": 0,
            "credit_card": 0,
            "ssn": 0,
            "ip_address": 0,
            "person": 0,
        }
        cleaned: list[str] = []
        for raw in df["review_text"].tolist():
            text, counts = _redact(str(raw))
            cleaned.append(text)
            for k, v in counts.items():
                pii_total[k] += v

        for stage in STAGES:
            if progress_cb:
                progress_cb(stage, 0.15)
            if self.sleep_s:
                time.sleep(self.sleep_s)
            if progress_cb:
                progress_cb(stage, 1.0)

        n = len(df)
        unassigned_n = max(0, n // 12)
        assigned_n = n - unassigned_n
        weights = [max(1, 10 - i) for i in range(n_themes)]
        wsum = sum(weights)
        theme_sizes = [int(assigned_n * w / wsum) for w in weights]
        theme_sizes[0] += assigned_n - sum(theme_sizes)

        assignment: list[Optional[str]] = [None] * n
        idx = 0
        for spec, size in zip(specs, theme_sizes):
            for _ in range(size):
                if idx >= n:
                    break
                assignment[idx] = spec[0]
                idx += 1
        # shuffle assignment deterministically without changing counts
        order = list(range(n))
        rng.shuffle(order)
        shuffled: list[Optional[str]] = [None] * n
        values = assignment[:]
        for i, src in enumerate(order):
            shuffled[src] = values[i]
        assignment = shuffled

        reviews = []
        scores_by_theme: dict[str, list[float]] = {s[0]: [] for s in specs}
        dates: list[Optional[str]] = []
        for i in range(n):
            row = df.iloc[i]
            theme_id = assignment[i]
            base = next((s[3] for s in specs if s[0] == theme_id), 0.0)
            jitter = (rng.random() - 0.5) * 0.3
            if pd.notna(row.get("rating")):
                rating = float(row["rating"])
                rating_score = (rating - 3) / 2.0
                score = round(max(-1.0, min(1.0, 0.6 * base + 0.4 * rating_score + jitter)), 2)
            else:
                rating = None
                score = round(max(-1.0, min(1.0, base + jitter)), 2)
            label = _label_for(score)
            dval = None
            if "date" in df.columns and pd.notna(row.get("date")):
                ts = pd.to_datetime(row["date"], errors="coerce")
                if pd.notna(ts):
                    dval = ts.date().isoformat()
            dates.append(dval)
            if theme_id:
                scores_by_theme[theme_id].append(score)
            reviews.append(
                {
                    "row": i,
                    "text": cleaned[i],
                    "sentiment_score": score,
                    "sentiment_label": label,
                    "theme_id": theme_id,
                    "date": dval,
                    "rating": rating,
                }
            )

        themes = []
        for spec in specs:
            tid, gclass, name, _base, _lab = spec
            members = [r for r in reviews if r["theme_id"] == tid]
            if not members:
                continue
            mean = sum(r["sentiment_score"] for r in members) / len(members)
            mean = round(mean, 2)
            reps = [r["row"] for r in sorted(members, key=lambda r: r["sentiment_score"])[:3]]
            samples = []
            for j, r in enumerate(members[:3], start=1):
                samples.append({"id": f"v{j}", "text": r["text"][:240], "sentiment": r["sentiment_label"]})
            themes.append(
                {
                    "id": tid,
                    "general_class": gclass,
                    "name": name,
                    "count": len(members),
                    "sentiment": _label_for(mean),
                    "sentiment_score": mean,
                    "sample_verbatims": samples,
                    "representative_indices": reps,
                }
            )
        themes.sort(key=lambda t: t["count"], reverse=True)

        pos = sum(1 for r in reviews if r["sentiment_label"] == "Positive")
        neu = sum(1 for r in reviews if r["sentiment_label"] == "Neutral")
        neg = sum(1 for r in reviews if r["sentiment_label"] in {"Negative", "Strongly Negative"})
        p_i, n_i, g_i = _percent_ints(pos, neu, neg)
        nss = round((pos - neg) / n * 100, 1) if n else 0
        usable_dates = [d for d in dates if d]
        date_range = None
        if usable_dates:
            date_range = {"start": min(usable_dates), "end": max(usable_dates)}
        ratings = [r["rating"] for r in reviews if r["rating"] is not None]
        pii_sum = sum(pii_total.values())
        pii_total["total"] = pii_sum
        mean_polarity = round(sum(r["sentiment_score"] for r in reviews) / n, 4) if n else 0.0

        payload = {
            "summary": {
                "total_reviews": n,
                "overall_sentiment": _overall(float(nss)),
                "net_sentiment_score": int(nss) if float(nss) == int(nss) else nss,
                "pii_redacted_count": pii_sum,
                "model_validation_accuracy": "78.0%",
                "drift_status": "Low (0.03)",
            },
            "sentiment_breakdown": {"positive": p_i, "neutral": n_i, "negative": g_i},
            "themes": themes,
            "reviews": reviews,
            "meta": {
                "device": "cpu",
                "backends": self._info["backends"],
                "mean_polarity": mean_polarity,
                "pii_breakdown": pii_total,
                "validation": {
                    "n": 100,
                    "dataset": "embedded-100-row synthetic set",
                    "overall_accuracy": 0.78,
                    "display": "78.0%",
                    "sentiment_accuracy": 0.65,
                    "sentiment_recall_by_class": {"Positive": 0.77, "Neutral": 0.93, "Negative": 0.35},
                    "tier1_topic_accuracy": 0.91,
                },
                "drift": {
                    "psi": 0.03,
                    "status": "Low",
                    "display": "Low (0.03)",
                    "centroid_cosine_distance": 0.01,
                    "baseline_source": "file:baseline_embeddings.npz",
                    "baseline_size": 10000,
                    "embedder": "mock",
                },
                "date_range": date_range,
                "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
                "themes_total": len(themes),
                "themes_returned": len(themes),
                "seconds": {
                    "pii": 0.1,
                    "sentiment": 0.2,
                    "embeddings": 0.1,
                    "topics": 0.2,
                    "validation": 0.05,
                    "drift": 0.05,
                    "total": max(0.4, n / 500.0),
                },
                "warnings": [],
            },
        }
        return result_from_dict(payload)


def _unused_hash(text: str) -> int:
    return int(hashlib.md5(text.encode()).hexdigest()[:8], 16)


# keep date helper referenced for deterministic spreads when dates missing
def spread_dates(n: int, end: date | None = None) -> list[str]:
    end = end or date(2026, 10, 1)
    return [(end - timedelta(days=i % 90)).isoformat() for i in range(n)]
