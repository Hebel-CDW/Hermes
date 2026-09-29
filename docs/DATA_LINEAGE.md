# Data Lineage — Project Hermes V2

**Classification:** Internal, Confidential
**Verified against:** live code on 2026-09-15. All example values are synthetic.

Answers: *where did this number come from, and what happened to it on the way?*

---

## 0. The two independent tracks

Hermes has **two ingestion tracks that never merge**. This is the single most important fact
about its data model, and the reason the 2025 Excel is handled separately.

```
TRACK A — SCORING                         TRACK B — BASELINE (validation only)
─────────────────────────                 ──────────────────────────────────────
tickets / certs / declared                Skill_Matrix_2025.xlsx
        │                                         │
        ▼                                         ▼
  evidence_staging                        baseline_assessments
        │                                 account_context
        ▼                                 cert_staging
   skills_matrix                                  │
        │                                         │
        ▼                                         ▼
  ranking / gaps  ◄──── NO EDGE ────────  baseline_agreement.py (offline report)
        │
        ▼
  human decision
```

**The missing edge is the design.** `baseline_assessments` has no read path into
`merge_evidence`, `rank_candidates`, or `compute_gaps`. Manager ratings **grade** the engine;
they never **train** it. Enforced by `tests/guardrails/test_baseline_isolation.py`.

---

## 1. Source

| Source | Classification | Location | Status |
|---|---|---|---|
| `pilot_population.json` | **SYNTHETIC** | `data/fixtures/` (committed) | Active — 5 people, E1001–E1005 |
| `Skill_Matrix_2025.xlsx` | **REAL** | `data/source/` (gitignored) | Active — 22 sheets, 310 people |
| `Project_Hermes_Technical_Skills_Collection_Template.xlsx` | **REAL** | `data/source/` (gitignored) | Reference only |
| ServiceNow / LMS / HR connectors | **REAL** | `POST /api/ingest/tickets`, `POST /api/certs/{id}/date` + `/promote` | Identity-gated API (one team / known `employee_id`). Power Platform flows remain stubs that should call these routes. |

> Track A tickets can now be ingested through `POST /api/ingest/tickets` for identities
> already in `identity_map`. LMS-style certificates promote only after a human supplies
> `earned_at`. The 2025 workbook remains Track B.

---

## 2. Ingestion

| Track | Entry point | Reads | Writes |
|---|---|---|---|
| A | `scripts/ingest_fixtures.py` | `pilot_population.json` | `identity_map`, `identity_vault`, `evidence_staging`, `skills_matrix`, `demand_signals`, `role_profiles`, `org_edges` |
| B | `scripts/phase8/ingest_baseline.py` | `Skill_Matrix_2025.xlsx` | `baseline_assessments`, `account_context`, `skill_aliases` |
| B | `scripts/phase8/ingest_certificates.py` | `Certificates` sheet | `cert_staging` (`earned_at = NULL`) |

**Secret boundary.** Track B calls `require_real_data_ingest_secret()`, which **refuses to run in
`HERMES_TEST_MODE`**. Real people may not be tokenised with the repository's published fixture
secret. Track A may run in test mode — no real person is involved.

---

## 3. Abstraction (the only way in)

**Code:** `IdentityAbstractionGate.abstract_record` → `HermesService.abstract`

```
raw record  {employee_id: "E1001", name: "Alex Rivera", ...}
        │
        │  1. reject protected attributes at ANY nesting depth  → ValueError
        │  2. coded_identity = "EMP-" + HMAC-SHA256(secret, lower(key))[:8]
        │  3. strip IDENTITY_PII_FIELDS from the record
        │  4. display name → identity_vault ONLY
        ▼
coded record  {coded_identity: "EMP-a1b2c3d4", ...}
```

| Table | Holds | Who may read it |
|---|---|---|
| `identity_map` | `coded_identity` ↔ irreversible `source_hash` | pipeline |
| `identity_vault` | `coded_identity` → **display_name** | `IdentityResolutionGateway` only |

**Downstream of this line, no component sees a real name.** The vault is joined exactly once,
by the resolution gateway, for a shortlisted candidate, by the manager who owns the request,
rate-limited to 10/min, and written to the audit ledger.

> **Track B caveat.** Phase 8 tokenises on the **person's name** (no employee id exists in the
> workbook), so two people sharing a name collide into one identity, and a spelling change
> creates a new one. Recorded in the readiness report.

---

## 4. Normalisation

### Track A — taxonomy keyword match
`SkillsTaxonomy.match_keywords(text)` → `skill_id[]`. A ticket matching no keyword produces no
evidence. There is no fuzzy fallback.

### Track B — label and scale normalisation

```
raw_label "Kubernetes Admin"
    │  normalize_label()  → lowercase, collapse whitespace, "&"→"and", strip punctuation
    ▼
normalized_label "kubernetes admin"
    │  SkillAliasResolver.resolve()
    ▼
┌─ exact ontology match ──────────→ skill_id, mapped_by="auto",  confidence 1.0
├─ approved alias row ────────────→ skill_id, mapped_by="human", stored confidence
└─ no match ─────────────────────→ skill_id = NULL, mapped_by="pending"   ← STOPS HERE
```

