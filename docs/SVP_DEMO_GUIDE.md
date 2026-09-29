# SVP Demo Guide — Project Hermes V2

**Classification:** Internal, Confidential
**Audience:** a highly technical reviewer who will challenge every number
**Runtime:** ~2 minutes for the scripted path; ~10 minutes with the UI

---

## 0. Before you start — say this first

> "Hermes is a **recommendation-only** prototype. It is local-first. Nothing here is
> production. Everything you are about to see runs on **synthetic data**; I will show you
> the real-data path separately and tell you exactly where it is blocked."

Set that frame in the first thirty seconds. The fastest way to lose a technical audience is
to let them discover a limitation you did not volunteer.

---

## 1. Data classification — know which is on screen

| Label | What it is | Where it lives | In this demo? |
|---|---|---|---|
| **SYNTHETIC DATA** | Invented people E1001–E1005, invented tickets/certs | `data/fixtures/pilot_population.json` (committed) | ✅ **This is the demo** |
| **DEMO DATA** | The pinned run over that fixture: `as_of=2026-09-01`, `run=demo-run-0001` | `scripts/demo_svp.py` | ✅ |
| **REAL DATA** | 310 actual colleagues, actual client accounts | `data/source/*.xlsx`, `hermes_phase8.db` — **gitignored** | ❌ shown only as counts |
| **BASELINE DATA** | 2025 manager assessments | `baseline_assessments` — **never scored** | ❌ discussed, not scored |

**If asked "is this real data?" the answer is no, and that is deliberate.** The scoring path
has never run on real employees, because the real labels are not yet governed (§7).

---

## 2. Run it

```bash
cd /Users/hebel/Hermes
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export HERMES_TEST_MODE=1          # synthetic fixtures only

python -m scripts.demo_svp          # the 14-step walkthrough
python -m scripts.demo_svp --verify # prove it is reproducible
```

`--verify` runs the whole pipeline **twice into two separate databases** and asserts the
transcripts are byte-identical:

```
DETERMINISM OK - two independent runs produced identical transcripts
  scoring_config_version: 5a35863a05c7
  computation_run_id:     demo-run-0001
SAFEGUARDS OK   - baseline isolation, input rejection, identity governance,
                  excluded-candidate refusal, audit anchor, real-data refusal
```

`--verify` fails (exit 1) if any safeguard in §3a does not behave as expected. The demo runs
in a temporary directory and removes it; it never rewrites tracked files.

### Why it is deterministic

Two things would otherwise drift, and both are pinned:

| Source of drift | Pinned to |
|---|---|
| `freshness` decays against wall-clock time | `AS_OF = 2026-09-01T00:00:00Z` |
| `computation_run_id` is a `uuid4()` | `RUN_ID = "demo-run-0001"` |

Everything else is already deterministic: ranking ties break on `coded_identity`, and no
other wall-clock value enters a score.

Regression-tested by `tests/e2e/test_demo_determinism.py`.

---

## 3. The 14 steps

### 1–2 · Incoming request and required skills
A Kubernetes migration needing `container_orchestration ≥ 3` and `azure_networking ≥ 2`.
Levels are ontology levels with **behavioural definitions** (`taxonomy/skills_ontology.yaml`) —
not opinions.

### 3 · Evidence collection
Counts by type. Say plainly: **only `matched_keywords` and `source_ref` persist — never
ticket text** (`db.stage_evidence` whitelists five keys). Enforced by
`tests/security/test_tier0.py::test_no_ticket_excerpt_in_db`.

### 4 · Skill inference
The matrix, stamped with `computation_run_id` and `as_of`. Each row carries four separate
numbers: `proficiency`, `confidence`, `volume_score`, `freshness`.

> **If challenged "isn't confidence just evidence count?"** — no, and this is the point.
> `confidence` measures **cross-type agreement** (0.35 × distinct evidence types, +0.20 when
> demonstrated and certified agree). `volume_score` measures **quantity**
> (`1 − e^(−0.35·n_demo)`, saturating). Ten tickets and no certificate is still *one kind* of
> evidence. See `SCORING_SPECIFICATION.md` §4.3–4.4.

### 5 · Candidate ranking
Shortlist plus — critically — `excluded_candidates` with machine-readable reasons:

```json
"excluded_candidates": [
  {"coded_identity": "EMP-666c8943", "reason": "no_evidence_on_any_required_skill"}
]
```

> **"Why was that person not shortlisted?"** has an answer. Exclusion reasons used to be
> computed and discarded.

### 6 · Calculation inspector  ← **the centrepiece**

This is the step that wins or loses a technical audience. The payload contains every operand:

```json
"container_orchestration": {
  "status": "matched",
  "required_level": 3,  "actual_level": 4,  "level_ratio": 1.0,
  "confidence": 1.0,    "volume_score": 0.5034,  "freshness": 0.475,
  "decay_class": "fast", "half_life_days": 120.0,
  "adjacency_discount": 1.0, "adjacency_source_skill": null,
  "contribution": 0.239115,
  "evidence_ids": ["INC001:container_orchestration", "...", "cert-CKA-E1001"],
  "source_refs": ["CKA", "INC001", "INC002", "declared"]
}
```

