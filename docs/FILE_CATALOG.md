# File Catalog — Project Hermes V2

**Classification:** Internal, Confidential
**Verified against:** the tree on 2026-09-15.

Answers: *why does this file exist, and what breaks without it?*

**Security column legend**
🔴 handles real identities or secrets · 🟠 enforces a guardrail · 🟡 reads confidential source data · ⚪ no direct exposure

---

## 1. Judgment core — `src/`

These five packages are the system. Everything else is ingestion, transport, or documentation.

| File | Purpose / why it exists | Inputs | Outputs | Depends on | Sec |
|---|---|---|---|---|---|
| `identity_abstraction/gate.py` | **Sole ingress.** Turns a raw record into `EMP-`+8hex and strips PII, so no downstream component can see a name. Also hosts the recursive leakage scanner. | raw record mapping, `IDENTITY_MAP_SECRET` | `AbstractionResult`, leakage findings | `shared.models` | 🔴🟠 |
| `skill_inference/engine.py` | Converts evidence into one scored `SkillRecord` per (person, skill): level, confidence, volume, freshness. The freshness-applied-once rule lives here. | `EvidenceRecord[]`, taxonomy, config | `SkillRecord[]` | `shared.config`, `shared.taxonomy` | ⚪ |
| `fitness_gap/engine.py` | Ranks candidates and computes gaps. Owns exclusion rules, adjacency, the shortlist cap, and the calculation inspector payload. | `SkillRecord[]`, `StaffingRequest`, allocation, adjacency | `FitnessResult`, `GapResult` | `shared.audit`, `shared.config`, `shared.models` | 🟠 |
| `identity_resolution/gateway.py` | The **only** path from coded token back to a name. Enforces requester ownership and shortlist membership, and audits every reveal. | shortlist, requester id, owner id | `[{coded_identity, display_name}]` | `identity_abstraction.gate`, `shared.audit` | 🔴🟠 |
| `shared/models.py` | Domain types + the two forbidden-field frozensets. Fairness is enforced here by *absence*: there is no field to put an age or gender in. | — | pydantic models, `PROTECTED_ATTRIBUTE_FIELDS`, `IDENTITY_PII_FIELDS`, exclusion sets | pydantic | 🟠 |
| `shared/config.py` | Scoring constants, and `version` as a **hash of the values**. Makes "which config produced this score?" answerable. | env overrides | `ScoringConfig` | — | ⚪ |
| `shared/db.py` | All SQLite access, schema migration, audit hash-chaining, matrix history. Single persistence chokepoint. | schema DDL, records | rows, chain hashes | `shared.models` | 🔴 |
| `shared/service.py` | Application wiring: abstraction → inference → matrix → ranking → decisions → `/me`. Where a run id is minted. | DB, secret | orchestrated results | all engines | 🔴 |
| `shared/audit.py` | Append-only ledger façade over memory + SQLite. | event type, actor, payload | `AuditEvent` | `shared.db` | 🟠 |
| `shared/auth.py` | HS256 JWT issue/verify → `AuthPrincipal`. **Prototype stub**, replaceable by OIDC/Entra. | `HERMES_JWT_SECRET` | token / principal | PyJWT | 🔴 |
| `shared/secrets.py` | Fail-closed secret validation. `require_real_data_ingest_secret()` refuses to tokenise real people in test mode. | env | validated secret or `RuntimeError` | — | 🔴🟠 |
| `shared/org.py` | Gaps ACL — self / direct report / admin. Stops gap browsing across the org. | principal, subject, `org_edges` | bool / raises | `shared.auth` | 🟠 |
| `shared/rate_limit.py` | In-memory sliding window; caps identity resolution at 10/min/principal. | key | bool | — | 🟠 |
| `shared/exclusions.py` | Classifies a workbook column as `skill` \| `account` \| `excluded`; **raises** on `culture fit`. Writes the exclusion log. | column label, sheet | classification + `phase8_exclusions.json` | `shared.models` | 🟠🟡 |
| `shared/taxonomy.py` | Loads/validates the ontology; keyword matching; decay-class half-life table. | `skills_ontology.yaml` | `SkillsTaxonomy`, validation errors | PyYAML | ⚪ |
| `shared/demand.py` | Demand-signal interface + fixture/ticket-volume sources. **Aspirational** — 0% coverage, no production caller. | counts | weights | — | ⚪ |

