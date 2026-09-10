# Bias / impact audit methodology

## Separation of concerns

Hermes **ops path** scores skills from ticket-grounded evidence only. Impact audits run
**offline** (HR-held) and must never be joined into ranking features.

## Metrics

1. **Gini of shortlist appearances** — concentration of who appears on shortlists.
2. **Never-shortlisted cohort** — coded identities with zero appearances in the period.
3. **Tenure-band accrual** — supplied via HR export keyed by coded identity mapping vault
   under dual control; Hermes does not store tenure or protected attributes.

## Cadence

Quarterly for pilot; monthly if EU AI Act high-risk documentation is in scope.

## Guardrail 8

Never score on historical staffing decisions. Decision events are audit-only feedback labels.
