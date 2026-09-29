# Evidence merge rules

> **Superseded.** The canonical, code-verified description of evidence merging and every
> scoring formula now lives in **[`docs/SCORING_SPECIFICATION.md`](SCORING_SPECIFICATION.md)**.
>
> The previous contents of this file described an **earlier algorithm** and were contradicted by
> the live engine in three material ways (recorded in
> [`docs/ARCHITECTURE_REVIEW_V2.md §2`](ARCHITECTURE_REVIEW_V2.md)):
>
> - it claimed proficiency was a *freshness-weighted* vote — the engine weights the level vote by
>   **evidence type only**, and applies freshness exactly once on the skill record;
> - it claimed confidence was the *sum of weighted contributions normalised by total type
>   weights* — confidence is actually **cross-type agreement** (`0.35 × distinct_type_count`,
>   plus `0.20` when demonstrated and certified agree);
> - it omitted `volume_score` entirely, which is a first-class multiplicand.
>
> This stub is kept rather than deleted because `PROJECT_BIBLE.md` links to this path.

## Where to look now

| Question | Section of `SCORING_SPECIFICATION.md` |
|---|---|
| How is a proficiency level inferred from a ticket? | §2 |
| How does freshness decay, and is it applied twice? | §3 |
| Which declared evidence is admitted? | §4.1 |
| How is the merged level chosen? | §4.2 |
| How is confidence computed? | §4.3 |
| How is evidence volume computed, and how does it differ from confidence? | §4.4 |
| How are candidates ranked? | §5 |
| How are gaps ranked? | §6 |
| How is the 2025 baseline normalised, and why is it isolated? | §7 |

Executable ground truth: `src/skill_inference/engine.py`, `src/fitness_gap/engine.py`,
pinned by `tests/unit/test_scoring_golden.py` and `tests/unit/test_scoring_inspector.py`.
