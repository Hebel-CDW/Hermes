# Phase 8 — items needing human decision

## B-CULTURE-FIT-COLUMNS

Most 2025 skill sheets include a `Culture fit` column. `classify_assessment_column("culture fit")` **raises** (guardrail test). Full-workbook ingest **strips** those columns with an explicit `culture_fit_forbidden_column` exclusion log entry so the load can complete. Confirm this strip-and-log behaviour is acceptable vs aborting the entire workbook.

## A-LABEL-COUNT

Brief estimated ~650 distinct skill labels. Extraction observed **752** distinct labels (before clustering), including soft-skill and account columns classified as excluded. Confirm whether meta/soft columns should be omitted from the distinct-label denominator.

## A-SEMANTIC-DUPES

String similarity ≥ 0.87 flagged ~38 clusters for human review (`needs_human_review=yes` in `candidate_skills.csv`). Semantic duplicates (different spellings that are the same skill but <0.87 similar) were **not** auto-merged. Humans must curate `skill_aliases` with `mapped_by=human`.

## B-MANAGER-VARIANTS

`manager_variants.csv` proposes canonical forms for spelling variants (e.g. Xavier / Xavier Cardoz). **No auto-merge** into `org_edges`. Apply only after `mapped_by=human` rows are written.

## B-TEAM-VARIANTS

Certificates team names do not join cleanly to skill-sheet names (`Virtulization` vs `Virtualization`, etc.). `team_variants.csv` is a proposal only.

## B-SHEET-ROW-DELTAS

Several sheets differ from the brief’s expected person-row counts after Group Average / section-header filtering (e.g. Tools 2 vs 3 expected unique people; Azure 15 vs 16). Deltas are logged in `data/reports/phase8_dropped_rows.json` and `phase8_ingest_report.json`. Confirm tolerances.

## C-CERT-DATES

428 certs staged with `earned_at=NULL`. `cert_date_request.csv` must be completed by humans before any certified evidence enters `skills_matrix`. Do not invent dates.

## C-CERT-LABEL-MAP

188 distinct cert labels need mapping onto ontology `cert_codes`. Unmapped labels stay pending and are not promoted.

## D-CLIENT-BLOCKLIST

`config/client_names.txt` is gitignored. Operators must maintain the real account list locally. Committed artifacts redact account labels as `[REDACTED_ACCOUNT]`.

## E-NO-OVERLAPS-YET

`baseline_agreement` correctly reports zero overlaps until the same people have ticket/cert evidence in `skills_matrix` with resolved `skill_id`s (today nearly all baseline `skill_id`s are pending).
