# Taxonomy governance

- Ontology is versioned in `taxonomy/skills_ontology.yaml` (`version` field).
- Level-definition changes invalidate scores: recompute matrix and bump config-derived
  scoring version (hash of weights/half-lives/flags).
- Approval checklist: `docs/taxonomy-approval-checklist.md`.
- Inbox: Data Quality → Taxonomy inbox (`GET /api/taxonomy/pending`,
  `POST /api/taxonomy/aliases/{label}/resolve`). Approvals write `mapped_by=human` only.
  See `taxonomy/pilot_aliases.yaml` and `docs/EXCEL_SUNSET.md`.
- Adjacency: optional `relations:` lists grant discounted partial credit in fitness.
