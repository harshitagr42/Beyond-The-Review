# Beyond the Review

A three-tier application that turns raw app-store / survey reviews into actionable insights:
PII-redacted verbatims, sentiment analysis, theme taxonomy, trend charts, and drift detection.

```
┌──────────┐  HTTP  ┌──────────────┐  in-process  ┌─────────────┐
│ frontend │ ◄────► │   backend    │ ◄──────────► │  ml-engine  │
│ (Vite)   │        │  (FastAPI)   │              │  (PyTorch)  │
└──────────┘        └──────────────┘              └─────────────┘
```

## Repository layout

| Folder | Description |
|---|---|
| `frontend/` | React + Vite web app |
| `backend/` | FastAPI REST API, job queue, SQLite storage |
| `ml-engine/` | Local NLP engine (PII, sentiment, themes, drift) |

## One-time setup

Python 3.11 is required. One virtual environment covers both `ml-engine` and `backend`.

```bash
# Create the venv at the repo root
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Install ML engine deps (torch, transformers, bertopic, …)
pip install -r ml-engine/requirements.txt

# Install backend deps
pip install -r backend/requirements.txt

# (Optional) spaCy NER model for name redaction
python -m spacy download en_core_web_sm

# Download the Hugging Face models once (~1.5 GB)
cd ml-engine
python scripts/download_models.py
cd ..

# Configure the backend
cp backend/.env.example backend/.env
# backend/.env ships with ML_ENGINE=local — no changes needed for the typical case.
```

> Once models are downloaded, add `HF_HUB_OFFLINE=1` to `backend/.env` to run fully offline.

## Running everything

Open **two terminal tabs** (both with the venv activated):

**Tab 1 — backend** (from `backend/`):

```bash
cd backend
source ../.venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Tab 2 — frontend** (from `frontend/`):

```bash
cd frontend
npm run dev
```

The app is then available at the URL printed by Vite (usually `http://localhost:5173`).  
API documentation: `http://localhost:8000/docs`.

> **Do not** start the backend with `--reload`. It would reload the ML models on every file change.

## Development with the mock engine

To run the backend without models (e.g. for frontend development or running the test suite):

```bash
# In backend/.env:
ML_ENGINE=mock
```

## Tests

```bash
# Backend (from backend/)
cd backend && pytest -q

# ML engine (from ml-engine/)
cd ml-engine && pytest -q
```

The backend test suite uses the mock engine by default. Pass `-m integration` to run the real engine tests.

## Components

- **[ml-engine/README.md](ml-engine/README.md)** – ML pipeline details, output schema, drift, PII, LLM assist
- **[backend/README.md](backend/README.md)** – Backend setup, env vars, test instructions
- **[backend/docs/API_CONTRACT.md](backend/docs/API_CONTRACT.md)** – Full REST API contract