**Do the arithmetic out loud:**

```
1.0 × 1.0 × 0.5034 × 0.475 × 1.0 = 0.239115      ← contribution
0.239115 / 2 required skills      = 0.119557      ← mean_contribution
0.119557 × 1.00 allocation_mult   = 0.1196        ← fitness_score  ✓
```

The `formula` string ships **in the payload**, and `calculation` carries
`scoring_config_version` and `computation_run_id`. A reviewer can reproduce the score without
reading source code — which is the stated requirement.

Anticipate three challenges:

| Challenge | Answer |
|---|---|
| "Why is `level_ratio` capped at 1.0? Level 4 beat level 3 by nothing." | Deliberate fairness choice. Uncapped, the same experts win every request and nobody else develops — the concentration `scripts/impact_audit.py` measures. Hermes answers *"who meets this need?"*, not *"who is most senior?"* (`SCORING_SPECIFICATION.md` §5.1) |
| "Freshness 0.475 — is decay applied twice?" | No. Applied **once**, on the skill record. The level vote uses type weight only (explicit comment at `skill_inference/engine.py:198`); the fitness engine multiplies by it once. |
| "`decay_class: fast` but `half_life_days: 120`, not 90?" | Correct catch. An explicit `freshness_half_life_days` override wins over `decay_class`. The inspector always shows **the number actually used**. The label inconsistency is logged AMBER in the readiness report. |

### 7 · Evidence drill-down
`evidence_ids` and `source_refs` — ticket numbers and cert codes, scoped to **that candidate**.

### 8 · Identity remains coded
Everything so far is `EMP-` + 8 hex. Nothing has touched `identity_vault`.
`test_identity_stays_coded_until_the_resolution_step` asserts this mechanically.

### 9 · Controlled identity resolution
Names appear **only here**, gated by four controls: requester owns the request; shortlist-only;
10/min rate limit; written to the audit ledger.

### 10 · Manager decision
`accepted` with `engine_rank_of_choice = 1`. Stress the guardrail: the decision is recorded
**for audit only** and is never read back into scoring. `engine_rank_of_choice` is the
disagreement metric — it tells you when managers override the engine, and it is deliberately
not a feature.

### 11 · Audit event
Event counts by type and `chain_verified: true` (hash-chain replay).

> **Say exactly this:** "Tamper-evident application audit chain with external integrity
> anchor." Verification detects edited events, deleted events (including the most recent ones
> and a fully emptied ledger), and a chain recomputed end-to-end. It is **not** WORM: an attacker
> who can rewrite both the database and the anchor file (and holds the signing key) is not
> stopped. In production the anchor directory (`HERMES_AUDIT_ANCHOR_DIR`) must live on storage the
> application's database writer cannot modify.

### 12–13 · Skill gap and learning recommendation
Gaps ordered by `demand_impact = demand_weight × deficit` — organisational value, not gap size.
Note the documented asymmetry: **ranking applies adjacency, gaps do not**. For staffing,
"close enough" helps; for a development plan, an adjacent skill is not the one to learn.

### 14 · Matrix history / recalculation
Two pinned runs, `recalculation_is_stable: true`, and — stated plainly —
`bootstrap_runs_with_uuid_ids`, because the bootstrap ingest still mints a `uuid4()`.

---

## 3a. Safeguards section (printed after step 14)

Every value is a status code, reason code or count — no names — and each is asserted by
`--verify`:

| Safeguard | Expected |
|---|---|
| Baseline isolation — manager ratings injected for every candidate, re-rank | ranking unchanged |
| Invalid input — unknown skill, level 6/0/3.5/"3", empty requirements, coverage 1.5 | 422 each |
| Unauthenticated rank | 401 |
| Employee → rank / list identities / create identity | 403 each |
| Second manager → re-rank / resolve / decide the first manager's request | 403 each |
| Token request asserting `roles` | 422 |
| Owner resolve | 200 |
| Decision naming an excluded candidate | 422 `candidate_excluded` |
| Latest audit event deleted (on a copy) | detected |
| Real ingest in test mode · published secret without the flag | REFUSED · REFUSED |
| Database without trust metadata | `missing_trust_metadata` |
| Unmapped workbook label | `pending`, `skill_id = null` |

### Demo principals (synthetic registry)

| Principal | Role | Synthetic identity |
|---|---|---|
| `demo-manager` | manager | E1001 (E1002, E1003 report to them) |
| `demo-manager-2` | manager | E1004 — used to prove request ownership |
| `demo-employee` | employee | E1003 |
| `demo-employee-2` | employee | E1005 |
| `demo-admin` | admin | none |

The token endpoint accepts only `{"sub": "<principal>"}`. Roles and coded identity are derived on
the server; tokens carrying role or identity claims are rejected.

---

