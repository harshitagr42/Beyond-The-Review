# Frontend

React + Vite dashboard for the Feedback & Review Analyzer.

## Run

The backend must be running at `http://127.0.0.1:8000` (see the repo root README).

```bash
cd frontend
npm install
npm run dev
```

Vite serves the app (port `3000`) and proxies `/api` to `http://127.0.0.1:8000` so the browser can call `/api/v1/...` without CORS issues.

## Environment

Copy `.env.example` to `.env` if you need to override the API base URL.

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | empty → `/api/v1` | Absolute API origin + path for production, or when not using the Vite proxy. Leave empty in development. |
