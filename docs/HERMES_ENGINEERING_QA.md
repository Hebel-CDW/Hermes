# Hermes Engineering Q&A

**Purpose:** defend Hermes in front of a VP, a delivery/engineering manager, an end-user manager, and a CTO, without reading documentation.
**Basis:** the working tree on 2026-09-24 (uncommitted). No code, config, or existing document was changed to produce this file.
**Rule:** every answer is grounded in source, tests, API behaviour, schema, or a command that was actually run. Nothing here describes a capability that does not exist.

## Label legend (used inline)

| Label | Meaning |
|---|---|
| **VERIFIED** | I executed it in this review: a test that passes in the full run, a script, a live API call, a browser action, or a direct call into the scoring engines. |
| **INFERRED** | Read from source but not executed. Treat as "the code says", not "I saw it happen". |
| **NOT IMPLEMENTED** | Does not exist in the code today. |
| **PROTOTYPE ONLY** | Exists, but only as a stub, a fixture, a demo registry, or a heuristic not fit for real use. |

People in this document are referred to by name or as "they". The fixture has no gender field (protected attributes are stripped by design), so no pronoun is stated anywhere in the data.

## Verification log (what was actually run)

| # | What | Result |
|---|---|---|
| V1 | Full backend suite `pytest` (unit, API, security, guardrails, e2e, phase8) | **389 passed**, coverage 92.28% (gate 85%) |
| V2 | Frontend: `tsc --noEmit`, `vitest`, `vite build` | clean; **83 tests passed** |
| V3 | `python -m scripts.live_smoke` against a live server, twice (local demo and a production-style config with no test mode) | **55/55** checks |
| V4 | `python -m scripts.demo_svp --verify` | "DETERMINISM OK", "SAFEGUARDS OK", config `9220dcfdfcf3` |
| V5 | Direct calls into `SkillInferenceEngine` / `FitnessGapEngine`: the full Alex trace plus 14 edge-case experiments (cert-only, declared-only, staleness, level cap, allocation, ties, adjacency, coverage, critical skill, unknown skill, date drift, config change, determinism, evidence disagreement) | results quoted below; commands in Appendix A |
| V6 | `scripts.phase8.real_data_report --verify` (aggregate counts only) | "CONSISTENCY OK"; numbers quoted in the Data section |
| V7 | Startup with no secrets; `HERMES_ENV=production` token endpoint | refuses to start (exit 3); token endpoint returns 403 |
| V8 | Real API calls through `TestClient`: decision semantics, manager scope, declaration accumulation | quoted below |
| V9 | Browser walkthrough of every screen as manager and as employee | no console errors; screens as described |
| V10 | Source-wide search of `web/src` for arithmetic on score fields | only bar-width clamping and layout math |

---

# Executive Questions

Each answer is written to be spoken in 30–60 seconds.

**Q1. What problem is Hermes solving?**
"Today, staffing runs on memory and spreadsheets. A manager asks 'who has done something like this?' and answers from their own network. Skills surveys go stale within months, and people outside a manager's circle are invisible. Hermes replaces that with a living view of who has actually shown which skills, so the question can be answered from evidence."

**Q2. Why does this problem matter?**
"Two reasons. Delivery speed: the right person is found faster. And fairness and retention: capable people who are not in the manager's circle stop being overlooked. There is also a hard data reality behind it. The current 2025 skills workbook covers 310 people across 22 sheets, but it uses 673 differently worded skill labels on rating scales that were never defined. That is not something you can staff from." **[VERIFIED: V6]**

**Q3. What does Hermes actually do?**
"It reads three kinds of evidence: work tickets, dated certificates, and skills a manager has confirmed. It turns them into a skills matrix. When a manager describes a role, it ranks who fits, explains every rank, lists who was left out and why, and shows what someone would need to learn. The manager makes the decision, and the decision is recorded."

**Q4. What is different compared with a spreadsheet or manager memory?**
"Three things. Every skill claim points to dated evidence. Skills fade over time, so an old certificate counts for less than recent work. And every score can be recomputed by hand, and the same input always gives the same answer. A spreadsheet holds opinions from a survey date; Hermes holds evidence with dates." **[VERIFIED: determinism, V4/V5]**

**Q5. What is the business workflow?**
"Evidence comes in, Hermes builds the matrix. A manager picks a role and clicks Find people. Hermes returns a ranked shortlist with reasons and a list of people not shortlisted with reasons. The manager chooses, overrides, or rejects, and that is logged. The manager can then look at the team's skills, see learning gaps, or add a skill they have personally confirmed. Employees can see their own evidence and flag something that looks wrong."

**Q6. What does the manager get?**
"A ranked shortlist with the evidence behind each rank, an explicit list of people excluded and why, a team skills grid, learning gaps per person against a role, a way to add a confirmed skill, and an audited record of their decision."

**Q7. What does the employee get?**
"A read-only view of their own skills and the evidence behind them, and a way to flag something that looks wrong, which goes to their manager to review. They cannot add or edit skills themselves; only managers can." **[VERIFIED: V3, employee `/api/team/declare` refused; `/api/me`, `/api/me/contest` allowed]**

**Q8. What is the most important capability demonstrated?**
"Explainable, repeatable ranking. Every score breaks down into five visible factors tied to named evidence, and the same evidence always produces the same number. That is what lets a manager trust it without trusting a black box." **[VERIFIED: V4, V5]**

**Q9. What does the current demo prove?**
"That the mechanism works end to end on synthetic data: identities are coded, evidence becomes a score, the score becomes a ranked shortlist with reasons, a human decides, and the whole path is logged. It also proves access control, reproducibility, and that unsafe inputs are refused: 389 automated tests and a 55-point live check pass."

**Q10. What does the demo NOT prove?**
"It does not prove the rankings are *right*. There is no validation against how managers actually judge people: the agreement check has zero overlaps because none of the 673 real workbook labels has been approved yet. No real employee has been scored. It has not been load-tested. There is no real company sign-in, and the connections to ServiceNow, the learning system, and HR are not built." **[VERIFIED: V6; NOT IMPLEMENTED: integrations, SSO]**

**Q11. Why should the organisation trust a recommendation?**
"Because it can be inspected, not because we ask for trust. The score is a formula on the screen with every input traceable to a ticket or certificate. No AI model decides anything. Old manager ratings, client familiarity, soft skills, and culture fit are excluded. The honest limit is that we trust the *mechanism* today, not yet its *accuracy* on real people." **[VERIFIED: no model code in `src/` or `api/`; baseline isolation test passes]**

**Q12. What happens when Hermes is wrong?**
"It is a recommendation, so the manager can override or reject it, and the choice is recorded. An employee can flag evidence they disagree with, and their manager can confirm it, which adds a manager-confirmed skill. What Hermes cannot do today is delete or overwrite the original evidence. A wrong ticket-based skill stays on file until it ages out. There is no correction workflow beyond adding a confirmed skill." **[INFERRED: `HermesService.resolve_contest`; NOT IMPLEMENTED: evidence removal]**

**Q13. Who makes the final decision?**
"The manager who owns the request, always. Only the owner can record a decision, and the server enforces that, not just the screen." **[VERIFIED: `test_request_hijack_is_refused_for_rank_resolve_and_decision`, `test_decision_for_non_shortlisted_candidate_is_422`]**

**Q14. What data does Hermes use?**
"Ticket descriptions (only the matched keywords and ticket number are kept, never the text), dated certificates, manager-confirmed skills, role definitions, and a demand weight per skill. It does not use 2025 manager ratings, client familiarity, soft skills, culture fit, protected attributes, or past staffing decisions." **[VERIFIED: `test_no_ticket_excerpt_in_db`, `test_baseline_isolation`; INFERRED: schema]**

**Q15. What is needed to move from prototype to enterprise deployment?**
"Six things. Real sign-in through the company identity provider. A managed database with encryption and backups. Live feeds from ServiceNow, the learning system, and HR. Human approval of the 673 pending skill labels and dating of 427 certificates, so real people can be scored. A validation study against manager judgement plus a fairness test on real data. And operations basics: monitoring, load testing, and a legal review for employment-related AI." **[VERIFIED counts: V6]**

**Q16. What is the biggest current limitation?**
"No real employee is scored, because none of the 673 workbook labels is mapped to a governed skill and none of the 427 certificates is dated. That is deliberate: mapping is a human governance step. Right behind it is that skill levels from tickets come from keyword rules, which are unproven on real ticket text." **[VERIFIED: V6, V8; PROTOTYPE ONLY: keyword rules]**

**Q17. What is the next logical phase?**
"Phase 8 governance: humans approve the label-to-skill mappings and certificate dates so the first real people can be scored. Then compare Hermes against the 2025 manager ratings, which the comparison tool already supports. Only after that, connect live systems and real sign-in." **[INFERRED: `docs/phase8/BLOCKED.md`, `scripts/phase8/baseline_agreement.py`]**

---

# Manager Questions

**Q1. How does a manager create a staffing request?**
*Screen:* Find people. *Action:* pick a role template, optionally open Advanced (request id, minimum coverage, shortlist size, the skill list), click **Find people**. *System:* `POST /api/fitness/rank` (`api/main.py: fitness_rank`) creates the request as `open`, owned by the signed-in manager, and stores the ranking. The UI generates an id like `req-20260924062921` (`web/src/views/Capability.tsx: newRequestId`). **[VERIFIED: V9]**

**Q2. How does Hermes determine who fits?**
For each required skill it looks up the person's skill record and multiplies five factors: level ratio × confidence × volume × freshness × relatedness. It averages across the required skills, then applies a small availability factor (0.85 to 1.0). Code: `FitnessGapEngine._fitness`, `src/fitness_gap/engine.py:176`. **[VERIFIED: V5]**

**Q3. Why is Alex ranked first?**
Alex is the only shortlisted person with direct evidence on the critical skill. Container orchestration: two tickets (a Kubernetes migration rollback and a Helm upgrade, both in July), a CKA certificate, and a manager-confirmed declaration, giving level 4 against a required 4, confidence 1.0, volume 0.5034, freshness 0.4153: contribution 0.2091. Azure networking: missing, 0. Infrastructure as code: related through container orchestration, half credit, 0.1045. Mean over three required skills = **0.1045**. **[VERIFIED: V5 reproduces 0.104531 exactly and matches the UI]**

**Q4. Why is Sam second?**
Sam has one ticket ("Terraform module for App Service", 2026-05-20), which yields Azure Compute level 3 and Infrastructure as Code level 2. Container orchestration and Azure networking are credited only through Azure Compute as related skills at half credit and a level ratio of 0.75. IaC is direct but at level 2 of 3 required. Confidence 0.35, volume 0.2953, freshness 0.786. Mean = **0.0384**. Sam covers all three skills, but thinly. **[VERIFIED: live UI value 0.0384; hand-computed 0.03837]**

**Q5. Why is Riley at zero?**
Riley's only evidence is a manager-confirmed declaration of Azure Compute at level 2. **Volume counts demonstrated evidence only**, and Riley has none, so volume = 0 and every contribution is 0. Riley still appears on the shortlist because a related skill (Azure Compute) gives coverage 2 of 3 (67%), above the 60% floor, and the critical skill counts as covered through that relationship. *Honest note:* showing a 0.0 person as a "recommendation" is a design choice a sceptic can challenge. **[VERIFIED: V5 experiment E1, live UI]**

**Q6. Why was Jordan excluded?**
Jordan has evidence on Azure networking only (a ticket and an AZ-700 certificate). That covers 1 of 3 required skills (33%), below the 60% floor: reason `below_min_coverage`. **[VERIFIED: live UI and V8]**

**Q7. Why was Casey excluded?**
Casey's only evidence is incident management (a SEV1 bridge ticket). Nothing touches any required skill: reason `no_evidence_on_any_required_skill`. **[VERIFIED]**

**Q8. Why does Alex only have about 10–11%?**
The score is a product of factors that are each below 1, then averaged with a zero for the missing skill. For Alex: volume 0.50 (two tickets; it needs about ten to reach 0.97), freshness 0.42 (the average of four evidence items, dragged down by a 327-day-old certificate at a 120-day half-life), a missing skill contributing 0, and a related skill at half credit. A "perfect" 100% would need many recent tickets, all evidence types, and direct evidence on every skill. The number is for *comparing* people, not a grade. It also drifts with the calendar: the same evidence gave 0.1196 at 1 Sep, 0.1047 at 24 Sep, and 0.0619 at 24 Dec. **[VERIFIED: V5 E2, E3, E10]**