## 2. Phase 8 — real workbook parsing — `src/phase8/`

Deliberately a separate package: it must be impossible to reach the scoring path from here.

| File | Purpose / why it exists | Inputs | Outputs | Sec |
|---|---|---|---|---|
| `workbook.py` | openpyxl helpers, label normalisation, `slug_skill_id`, header detection, group-average and fractional-value predicates. Shared vocabulary for all parsers. | `.xlsx` | normalised strings, rows | 🟡 |
| `parsers.py` | Sheet-shape dispatch (`Collab` transposed vs people-as-rows) producing `ParsedAssessment` / `DroppedRow`. One table, not 22 copies. | sheet rows, `ExclusionLog` | assessments, drops | 🟡 |
| `normalize.py` | The **only** place a raw rating becomes a 1–5 level. `0.0 → NULL`; Collab 1–4 → 1,2,4,5. Isolated so the mapping can be revised without re-ingesting raw values. | raw value, scale | level or `None` | 🟠 |
| `aliases.py` | Governed label→skill resolution. Refuses to fuzzy-match; unknown labels are persisted as `pending`. The reason 12,697 rows are unmapped. | raw label, ontology, `skill_aliases` | `AliasResolution` | 🟠 |

## 3. HTTP surface — `api/`

| File | Purpose | Inputs | Outputs | Sec |
|---|---|---|---|---|
| `main.py` | FastAPI app: auth stub, dashboard, skills/roles/identities, matrix runs, abstract, merge, rank, gaps (ACL), resolve (rate-limited), decision, `/me`, contest, and the contained SPA fallback. | HTTP + JWT | JSON / static files | 🔴🟠 |

> `_safe_static_candidate` exists solely because the SPA fallback is unauthenticated: it
> resolves and containment-checks every path so `web/dist` cannot be escaped
> (`tests/security/test_spa_path_traversal.py`).

## 4. Scripts — `scripts/`

| File | Purpose / why it exists | Outputs | Sec |
|---|---|---|---|
| `ingest_fixtures.py` | Track A ingest: synthetic pilot → identity gate → inference → matrix. The CI and demo data source. | `hermes.db`, `coded_matrix_sample.json` | ⚪ |
| `hermes_query.py` | CLI for staff/gaps — proves the engine is usable without the UI. | narrated text / JSON | 🔴 (`--resolve`) |
| `narrate.py` | Narrate-**only** formatter + `assert_grounded_staffing`. Enforces "rules decide, language describes": refuses to print a candidate lacking evidence. | text | 🟠 |
| `dashboard_export.py` | Static coded-only HTML/JSON dashboard (Power BI stand-in); asserts no name fields. | `data/reports/dashboard.*` | 🟠 |
| `leakage_audit.py` | CI gate: scans the exported matrix for PII, emails, blocklisted names, client labels. | pass/fail + findings | 🟠 |
| `fairness_audit.py` | CI gate: greps the SQL schema for protected-attribute column names. Fairness by *schema absence*. | pass/fail | 🟠 |
| `impact_audit.py` | HR-held bias metric: Gini concentration of shortlist appearances + never-shortlisted cohort. Explicitly outside the scoring path. | `docs/validation/impact-audit-latest.json` | 🟠 |
| `verify_audit_chain.py` | CI gate: replays `prev_hash`/`row_hash`. | pass/fail | 🟠 |
| `coverage_report.py` | Pilot demonstrated-evidence coverage vs the ≥80% MVP criterion. | JSON, exit code | ⚪ |
| `seed_local_matrix.py` | Thin convenience wrapper over `ingest_fixtures`. Redundant. | — | ⚪ |
| `validation_keyword_precision.py` | Keyword precision on held-out fixture tickets. | `docs/validation/keyword-precision*` | ⚪ |
| `validation_manager_agreement.py` | Engine vs 30 recorded manager decisions. | `docs/validation/manager-agreement*` | ⚪ |
| `phase8/extract_labels.py` | Workstream A: extract + cluster all 752 workbook labels into `candidate_skills.csv` **as proposals**. Never writes the ontology. | CSV + report | 🟡 |
| `phase8/ingest_baseline.py` | Workstream B: workbook → `baseline_assessments` + `account_context`. Fails closed on test-mode secrets. | reports, DB rows | 🔴🟡 |
| `phase8/ingest_certificates.py` | Workstream C: Certificates sheet → `cert_staging` with `earned_at=NULL`, plus `cert_date_request.csv` for humans. | CSV, DB rows | 🔴🟡 |
| `phase8/promote_certs.py` | Promotes only human-dated cert rows into certified evidence. | report | 🟠 |
| `phase8/baseline_agreement.py` | Workstream E: the **only** consumer of baseline data — compares it with the engine offline. | `baseline_agreement.{json,md}` | 🟠 |
| `phase8/generate_template_v2.py` | Builds the v2 collection workbook from the ontology + 2025 team list. | `Hermes_Skills_Collection_Template_v2.xlsx` | ⚪ |

