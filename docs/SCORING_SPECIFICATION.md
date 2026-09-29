# Scoring Specification — Project Hermes V2

**Status:** Canonical. Supersedes `docs/evidence-merge-rules.md` (which described a superseded algorithm).
**Classification:** Internal, Confidential
**Scoring config version at time of writing:** `9220dcfdfcf3` (was `5a35863a05c7` before the pilot ontology merge; ticket keywords and adjacency fingerprint changed — see `docs/EXCEL_SUNSET.md`)
**Verified against:** live code, by execution, on 2026-09-15.

> **Contract for this document.** Every formula below corresponds to executable code at a
> named `file:line`. If code and this document disagree, **the code is correct and this
> document is a defect** — fix the document and add a test. `tests/unit/test_scoring_golden.py`
> and `tests/unit/test_scoring_inspector.py` mechanically enforce the key claims.

---

## 0. The whole pipeline in one expression

```
fitness(candidate) = mean over required skills of
                       level_ratio × confidence × volume_score × freshness × adjacency_discount
                     × allocation_multiplier
```

Five factors, multiplied. Then averaged across required skills. Then scaled once by availability.
Nothing else enters a score. In particular **none** of the following are inputs:
manager baseline ratings, client/account familiarity, soft-skill assessments, culture fit,
historical staffing decisions, tenure, or any protected attribute.

---

## 1. Configuration — the only tunable constants

**Code:** `src/shared/config.py`

| Field | Default | Env override | Allowed range | Used at |
|---|---|---|---|---|
| `demonstrated_weight` | 0.55 | `HERMES_W_DEMO` | 0–1 | level vote |
| `certified_weight` | 0.30 | `HERMES_W_CERT` | 0–1 | level vote |
| `declared_weight` | 0.15 | `HERMES_W_DECL` | 0–1 | level vote |
| `half_life_fast_days` | 90 | `HERMES_HALF_LIFE_FAST` | 1–36500 | freshness, class `fast` |
| `half_life_medium_days` | 365 | `HERMES_HALF_LIFE_MEDIUM` | 1–36500 | freshness, class `medium` |
| `half_life_slow_days` | 1095 | `HERMES_HALF_LIFE_SLOW` | 1–36500 | freshness, class `slow` |
| `volume_k` | 0.35 | `HERMES_VOLUME_K` | 0.0001–10 | volume score |
| `allocation_weight` | 0.15 | `HERMES_ALLOC_W` | 0–1 | allocation multiplier |
| `adjacency_discount` | 0.5 | `HERMES_ADJACENCY_DISCOUNT` | 0–1 | adjacent-skill credit |
| `min_confidence` | 0.1 | *(not overridable)* | — | confidence floor |
| `min_coverage_ratio` | 0.6 | `HERMES_MIN_COVERAGE` | 0–1 | exclusion floor |
| `max_shortlist_size` | 10 | `HERMES_MAX_SHORTLIST` | 1–10 | shortlist cap |

Values outside the allowed range, or unparseable, raise `ConfigurationError` at load.
`HERMES_HALF_LIFE` (a single global half-life) was **removed**: every ontology skill has a
decay class, so it could never change a score. Setting it now raises instead of being ignored.

### 1.1 Version = hash of values, not a label

```python
version = sha256(canonical_json({
    <every field above except the three class half-lives>,
    "effective_half_lives": {skill_id: half-life actually used, for every ontology skill},
    "taxonomy_fingerprint": sha256(ticket_keywords + adjacency relations per skill),
}))[:12]
```

**Reason.** A free-text version stamp can lie. A hash of the actual values cannot: two runs
with the same version provably used the same constants.

**Invariant (enforced):** the version changes **if and only if** scores can change.
`tests/unit/test_v2_integrity.py::test_version_changes_if_and_only_if_scores_change` checks
every env-overridable parameter against a synthetic scenario sensitive to it.

### 1.2 Why effective half-lives, not the class table

Only the `medium` class is actually reached today: every `fast` and `slow` skill has an
explicit per-skill override. Hashing the raw class values would let `HERMES_HALF_LIFE_FAST`
move the version with no possible score change (the same defect class as the original
`allocation_weight` bug). Hashing each skill's *effective* half-life makes the version move
exactly when a skill's decay changes. Default effective values equal the pre-hardening
constants, so every score is unchanged; only the version string moved.

