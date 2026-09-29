# Excel sunset — freeze the 2025 survey, cancel the next workbook

**Policy (this week, operations):** do **not** issue a Skill Matrix 2026 workbook.
Updates go through Hermes: tickets, dated certificates, and manager-confirmed
declared skills (`Update skills`). The 2025 `.xlsx` is a frozen labelled survey.

## Dual-run

| View | Source | Used for Find people |
|---|---|---|
| Living (evidence) | `skills_matrix` from tickets / dated certs / declared | Yes |
| 2025 survey | `baseline_assessments` only | **Never** |

`GET /api/baseline/matrix` is read-only, coded identities only, `used_for_fitness: false`.
Copy in Team skills: the survey is not used for Find people.

## Vocabulary

Pilot ontology (~40–80 skills) lives in `taxonomy/pilot_ontology.yaml` and is merged
into `taxonomy/skills_ontology.yaml`. Alias proposals in `taxonomy/pilot_aliases.yaml`
are **not** scores. A human must approve them (`mapped_by=human`) in Data Quality →
Taxonomy inbox. Rejected labels stay `mapped_by=rejected` with an empty `skill_id`.
No LLM / fuzzy auto-map.

## Kill gate (`GET /api/excel-sunset`)

`next_workbook_allowed` is always `false`. `ready_to_retire_excel` is true only when:

1. Survey year frozen at 2025
2. Pilot demonstrated coverage ≥ 80%
3. At least one baseline ∩ living overlap on a mapped skill
4. At least one audited staffing decision in Hermes

Until then the 2025 survey view is the off-ramp, not a new spreadsheet.

## What we will not do

- Copy 2025 ratings into `skills_matrix` / fitness
- Auto-map 673 labels with an LLM
- Show real names in the matrix
- Invent certificate dates
- Wait for a 73k vendor ontology before staffing this org