**Q9. Does a missing skill automatically eliminate someone?**
No. A missing skill contributes 0 but stays in the denominator. Someone is eliminated only if (a) they have no evidence on any required skill, (b) their coverage is below the floor (default 60%), or (c) a skill marked *critical* is unmatched. Alex is missing Azure networking and is still ranked first. **[VERIFIED: E8; `src/fitness_gap/engine.py:91-101`]**

**Q10. What happens if two candidates have similar skills?**
Scores are compared at 4 decimal places. Exact ties go to the lower coded identity (`EMP-…` token), which is stable but arbitrary. There is no "statistical tie" concept, so a difference of 0.001 still ranks one above the other. **[VERIFIED: E6; NOT IMPLEMENTED: uncertainty bands]**

**Q11. Does availability matter?**
Barely, and not in the demo. The factor is `0.85 + 0.15 × allocation`, so even zero availability only multiplies the score by 0.85 and never excludes anyone. The screen has no availability input, and every person is loaded at allocation 1.0, so the factor is always exactly 1.0 today. The request also carries an `availability_required` field that is accepted and then ignored. **[VERIFIED: E5; PROTOTYPE ONLY; NOT IMPLEMENTED: `availability_required` is unused, no capacity data source]**

**Q12. Does certification matter?**
Yes, but not on its own. A certificate adds to the level vote (weight 0.30), raises confidence (a second kind of evidence; +0.2 more when paired with tickets), and its age counts in freshness. **A certificate alone contributes zero to the score** because volume is zero without tickets. Measured: cert only 0.0, one ticket 0.0905, ticket plus cert 0.2327. Certificates promoted from the workbook are recorded at a fixed level 3. **[VERIFIED: E1, E13; INFERRED: fixed level 3 at `service.py: promote_certificate`]**

**Q13. Does declared skill matter?**
A little. A manager-confirmed declaration has weight 0.15 in the level vote and counts as an extra kind of evidence for confidence. Alone it contributes zero (no volume). Unconfirmed declarations are ignored entirely. One caveat: each declaration is a separate record with no de-duplication, so four identical level-5 declarations outvote a single level-1 ticket in the level vote. Volume still limits the score effect. **[VERIFIED: E1, V8]**

**Q14. How is stale knowledge handled?**
Every evidence item decays by half-life: 0.5^(age ÷ half-life). Container orchestration and Azure networking use 120 days; most other pilot skills use 365. At one half-life the score contribution halves. A skill's freshness is the **average** of its items, so a very old certificate pulls a skill down even when recent work exists. **[VERIFIED: E3; documented AMBER in `docs/SCORING_SPECIFICATION.md` §4.5]**

**Q15. How does Hermes treat adjacent skills?**
As half credit (configurable, default 0.5) when the required skill is missing but a related skill exists. Relatedness is defined in the taxonomy and works in both directions. It applies in rankings only, not in learning gaps. *Note:* the critical-skill check also accepts an adjacent skill, so someone with no direct evidence on a critical skill can still pass it. **[VERIFIED: E7, E8; `FitnessGapEngine._lookup_skill`]**

**Q16. Can a manager override the recommendation?**
Yes: choose "someone else on the list" or "no one". The choice must be a shortlisted, non-excluded person. It cannot be someone outside the shortlist. The API does not force the label to match reality: a rank-3 person can be recorded as "accepted". The recorded `engine_rank_of_choice` (3 in that case) is what reveals it. **[VERIFIED: V8; `HermesService.decide`]**

**Q17. Does the manager's decision influence future recommendations?**
No. Decisions are written to the request record and the audit ledger only. Nothing in the scoring path reads them. **[VERIFIED: `test_decision_is_recorded_and_flagged_as_audit_only`; INFERRED: no read path in `skill_inference/` or `fitness_gap/`]**

**Q18. Can Hermes explain why somebody was excluded?**
Yes, with a machine-readable reason for each: `no_evidence_on_any_required_skill`, `below_min_coverage`, `missing_critical_skill`. Screen: Who fits → "Not a fit this time". **[VERIFIED: V9, `test_excluded_candidates_carry_machine_readable_reasons`]**

**Q19. Can a manager see the underlying evidence?**
Yes, per skill: evidence ids and source references (ticket numbers, certificate codes), on Why → "How the score was made". The ticket *text* is never stored. **[VERIFIED: V9; `test_no_ticket_excerpt_in_db`]**

**Q20. What happens if the required skill does not exist?**
The request is refused with a 422 naming the unknown skill ids. Skills must be in the governed ontology. **[VERIFIED: `test_invalid_rank_inputs_are_422`, `test_unknown_skill_evidence_is_rejected_not_scored`]**

**Q21. How does a manager know the recommendation isn't arbitrary?**
Every operand is in the payload: level ratio, confidence, volume, freshness, relatedness, the formula string, the config version, and the run id. `test_score_is_recomputable_from_payload_alone` recomputes the score from that payload. The rules are fixed and the same input gives the same output. **[VERIFIED]**

**Q22. Can the manager see real employee identities?**
It depends on the data. On the **synthetic demo**, any manager or admin can call `/api/identity/directory` and see every name. On **real data** that endpoint is refused (403 `directory_not_synthetic`) and names appear only through the controlled resolve step for shortlisted candidates on a request the manager owns. **[VERIFIED: V3; INFERRED: real-mode path from `api/main.py: identity_directory`]**

**Q23. How is identity resolution controlled?**
Four controls in `IdentityResolutionGateway.resolve_shortlist`: the requester must own the request, only shortlisted people can be resolved, the API limits it to 10 per minute, and every resolution is written to the audit ledger. **[VERIFIED: `test_request_hijack_is_refused_for_rank_resolve_and_decision`; INFERRED: rate limit from `api/main.py`]**

**Q24. What happens when a manager is not authorized?**
The server returns 403 with a structured `{detail, error}` body, and the UI shows a plain message ("You're not authorized…"). Examples: deciding another manager's request, updating someone who is not a direct report. Note the scope: managers can *see* the whole population's skills and rankings; only edits and per-person gap views are limited to direct reports, and requests are owner-only. **[VERIFIED: V3, V8, `test_rbac_matrix`, `test_gaps_acl_by_role`]**

---

# End User Questions

*A manager using Hermes for the first time.*

**Q1. What do I do first?**
Sign in, read the welcome card, click **Start looking**. You land on **Find people**. *(Screen: Welcome, then Find people.)*

**Q2. What information do I provide?**
Almost nothing: pick a role. Advanced options (skills, minimum coverage, shortlist size, request id) are optional.

**Q3. What does "Who fits" mean?**
It is the ranked list for the role you picked, best match first, with a section for people who were not a fit and why.

**Q4. Why is this person recommended?**
Click **Why**. You see each required skill with a tag: **Has it**, **Close** (a related skill), or **Missing**, plus the evidence behind it.

**Q5. What does the percentage mean?**
A relative score for comparing people for this role. It is not a pass mark. It is the average across the required skills of how strong, how well-evidenced, how much, and how recent the proof is.

**Q6. Why is the score so low?**
Because the demo has little history, and every factor is below 1. More recent work and more kinds of evidence raise it.

**Q7. Why is someone missing?**
They appear under **Not a fit this time** with a reason: too few of the needed skills, or no evidence on any of them.

**Q8. What does "evidence" mean?**
Work tickets that mention the skill, dated certificates, and skills a manager has confirmed. Work counts most.

**Q9. What does confidence mean?**
How many *different kinds* of evidence support the skill. One kind is 35%, two is 70%, all three is 100%. It does **not** check whether the sources agree with each other. **[VERIFIED: E13; note this differs from how the spec and voiceover describe it]**

**Q10. What does freshness mean?**
How recent the evidence is. It halves every 120 days for container orchestration and Azure networking, and every 365 days for most other skills.

**Q11. What does "adjacent skill" mean?**
A related skill. It counts for half in the ranking. For example, container work gives half credit toward infrastructure as code.

**Q12. Can I trust a certification?**
It counts, but a certificate alone will not lift a score, and it fades with age. Hermes records that the certificate exists and when it was earned; it does not verify it with the issuer. **[NOT IMPLEMENTED: issuer verification]**

**Q13. Can I choose somebody else?**
Yes: "Someone else on the list" or "No one". You cannot pick someone who is not on the shortlist.

**Q14. What happens after I choose somebody?**
The request is marked with your decision, who approved it, and when. It is logged. It does not change future recommendations. **[VERIFIED: V9]**

**Q15. Can Hermes tell me what that person should learn?**
It shows the **skill gaps** against a role, ordered by demand weight × how far the person is from the required level. It does not suggest courses: there is no catalogue. Demand weights are fixed numbers from the fixture, not live data. **[PROTOTYPE ONLY: demand weights; NOT IMPLEMENTED: learning catalogue, live demand feed]**

**Q16. Can I see the whole team's skills?**
Yes, on **Team skills**. Today it shows everyone in the database, not only your direct reports. **[VERIFIED: V8, V9]**

**Q17. Can I see employee names?**
In the demo, yes. On real data, names appear only for shortlisted candidates on your own request, through the resolve step.

**Q18. Can I challenge the recommendation?**
You can override it. You cannot change the score. An *employee* can flag a piece of evidence; you can then confirm (which adds a confirmed skill) or dismiss.

**Q19. Can I use Hermes without understanding the scoring formula?**
Yes. Find people, read Who fits, click Why. The formula view is optional.

**Q20. What happens if the system has insufficient evidence?**
Those people are excluded with a reason, and the page says the engine shortlisted nobody if no one qualifies. If someone has related-skill coverage but no demonstrated work, they can appear at 0.0.

---

# Architecture Questions

**Q1. Why FastAPI?**
*Choice:* FastAPI in `api/main.py`. *Why:* Pydantic request models give automatic 422s for bad input (unknown skill ids, levels outside 1–5), `Depends(require_roles(...))` puts role checks on each route, and one process serves the API and the built web app. It replaced Azure Functions for the local-first build (`PROJECT_BIBLE.md` §20 decision 3; `functions/` is kept only as history). *Cost:* endpoints are synchronous and call SQLite directly, so there is no async I/O benefit. **[INFERRED: source; VERIFIED: 422 behaviour in V3]**

**Q2. Why React/Vite?**
The bible locks "React animated console is the primary human UI" (decision 5). Vite builds static files that FastAPI serves (`WEB_DIST`). A hand-written typed client (`web/src/api/types.ts`, `endpoints.ts`, `http.ts`) keeps the UI honest about API shapes. *Cost:* types are not generated from the OpenAPI schema, so drift is caught by a contract test, not by the compiler. **[VERIFIED: V2 build and tests]**

**Q3. Why SQLite?**
Zero-ops, one file per environment, real transactions. `BEGIN IMMEDIATE` makes audit appends and request ownership atomic (`HermesDB.append_audit`, `save_staffing_request`). *Cost:* single writer, no encryption at rest, no row-level security, and the identity vault sits in the same file. The bible plans Azure SQL later (decision 4). **[INFERRED: `src/shared/db.py`]**

**Q4. Why local-first?**
No cloud approvals needed to run or demo, safe synthetic-only defaults, runs on a laptop. The Azure path (`infra/`, `power-platform/`, `functions/`) is stubs and is **not deployed**. **[PROTOTYPE ONLY for the Azure stubs]**

**Q5. Where is the composition root?**
`api/main.py: get_service()` lazily builds a `HermesDB`, then `HermesService` (`src/shared/service.py:46`), which constructs the identity gate, audit ledger, inference engine, fitness engine and resolution gateway, and finally calls `ensure_database_trusted`. Routes receive it via `Depends(get_service)`. The startup hook `_lifespan` validates secrets. **[VERIFIED: V7 startup behaviour]**

**Q6. What are the major bounded responsibilities?**

