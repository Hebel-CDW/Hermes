# V2 Readiness Report — Project Hermes (SVP demo build)

**Classification:** Internal, Confidential
**Date:** 2026-09-16
**Scoring config version:** `5a35863a05c7`
**Status:** **SVP-demonstrable engineering prototype. Not production-ready.**

> Every GREEN line was verified by execution on 2026-09-16. Commands and tests are named.

---

## 1. Validation run

| Check | Command | Result |
|---|---|---|
| Test suite | `python -m pytest -q -p no:cacheprovider` | **301 passed, 0 failed, 0 errors, 0 skipped** (207 before hardening; 77 at first audit) |
| Coverage gate | `--cov=… --cov=phase8 --cov-fail-under=85` | **91.68%** — gate passes |
| Demo | `python -m scripts.demo_svp --verify` (run twice) | DETERMINISM OK + SAFEGUARDS OK, both runs |
| Demo, separate processes | two `--json` runs | byte-identical transcripts |
| Independent scoring | recomputed from raw `evidence_staging` rows + ontology YAML, no engine imports | 0.1196 = engine 0.1196 |
| Frontend | `npx tsc --noEmit -p tsconfig.app.json`; `npm run build` | pass; pass |
| Bundle scan | secrets, vault fields, DB/workbook/blocklist names, JWTs, real names, client labels | clean (see §6 caveat) |
| Live API smoke | uvicorn, synthetic DB with strong synthetic secret, **not** test mode | **51/51** checks |
| CI audits | leakage, fairness, audit chain, coverage report, impact audit, dashboard, CLI query | all pass |
| Real workbook | parsed in memory (no DB writes) | counts in §5 |

---

## 2. RED — genuine blockers

| # | Item | Why | Clears when |
|---|---|---|---|
| R-1 | **The V2 work is uncommitted** | Everything in this report exists only in the working tree. `HEAD` (`e45d72b`) still contains the unauthenticated file read, the request hijack, the token stub, and the test-mode secret defects. A clean clone reproduces all of them. | The working tree is committed and the demo is run from that commit. |

No other item blocks a clearly framed prototype demo. The AMBER items block **production**.

---

## 3. AMBER — prototype limitations (stated, not hidden)

| # | Limitation |
|---|---|
| A-1 | **Local authentication.** A local issuer for five synthetic principals; no real identity provider, MFA, or session revocation. Disabled outside local/test mode (all requests are then refused). |
| A-2 | **Incomplete ontology mapping.** 5 governed skills vs 691 distinct real skill labels; **0 mapped**. Real ratings are never scored; synthetic data is the only scored population. |
| A-3 | **Keyword-based skill inference.** Deterministic 11 depth / 6 surface terms; precision on real ticket text unmeasured. No ML, no LLM. |
| A-4 | **Prototype infrastructure.** SQLite, single process, in-memory rate limiter, no live source connectors (ServiceNow/LMS/HR are stubs). |
| A-5 | **Audit anchor scope.** Tamper-evident application audit chain with external integrity anchor — not WORM. Defeated by an attacker who can rewrite both the DB and the anchor and holds the anchor key. The anchor defaults to beside the DB; set `HERMES_AUDIT_ANCHOR_DIR` to separate storage. Concurrent anchor updates are best-effort (never move backwards). |
| A-6 | **Quarantined real database still on disk.** `data/quarantine/hermes_phase8.UNTRUSTED.db` (gitignored, refused by the application) holds 310 reversible real identities; the data owner should securely delete it or rebuild with a strong secret. |
| A-7 | **Default run ids.** Pinned runs are reproducible; default `stage_and_merge` still mints `uuid4()` run ids (reported as `bootstrap_runs_with_uuid_ids` in the demo). |
| A-8 | **Name-keyed Phase 8 identities.** The workbook has no employee id; same-name people merge. |
| A-9 | **`decay_class` labels vs overrides.** Two skills carry explicit half-life overrides that differ from their class label; the inspector always shows the half-life actually used. |
| A-10 | **UI not browser-automated.** Excluded-candidate panel and score derivation verified by typecheck, build and API payloads only; rehearse the click path. `web/dist` is untracked — run `npm run build` first. |
| A-11 | **Hygiene.** Unused `availability`/`cold_start_ids` parameters, `setup.cfg`, `shared/demand.py` (0% coverage), `phase8/workbook.py` 71%, `phase8/normalize.py` 73%. |
| A-12 | **Legacy local DB.** `data/hermes_validation.db` has no trust metadata and is refused; neither the demo nor CI uses it. |

