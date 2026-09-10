# Hermes Web Console

Highly animated operator UI (Vite + React + TypeScript + Framer Motion).

## Develop

Terminal 1 — API (ingest first if needed):

```bash
cd ..
source .venv/bin/activate
python -m scripts.ingest_fixtures
uvicorn api.main:app --reload --port 8000
```

Terminal 2 — UI:

```bash
npm install
npm run start:web
```

Open http://localhost:5173 — Vite proxies `/api` to the FastAPI backend.

## Production-local

```bash
npm run build
uvicorn api.main:app --port 8000
```

## Screens

- `/` Entry — brand-first animated hero
- `/staff` Rank + resolve shortlist
- `/learn` Demand-ranked skill gaps
- `/matrix` Coverage / freshness / heatmap (coded IDs only)
