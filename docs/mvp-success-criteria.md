# MVP Success Criteria

Automated and manual checks mapped to Project Hermes V0.1.

| Metric | Target | How verified |
|--------|--------|--------------|
| Evidence coverage | ≥ 80% | `scripts/coverage_report.py` against pilot population |
| Identity leakage | Zero | `pytest tests/audits/test_leakage_audit.py` + `hermes-leakage-audit` |
| Ranking traceability | 100% | Golden ranking tests assert every score cites evidence IDs |
| Query response latency | ≤ 3s | E2E timing harness in `tests/e2e/` (Function path; Copilot overhead measured in Azure) |
| Skills matrix availability | Operational on coded pilot data | Integration tests + Phase 4 validation report |

## CI gates

- Unit + integration tests with coverage ≥ 80% on custom packages
- Leakage audit must pass
- Fairness schema audit must pass (no protected-attribute columns)
