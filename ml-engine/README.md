# Feedback & Review Analyzer – local NLP engine

Local-first Python service that turns a batch of raw app reviews (CSV / Excel / DataFrame) into
backend-ready JSON: PII-redacted verbatims, a two-tier theme taxonomy with review counts, sentiment
(polarity, labels, Net Sentiment Score), a validation accuracy figure and a drift score.

No training. No mandatory paid APIs. Runs on Apple Silicon via PyTorch MPS (CPU/CUDA also work).

```
reviews ─► PII sanitizer ─► sentiment ─┐
              │                        ├─► themes + summary JSON
              └─► embeddings ─► Tier 1 zero-shot ─► Tier 2 clustering ─┘
                         └──────────────► drift (PSI) ;  validation set ─► accuracy
```

| Module | What it does |
|---|---|
| `src/ml/pii_sanitizer.py` | Regex (+ optional spaCy PERSON NER) redaction of emails, phones, credit cards (Luhn-checked), SSNs, IPs → `[EMAIL_REDACTED]` `[PHONE_REDACTED]` `[PII_REDACTED]`; running tally per run |
| `src/ml/topic_extractor.py` | Tier 1: zero-shot (`cross-encoder/nli-deberta-v3-small`) into 5 default classes. Tier 2: BERTopic (≥300 reviews in a class) or k-means on embeddings, named with c-TF-IDF key phrases; similar verbatims grouped, counts per sub-issue |
| `src/ml/sentiment_engine.py` | `cardiffnlp/twitter-roberta-base-sentiment-latest` (polarity = P(pos) − P(neg)), VADER fallback; labels Positive / Neutral / Negative / Strongly Negative; NSS = %pos − %neg |
| `src/ml/drift_validator.py` | Accuracy on the embedded 100-row set; PSI drift against a saved baseline |
| `src/ml/pipeline.py` | Orchestration + CLI |
| `src/ml/llm_assist.py` | Optional, off by default (see below) |

## Setup (macOS, Apple Silicon)

```bash
cd ml-engine
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download en_core_web_sm      # only needed if ENABLE_SPACY_NER=true
cp .env.example .env                         # optional; defaults work
```

Use a native arm64 Python (`python3 -c "import platform; print(platform.machine())"` must print `arm64`).
An x86/Rosetta Python installs a PyTorch build without MPS.

## Run

```bash
python scripts/make_sample_data.py --rows 2000 --out data/sample_reviews.csv   # demo data (with fake PII)
python -m src.ml.pipeline --input data/sample_reviews.csv --output output/analysis.json -v
```

Useful flags: `--device mps|cpu`, `--fallback` (skip all transformer models: VADER + keyword Tier 1),
`--sheet NAME` (Excel), `--text-column`, `--strict-schema` (omit the extra `meta` block),
`--save-baseline` (see Drift). The first run downloads the Hugging Face models (roughly 1–1.5 GB in total) once;
afterwards set `HF_HUB_OFFLINE=1` to run fully offline.

From Python:

```python
import pandas as pd
from src.ml.pipeline import FeedbackAnalysisPipeline
pipe = FeedbackAnalysisPipeline()                    # loads models once, reuse across batches
result = pipe.run(pd.read_csv("reviews.csv"))        # columns: review_text, date, rating (date/rating optional)
```

## Verify MPS

```bash
python -m src.ml.device
```

You want `"mps_built": true`, `"mps_available": true`, `"selected_device": "mps"`,
`"matmul_matches_cpu": true` and the line `OK: PyTorch MPS acceleration is active.`

Then confirm the real pipeline uses it:

```bash
python -m src.ml.pipeline --input data/sample_reviews.csv -v 2>&1 | grep -i "device"   # "Device: mps"
```

and in the output JSON check `meta.device == "mps"`. While it runs, Activity Monitor → Window → GPU History
should show activity. If MPS is unavailable the pipeline silently runs on CPU (same results, slower).
`PYTORCH_ENABLE_MPS_FALLBACK=1` is set automatically so ops MPS doesn't implement fall back to CPU; if a model
still errors on MPS the engine retries that model on CPU and records it in `meta.warnings`.

## Output

Exactly the schema from the spec (`summary`, `sentiment_breakdown`, `themes`), plus a top-level `meta`
block (devices, backends used, timings, PII breakdown by type, validation + drift details, warnings).
Pass `--strict-schema` / `include_meta=False` to drop it.

Definitions worth knowing:

- `pii_redacted_count` counts redacted **entities** (one per replaced span), not words.
- `sentiment_breakdown` are integer percentages summing to 100; "negative" includes Strongly Negative.
- `net_sentiment_score` = % Positive − % Negative; `overall_sentiment` is "Negative Trend" at ≤ −10,
  "Positive Trend" at ≥ +10, else "Mixed Trend".
- A theme's `sentiment_score` is the mean polarity of its reviews; `sample_verbatims` are the reviews closest
  to the cluster centre (PII already redacted). `themes` are sorted by `count`, capped at `MAX_THEMES`.
- Reviews the zero-shot model is unsure about (< `ZERO_SHOT_MIN_SCORE`) land in an `Other` class.
- The `rating` column is parsed and averaged into `meta` but does not influence scoring.

## Validation accuracy

`model_validation_accuracy` = mean of (3-class sentiment accuracy, Tier-1 category accuracy) on the embedded
100-row set (`src/ml/validation_data.py`; 20 per class, hand-written). Per-task numbers are in
`meta.validation`. This set is small and synthetic: use it to catch broken installs and regressions, not as an
estimate of accuracy on your real reviews. For that, replace it with a sample of your own labelled reviews.

## Drift

PSI is computed on the distribution of cosine similarity to the baseline centroid (decile bins from the
baseline); `meta.drift` also has the centroid cosine distance. < 0.10 Low, < 0.25 Moderate, otherwise High.

The baseline is a saved `.npz` of embeddings (`BASELINE_PATH`). **If none exists, the first batch you analyze
becomes the baseline** and the status reads `Baseline initialized`; later batches are compared against it. To
reset it from a period you consider healthy: `--save-baseline`. A baseline is tied to the embedding model that
made it; if you change `EMBEDDING_MODEL` (or run `--fallback` against a model-built baseline) drift reports
`Unavailable` until you save a new one.

## Optional LLM assist (off by default)

Set `ENABLE_LLM_ASSIST=true` plus `OPENAI_API_KEY` (`pip install openai`) or `HUGGINGFACE_HUB_TOKEN`.
It (a) classifies reviews the zero-shot model is unsure about and (b) rewrites cluster names as readable titles.
Only PII-redacted text is sent, and calls are capped by `LLM_MAX_CALLS`. `HUGGINGFACE_HUB_TOKEN` is also picked
up by `huggingface_hub` for authenticated model downloads even with LLM assist off.

## Tests

```bash
pytest -q     # 13 tests; the pipeline test runs in --fallback mode so it needs no model downloads
```

## Known limitations

- Theme names without an LLM are keyword phrases (e.g. "Charged Twice Monthly Subscription"), not polished sentences.
- Tier 2 clusters mix praise and complaints about the same feature unless the embedding model separates them.
- The `--fallback` path (VADER + keyword Tier 1 + hashed vectors) is for smoke tests and offline emergencies;
  VADER in particular under-detects technical complaints ("crashes after the splash screen" scores neutral).
- Reviews are assumed to be English.