**Pending labels never become skills.** They are persisted for human curation and are invisible
to scoring. Today **100% of the 12,697 baseline rows are `pending`** — which is why the agreement
harness reports 0 overlaps. That is the guardrail working, not a bug.

Rating normalisation is `phase8/normalize.py` (`SCORING_SPECIFICATION.md` §7): `0.0 → NULL`
(not assessed), Collab 1–4 → 1,2,4,5, five-point pass-through.

### Excluded at the boundary

| Label class | Destination | Code |
|---|---|---|
| Client / account names | `account_context` — **never** a skill | `is_client_name_label` |
| Soft skills | dropped + logged | `EXCLUDED_ASSESSMENT_FIELDS` |
| `culture fit` | `CultureFitForbiddenError`; stripped with an explicit log entry at full-workbook ingest | `classify_assessment_column` |

---

## 5. Evidence

**Table:** `evidence_staging`

| Column | Example | Note |
|---|---|---|
| `evidence_id` | `INC001:container_orchestration` | deterministic, idempotent upsert key |
| `coded_identity` | `EMP-a1b2c3d4` | never a name |
| `skill_id` | `container_orchestration` | canonical only |
| `evidence_type` | `demonstrated` | CHECK-constrained |
| `proficiency` | `4` | CHECK 1–5 |
| `occurred_at` | `2026-07-01T00:00:00+00:00` | ISO-8601 UTC, **never invented** |
| `source_ref` | `INC001` | ticket number / cert code |
| `payload_json` | `{"matched_keywords":["kubernetes"],"source_ref":"INC001"}` | **whitelisted keys only** |

**Guardrail 12 is structural.** `db.stage_evidence` copies only
`matched_keywords`, `source_ref`, `manager_confirmed`, `reopen`, `escalation` into
`payload_json`. Ticket text cannot reach the database even if a caller passes it.

**Missing dates stop the pipeline; they are not filled in.** `cert_staging` rows with
`earned_at = NULL` never become evidence; a human must complete `cert_date_request.csv`.

---

## 6. Inference

**Code:** `SkillInferenceEngine.merge_evidence`

```
evidence_staging (all rows)
        │  group by (coded_identity, skill_id)
        │  drop declared-without-manager-confirmation
        ▼
per group →  proficiency   (type-weighted vote + demonstrated-mode override)
             confidence    (0.35 × distinct evidence types, +0.20 demo∧cert)
             volume_score  (1 - e^(-0.35 × n_demonstrated))
             freshness     (mean of 0.5^(days/half_life))   ← applied ONCE
```

Full derivations and reasons: `SCORING_SPECIFICATION.md` §2–§4.

---

## 7. Matrix

**Tables:** `skills_matrix` (current) + `skills_matrix_history` (point-in-time)

`replace_skills_matrix` is a full recompute: it closes open history rows (`valid_to`), deletes
`skills_matrix`, and re-inserts. Every row carries `scoring_config_version` and
`computation_run_id`, so any stored score can be traced to the constants and the run that
produced it.

```
skills_matrix row:
  EMP-a1b2c3d4 | container_orchestration | 4 | conf 0.90 | fresh 0.80 | vol 0.70
               | evidence_ids ["INC001:…","cert-CKA-E1001"]
               | scoring_config_version 5a35863a05c7
               | computation_run_id <uuid4>
```

> **AMBER.** `computation_run_id` is a `uuid4()`, so it identifies a run but is not a content
> hash of its inputs — an identical re-merge yields a different id.

---

## 8. Ranking

**Code:** `FitnessGapEngine.rank_candidates`

```
skills_matrix  +  role/request requirements
               +  availability.allocation
               +  taxonomy relations (adjacency)
        │
        ▼
per candidate → reasoning_detail{skill → full operand trace}
                calculation{coverage, allocation, versions, run id, formula}
        │  exclude: no evidence | below_min_coverage | missing_critical_skill
        │  sort (-fitness_score, coded_identity)   ← deterministic
        │  cap at min(requested, 10)
        ▼
shortlist (coded identities only)  +  excluded_candidates[{coded_identity, reason}]
```

**Inputs that are structurally absent here:** `baseline_assessments`, `account_context`,
`staffing_requests` history, any protected attribute, any name.

---

## 9. Decision (human, terminal)

```
POST /api/identity/resolve        → vault join, owner-gated, rate-limited, audited
POST /api/staffing/{id}/decision  → accepted | rejected | overridden
```

Written to `staffing_requests`: `status`, `approved_by`, `decided_at`,
`chosen_coded_identity`, `engine_rank_of_choice`, `rejection_reason`, `override_note`.

**`engine_rank_of_choice` is the disagreement metric** — it records when a manager picked
someone other than rank 1. It is deliberately **write-only with respect to scoring**: nothing
reads `staffing_requests` back into the engine. Guardrail 8, stamped into every decision's
audit payload as `never_score_on_historical_staffing_decisions`.

