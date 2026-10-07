"""Main orchestration: CSV/Excel/DataFrame in -> backend-ready JSON out.

CLI:
    python -m src.ml.pipeline --input reviews.csv --output output/analysis.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import Settings
from .device import resolve_device
from .drift_validator import DriftMonitor, ValidationEvaluator
from .embedder import Embedder
from .llm_assist import LLMAssist
from .pii_sanitizer import PIISanitizer
from .sentiment_engine import SentimentEngine, SentimentResult, percent_ints
from .topic_extractor import ThemeCluster, TopicExtractor

log = logging.getLogger("feedback_analyzer")

# Type alias for the progress callback: progress_cb(stage_name, fraction)
ProgressCb = Callable[[str, float], None]


def _num(x: float, nd: int = 1):
    """Round; return an int when the value is whole (matches the schema's -18 style)."""
    r = round(float(x), nd)
    return int(r) if r == int(r) else r


def _call_cb(cb: Optional[ProgressCb], stage: str, fraction: float) -> None:
    """Call the progress callback, swallowing any exception it raises."""
    if cb is None:
        return
    try:
        cb(stage, fraction)
    except Exception as exc:  # noqa: BLE001
        log.warning("progress_cb raised on stage=%s fraction=%.2f: %s", stage, fraction, exc)


class FeedbackAnalysisPipeline:
    def __init__(self, settings: Optional[Settings] = None, force_fallback: Optional[bool] = None):
        self.s = settings or Settings.from_env()
        self.force_fallback = (self.s.ml_backend == "fallback") if force_fallback is None else force_fallback
        self.device = "cpu" if self.force_fallback else resolve_device(self.s.device)
        log.info("Device: %s (fallback mode: %s)", self.device, self.force_fallback)

        self.sanitizer = PIISanitizer(self.s.enable_spacy_ner, self.s.spacy_model)
        self.embedder = Embedder(self.s, self.device, self.force_fallback)
        self.llm = LLMAssist(self.s)
        self.sentiment = SentimentEngine(self.s, self.device, self.force_fallback)
        self.topics = TopicExtractor(self.s, self.device, self.embedder, self.llm, self.force_fallback)
        self.validator = ValidationEvaluator()
        self.drift = DriftMonitor(self.s, self.embedder)
        self._validation: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ input
    @staticmethod
    def load_file(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
        p = Path(path)
        if p.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
            return pd.read_excel(p, sheet_name=sheet if sheet else 0)
        return pd.read_csv(p)

    @staticmethod
    def _prepare(df: pd.DataFrame, text_column: str) -> pd.DataFrame:
        if text_column not in df.columns:
            raise ValueError(f"Input is missing the '{text_column}' column (found: {list(df.columns)})")
        out = df.copy()
        # Preserve the original 0-based row position before dropping empties.
        out["_source_row"] = range(len(out))
        out[text_column] = out[text_column].fillna("").astype(str).str.strip()
        out = out[out[text_column] != ""].reset_index(drop=True)
        if out.empty:
            raise ValueError("No non-empty reviews to analyze.")
        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
        if "rating" in out.columns:
            out["rating"] = pd.to_numeric(out["rating"], errors="coerce")
        return out

    # -------------------------------------------------------------------- run
    def run_file(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.run(self.load_file(path, kwargs.pop("sheet", None)), **kwargs)

    def run(
        self,
        df: pd.DataFrame,
        text_column: str = "review_text",
        save_baseline: bool = False,
        include_meta: bool = True,
        include_reviews: bool = False,
        progress_cb: Optional[ProgressCb] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timings: Dict[str, float] = {}

        def tick(name: str, since: float) -> float:
            now = time.perf_counter()
            timings[name] = round(now - since, 3)
            return now

        df = self._prepare(df, text_column)
        t = time.perf_counter()

        # Ordered pipeline stages with their progress keys
        _STAGES = [
            "pii_redaction",
            "sentiment",
            "embeddings",
            "topics",
            "validation",
            "drift",
        ]

        # ---- PII ----------------------------------------------------------------
        _call_cb(progress_cb, "pii_redaction", 0.0)
        self.sanitizer.reset()
        clean = self.sanitizer.sanitize_batch(df[text_column].tolist())
        t = tick("pii", t)
        _call_cb(progress_cb, "pii_redaction", 1.0)

        # ---- Sentiment ----------------------------------------------------------
        _call_cb(progress_cb, "sentiment", 0.0)
        sent = self.sentiment.analyze(clean)
        t = tick("sentiment", t)
        _call_cb(progress_cb, "sentiment", 1.0)

        # ---- Embeddings ---------------------------------------------------------
        _call_cb(progress_cb, "embeddings", 0.0)
        emb = self.embedder.encode(clean)
        t = tick("embeddings", t)
        _call_cb(progress_cb, "embeddings", 1.0)

        # ---- Topics -------------------------------------------------------------
        _call_cb(progress_cb, "topics", 0.0)
        clusters = self.topics.extract(clean, emb)
        t = tick("topics", t)
        _call_cb(progress_cb, "topics", 1.0)

        themes = self._assemble_themes(clusters, clean, sent)

        # ---- Validation ---------------------------------------------------------
        _call_cb(progress_cb, "validation", 0.0)
        if self._validation is None:  # the embedded set never changes, so score it once per process
            self._validation = self.validator.evaluate(self.sentiment, self.topics)
        t = tick("validation", t)
        _call_cb(progress_cb, "validation", 1.0)

        # ---- Drift --------------------------------------------------------------
        _call_cb(progress_cb, "drift", 0.0)
        drift = self.drift.compute(emb)
        if save_baseline:
            drift["baseline_saved_to"] = self.drift.save_baseline(emb)
        tick("drift", t)
        _call_cb(progress_cb, "drift", 1.0)

        agg = self.sentiment.summarize(sent)
        pos_i, neu_i, neg_i = percent_ints([agg["positive"], agg["neutral"], agg["negative"]])

        result: Dict[str, Any] = {
            "summary": {
                "total_reviews": int(len(df)),
                "overall_sentiment": self.sentiment.overall_label(agg["nss"]),
                "net_sentiment_score": _num(agg["nss"]),
                "pii_redacted_count": self.sanitizer.total_redacted,
                "model_validation_accuracy": self._validation["display"],
                "drift_status": drift["display"],
            },
            "sentiment_breakdown": {"positive": pos_i, "neutral": neu_i, "negative": neg_i},
            "themes": themes,
        }

        if include_reviews:
            result["reviews"] = self._assemble_reviews(df, clusters, clean, sent, text_column)

        if include_meta:
            notes: List[str] = []
            for comp in (self.sanitizer, self.embedder, self.sentiment, self.topics, self.llm, self.drift):
                notes.extend(getattr(comp, "notes", []))
            timings["total"] = round(time.perf_counter() - t0, 3)
            result["meta"] = {
                "device": self.device,
                "backends": {
                    "sentiment": self.sentiment.backend,
                    "tier1": self.topics.tier1_backend,
                    "tier2": sorted(self.topics.tier2_backends),
                    "embeddings": self.embedder.name,
                    "llm_assist": self.llm.provider if self.llm.enabled else "off",
                },
                "mean_polarity": round(agg["mean_score"], 4),
                "pii_breakdown": self.sanitizer.report(),
                "validation": self._validation,
                "drift": drift,
                "date_range": self._date_range(df),
                "average_rating": _num(df["rating"].mean(), 2) if "rating" in df and df["rating"].notna().any() else None,
                "themes_total": len(clusters),
                "themes_returned": len(themes),
                "seconds": timings,
                "warnings": sorted(set(notes)),
            }
        return result

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _date_range(df: pd.DataFrame) -> Optional[Dict[str, str]]:
        if "date" not in df or df["date"].notna().sum() == 0:
            return None
        return {"start": df["date"].min().date().isoformat(), "end": df["date"].max().date().isoformat()}

    def _assemble_themes(
        self, clusters: List[ThemeCluster], texts: List[str], sent: List[SentimentResult]
    ) -> List[Dict[str, Any]]:
        themes: List[Dict[str, Any]] = []
        vid = 0
        for n, c in enumerate(clusters[: self.s.max_themes], start=1):
            score = float(np.mean([sent[i].score for i in c.indices]))
            verbatims = []
            for i in c.representatives:
                vid += 1
                verbatims.append({"id": f"v{vid}", "text": texts[i], "sentiment": sent[i].label})
            themes.append(
                {
                    "id": f"theme-{n}",
                    "general_class": c.general_class,
                    "name": c.name,
                    "count": len(c.indices),
                    "sentiment": self.sentiment.label_for(score),
                    "sentiment_score": round(score, 2),
                    "sample_verbatims": verbatims,
                    # Positions (0-based within analysed rows) of the representative reviews,
                    # in the same order as sample_verbatims.
                    "representative_indices": [int(i) for i in c.representatives],
                }
            )
        return themes

    def _assemble_reviews(
        self,
        df: pd.DataFrame,
        clusters: List[ThemeCluster],
        clean_texts: List[str],
        sent: List[SentimentResult],
        text_column: str,
    ) -> List[Dict[str, Any]]:
        """Build the per-review list.

        Returns one entry per analysed review (post-empty-drop) in row order.
        Invariant: the number of reviews carrying a given theme_id equals that theme's count.
        """
        # Build a map: analysed-row-index -> theme_id (for themes within max_themes cap)
        row_to_theme: Dict[int, str] = {}
        for n, c in enumerate(clusters[: self.s.max_themes], start=1):
            theme_id = f"theme-{n}"
            for idx in c.indices:
                row_to_theme[idx] = theme_id

        reviews = []
        for row in range(len(df)):
            r = df.iloc[row]
            source_row = int(r["_source_row"])

            date_val = None
            if "date" in df.columns and pd.notna(r.get("date")):
                try:
                    date_val = pd.Timestamp(r["date"]).date().isoformat()
                except Exception:
                    date_val = None

            rating = r.get("rating") if "rating" in df.columns else None
            if rating is not None and (not isinstance(rating, float) or not (rating != rating)):
                rating = float(rating)
            else:
                rating = None

            reviews.append(
                {
                    "row": row,
                    "source_row": source_row,
                    "text": clean_texts[row],
                    "sentiment_score": round(float(sent[row].score), 4),
                    "sentiment_label": sent[row].label,
                    "theme_id": row_to_theme.get(row),
                    "date": date_val,
                    "rating": rating,
                }
            )
        return reviews


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Not JSON serializable: {type(o)}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Feedback & Review Analyzer - local NLP engine")
    ap.add_argument("--input", required=True, help="CSV or Excel file with a review_text column")
    ap.add_argument("--output", default="output/analysis.json", help="JSON output path, or '-' for stdout")
    ap.add_argument("--text-column", default="review_text")
    ap.add_argument("--sheet", default=None, help="Excel sheet name (default: first sheet)")
    ap.add_argument("--device", choices=["auto", "mps", "cuda", "cpu"], default=None)
    ap.add_argument("--fallback", action="store_true", help="Skip transformer models (VADER + keyword/TF-IDF)")
    ap.add_argument("--save-baseline", action="store_true", help="Save this batch's embeddings as the drift baseline")
    ap.add_argument("--strict-schema", action="store_true", help="Omit the extra top-level 'meta' block")
    ap.add_argument("--include-reviews", action="store_true", help="Include per-review list in output")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    settings = Settings.from_env()
    if args.device:
        settings.device = args.device
    pipe = FeedbackAnalysisPipeline(settings, force_fallback=True if args.fallback else None)
    result = pipe.run_file(
        args.input,
        sheet=args.sheet,
        text_column=args.text_column,
        save_baseline=args.save_baseline,
        include_meta=not args.strict_schema,
        include_reviews=args.include_reviews,
    )
    payload = json.dumps(result, indent=2, ensure_ascii=False, default=_json_default)
    if args.output == "-":
        print(payload)
    else:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        s = result["summary"]
        print(
            f"Analyzed {s['total_reviews']} reviews -> {out}\n"
            f"  sentiment: {s['overall_sentiment']} (NSS {s['net_sentiment_score']}) | "
            f"PII redacted: {s['pii_redacted_count']} | validation: {s['model_validation_accuracy']} | "
            f"drift: {s['drift_status']} | themes: {len(result['themes'])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
