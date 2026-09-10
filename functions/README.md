# Legacy Azure Functions host

**Local-first Hermes uses FastAPI** in [`api/main.py`](../api/main.py).

```bash
uvicorn api.main:app --reload --port 8000
```

This `functions/` directory is retained only as a historical reference for a future Azure path. Do not deploy it for the local MVP.
