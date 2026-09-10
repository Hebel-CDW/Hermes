# Hermes validation

Fixture-backed gates (CI-safe):

1. **Keyword precision** — `scripts/validation_keyword_precision.py`
2. **Manager agreement baseline** — `scripts/validation_manager_agreement.py` (30 decisions)
3. **Cold start visibility** — `tests/validation/test_validation_gates.py`

Real anonymised ServiceNow corpora are run manually under secure controls; do not commit raw ticket bodies with PII.
