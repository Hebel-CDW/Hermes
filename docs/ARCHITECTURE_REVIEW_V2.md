# Architecture Review V2 — Project Hermes

**Document type:** Phase 1 repository audit (read-only; no code was modified to produce this)
**Classification:** Internal, Confidential
**Audited tree:** `/Users/hebel/Hermes` @ `e45d72b` (working tree: `PROJECT_BIBLE.md`, `data/fixtures/coded_matrix_sample.json` modified)
**Audit date:** 2026-09-15
**Method:** Full read of `PROJECT_BIBLE.md`, `README.md`, `src/**`, `api/**`, `scripts/**`, `tests/**`, `docs/**`, `taxonomy/**`, `web/**`, `infra/sqlite/001_schema.sql`, the three SQLite databases, the real `Skill_Matrix_2025.xlsx`, and all generated reports. **Executable code and tests were treated as ground truth; documentation was treated as a claim to be verified against code.**

---

## 0. Verified baseline (what is actually true today)

These are measured facts, not claims.

| Fact | Value | How verified |
|------|-------|--------------|
| Test suite | **77 passed, 0 failed** | `pytest -q` |
| Coverage (gated packages) | **87.69%**, gate ≥80% | pytest-cov |
| Coverage **including `phase8`** | **76%** — *below the current gate* | `pytest --cov=phase8` |
| `src/phase8/parsers.py` coverage | **0%** (131/131 statements unexecuted) | `pytest --cov=phase8` |
| Real workbook | present, **22 sheets** | `openpyxl` inspection |
| Baseline rows ingested | **12,496** rows in `hermes_phase8.db` | `SELECT COUNT(*)` |
| Baseline rows mapped to a canonical skill | **0** (`pending_aliases: 12697` of `baseline_rows: 12697`) | `data/reports/phase8_ingest_report.json` |
| Baseline↔engine agreement | **0 overlaps** — harness cannot yet grade anything | `data/reports/baseline_agreement.json` |
| Real people in `hermes_phase8.db` | **310** identities + 310 vault display names | `SELECT COUNT(*)` |
| Pilot scoring DB | 5 identities, 6 matrix rows, 10 evidence rows | `data/hermes.db` |

**The single most important line in this table:** the Phase 8 baseline is 100% unmapped. Every one of the 12,697 skill labels resolved to `pending`. The agreement harness — the mechanism the bible describes as "baseline-as-judge" — therefore currently grades nothing. This is *correct, guardrail-respecting behaviour* (no fuzzy auto-mapping), but the system must not be presented as if validation-by-baseline is operational. It is not. It is blocked on human taxonomy governance.

---

## 1. Critical findings (production blockers)

### C-1 — Unauthenticated arbitrary file read via SPA fallback  🔴 CRITICAL

`api/main.py:421-431`

```python
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith("api") or full_path == "health":
        raise HTTPException(status_code=404)
    index = WEB_DIST / "index.html"
    candidate = WEB_DIST / full_path        # <-- no containment check
    if full_path and candidate.is_file():
        return FileResponse(candidate)
```

`full_path` is joined onto `WEB_DIST` with no normalisation and no check that the result stays inside `web/dist`. The route has **no `Depends(get_principal)` and no `Depends(require_api_key)`** — it is completely unauthenticated.

**Reproduced against the live app** (`TestClient`, no credentials):

| Request | Status | Bytes returned |
|---------|--------|----------------|
| `GET /%2e%2e/%2e%2e/data/hermes_phase8.db` | 200 | **8,261,632** |
| `GET /%2e%2e/%2e%2e/config/client_names.txt` | 200 | 519 |
| `GET /%2e%2e/%2e%2e/data/source/Skill_Matrix_2025.xlsx` | 200 | 201,001 |
| `GET /%2e%2e/%2e%2e/%2e%2e/.zshrc` | 200 | 193 (**outside the repo root**) |

**Impact.** The first row alone exfiltrates `identity_vault` for **310 real employees**, the entire manager baseline, and `account_context` — in one unauthenticated GET. This defeats Guardrail 1 (single abstraction entry), Guardrail 3 (governed resolution), Guardrail 7 (leakage audit), and Guardrail 15 (account isolation) simultaneously, and it bypasses the rate limiter, the JWT owner check, and the audit ledger — the resolution never appears in `audit_ledger` at all.

