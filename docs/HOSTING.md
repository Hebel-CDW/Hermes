# Hosting Hermes

**Short answer:** the app is packaged for a single container and is safe to host **as a synthetic-data demo behind company sign-in**. It is **not** ready for real employee data or open internet access until the items under "Before real users" are done. They are few and well-located.

## What is verified, and what is not

| Item | Status |
|---|---|
| One-command local run (`scripts/run_demo.sh`) | Verified: built, seeded, 55/55 self-check, clean reset |
| App runs from a clean tree with **only** the files the Dockerfile copies, strong secrets, **no test mode** | Verified by simulation: boots, seeds, serves, 55/55 |
| Refuses to start without strong secrets | Verified (exit code 3, clear message) |
| `HERMES_ENV=production` closes the demo sign-in, sends HSTS, honours `HERMES_CORS_ORIGINS` | Verified and covered by automated tests |
| Security headers, `/health`, `/ready` probes | Verified and covered by automated tests |
| `docker compose build` + `docker compose up` (api + ollama) | **Verified 2026-10-02**: real build, both containers healthy, `GET /ready` 200, full `scripts.live_smoke` (62/62) passed against the running container, `docker compose down -v` left no residue. |
| Behaviour under multiple users or replicas | Not tested |

## Option A: Docker Compose (simplest)

```bash
cp .env.example .env   # fill in IDENTITY_MAP_SECRET / HERMES_JWT_SECRET; OLLAMA_MODEL optional
docker compose up -d
curl http://localhost:8000/ready        # {"status":"ready"}
python -m scripts.live_smoke --base http://localhost:8000
```

Brings up the API (which already bundles the built React UI in the same
container — one port, not two) plus a local Ollama for `/api/requests/parse`.
Leaving `OLLAMA_MODEL` unset in `.env` is fine: that one endpoint answers
`{"available": false, ...}` and every other route is unaffected (see
`docs/HERMES_V3_ARCHITECTURE.md`).

## Option B: plain container

```bash
docker build -t hermes .
docker run -d --name hermes -p 8000:8000 -v hermes-data:/data \
  -e HERMES_ENV=local -e HERMES_DEMO_SEED=1 \
  -e IDENTITY_MAP_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" \
  -e HERMES_JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" \
  hermes
curl http://localhost:8000/ready        # {"status":"ready"}
python -m scripts.live_smoke --base http://localhost:8000
```

Keep the two secrets in your platform's secret store; the same values must be used on every restart, or the database's identity fingerprint will no longer match and `/ready` will return 503.

## Option C: a VM

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install .
(cd web && npm ci && npm run build)
export HERMES_DB_PATH=/var/lib/hermes/hermes.db IDENTITY_MAP_SECRET=... HERMES_JWT_SECRET=...
python -m scripts.ingest_fixtures            # demo data only
uvicorn api.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```

Put TLS and company sign-in in front (nginx, Caddy, or your platform's ingress).

## Environment

See `.env.example` for the full annotated list. The ones that matter:

| Variable | Purpose |
|---|---|
| `IDENTITY_MAP_SECRET`, `HERMES_JWT_SECRET` | **Required.** Strong, unique, at least 16 chars. The app refuses to start otherwise. |
| `HERMES_DB_PATH` | SQLite file. Keep it on a persistent volume, together with its `.audit-anchor.json`. |
| `HERMES_ENV` | `local` keeps the demo sign-in; `production` disables it (see below). |
| `HERMES_CORS_ORIGINS` | Only needed if the UI is served from a different origin than the API. Default setup needs nothing. |
| `HERMES_DEMO_SEED=1` | Container only: seed the synthetic demo database on first start of an empty volume. |
| `PORT` | Container listen port (default 8000). |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Optional. Power only `POST /api/requests/parse`. Unset means that one endpoint answers "unavailable" — nothing else is affected, by design. |

**Traps found while preparing this:**

- `HERMES_HALF_LIFE` was removed. Setting it makes the app refuse to start. The old `.env.example` set it; it is fixed and now covered by a test.
- Do **not** set `HERMES_API_KEY` for the bundled UI. When set, every API call must send `X-API-Key`, which the UI never does, so every screen would return 401.
- The demo sign-in has no password. With `HERMES_ENV=local`, anyone who can reach the URL can sign in as a manager or admin. **A hosted demo must sit behind SSO, a VPN, or at least basic auth at the edge.**

## Before real users (the few changes)

1. **Real sign-in — DONE as of 2026-10-02.** Set `AUTH_MODE=production` plus `OIDC_ISSUER`/`OIDC_AUDIENCE`/`OIDC_CLIENT_ID` (see `.env.example`). This hard-disables the demo registry (regardless of `HERMES_ENV`) and validates real OIDC tokens — signature via the IdP's own published JWKS (standard discovery, not a guessed URL), plus issuer/audience/expiry. The app refuses to even *start* with `AUTH_MODE=production` and no OIDC config, same fail-closed policy as the two secrets above. Role claims are mapped conservatively: a value that isn't exactly `employee`/`manager`/`admin` is dropped, never granted. Verified end-to-end against a real local OIDC provider (real RSA keypair, real JWKS-over-HTTP, real signed RS256 tokens) in `tests/unit/test_oidc_auth.py` and `tests/api/test_production_auth.py` — **not verified against a live Microsoft Entra ID tenant**, since none is available in this environment; the validation logic is IdP-agnostic standard OIDC, but confirm interoperability against your actual tenant before relying on it. A sign-in's OIDC `sub` still needs linking to a coded identity via the existing `POST /api/org/bind-principal` (unchanged from before).
2. **Database.** SQLite is a single-writer file. Run **one** instance with a persistent volume and backups. Moving to a managed database means changing `src/shared/db.py` and the schema in `infra/sqlite/`.
3. **Rate limits are per process.** `src/shared/rate_limit.py` keeps counters in memory, so several workers or replicas each get their own allowance. Fine for one instance.
4. **Real employee data.** Do not load it into a hosted demo. Real-data mode has its own guardrails (strong secrets, coded identities, no test mode) and its own runbook: `docs/HERMES_REAL_DATA_INTEGRATION.md`. The Docker image intentionally excludes `secrets/`, `data/real/`, `data/source/`, all `*.xlsx`, and `config/client_names.txt`.
5. **Observability.** Only uvicorn access logs exist. Add log shipping and an alert on `/ready` returning non-200 (it also fails if the audit chain no longer verifies).
6. **Session storage.** The sign-in token lives in the browser's `sessionStorage` with a one-hour lifetime. Acceptable for a demo; revisit when real sign-in is added.
7. **LLM assist privacy.** `POST /api/requests/parse` sends only the manager's own typed free-text description to Ollama — no employee PII, no coded identities, no evidence. If Ollama is later moved to a hosted/enterprise endpoint, confirm that endpoint's own data-handling terms before pointing production at it; the `LLMProvider` boundary (`src/ai/provider.py`) makes that swap a config change, not a code change.

## Health checks

| Endpoint | Meaning |
|---|---|
| `GET /health` | Process is up. Use as the liveness probe. |
| `GET /ready` | Database opens, passes the trust policy, and the tamper-evident audit chain verifies. Use as the readiness probe. Returns 503 with a reason otherwise. |
