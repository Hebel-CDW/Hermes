# Hermes risk register (pilot)

| ID | Risk | Severity | Mitigation | Oversight evidence |
|---|---|---|---|---|
| R1 | Roster enumeration via rank+resolve | High | Shortlist cap 10; resolve owner binding; rate limit | Abuse tests in `tests/security` |
| R2 | PII leakage into matrix | High | Recursive PII scan; no ticket excerpts | Leakage audit CI |
| R3 | Unfair cold-start exclusion (silent) | Med | Cold-start policy; insufficient-evidence cohort | `docs/cold-start-policy.md` |
| R4 | Scoring on past staffing choices | High | Guardrail 8 — decisions audit-only | Decision payload flag |
| R5 | EU AI Act high-risk non-compliance | High | Docs, bias tests, human oversight, consultation | `PROJECT_BIBLE.md` Legal |
| R6 | Secret default in prod | High | Fail-closed startup | `shared/secrets.py` |
| R7 | Audit tampering | Med | Hash chain + CI verify | `scripts/verify_audit_chain.py` |
