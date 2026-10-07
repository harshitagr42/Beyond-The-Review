# Beyond the Review – Backend

FastAPI service that accepts CSV/Excel review files, runs them through the local ML engine (`../ml-engine/`),
stores the results in SQLite, and serves them through a REST API.

## Prerequisites

- Python 3.11 (arm64 native on Apple Silicon; verify with `python3 -c "import platform; print(platform.machine())"`)
- The ML engine at `../ml-engine/` (its Hugging Face models must be downloaded once first; see ml-engine/README.md)
- `npm` (for the frontend, see `../frontend/`)

## One-time setup

```bash
# From the repo root — one venv for both ml-engine and backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Install ML engine deps first (torch, transformers, bertopic …)
pip install -r ml-engine/requirements.txt

# Then install backend deps
pip install -r backend/requirements.txt

# Optional — download spaCy model for NER-based PII redaction
python -m spacy download en_core_web_sm

# Copy and edit the example env file
cp backend/.env.example backend/.env
# Edit backend/.env: set ML_ENGINE=local to use the real models
```

> After models are downloaded once, add `HF_HUB_OFFLINE=1` to `backend/.env` to prevent any accidental network access.

## Running

**Backend** — run from inside `backend/` (do NOT use `--reload`; it would reload the ML models on every code change):

```bash
cd backend
source ../.venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Frontend** — run from inside `frontend/`:

```bash
cd frontend
npm run dev
```

API docs are available at `http://localhost:8000/docs` once the backend is running.

## Running tests

```bash
# From backend/
cd backend
source ../.venv/bin/activate
pytest -q
```

The default test suite uses the `mock` engine — no model downloads needed. To run integration tests against the real engine:

```bash
pytest -q -m integration
```

## Environment variables

See [`.env.example`](.env.example) for a full list with comments.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `ML_ENGINE` | `local` | `local` = real FeedbackAnalysisPipeline; `mock` = no torch (tests/dev) |
| `ML_ENGINE_PATH` | `../ml-engine` | Path to the ml-engine folder (relative to `backend/`) |
| `DATA_DIR` | `./data_store` | Where SQLite DB and uploaded files are stored |
| `HF_HUB_OFFLINE` | _(unset)_ | Set to `1` after models are downloaded to run fully offline |
