# Hermes V2 — Real Skill Matrix Integration

**Date:** 2026-09-17 · **Scoring config:** `5a35863a05c7` · **Status:** governed prototype. Real data is imported, validated and protected; **no real person is scored**. Not production-ready. All work is uncommitted.

Every number below was read from the real-data database (`python -m scripts.phase8.real_data_report`) or measured by the named command. No name, raw row, client label or secret appears in this document.

---

## 1. Workbook structure

`data/source/Skill_Matrix_2025.xlsx` is gitignored and read in place only.

| Shape | Sheets | Handling (existing Phase 8 parser) |
|---|---|---|
| People as rows, header in row 0, one column per skill | 20 team sheets (row counts 17–53, 32–134 columns) | `parse_standard_people_rows` |
| Transposed: people across row 0 from column E, applications down column B, 1–4 scale | `Collab` | `parse_collab_transposed` |
| Certificates: banner row, header in row 1, name/team/manager, then up to 9 certificate cells | `Certificates` | certificate workstream (`ingest_certificates`) |

22 sheets in total. The existing parser handled every shape, so no new parser was written.

## 2. Ingestion results

Command, run outside test mode with a strong secret:
- `set -a; . secrets/hermes_real_data.env; set +a`
- `python -m scripts.phase8.ingest_real`

The command refuses to run in test mode and refuses the published fixture secrets. The secrets file is gitignored, mode 600, and its values are never printed.

| Metric | Value |
|---|---|
| Sheets | 22 |
| People detected (coded identities) | **310** |
| Cells processed | 13,243 |
| Cells accepted | **12,852** (12,696 skill cells; 156 client/account cells, isolated) |
| Cells rejected | **391** |
| Distinct workbook skill labels (normalised) | 673 |
| Mapped / pending | **0 / 673** |
| Rejected labels | client/account 8 · soft skill 13 · culture fit 1 |
| Excluded column occurrences | 251 |
| Certificate cells | 427 (203 people on the Certificates sheet; 187 distinct certificate labels) |
| Scored population | **0** |

The earlier label-extraction report counted 691 distinct **raw** labels. That count includes excluded columns and case or spacing variants; governance operates on the 673 normalised skill labels.

## 3. Data quality results

| Rejection code | Count |
|---|---|
| `non_numeric_cell` | 198 |
| `missing_name` | 136 |
| `fractional_average` (group averages) | 38 |
| `group_or_section_header` | 17 |
| `out_of_range_value` | 1 |
| `section_header` | 1 |

Every rejection carries a code from the closed `RejectionReason` vocabulary.

Baseline level distribution is stored for governance only and never scored. Consistency checks (`real_data_report --verify`) all pass:
- People detected equals `identity_map`.
- Pending labels equal pending alias rows.
- Certificate cells equal staged rows; exact certificate classifications equal stored `cert_code` rows.
- Accepted cells equal skill cells plus account cells; processed equals accepted plus rejected.
- Mapped labels equal the mapping trace.
- Baseline rows do not exceed accepted skill cells.
- Nobody is scored without evidence.

## 4. Identity protection

- **Coded identities.** Each person becomes `EMP-xxxxxxxx`, an HMAC of the normalised source key under the real-data secret. Tokens are deterministic: re-ingesting yields the same tokens (tested). None can be recomputed from a published secret (tested; also enforced by the trust policy).
- **Names stay in the vault.** Names exist only in `identity_vault`. A full-table scan of every other table found 0 names.
- **Resolution.** The only reveal path is the existing owner-scoped, rate-limited, audited `POST /api/identity/resolve`.
- **Audit.** Abstraction is audited once per person (310 `evidence_ingestion` events), not once per cell, plus one aggregate `phase8_workbook_ingest` event. The audit chain verifies.
- **Reports on disk are name-free.** Persisted rejections contain `{sheet, reason}` only; the parser's in-memory detail embeds names and is no longer written. Name-bearing review worksheets are opt-in (`--governance-worksheets`, `--cert-request-with-names`) and written only to gitignored paths.
- **No tracked file is written.** Previously the ingest overwrote tracked `data/phase8/team_variants.csv`.
- **The frontend cannot reverse a token.** No endpoint returns the vault, `source_employee_key` or `source_hash`, and the browser never holds the secret. Response scan across 12 endpoints × 3 roles: 0 names, 0 vault fields, 0 client labels, 0 certificate labels.

## 5. Taxonomy mapping status

