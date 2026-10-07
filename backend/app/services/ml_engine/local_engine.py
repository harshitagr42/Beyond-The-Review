from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.services.ml_engine.base import (
    AnalysisResult,
    EngineContractMismatch,
    MLEngine,
    ProgressCb,
    result_from_dict,
)
from app.utils.logging import get_logger, log_event

log = get_logger("app.ml")


def assert_engine_contract(engine_path: Path) -> None:
    pipeline_file = engine_path / "src" / "ml" / "pipeline.py"
    if not pipeline_file.is_file():
        raise EngineContractMismatch(
            "ENGINE_CONTRACT_MISMATCH: ML_ENGINE_PATH does not contain src/ml/pipeline.py."
        )
    text = pipeline_file.read_text(encoding="utf-8")
    if '"reviews"' not in text and "'reviews'" not in text:
        raise EngineContractMismatch(
            "ENGINE_CONTRACT_MISMATCH: FeedbackAnalysisPipeline does not return reviews[]. "
            "The backend requires per-review rows; refusing to limp along."
        )


class LocalEngine(MLEngine):
    def __init__(self, engine_path: Path) -> None:
        self.engine_path = Path(engine_path).resolve()
        self._status = "loading"
        self._info: dict[str, Any] = {
            "engine": "local",
            "version": "unknown",
            "device": None,
            "backends": {},
        }
        assert_engine_contract(self.engine_path)
        root = str(self.engine_path)
        if root not in sys.path:
            sys.path.insert(0, root)
        from src.ml.pipeline import FeedbackAnalysisPipeline

        self._pipeline = FeedbackAnalysisPipeline()
        self._run = self._pipeline.run
        self._accepts_progress = "progress_cb" in inspect.signature(self._run).parameters
        self._status = "ready"
        self._info["device"] = getattr(self._pipeline, "device", None)

    def status(self) -> str:
        return self._status

    def info(self) -> dict[str, Any]:
        info = dict(self._info)
        if hasattr(self._pipeline, "sentiment"):
            info["backends"] = {
                "sentiment": getattr(self._pipeline.sentiment, "backend", None),
                "tier1": getattr(self._pipeline.topics, "tier1_backend", None),
                "tier2": list(getattr(self._pipeline.topics, "tier2_backends", []) or []),
                "embeddings": getattr(self._pipeline.embedder, "name", None),
                "llm_assist": (
                    self._pipeline.llm.provider
                    if getattr(self._pipeline.llm, "enabled", False)
                    else "off"
                ),
            }
        return info

    def analyze(self, df: pd.DataFrame, progress_cb: Optional[ProgressCb] = None) -> AnalysisResult:
        kwargs: dict[str, Any] = {
            "text_column": "review_text",
            "include_meta": True,
            "include_reviews": True,  # required by the backend contract
        }
        if self._accepts_progress and progress_cb is not None:
            kwargs["progress_cb"] = progress_cb
        try:
            payload = self._run(df, **kwargs)
        except EngineContractMismatch:
            raise
        except Exception as exc:
            log_event(log, "engine_error", exc_type=type(exc).__name__)
            raise
        if not isinstance(payload, dict) or "reviews" not in payload:
            raise EngineContractMismatch(
                "ENGINE_CONTRACT_MISMATCH: engine output is missing reviews[]."
            )
        return result_from_dict(payload)