The original C-3 regression stays pinned by
`test_changing_allocation_weight_changes_both_version_and_score`: before V2, `allocation_weight`
was hashed but unused, so tuning it moved the version while every score stayed byte-identical.

---

## 2. Evidence → proficiency level (demonstrated)

**Code:** `SkillInferenceEngine._demonstrated_level`, `src/skill_inference/engine.py:71-91`

| | |
|---|---|
| **Input** | ticket short-description text, `skill_id`, optional metadata flags |
| **Output** | `ProficiencyLevel` 1–5 |

### Transformation

1. `depth_hits` = count of these 11 terms present in the lowercased text:
   `architecture, cluster, design, migration, outage, p1, production, rollback, sev1, sev2, upgrade`
2. `surface_hits` = count of these 6 terms:
   `access, login, mention, password, reset, unlock`
3. `tier` = strength of the taxonomy keyword that matched:
   - `2` if the matched `ticket_keyword` is multi-word or longer than 12 characters
   - `1` otherwise

### Formula

```
if   depth_hits >= 2 or (depth_hits >= 1 and tier >= 2):  level = 4  (Advanced)
elif depth_hits >= 1 or tier >= 2:                        level = 3  (Proficient)
elif surface_hits and not depth_hits:                     level = 2  (Working)
else:                                                     level = 2 if tier else 1
level = max(1, level - negative_penalty)
```

`negative_penalty` = `+1` if metadata has `reopen`/`reopened`, `+1` if `escalation`/`escalated`.

**Reason.** "Resolved a ticket mentioning Kubernetes" is not evidence of proficiency. A password
reset that mentions a cluster is surface work; a production cluster migration is depth work. The
tier term prevents a single short keyword (`k8s`) from carrying the same weight as a specific
phrase (`container orchestration`). Reopens and escalations are negative signals about the
quality of the resolution, so they lower the ceiling rather than raising it.

**Prototype limitation (AMBER).** This is deterministic keyword heuristics over a fixed
11+6 word list, tuned on pilot fixtures. It is *not* a trained model and its precision on real
ServiceNow text is unmeasured — `docs/validation/keyword-precision.md` reports a fixture-only
figure. No LLM participates in this or any other scoring decision.

---

## 3. Freshness

**Code:** `SkillInferenceEngine.freshness_score` / `half_life_for_skill`, `src/skill_inference/engine.py:132-155`

| | |
|---|---|
| **Input** | `occurred_at`, `skill_id`, `as_of` (default: now, UTC) |
| **Output** | float in `[0, 1]` |

### Formula

```
days      = max(0, (as_of - occurred_at).total_seconds() / 86400)
half      = half_life_for_skill(skill_id)
freshness = clamp(0.5 ** (days / half), 0, 1)
```

### `half_life_for_skill` resolution order

1. `skill.freshness_half_life_days` if set on the ontology entry — **wins outright**
2. else the configured class half-life (`half_life_fast/medium/slow_days`)
3. a skill not in the ontology raises `UnknownSkillError` — it is never decayed with an
   unversioned default (the former hardcoded fallbacks and 180-day default were removed)

### Effective half-lives today (measured, not assumed)

| skill_id | `decay_class` | `freshness_half_life_days` | **Effective** |
|---|---|---|---|
| `container_orchestration` | fast | 120 | **120** |
| `azure_networking` | medium | 120 | **120** |
| `azure_compute` | medium | — | **365** |
| `incident_management` | slow | 365 | **365** |
| `infrastructure_as_code` | medium | — | **365** |

> ⚠️ **Known inconsistency (AMBER).** Because the explicit override wins, `decay_class` is
> *descriptive only* where an override exists. `container_orchestration` is labelled `fast`
> (90d) but decays at 120d; `azure_networking` is labelled `medium` (365d) but decays at 120d.
> The number the engine actually used is always surfaced in the inspector as `half_life_days`,
> so no reviewer is misled by the label — but the ontology should be reconciled. Tracked in
> `docs/V2_READINESS_REPORT.md`.

**Freshness is applied exactly once**, on the skill record (`engine.py:219`). It is deliberately
**not** folded into the level vote (`engine.py:198`) and **not** folded into confidence. The
fitness engine then multiplies by it a single time. Double-decay was a real risk in the earlier
design and is now structurally prevented.

---

## 4. Evidence merge → one skill record

**Code:** `SkillInferenceEngine.merge_evidence` / `_score_group`, `src/skill_inference/engine.py:157-230`

