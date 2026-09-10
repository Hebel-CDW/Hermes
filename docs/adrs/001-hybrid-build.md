# ADR 001: Hybrid low-code + custom code

## Decision

Use Power Automate / Copilot / Power BI for orchestration and narration; implement identity, inference, fitness/gap, and resolution as tested Python Azure Functions.

## Rationale

Identity and fairness decisions must be reviewable line-by-line and cannot live in an editable canvas. Connector plumbing does not benefit from a fully custom rewrite.
