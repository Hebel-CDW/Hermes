# Evidence merge rules

Deterministic precedence used by `SkillInferenceEngine`:

1. Only manager-confirmed declared evidence is ingested.
2. Proficiency is a freshness-weighted vote across demonstrated, certified, and declared evidence using scoring config weights (default 0.55 / 0.30 / 0.15).
3. When demonstrated evidence is within one level of the weighted winner, the higher of the two levels is taken.
4. Confidence is the sum of weighted contributions normalised by total type weights, floored at `min_confidence`.
5. Freshness is the mean of per-evidence exponential decay (`half_life_days`, default 180).
6. Conflicts are always resolved by the rules above — no unresolved merge states.