| Class | Count | Enters scoring |
|---|---|---|
| MAPPED | 0 | only via governed evidence, never from baseline ratings |
| PENDING | 673 | no |
| REJECTED: client/account | 8 | no (isolated in `account_context`) |
| REJECTED: soft skill | 13 | no |
| REJECTED: culture fit | 1 | no |

Resolution uses the existing `SkillAliasResolver`: an exact ontology id/name match, then an approved alias, and otherwise pending. There is no fuzzy matching and no LLM. Mapped labels are recorded with `label`, `skill_id`, `mapped_by` and `match_confidence` in the ingestion summary and shown in the Data Quality view. For the real workbook this trace is empty. The canonical ontology stays at 5 skills, unchanged.

## 6. Certificate mapping

| Metric | Value |
|---|---|
| Certificate cells staged | 427 |
| Exact certificate-code match (whole-token, `resolve_cert_label`) | 5 |
| Pending (unmapped or ambiguous) | 422 |
| `earned_at` recorded | 0 (NULL preserved) |
| Promoted to evidence | 0 |

No certificate-to-skill relation is inferred and no dates are invented. A certificate becomes evidence only through `promote_certs --mode real` once a human supplies `earned_at`.

## 7. API integration

- **`GET /api/data-quality`** (new; manager/admin; 401 unauthenticated, 403 employee) returns pipeline states, ingestion aggregates, rejection codes, label governance, certificate counts and live DB counts. It computes everything from the database and returns aggregates only.
- **`GET /api/session` and `GET /api/overview`** now include `data_classification` (`synthetic` | `real`), read from DB trust metadata.
- **Other endpoints** are reused unchanged and work on the real DB:
  - `/api/workforce` returns 310 coded identities with `skill_count 0`.
  - `/api/dashboard` returns no cells.
  - `/api/me` returns 400 for principals without a coded identity (the UI does not call it for them).
  - Ranking returns no candidates.
- **Trust policy** is unchanged: a real DB is served only outside test mode, with the matching strong secret and no reversible tokens.
- **Downloads blocked.** The workbook, databases and secrets are not downloadable through the static or SPA routes (tested with traversal variants).

## 8. UI integration

Existing components and design, no redesign:
- **Data Quality** (`/data-quality`, new route): Imported / Validated / Mapped / Pending / Scored strip, KPI strip, rejection category bars, taxonomy governance bars, certificate bars, and the approved mapping trace (empty state when there is none).
- **Shell:** the sidebar footer and a top-bar chip show "Real workforce data" from the server session. The previously hardcoded "Synthetic demo data" text is removed.
- **Overview:** the pipeline strip plus "No scored capability" instead of a 0% ring.
- **Workforce:** "No scored capability" in place of the topology. A filterable list of coded identities shows 60 at a time, and the inspection ledger shows no invented metrics.
- **Skills:** the atlas shows the 5 canonical skills only, with a separate "Canonical skills vs workbook labels" count card linking to Data Quality.
- **Matrix:** "Real capability matrix unavailable · Skill labels require governed mapping before scoring" with API counts (673 pending, 0 mapped, 0 scored, 310 imported). No grid is drawn.
- **Profile:** a "No personal skill profile" empty state for principals with no coded identity.

**Live check** (uvicorn on the real DB, outside test mode, Chrome DevTools):
- 90 renders (manager 10 routes, admin 5, employee 3, × 1440/1280/1024/768/390): 0 overflow, 0 error states, 0 failed requests.
- DOM values equal `/api/data-quality` for all 5 pipeline states, all rejection rows and the certificate counts.
- Rendered text of all pages: 0 vault names, 0 client labels.

## 9. Security validation

`tests/phase8/test_real_data_integration.py` (27 tests; invented workbook, real-data path, strong random secret, no test mode):
- **Counts:** workbook → DB → API counts; mapped trace; deterministic re-ingest.
- **Audit:** once per person, not per cell.
- **Names:** only in the vault; not in reports; not reproducible from published secrets.
- **API responses:** no names, vault fields or client labels for any role; data-quality equals DB; RBAC.
- **Scoring:** pending and mapped baseline labels never score (matrix empty, rank empty); client labels never reach scoring tables.
- **Certificates:** keep NULL dates.
- **Secrets and modes:** published or weak secrets rejected (no DB created); test mode rejected; demo, synthetic and validation DB paths refused; real DB returns 503 in test mode; a real workbook cannot enter a synthetic DB.
- **Downloads:** the raw workbook, DB and secrets cannot be downloaded.
- **Bundle:** contains no real-data markers.