| Responsibility | Where |
|---|---|
| Identity abstraction (coding, PII/protected-attribute stripping) | `src/identity_abstraction/gate.py` |
| Skill inference (evidence to skill records) | `src/skill_inference/engine.py` |
| Fitness ranking and gaps | `src/fitness_gap/engine.py` |
| Identity resolution (names for shortlisted people) | `src/identity_resolution/gateway.py` |
| Audit ledger | `src/shared/audit.py`, `src/shared/db.py` |
| Persistence | `src/shared/db.py` + `infra/sqlite/001_schema.sql` |
| Trust and secrets | `src/shared/db_trust.py`, `src/shared/secrets.py` |
| Authentication and roles | `src/shared/auth.py`, `demo_identities.py`, `org.py`, `api/main.py` |
| Read models for screens | `src/shared/read_models.py`, `excel_sunset.py` |
| Workbook ingestion (Phase 8) | `src/phase8/*`, `scripts/phase8/*` |
| HTTP surface and RBAC | `api/main.py` |
| Presentation | `web/src/*` |

**Q7. Where is scoring implemented?**
Two files. `SkillInferenceEngine` (`src/skill_inference/engine.py`) turns evidence into a skill record with level, confidence, volume and freshness. `FitnessGapEngine` (`src/fitness_gap/engine.py`) turns skill records into a ranked fitness. Constants: `src/shared/config.py`.

**Q8. Where is identity abstraction implemented?**
`IdentityAbstractionGate` (`gate.py`): `tokenize` (line 58) computes `EMP-` + first 8 hex of `HMAC-SHA256(secret, normalised key)`; `abstract_record` (82) strips PII and rejects protected attributes at any nesting depth; `assert_no_pii` (121); `scan_for_identity_leakage` (137). **[VERIFIED: `test_nested_pii_blocked`, `test_token_stable_across_shuffle_orders`]**

**Q9. Where is identity resolution implemented?**
`IdentityResolutionGateway.resolve_shortlist` (`gateway.py:21`), called by `HermesService.resolve` (`service.py:246`), exposed at `POST /api/identity/resolve` (`api/main.py:608`).

**Q10. Where is authorization implemented?**
Token: `verify_token` / `build_principal` (`src/shared/auth.py`). Roles: `require_roles` (`api/main.py:163`). Team scope: `require_gap_access` (`src/shared/org.py`). Request ownership: `HermesService.rank/decide/resolve` plus the conditional SQL in `HermesDB.save_staffing_request` and `record_staffing_decision`.

**Q11. Where is audit implemented?**
`AuditLedger.append` (`src/shared/audit.py`) calls `HermesDB.append_audit` (`db.py:670`), which takes the write lock, links `prev_hash`, computes `row_hash` (`hash_audit_row`, `db.py:39`), and updates the external anchor. `verify_audit_chain` (707) and `_verify_anchor` (732) check it.

**Q12. Where is Phase 8 implemented?**
Library: `src/phase8/` (`workbook.py`, `parsers.py`, `normalize.py`, `quality.py`, `aliases.py`). Commands: `scripts/phase8/` (`ingest_baseline`, `ingest_real`, `ingest_certificates`, `promote_certs`, `baseline_agreement`, `real_data_report`). Tables: `baseline_assessments`, `account_context`, `skill_aliases`, `manager_aliases`, `cert_staging`, `phase8_ingest_runs`. API: `/api/data-quality`, `/api/taxonomy/pending`, `/api/certs/*`, `/api/baseline/matrix`.

**Q13. Why are these responsibilities separated?**
`docs/adrs/001-hybrid-build.md`: "Identity and fairness decisions must be reviewable line-by-line." The engines take config and data as arguments, so tests can pin them (`test_scoring_golden.py` feeds records straight to the fitness engine). Isolation is enforced by tests, for example the scoring modules must not reference `baseline_assessments`. *Honest note:* the engines are not perfectly pure, because they write their own audit events. **[VERIFIED: `test_scoring_modules_do_not_import_baseline_table`]**

---

# Scoring Questions

**Q14. Give me the exact scoring formula.**
```
level_ratio      = min(1, actual_level / required_level)
contribution(s)  = level_ratio × confidence × volume_score × freshness × adjacency_discount     (0 if the skill is missing)
mean             = Σ contribution(s) / (number of required skills)
fitness          = mean × ((1 − w) + w × allocation)          with w = 0.15, allocation in [0, 1]
```
*Implementation:* `FitnessGapEngine._fitness`, `src/fitness_gap/engine.py:203-211` (contribution), `245-258` (mean and allocation). *Tests:* `test_scoring_golden.py` (exact 0.504 / 0.4662 / 0.4284), `test_formula_string_matches_the_implemented_arithmetic`, `test_score_is_recomputable_from_payload_alone`. **[VERIFIED: V1, V5]**

**Q15. Why is level capped at 1?**
So a level-5 expert does not outscore a level-3 person on a level-3 need. The stated intent is "who meets this need", not "who is most senior", and it avoids the same experts winning every request. *Effect:* measured, actual level 5 against required 3 gives the same score as actual 3. *Cost:* no preference for a stronger person beyond a tie. **[VERIFIED: E4; rationale from `docs/SVP_DEMO_GUIDE.md` §6]**

**Q16. Why does missing evidence contribute zero?**
There is nothing to credit. The payload marks it `status: "missing"` with every operand null, so it is explicit, not hidden. **[VERIFIED: `test_missing_skill_is_explicit_not_absent`]**

**Q17. Why does missing evidence remain in the denominator?**
So a person is not rewarded for being evaluated on fewer skills. The mean is over *required* skills, not skills the person has. *Cost:* scores run low for partial matches, which is why Alex sits near 10%. **[VERIFIED: engine line 247; E8]**

**Q18. How is confidence calculated?**
`_score_group`, `src/skill_inference/engine.py:217-221`: `confidence = clamp(0.35 × number of distinct evidence types, 0.1, 1.0)`, plus 0.2 when demonstrated and certified evidence are both present. Any one type = 0.35; two = 0.70; demonstrated + certified = 0.90; all three = 1.00. **It counts kinds of evidence. It does not check whether the sources agree.** Documents that call it "agreement" overstate it. **[VERIFIED: E13]**

**Q19. How is volume calculated?**
`volume_score = 1 − exp(−0.35 × n_demonstrated)`, where `n_demonstrated` counts demonstrated evidence records for that person and skill (`engine.py:223-224`). Measured: 1 ticket 0.2953, 2 → 0.5034, 3 → 0.6501, 5 → 0.8262, 10 → 0.9698. Certificates and declarations contribute no volume. Re-ingesting the same ticket should not double count, because the evidence id is `ticket:skill` and staging upserts on it. **[VERIFIED: E2 values; INFERRED: the re-ingest behaviour, which I did not execute]**

**Q20. How is freshness calculated?**
Per evidence item: `0.5 ^ (age_in_days / half_life)`, clamped to [0, 1] (`freshness_score`, `engine.py:147`). Half-life is the skill's override in the ontology, else its class value (fast 90, medium 365, slow 1095 days). A skill's freshness is the **average** over its items (`engine.py:225`). Measured for a 120-day half-life: 60 days 0.707, 120 days 0.5, 240 days 0.25. **[VERIFIED: E3, V5]**
*Two catches.* (1) The stored freshness is fixed at the last recompute; nothing recomputes on a schedule, so it only refreshes when evidence is written. **[INFERRED: `HermesService.stage_and_merge`; NOT IMPLEMENTED: scheduled recompute]** (2) Every evidence write recomputes the entire matrix at "now", so a routine skill update moves everyone's freshness slightly.

**Q21. How is adjacency calculated?**
`_lookup_skill` (`fitness_gap/engine.py:150`): direct match → 1.0; else a related skill (forward relations, then reverse) → `config.adjacency_discount` (0.5); else missing. The adjacency map is built from the taxonomy's `related_skills` and `relations` in `HermesService.__init__`. **[VERIFIED: E7]**

**Q22. How does allocation affect the result?**
Multiplier `(1 − 0.15) + 0.15 × allocation`, range 0.85–1.0. Allocation is read from the `availability` table (1.0 for everyone at ingest) and can be overridden per request with an `availability` map. Allocation 0.5 gives ×0.925; 0 gives ×0.85. **[VERIFIED: E5; PROTOTYPE ONLY]**

**Q23. What configuration parameters affect scoring?**

| Env var | Field | Default | Used for |
|---|---|---|---|
| `HERMES_W_DEMO` / `_CERT` / `_DECL` | evidence-type weights | 0.55 / 0.30 / 0.15 | level vote only |
| `HERMES_HALF_LIFE_FAST` / `_MEDIUM` / `_SLOW` | class half-lives (days) | 90 / 365 / 1095 | freshness (fast is unused today; every fast skill has an override) |
| `HERMES_VOLUME_K` | volume steepness | 0.35 | volume |
| `HERMES_ALLOC_W` | allocation weight | 0.15 | availability multiplier |
| `HERMES_ADJACENCY_DISCOUNT` | related-skill credit | 0.5 | adjacency |
| `HERMES_MIN_COVERAGE` | coverage floor | 0.6 | exclusion |
| `HERMES_MAX_SHORTLIST` | shortlist cap | 10 | cap |
| (not overridable) | `min_confidence` | 0.1 | confidence floor |

`HERMES_HALF_LIFE` was removed and now makes startup fail. Code: `src/shared/config.py:96-108`. **[VERIFIED: `test_removed_global_half_life_env_var_is_refused`]**

**Q24. How is configuration versioned?**
`ScoringConfig.version` (`config.py:76-92`) is the first 12 hex characters of a SHA-256 over canonical JSON of the constants, the taxonomy fingerprint (keywords and adjacency), and each skill's effective half-life. The current value is `9220dcfdfcf3`. It is stamped on every skill record, ranking and calculation. `test_version_changes_if_and_only_if_scores_change` checks 11 parameters; `test_default_config_version_is_pinned` pins the value. **[VERIFIED: V1, V4, E11]**
*Limit, stated plainly:* the hash covers env-tunable constants and the taxonomy, **not** constants written into the inference code: the confidence steps (0.35, +0.2), the depth/surface keyword lists and level tiers, the volume formula's shape, or the certificate level of 3. Editing those changes scores without changing the version. **[INFERRED: `config.py:76-92` against `skill_inference/engine.py:29-49, 217-224`]** Also, `config.py`'s docstring cites `tests/unit/test_config_fidelity.py`; that file does not exist. The real test is in `test_v2_integrity.py`.

**Q25. Can the same input produce a different result?**
Not for the same evidence, taxonomy, config and `as_of` date: two runs were identical apart from `computed_at`. **[VERIFIED: E12, V4]** In the live app the recompute clock is "now", so the same evidence drifts over days: Alex-like evidence scored 0.1196 at 1 Sep, 0.1047 at 24 Sep, 0.0880 at 24 Oct, 0.0619 at 24 Dec **[VERIFIED: E10]**. `computation_run_id` is a random UUID per run, so identical inputs get different run ids (a known open gap, spec §10).

**Q26. Can the score be independently reproduced?**
From the payload alone, yes: every operand and the formula string ship with the result, and a test recomputes the score from them. From raw evidence, I did it by hand for Alex and matched 0.104531 exactly (Part "Trace one candidate"). Reproducing the operands themselves needs the rules in `docs/SCORING_SPECIFICATION.md`. **[VERIFIED: V5, `test_score_is_recomputable_from_payload_alone`]**

**Q27. How do you prove the frontend isn't changing the score?**
(1) A search of `web/src` for arithmetic on score fields finds only bar-width clamping and layout math **[VERIFIED: V10]**. (2) `web/src/lib/format.ts` states "Values are displayed, never recomputed"; the derivation panel substitutes backend numbers verbatim (`CandidateDetail.tsx: Derivation`). (3) `scoring.test.tsx` renders the real API fixture and asserts the displayed fitness equals the API value to 4 decimals. (4) `tests/api/test_ui_contract.py` fails if the fixture drifts from the live API. The UI only rounds for display (1 decimal for percent, 4 for the raw value). **[VERIFIED: V1, V2]**

---

# Evidence Questions

**Q28. What constitutes demonstrated evidence?**
A ticket whose description matches a skill's keywords (`SkillInferenceEngine.infer_from_ticket`). The level comes from rules: 11 "depth" words (migration, cluster, outage, rollback…), 6 "surface" words (password, reset, unlock…), and the strength of the keyword (multi-word or over 12 characters counts as stronger). Only the matched keywords and the ticket number are stored. **[PROTOTYPE ONLY: keyword heuristics tuned on the pilot fixture; real ticket text is unmeasured]**
*Verified defect class:* matching is plain substring matching. The Active Directory keyword `ad` matches "upgrade", "badge", "ahead", and "audit". Alex's Helm *upgrade* ticket therefore credits Alex with Active Directory level 3, visible on the Update skills screen. It does not change the demo ranking because that skill is not required. **[VERIFIED: V5, `taxonomy.match_keywords`]**