This is the highest-severity finding in the repository and must be fixed before any demo that runs the built SPA.

### C-2 — Real-workbook ingestion silently forces test mode  🔴 CRITICAL

`scripts/phase8/ingest_baseline.py:20`, `ingest_certificates.py:17`, `promote_certs.py:13`, `baseline_agreement.py:14`, `impact_audit.py:18`

```python
os.environ.setdefault("HERMES_TEST_MODE", "1")
```

Every Phase 8 entry point sets test mode before importing `shared.secrets`. In test mode `require_identity_map_secret()` returns the hardcoded fallback `"hermes-test-mode-secret-not-for-prod"` (`src/shared/secrets.py:28`).

**Consequence:** the coded identities for all **310 real employees** in `hermes_phase8.db` were derived from a secret that is published in this repository. `EMP-` tokens are `HMAC-SHA256(known_secret, lower(name))[:8]` — anyone with the repo can rebuild the full name→token table offline from a candidate name list. The pseudonymisation is decorative for real data.

This directly contradicts Guardrail 9 ("fail-closed secrets") and the bible's claim that test-mode secrets are "pytest only" (`PROJECT_BIBLE.md:281`). It also means the existing `hermes_phase8.db` must be treated as compromised and re-tokenised under a real secret, not merely "fixed going forward".

### C-3 — `allocation_weight` is versioned but never applied  🔴 HIGH (scoring integrity)

`src/shared/config.py:18,46,63` defines `allocation_weight=0.15`, exposes it as `HERMES_ALLOC_W`, and **includes it in the scoring-config version hash**. But `src/fitness_gap/engine.py:187` hardcodes the coefficients:

```python
total *= 0.85 + 0.15 * max(0.0, min(1.0, allocation))
```

Verified: `allocation_weight` has **zero** read sites outside `config.py`.

**Consequence:** setting `HERMES_ALLOC_W=0.4` changes `scoring_config_version` — the audit ledger and every `skills_matrix` row will record a *different* scoring version — while producing **byte-identical scores**. The version hash, which is the system's core reproducibility claim (`PROJECT_BIBLE.md:289`), therefore lies in both directions: it signals change where none occurred, and an operator's deliberate tuning is silently discarded. An SVP asking "how do I know a score came from this config?" currently has no sound answer for this parameter.

---

## 2. Scoring discrepancies between documentation and live code

The bible flags §17 as stale (`PROJECT_BIBLE.md:435`) and that disclaimer is honest — but `docs/evidence-merge-rules.md` carries **no** such disclaimer and is actively wrong. It is the document an engineer would most likely trust.

| `docs/evidence-merge-rules.md` claim | Live code | Verdict |
|---|---|---|
| §2 "Proficiency is a **freshness-weighted** vote" | `engine.py:198` — `contribution = tw * item.weight`; comment explicitly states *"Level vote uses type weight only (freshness applied once on record freshness)"* | **WRONG** — describes superseded algorithm |
| §4 "Confidence is the **sum of weighted contributions normalised by total type weights**" | `engine.py:213` — `confidence = max(min_confidence, min(1.0, 0.35 * type_count))`, `+0.2` if demonstrated ∧ certified | **WRONG** — confidence is now cross-type *agreement*, not accumulation |
| §5 "half_life_days, default 180" | Per-skill override; effective half-lives are 120/365, never 180 for any ontology skill | **MISLEADING** |
| *(no mention)* | `volume_score = 1 - exp(-k·n_demo)` is a first-class scoring factor | **MISSING** — an entire multiplicand is undocumented |

Additional doc drift:

- `docs/architecture.md:12` — "Deterministic tokenization to `EMP-####`". Live format is `EMP-` + 8 hex (`gate.py:19,64`). The bible's §17 snapshot also still contains the superseded `EMP-%04d` implementation.
- `PROJECT_BIBLE.md:9` claims "~77 pytest cases · coverage ≥80%" — the count is accurate (77) but the coverage figure silently excludes `phase8`, where the real-data parser sits at 0%.
- `PROJECT_BIBLE.md:353` states `fitness = mean(contrib) * (0.85 + 0.15 * allocation)` — this one *is* correct and matches `engine.py:187`, which makes the `allocation_weight` config field (C-3) doubly misleading.

