"""Enterprise quality module: validation accuracy + embedding drift.

ValidationEvaluator
  Runs the live sentiment engine and Tier-1 classifier over the embedded 100-row set.
  Headline accuracy = mean of (3-class sentiment accuracy, Tier-1 category accuracy).
  "Strongly Negative" counts as Negative when scoring.

DriftMonitor
  Population Stability Index on the distribution of cosine similarity to the baseline
  centroid (decile bins taken from the baseline), plus the centroid cosine distance.
  Status: PSI < 0.10 Low, < 0.25 Moderate, otherwise High.
  Baseline = embeddings saved at BASELINE_PATH. If none exists yet, the first batch is saved
  as the baseline and the status reads "Baseline initialized" (the embedded validation set is
  synthetic, so it is deliberately not used as a drift reference for real reviews).
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from .config import Settings
from .embedder import Embedder
from .sentiment_engine import NEGATIVE, NEGATIVE_LABELS, SentimentEngine
from .topic_extractor import TopicExtractor
from .validation_data import VALIDATION_SET

log = logging.getLogger("feedback_analyzer")


class ValidationEvaluator:
    def __init__(self, dataset: Optional[List[Dict[str, str]]] = None):
        self.dataset = dataset or VALIDATION_SET

    def evaluate(self, sentiment: SentimentEngine, topics: TopicExtractor) -> Dict[str, Any]:
        texts = [r["text"] for r in self.dataset]
        n = len(texts)

        preds = [NEGATIVE if r.label in NEGATIVE_LABELS else r.label for r in sentiment.analyze(texts)]
        gold = [r["sentiment"] for r in self.dataset]
        sent_acc = float(np.mean([p == g for p, g in zip(preds, gold)]))
        per_class = {
            lab: round(float(np.mean([p == g for p, g in zip(preds, gold) if g == lab])), 3)
            for lab in ("Positive", "Neutral", "Negative")
        }

        accs = [sent_acc]
        topic_acc: Optional[float] = None
        if {r["category"] for r in self.dataset} <= set(topics.categories):
            tier1 = topics.classify_general(texts, use_llm=False)
            topic_acc = float(np.mean([p[0] == r["category"] for p, r in zip(tier1, self.dataset)]))
            accs.append(topic_acc)

        overall = float(np.mean(accs))
        return {
            "n": n,
            "dataset": "embedded-100-row synthetic set",
            "overall_accuracy": round(overall, 4),
            "display": f"{overall * 100:.1f}%",
            "sentiment_accuracy": round(sent_acc, 4),
            "sentiment_recall_by_class": per_class,
            "tier1_topic_accuracy": None if topic_acc is None else round(topic_acc, 4),
        }


def _psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def drift_status(psi: float) -> str:
    return "Low" if psi < 0.10 else ("Moderate" if psi < 0.25 else "High")


class DriftMonitor:
    def __init__(self, settings: Settings, embedder: Embedder):
        self.s = settings
        self.embedder = embedder
        self.notes: List[str] = []

    def save_baseline(self, embeddings: np.ndarray) -> str:
        path = self.s.baseline_path
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            embeddings=embeddings.astype(np.float32),
            embedder=np.array(self.embedder.name),
            created=np.array(dt.datetime.now(dt.timezone.utc).isoformat()),
        )
        return str(path)

    def load_baseline(self):
        """Return (embeddings or None, state). state is 'file:<name>', 'missing' or 'unusable'."""
        path = self.s.baseline_path
        if not path.exists():
            return None, "missing"
        try:
            data = np.load(path, allow_pickle=False)
            saved_with = str(data["embedder"])
            if saved_with == self.embedder.name:
                return data["embeddings"], f"file:{path.name}"
            self.notes.append(
                f"Baseline {path.name} was built with '{saved_with}' but the current embedder is "
                f"'{self.embedder.name}'; drift not computed. Re-run with --save-baseline to replace it."
            )
        except Exception as exc:
            self.notes.append(f"Could not read baseline {path.name} ({type(exc).__name__}); drift not computed.")
        log.warning(self.notes[-1])
        return None, "unusable"

    def compute(self, current: np.ndarray) -> Dict[str, Any]:
        if len(current) == 0:
            return {"psi": None, "status": "Unknown", "display": "Unknown", "notes": ["no reviews"]}
        base, source = self.load_baseline()
        if base is None and source == "missing":
            # First run: there is nothing to compare against, so this batch becomes the baseline.
            try:
                saved = self.save_baseline(current)
                self.notes.append(f"No drift baseline found; saved this batch as the baseline ({saved}).")
                return {"psi": None, "status": "Baseline initialized", "display": "Baseline initialized",
                        "baseline_saved_to": saved, "embedder": self.embedder.name}
            except OSError as exc:
                self.notes.append(f"Could not save drift baseline: {exc}")
                return {"psi": None, "status": "Unavailable", "display": "Unavailable", "embedder": self.embedder.name}
        if base is None:
            return {"psi": None, "status": "Unavailable", "display": "Unavailable (baseline unusable)",
                    "embedder": self.embedder.name}
        centroid = base.mean(axis=0)
        centroid = centroid / max(float(np.linalg.norm(centroid)), 1e-9)
        psi = _psi(base @ centroid, current @ centroid)

        cur_c = current.mean(axis=0)
        cur_c = cur_c / max(float(np.linalg.norm(cur_c)), 1e-9)
        status = drift_status(psi)
        return {
            "psi": round(psi, 4),
            "status": status,
            "display": f"{status} ({psi:.2f})",
            "centroid_cosine_distance": round(float(1.0 - centroid @ cur_c), 4),
            "baseline_source": source,
            "baseline_size": int(len(base)),
            "embedder": self.embedder.name,
        }