## 4. The UI path (optional)

```bash
cd web && npm ci && npm run build
cd .. && uvicorn api.main:app --port 8000
```

Open <http://127.0.0.1:8000/> → **Staff** → Rank → expand a skill → **SCORE DERIVATION**.
The UI renders the same operands and the same arithmetic line as the JSON, plus the candidate id,
run id and config version. Below the shortlist, **EXCLUDED** lists each excluded coded identity
with its reason.

> The server needs trusted synthetic data first: `HERMES_TEST_MODE=1 python -m
> scripts.ingest_fixtures` (writes trust metadata), then start uvicorn in the same mode.
> In-browser rendering was verified by build + typecheck only; rehearse the click path.

Then `/matrix` for the history scrubber and `/me` for the employee evidence-and-contest view.

---

## 5. The real-data path — show it, do not run it

```bash
# Requires a genuine secret; refuses to run in test mode.
unset HERMES_TEST_MODE
export IDENTITY_MAP_SECRET='<strong unique secret>'
python scripts/phase8/ingest_baseline.py data/source/Skill_Matrix_2025.xlsx data/hermes_phase8.db
```

Demonstrate the refusal instead — it is more persuasive than the success:

```bash
HERMES_TEST_MODE=1 python scripts/phase8/ingest_baseline.py data/source/Skill_Matrix_2025.xlsx /tmp/x.db
# RuntimeError: Refusing to tokenise real data in HERMES_TEST_MODE. Coded identities
# would be derived from the published fixture secret and be trivially reversible.
```

**Say why:** coded identities are `HMAC(secret, name)`. Deriving them from a secret committed
to the repository would make the pseudonymisation reversible by anyone with the source. That
is exactly what the earlier code did, and the existing `hermes_phase8.db` must be rebuilt
under a real secret before it is trusted.

---

## 6. What to show about the real workbook

Numbers only — no names, no client accounts:

| Metric | Value |
|---|---|
| Sheets | 22 |
| People discovered | 310 |
| Baseline rows ingested | 12,496 |
| Distinct labels found | 752 |
| Labels clustered into candidates | 682 |
| **Labels mapped to a canonical skill** | **0** |
| Baseline↔engine agreement overlaps | **0** |

---

## 7. The hardest question, and the honest answer

> **"Your baseline agreement report shows zero overlaps. So you've validated nothing?"**

**"Correct — and that is the system working, not failing."**

All 12,697 baseline labels resolved to `pending`. Hermes refuses to fuzzy-match a raw
spreadsheet label onto a canonical skill, because a wrong mapping silently corrupts every
downstream score and nobody would notice. The ontology has 5 governed skills; the workbook has
752 ungoverned labels. Until a human approves mappings (`mapped_by='human'`), those labels do
not exist as far as scoring is concerned.

The unblock is human taxonomy curation, tracked in `docs/phase8/BLOCKED.md`. The engineering to
*consume* approved mappings is built and tested
(`tests/guardrails/test_taxonomy_governance.py`) — it is waiting on governance, not on code.

---

## 8. Other likely challenges

| Question | Where the answer lives |
|---|---|
| "Show me every formula." | `docs/SCORING_SPECIFICATION.md` — every formula cites a `file:line` |
| "Could a stale doc be lying to me?" | `test_default_config_version_is_pinned` fails if constants change without updating the spec |
| "Where does this number come from?" | `docs/DATA_LINEAGE.md` §12 — 7-step reverse lookup, every link a stored column |
| "Why does this file exist?" | `docs/FILE_CATALOG.md` |
| "What's broken?" | `docs/V2_READINESS_REPORT.md` — RED/AMBER items listed first |
| "Does an LLM decide scores?" | No. No model is consulted anywhere in the scoring path. The UI may only restate engine JSON (`scripts/narrate.py` refuses to print a candidate without evidence). |
| "How do you prevent bias?" | No protected-attribute field exists in the schema (`scripts/fairness_audit.py` greps it); `level_ratio` is capped to avoid expert concentration; `volume_score` saturates so ticket throughput can't dominate; `scripts/impact_audit.py` reports Gini concentration. |
| "What if data is missing or ambiguous?" | Missing date → row stays out of the matrix. Ambiguous label → `pending`. Missing skill → `status: "missing"`, contributes 0 but still counts in the denominator. Out-of-range rating → rejected with `out_of_range_value`. |

---

## 9. Do not claim

- ❌ "Production ready" — it is a local-first prototype
- ❌ "Validated against manager assessments" — 0 overlaps today
- ❌ "Integrated with ServiceNow/LMS" — connectors are stubs
- ❌ "WORM audit" — hash-chained SQLite
- ❌ "Authenticated" / "SSO" — local issuer for five synthetic principals; no real identity provider
- ❌ "Runs on real data" — the scoring path has only ever run on synthetic fixtures

Everything on that list is a real limitation, stated in `docs/V2_READINESS_REPORT.md`.
Volunteering them is what makes the rest of the demo credible.