UI contract (`tests/api/test_ui_contract.py`, `web/src/test/realdata.test.tsx`): real-mode payloads are captured from the invented workbook through the real path. The UI renders the same numbers as the API, with no fake scoring.

**Leak scan against the real vault** (counts only):

| Scope | Names | Client labels | Raw labels | Cert labels | Secrets |
|---|---|---|---|---|---|
| `web/dist` bundle | 0 | 0 | 0 | 0 | 0 |
| Committable files | 0 multi-word names | see §12 | pre-existing only | pre-existing only | 0 |

## 10. Performance

Profiled with cProfile on the real workbook.

| | Before | After |
|---|---|---|
| Baseline ingest | **42.5 s** | **1.9 s** |
| Certificate ingest | one session per cell | 0.1 s |
| DB sessions | 158,974 | per sheet / per new person |
| Identity abstractions (each with audit append + anchor write) | 13,055 (one per cell) | 310 (one per person) |

**Cause:** `svc.abstract` ran for every cell, adding identity upsert, availability, audit append and anchor file write each time. `insert_baseline` also opened one session per row.

**Fix:**
- Each person is abstracted once per run; known identities are reused.
- `insert_baselines`, `upsert_account_contexts` and `insert_cert_stagings` use `executemany` in one transaction per sheet, so a failure rolls the whole sheet back.
- Validation, rejection codes, alias governance and auditing are unchanged; determinism is tested.

## 11. Synthetic vs real-data separation

| | Synthetic demo | Real workbook |
|---|---|---|
| Database | `data/hermes.db` / demo temp DB | `data/real/hermes_real.db` (gitignored) |
| Classification | `synthetic` | `real` (relabelling refused) |
| Secret | test-mode fixture secret | strong secret in `secrets/hermes_real_data.env` |
| Mode | `HERMES_TEST_MODE=1` | test mode refused for ingest and serving |
| Purpose | deterministic SVP demo | governed ingestion, quality, taxonomy governance |

- `python -m scripts.demo_svp --verify` passes twice (DETERMINISM OK, SAFEGUARDS OK), and `demo_svp` is unchanged.
- `phase8_ingest_runs` counts as a real-data table: a synthetic DB containing it is refused.

**Final gates:**
- `python -m pytest -q -p no:cacheprovider`: **345 passed**, coverage **92.35%**.
- `npx tsc --noEmit -p tsconfig.app.json`: pass. `npm run build`: pass. `npm test`: 71 passed.

## 12. Remaining limitations

1. **Nothing is scored.** 673 labels await human taxonomy approval and 422 certificates await mapping; no certificate has a date. Real people show no capability until governed mappings and dated evidence exist. This is correct, not a defect.
2. **Pre-existing tracked content (in `HEAD`, before this work):**
   - `config/client_names.example` holds a "safe test token" that is also a real account label; five test files use it.
   - `data/phase8/candidate_skills.csv` contains workbook skill labels (no names, no client labels).
   - A single-token name match was replaced with an invented token in `docs/phase8/BLOCKED.md` and `tests/phase8/test_baseline_normalize_and_managers.py` in the working tree; git history still contains it (history was not rewritten, per instruction).
3. **Stale name-bearing files from earlier Phase 8 runs** (gitignored, untracked, not created by this work): `data/phase8/cert_date_request.csv` (no dates filled), `data/phase8/manager_variants.csv`, `data/reports/phase8_dropped_rows.json`. They should be securely deleted by the data owner.
4. **Same-name merge.** The workbook has no employee id; identities are keyed by normalised name, so same-name people merge.
5. **Unsalted source hash.** `identity_map.source_hash` is an unsalted SHA-256 of the normalised name. It is not exposed by any endpoint, but it is dictionary-checkable by anyone holding the database file.
6. **Local auth only.** Demo principals are not mapped to real coded identities, so real employees cannot sign in; `/profile` shows an empty state.
7. **Non-name artefacts on disk.** Account-context client labels and certificate labels are stored in the real DB and in gitignored reports (`phase8_exclusions.json`, `cert_date_request.csv`); they are never served.
8. **Keyword overlap.** Some generic workbook header words coincide with words in the ontology's own descriptions served by `/api/skills`; those are governed YAML text, not workbook data.