**Assessment:** the *code* is more defensible than the *docs*. The current algorithm (agreement-based confidence, volume separated from confidence, freshness applied exactly once) is the better design and already satisfies the Phase 4 objectives. The failure is that no document states it correctly. This is exactly the gap `docs/SCORING_SPECIFICATION.md` must close in Phase 2.

---

## 3. Dead code, unused parameters, and misleading abstractions

| Location | Finding | Impact |
|---|---|---|
| `fitness_gap/engine.py:43` | `availability` parameter — **0 reads** in the function body | Callers (`service.py`) believe they are passing availability; it is discarded. Availability is in fact honoured only via `allocation`. |
| `fitness_gap/engine.py:46` | `cold_start_ids` parameter — **0 reads** | Dead API surface |
| `fitness_gap/engine.py:105-106` | Comment "Exploration slot: optionally append one cold-start…" with no implementing code | Comment describes a feature that does not exist |
| `models.py:85`, `api/main.py:265` | `availability_required` flows API → `StaffingRequest` → engine and is never read | Dead contract across three layers |
| `fitness_gap/engine.py:70,75` | `detail["_exclusion"]` is set, then the candidate is dropped and `detail` discarded | Exclusion reasons are computed and thrown away — no way to answer "why was X excluded?" |
| `fitness_gap/engine.py:73-75` | `(sid in skills) or self._lookup_skill(skills, sid)[0] is not None` — first clause is subsumed by the second | Redundant |
| `fitness_gap/engine.py:147,173,188` | `reasoning_detail` is a skill-keyed dict polluted with `_allocation` / `_exclusion` magic keys | Type-unsafe; frontend must `isSkillDetail()`-guard every value (`ShortlistReveal.tsx:12`) |
| `phase8/aliases.py:53-62` | Two **identical** branches: `if slug in self._ontology.values()` then `if slug in set(self._ontology.values())` | Duplicated logic; second is unreachable |
| `phase8/parsers.py:164` | `parse_collab_transposed` prepends `DroppedRow(sheet,"people_columns",count)` into the **dropped** list | A metric masquerading as a rejection; corrupts `phase8_dropped_rows.json` |
| `scripts/phase8/ingest_baseline.py:56` | `propose_variants(..., kind)` — `kind` unused | Dead parameter |
| `scripts/phase8/ingest_baseline.py:105-107` | `if db_path.exists(): pass` | No-op block |
| `scripts/phase8/ingest_baseline.py:30-53` | `EXPECTED_PERSON_ROWS` is reported but never asserted | Looks like a validation gate; is not one |
| `src/shared/demand.py` | **0% coverage**, no production caller | Entire module is aspirational |
| `setup.cfg` | Duplicates `pyproject.toml` packaging, omits PyJWT/openpyxl | Two sources of truth; `setup.cfg` is stale |
| `scripts/phase8/promote_certs.py:23-24` | Re-imports `ingest_certificates` by mutating `sys.path` after already importing it at module top (line 15) | Fragile double-import |
| `service.py:245` | `__import__("json")` inline despite module-level imports elsewhere | Code smell |

---

## 4. Guardrails that are weaker than documented

### G-1 — Role-level governance controls are stored but never enforced

`role_profiles.critical_skills_json` and `min_coverage_ratio` are persisted (`db.py:315-330`) and exposed via `GET /api/roles`, and `TargetRoleProfile` carries both fields (`models.py:94-95`).

**But `/api/fitness/rank` never loads them from the role.** `RankBody` takes `critical_skills` and `min_coverage_ratio` from the *client request body* (`api/main.py:267-268`). A client that omits them gets `critical_skills=[]` and the global default floor — silently bypassing the role's own critical-skill requirement.

`compute_gaps` ignores both fields entirely.

**Consequence:** Guardrail "coverage/critical floors" (`PROJECT_BIBLE.md:312`) is enforced only if the caller volunteers the constraint. That is not a guardrail; it is an option.

### G-2 — Audit chain ordering is not well-defined

`db.append_audit` selects the predecessor with `ORDER BY created_at DESC, event_id DESC` (`db.py:424`); `verify_audit_chain` replays with `ORDER BY created_at ASC, event_id ASC` (`db.py:451`). `event_id` is a random UUID4 and there is **no monotonic sequence column** on `audit_ledger`.

