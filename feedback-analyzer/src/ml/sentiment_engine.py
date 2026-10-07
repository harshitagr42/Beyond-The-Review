"""Sentiment engine: polarity in [-1, +1], 4-way label, Net Sentiment Score.

Backends
  roberta : cardiffnlp/twitter-roberta-base-sentiment-latest (HF pipeline, MPS-accelerated)
            polarity = P(positive) - P(negative)
  vader   : nltk.sentiment.vader (or the vaderSentiment package if the NLTK lexicon
            can't be downloaded); polarity = compound score
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np

from .config import Settings

log = logging.getLogger("feedback_analyzer")

POSITIVE = "Positive"
NEUTRAL = "Neutral"
NEGATIVE = "Negative"
STRONG_NEGATIVE = "Strongly Negative"
NEGATIVE_LABELS = {NEGATIVE, STRONG_NEGATIVE}

_LEGACY_LABELS = {"label_0": "negative", "label_1": "neutral", "label_2": "positive"}


@dataclass
class SentimentResult:
    score: float
    label: str


def percent_ints(counts: Sequence[int]) -> List[int]:
    """Convert counts to integer percentages that sum to exactly 100 (largest remainder)."""
    total = sum(counts)
    if total == 0:
        return [0] * len(counts)
    raw = [c * 100.0 / total for c in counts]
    floors = [int(r) for r in raw]
    remainder = 100 - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


class SentimentEngine:
    def __init__(self, settings: Settings, device: str = "cpu", force_fallback: bool = False):
        self.s = settings
        self.device = device
        self.backend = "none"
        self.notes: List[str] = []
        self._pipe = None
        self._vader = None

        want = "vader" if force_fallback else settings.sentiment_backend
        if want in ("auto", "roberta"):
            try:
                self._load_roberta()
                self.backend = "roberta"
            except Exception as exc:
                if want == "roberta":
                    raise
                self.notes.append(
                    f"RoBERTa sentiment unavailable ({type(exc).__name__}); falling back to VADER."
                )
                log.warning(self.notes[-1])
        if self.backend == "none":
            self._load_vader()

    # ----------------------------------------------------------------- loaders
    def _load_roberta(self) -> None:
        from transformers import pipeline

        self._pipe = pipeline(
            "text-classification",
            model=self.s.sentiment_model,
            tokenizer=self.s.sentiment_model,
            device=self.device,
        )

    def _load_vader(self) -> None:
        try:
            import nltk
            from nltk.sentiment.vader import SentimentIntensityAnalyzer

            try:
                self._vader = SentimentIntensityAnalyzer()
            except LookupError:
                nltk.download("vader_lexicon", quiet=True)
                self._vader = SentimentIntensityAnalyzer()
            self.backend = "vader-nltk"
            return
        except Exception as exc:
            self.notes.append(f"NLTK VADER lexicon unavailable ({type(exc).__name__}); using vaderSentiment.")
            log.info(self.notes[-1])
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer as _V

        self._vader = _V()
        self.backend = "vader"

    # --------------------------------------------------------------- labelling
    def label_for(self, score: float) -> str:
        if score >= self.s.positive_threshold:
            return POSITIVE
        if score <= self.s.strong_negative_threshold:
            return STRONG_NEGATIVE
        if score <= self.s.negative_threshold:
            return NEGATIVE
        return NEUTRAL

    # --------------------------------------------------------------- inference
    def _predict_roberta(self, texts: List[str]) -> np.ndarray:
        # Sort by length so each padded batch is homogeneous (big speed-up), then restore order.
        order = np.argsort([len(t) for t in texts])
        sorted_texts = [texts[i] for i in order]

        def run():
            return self._pipe(
                sorted_texts,
                batch_size=self.s.batch_size,
                top_k=None,
                truncation=True,
                max_length=256,
            )

        try:
            outputs = run()
        except RuntimeError as exc:
            if self.device == "cpu":
                raise
            self.notes.append(f"Sentiment inference failed on {self.device} ({exc}); retrying on CPU.")
            log.warning(self.notes[-1])
            self.device = "cpu"
            self._load_roberta()
            outputs = run()

        scores = np.zeros(len(texts), dtype=np.float64)
        for rank, out in enumerate(outputs):
            probs: Dict[str, float] = {}
            for d in out:
                name = str(d["label"]).lower()
                probs[_LEGACY_LABELS.get(name, name)] = float(d["score"])
            scores[order[rank]] = probs.get("positive", 0.0) - probs.get("negative", 0.0)
        return scores

    def _predict_vader(self, texts: List[str]) -> np.ndarray:
        return np.array([self._vader.polarity_scores(t)["compound"] for t in texts], dtype=np.float64)

    def analyze(self, texts: Sequence[str]) -> List[SentimentResult]:
        texts = list(texts)
        if not texts:
            return []
        unique = list(dict.fromkeys(texts))
        scores = self._predict_roberta(unique) if self.backend == "roberta" else self._predict_vader(unique)
        scores = np.clip(scores, -1.0, 1.0)
        lut = {t: round(float(s), 4) for t, s in zip(unique, scores)}
        return [SentimentResult(lut[t], self.label_for(lut[t])) for t in texts]

    # --------------------------------------------------------------- aggregate
    @staticmethod
    def summarize(results: Sequence[SentimentResult]) -> Dict[str, float]:
        n = len(results)
        if n == 0:
            return {"positive": 0, "neutral": 0, "negative": 0, "nss": 0.0, "mean_score": 0.0}
        pos = sum(r.label == POSITIVE for r in results)
        neg = sum(r.label in NEGATIVE_LABELS for r in results)
        neu = n - pos - neg
        return {
            "positive": pos,
            "neutral": neu,
            "negative": neg,
            "nss": (pos - neg) * 100.0 / n,  # NSS = %positive - %negative
            "mean_score": float(np.mean([r.score for r in results])),
        }

    @staticmethod
    def overall_label(nss: float) -> str:
        if nss <= -10:
            return "Negative Trend"
        if nss >= 10:
            return "Positive Trend"
        return "Mixed Trend"