## 5. Tests — `tests/`

| Path | What it protects |
|---|---|
| `conftest.py` | Shared fixtures; sets test-mode secrets |
| `unit/test_scoring_golden.py` | **Exact** scores + config-hash faithfulness (C-3 regression) |
| `unit/test_scoring_inspector.py` | Inspector completeness; score recomputable from payload alone |
| `unit/test_skill_inference.py`, `test_decay_and_adjacency.py` | Merge, per-skill decay, adjacency discount |
| `unit/test_fitness_gap.py` | Ranking order, shortlist cap, coverage floor, gap priority |
| `unit/test_identity_*.py`, `test_gate_collisions_and_export.py` | Tokenisation, resolution, collisions |
| `unit/test_declared_unconfirmed_skipped.py` | Unconfirmed declared evidence never scores |
| `unit/test_narrate_grounding.py` | Narration cannot invent candidates |
| `unit/test_audit.py`, `test_taxonomy*.py` | Ledger, ontology completeness |
| `guardrails/test_baseline_isolation.py` | **Load-bearing:** baseline cannot move results |
| `guardrails/test_account_context_isolation.py` | Client familiarity cannot move results |
| `guardrails/test_soft_skill_exclusion.py` | Soft skills excluded; culture fit raises |
| `guardrails/test_client_blocklist.py` | Account labels never become skills |
| `security/test_tier0.py` | Nested PII, email leakage, token stability, no ticket excerpts, fail-closed secrets |
| `security/test_spa_path_traversal.py` | **C-1 regression:** unauthenticated file read |
| `api/test_api.py`, `test_frontend_endpoints.py` | Rank/resolve/ACL/decision lifecycle; coded-only dashboard |
| `integration/`, `e2e/` | Worked examples end to end; latency and coverage |
| `validation/test_validation_gates.py` | Keyword precision, 30 manager decisions, cold-start invisibility |
| `phase8/*` | Label membership, alias pending/approved, normalisation, NULL cert dates, template round-trip |

## 6. Data — `data/`

| Path | Classification | Committed? | Why |
|---|---|---|---|
| `fixtures/pilot_population.json` | **SYNTHETIC** | yes | Deterministic CI + demo input |
| `fixtures/validation/*.json` | **SYNTHETIC** | yes | Held-out tickets, 30 manager decisions |
| `fixtures/coded_matrix_sample.json` | **SYNTHETIC** | yes | Leakage-audit target |
| `source/*.xlsx` | **REAL** | **no** (gitignored) | Confidential 2025 workbook |
| `hermes.db` | SYNTHETIC | no | Pilot runtime DB |
| `hermes_phase8.db` | **REAL** (310 identities + vault names) | **no** | Baseline runtime DB |
| `phase8/candidate_skills.csv` | derived from REAL, **redacted** | yes | Governance proposals for human curation |
| `phase8/cert_date_request.csv` | **REAL** | **no** (example committed) | Human date-completion worksheet |
| `phase8/manager_variants.csv` | **REAL** | **no** (example committed) | Manager spelling proposals |
| `phase8/team_variants.csv` | team names only | yes | Team spelling proposals |
| `reports/*` | derived | no | Regenerated by scripts |

## 7. Taxonomy, schema, config

| Path | Purpose | Sec |
|---|---|---|
| `taxonomy/skills_ontology.yaml` | The 5-skill canonical ontology: 5 behavioural levels, keywords, cert codes, relations, decay classes. Changing it invalidates scores. | ⚪ |
| `infra/sqlite/001_schema.sql` | **Executed** schema; comment asserts no protected attributes; `fairness_audit` scans it. | 🟠 |
| `infra/sql/001_schema.sql` | Azure SQL variant — **not executed**; drift risk. | ⚪ |
| `config/client_names.txt` | Real account blocklist. | 🔴 **gitignored** |
| `config/client_names.example` | Shape reference. | ⚪ |
| `pyproject.toml` | Deps, console scripts, pytest + coverage gate. | ⚪ |
| `setup.cfg` | **Stale duplicate** of packaging; omits PyJWT/openpyxl. Should be deleted. | ⚪ |
| `.github/workflows/ci.yml` | ingest → pytest → chain → leakage → fairness → coverage → smoke → web build → web tests. | 🟠 |

