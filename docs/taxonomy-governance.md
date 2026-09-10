# Taxonomy governance

- Ontology is versioned in `taxonomy/skills_ontology.yaml` (`version` field).
- Level-definition changes invalidate scores: recompute matrix and bump config-derived
  scoring version (hash of weights/half-lives/flags).
- Approval checklist: `docs/taxonomy-approval-checklist.md`.
- Adjacency: optional `relations:` lists grant discounted partial credit in fitness.