**Q29. How are evidence types weighted?**
Demonstrated 0.55, certified 0.30, declared 0.15, **only in the level vote** (`_score_group`, `engine.py:200-208`). They do not multiply the score. Their score effect is indirect: through the level, through confidence (number of types), and through volume (demonstrated only). **[VERIFIED: E1, E13]**

**Q30. Can declared skills dominate?**
Not the score: a declared-only skill has zero volume. They can decide the *level*: four identical level-5 declarations beat one level-1 ticket, because each declaration is a separate record with no de-duplication (3 declarations: level 1; 4: level 5). They are manager-only and limited to 10 per minute. **[VERIFIED: V8]**

**Q31. Can one noisy evidence source dominate?**
Volume saturates (10 tickets ≈ 0.97), so throughput cannot run away. The real noise risk is the substring keyword matcher adding spurious skills (Q28). One ticket can match several skills. **[VERIFIED: E2, matcher output]**

**Q32. How is evidence merged?**
`merge_evidence` → `_score_group` (`engine.py:159-236`): group by person and skill; drop unconfirmed declarations; level = highest weighted vote (ties go to the higher level), then lifted to the demonstrated mode if within one level; confidence by type count; volume by demonstrated count; freshness is the mean. Unknown skills raise `UnknownSkillError`. **[VERIFIED: V5, `test_unknown_skill_evidence_is_rejected_not_scored`]**

**Q33. How are stale observations handled?**
Decay only. Nothing is ever expired or deleted, and the decay is recalculated only when the matrix is recomputed. **[VERIFIED: E3; INFERRED: no scheduler]**

**Q34. What happens to negative evidence?**
**NOT IMPLEMENTED in the running pipeline.** `_negative_penalty` (reopened or escalated tickets lower the level) exists in `engine.py:63`, but `infer_from_ticket` never passes ticket metadata to it, and nothing in the code sets a `reopen` or `escalation` flag. The scoring specification describes it as active. **[VERIFIED: source-wide search finds only `engine.py:91` and the whitelist at `db.py:308`]**

**Q35. Can historical staffing decisions enter the model?**
No. They are stored for audit, with a `guardrail: never_score_on_historical_staffing_decisions` marker in the audit payload, and no scoring code reads them. **[VERIFIED: `test_decision_is_recorded_and_flagged_as_audit_only`]**

---

# Security Questions

*Each answer names the control, where it is enforced, and the test.*

**Q36. Why are identities coded?**
*Control:* pseudonymisation. *Enforcement:* `IdentityAbstractionGate.tokenize`. Scoring, the matrix, and most screens handle `EMP-xxxxxxxx`, so a bug or a log cannot leak a name from those paths. *Test:* `test_nested_pii_blocked`, `test_token_stable_across_shuffle_orders`. It is pseudonymous, not anonymous: the reverse map is stored (Q47).

**Q37. Can the frontend reverse an identity?**
Not by computation: it never holds the secret. It can obtain names only where the API deliberately returns them: `/api/identity/directory` on synthetic data, or the resolve step on real data. **[VERIFIED: employee gets 403 on the directory, V3; INFERRED: real-data path]**

**Q38. Who can resolve identities?**
The manager who owns the request, for shortlisted people only. *Enforcement:* `require_roles(MANAGER)` and `IdentityResolutionGateway.resolve_shortlist`. On synthetic data, any manager or admin can also read the full directory. **[VERIFIED: V3, `test_request_hijack_is_refused_for_rank_resolve_and_decision`]**

**Q39. How is identity resolution audited?**
Each resolution appends an `identity_resolution` event with the request id and resolved tokens, hash-chained like every other event. **[VERIFIED: demo safeguard in V4; `test_resolution_step_is_the_only_place_names_appear`]**

**Q40. Can a manager impersonate another manager?**
In the demo, yes, trivially: `POST /api/auth/token {"sub":"demo-manager-2"}` returns a token with no password. That is the demo registry, not real authentication. **[VERIFIED: V3; PROTOTYPE ONLY]** With `HERMES_ENV=production` the endpoint returns 403 and nobody can log in until a real identity provider is added. **[VERIFIED: V7]**

**Q41. Can a user manipulate role claims?**
*Control:* the token carries only `sub`; roles and coded identity are looked up server-side on every request; tokens with `roles`, `coded_identity`, `role` or `groups` claims are rejected as forged (`FORBIDDEN_CLAIMS`, `auth.py`). *Tests:* `test_validly_signed_token_with_forged_role_claim_is_rejected`, `…_forged_coded_identity_…`, `test_token_endpoint_rejects_client_asserted_roles_and_identity`. *Caveat:* HS256 with a shared secret means anyone holding `HERMES_JWT_SECRET` can mint a token for any registered principal. **[VERIFIED: V1]**

**Q42. Can request ownership be hijacked?**
No. *Control:* ownership is written once and never updated; the update SQL is conditional on the stored owner and `open` status (`HermesDB.save_staffing_request`), and the service checks too. *Tests:* `test_request_hijack_is_refused_for_rank_resolve_and_decision`, `test_hijacked_rank_leaves_no_audit_or_shortlist_change`, `test_db_layer_refuses_ownership_overwrite_even_without_service_check`. **[VERIFIED]**

**Q43. Can a non-owner make a decision?**
No: 403. *Enforcement:* `HermesService.decide` plus the conditional `UPDATE` in `record_staffing_decision`. Live: `demo-manager-2` deciding another manager's request was refused. **[VERIFIED: V3]**

**Q44. Can an employee access another employee's data?**
No. `/api/me` is bound to the server-side identity; gap views require self, direct report, or admin; employees get 403 on manager routes. Employees can read the skills catalogue and role definitions, which are not personal. *Tests:* `test_me_is_bound_to_the_server_side_identity`, `test_gaps_acl_by_role`, `test_rbac_matrix`. **[VERIFIED: V1, V3]**

**Q45. What happens if the identity secret is missing?**
The app refuses to start (`RuntimeError`, exit code 3). Published fixture secrets are rejected outside test mode. *Test:* `test_fail_closed_secret_outside_test_mode`, `test_published_fixture_secret_is_rejected_without_test_mode_flag`. **[VERIFIED: V7, V1]**

**Q46. What happens if the database is untrusted?**
The API returns 503 with a reason code, for example `missing_trust_metadata`, `identity_secret_mismatch`, `real_database_in_test_mode`, `published_identity_secret`, `reversible_identity_mapping`. *Enforcement:* `assess_database_trust` in `db_trust.py`. A brand-new empty database is trusted by design. **[VERIFIED: `test_api_refuses_to_serve_a_database_without_trust_metadata` and the `test_v2_integrity.py` trust tests]**

**Q47. What happens if the database is copied?**
The file carries everything. `identity_vault` stores `display_name` and the raw `source_employee_key` in plaintext in the same SQLite file, and there is no encryption at rest. The trust check stops the *app* serving a mismatched database; it does nothing to protect a copied file. In real-data ingestion names come from the workbook (`ingest_baseline.py:167` passes `name`), so the real database's vault holds real names. I did not open the vault. On this machine `data/real/hermes_real.db` has mode 0644 (readable by other local users). **[INFERRED: schema and ingest code; VERIFIED: file mode from `ls -la`]** *Fix direction:* encrypted storage, tighter file mode, vault kept apart from the scoring database.

**Q48. What happens if someone modifies the audit ledger?**
Detected. Editing a row breaks the hash chain; deleting the newest events, emptying the ledger, or recomputing the whole chain is caught by the external signed anchor. `/ready` returns 503, and Overview shows "Audit trail check failed". *Tests:* `test_anchor_detects_event_modification`, `…_middle_deletion`, `…_latest_event_deletion`, `…_deletion_of_all_events`, `…_recomputed_forged_chain`, plus my `test_ready_fails_when_audit_chain_is_tampered`. **[VERIFIED: V1]**
*Limits:* not WORM. The anchor sits next to the database by default and is signed with `IDENTITY_MAP_SECRET` (or `HERMES_AUDIT_ANCHOR_KEY`), so an attacker with file write access and that key can forge both. Set `HERMES_AUDIT_ANCHOR_DIR` to storage the app cannot write. Verification runs on demand (`/ready`, Overview, CI), not continuously, and with no key configured (test mode) the anchor is unsigned. Free-text notes typed by users (override notes, contest reasons) are stored verbatim in the audit payload with no scrubbing. **[INFERRED: source]**

---

# Data Questions

**Q49. What is the source of truth?**
Evidence lives in `evidence_staging`; the skills matrix (`skills_matrix`, with `skills_matrix_history`) is derived from it and can be recomputed. The governed skill list is `taxonomy/skills_ontology.yaml` plus `pilot_ontology.yaml` (49 skills). Role requirements live in `role_profiles`. The 2025 workbook is baseline only, never source of truth for scoring.

**Q50. What is synthetic data?**
Five invented people E1001–E1005 with 5 tickets, 2 certificates and 2 declarations (`data/fixtures/pilot_population.json`), stored in a database marked `synthetic` in `hermes_meta`. **[VERIFIED: V3, V9]**

**Q51. What is real data?**
The 2025 Skill Matrix workbook, ingested into `data/real/hermes_real.db` (gitignored, classification `real`). **[VERIFIED: V6]**

| Measure | Value |
|---|---|
| Sheets / people | 22 / 310 |
| Cells processed / accepted / rejected | 13,243 / 12,852 / 391 |
| Rejections by reason | non_numeric_cell 198, missing_name 136, fractional_average 38, group_or_section_header 17, out_of_range_value 1, section_header 1 |
| Workbook skill labels | 673 (mapped **0**, pending **673**) |
| Labels rejected by rule | client/account 8, soft skill 13, culture fit 1 |
| Certificates | 427 staged, 5 exact code, 422 pending, **0 dated** |
| Scored population | **0** |

**Q52. How does the 2025 workbook enter Hermes?**
`open_workbook` → `parse_sheet` → per-cell validation (`src/phase8/parsers.py`) → names abstracted through `IdentityAbstractionGate` → `baseline_assessments`, `account_context`, `cert_staging`. Labels go through `SkillAliasResolver` and stay `pending`. It requires a strong secret (32+ characters, 10+ distinct) and refuses test mode. *Tests:* `test_real_data_ingest_refuses_test_mode`, `…_denylisted_secret`, `test_workbook_parsers.py`. **[VERIFIED: V1, V6]**

**Q53. What happens to invalid rows?**
Each is rejected with a code from a closed vocabulary (`RejectionReason`), counted in the quality report, and never silently stored. Out-of-range values used to become an unexplained NULL and are now explicit rejections. **[VERIFIED: V6; tests in `test_workbook_parsers.py`]**

**Q54. What happens to Group Average rows?**
Detected explicitly (`_row_is_group_average`) and rejected as `group_or_section_header` (17 in the real file). Fractional cell values, which are averages, are rejected as `fractional_average` (38). **[VERIFIED: V6]**

**Q55. What happens to soft skills?**
Labels in `EXCLUDED_ASSESSMENT_FIELDS` (communication, customer service, flexibility, knowledge sharing, "technical expertise", "tools expertise" and others) are dropped and logged as `soft_skill_excluded`: 13 in the real file. *Test:* `tests/guardrails/test_soft_skill_exclusion.py`. **[VERIFIED: V1, V6]**

**Q56. What happens to culture-fit fields?**
`classify_assessment_column` raises `CultureFitForbiddenError` for direct callers; the sheet parser logs the column as `culture_fit_forbidden_column` and skips it: 1 label in the real file. **[VERIFIED: V6; INFERRED: `parsers.py:95-99`]**

**Q57. What happens to client/account labels?**
Columns matching the client blocklist are routed to `account_context` (which has a `familiarity_raw` column) and never reach scoring: 8 in the real file. The blocklist is `config/client_names.txt` (gitignored) with `client_names.example` as fallback, and the Docker image ships only the example. *Test:* `test_account_context_isolation.py`. **[VERIFIED: V1, V6]** The voiceover line "client familiarity… not even fields" is wrong: a table exists; it is isolated, not absent.