**Reproduced:** two events written in the order `["zzzz-last", "aaaa-first"]` sharing a `created_at` produce a chain that fails its own verifier:

```
verify_audit_chain errors: ['aaaa-first: prev_hash mismatch', 'zzzz-last: prev_hash mismatch']
```

Microsecond timestamps make natural collisions rare, but "rare" is not "sound". The ledger's integrity claim rests on an ordering that the schema does not guarantee. `hermes_phase8.db` holds 13,259 audit rows written in a tight ingest loop — precisely the collision-prone workload.

### G-3 — Cert label → skill mapping is an ungoverned substring match

`scripts/phase8/ingest_certificates.py:109-112`:

```python
for code, sid in code_to_skill.items():
    if code in low or low in code:      # bidirectional substring
        skill_id = sid
        break
```

This auto-maps a certificate label onto a canonical `skill_id` with no confidence score, no alias table entry, no `mapped_by='human'`, and no pending state — the exact pattern `phase8/aliases.py` was built to prevent. Short cert codes make false positives easy (`"CKA"` matches any label containing those letters; iteration order decides the winner).

It writes the resolved `skill_id` into the column named **`cert_code`** (line 130-131), so the column's contents contradict its name.

This is the one place in the codebase where the "no auto-mapping without governance" rule is violated. It is currently latent — `promoted` counts are 0 because all `earned_at` are NULL — but it will fire the moment humans complete `cert_date_request.csv`.

### G-4 — Baseline-isolation test cannot catch the regression it exists to prevent

`tests/guardrails/test_baseline_isolation.py:41-96` builds evidence **in memory** and calls `inference.merge_evidence(evidence)` / `fitness.rank_candidates(...)` directly. It never exercises `HermesService.rank`, which is the code path that actually loads from SQLite.

Populating `baseline_assessments` therefore *cannot* change the result, regardless of what the production code does — the test would still pass if `service.rank` began joining `baseline_assessments` tomorrow. The companion test (line 99) is a `grep` for the string `baseline_assessments`, which is defeated by any indirection.

The guardrail is load-bearing (`PROJECT_BIBLE.md:150`) and deserves a test that runs through the DB-backed service path.

---

## 5. Data-model weaknesses

| Finding | Location | Notes |
|---|---|---|
| `computation_run_id` is written to `skills_matrix` but dropped on read | `db.py:238-254`; `SkillRecord` has no such field | The matrix cannot state which run produced it; the inspector required by Phase 3 has nothing to cite |
| Run IDs are `uuid4()` | `service.py:117` | Identical inputs + identical config produce a different run id every time — the opposite of a reproducibility key |
| `replace_skills_matrix` fallback run id is a **timestamp** | `db.py:185` | Non-deterministic second source of run identity |
| `skills_matrix_history` has no FK, no unique constraint, no index on `(coded_identity, skill_id)` | `001_schema.sql:57-70` | Append-only table with no integrity constraints |
| `skill_aliases.skill_id` is `TEXT NOT NULL` but pending rows store `''` | `aliases.py:72` vs `001_schema.sql:162` | Sentinel empty string instead of NULL; `mapped_by` has no CHECK constraint |
| `baseline_assessments` has no unique constraint on `(coded_identity, raw_label, source_sheet)` | `001_schema.sql:146` | Relies solely on the derived `baseline_id` hash |
| `cert_staging.cert_code` stores a `skill_id` after promotion | `ingest_certificates.py:131` | Column name contradicts contents |
| No index on `evidence_staging(skill_id)`, `audit_ledger(event_id)` beyond PK, or `account_context(account_label)` | `001_schema.sql:128-131` | Acceptable at pilot scale; noted for honesty |
| `infra/sql/001_schema.sql` (Azure) vs `infra/sqlite/001_schema.sql` | two schemas | Drift risk; only the SQLite one is executed |

---

## 6. API weaknesses

