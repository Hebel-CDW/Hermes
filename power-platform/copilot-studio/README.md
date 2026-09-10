# Copilot Studio — Hermes query surface

**Rules decide. Rules compute.** Copilot only narrates Fitness/Gap engine output.

## Topics

1. **StaffingFit** — manager asks who fits a skill profile
2. **LearningPath** — engineer asks gaps vs a target role

## Grounded actions

- `RankCandidates` → `POST /api/fitness/rank`
- `ComputeGaps` → `POST /api/fitness/gaps`
- `ResolveShortlist` → `POST /api/identity/resolve` (manager only, after rank)

## System instructions (must ship as-is)

See `system-instructions.md`.
