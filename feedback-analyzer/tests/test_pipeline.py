"""End-to-end test in lightweight fallback mode (no model downloads needed)."""
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.ml.config import Settings
from src.ml.pipeline import FeedbackAnalysisPipeline
from src.ml.sentiment_engine import percent_ints
from src.ml.validation_data import VALIDATION_SET

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sample_df(tmp_path_factory):
    out = tmp_path_factory.mktemp("data") / "sample.csv"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_sample_data.py"), "--rows", "600", "--out", str(out)],
        check=True,
        cwd=ROOT,
    )
    return pd.read_csv(out)


@pytest.fixture(scope="module")
def pipe(tmp_path_factory):
    s = dataclasses.replace(
        Settings.from_env(),
        enable_spacy_ner=False,
        enable_llm_assist=False,
        baseline_path=tmp_path_factory.mktemp("bl") / "baseline.npz",
    )
    return FeedbackAnalysisPipeline(s, force_fallback=True)


def test_validation_set_shape():
    assert len(VALIDATION_SET) == 100
    assert {r["sentiment"] for r in VALIDATION_SET} == {"Positive", "Neutral", "Negative"}
    assert len({r["category"] for r in VALIDATION_SET}) == 5


def test_percent_ints_sum_to_100():
    for counts in ([1, 1, 1], [25, 20, 55], [0, 0, 7], [333, 333, 334]):
        assert sum(percent_ints(counts)) == 100


def test_output_schema(pipe, sample_df):
    res = pipe.run(sample_df)
    assert set(res) >= {"summary", "sentiment_breakdown", "themes"}
    assert set(res["summary"]) == {
        "total_reviews", "overall_sentiment", "net_sentiment_score",
        "pii_redacted_count", "model_validation_accuracy", "drift_status",
    }
    assert res["summary"]["total_reviews"] == len(sample_df)
    assert res["summary"]["model_validation_accuracy"].endswith("%")
    assert res["summary"]["drift_status"].split(" ")[0] in {"Low", "Moderate", "High", "Baseline"}
    assert sum(res["sentiment_breakdown"].values()) == 100
    json.dumps(res)  # must be serialisable

    themes = res["themes"]
    assert themes and [t["count"] for t in themes] == sorted((t["count"] for t in themes), reverse=True)
    for t in themes:
        assert set(t) == {"id", "general_class", "name", "count", "sentiment", "sentiment_score", "sample_verbatims"}
        assert t["sample_verbatims"] and -1 <= t["sentiment_score"] <= 1
        assert t["sentiment"] in {"Positive", "Neutral", "Negative", "Strongly Negative"}
    assert sum(t["count"] for t in themes) <= len(sample_df)


def test_pii_never_reaches_output(pipe, sample_df):
    res = pipe.run(sample_df)
    blob = json.dumps(res)
    for secret in ("@example.com", "4111 1111", "123-45-6789", "192.168.1."):
        assert secret not in blob
    assert res["summary"]["pii_redacted_count"] > 0
    assert "[EMAIL_REDACTED]" in blob or "[PII_REDACTED]" in blob or "[PHONE_REDACTED]" in blob


def test_strict_schema_and_bad_input(pipe, sample_df):
    assert "meta" not in pipe.run(sample_df.head(80), include_meta=False)
    with pytest.raises(ValueError):
        pipe.run(pd.DataFrame({"wrong": ["x"]}))
    with pytest.raises(ValueError):
        pipe.run(pd.DataFrame({"review_text": ["", None, "   "]}))


def test_drift_baseline_lifecycle(tmp_path, sample_df):
    s = dataclasses.replace(
        Settings.from_env(), enable_spacy_ner=False, enable_llm_assist=False, baseline_path=tmp_path / "b.npz"
    )
    p = FeedbackAnalysisPipeline(s, force_fallback=True)

    first = p.run(sample_df)  # no baseline yet -> initialised from this batch
    assert first["summary"]["drift_status"] == "Baseline initialized"
    assert (tmp_path / "b.npz").exists()

    same = p.run(sample_df)  # identical data vs its own baseline
    assert same["summary"]["drift_status"].startswith("Low")
    assert same["meta"]["drift"]["psi"] < 0.05

    shifted = p.run(pd.DataFrame({"review_text": ["Invoice emailed after every payment."] * 60}))
    assert shifted["meta"]["drift"]["status"] in {"Moderate", "High"}  # very different distribution
