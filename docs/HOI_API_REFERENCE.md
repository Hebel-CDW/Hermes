# HOI — API reference
Auth: `Authorization: Bearer <token>` (demo `POST /api/auth/token {"sub": "demo-sales"|"demo-sales-2"|"demo-manager"|"demo-finance"|"demo-hr"|"demo-admin"}`). Errors: `{detail, error}`. Rate limit 120/min/principal. `{oid}` = `OPP-YYYY-XXXXXX`.

| Method & path | Roles | Purpose |
|---|---|---|
| GET `/api/hoi/status` | any HOI role | capabilities, pending integrations |
| GET `/api/hoi/skills` | any HOI role | governed skill id/name list for requirement mapping |
| POST `/api/opportunities` | sales, manager | create (client_alias, name, currency, contract_type, duration_months, geography, bid_deadline, start/end, is_synthetic) |
| GET `/api/opportunities`, `/{oid}` | members, admin | list / detail with readiness |
| POST `/{oid}/members` | owner | add deal-team member |
| POST/GET `/{oid}/documents` | sales, manager / members | upload (`{doc_type: rfp|sow|jd, filename, content_b64}`, ≤10 MB, pdf/docx/txt; identical bytes return the existing document with `duplicate: true`) / list |
| POST `/{oid}/extract` | sales, manager | `{document_ids?, use_llm?}` → draft version |
| GET `/{oid}/requirements?version_id=` | members | versions + current roles, sources, `blocking_problems` |
| PUT `/{oid}/requirements/{vid}` | sales, manager | human correction (draft only) |
| POST `/{oid}/requirements/approve` | sales, manager | `{version_id}`; 422 if incomplete; locks + content hash |
| POST `/{oid}/requirements/revise` | sales, manager | new draft from latest |
| POST `/{oid}/internal-match` | manager | rank approved requirements; 409 `requirements_not_approved` otherwise |
| GET `/{oid}/shortlist?run_id=` | members | manager: coded candidates, eligibility checks, explanation, `staffing_request_id`; others: counts only |
| POST `/{oid}/market-analysis` | members | benchmark snapshot per role/basis; `unavailable` when absent |
| POST `/{oid}/scenarios` | manager, finance | custom scenario (`cost_policy_id`, `rate_card_id`, `assignments[]`, optional months/currency/cost_as_of/project_direct_costs) |
| POST `/{oid}/scenarios/compare` | manager, finance | internal / external / hybrid drafts |
| GET `/{oid}/scenarios`, `/{sid}` | members | role-redacted view |
| POST `/{oid}/approvals` | per lane | `{scenario_id, approver_role: delivery|finance|hr, outcome, reason?, override_reason?}` |
| POST `/{oid}/export` | members | `{scenario_id, format: json|markdown}`; 409 until fully approved |
| GET `/{oid}/audit` | members | events + `chain_valid` |
| POST `/api/market/benchmarks/import` | finance, admin | `{csv_text, declare_synthetic}` all-or-nothing |
| GET `/api/market/benchmarks?role&geography&basis` | HOI roles | provenance, coverage |
| PUT `/api/finance/cost-policies/{name}`, `/rate-cards/{name}` | finance | new version each save |
| GET `/api/finance/cost-policies` | finance (payload), manager/admin (names) | |
| GET `/api/rate-cards` | sales, manager, finance, admin | |
| POST/GET `/api/finance/loaded-costs` | finance only | encrypted store / audited raw read |
| GET `/api/finance/summary`, `/access-log` | finance, hr, admin | counts / who accessed (no values) |

Scenario view by role: **finance** full (`finance`, `assumptions`, per-line cost, breakdown); **manager/hr/admin** `economics{revenue, margin_band}`; **sales** assignment counts, and `approved_totals{revenue}` once approved. Cost policy fields: `overhead_pct, overhead_treatment, contingency_pct, training_per_fte, travel_per_fte_month, tools_per_fte_month, recruiting_onboarding_per_external_slot, transition_total, standard_hours_per_month, utilization, internal_lead_weeks, fx_rates{"EUR->USD":{rate,as_of,source}}`. Benchmark CSV columns: `role,geography,seniority,engagement_type,basis,currency,unit,p25,p50,p75,sample_count,source,as_of[,time_to_fill_weeks,synthetic]` (salary⇔permanent; contractor_cost/bill_rate⇔contractor|vendor).
