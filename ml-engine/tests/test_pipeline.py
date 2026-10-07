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
    # Default output must NOT include reviews key
    assert "reviews" not in res
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
        assert set(t) == {
            "id", "general_class", "name", "count", "sentiment",
            "sentiment_score", "sample_verbatims", "representative_indices",
        }
        assert t["sample_verbatims"] and -1 <= t["sentiment_score"] <= 1
        assert t["sentiment"] in {"Positive", "Neutral", "Negative", "Strongly Negative"}
        # representative_indices must be valid 0-based positions within analysed rows
        n_analysed = res["summary"]["total_reviews"]
        for idx in t["representative_indices"]:
            assert 0 <= idx < n_analysed
        # number of representative_indices == number of sample_verbatims
        assert len(t["representative_indices"]) == len(t["sample_verbatims"])
    assert sum(t["count"] for t in themes) <= len(sample_df)


def test_reviews_list_invariants(pipe, sample_df):
    """When include_reviews=True the reviews list must satisfy all documented invariants."""
    res = pipe.run(sample_df, include_reviews=True)

    assert "reviews" in res
    reviews = res["reviews"]
    themes = res["themes"]

    # reviews length == total_reviews (analysed rows, not raw rows)
    assert len(reviews) == res["summary"]["total_reviews"]

    # every non-null theme_id must exist in themes
    theme_ids = {t["id"] for t in themes}
    for r in reviews:
        if r["theme_id"] is not None:
            assert r["theme_id"] in theme_ids, f"unknown theme_id {r['theme_id']!r}"

    # per-theme counts match
    theme_count: dict[str, int] = {}
    for r in reviews:
        if r["theme_id"] is not None:
            theme_count[r["theme_id"]] = theme_count.get(r["theme_id"], 0) + 1
    for t in themes:
        assert theme_count.get(t["id"], 0) == t["count"], (
            f"theme {t['id']}: expected count {t['count']}, got {theme_count.get(t['id'], 0)}"
        )

    # source_row values are unique and within the original DataFrame row range
    source_rows = [r["source_row"] for r in reviews]
    assert len(source_rows) == len(set(source_rows)), "source_row values are not unique"
    max_source_row = len(sample_df) - 1
    for sr in source_rows:
        assert 0 <= sr <= max_source_row

    # row values are sequential from 0
    assert [r["row"] for r in reviews] == list(range(len(reviews)))

    # output is still JSON-serialisable
    json.dumps(res)


def test_reviews_not_present_by_default(pipe, sample_df):
    """Without include_reviews the result must have no reviews key."""
    res = pipe.run(sample_df)
    assert "reviews" not in res


def test_progress_callback_stages(pipe, sample_df):
    """Progress callback must fire exactly (stage, 0.0) then (stage, 1.0) for each stage, in order."""
    expected_stages = ["pii_redaction", "sentiment", "embeddings", "topics", "validation", "drift"]
    calls: list[tuple[str, float]] = []

    def cb(stage: str, fraction: float) -> None:
        calls.append((stage, fraction))

    pipe.run(sample_df, progress_cb=cb)

    # Stages arrive in the documented order
    assert [s for s, _ in calls[::2]] == expected_stages, f"stage order: {calls}"
    # Each stage gets 0.0 then 1.0
    for i, stage in enumerate(expected_stages):
        assert calls[2 * i] == (stage, 0.0)
        assert calls[2 * i + 1] == (stage, 1.0)


def test_raising_callback_does_not_abort(pipe, sample_df):
    """A callback that raises must not stop the pipeline run."""
    def bad_cb(stage: str, fraction: float) -> None:
        raise RuntimeError("callback failure")

    result = pipe.run(sample_df, progress_cb=bad_cb)
    assert "summary" in result  # run completed


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
