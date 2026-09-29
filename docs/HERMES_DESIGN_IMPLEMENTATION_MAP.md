# Hermes Design → Implementation Map

Approved designs: `hermes_design/` (design system: `precision_enterprise_minimal/DESIGN.md`).
Every value on screen is read from the Hermes API. React formats numbers and never calculates fitness, volume, contribution or ranking.

Status: **Implemented** = wired to the real API and covered by tests. **Adapted** = implemented, but a design element with no API source was replaced by an empty state or left out (see Notes).

| Design | React Route | Status | API | Notes |
|---|---|---|---|---|
| Shared shell (all screens) | all authenticated routes | Implemented | `GET /api/session`, `GET /api/overview` (activity), `GET /api/skills`, `GET /api/staffing/requests` (search) | Sidebar, top bar, ⌘K search, activity, account menu, page transition, responsive drawer below 860px. Nav is gated by server-derived roles; the server still enforces. The design's "Global Enterprise", "v3.4" and photo avatar are replaced by product name, "V2" and initials. |
| `hermes_logo_mark` | shell, `/login` | Implemented | none | Inline SVG mark: ink uprights, crimson crossbar. |
| none (auth) | `/login` | Implemented | `POST /api/auth/token` `{sub}` | Synthetic demo principals only. No role picker, no roles stored client-side. |
| `hermes_overview`, `hermes_overview_minimalist_ecosystem` | `/overview` | Adapted | `GET /api/overview` | KPI strip, readiness ring, domain coverage bars, request status, audit activity, config and run provenance. The velocity trend and "critical deficit" threshold have no API source and are left out. |
| `hermes_workforce` | `/workforce` | Implemented | `GET /api/workforce` | Topology clustered by `primary_domain`. Node size = `skill_count` (breadth); ring = `mean_confidence`. The inspection ledger shows API values. |
| `hermes_skills` | `/skills` | Implemented | `GET /api/skills`, `GET /api/skills/{skill_id}` | Atlas from the governed ontology and its relations. The inspector shows coverage, confidence, freshness, level distribution, holders, related skills and proficiency definitions. |
| `hermes_skill_matrix` | `/matrix` | Implemented | `GET /api/dashboard`, `GET /api/skills`, `GET /api/workforce` | Row = `skill_id`, column = `coded_identity`, cell = level 1–5. Hatched cell = no evidence. Hover or focus shows confidence, freshness and volume. No photos or invented numbers. |
| `hermes_requests` | `/requests` | Implemented | `GET /api/staffing/requests` | Tabs All/Open/Decided. Table: id, owner, requirements, candidate count, excluded count, status, decision. Only the caller's own requests. |
| none (request ledger) | `/requests/:id` | Implemented | `GET /api/staffing/requests/{id}`, `POST /api/identity/resolve`, `POST /api/staffing/{id}/decision` | Ranking in API order, excluded candidates with API reason codes, identity resolution (protected → resolved; 401/403/429 handled), decision form (shortlist only; no owner or approver sent; 403/409/422 rendered). |
| none (search form) | `/capability` | Implemented | `GET /api/skills`, `GET /api/roles`, `POST /api/fitness/rank` | The role template sends `role_id`, so the server enforces critical skills and the coverage floor. Opens the stored request after ranking. |
| `hermes_candidate_detail_candidate_0007_1`, `_2` | `/capability/:id?request=` | Implemented | `GET /api/staffing/requests/{id}` (stored `result`) | Match fitness, coverage, allocation multiplier, capability delta matrix (required vs demonstrated). Excluded candidates show the API reason. |
| `hermes_score_derivation_candidate_0007` | `/capability/:id?request=&view=derivation` | Implemented | `GET /api/staffing/requests/{id}` (stored `result`) | Run id, config version, fitness, 01–06 pipeline, per-skill ledger (required, demonstrated, confidence, volume, freshness, adjacency, contribution), API formula plus substitution using the exact backend numbers, raw payload, JSON export. |
| `hermes_learning` | `/learning` | Adapted | `GET /api/roles`, `GET /api/identities` (manager/admin), `POST /api/fitness/gaps` | Current → target level stepper per engine gap. The design's course modules, hours and CEUs have no source, so an explicit "No learning catalogue connected" empty state is shown instead. |
| none (governance) | `/data-quality` | Implemented | `GET /api/data-quality` | Imported / validated / mapped / pending / scored states, rejection categories, taxonomy governance, certificates. Aggregates only. Real-data empty states are shared with Overview, Workforce, Skills, Matrix and Profile. |
| `hermes_insights` | `/insights` | Adapted | `GET /api/overview`, `GET /api/dashboard`, `GET /api/matrix/runs` | Domain capability table, freshness by skill, computation runs. The skill-demand trend and period filters have no API source and are replaced by an empty state. |
| none (profile) | `/profile` | Implemented | `GET /api/session`, `GET /api/me`, `POST /api/me/contest` | The subject is always the signed-in principal; no identity parameter is accepted or sent. |
| `professional_studio_portrait_headshot…` | none | Not used | none | Stock photo of a person. Hermes shows coded identities only. |