**Q58. Why aren't all workbook labels automatically mapped?**
`SkillAliasResolver.resolve` matches only exact ontology names, human-approved aliases, or an exact slug; everything else is `pending`: "never fuzzy-match into a live skill_id". A wrong automatic mapping would silently corrupt every downstream score, and there are 673 labels against 49 governed skills. **[VERIFIED: `test_labels_without_an_exact_code_stay_unmapped`, V6]**

**Q59. Why isn't real employee scoring currently claimed?**
Zero labels are mapped, zero certificates are dated, and the scored population is 0. There is nothing to score honestly. *Test:* `test_real_mode_fixture_reports_no_fake_scoring`. **[VERIFIED: V6, V1]**

---

# API Questions

**Q60. How does the frontend get data?**
A typed client: `web/src/api/http.ts` (`apiFetch`, adds the Bearer token kept in `sessionStorage["hermes.token"]`), `endpoints.ts` (one function per route), `types.ts`. Views load through the `useApi` hook with abort signals. **[VERIFIED: V9]**

**Q61. Does React calculate anything important?**
No. Only formatting and layout. **[VERIFIED: V10]**

**Q62. How do you guarantee UI/API consistency?**
Three layers: TypeScript types; a contract fixture (`web/src/test/fixtures/api-contract.json`) generated from the live API by `scripts/export_ui_contract.py`; and `tests/api/test_ui_contract.py`, which fails on shape drift. Vitest renders the fixture and asserts the screen equals the API values. *Limits:* types are hand-written; the shape check looks at the first element of each list. **[VERIFIED: V1, V2]**

**Q63. What happens if an API returns stale data?**
The ranking screen shows the stored ranking exactly as computed. There is **no warning** if evidence has changed since, only a "Computed at" time on the derivation tab. **[NOT IMPLEMENTED: staleness indicator]** The UI fetches on navigation with no cache layer. **[INFERRED]**

**Q64. How are authorization failures handled?**
The server returns 401/403 with `{detail, error}`. `ApiError` maps codes to plain sentences, and a 401 fires `hermes:unauthorized`, which signs the user out. Menus are also filtered by role, but the server is the authority. *Tests:* `http.test.ts`, `test_error_responses_are_structured`. **[VERIFIED: V1, V2, V3]**

**Q65. How is request state persisted?**
In `staffing_requests`: owner, status (`open` → `accepted` / `rejected` / `overridden`), shortlist, exclusions, the full ranking payload, requirements, and decision fields. Re-ranking is allowed while `open`; after a decision it returns 409. **[VERIFIED: `test_rerank_after_decision_conflicts`]**

**Q66. Why is the ranking payload saved?**
So the screen is a read model of what was decided on: `GET /api/staffing/requests/{id}` returns it verbatim and never re-ranks. Decisions are validated against the stored shortlist and exclusions. *Trade-off:* a manager can look at a snapshot that is no longer current (Q63). *Alternative:* re-rank on view, which would show numbers that drift and no longer match what was decided. **[VERIFIED: V3; `api/main.py:435`]**

---

# Testing Questions

**Q67. What does the test suite actually prove?**
389 backend tests: scoring golden values and inspector recomputation; config-version rules; identity gate and PII rejection; RBAC, request ownership, forged claims, token defects; the audit chain and anchor; database trust and secret policy; workbook parsing, quality codes, and isolation guardrails; and demo determinism. 83 frontend tests: rendering of real API payloads, navigation by role, error handling. **[VERIFIED: V1, V2]**

**Q68. What does 92% coverage mean here?**
Statement coverage of six `src/` packages only (`identity_abstraction`, `skill_inference`, `fitness_gap`, `identity_resolution`, `shared`, `phase8`), with an 85% gate (`pyproject.toml` `addopts`). **[VERIFIED: V1]**

**Q69. What is NOT covered?**
- `api/main.py` (943 lines, the enforcement layer) and `scripts/` are outside the measurement, although tests exercise them. The frontend has no coverage measurement.
- `shared/demand.py` is 0% (an unused stub). Weakest measured: `phase8/workbook.py` 72%, `normalize.py` 73%.
- No test asserts an exact volume, confidence, or level number computed from raw evidence (a search for 0.2953 and 0.5034 in `tests/` finds nothing). The golden test pins the fitness stage; the upstream constants are covered only by sensitivity tests.
- No load test, no automated browser test, no penetration test. Latency is tested on 5 people. **[VERIFIED: coverage report, searches; INFERRED: the rest]**

**Q70. What does the 55-point live self-test prove?**
Over real HTTP against a running instance: the app and its security headers are served; path traversal is blocked; missing or forged tokens are refused; roles are enforced; ranking input is validated and ordered; requests persist; decisions record and cross-manager decisions are refused; gaps, skill updates, and contests follow team scope; and the audit chain still verifies after all writes. It does not prove scale, real sign-in, or that levels are correct. **[VERIFIED: V3]**

**Q71. What does the browser walkthrough prove?**
That real screens show the API values, the flows work for manager and employee, and there are no console errors. It is manual, not automated. **[VERIFIED: V9]**

**Q72. What security tests exist?**
`tests/security/test_v2_api_hardening.py` (27 tests: hijack, RBAC matrix, forged claims, validation, untrusted DB), `test_tier0.py` (11: PII, fail-closed secrets), `test_spa_path_traversal.py`, `test_hosting_hardening.py` (12: headers, `/ready`, CORS, production mode), plus `test_v2_integrity.py` (audit anchor, database trust, secret policy). **[VERIFIED: V1]**

**Q73. What happens if scoring changes accidentally?**
Changing the fitness formula fails `test_scoring_golden.py`. Changing an env-tunable constant or the taxonomy changes the version and fails the pinned-version test. Changing a constant written into the inference code (Q24) is **not** caught by an exact-value test. **[VERIFIED: V1; INFERRED: the gap]**

**Q74. How do you test determinism?**
`tests/e2e/test_demo_determinism.py::test_two_runs_produce_identical_transcripts` runs the 14-step demo twice into separate databases with a pinned clock and run id and compares the transcripts. `demo_svp --verify` does the same. It proves repeatability, not that numbers never change. **[VERIFIED: V1, V4, E12]**

**Q75. How do you test baseline isolation?**
Behavioural: `test_merge_rank_gaps_identical_with_baseline_populated_or_empty` inserts baseline rows and asserts merge, rank and gaps are unchanged. Static: `test_scoring_modules_do_not_import_baseline_table` searches the three scoring files for the table name. The demo also injects manager ratings and re-ranks. *Weakness:* the static check is a text search. **[VERIFIED: V1, V4]**

---

# Production Questions

**Q76. Is this production-ready?**
No. It is a hardened prototype: safe as a synthetic-data demo behind company access control, not yet ready for real employees. **[VERIFIED: V3, V7]**

**Q77. What is missing?**
Real sign-in; a managed, encrypted database; live integrations; governed skill mapping and certificate dating; validation against manager judgement; fairness testing on real data; monitoring; load testing; backups and recovery; a legal review. Each is listed below.

**Q78. What happens to authentication?**
Today: HS256 shared secret and five demo principals with no password. Production mode disables it with nothing in its place, so nobody can log in. Swap points: `verify_token` and `build_principal` in `src/shared/auth.py`; `POST /api/org/bind-principal` and `principal_bindings` already link a sign-in to an employee. **[VERIFIED: V7; PROTOTYPE ONLY; NOT IMPLEMENTED: identity provider]**

**Q79. What happens to the database?**
SQLite is a single-writer file: run one instance with a persistent volume. Moving to a managed database means changing `src/shared/db.py` (1,106 lines) and the schema in `infra/sqlite/`. **[INFERRED]**

**Q80. What happens to rate limiting?**
`RateLimiter` (`src/shared/rate_limit.py`) is in memory, per process, 10 calls per minute, and applied only to identity resolve and skill declarations. Rank, decision, contest, and the token endpoint are not throttled. **[VERIFIED: `api/main.py` read; NOT IMPLEMENTED: edge or global limits]**

**Q81. What happens to observability?**
Only uvicorn access logs, `/health`, `/ready`, and the audit ledger. No metrics, tracing, or structured logs. **[NOT IMPLEMENTED]**

**Q82. What happens to backups?**
**NOT IMPLEMENTED.** The database and its `.audit-anchor.json` must be backed up and restored together.

**Q83. What happens to disaster recovery?**
**NOT IMPLEMENTED.** No replication or failover; one file on one disk.

**Q84. What happens to real identity provider integration?**
**NOT IMPLEMENTED.** The design is right, since the token proves who and the server decides roles, but no provider is connected.

**Q85. What happens to ServiceNow/LMS/HR integrations?**
**NOT IMPLEMENTED.** The only ingestion API is `POST /api/ingest/tickets` (admin, up to 200 tickets per call). The Power Automate flow files and the `functions/` host are unreviewed stubs; fixtures stand in for the real sources. **[PROTOTYPE ONLY]**

**Q86. What happens when thousands of users access the system?**
Not load-tested. Structural limits: SQLite single writer; every evidence write reloads all evidence and replaces the whole matrix (`stage_and_merge`); ranking loads the entire matrix per request; `/api/workforce` and `/api/matrix/runs/{id}` return everything unpaginated; the latency test covers 5 people. **[INFERRED; NOT VERIFIED at scale]**

---

# Architecture Decisions

Format for each: **WHAT** we chose, **WHY**, **ALTERNATIVES**, **GAIN**, **COST**, **FUTURE** (how it changes for production).

**FastAPI**
- **WHAT:** FastAPI app in `api/main.py` serving the API and the built UI.
- **WHY:** Pydantic validation (422 on bad input), per-route role dependencies, single process for API + UI, and it replaced Azure Functions for the local-first build (bible decision 3).
- **ALTERNATIVES:** Azure Functions (kept as history in `functions/`), Flask, Django, ASP.NET.
- **GAIN:** validation and RBAC in a few lines, generated OpenAPI.
- **COST:** synchronous handlers over SQLite (no async benefit); a global service singleton (`_SERVICE`) that tests must reset.
- **FUTURE:** run several workers behind a gateway only after the database and rate limiter are shared; or move to the Azure host the bible anticipates.

**React (Vite)**
- **WHAT:** React 18, Vite, react-router, framer-motion, self-hosted Inter font.
- **WHY:** bible decision 5, a rich explainability UI (score ledger, team grid).
- **ALTERNATIVES:** server-rendered pages, Streamlit, Power Apps/Power BI (which the bible reserves for narration).
- **GAIN:** interactive derivation view, testable components, static hosting.
- **COST:** a build step and a UI codebase to maintain.
- **FUTURE:** keep; add a sign-in redirect flow and a generated API client.

**SQLite**
- **WHAT:** one SQLite file per environment (`infra/sqlite/001_schema.sql`).
- **WHY:** zero-ops local-first; real transactions for atomic audit and ownership writes.
- **ALTERNATIVES:** Azure SQL, Postgres.
- **GAIN:** trivial setup, a single file that carries its own trust metadata.
- **COST:** single writer, no encryption at rest, no row-level security, plaintext identity vault in the same file.
- **FUTURE:** managed database; move the vault to a separately secured store; encrypted volumes; backups.

**Coded identity**
- **WHAT:** `EMP-` + 8 hex from `HMAC-SHA256(secret, normalised key)`.
- **WHY:** keep names out of scoring and most of the UI; fairness by architecture.
- **ALTERNATIVES:** random ids with a lookup table; full anonymisation; no coding.
- **GAIN:** stable ids across ingests without a lookup, so sources join cleanly; collisions are handled by walking the digest.
- **COST:** pseudonymous, not anonymous. The reverse map is stored, 8 hex is only 32 bits, and changing the secret changes every token (the fingerprint check refuses a mismatched database).
- **FUTURE:** vault in a managed key store; a rotation plan.

**Deterministic scoring**
- **WHAT:** fixed rules and a visible formula; no model.
- **WHY:** auditability, reproducibility, and a defensible posture for an employment-related tool (bible §23).
- **ALTERNATIVES:** machine-learned ranker; embedding or language-model scoring.
- **GAIN:** every number is explainable and testable.
- **COST:** heuristics are brittle (keyword substring matching), constants are hand-set and unvalidated, and nothing learns.
- **FUTURE:** keep rules for ranking; improve evidence extraction and calibrate constants against a validation set, with each change versioned.

