# Hermes Architecture (Local-First)

**Classification:** Internal, Confidential — Project EVOLVE / Project Hermes

## Purpose

Hermes is a recommendation layer for skills-based staffing and learning-path guidance. It never auto-assigns work and never uses protected demographic attributes.

## Local runtime layers

1. **Fixture ingestion** — CLI loads ServiceNow/LMS/HR-shaped JSON fixtures and posts them through the identity abstraction gate into SQLite.
2. **Identity abstraction gate** — Deterministic tokenization to `EMP-` + 8 lowercase hex
   (`HMAC-SHA256(IDENTITY_MAP_SECRET, normalised_key)`, e.g. `EMP-a1b2c3d4`); PII stripped before
   matrix write; display names stored only in restricted `identity_vault`.
3. **Skill inference engine** — Maps evidence to taxonomy skills; merges demonstrated, certified,
   and manager-confirmed declared evidence into a level plus **confidence, volume_score, and
   freshness** (see [`SCORING_SPECIFICATION.md`](SCORING_SPECIFICATION.md) §4).
4. **Fitness and gap engine** — Deterministic ranking and demand-ranked gaps
   ([`SCORING_SPECIFICATION.md`](SCORING_SPECIFICATION.md) §5–§6).
5. **Identity resolution gateway** — Sole logged path resolving shortlisted coded IDs for the requesting manager.
6. **Presentation** — FastAPI + CLI narrate engine output; HTML dashboard shows coded IDs only.

## Guardrails

- Single identity abstraction entry point
- No protected attribute fields in schema or scoring
- Governed, logged identity resolution (shortlist + requester only)
- Human override on every recommendation
- Full audit lineage in SQLite `audit_ledger`
- Confidence and freshness on every skill record