Evidence is grouped by `(coded_identity, skill_id)`. One `SkillRecord` per group.

### 4.1 Admission rule

Declared evidence is **dropped** unless manager-confirmed (`engine.py:164-169`):

```
if evidence_type == DECLARED:
    if manager_confirmed is False:                                                skip
    if manager_confirmed is None and not metadata.get("manager_confirmed", True): skip
```

**Reason.** Self-declared skill with no corroboration is the weakest possible signal and the
easiest to game. It may contribute only once a human has vouched for it.

### 4.2 Proficiency level — type-weighted vote

```
for each evidence item:
    level_scores[item.proficiency] += type_weight(item.type) * item.weight   # NO freshness here
best_level = argmax(level_scores)            # ties broken toward the higher level

if demonstrated evidence exists:
    demo_mode = most common demonstrated level
    if |demo_mode - best_level| <= 1:
        best_level = max(best_level, demo_mode)
```

**Reason.** Weighting by evidence type encodes *demonstrated > certified > declared*. The
demonstrated-mode override means that when the vote is close, real delivered work breaks the
tie upward rather than a certificate dragging the level down. The `<= 1` guard stops a single
outlier ticket from jumping the level by more than one band.

### 4.3 Confidence — cross-type **agreement**, not accumulation

```
type_count = number of DISTINCT evidence types present
confidence = max(min_confidence, min(1.0, 0.35 * type_count))
if DEMONSTRATED and CERTIFIED both present:
    confidence = min(1.0, confidence + 0.2)
```

| Evidence types present | confidence |
|---|---|
| any one type alone | **0.35** |
| demonstrated + declared | **0.70** |
| certified + declared | **0.70** |
| demonstrated + certified | **0.90** |
| all three | **1.00** |

**Reason.** Confidence answers *"how sure are we this skill is real?"* — that is a question about
**corroboration across independent sources**, not about how much of one source we have. Ten
tickets and no certificate is still a single kind of evidence. The demonstrated+certified bonus
reflects that theory and practice agreeing is the strongest corroboration available.

**This is the key separation the V2 brief requires.** Confidence measures *agreement*;
`volume_score` (below) measures *quantity*. They are independent factors, multiplied separately.

### 4.4 Volume score — saturating evidence quantity

```
volume_score = 1 - exp(-volume_k * n_demonstrated)        # volume_k = 0.35
```

| `n_demo` | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 |
|---|---|---|---|---|---|---|---|---|
| `volume_score` | 0.0000 | 0.2953 | 0.5034 | 0.6501 | 0.7534 | 0.8262 | 0.8775 | 0.9392 |

**Reason.** More demonstrated work should increase confidence in the *signal*, but with
diminishing returns — the 20th ticket tells you far less than the 2nd. Saturation prevents
high-ticket-volume roles (service desk) from dominating rankings purely by throughput, which
would be a structural fairness problem. Only **demonstrated** evidence counts: certificates and
declarations do not have a meaningful "volume".

### 4.5 Record freshness

```
freshness = arithmetic mean of per-item freshness across all items in the group
```

**Known limitation (AMBER).** A mean lets many old items dilute one recent one. A
recency-weighted aggregate (e.g. max, or a decayed weighted mean) is arguably more correct.
Changing it would alter every stored score, so it is deliberately deferred and recorded here
rather than silently changed.

---

## 5. Fitness ranking

**Code:** `FitnessGapEngine.rank_candidates` / `_fitness`, `src/fitness_gap/engine.py`

### 5.1 Per required skill

```
record, adjacency_discount, source = lookup(skills, skill_id)

level_ratio  = min(1.0, actual_level / max(1, required_level))
contribution = level_ratio × confidence × volume_score × freshness × adjacency_discount
```

**`level_ratio` is capped at 1.0.** Exceeding the requirement earns no extra credit.

> **Reason.** This is a deliberate fairness choice. Uncapped, a level-5 expert would outrank a
> fully-qualified level-3 on every request, concentrating all work on a few people and starving
> everyone else of development opportunity — the exact dynamic `scripts/impact_audit.py`
> measures via Gini concentration. Hermes answers *"who meets this need?"*, not *"who is most
> senior?"*

### 5.2 Adjacency

**Code:** `_lookup_skill`; versioned config field `adjacency_discount` (default 0.5, `HERMES_ADJACENCY_DISCOUNT`)

