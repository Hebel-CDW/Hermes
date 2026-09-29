# Hermes V2 — UI Integration Report

**Date:** 2026-09-17 · **Scoring config:** `5a35863a05c7` · **Status:** prototype on synthetic data, not production-ready. All work is uncommitted.

## 1. Screens implemented

| Route | Screen |
|---|---|
| `/login` | Demo principal sign-in (synthetic principals, `sub` only) |
| `/overview` | Workforce capability overview |
| `/workforce` | Capability topology and inspection ledger |
| `/skills` | Skills atlas and skill inspector |
| `/matrix` | Skill × coded-identity heatmap |
| `/requests` | Staffing request list |
| `/requests/:id` | Ranked shortlist, exclusions, identity resolution, decision |
| `/capability` | Find Capability (rank form) |
| `/capability/:id?request=` | Candidate detail; `&view=derivation` shows the score derivation |
| `/learning` | Gap analysis against governed role profiles |
| `/insights` | Domain capability, freshness, computation runs |
| `/profile` | Session identity, own evidence, contest |

The shell covers the sidebar, top bar, ⌘K search, activity menu, account menu, page transition and mobile drawer. Mapping to design files: `docs/HERMES_DESIGN_IMPLEMENTATION_MAP.md`.

## 2. API endpoints wired

**Existing endpoints:**
- `POST /api/auth/token`
- `GET /api/skills`, `GET /api/roles`, `GET /api/identities`
- `GET /api/dashboard`, `GET /api/matrix/runs`
- `POST /api/fitness/rank`, `POST /api/fitness/gaps`
- `POST /api/identity/resolve`
- `POST /api/staffing/{id}/decision`
- `GET /api/me`, `POST /api/me/contest`

**New read-only endpoints.** These were added because no endpoint listed requests, returned a stored ranking, or reported server-derived roles. None writes to the DB or the audit ledger, and none recomputes a score.
- `GET /api/session`
- `GET /api/overview`
- `GET /api/workforce`
- `GET /api/skills/{skill_id}`
- `GET /api/staffing/requests`
- `GET /api/staffing/requests/{id}`

`/api/fitness/rank` now stores its response verbatim, together with the requirements. Request detail, candidate detail and score derivation all render that stored payload. Scoring, fitness, identity resolution, ownership, RBAC, audit and the Phase 8 controls are unchanged.

## 3. Design assets used

- `precision_enterprise_minimal/DESIGN.md` is implemented in `web/src/styles/hermes.css`:
  - Inter font; crimson `#B5122B`
  - Hairline `#E5E7EB`, ink scale, tertiary teal
  - 4px/8px radii, uppercase labels, tabular numbers, 1.5px stroke icons
  - Gap tag colours; micro-shadows only
- `hermes_logo_mark` is redrawn as an inline SVG.
- Screen layouts follow `hermes_overview`, `hermes_workforce`, `hermes_skills`, `hermes_skill_matrix`, `hermes_requests`, `hermes_candidate_detail_candidate_0007_1/_2`, `hermes_score_derivation_candidate_0007`, `hermes_learning` and `hermes_insights`.
- Not used: the executive headshot and all photo avatars (coded identities only), plus the design's sample numbers, course modules and trend lines (no API source).

## 4. Mock data removed

- **Deleted:**
  - `web/src/pages/`: Entry, Staff, Learn, Matrix, Me, Constellation
  - `web/src/components/`: ShortlistReveal, SkillHeatmap, CoverageRing, GapCascade, ScoreMeter, NarrateBanner, BrandMark
  - `web/src/motion/presets.ts`, `web/src/styles/tokens.css`, `web/src/api/client.ts`
- **Removed:**
  - The route-based principal switching (`/me` → employee)
  - The decorative constellation view
  - The `framer-motion` dependency
  - The Syne and IBM Plex fonts
- No hardcoded figures remain. Missing data renders an empty state.

## 5. Data consistency checks

| Check | Method | Result |
|---|---|---|
| Candidate IDs in API order | Live: DOM vs `GET /api/staffing/requests/{id}` inside the browser | match |
| Fitness per candidate | same | match |
| Exclusion `coded_identity` + reason | same | match |
| Request ID | same | match |
| Token claims | decoded in browser | `sub`, `iat`, `exp` only; `localStorage` empty |
| `/api/me?coded_identity=<other>` as employee | live fetch | 200 for own identity `EMP-f232ab6e`; query ignored |
| Another manager opens the request | live UI | 403 `request_not_owned`, rendered |
| Repeat decision | live fetch | 409 `request_state_conflict` |
| Fitness, run id, config version, per-skill confidence/volume/freshness/adjacency/contribution | Vitest on real captured payloads (`scripts/export_ui_contract.py`) | equal |
| Unsorted payload stays unsorted | Vitest | payload order shown |
| Matrix cell level / empty cell | Vitest on the real `/api/dashboard` payload | equal |
| Fixture shape vs live API | `tests/api/test_ui_contract.py` | pass |

