# Project Hermes (Local-First)

Dynamic skills and workforce intelligence prototype under **Project EVOLVE**.

Hermes turns ticket history, certifications, and manager-confirmed declared skills into a living, coded skills matrix. It ranks and explains staffing fit and learning gaps; managers always make the final call.

**Classification:** Internal, Confidential  
**Runtime:** Local-first (no Azure required)

**Full context pack:** see [PROJECT_BIBLE.md](PROJECT_BIBLE.md) (C-suite → DevOps → LLM handoff).

## Stack

| Concern | Technology |
|---------|------------|
| Judgment (identity, inference, fitness/gap, resolution) | Python packages in `src/` |
| HTTP API | FastAPI (`api/main.py`) |
| Skills matrix + audit ledger | SQLite (`data/hermes.db`) |
| Ingestion | Fixture CLI (`scripts/ingest_fixtures.py`) |
| Operator UI | Animated React console (`web/`) |
| Query CLI | `scripts/hermes_query.py` |

**Rules decide. Rules compute.** The UI/CLI never invent candidates.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m scripts.ingest_fixtures
uvicorn api.main:app --port 8000
```

### Animated frontend

```bash
cd web && npm install && npm run start:web
```

Open http://localhost:5173 (Staff / Learn / Matrix). Or build and serve from the API:

```bash
cd web && npm run build
uvicorn api.main:app --port 8000
```

Then open http://127.0.0.1:8000/

### CLI

```bash
python -m scripts.hermes_query staff --skills container_orchestration --level 3 --resolve
python -m scripts.hermes_query gaps E1003 --role senior_cloud_engineer
```

## MVP success criteria

| Metric | Target |
|--------|--------|
| Evidence coverage | ≥ 80% of pilot population |
| Identity leakage | Zero real names in core matrix |
| Ranking traceability | 100% evidence-linked |
| Query latency | ≤ 3 seconds |
| Matrix availability | Live on coded pilot data in SQLite |

Azure / Power Platform stubs remain for a future path — see [docs/future-azure.md](docs/future-azure.md).

### Auth (local)

`POST /api/auth/token` issues HS256 JWTs (local stub). API routes require `Authorization: Bearer <token>`. Set `HERMES_JWT_SECRET` and `IDENTITY_MAP_SECRET` (fail-closed outside `HERMES_TEST_MODE=1`).