| Situation | `adjacency_discount` | `status` |
|---|---|---|
| Exact skill present | **1.0** | `matched` |
| Only a `related_skills` / `relations` neighbour present | **0.5** | `adjacent` |
| Neither | 0.0 (contributes 0) | `missing` |

**Reason.** Someone with Azure Compute evidence is more plausible for a Container Orchestration
request than someone with nothing, but far less certain than direct evidence. Half credit is a
judgement call, held as one named constant so it is auditable and tunable in one place. The
inspector always reports `adjacency_source_skill`, so partial credit can never be mistaken for
direct evidence.

### 5.3 Aggregate

```
mean_contribution     = sum(contributions) / number_of_required_skills
w                     = allocation_weight                      # 0.15
allocation_multiplier = (1 - w) + w * clamp(allocation, 0, 1)   # spans [0.85, 1.00]
fitness_score         = round(mean_contribution * allocation_multiplier, 4)
```

The denominator is **all required skills**, including missing ones. A missing skill contributes
0 to the numerator but still counts in the denominator — so breadth genuinely matters.

**Reason for allocation being a multiplier and not a filter.** A boolean "available?" gate makes
a 90%-allocated expert invisible. A graduated multiplier keeps them rankable but slightly
penalised. The narrow `[0.85, 1.00]` band is deliberate: availability is a *scheduling* concern
and must never outweigh capability evidence.

### 5.4 Exclusion rules (evaluated in order)

| Order | Condition | `exclusion_reason` |
|---|---|---|
| 1 | No evidence on **any** required skill | `no_evidence_on_any_required_skill` |
| 2 | `coverage_ratio < min_coverage_ratio` | `below_min_coverage` |
| 3 | Any `critical_skills` entry unmatched (direct or adjacent) | `missing_critical_skill` |

where `coverage_ratio = matched_skill_count / required_skill_count`.

Excluded candidates are returned in `FitnessResult.excluded_candidates` with a machine-readable
reason. **They are never silently dropped** — "why was X not shortlisted?" is an answerable
question.

### 5.5 Ordering and cap

```
sort by (-fitness_score, coded_identity)          # coded_identity = deterministic tie-break
shortlist = first max(1, min(requested, config.max_shortlist_size, 10))
```

**Reason.** The `coded_identity` tie-break makes ranking **deterministic** — equal scores always
produce the same order, which is required for reproducibility. The hard cap of 10 is a
human-oversight control: a shortlist a manager cannot actually review is not oversight.

---

## 6. Gap computation

**Code:** `FitnessGapEngine.compute_gaps`

```
for each required skill of the target role:
    current = matrix level for (coded_identity, skill_id), else None
    if current is not None and current >= required:  skip      # not a gap
    demand        = demand_weights.get(skill_id, 0.5)
    deficit       = required_level - (current or 0)
    demand_impact = round(demand * deficit, 4)

sort by (-demand_impact, skill_id)
```

| | |
|---|---|
| **Input** | coded identity, `TargetRoleProfile`, skills matrix |
| **Output** | ordered `GapItem[]` |

**Reason.** A learning path should be ordered by *organisational value of closing the gap*, not
by gap size alone. A 1-level gap in a high-demand skill (`0.9 × 1 = 0.9`) outranks a 2-level gap
in a low-demand one (`0.3 × 2 = 0.6`). The `0.5` default for unknown demand is a neutral prior.

> **Documented asymmetry (AMBER).** `compute_gaps` deliberately does **not** apply adjacency.
> Ranking gives partial credit for a neighbouring skill; gaps do not. This is intentional — for
> staffing, "close enough" is useful; for a development plan, an adjacent skill is not the skill
> you need to learn. It is recorded here because it is a genuine behavioural difference between
> the two engines that a reviewer will notice.
>
> `TargetRoleProfile.critical_skills` and `min_coverage_ratio` are also **not** consulted by
> `compute_gaps`.

---

## 7. Baseline normalisation (Phase 8 — NOT a scoring input)

**Code:** `src/phase8/normalize.py`

```
normalize_level(raw_value, source_scale):
    None                   -> None
    0.0                    -> None          # "not assessed", never level 0 or 1
    collab_four_point      -> {1:1, 2:2, 3:4, 4:5}
    five_point_undefined   -> round(v) if 1.0 <= v <= 5.0 else None
```

`classify_scale(sheet)` returns `collab_four_point` for the `Collab` sheet, else
`five_point_undefined`.

