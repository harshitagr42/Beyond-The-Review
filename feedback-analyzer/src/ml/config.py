"""Central configuration. Everything is overridable via environment variables / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CATEGORIES: List[str] = [
    "Streaming/Playback",
    "Comments & Social",
    "Billing & Subscriptions",
    "Performance & Crashes",
    "UI/UX & Navigation",
]

# NLI zero-shot models work much better with a natural-language description
# than with a terse label such as "UI/UX & Navigation".
CATEGORY_DESCRIPTIONS: Dict[str, str] = {
    "Streaming/Playback": "video streaming and playback",
    "Comments & Social": "comments and social features",
    "Billing & Subscriptions": "billing, payments and subscriptions",
    "Performance & Crashes": "app performance, crashes and bugs",
    "UI/UX & Navigation": "user interface and navigation",
}


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = _env(name, "")
    if not raw:
        return list(default)
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass
class Settings:
    # hardware / mode
    device: str = "auto"
    ml_backend: str = "auto"  # auto | fallback

    # sentiment
    sentiment_backend: str = "auto"  # auto | roberta | vader
    sentiment_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    positive_threshold: float = 0.25
    negative_threshold: float = -0.25
    strong_negative_threshold: float = -0.60

    # tier 1
    tier1_backend: str = "auto"  # auto | zeroshot | keyword
    zero_shot_model: str = "cross-encoder/nli-deberta-v3-small"
    zero_shot_min_score: float = 0.30
    categories: List[str] = None  # type: ignore[assignment]

    # tier 2
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    tier2_backend: str = "auto"  # auto | bertopic | kmeans
    bertopic_min_docs: int = 300
    min_theme_size: int = 5
    max_subtopics_per_class: int = 8
    max_themes: int = 25
    samples_per_theme: int = 5

    batch_size: int = 32
    seed: int = 42

    # PII
    enable_spacy_ner: bool = False
    spacy_model: str = "en_core_web_sm"

    # drift
    baseline_path: Path = PROJECT_ROOT / "data" / "baseline_embeddings.npz"

    # optional LLM assist
    enable_llm_assist: bool = False
    llm_provider: str = "auto"  # auto | openai | huggingface
    llm_max_calls: int = 200
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    hf_token: str = ""
    hf_llm_model: str = "meta-llama/Llama-3.1-8B-Instruct"

    def __post_init__(self) -> None:
        if self.categories is None:
            self.categories = list(DEFAULT_CATEGORIES)

    @classmethod
    def from_env(cls) -> "Settings":
        baseline = Path(_env("BASELINE_PATH", str(PROJECT_ROOT / "data" / "baseline_embeddings.npz")))
        if not baseline.is_absolute():
            baseline = PROJECT_ROOT / baseline
        return cls(
            device=_env("DEVICE", "auto").lower(),
            ml_backend=_env("ML_BACKEND", "auto").lower(),
            sentiment_backend=_env("SENTIMENT_BACKEND", "auto").lower(),
            sentiment_model=_env("SENTIMENT_MODEL", cls.sentiment_model),
            positive_threshold=_env_float("POSITIVE_THRESHOLD", 0.25),
            negative_threshold=_env_float("NEGATIVE_THRESHOLD", -0.25),
            strong_negative_threshold=_env_float("STRONG_NEGATIVE_THRESHOLD", -0.60),
            tier1_backend=_env("TIER1_BACKEND", "auto").lower(),
            zero_shot_model=_env("ZERO_SHOT_MODEL", cls.zero_shot_model),
            zero_shot_min_score=_env_float("ZERO_SHOT_MIN_SCORE", 0.30),
            categories=_env_list("CATEGORIES", DEFAULT_CATEGORIES),
            embedding_model=_env("EMBEDDING_MODEL", cls.embedding_model),
            tier2_backend=_env("TIER2_BACKEND", "auto").lower(),
            bertopic_min_docs=_env_int("BERTOPIC_MIN_DOCS", 300),
            min_theme_size=_env_int("MIN_THEME_SIZE", 5),
            max_subtopics_per_class=_env_int("MAX_SUBTOPICS_PER_CLASS", 8),
            max_themes=_env_int("MAX_THEMES", 25),
            samples_per_theme=_env_int("SAMPLES_PER_THEME", 5),
            batch_size=_env_int("BATCH_SIZE", 32),
            enable_spacy_ner=_env_bool("ENABLE_SPACY_NER", False),
            spacy_model=_env("SPACY_MODEL", "en_core_web_sm"),
            baseline_path=baseline,
            enable_llm_assist=_env_bool("ENABLE_LLM_ASSIST", False),
            llm_provider=_env("LLM_PROVIDER", "auto").lower(),
            llm_max_calls=_env_int("LLM_MAX_CALLS", 200),
            openai_api_key=_env("OPENAI_API_KEY", ""),
            openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
            hf_token=_env("HUGGINGFACE_HUB_TOKEN", "") or _env("HF_TOKEN", ""),
            hf_llm_model=_env("HF_LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
        )