| Finding | Location |
|---|---|
| **C-1 path traversal** (see §1) | `main.py:421` |
| `required_skills: Dict[str, int]` is unvalidated; `ProficiencyLevel(v)` on an out-of-range value raises `ValueError` → **500**, not 400 | `main.py:263,286,303,326` |
| `POST /api/identity/abstract` accepts an arbitrary dict from any authenticated principal and writes to `identity_map`/`identity_vault` | `main.py:228-238` |
| No role check on `/api/fitness/rank` — any authenticated principal can rank | `main.py:276` |
| `@app.on_event("startup")` deprecated (emits warnings in the test run) | `main.py:44` |
| Rate limiter is per-process in-memory; resets on restart, ineffective multi-worker | `rate_limit.py`, `main.py:41` |
| `/api/auth/token` mints tokens with arbitrary `sub`, `roles`, **and `coded_identity`** — self-asserted identity. Gated only by `HERMES_ENV != local`, which defaults to `"local"` | `main.py:107-113` |
| Errors are unstructured `{"detail": str}`; no error codes for programmatic handling | throughout |
| `skills_matrix` freshness is recomputed only at merge time; `/api/dashboard` reports stored values as if current | `main.py:116` |

Note on the token issuer: because `HERMES_ENV` defaults to `"local"`, the stub is **enabled by default** and a caller can mint an `admin` token for any `coded_identity`. That is acceptable for a local prototype but must be stated plainly as prototype-only, not described as "auth".

---

## 7. Frontend weaknesses

| Finding | Location |
|---|---|
| `reasoning_detail` values must be runtime type-guarded because the backend mixes `_allocation`/`_exclusion` scalars into a skill-keyed map | `ShortlistReveal.tsx:12,183` |
| Drill-down shows level/confidence/volume/freshness/evidence but **never the arithmetic** — no `level_ratio`, no `contribution`, no `allocation`, no config version, no run id | `ShortlistReveal.tsx:74-108` |
| The UI cannot answer "why 0.82?" — it shows five factors and a score with no stated relationship between them | `ShortlistReveal.tsx` |
| `per_skill_reasoning` (a **formatted string**) is what is actually rendered as the summary; the structured object is secondary | `ShortlistReveal.tsx:177-187` |
| `ensureAuth` hardcodes `roles: ["manager","admin"]` and `sub: "mgr-ui"` — the UI grants itself admin | `client.ts:23-24` |
| JWT in `sessionStorage` (XSS-readable) | `client.ts:37` |
| `Dashboard` type omits `volume_score` though the API returns it | `client.ts:123-129` |
| No frontend tests of any kind | `web/` |
| `web/dist/` is committed despite being gitignored — and is the very directory C-1 serves from | `web/dist/**` |

---

## 8. Phase 8 weaknesses

Beyond C-2, G-3, and the 0%-coverage parser:

1. **No data-quality report.** `phase8_ingest_report.json` gives per-sheet `raw_person_rows`/`assessments`/`dropped` counts but none of: people accepted vs discovered, rows rejected **by machine-readable reason**, labels discovered/excluded/pending, rating distributions, or sheet-level anomaly flags. Phase 5 requires all of these.
2. **Rejections are free-text.** `DroppedRow(sheet, reason, detail)` where `detail` is `repr(row[:3])` or an f-string (`parsers.py:76,90,93,98`). Not machine-readable; cannot be aggregated or asserted on.
3. **Silent non-rejection.** A raw value of `7` on a 5-point sheet yields `normalised_level=NULL` (`normalize.py:32`) and is still inserted, with **no drop record**. Out-of-range data is silently swallowed.
4. **Unexplained row deltas.** `iSeries L2` parses 18 raw rows against 12 expected; `AIX` 17 vs 4. Tracked in `docs/phase8/BLOCKED.md` (B-SHEET-ROW-DELTAS) but never surfaced as a structured anomaly.
5. **Brittle magic.** `normalize_label(name).startswith("ibm i")` (`parsers.py:78`) hardcodes one workbook's section-header text. `range(3, min(len(row), 12))` (`ingest_certificates.py:41`) hardcodes cert column positions. `people` start at column index 4 in Collab (`parsers.py:122`).
6. **`identity_vault` is populated from real names at ingest** (`ingest_baseline.py:142`) — tokens are derived from *person names*, not employee IDs, so two people sharing a name collide into one identity and a name spelling change creates a new person.
7. **`data/phase8/team_variants.csv` is tracked in git** while `manager_variants.csv` is gitignored. Reviewed: it contains only team names, no personal data — acceptable, but the asymmetry is undocumented.

