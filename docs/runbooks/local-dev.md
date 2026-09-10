# Local development runbook

```bash
pip install -e ".[dev]"
export IDENTITY_MAP_SECRET=local-dev-secret
export HERMES_DB_PATH=data/hermes.db
python -m scripts.ingest_fixtures
uvicorn api.main:app --reload --port 8000
```

Health check: `curl http://127.0.0.1:8000/health`

Optional API key: set `HERMES_API_KEY` and send header `x-api-key`.
