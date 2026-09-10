# Source connector field catalogue

## ServiceNow (resolved tickets)

| Field | Purpose |
|-------|---------|
| number | ticket id / source_ref |
| short_description | keyword matching |
| category / subcategory | taxonomy mapping |
| cmdb_ci.sys_class_name | CI class matching |
| assigned_to | employee key (stripped at gate) |
| resolved_at | freshness |

## LMS

| Field | Purpose |
|-------|---------|
| employee_id | employee key |
| cert_code | maps to skill cert_codes |
| earned_at / expires_at | freshness / validity |

## HR

| Field | Purpose |
|-------|---------|
| employee_id | employee key |
| role_code / project_code | role history (availability context) |
| start_date / end_date | tenure on assignment |

**Forbidden:** age, gender, ethnicity, or any protected attribute at any stage.


## Field-level contract (hash-at-boundary)

| Source field | Hermes field | Transform |
|---|---|---|
| employee_id / sys_id | source key → `coded_identity` | HMAC EMP-8hex; store source_hash only in map |
| short_description | keyword match input | In-memory only; persist `matched_keywords` + `source_ref` |
| ticket_number | `source_ref` | Pass-through opaque ref |
| resolved_at | `occurred_at` | ISO-8601 UTC |
| cert_code | certified evidence | Map via taxonomy `cert_codes` |
| reopen_count / escalation | negative evidence (optional) | Persist flags in payload; never store free-text bodies |

**Hash-at-boundary:** raw employee keys are hashed (`source_hash`) before durable storage in `identity_map`. Display names live only in `identity_vault`, never in skills matrix rows.

## Guardrails

8. Never score on historical staffing decisions (accept/reject/override are audit labels only).