Hermes never assigns work. The pipeline terminates in a human.

---

## 10. Audit lineage

Every stage appends to `audit_ledger` with `prev_hash`/`row_hash` hash-chaining:

| Event | Emitted by |
|---|---|
| `evidence_ingestion` | `HermesService.abstract` |
| `inference_computation` | `HermesService.stage_and_merge` |
| `fitness_ranking` | `FitnessGapEngine.rank_candidates` |
| `gap_computation` | `FitnessGapEngine.compute_gaps` |
| `identity_resolution` | `IdentityResolutionGateway` |
| `staffing_decision` | `HermesService.decide` |
| `gap_admin_access` | `/api/fitness/gaps` (admin path) |
| `evidence_contest` | `/api/me/contest` |

Verified by `scripts/verify_audit_chain.py`.

Chain order is a monotonic `seq` column allocated inside a `BEGIN IMMEDIATE` transaction and
protected by a unique index (`UX_audit_seq`). This replaced `(created_at, event_id)` ordering,
which produced false mismatches for same-timestamp writes (`ARCHITECTURE_REVIEW_V2.md §G-2`,
regression-tested in `tests/unit/test_audit_chain_ordering.py`). Pre-V2 ledgers are backfilled
in insertion order on first open; the existing 13k-event Phase 8 ledger still verifies.

> **AMBER.** Hash-chained SQLite, **not** external WORM storage. Anyone with write access to the
> database file can rewrite the whole chain consistently; the chain detects partial tampering,
> not a full rewrite.

---

## 11. Data classification (used throughout the demo and reports)

| Label | Meaning | Where |
|---|---|---|
| **REAL DATA** | Actual employees / client accounts | `data/source/*.xlsx`, `hermes_phase8.db`, `config/client_names.txt` — all gitignored |
| **BASELINE DATA** | 2025 manager assessments — validation only, never scored | `baseline_assessments` |
| **SYNTHETIC DATA** | Invented people for tests/CI | `data/fixtures/pilot_population.json` (E1001–E1005) |
| **DEMO DATA** | Deterministic SVP walkthrough dataset | see `docs/SVP_DEMO_GUIDE.md` |

Committed artifacts derived from REAL sources are redacted: `candidate_skills.csv` carries
`[REDACTED_ACCOUNT]` markers; `manager_variants.csv` and all `.db` files are gitignored.

---

## 12. Reverse lookup — "where did this number come from?"

Given a `fitness_score` on screen:

1. `calculation.computation_run_id` → which matrix run
2. `calculation.scoring_config_version` → which constants (`SCORING_SPECIFICATION.md` §1)
3. `reasoning_detail[skill].evidence_ids` → which `evidence_staging` rows
4. `reasoning_detail[skill].source_refs` → which tickets / certs
5. `evidence_staging.occurred_at` + `half_life_days` → the freshness figure
6. `skills_matrix_history` filtered by run id → the matrix as it stood
7. `audit_ledger` filtered by `request_id` → who asked, who resolved, who decided

Every link is a stored column. No step requires reading source code.

---

## 13. V2 hardening controls on this lineage (added 2026-09-16)

| Control | Where | Effect on lineage |
|---|---|---|
| **Database trust metadata** | `shared/db_trust.py`, `hermes_meta` table | Every database records `data_classification` (`synthetic`/`real`) and a keyed fingerprint of the identity secret. The API refuses (503) a database with no metadata, a secret mismatch, a synthetic DB containing real-data tables, a real DB in test mode, or **any** identity reproducible from a published secret. |
| **Quarantine** | `data/quarantine/hermes_phase8.UNTRUSTED.db` | The pre-V2 Phase 8 database (310/310 reversible tokens) is out of every default path and refused if opened. |
| **Real-data secret policy** | `shared/secrets.py` | Real ingestion refuses test mode, missing/short/low-variety secrets, and the published fixture secrets **even without the test-mode flag**. `promote_certs.py` requires an explicit `--mode`. |
| **Server-derived principals** | `shared/auth.py`, `shared/demo_identities.py` | Tokens carry only `sub`. Roles and coded identity are looked up server-side on every request; tokens carrying role/identity claims are rejected as forged. |
| **Request ownership** | `db.save_staffing_request`, `service.rank/decide` | The requester is written once; re-ranking, resolving, or deciding someone else's request is refused (403) atomically in SQL. |
| **Decision governance** | `service.decide` | Decisions must come from the owner, on an open request with a shortlist, naming a shortlisted, non-excluded candidate. Exclusions are persisted with the request (`excluded_json`). |
| **External audit anchor** | `db.anchor_path()`, `_verify_anchor` | After each append, `{seq, chain_head, event_count}` is written (HMAC-signed when a key is available) outside the database file. Verification now detects latest-event deletion, full truncation, and a recomputed chain. Place anchors on separate storage with `HERMES_AUDIT_ANCHOR_DIR`. |
| **Ontology gate on evidence** | `service.stage_and_merge`, `SkillInferenceEngine.merge_evidence` | Evidence for a skill outside the ontology is rejected before staging (422 at the API). |