**Reason for `0.0 → NULL`.** A zero in the 2025 workbook means *not assessed*, not *no skill*.
Mapping it to level 1 would fabricate an assessment. This is the single most important rule in
Phase 8 ingestion.

**Reason for the 1–4 → 1,2,4,5 stretch.** The Collab sheet uses a 4-point scale with no
midpoint. Mapping 3→3 would compress the top of the scale and systematically understate the
strongest Collab practitioners relative to 5-point sheets. Mapping 3→4 preserves the
*proportional position* within the scale. Note this creates a deliberate hole at level 3.

> **These values never reach a score.** `baseline_assessments` has no path into
> `merge_evidence`, `rank_candidates`, or `compute_gaps`. The baseline exists to *grade* the
> engine (`scripts/phase8/baseline_agreement.py`), not to train it. See
> `tests/guardrails/test_baseline_isolation.py`. As of this writing the agreement harness
> reports **0 overlaps**, because 100% of baseline labels are unmapped `pending` aliases.

---

## 8. Worked example (reproducible, pinned by test)

Pinned by `tests/unit/test_scoring_golden.py`.

**Given** one candidate, one required skill:

| Input | Value |
|---|---|
| `required_level` | 3 (Proficient) |
| `actual_level` | 4 (Advanced) |
| `confidence` | 0.90 (demonstrated + certified) |
| `volume_score` | 0.70 |
| `freshness` | 0.80 |
| `adjacency_discount` | 1.0 (direct match) |
| `allocation` | 1.0 |

**Step 1 — level ratio**
`min(1.0, 4/3) = 1.0` — capped; the extra level earns nothing.

**Step 2 — contribution**
`1.0 × 0.90 × 0.70 × 0.80 × 1.0 = 0.504`

**Step 3 — mean over required skills**
`0.504 / 1 = 0.504`

**Step 4 — allocation multiplier**
`(1 - 0.15) + 0.15 × 1.0 = 1.00`

**Step 5 — fitness**
`round(0.504 × 1.00, 4) =` **`0.504`**

At `allocation = 0.5` → `0.504 × 0.925 =` **`0.4662`**
At `allocation = 0.0` → `0.504 × 0.850 =` **`0.4284`**

Every one of these numbers is returned by the API in `reasoning_detail` and `calculation`, so a
reviewer can repeat this arithmetic without reading source code.

---

## 9. What can and cannot change a score

**Can:** demonstrated / certified / manager-confirmed-declared evidence; its dates; its volume;
the taxonomy (keywords, relations, half-lives); role requirements; allocation; the scoring
config constants in §1.

**Cannot — by construction:**

| Excluded input | Mechanism |
|---|---|
| Manager baseline ratings | separate table, no read path (`test_baseline_isolation.py`) |
| Client / account familiarity | `account_context` only (`test_account_context_isolation.py`) |
| Soft skills, culture fit | rejected at ingest (`shared/exclusions.py`) |
| Historical staffing decisions | audit-only; never read back |
| Protected attributes | no schema field; blocked at the gate; `scripts/fairness_audit.py` |
| Real names | scoring sees only `EMP-` tokens |
| Unmapped (`pending`) skill labels | never resolve to a `skill_id` |
| LLM output | no model is consulted anywhere in the scoring path |

---

## 10. Reproducibility

A result is reproducible from three keys, all returned with every response:

| Key | Meaning |
|---|---|
| `scoring_config_version` | hash of the constants in §1 |
| `computation_run_id` | which inference run produced the matrix rows |
| `evidence_ids` / `source_refs` | exactly which evidence was used |

Given the same evidence, the same taxonomy, and the same config version, ranking is
**deterministic**: ordering ties break on `coded_identity`, and no wall-clock value enters a
score except through `freshness`, which accepts an explicit `as_of`.

> **Open gap (AMBER, tracked).** `computation_run_id` is currently a `uuid4()`
> (`shared/service.py`), so re-running an identical merge produces a different id. It
> identifies a run but is not yet a *content hash* of its inputs. Recorded as outstanding in
> `docs/V2_READINESS_REPORT.md`.

---

## 11. Change control

Changing any constant in §1, any formula here, or any ontology proficiency definition:

1. changes `scoring_config_version` (automatically, for §1);
2. **invalidates every stored score** — the matrix must be recomputed;
3. requires updating the pin in `test_default_config_version_is_pinned`;
4. requires updating this document in the same commit.

The version pin exists specifically so that step 4 cannot be silently skipped.