---

## 9. Test gaps

| Gap | Evidence |
|---|---|
| `src/phase8/parsers.py` — **0% coverage** | All real-workbook sheet parsing is untested |
| `phase8` package excluded from the coverage gate | `pyproject.toml:addopts` lists 5 packages, not `phase8` |
| Including `phase8` drops total to **76%** — below the existing 80% gate | measured |
| `api/` and `scripts/` excluded from coverage | `pyproject.toml` |
| No test asserts the **numeric value** of a fitness score | `test_fitness_gap.py` asserts ordering and `> 0` only — no golden test |
| No test pins `scoring_config_version` | A silent formula change is invisible to CI |
| No test for the SPA fallback route | C-1 went undetected |
| No malformed-input tests (bad XLSX, wrong sheet shape, non-numeric ratings) | `tests/phase8/` |
| No test that a **pending** alias cannot enter scoring | Phase 6 explicitly requires this |
| Baseline-isolation test bypasses the DB service path | §G-4 |
| `test_candidate_skills_csv_membership_invariant` skips silently without the workbook | `tests/phase8/test_extract_and_aliases.py:19` |
| No frontend tests | `web/` |
| `tests/unit/test_taxonomy*.py` are 8–9 lines each | Thin |

---

## 10. What is genuinely strong (do not regress these)

An honest audit records what works. These are well-built and should be preserved verbatim through V2:

- **Confidence/volume/freshness separation is already correct.** `engine.py:211-219` computes confidence as cross-type agreement, volume as a saturating count function, and freshness once — then `fitness_gap/engine.py:159-165` multiplies them exactly once each. The Phase 4 objective ("separate confidence from volume; never double-apply freshness") is **already met in code**; only the documentation lags.
- **Metadata whitelisting on evidence.** `db.stage_evidence` (`db.py:132-136`) persists only `matched_keywords`/`source_ref`/`manager_confirmed`/`reopen`/`escalation`. Ticket excerpts genuinely cannot reach the database, and a test enforces it.
- **No-fabricated-dates discipline is real.** `earned_at`/`assessed_at` stay NULL; `normalize_level(0.0)` returns NULL rather than level 1; NULL-dated certs provably never reach `skills_matrix`.
- **Recursive PII/leakage scanning** (`gate.py:30-44`, `_walk_strings`) inspects nested structures, not just top-level keys.
- **Alias resolution refuses to fuzzy-match** into a live `skill_id` (`aliases.py:64-77`) — which is precisely why 12,697 rows sit pending. That is the system behaving correctly under pressure.
- **Decisions are audit-only.** `service.decide` records `engine_rank_of_choice` and stamps the guardrail name into the payload; nothing reads it back into scoring.
- **Deterministic tokenisation** verified stable across three ingest orderings (`test_tier0.py:28`).

---

## 11. Prototype vs production — honest classification

| Capability | Status |
|---|---|
| Identity abstraction, inference, fitness/gap, resolution | **Prototype, working, tested** |
| Evidence merge algorithm | **Prototype, working** — sound design, undocumented |
| Coded matrix + history + audit chain | **Prototype** — chain ordering unsound (G-2) |
| Pilot fixture pipeline | **Prototype, working** — 5 synthetic people |
| Real workbook ingestion | **Prototype, partially working** — parses, but 0% mapped, 0% test coverage, test-mode secrets |
| Baseline-as-judge validation | **Blocked** — 0 overlaps; requires human taxonomy governance |
| Taxonomy | **Prototype** — 5 skills vs 752 discovered labels |
| Authentication | **Stub only** — self-asserted claims, local issuer |
| API security boundary | **Broken** — C-1 |
| Frontend | **Demo-grade** — no tests, self-granted admin |
| Azure / Power Platform / Functions | **Stubs** — not executed, not tested |
| Live connectors (ServiceNow/LMS/HR) | **Not implemented** |

**Nothing in this repository is production-ready.** The correct description is: *a working local-first prototype with a sound scoring core, a serious unauthenticated file-read vulnerability, and a real-data path that is ingested but not yet governed.*

---

## 12. Prioritised remediation plan for V2

