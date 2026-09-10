# Hermes Power BI measures

- `EvidenceCoveragePct = DIVIDE(DISTINCTCOUNT of coded_identity with demonstrated evidence, PilotPopulationCount)`
- `AvgFreshness = AVERAGE(skills_matrix[freshness])`
- `SkillsPerEngineer = AVERAGE of skill counts per coded_identity`
- `StaleSkillCount = COUNTROWS where freshness < 0.3`

All visuals must use `coded_identity`, never display names.
