# API router split (2026-10-02)

## Why

`api/main.py` had grown to ~959 lines holding all 38 routes, every Pydantic request
model, every dependency, and the app/middleware/lifecycle setup in one file. A
developer opening the repo had no way to tell "where does this endpoint belong?"
without reading the whole file. This was a pure structural refactor — no endpoint,
schema, auth rule, or behavior was changed. See the route-parity proof below.

## Router ownership

| Router | Owns |
|---|---|
| `health.py` | `/health`, `/ready` |
| `auth.py` | `/api/auth/token`, `/api/session` |
| `skills.py` | `/api/skills`, `/api/skills/{id}`, `/api/roles`, `/api/taxonomy/pending`, `/api/taxonomy/aliases/{label}/resolve` |
| `people.py` | `/api/identities`, `/api/identity/directory`, `/api/identity/abstract`, `/api/me`, `/api/overview`, `/api/workforce`, `/api/dashboard`, `/api/org/bind-principal`, `/api/org/edges` |
| `requests.py` | `/api/staffing/requests`, `/api/staffing/requests/{id}`, `/api/staffing/{id}/decision` |
| `candidates.py` | `/api/fitness/rank`, `/api/fitness/gaps`, `/api/identity/resolve` |
| `evidence.py` | `/api/inference/merge`, `/api/ingest/tickets`, `/api/matrix/runs`, `/api/matrix/runs/{id}` |
| `data_quality.py` | `/api/data-quality`, `/api/baseline/matrix`, `/api/excel-sunset` |
| `certificates.py` | `/api/certs/pending`, `/api/certs/{id}/date`, `/api/certs/{id}/promote` |
| `team.py` | `/api/team/skill-review/{id}`, `/api/team/declare`, `/api/team/contests/{id}/resolve`, `/api/me/contest` |

`api/dependencies.py` holds `get_service`/`reset_service_for_tests` (the service
singleton and its test-reset hook), `require_api_key`/`get_principal`/`require_roles`
(auth), and the two per-action rate limiters (`RESOLVE_LIMITER`, `DECLARE_LIMITER`) —
co-located with the reset hook because `reset_service_for_tests` is the one place
that must reset all three together.

`api/validation.py` holds `SKILL_IDS`, `REQUEST_ID_PATTERN`, `CODED_ID_PATTERN`, and
the two validator functions — used by request models in six different routers, owned
by none of them, so it got its own file rather than an arbitrary home or a
`utils.py` grab-bag.

The suggested `audit.py`/`admin.py` from the brief were deliberately **not**
created: there is no dedicated audit-read route today, and "admin" isn't a
resource domain — every admin-gated route is grouped by what it operates on
instead (e.g. `/api/identity/abstract` is in `people.py`, not a generic admin
bucket). `team.py` was added despite not being in the suggested list because the
team skill-review/declare/contest workflow is a cohesive, self-contained feature
with its own body models and its own `_require_team_subject` guard.

## What stays in main.py

FastAPI app creation, CORS + security-headers middleware, the `_lifespan` secret
checks, the global `HermesError` exception handler, router registration
(`app.include_router(...)`), and the built-SPA static-file fallback (which must be
mounted last, after every API route, exactly as before).

## Behavior preservation — proof, not assertion

- **Route snapshot diff**: dumped every `app.routes` path+method before and after
  the split (`/tmp/routes_before.txt` / `/tmp/routes_after.txt`) — **byte-identical**,
  44 routes both times (38 app routes + SPA fallback + 5 FastAPI auto-routes).
- **One behavior bug caught and avoided before it shipped**: two Pydantic fields
  (`TaxonomyResolveBody.decision`, `ContestResolveBody.status`) were originally
  `Literal[...]`; my first draft of each router rewrote them as custom
  `field_validator`s, which would have changed the exact 422 error payload shape.
  Caught by re-reading against the original before writing, fixed to the verbatim
  `Literal` type.
- **One cross-module state bug caught and avoided**: `from api.dependencies import
  RESOLVE_LIMITER` in `candidates.py`/`team.py` would have bound a *copy* of the
  reference at import time, so `reset_service_for_tests`'s reassignment of
  `dependencies.RESOLVE_LIMITER`/`DECLARE_LIMITER` would never be observed by the
  routers that use them — silently breaking the test-isolation behavior the
  original single-module globals had for free. Fixed by importing the
  `dependencies` module and reading `dependencies.RESOLVE_LIMITER` at call time.
- **Auth/ownership**: every route keeps its exact `require_api_key` /
  `require_roles(...)` / ownership-check call, copied verbatim.

## Tests

- Backend: **400 passed** (unchanged from before the split).
- Coverage (gated packages, unaffected by this change since `api/` isn't in the
  gate): **92.36%**, gate 85% — unchanged.
- `api/` coverage (informational, not gated): every new module 87–100% covered
  by the existing API/security/guardrail test suite with zero new tests added —
  the split didn't need new tests because it changed no behavior.
- Frontend: **83 passed**, unchanged. The UI contract fixture did **not** need
  regeneration — confirms the API surface is genuinely unchanged.

## Technical debt discovered, intentionally not touched

- `api/dependencies.py` and several routers still do function-local
  `from shared import read_models` imports (matching the original main.py's
  style) rather than a module-level import — left as-is; not a router-ownership
  issue.
- `src/shared/db.py` (1,106 LOC) still mixes identity/evidence/audit/org/cert
  responsibilities in one class — out of scope for an *API* router split.
- No `tags=` metadata was added to the new `APIRouter()` instances. It would
  improve the generated `/docs` grouping for free, but the brief said not to
  change response/schema surface beyond what's required, and tags touch the
  OpenAPI schema — left out rather than risk scope creep.