## 8. Frontend — `web/`

| Path | Purpose | Sec |
|---|---|---|
| `src/api/types.ts` | The only declaration of API response shapes (mirrors `shared/models.py`, `shared/read_models.py`). | ⚪ |
| `src/api/http.ts` | Single fetch entry point; bearer token in `sessionStorage`; `ApiError` with human messages per status and governance code. | 🔴 (holds JWT) |
| `src/api/auth.ts`, `src/lib/auth.tsx` | Demo sign-in by `sub` only; roles and coded identity read from `GET /api/session`. | 🔴 |
| `src/api/endpoints.ts` | Typed calls per domain (overview, workforce, skills, matrix, requests, learning, profile). | 🟠 |
| `src/lib/useApi.ts`, `src/lib/format.ts` | Abort + generation-guarded loader; presentation-only number formatting. | ⚪ |
| `src/ui/Shell.tsx`, `States.tsx`, `Bits.tsx`, `Icons.tsx` | App shell (nav gated by server roles, ⌘K search, activity, account), loading/empty/error states, primitives. | ⚪ |
| `src/views/*.tsx` | Overview, Workforce, Skills, Matrix, Requests, RequestDetail (ranking, exclusions, resolution, decision), Capability, CandidateDetail (score derivation), Learning, Insights, Profile, Login. | 🔴 (RequestDetail shows resolved names in memory) |
| `src/views/DataQuality.tsx`, `src/ui/Pipeline.tsx` | Real-data governance view: pipeline states, rejections, label governance, certificates (aggregates only). | 🟠 |
| `src/test/*.test.ts(x)`, `src/test/fixtures/api-contract.json` | Vitest suite rendering real captured API payloads (`scripts/export_ui_contract.py`). | ⚪ |
| `dist/` | Build output — **served by the SPA fallback**; the containment fix protects this boundary | 🟠 |

## 9. Future-state stubs (not executed, not tested)

`infra/main.bicep`, `infra/parameters.dev.json`, `functions/**`, `power-platform/**`
(`copilot-studio`, `power-automate` flows, `power-bi` measures).

**Why they exist:** they document the intended Azure/Power Platform target so the local-first
prototype is not mistaken for the end-state architecture. **They are inert** — no CI job runs
them and no test covers them. Copilot Studio instructions are narrate-only by construction.

## 10. Documentation

| Path | Role |
|---|---|
| `PROJECT_BIBLE.md` | Master context pack. **§17 embeds stale engine snapshots** — self-flagged; prefer live paths. |
| `docs/SCORING_SPECIFICATION.md` | **Canonical** formulas, code-verified |
| `docs/DATA_LINEAGE.md` | Source → decision trace |
| `docs/FILE_CATALOG.md` | This file |
| `docs/ARCHITECTURE_REVIEW_V2.md` | Phase 1 audit with reproduced findings |
| `docs/V2_READINESS_REPORT.md` | GREEN / AMBER / RED status |
| `docs/SVP_DEMO_GUIDE.md` | Deterministic demo walkthrough |
| `docs/evidence-merge-rules.md` | **Superseded stub** → points at the specification |
| `docs/architecture.md` | Short layer overview |
| `docs/taxonomy-governance.md`, `taxonomy-approval-checklist.md` | Ontology change control |
| `docs/bias-audit-methodology.md`, `human-oversight.md`, `cold-start-policy.md` | Fairness, oversight, new-joiner policy |
| `docs/risk-register.md`, `mvp-success-criteria.md`, `mvp-validation-report.md` | Delivery governance |
| `docs/phase8/BLOCKED.md` | **Open human decisions** — the honest backlog |
| `docs/runbooks/*`, `docs/future-azure.md`, `docs/adrs/001-hybrid-build.md` | Ops and rationale |

---

## 11. Files that should not survive to production

