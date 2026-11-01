# HOI — Test plan and results

Run: `source .venv/bin/activate && python -m pytest` (gate 85%, `hoi` included) · `cd web && npx tsc --noEmit && npx vitest run` · live: `python -m scripts.hoi_live_smoke --base http://127.0.0.1:8000`.

| Requirement / invariant | Test (tests/api/test_hoi_api.py unless noted) |
|---|---|
| Opportunity creation, access isolation | test_create_and_isolation |
| Upload validation, governance, encryption | test_upload_validation, test_upload_governance_and_encryption, test_pdf_without_text…, test_docx_text_extraction |
| Extraction source traceability, unknowns | test_extraction_has_verifiable_sources_and_unknowns, test_missing_fields_stay_unknown…, test_llm_assist_rejects_unverifiable_output |
| Human approval; **inv. 2** | test_unapproved_requirements_never_reach_matching_or_scenarios, test_approved_version_is_immutable… |
| Taxonomy mapping / unmapped | extraction tests (Quantum Compliance Mesh stays unmapped, blocks approval) |
| Fitness regression | test_internal_match_coded_deterministic_and_matches_engine |
| **inv. 1** pay never changes ranking | test_compensation_never_changes_fitness_ranking |
| Identity protection | test_shortlist_redacted…_name_reveal_only_via_gateway |
| Availability/eligibility | test_eligibility_constraints_are_separate_pass_fail |
| Cost & margin, units, currency | test_illustrative_cost_example_matches_design, test_gross_vs_contribution…, test_currency_units_and_missing_fx |
| **inv. 3** finance leakage | test_no_salary_leak_anywhere_outside_finance, test_audit_rejects_monetary_keys, tests/unit/test_hoi_migration.py (ciphertext) |
| Market provenance | test_market_import_provenance_and_validation, test_market_analysis_reports_unavailable_honestly |
| Scenario eligibility; **inv. 4** no assignment | test_scenarios_internal_external_hybrid_without_assignment, test_scenario_rejects_ineligible… |
| **inv. 5** determinism | test_scenario_is_deterministic, match determinism test |
| **inv. 6** no fabrication | test_missing_cost_inputs_are_unresolved_not_fabricated, unknown-field tests |
| Approvals, export, audit integrity | test_approval_workflow_export_and_sales_view, test_hr_authorization…, test_audit_chain_integrity_and_tamper_detection |
| Duplicate upload / role merge | test_repeated_identical_upload…, test_same_role_in_sow_and_jd_is_merged… |
| Local-model assist | test_llm_* (glitch tolerance, salvage, verified-only additions) |
| Demo seed / certificate eligibility | tests/unit/test_hoi_seed.py (one eligible candidate, whole-token cert matching, Hybrid needs HR) |
| PDF decompression bomb, oversized text, role cap | test_pdf_decompression_bomb…, test_oversized_extracted_text…, test_extraction_keeps_drafts_editable… |
| Early request-body limits (413/411) | test_oversized_request_bodies_are_refused_before_they_are_read |
| Key management fail-closed, separate keys | test_encryption_fails_closed_outside_local_mode…, test_separate_keys_for_documents_and_finance |
| Authorization matrix over every opportunity route | test_every_opportunity_route_is_scoped_to_the_deal_team |
| Database CHECK constraints | tests/unit/test_hoi_migration.py::test_check_constraints_refuse_invalid_values_at_the_database |
| Plain-language scenario warnings; overview pipeline | test_missing_cost_inputs…(unresolved_detail), web/src/test/hoi.test.tsx |
| Migration parity | tests/unit/test_hoi_migration.py |
| Frontend | web/src/test/hoi.test.tsx (nav/roles, guards, approval gating, redaction, finance view, synthetic labels, audit) |

Not covered / pending: parsing precision & recall (needs a labelled SOW/JD corpus and agreed thresholds — none invented); PostgreSQL execution of migration 002 (parity is textual; run with `HERMES_TEST_POSTGRES_URL`); fairness/adverse-impact review; load testing beyond the single-user latency in `hoi_live_smoke` (compare ≈ 40 ms, match ≈ 30 ms on the 36-person org); browser visual QA (extension was unavailable).
