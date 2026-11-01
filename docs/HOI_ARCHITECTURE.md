# Hermes Opportunity Intelligence (HOI) — Architecture

Source: `Hermes_Opportunity_Intelligence_Developer_Design.docx` (30 Oct 2026) and `hermes_prototype.html` (visual reference only). Everything below is implemented inside the existing FastAPI + React + SQLite/PostgreSQL app; there is no second backend.

## Flow
Opportunity → document intake → requirement extraction (draft) → **human approval** → internal matching (existing fitness engine + separate eligibility) → finance-separated costing → market benchmarks → internal/external/hybrid scenarios → Delivery / Finance / (HR) approvals → redacted report. Hermes recommends; people decide; nothing is assigned.

## Modules (`src/hoi/`)
| Module | Responsibility |
|---|---|
| `documents.py` | validation (type, signature, size, PDF active content, DOCX macros), checksum, versioning, encrypted storage, PDF/DOCX/TXT text. Scanner is an adapter (`not_scanned`). No OCR: image-only PDFs → `needs_ocr`. |
| `extraction.py` | rule-based extractor + optional local-LLM merge. Every item has `source{document_id,start,end,quote}` and a heuristic confidence. Unverifiable items are rejected; unstated values stay `null`. |
| `service.py` | opportunities, deal-team access, requirement versions, approval gate, internal matching, hash-chained per-opportunity audit. |
| `finance.py` | **Finance vault**: encrypted loaded costs (individual or role band), cost policies, rate cards, access log. Only path that reads cost. |
| `costing.py` | pure `Decimal` calculation, version `hoi-calc-1.0`. |
| `market.py` | curated CSV import (atomic), basis separation, coverage flags. |
| `scenarios.py` | scenario build/compare, role-redacted views, approvals, export, market analysis. |
| `crypto.py` | Fernet keys, one for documents (`HOI_DOC_KEY`), one for finance (`HOI_FINANCE_KEY`). |
API: `api/routers/hoi.py` (thin). UI: `web/src/views/hoi/*`.

## Reuse of existing Hermes
* Fitness: `HermesService.rank` — unchanged. HOI passes approved skills/levels, must-haves as `critical_skills`. A test asserts HOI scores equal a direct engine run.
* Name reveal: HOI stores a normal staffing request per role; names come only from `POST /api/identity/resolve` (owner-only, rate-limited, audited).
* Auth/RBAC: same JWT principals; new roles `sales`, `finance`, `hr` (`demo_identities.py`, OIDC known-roles list).
* Audit: events go to the existing hash-chained ledger *and* to `opportunity_audit` (own chain, verifiable per opportunity).
* Availability: the existing `availability` table is the capacity source; a snapshot is stored per match run.

## Data model (migration `infra/{sqlite,postgres}/002_hoi.sql`, applied by `HermesDB.migrate`)
opportunities, opportunity_members, opportunity_documents, requirement_versions, resource_requirements, candidate_shortlists, capacity_snapshots, cost_parameters, fin_loaded_costs (encrypted), market_benchmarks, commercial_scenarios, scenario_assignments, approval_events, opportunity_audit, fin_access_log. Money is decimal TEXT. `scripts/migrate_sqlite_to_postgres.py` includes the new tables.

## Costing definitions (Finance must certify before production)
revenue = Σ bill_rate × FTE × months; direct labor = Σ loaded monthly cost × FTE × months; contractor = benchmark `contractor_cost` (P25/P50/P75 chosen, default P50; year/hour normalised to month); other = recruiting per external slot, training/FTE, travel/FTE-month, tools/FTE-month, transition, project direct costs; contingency % of direct; allocated overhead % of internal labor.
* **Gross margin** = (revenue − COGS)/revenue; COGS includes overhead only if policy `overhead_treatment=in_cogs`.
* **Contribution** = revenue − (direct + contingency); never includes allocated overhead.
* Cross-currency needs a Finance FX rate in the policy; absent → unresolved, never guessed.
Worked example from the design doc (1 FTE × 6 mo, 7,000 cost, 12,000 rate, 6,000 extra) → 72,000 / 48,000 / 24,000 / 33.33% (test-verified).

## Certificate eligibility and duplicate documents
A mandatory certificate passes only with evidence: a promoted workbook certificate, or a CERTIFIED evidence record whose code is the record's `source_ref`. A requirement matches by whole-token equality or by citing the held code (`Azure Administrator Associate (AZ-104)`); a name alone never implies a code. Documents with identical bytes are ignored on re-upload, and roles with the same normalised name are merged with conflicts noted, never silently resolved.

## Scenario rules
Eligible candidates only (separate pass/fail: capacity, mandatory certificates, mandatory location=unverified as Hermes has no location data), filled in fitness-rank order; cost never reorders. Hybrid = eligible internal first, external for the gap; not offered when it would duplicate another scenario. Choosing a lower-ranked eligible candidate over a higher-ranked one sets `override_required`; Delivery approval then needs an `override_reason`. Risk is a rule-based level (flags listed), not a probability.

## Migration operations
`infra/{sqlite,postgres}/002_hoi.sql` are additive and idempotent (`CREATE … IF NOT EXISTS`, applied on every `HermesDB.migrate()`); re-opening a database is a no-op. They only add tables, so rolling back the *application* never requires touching the schema. To remove HOI entirely (destroys all opportunity, finance and audit data in those tables; take a backup first), drop in this order: `fin_access_log, opportunity_audit, approval_events, scenario_assignments, commercial_scenarios, market_benchmarks, fin_loaded_costs, cost_parameters, capacity_snapshots, candidate_shortlists, resource_requirements, requirement_versions, opportunity_documents, opportunity_members, opportunities`. No down-migration file is shipped on purpose: a `*_down.sql` in that folder would match the migration glob and be applied automatically.

## Azure
Unchanged: `docs/future-azure.md` remains the separate production target (Entra ID/OIDC, Key Vault for the two keys, Blob for documents, Azure SQL/PostgreSQL). Nothing Azure-specific is required locally.