**Phase 8 (baseline as judge, not seed)**
- **WHAT:** the 2025 workbook lands in isolated tables and is never a scoring input; label mapping is human-approved.
- **WHY:** the workbook has undefined scales and 673 free-text labels; seeding the engine with it would import its noise.
- **ALTERNATIVES:** seed the matrix from the workbook; fuzzy auto-mapping.
- **GAIN:** protects scoring integrity and enables an honest agreement check later.
- **COST:** cold start. No real person is scored until governance completes.
- **FUTURE:** approve mappings, date certificates, run the agreement harness, then decide whether any of it should be used.

**Typed API client**
- **WHAT:** hand-written TypeScript types and one function per route, plus a contract fixture.
- **WHY:** catch UI/API drift early without a code generator.
- **ALTERNATIVES:** OpenAPI code generation, GraphQL.
- **GAIN:** compile-time shapes and a test that fails on drift.
- **COST:** manual upkeep; the shape check inspects only the first list element.
- **FUTURE:** generate types from OpenAPI.

**Saved ranking payload**
- **WHAT:** the full ranking response is stored in `staffing_requests.result_json` and replayed verbatim.
- **WHY:** what the manager saw is what they decided on; decisions are validated against the stored shortlist.
- **ALTERNATIVES:** re-rank on every view.
- **GAIN:** consistency and audit-grade evidence of what was shown.
- **COST:** a snapshot can go stale with no warning.
- **FUTURE:** show a "newer evidence exists" indicator by comparing run ids.

**Audit chain**
- **WHAT:** SHA-256 hash chain in SQLite plus a signed external anchor file.
- **WHY:** tamper evidence with no extra infrastructure.
- **ALTERNATIVES:** WORM storage, an immutable blob, an external log service.
- **GAIN:** detects edits, deletions (including the newest events), and a recomputed chain.
- **COST:** not WORM; the anchor sits beside the database by default and is signed with an app secret; verification is on demand.
- **FUTURE:** anchor to separate or immutable storage (`HERMES_AUDIT_ANCHOR_DIR`), alert on `/ready` failures, and protect the data tables too (only the ledger is chained today).

**Local authentication**
- **WHAT:** HS256 JWT and a registry of five demo principals.
- **WHY:** exercise role and ownership logic without an identity provider.
- **ALTERNATIVES:** OIDC against the company provider from day one.
- **GAIN:** the hard part (server-derived roles, ownership) is built and tested.
- **COST:** no real authentication; anyone can sign in as any demo principal.
- **FUTURE:** verify provider tokens in `verify_token`, map roles from the directory in `build_principal`.

**Synthetic demo mode**
- **WHAT:** `HERMES_TEST_MODE=1` plus a database classified `synthetic`; published fixture secrets are accepted only there.
- **WHY:** allow safe demos and tests while making real data refuse test mode (`real_database_in_test_mode`, `published_identity_secret`).
- **ALTERNATIVES:** a separate demo codebase.
- **GAIN:** the safety rules are testable in one code path.
- **COST:** synthetic tokens are forgeable by anyone who has the repository. That is acceptable for invented people and never for real ones.
- **FUTURE:** keep demo and production as separate deployments.

---

# End-to-End Trace

**Request:** Senior Cloud Engineer (container orchestration ≥ 4 and critical, Azure networking ≥ 4, infrastructure as code ≥ 3, coverage floor 0.6). Values are from the live demo database ingested 2026-09-24. **[VERIFIED: V5, V8, V9]**

*Steps 4–9 run when evidence is loaded (`stage_and_merge`), not at ranking time. Ranking reads the stored skill records.*

| # | Step | File → function / class | Data structure | Input → output |
|---|---|---|---|---|
| 1 | User input | `web/src/views/Capability.tsx` (`newRequestId`, `fromRole`, submit) → `web/src/api/endpoints.ts` `requestsApi.rank` → `api/http.ts apiFetch` | `RankBody` (`api/types.ts`) | role choice → `POST /api/fitness/rank` with Bearer token, body `{request_id, required_skills, critical_skills, min_coverage_ratio, role_id, shortlist_size}` |
| 2 | Request creation | `api/main.py: fitness_rank` (line 531) → `StaffingRequest` (`src/shared/models.py:81`) | `StaffingRequest` (frozen) | body + verified principal → request with `requester_id = principal.sub` (client-sent requester ignored) |
| 3 | Validation | `RankBody` validators; `_validate_levels`; `require_roles(MANAGER)`; role merge via `db.get_role`; ownership in `HermesService.rank` (`service.py:189`) | pydantic errors, `RequestOwnershipError`, `RequestStateConflict` | skill ids ∈ ontology, levels 1–5, id pattern, shortlist 1–10; role's critical skills and floor can be tightened, never loosened; existing request must be owned and `open` |
| 4 | Requirements | `infra` fixture → `db.upsert_role`; table `role_profiles` | `{container_orchestration:4, azure_networking:4, infrastructure_as_code:3}`, critical `[container_orchestration]`, floor 0.6 | role id → requirements |
| 5 | Evidence retrieval | `HermesService.stage_and_merge` (`service.py:145`) → `db.load_all_evidence` (`db.py:338`) | `List[EvidenceRecord]` from `evidence_staging` | rows → records (at load time) |
| 6 | Skill inference | `SkillInferenceEngine.infer_from_ticket` (`engine.py:94`), `taxonomy.match_keywords`, `_demonstrated_level` (72) | `EvidenceRecord(type=demonstrated)` | ticket text → skill ids and level; only keywords and ticket number stored |
| 7 | Confidence | `_score_group` (`engine.py:217-221`) | float | distinct evidence types → 0.35 per type, +0.2 demo+cert, cap 1.0 |
| 8 | Volume | `_score_group` (223-224) | float | demonstrated count → `1 − e^(−0.35n)` |
| 9 | Freshness | `freshness_score` (147), `half_life_for_skill` (133), mean at line 225 | float | ages and half-lives → mean of `0.5^(days/half-life)` → `SkillRecord`, saved by `db.replace_skills_matrix` (358) |
| 10 | Adjacency | `FitnessGapEngine._lookup_skill` (`fitness_gap/engine.py:150`); adjacency map from `HermesService.__init__` | `(record, discount, source_skill)` | required skill + person's records → direct 1.0, related 0.5, or missing |
| 11 | Contribution | `_fitness` (176-243) | `SkillContribution` (`models.py:101`) | level ratio × confidence × volume × freshness × discount |
| 12 | Fitness | `_fitness` (245-270); allocation from `db.get_allocation` | `CalculationDetail` (`models.py:137`) | mean over required skills × allocation multiplier → score |
| 13 | Ranking | `rank_candidates` (53-148): exclusions (91-101), sort `(-score, coded_identity)` (114), cap (115) | `RankedCandidate`, `FitnessResult` | all people → shortlist + `excluded_candidates` |
| 14 | Shortlist saved | `HermesService.rank` → `db.save_staffing_request` (574); audit `fitness_ranking` | `staffing_requests` row (`result_json`, `shortlist_json`, `excluded_json`) | result → stored verbatim, status `open` |
| 15 | UI | redirect `/requests/{id}` → `views/RequestDetail.tsx` → `GET /api/staffing/requests/{id}` (`api/main.py:435`, `read_models.request_summary`); `lib/format.ts` (`pct`, `fixed`); names via `lib/names.tsx` | `RequestDetail` (`types.ts:200`) | stored payload → table (rank, name, 10.4%, 0.1045, "evidence for 2 of 3 skills"); exclusions; decision form |
| 16 | Manager decision | `RequestDetail` form → `POST /api/staffing/{id}/decision` (`api/main.py:636`) → `HermesService.decide` (`service.py:270`) → `db.record_staffing_decision` (`db.py:800`) | `DecisionBody`, updated row | status + chosen id → checks: exists → owner → open → shortlist present → candidate named → not excluded → on shortlist; records `engine_rank_of_choice` |
| 17 | Audit | `AuditLedger.append` (`audit.py`) → `HermesDB.append_audit` (`db.py:670`) → `_write_anchor` | `audit_ledger` row (`prev_hash`, `row_hash`, `seq`) plus anchor file | events `evidence_ingestion`, `inference_computation`, `fitness_ranking`, `staffing_decision` → chained and anchored |

---

# Trace One Candidate: Alex Rivera

*As of 2026-09-24 06:05 UTC, matching the live screen. Every number below was reproduced by executing the engines.* **[VERIFIED: V5, Appendix A]**

| Stage | Where it comes from | Value |
|---|---|---|
| **Raw evidence** | fixture `pilot_population.json` | ticket INC001 (2026-07-01) "Kubernetes migration rollback for prod cluster"; ticket INC002 (2026-07-15) "Helm chart upgrade on k8s worker pool"; certificate CKA level 4 (2025-11-01); manager-confirmed declaration container orchestration level 3 (2026-01-15) |
| **Skill match** | `taxonomy.match_keywords` | INC001 → container orchestration (`kubernetes`, `kube`) and workload migration (`migration`); INC002 → container orchestration (`k8s`, `helm`) and Active Directory (`ad`, a false positive from "upgrade") |
| **Ticket levels** | `_demonstrated_level` | INC001: three depth words (migration, rollback, cluster) → level 4. INC002: one depth word (upgrade) → level 3 |
| **Level (skill)** | `_score_group` vote | level 4 gets 0.55 (INC001) + 0.30 (cert) = 0.85; level 3 gets 0.55 (INC002) + 0.15 (declared) = 0.70 → **level 4** |
| **Confidence** | 3 distinct types × 0.35 = 1.05 → capped 1.0 (+0.2 also capped) | **1.0** |
| **Volume** | 2 demonstrated records: 1 − e^(−0.35×2) | **0.5034** |
| **Freshness** | half-life 120 d (container orchestration override); ages 84.8, 70.8, 327.3, 252.3 days → 0.6129, 0.6645, 0.1510, 0.2329; mean | **0.4153** |
| **Contribution: container orchestration** | 4/4 → ratio 1.0; 1.0 × 1.0 × 0.5034 × 0.4153 × 1.0 | **0.2091** |
| **Contribution: Azure networking** | no evidence, no related skill present | **missing, 0** |
| **Contribution: infrastructure as code** | missing directly; related to container orchestration (IaC lists it as a related skill); ratio min(1, 4/3) = 1.0; 1.0 × 1.0 × 0.5034 × 0.4153 × **0.5** | **0.1045** |
| **Coverage** | container orchestration + IaC (related) = 2 of 3 = 0.667 ≥ 0.6; critical skill satisfied | not excluded |
| **Fitness** | (0.2091 + 0 + 0.1045) / 3 = 0.104531; allocation 1.0 → multiplier 1.0 | **0.1045** |
| **Ranking** | 0.1045 > Sam 0.0384 > Riley 0.0000 | **rank 1** |
| **Display** | `RequestDetail.tsx` + `lib/format.ts`: `pct(0.1045)`, `fixed(0.1045)`, `matched_skill_count` | "10.4%", "0.1045", "evidence for 2 of 3 skills" |

*Read-across:* with Alex's volume (0.5034) and freshness (0.4153), even direct evidence on all three skills would cap the score at 0.2091. Alex reaches 0.1045, so half the ceiling is lost to the missing skill and the half-credit skill. The ceiling itself is low because of volume and freshness, not because of a low level (Alex is level 4 of 4 on the critical skill).

---

# Failure Scenarios