**P0 — must fix before any SVP demo**
1. C-1: contain `spa_fallback` to `web/dist` (resolve + containment check), return 404 otherwise. Add a regression test.
2. C-2: remove `os.environ.setdefault("HERMES_TEST_MODE", "1")` from all Phase 8 entry points; require a real secret; document that `hermes_phase8.db` must be rebuilt.
3. C-3: apply `allocation_weight` in `_fitness`, or delete it from the config and the version hash. Add a test that the version hash changes **iff** scores can change.

**P1 — required for "every engineering question has a precise answer"**
4. `docs/SCORING_SPECIFICATION.md` with formulas matching code line-for-line (Phase 2).
5. Structured `reasoning_detail` with `level_ratio`, `contribution`, `allocation`, `computation_run_id`, `scoring_config_version`; remove magic `_` keys (Phase 3).
6. Deterministic `computation_run_id` = hash(inputs + config version) (Phase 8).
7. Golden scoring tests pinning exact numeric scores and the config version (Phase 7).
8. Add `phase8` to the coverage gate without lowering the threshold (Phase 7).

**P2 — data integrity and governance**
9. Machine-readable rejection reasons + full data-quality report (Phase 5).
10. Governed cert-label mapping — route G-3 through the alias table (Phase 6).
11. Monotonic `seq` column on `audit_ledger`; order the chain by it (Phase 8).
12. Enforce role-level `critical_skills`/`min_coverage_ratio` server-side (G-1).
13. Baseline-isolation test through the DB-backed service path (G-4).

**P3 — hygiene**
14. Remove dead parameters and duplicated branches (§3).
15. Reconcile `docs/evidence-merge-rules.md`, `docs/architecture.md`, and bible §17 (or delete §17 in favour of pointers).
16. Delete `setup.cfg`.

---

## 13. Questions the SVP will ask, and whether we can answer them today

| # | Question | Can we answer now? |
|---|---|---|
| 1 | How are skills calculated? | Yes in code; **no** in docs (§2) |
| 2 | How is proficiency determined? | Yes — depth/surface keyword tiers + type-weighted vote; undocumented |
| 3 | How is evidence weighted? | Yes — 0.55/0.30/0.15, config-hashed |
| 4 | How does freshness work? | Yes — per-skill half-life, applied exactly once |
| 5 | How does confidence work? | Yes in code; **docs describe the wrong formula** |
| 6 | How do sources merge? | Yes |
| 7 | How are candidates ranked? | Yes — but `allocation_weight` inconsistency (C-3) |
| 8 | How are gaps calculated? | Yes — `demand_weight × deficit`; adjacency **not** applied (inconsistent with ranking) |
| 9 | Why is the 2025 Excel separate? | Yes — strongest answer in the repo |
| 10 | Why are identities coded? | Yes — **but C-1 and C-2 undermine the answer in practice** |
| 11 | Why does every file exist? | **No** — `FILE_CATALOG.md` does not exist (Phase 2) |
| 12 | Is the result reproducible? | **No** — run ids are UUIDs; version hash is unfaithful (C-3) |
| 13 | How is bias prevented? | Partly — schema audit + Gini impact audit; no protected attributes by construction |
| 14 | How is it audited? | Partly — chain ordering unsound (G-2); C-1 bypasses audit entirely |
| 15 | Prototype vs production? | Yes — §11 |
| 16 | What happens when data is missing/ambiguous? | Partly — pending aliases and NULL dates are handled well; out-of-range values are silently swallowed (§8.3) |

**Seven of sixteen** currently lack a precise, demonstrable answer. Closing those is the objective of Phases 2–10.

---

*End of Phase 1 audit. No source files were modified in producing this document.*

---

## Addendum — remediation status (2026-09-16)

Sections 1–13 above are preserved as the audit record. Status after V2 implementation:

