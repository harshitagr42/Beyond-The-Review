from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

REDACTION_TAGS = ("[EMAIL_REDACTED]", "[PHONE_REDACTED]", "[PII_REDACTED]")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
VALENCE_THRESHOLD = 1.5


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, float]:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        return dict(SentimentIntensityAnalyzer().lexicon)
    except Exception:
        return {}


def py_to_utf16(text: str, index: int) -> int:
    return len(text[:index].encode("utf-16-le")) // 2


def highlight_text(text: str) -> list[dict[str, Any]]:
    try:
        return _highlight(text)
    except Exception:
        return []


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for tag in REDACTION_TAGS:
        start = 0
        while True:
            i = text.find(tag, start)
            if i < 0:
                break
            spans.append((i, i + len(tag)))
            start = i + len(tag)
    return spans


def _in_span(idx: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= idx < b for a, b in spans)


def _highlight(text: str) -> list[dict[str, Any]]:
    lex = _lexicon()
    if not lex or not text:
        return []
    protected = _protected_spans(text)
    hits: list[dict[str, Any]] = []
    lower = text.lower()
    # Prefer longer lexicon keys (phrases) first.
    phrases = sorted((k for k in lex if " " in k), key=len, reverse=True)
    used = [False] * len(text)

    def mark(start: int, end: int, score: float, term: str) -> None:
        if any(used[i] for i in range(start, end)):
            return
        if any(_in_span(i, protected) for i in range(start, end)):
            return
        if abs(score) < VALENCE_THRESHOLD:
            return
        polarity = "positive" if score > 0 else "negative"
        for i in range(start, end):
            used[i] = True
        hits.append(
            {
                "start": py_to_utf16(text, start),
                "end": py_to_utf16(text, end),
                "polarity": polarity,
                "term": text[start:end],
            }
        )

    for phrase in phrases:
        start = 0
        needle = phrase.lower()
        while True:
            i = lower.find(needle, start)
            if i < 0:
                break
            mark(i, i + len(phrase), float(lex[phrase]), text[i : i + len(phrase)])
            start = i + len(phrase)

    def _score_word(k: str) -> Optional[float]:
        if k in lex:
            return float(lex[k])
        candidates = []
        if k.endswith("ed"):
            candidates.extend([k[:-2], k[:-1]])
        elif k.endswith("ing"):
            candidates.extend([k[:-3], k[:-3] + "e"])
        elif k.endswith("es"):
            candidates.extend([k[:-2], k[:-1]])
        elif k.endswith("s"):
            candidates.append(k[:-1])
        elif k.endswith("ly"):
            candidates.append(k[:-2])
        for c in candidates:
            if c in lex:
                return float(lex[c])
        return None

    for m in TOKEN_RE.finditer(text):
        word = m.group(0)
        key = word.lower()
        score = _score_word(key)
        if score is None:
            continue
        mark(m.start(), m.end(), score, word)

    hits.sort(key=lambda h: h["start"])
    return hits