| What if… | What happens | Where | Status |
|---|---|---|---|
| a candidate has no evidence | excluded `no_evidence_on_any_required_skill`, listed under "Not a fit", cannot be chosen (422 `candidate_excluded`) | `rank_candidates:91`, `HermesService.decide` | **VERIFIED** |
| a candidate has only declared evidence | volume 0 → score 0.0000; still shortlisted if related-skill coverage ≥ 60% (Riley) | `_score_group:223`, E1 | **VERIFIED** |
| the skill is missing | contributes 0, stays in the denominator; excluded only if coverage < floor or a critical skill is unmatched | `_fitness:191` | **VERIFIED** |
| the skill is adjacent | half credit, labelled "Close" with its source skill; the critical check accepts it too | `_lookup_skill` | **VERIFIED** |
| evidence is old | decays by half-life; averaged with newer items (so it can drag a skill down); never deleted | `freshness_score` | **VERIFIED** |
| evidence sources disagree | level by weighted vote, lifted to the demonstrated mode within one level; confidence does not fall on disagreement (three types give 1.0 even if levels differ) | `_score_group:200-215` | **VERIFIED** (E13, E14) |
| the request has an invalid skill | 422 naming the ids; same for evidence (`UnknownSkillError`) | `_validate_levels`, `merge_evidence` | **VERIFIED** |
| a candidate is below coverage | excluded `below_min_coverage`; a client can raise the role's floor but never lower it | `rank_candidates:94`; `test_client_cannot_loosen_role_coverage_floor` | **VERIFIED** |
| two managers access the same request | the first owns it; the second gets 403 on rank, resolve, decide, and view. Request ids are generated to the second (`req-YYYYMMDDHHMMSS`), so two managers submitting in the same second would collide and the second is refused | `save_staffing_request` conditional SQL | ownership **VERIFIED**; collision **INFERRED** |
| a non-owner decides | 403 `request_not_owned`; no audit event and no state change | `HermesService.decide` | **VERIFIED** |
| the identity service is unavailable | there is no separate identity service: the coded map and vault live in the same database, so a database outage stops everything (503/500). With no identity provider configured outside local mode, every request is refused | `db.py`, `build_principal` | **INFERRED**; V7 for the auth part |
| the database is tampered with | ledger edits and deletions are detected (`/ready` 503, Overview flag); a missing trust record gives 503. **Edits to the data tables (for example `skills_matrix`) are not detected**, because only the audit ledger is chained | `verify_audit_chain`, `assess_database_trust` | ledger **VERIFIED**; table gap **INFERRED** |
| the scoring configuration changes | the version hash changes; the matrix must be recomputed by hand; ranking does not compare a stored record's version with the current config, so old and new rows can mix until then | `service.rank` | **INFERRED** |
| the API is unavailable | the UI shows an error state with Retry; no offline mode; a 401 signs the user out | `web/src/ui/States.tsx`, `http.ts` | **INFERRED**; V9 partial |
| there is no real data | the demo runs on synthetic data; the real-data screens show counts with scored = 0 and "Identity protected" | `read_models.data_quality` | **VERIFIED** (V6, `test_real_mode_fixture_reports_no_fake_scoring`) |
| the workbook has a skill Hermes doesn't know | the label becomes `pending`, never a `skill_id`; it appears in `/api/taxonomy/pending`; an admin approves or rejects it | `SkillAliasResolver`, `resolve_taxonomy_alias` | **VERIFIED** (tests; V6: 673 pending) |

---

# Claims vs Evidence

| CLAIM | EVIDENCE | VERIFIED? | LIMITATION |
|---|---|---|---|
| "Scoring is deterministic." | Two demo runs produce identical transcripts (`demo_svp --verify`, `test_two_runs_produce_identical_transcripts`); engine run twice gave identical output (E12) | **Yes**, for a fixed `as_of`, config and evidence | The live clock is "now", so numbers drift over days (0.1196 → 0.0619 over four months). `computation_run_id` is a random UUID |
| "Scores are explainable." | Every operand and the formula ship in the payload; `test_score_is_recomputable_from_payload_alone`; I reproduced Alex by hand | **Yes** | Explains the arithmetic, not whether the level heuristic is right. "Confidence" is described as agreement but is a count of evidence types |
| "Identities are protected." | Coded tokens, PII gate, resolve gateway, trust policy, fail-closed secrets, all tested | **Partly** | The reverse map (names and raw keys) is plaintext in the same database; no encryption at rest; the synthetic directory returns every name to any manager or admin; the real database file is mode 0644 |
| "Managers remain in control." | Only the owner decides; decisions validated; decisions never read back | **Yes** | A manager can rank and select themself (the demo manager is Alex, the top candidate); status labels are not reconciled with rank; the choice must be on the shortlist |
| "Historical ratings don't influence scoring." | `test_merge_rank_gaps_identical_with_baseline_populated_or_empty`; static import check; demo safeguard | **Yes** | The static check is a text search; isolation is enforced per module |
| "Real data is safely ingested." | Strong-secret rule, test-mode refusal, trust policy, aggregate-only report (V6); tests | **Partly** | The real database's vault holds names at rest (mode 0644); stale name-bearing files from earlier runs still exist under `data/phase8/` and `data/reports/` (gitignored; contents not opened) |
| "Audit is tamper-evident." | Hash chain plus signed anchor; ten audit-anchor tests in `test_v2_integrity.py`; my tamper test for `/ready` | **Yes** | Not WORM; anchor co-located and signed by the app's own secret by default; verified on demand; only the ledger is protected, not the data tables |
| "Frontend doesn't calculate scores." | Source-wide search; `format.ts`; contract and render tests | **Yes** | It rounds for display (1 decimal percent, 4 decimal raw) |
| "Configuration is versioned." | Hash of constants, taxonomy and effective half-lives; iff test over 11 parameters; pinned value | **Yes**, for env constants and the taxonomy | Constants inside the inference code (0.35 and +0.2 confidence steps, keyword lists, level tiers, volume shape, certificate level 3) are not in the hash; ranking does not check versions |
| "Recommendations are reproducible." | Same as determinism; the payload carries config version and run id | **Partly** | Reproducible only with a pinned date; ties break on an arbitrary but stable token order |

---

# 30-Second Explanation

"Hermes helps a manager answer 'who should do this work?' from evidence instead of memory. It reads work tickets, dated certificates and manager-confirmed skills, ranks people against a role, and shows exactly why, including who was left out and why. The rules are fixed and visible, no AI model decides, and the manager makes the final call. Today it runs on invented people; the real workbook is loaded but nobody real is scored until humans approve the skill mappings."

# 60-Second Explanation

"Staffing today runs on memory and a yearly spreadsheet that goes stale. Hermes builds a living skills picture from what people have actually done: tickets, certificates with dates, and skills a manager has personally confirmed. A manager picks a role and gets a ranked shortlist. Each score breaks into five visible factors: how strong the skill is, how many kinds of evidence back it, how much work there is, how recent it is, and whether the skill is direct or only related. It also lists who was excluded and why. The same evidence always gives the same answer, every number can be traced to a ticket or certificate, and no model is involved. The manager chooses, and the choice is logged but never changes future scores. What it does not yet do: score real employees, because the 673 labels in the 2025 workbook still need human approval; connect to live systems; or sign users in through the company identity provider."

# 3-Minute Explanation

"The problem is simple. Managers staff from memory. Expertise outside their network is invisible, and the annual skills survey is stale as soon as it is collected. The real 2025 workbook shows it: 310 people, 673 differently worded skill labels, rating scales nobody defined.

Hermes turns three kinds of evidence into a skills matrix. Work tickets show demonstrated skill. Dated certificates show formal skill. Skills a manager confirms are the weakest evidence. Each skill record carries a level, a confidence, a volume, and a freshness. Confidence is how many different kinds of evidence support it. Volume is how much demonstrated work there is, with diminishing returns. Freshness fades with a half-life, 120 days for container skills.

A manager describes a role and clicks Find people. For every required skill Hermes multiplies level ratio, confidence, volume, freshness and a relatedness factor, averages across the skills, and applies a small availability factor. A missing skill counts as zero but stays in the average. Someone is excluded only if they have no relevant evidence, cover under 60% of the skills, or lack a critical one, and the reason is shown.

Identities are coded from the start. Names appear only for shortlisted people on a manager's own request, or in the demo through a directory. Every access is checked on the server, and every write goes into a hash-chained, anchored audit log. The manager decides; the decision is recorded and never fed back into scoring.

What is proven: the mechanism, access control, repeatability, and refusal of unsafe input: 389 backend tests, 83 frontend tests, and a 55-point live check. What is not: that rankings match real judgement, because no real employee is scored yet; there is no company sign-in; no live integrations; and it has not been load-tested. The next step is human approval of the workbook mappings, then a comparison against the 2025 ratings."

# 10-Minute Technical Explanation

**Shape.** A React 18 single-page app (Vite build) is served by a FastAPI process (`api/main.py`), which delegates to `HermesService` (`src/shared/service.py`), the composition root that wires four judgement components to one SQLite file through `HermesDB` (`src/shared/db.py`). The four components are the identity abstraction gate, the skill inference engine, the fitness/gap engine, and the identity resolution gateway. An `AuditLedger` records every state-changing event.

**Identity.** Every person enters through `IdentityAbstractionGate`: PII and protected attributes are stripped or rejected, and the employee key becomes `EMP-` + 8 hex from an HMAC with a secret. Names live in `identity_vault`. The database carries trust metadata (classification and a secret fingerprint); `ensure_database_trusted` refuses to serve a database whose identities could be reversed (published secret, test mode with real data, missing metadata). Secrets fail closed at startup.

**Evidence to skill record.** Tickets are matched to skills by taxonomy keywords (plain substring matching) and given a level by depth/surface word rules. Certificates and manager-confirmed declarations arrive as evidence records. `_score_group` groups by person and skill and produces: a level (type-weighted vote 0.55/0.30/0.15, lifted to the demonstrated mode within one level), confidence (0.35 per distinct evidence type, +0.2 for demonstrated+certified, capped at 1), volume (1 − e^(−0.35n) over demonstrated records), and freshness (mean of 0.5^(age/half-life)). Every write recomputes the whole matrix at "now" and keeps history.

**Ranking.** `FitnessGapEngine` reads stored skill records. Per required skill: level ratio (capped at 1) × confidence × volume × freshness × adjacency (1.0 direct, 0.5 related). Mean over required skills (missing = 0, still counted), times `0.85 + 0.15 × allocation`. Exclusions: no evidence, coverage below 0.6, or a critical skill unmatched (adjacent counts). Order by score then token; cap 10. The full result is saved and replayed verbatim.

**Governance.** The API derives roles and coded identity server-side from a `sub`-only token; forged claims are rejected. Requests are owner-only, enforced in the service and in conditional SQL. Managers can decide only among the shortlist. Decisions are audit-only. The audit ledger is a SHA-256 chain with a signed external anchor; verification catches edits, tail deletion and rewrites, but it is not WORM and protects only the ledger.

**Phase 8.** The 2025 workbook is parsed into isolated tables with a closed vocabulary of rejection reasons; soft skills and culture fit are stripped; client labels go to `account_context`; every label stays `pending` until a human maps it. Today: 310 people, 12,852 accepted cells, 673 labels, 0 mapped, 427 certificates, 0 dated, 0 scored.

**Versioning and tests.** A 12-character hash of constants, taxonomy fingerprint and effective half-lives stamps every record; tests assert it changes exactly when scores can change, but constants inside the inference code are outside it. The suite: 389 backend and 83 frontend tests, a 55-check live smoke, and a determinism check. Coverage (92%) covers six `src/` packages, not the API layer.

**Honest limits.** Level inference is keyword heuristics with a known false-positive class. Negative evidence is not wired in. Availability, demand and allocation are fixtures. No real sign-in, no encryption at rest, single-writer database, no integrations, no load test.

---

# Appendix A: Reproduce the Alex trace

Save as any file inside the repo root (for example `/tmp/trace.py`), then run `source .venv/bin/activate && PYTHONPATH=src:. python /tmp/trace.py`. Expected output: `0.1045 0.104531`. **[VERIFIED]**

```python
import os, sys
os.environ["HERMES_TEST_MODE"] = "1"
sys.path[:0] = ["src", "."]
from datetime import datetime
from skill_inference.engine import SkillInferenceEngine
from fitness_gap.engine import FitnessGapEngine
from shared.taxonomy import load_taxonomy
from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel, StaffingRequest

eng, tax = SkillInferenceEngine(), load_taxonomy()
adj = {s.skill_id: list(dict.fromkeys(list(s.related_skills or []) + list(s.relations or [])))
       for s in tax.all_skills() if (s.related_skills or s.relations)}
fit = FitnessGapEngine(config=eng.config, adjacency=adj)
D = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
A = "EMP-ALEX0001"
ev = []
for tid, text, when in (("INC001", "Kubernetes migration rollback for prod cluster", "2026-07-01T12:00:00Z"),
                        ("INC002", "Helm chart upgrade on k8s worker pool", "2026-07-15T12:00:00Z")):
    ev += eng.infer_from_ticket(A, text, D(when), tid, tid)
ev.append(EvidenceRecord(evidence_id="cert-CKA", coded_identity=A, skill_id="container_orchestration",
    evidence_type=EvidenceType.CERTIFIED, proficiency=ProficiencyLevel(4),
    occurred_at=D("2025-11-01T00:00:00Z"), source_ref="CKA"))
ev.append(EvidenceRecord(evidence_id="decl", coded_identity=A, skill_id="container_orchestration",
    evidence_type=EvidenceType.DECLARED, proficiency=ProficiencyLevel(3),
    occurred_at=D("2026-01-15T00:00:00Z"), source_ref="declared", metadata={"manager_confirmed": True}))
m = eng.merge_evidence(ev, as_of=D("2026-09-24T06:05:00Z"))
req = StaffingRequest(request_id="R", requester_id="m",
    required_skills={"container_orchestration": 4, "azure_networking": 4, "infrastructure_as_code": 3})
r = fit.rank_candidates(req, m, critical_skills=["container_orchestration"])
c = r.candidates[0]
print(c.fitness_score, c.calculation.mean_contribution)
```