| Finding | Status | Evidence |
|---|---|---|
| C-1 unauthenticated file read | **Fixed** | `tests/security/test_spa_path_traversal.py`; live probe returns SPA shell |
| C-2 real ingest under test-mode secret | **Fixed going forward**; existing `hermes_phase8.db` must be rebuilt (RED R-5) | `require_real_data_ingest_secret`, `tests/security/test_tier0.py` |
| C-3 `allocation_weight` hashed but unused | **Fixed** | `tests/unit/test_scoring_golden.py` |
| §2 doc/code scoring discrepancies | **Fixed** | `SCORING_SPECIFICATION.md`; `evidence-merge-rules.md` superseded; `architecture.md` corrected |
| §3 `_exclusion` / `_allocation` magic keys, discarded exclusion reasons | **Fixed** | `calculation` envelope + `excluded_candidates`; `test_scoring_inspector.py` |
| §3 Collab `people_columns` pseudo-rejection | **Fixed** | `test_workbook_parsers.py` |
| §3 unused `availability`, `cold_start_ids`, `availability_required`; duplicate alias branch; `setup.cfg`; `demand.py` | **Open** (hygiene, no behavioural impact) | — |
| G-1 role controls not enforced | **Fixed when `role_id` is supplied** (AMBER A-13) | `test_governance_regressions.py` |
| G-2 audit chain ordering | **Fixed** | `test_audit_chain_ordering.py`; real ledger verifies after migration |
| G-3 substring cert mapping | **Fixed** | `test_governance_regressions.py` |
| G-4 baseline-isolation test bypassed DB path | **Fixed** (new service-path test; original kept) | `test_service_rank_and_gaps_unchanged_by_baseline_rows` |
| §5 `computation_run_id` dropped on read; UUID run ids | **Partially fixed** — carried on reads and results; pinnable; default still UUID (AMBER A-4) | `test_scoring_inspector.py`, demo |
| §6 invalid levels → 500 | **Fixed** (422) | `test_governance_regressions.py` |
| §6 token stub, in-memory rate limiter, deprecated startup hook | **Open** (RED R-1, R-7; AMBER A-12) | — |
| §7 frontend cannot show the arithmetic | **Fixed** | `ShortlistReveal.tsx` score derivation; `npm run build` |
| §7 self-granted admin, JWT in sessionStorage, no frontend tests | **Open** (RED R-1) | — |
| §8 no data-quality report; free-text rejections; silent out-of-range | **Fixed** | `phase8/quality.py`, `test_workbook_parsers.py` |
| §8 name-keyed Phase 8 identities; brittle sheet heuristics | **Open** (AMBER A-6) | — |
| §9 phase8 excluded from coverage gate; parsers 0% | **Fixed** — gate includes phase8, raised to 85%; parsers 86% | `pyproject.toml` |

Full classification: `docs/V2_READINESS_REPORT.md`.



---

## Addendum 2 — SVP demo hardening (2026-09-16)

Remediation of the defects reproduced in the independent V2 validation run:

| Validation finding | Status | Evidence |
|---|---|---|
| Request-ID hijack (another manager re-ranks, resolves, locks owner out) | **Fixed** — immutable ownership enforced in the service and atomically in SQL | `tests/security/test_v2_api_hardening.py`, live smoke |
| Non-owner decisions; decisions naming non-shortlisted candidates | **Fixed** — owner, open request, shortlist present, candidate shortlisted and not excluded | same |
| No role authorization (employee could rank, enumerate, create identities) | **Fixed** — per-route roles; managers see only direct reports | role × endpoint matrix test |
| Token stub accepting arbitrary roles / coded identity; `/me` impersonation | **Fixed** — synthetic registry, `sub`-only tokens, forged claims rejected | anti-impersonation tests |
| Published fixture secret accepted for real ingest without the flag; `promote_certs` forcing test mode | **Fixed** | `tests/unit/test_v2_integrity.py` |
| Reversible `hermes_phase8.db` servable | **Fixed** — trust metadata policy + quarantine | DB trust tests |
| Audit truncation / wipe / recomputed chain undetected | **Fixed** — external signed anchor | anchor tamper tests |
| `HERMES_HALF_LIFE` hashed but ineffective | **Fixed** — removed; effective per-skill half-lives hashed; adjacency discount versioned | fidelity test per parameter |
| Excluded candidates not rendered in UI | **Fixed** | build + typecheck (browser rendering not automated) |
| Unknown skills → 200 | **Fixed** — 422 | input validation tests |
| Deprecated `on_event` startup | **Fixed** — lifespan | test output |

Still open: §3 dead parameters (`availability`, `cold_start_ids`), `setup.cfg`, `demand.py`
(no behavioural impact); name-keyed Phase 8 identities; keyword heuristics; no real IdP.