| File | Why |
|---|---|
| `setup.cfg` | Stale duplicate packaging config |
| `scripts/seed_local_matrix.py` | Thin wrapper over `ingest_fixtures` |
| `src/shared/demand.py` | No caller, 0% coverage |
| `web/dist/` (committed) | Build artifact; gitignored yet tracked |
| `api/main.py` `/api/auth/token` + `shared/demo_identities.py` | Local issuer for a fixed synthetic principal registry (no client-asserted claims since V2) — must still be replaced by OIDC for any real deployment |
| `PROJECT_BIBLE.md` §17 | Stale code snapshots that contradict the live tree |

---

## 12. Files added or materially changed by the V2 SVP hardening (2026-09-16)

| File | Purpose / why it exists | Sec |
|---|---|---|
| `src/shared/errors.py` | Typed domain errors carrying a stable `code` and HTTP status; the API returns `{detail, error}`. | ⚪ |
| `src/shared/demo_identities.py` | The only principals the local issuer knows (`demo-manager`, `demo-manager-2`, `demo-employee`, `demo-employee-2`, `demo-admin`), mapped to synthetic fixture keys. Disabled outside local/test. | 🟠 |
| `src/shared/auth.py` | Tokens carry `sub` only; `build_principal` derives roles + coded identity server-side; forged claims rejected. | 🔴🟠 |
| `src/shared/db_trust.py` | Database trust policy (classification, secret fingerprint, reversible-identity probe). | 🔴🟠 |
| `src/shared/secrets.py` | Explicit secret trust policy; published fixture secrets denylisted outside test mode; stricter real-data rules. | 🔴🟠 |
| `src/shared/config.py` | Validated, range-checked config; version hashes effective half-lives, adjacency discount, taxonomy keywords/relations. | 🟠 |
| `src/shared/db.py` | Ownership-safe request upsert, atomic decision write, `hermes_meta`, external audit anchor. | 🔴🟠 |
| `src/shared/service.py` | Ownership check before ranking; decision governance; ontology gate on evidence; trust marking. | 🟠 |
| `api/main.py` | Per-route role authorization, input validation (unknown skills, formats), structured errors, trust check in `get_service`, lifespan startup. | 🔴🟠 |
| `scripts/phase8/promote_certs.py` | Requires `--mode real|synthetic`; never sets test mode. | 🔴 |
| `scripts/demo_svp.py` | Adds a `safeguards` section and asserts each safeguard in `--verify`; temp DB by default; never rewrites tracked fixtures. | ⚪ |
| `web/src/api/*`, `web/src/lib/auth.tsx` | Auth by registry principal `sub` only; roles from `/api/session`; no client role selection. | 🟠 |
| `web/src/views/RequestDetail.tsx`, `CandidateDetail.tsx` | Excluded-candidate panel (coded id + reason); stored ranking rendered verbatim with run id and config version. | ⚪ |
| `data/quarantine/` (gitignored) | Isolated untrusted real-data database + README. | 🔴 |
| `tests/security/test_v2_api_hardening.py` | Hijack, decision governance, role × endpoint matrix, anti-impersonation, input validation, untrusted DB. | 🟠 |
| `tests/unit/test_v2_integrity.py` | Audit anchor tamper cases, DB trust rules, secret policy + `promote_certs` modes, config-hash fidelity per parameter. | 🟠 |


## Real-data integration (2026-09-17)

| Path | Purpose | Sec |
|---|---|---|
| `scripts/phase8/ingest_real.py` | Governed real-workbook ingestion into `data/real/hermes_real.db`; refuses test mode, weak/published secrets and demo/synthetic DB paths; records an aggregate run summary. | 🔴 |
| `scripts/phase8/real_data_report.py` | Aggregate-only validation report with `--verify` consistency checks. | 🟠 |
| `scripts/phase8/synthetic_workbook.py` | Invented Skill-Matrix-shaped workbook for tests and UI contract capture. | ⚪ |
| `scripts/phase8/ingest_baseline.py`, `ingest_certificates.py` | Batched per-sheet transactions, one abstraction per person, name-free persisted reports, opt-in name-bearing worksheets. | 🔴 |
| `src/shared/read_models.py::data_quality` | DB-derived imported/validated/mapped/pending/scored model. | 🟠 |
| `tests/phase8/test_real_data_integration.py` | Identity protection, taxonomy governance, no-fake-scoring, secret/mode/DB separation, download refusal. | 🟠 |
| `data/real/`, `secrets/` (gitignored) | Real-data database and its secrets. | 🔴 |