---

## 4. GREEN — working and verified

| Capability | Evidence |
|---|---|
| **Deterministic scoring** — exact golden scores; version pinned | `test_scoring_golden.py` |
| **Calculation transparency** — every operand per skill + candidate derivation; independently recomputed | `test_scoring_inspector.py`, §1 |
| **Config-hash fidelity** — version changes iff scores can change, for every env parameter; effective half-lives and adjacency discount versioned; invalid config fails loudly | `test_v2_integrity.py` |
| **Baseline isolation** — service path, API path, live demo safeguard | `test_governance_regressions.py`, demo |
| **Identity abstraction** — coded until governed resolution | demo tests, smoke |
| **Request ownership** — hijack refused for rank / resolve / decision; owner unaffected; atomic in SQL | `test_v2_api_hardening.py`, smoke |
| **Decision governance** — owner only; 404 unknown; 409 already decided; 422 for no shortlist / not shortlisted / excluded / missing candidate; forged `approved_by` rejected | same |
| **RBAC** — role × endpoint matrix; managers see only direct reports | same |
| **Anti-impersonation** — token accepts only `sub`; validly signed tokens with role/identity claims rejected; `/me` bound server-side | same |
| **Secret hardening** — published secrets rejected outside test mode, and for real data even without the flag; `promote_certs` requires an explicit mode | `test_v2_integrity.py`, `test_tier0.py` |
| **Unsafe DB protection** — no metadata / reversible identities / secret mismatch / mixed data → 503 | same |
| **Audit integrity** — edit, middle deletion, latest deletion, full deletion, recomputed chain, missing anchor, forged anchor all detected | `test_v2_integrity.py`, `test_audit_chain_ordering.py` |
| **File traversal** — 12 raw / encoded / double-encoded / backslash / absolute / assets variants over live HTTP | `test_spa_path_traversal.py`, smoke |
| **Input validation** — unknown skills, bad levels, empty maps, coverage > 1, malformed ids → 422 | tests, smoke |
| **Phase 8 validation** — coded rejections, group averages, out-of-range/fractional rejected, soft skills / culture fit / client labels excluded, no names in report, governed certificate mapping | `test_workbook_parsers.py`, `test_taxonomy_governance.py`, §5 |
| **Synthetic demo** with live safeguards asserted by `--verify` | demo |

---

## 5. Real workbook (in memory, counts only)

| Metric | Value |
|---|---|
| Accepted cells | 12,852 |
| Rejected rows | 392 — `non_numeric_cell` 198, `missing_name` 136, `fractional_average` 38, `group_or_section_header` 17, `section_header` 1, `out_of_range_value` 1, `deferred_to_cert_workstream` 1 |
| Unregistered rejection codes | 0 |
| Ratings | L1 2,530 · L2 1,875 · L3 1,870 · L4 3,485 · L5 241 · not assessed 2,851 |
| Distinct skill labels | 691 — **0 mapped** (all 21 sheets flag `all_labels_pending`) |
| Soft-skill / culture-fit / client labels in skill cells | 0 / 0 / 0 |
| Exclusion log | soft skill 220 · culture-fit column 20 · client/account 11 |
| Certificates | 427 cells → 5 exact cert-code matches, 422 unmapped |
| Real names in data-quality report | 0 |

---

## 6. Bundle-scan caveat

A naive substring scan matched one real vault entry: a single four-letter word that occurs only
inside a React CSS property name in `react-dom`. It is not a whole-word match and originates in a
third-party library, not Hermes data. Multi-word real names found: 0 of 274.

---

## 7. Demo command

```bash
source .venv/bin/activate
python -m scripts.demo_svp --verify
```