Live walkthrough on a fresh synthetic DB:

login → overview → workforce (select identity) → skills → find capability (role template) → rank → request → candidate → score derivation → excluded → resolve → decision → ownership 403 → employee profile → learning gaps.

Server log: 821 requests. The only 4xx responses were the two deliberate negative checks (403, 409). There were no 5xx responses and no console messages.

## 6. Tests added

**Frontend** (Vitest + Testing Library, jsdom; `npm test`): **60 tests** in 5 files.
- `http.test.ts`: status and governance-code messages, bearer-only headers, 401 sign-out signal.
- `app.test.tsx`: login sends only `sub`, role-gated navigation, employee guard, invalid session, 404, all 9 main routes render.
- `requests.test.tsx`:
  - List fields; API order and no re-sorting; exclusion reasons; no stored ranking; ownership 403.
  - Identity protected → resolved; resolve 401/403/429.
  - Shortlist-only decision body with no owner or approver; decision 403/409/422 ×2; decided state.
  - Rank body; rank 409.
- `scoring.test.tsx`: candidate fitness, every derivation operand, excluded candidate reason, missing request context, no stale state when switching candidates while a slow response is in flight.
- `views.test.tsx`: overview values, empty/500/503/404/loading states, workforce selection, skills atlas, matrix levels and empty cells, profile with no identity parameter, learning with no invented courses.

**Backend:**
- `tests/api/test_read_models.py` (13 tests): RBAC, no audit side effects, verbatim stored result, owner scoping, server-derived session.
- `tests/api/test_ui_contract.py` (3 tests): fixture shape and ranking vs the live API; no secrets, names or tokens in the fixture.

**CI:** a `Test web` step was added after `Build web`.

## 7. Build result

| Command | Result |
|---|---|
| `python -m pytest -q -p no:cacheprovider` | **317 passed**, coverage **91.97%** (gate 85%) |
| `python -m scripts.demo_svp --verify` (run twice) | DETERMINISM OK + SAFEGUARDS OK, both runs |
| `cd web && npx tsc --noEmit -p tsconfig.app.json` | pass |
| `npm run build` | pass: JS 249.9 kB (75.2 kB gzip), CSS 20.4 kB |
| `npm test` | 60 passed |
| Responsive check (1440/1280/1024/768/390, all routes) | 75 route × width renders with no horizontal overflow and no error state |

## 8. Security scan result

Scanned `web/dist` and `web/src` (40 files):
- **JWTs:** 0
- **Secret names** (`IDENTITY_MAP_SECRET`, `HERMES_JWT_SECRET`, published test secrets): 0
- **Sensitive paths:** `identity_vault` 0, `hermes_phase8` 0, workbook references 0
- **Client labels:** 0 of 12
- **Real names:** 0 of 274 multi-word real names (loaded read-only in memory from the quarantined DB; only counts printed)
- **One match:** `password`, from React DOM's built-in input-type table, not app code.

The token lives in `sessionStorage`; nothing else is persisted. Resolved names are held in component state only.

## 9. Known limitations

- **Fixture keys in evidence ids.** Stored rankings include `evidence_ids`/`source_refs` that embed synthetic fixture keys (e.g. `decl-E1001`). They can be seen in the collapsed raw-payload panel and the JSON export. This comes from the existing backend payload; the UI no longer renders the free-text reasoning strings.
- **Placeholder values in the resolve response.** `POST /api/identity/resolve` returns placeholder `rank`/`fitness_score` values; the UI uses only `display_name`. Resolved names are gone after a reload (by design).
- **Old requests.** Requests ranked before `result_json` existed show "No stored ranking" until re-ranked.
- **No API source for:** trends/velocity, a learning catalogue, notifications (activity shows audit event types only), or period/business-unit filters. These show empty states or are left out.
- **Admin access.** Administrators have no request pages: the request endpoints are owner-manager only.
- **Browser verification** was a scripted Chrome DevTools session plus iframe width sweeps, not a committed end-to-end suite. Screenshots were reviewed at 1440px and 390px only.
- **Font loading.** Inter loads from Google Fonts; offline it falls back to system fonts.
- **Auth.** Demo auth is local only (no identity provider).
- **Status.** Synthetic data only; everything is uncommitted; not production-ready.
