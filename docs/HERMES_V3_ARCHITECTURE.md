# Hermes V3 — LLM-Assist Architecture (2026-10-02)

**Status labels used below** (same convention as `docs/HERMES_ENGINEERING_QA.md`):
**BUILT** = exists, tested, verified in this session. **DESIGNED, NOT BUILT** = the
boundary/contract is specified here so a future implementation has a target, but
no code exists. Nothing in this document describes an unbuilt feature as if it
were working.

## Core principle (unchanged, now enforced in code)

**RULES COMPUTE. LLM ASSISTS. HUMANS DECIDE.**

Concretely: `src/fitness_gap/engine.py` (the deterministic scorer) has zero
knowledge of `src/ai/*` and is never imported by it. The only connection point
is a request body shape — a `Dict[str, int]` of `skill_id -> level` — that can
be typed by hand or proposed by the LLM; the engine cannot tell which. This is
proven, not asserted: `tests/unit/test_llm_does_not_affect_scoring_determinism.py`
builds that dict both ways and shows the ranked output is byte-identical.

## What's BUILT in this slice

### LLM provider boundary (`src/ai/`)

```
src/ai/
    provider.py            LLMProvider protocol + LLMUnavailableError
    ollama_provider.py      OllamaProvider — real local Ollama, httpx-based
    mock_provider.py        MockLLMProvider — deterministic, no network, used by all core tests
    schemas.py               WorkRequirementProposal / SkillProposal (Pydantic)
    services/
        work_requirement.py  extract_work_requirement() — the one implemented LLM task
```

`LLMProvider` has one method, `generate(prompt, system=None) -> str`. Everything
else — JSON parsing, schema validation, skill-name governance — lives one layer
up in `services/`, never in a provider. This is what lets Ollama be swapped for
an Azure-hosted model later (Phase 25 of the brief) without touching a single
calling site.

Configuration: `OLLAMA_BASE_URL` (default `http://localhost:11434`),
`OLLAMA_MODEL` (**no hardcoded fallback** — fails closed with a
`ConfigurationError` if unset, matching this codebase's existing secrets
policy in `shared/secrets.py`). Verified live in this environment against
`qwen2.5:7b-instruct`, ~6.3s per call.

### Natural-language work-request parsing

`POST /api/requests/parse` (MANAGER-only, `api/routers/assist.py`). Takes
`{"description": "..."}`, returns:

```json
{
  "available": true,
  "proposal": {
    "skills": [{"skill": "Python", "importance": "required", "mapped_skill_id": "python"}],
    "ambiguities": ["API Integration"]
  },
  "reason": null
}
```

Governance, enforced by `src/ai/services/work_requirement.py`, verified by
`tests/unit/test_work_requirement_extraction.py`:

- A skill label is mapped to a `skill_id` only on an **exact** normalized
  match against the governed taxonomy (reusing
  `src/phase8/aliases.ontology_lookup_map` — the same resolver the real-data
  ingestion pipeline uses; no new matching logic was invented).
- Anything that doesn't match exactly lands in `ambiguities`, never in
  `skills` — the LLM cannot create a taxonomy entry, mapped or not.
- Malformed/unparseable model output raises `LLMExtractionError`, caught at
  the API layer and turned into `{"available": false, "reason": "..."}` —
  never a 500, never silently-wrong data.
- If Ollama is unreachable or misconfigured, same clean `available: false`
  response (Phase 16's "AI assistance unavailable, continue manually").
- The proposal is never submitted to ranking automatically. A manager must
  still send the confirmed `required_skills` dict to the existing, completely
  unmodified `POST /api/fitness/rank`.

### Testing

`MockLLMProvider` backs every test above — core CI has zero dependency on a
running Ollama. One self-skipping live test
(`tests/integration/test_ollama_live.py`) actually exercises the real model
when `OLLAMA_MODEL` is set and Ollama is reachable; it was run successfully
during this work (see commit history) and skips cleanly otherwise.

## What's DESIGNED, NOT BUILT

Everything below is explicitly out of scope for this slice. Describing it here
is a target contract for future work, not a claim that it exists.

- **Microsoft Teams integration** (`integrations/teams/` — client, cards,
  service, mock adapter). No code written. Requires real Teams/Bot Framework
  credentials to build and test meaningfully; a mock-only implementation
  without the real send/receive contract would be closer to theater than to
  the "production-compatible interface, clearly labeled mock mode" the brief
  asks for.
- **Employee capability survey / Teams Adaptive Cards workflow**. Depends on
  the above.
- **DECLARED → DEMONSTRATED → CERTIFIED → VERIFIED evidence-strength model**.
  Today's evidence model already has `demonstrated` / `certified` / `declared`
  evidence *types* (`shared/models.py`); a four-stage *strength* progression
  on top of that is a real data-model and scoring-weight decision, not
  something to bolt on inside an LLM-assist session.
- **Learning-loop recommendations, continuous profile-nudge cadence,
  frontend UX redesign (manager/employee screens, command palette, motion),
  PostgreSQL migration, Azure Container Apps deployment, Docker compose for
  Ollama+API+web.** None attempted. Each is independently a multi-day-or-more
  effort; attempting all of them in this pass would mean shipping each one
  half-verified, which is the opposite of this codebase's existing discipline
  (see `docs/HERMES_ENGINEERING_QA.md`'s own verification culture).

## Security (preserved, not re-litigated)

Nothing about HMAC coded identity, owner-scoped identity resolution,
role-based access, fail-closed secrets, database trust checks, audit logging,
or leakage detection was touched. The one new endpoint:

- Is MANAGER-role-gated like `/api/fitness/rank`.
- Never writes evidence, never touches `skills_matrix`, `audit_ledger`, or
  any identity table.
- Sends only the manager's free-text description to the LLM — no employee
  PII, no coded identities, no evidence.
- Logs nothing beyond what FastAPI's existing request handling already does;
  no raw prompt/response logging was added (observability — Phase 30 — is
  explicitly deferred, not silently done partially).

## Real-data governance (unchanged)

`skills_matrix = 0`, activation state `GOVERNANCE_PENDING`, 427 certificates
awaiting dates, 422 labels awaiting mapping — none of this session's work
touches that state. The LLM-assist feature operates entirely on a manager's
*request description*, never on a candidate's evidence, so it has no path to
affect real-data activation in either direction.

## Production evolution (separated per the brief's NOW/NEXT/LATER)

**NOW (this slice)**: local Ollama, manager-only NL work-request parsing,
mock-backed CI, one live-Ollama smoke test.

**NEXT**: real Teams integration; evidence-strength model decision; frontend
to actually surface `/api/requests/parse` in the "+ FIND SOMEONE" flow
(today it's a backend-only, TestClient-verified endpoint with no UI
consumer); PostgreSQL; enterprise LLM endpoint behind the same
`LLMProvider` interface.

**LATER**: HA/DR, load testing, full UX redesign, learning ecosystem.