Change `as_of` to see the calendar drift (`2026-09-01` gives 0.1196, the pinned demo value).

---

# Before the SVP Meeting

## 1. What you should know cold

1. **The formula**, in one breath: level ratio (capped) × confidence × volume × freshness × relatedness, averaged over *required* skills (missing = 0), × a 0.85–1.0 availability factor.
2. **Alex's number and why it is small:** 0.1045 = (0.209 + 0 + 0.105) / 3. Two tickets (volume 0.50), stale certificate dragging freshness to 0.42, one missing skill, one half-credit skill.
3. **Confidence is the number of evidence *types*, not agreement.** Volume counts demonstrated evidence only. Therefore a certificate alone scores 0, and a declared skill alone scores 0 (Riley).
4. **Weights 0.55/0.30/0.15 vote on the *level* only.**
5. **Determinism is true with a pinned date.** In the live app the same evidence loses score as it ages (0.1196 → 0.1047 in three weeks).
6. **The honest headline:** the mechanism is proven; accuracy is not, because 0 of 673 real labels are mapped and 0 real people are scored.
7. **The decision rules:** owner-only, shortlist-only, audit-only, never fed back. The demo manager is Alex, the top candidate, and nothing prevents self-selection.
8. **What is not built:** real sign-in, integrations, negative evidence, live availability/demand, encryption at rest, scale testing.
9. **Audit is tamper-evident, not WORM,** and protects the ledger, not the data tables.
10. **Numbers to quote:** 389 backend tests, 83 frontend tests, 55 live checks, coverage 92% (six `src/` packages), 49 governed skills, 310 people, 673 labels, 427 certificates, 0 dated, 0 scored.

## 2. The 10 questions most likely to expose weak understanding

1. "Why is your best candidate only 10%?" (Q8: factors below one, a zero in the mean, drift with time.)
2. "Sam covers all three skills and ranks below Alex who covers two. Why?" (Related skills at half credit, thin evidence.)
3. "You said confidence is agreement between sources. Does it check that they agree?" (No: it counts types.)
4. "Does a certificate raise someone's score?" (Not alone; only with tickets.)
5. "Why does Riley, who scores zero, appear on a recommendation list?" (Coverage via a related skill; a real design question.)
6. "If I run this next month, will the numbers change?" (Yes, freshness decays.)
7. "Can a manager pick themselves?" (Yes; Alex is the demo manager and the top candidate.)
8. "What stops someone adding a skill to game it?" (Manager-only, weight 0.15, no volume alone; but four repeats can set the level.)
9. "Where do the demand numbers in the learning view come from?" (Static fixture values.)
10. "How do you know the levels from tickets are right?" (You don't yet: keyword rules, unmeasured on real text, with a known `ad`-in-"upgrade" false positive.)

## 3. The 10 technical questions a CTO could use to challenge the architecture

1. "Your config version claims to change iff scores change. Show me a score change that leaves it unchanged." (Edit the 0.35 in `_score_group`.)
2. "Your identity is pseudonymous. Where is the reverse map and who can read the file?" (Same SQLite file, plaintext, real DB is mode 0644.)
3. "What is tamper-evident about your audit if the anchor is next to the database and signed with the app's own secret?" (Not WORM; set `HERMES_AUDIT_ANCHOR_DIR`.)
4. "You chain the audit ledger. Who protects `skills_matrix`?" (Nobody; an edit there is not detected.)
5. "What is your authentication?" (Five passwordless demo principals; production mode has none.)
6. "Every evidence write recomputes the whole matrix at 'now'. What happens at 100× the data or 1,000 users?" (Untested; single writer, full recompute, unpaginated reads.)
7. "Your 92% coverage: what is it measuring?" (Six `src/` packages; not `api/main.py`, scripts, or the frontend.)
8. "What test would fail if I changed the volume constant inside the inference code?" (None with an exact value; only sensitivity tests.)
9. "Two concurrent managers, the same request id?" (Client ids are to-the-second; ownership refuses the second.)
10. "Negative evidence is in your spec. Where does it run?" (It doesn't: `_negative_penalty` is never given metadata.)

## 4. The 10 questions a manager or end user could ask

1. "Why isn't my report Jordan on the list?" (Under 60% coverage; only Azure networking evidence.)
2. "Can I see people who don't report to me?" (Yes, today: team skills and rankings are population-wide.)
3. "Can I remove a wrong skill?" (No; you can only add a confirmed one.)
4. "What does 'Close' mean?" (A related skill at half credit.)
5. "Why does the learning view show Infrastructure as Code as missing when Who fits said Close?" (Gaps count direct evidence only.)
6. "Can I change availability or workload?" (Not in the screen; the factor is always 1.0 today.)
7. "Is my employee's data on the screen real?" (No, invented; the sidebar says so.)
8. "What happens if I pick the third person?" (Recorded as accepted or overridden with rank 3; audited.)
9. "How often does it update?" (When evidence is written; freshness does not update on its own.)
10. "Who else can see my decision?" (It is stored under your login; only you can view your requests.)

## 5. Statements in the current demo material that are technically inaccurate

**Voiceover (`docs/ELEVENLABS_VOICEOVER.md`)**

| Where | Says | Reality |
|---|---|---|
| On-screen facts, Tracks 05, 10 | Alex "meets 2 of 3"; Sam "meets 3 of 3" | The UI now says "evidence for N of M". "Meets" overstates it: Alex directly has 1 of 3 (container orchestration); infrastructure as code is related, Azure networking is missing |
| Track 05 and elsewhere | "He meets…", "He declared a skill" | The data has no gender field, and Hermes states it uses no protected attributes. Use the person's name or "they" |
| Track 07 | "Confidence — do independent sources agree" | It counts distinct evidence *types*; it never compares their levels |
| Track 07 | "The config version… If those constants change, the version changes. If they do not, the version does not." | True for env constants and the taxonomy; false for constants written into the inference code |
| Track 07 | "You can reproduce this number without reading our source code." | True for the final fitness from the payload; the payload's own confidence, volume and freshness need the rules in the spec |
| Track 08 | "Rows are the five governed skills." | The Team skills page lists all 49 governed skills |
| Track 08 | "Client familiarity, tenure, culture fit — not inputs. They are not even fields." | Not inputs to scoring: correct. But client familiarity **is** stored (`account_context.familiarity_raw`), isolated from scoring. There is no tenure field |
| Track 09 | "…in order of organisational demand, not gap size." | The order is `demand weight × deficit`, so gap size matters; demand weights are static fixture values (`shared/demand.py` is an unused stub) |
| Track 09 | "Azure networking — the missing skill that actually blocked coverage." | Nothing was blocked: coverage was 2 of 3, above the 60% floor. The missing skill lowered the average |
| On-screen facts | Alex "~11%" | About 10.4–10.5% today; 11.96% only at the pinned demo date of 1 Sep. It drifts down over time |

**Other documents**

| Where | Says | Reality |
|---|---|---|
| `docs/SVP_DEMO_GUIDE.md` step 4 and steps 12–13 | "cross-type agreement"; gaps ordered "not gap size" | Same two points as above |
| `docs/SVP_DEMO_GUIDE.md` section 4 (UI path) | Click **Staff**, use the history scrubber | Those pages no longer exist in the current UI |
| `docs/SVP_DEMO_GUIDE.md` sections 6–7 | 12,496 baseline rows, 752 labels, 12,697 labels, "ontology has 5 governed skills" | Current verified figures: 12,852 accepted cells, 673 labels, 49 governed skills. The guide also contradicts itself (12,496 vs 12,697) |
| `docs/SVP_DEMO_GUIDE.md` step 9 | "Names appear **only here**" (the resolution step) | True in the CLI demo; in the UI on synthetic data, names appear on every screen through the directory |
| `docs/SCORING_SPECIFICATION.md` §2 | Reopen/escalation lowers the level | Never wired: the function exists but the ticket path never passes metadata |
| `PROJECT_BIBLE.md` Guardrail 3 | "names only for shortlisted candidates" | Holds for real data; on synthetic data any manager or admin can read the whole directory |
| `src/shared/config.py` docstring | "enforced by `tests/unit/test_config_fidelity.py`" | That file does not exist; the test is `test_v2_integrity.py::test_version_changes_if_and_only_if_scores_change` |
| `docs/DEMO_RUNBOOK.md` (written earlier in this engagement) | "Managers see their own team and requests" | Managers see the whole population's skills and rankings; only edits and per-person gap views are limited to direct reports, and requests are owner-only |
| `docs/DEMO_RUNBOOK.md` | "Self-declared skills carry the least weight… leaves the score at 0" | The declared weight (0.15) affects only the level vote. The score is 0 because *volume* counts demonstrated evidence only, which is also why a certificate alone scores 0 |
| `docs/DEMO_RUNBOOK.md` step 5 | "…related to what he has done" | Pronoun not in the data; use "they" |

## Addendum — 2026-10-02 (real-data governance additions)

Everything above is the pinned 2026-09-24 snapshot; it is left as-is rather than silently
rewritten, since its own basis line ties each number to a review done on that date. This
addendum documents what changed on top of it, verified the same way (commands actually run,
not assumed).

**What was added**, all additive — no existing endpoint, schema, or test was changed or removed:

- `src/shared/read_models._activation_status()` — derives `NOT_READY` / `INGESTED` /
  `GOVERNANCE_PENDING` / `PARTIALLY_ACTIVE` / `ACTIVE` from stored counts alone (`skills_matrix`
  row count is the hard gate; `scored_people == 0` can never report `ACTIVE`). `VALIDATED` is
  reserved and intentionally never auto-derived. Surfaced as `data_quality().activation_status`,
  i.e. the existing `GET /api/data-quality` route — no new route needed.
- `src/shared/read_models.cert_governance_queue()` + `GET /api/certs/pending` — a read-only,
  ADMIN-only triage view of every un-promoted certificate, classified `needs_date` /
  `needs_mapping` / `needs_date_and_mapping` / `ready_to_promote`. Backs the cert-governance
  admin workflow; performs no fuzzy matching or auto-approval itself.
- `src/identity_abstraction/gate.scan_real_database_for_leakage()` +
  `scripts/audit_real_db_leakage.py` — extends the identity-leakage audit (previously synthetic-
  fixture-only, see `tests/audits/test_leakage_audit.py`) to the actual real database:
  `skills_matrix`, `evidence_staging`, and every `audit_ledger` payload, with the name blocklist
  pulled live from `identity_vault` (never a committed file). Intended as a pre-demo safety gate.

**Verified 2026-10-02**, run directly, not assumed:

| # | What | Result |
|---|---|---|
| V-10-02-a | `python -m pytest --no-cov` (full backend suite, after the additions) | **400 passed** (was 389) |
| V-10-02-b | Same run, with coverage | coverage **92.36%** (was 92.28% — improved, not lowered; gate 85%) |
| V-10-02-c | `npx vitest run` (web/) | **83 passed**, unchanged |
| V-10-02-d | `python scripts/audit_real_db_leakage.py` against `data/real/hermes_real.db` | `{"status": "pass", "finding_count": 0}` |
| V-10-02-e | `cert_governance_queue()` against `data/real/hermes_real.db` | `{"needs_date": 427, "needs_mapping": 422, "ready_to_promote": 0, "promoted": 0}` |
| V-10-02-f | `data_quality().activation_status` against `data/real/hermes_real.db` | `{"state": "GOVERNANCE_PENDING", "scored_people": 0}` |

**No data was fabricated.** `skills_matrix` is still 0 rows for the real database; this addendum
adds visibility and an admin triage queue, not a score. The real-data blocker and its exact fix
path are unchanged from the 2026-09-24 snapshot above — see the Data section and
`docs/phase8/BLOCKED.md`.
