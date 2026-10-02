"""Phase 31 critical regression test — explicitly required by the V3 directive:

'Same evidence + same config + same as_of must produce exactly the same
deterministic ranking regardless of LLM output.'

Proof strategy: build the required_skills dict two ways — once "manually" (as
a manager typing skill ids directly) and once via the LLM-assist proposal
(mapped_skill_id values from a mocked LLM response) — and show the two paths
produce byte-identical FitnessGapEngine output. The engine has no code path
that can even see where a dict came from; this test pins that down explicitly
rather than leaving it implicit.
"""

from __future__ import annotations

import os

os.environ.setdefault("HERMES_TEST_MODE", "1")

from ai.mock_provider import MockLLMProvider  # noqa: E402
from ai.services.work_requirement import extract_work_requirement  # noqa: E402
from fitness_gap.engine import FitnessGapEngine  # noqa: E402
from shared.models import ProficiencyLevel, SkillRecord, StaffingRequest  # noqa: E402

#: Presentation-only wall-clock stamps, not score inputs — same convention as
#: tests/api/test_ui_contract.py's VOLATILE_KEYS. Two sequential engine calls
#: with identical scoring inputs legitimately get different "now" stamps;
#: that is not the determinism property this test is pinning down.
VOLATILE_KEYS = {"computed_at", "created_at", "decided_at", "occurred_at", "valid_from"}


def _strip_volatile(value):
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def _matrix():
    return [
        SkillRecord(
            coded_identity="EMP-aaaa0001",
            skill_id="python",
            proficiency=ProficiencyLevel(4),
            confidence=0.9,
            freshness=0.8,
            volume_score=0.7,
            evidence_ids=["e1"],
            scoring_config_version="v1",
        ),
    ]


def test_llm_sourced_and_manually_typed_requests_rank_identically():
    # Manual path: manager types the skill id directly.
    manual_required = {"python": 3}

    # LLM-assist path: the same skill, proposed in natural language.
    provider = MockLLMProvider(
        fixed_response='{"skills": [{"skill": "Python", "importance": "required"}]}'
    )
    proposal = extract_work_requirement(provider, "need a python person")
    llm_required = {s.mapped_skill_id: 3 for s in proposal.skills}

    assert llm_required == manual_required, "LLM path produced a different skill dict than manual entry"

    engine = FitnessGapEngine()
    matrix = _matrix()

    def _rank(required):
        request = StaffingRequest(
            request_id="req-determinism-check",
            requester_id="demo-manager",
            required_skills={k: ProficiencyLevel(v) for k, v in required.items()},
            shortlist_size=1,
        )
        return engine.rank_candidates(request, matrix, computation_run_id="fixed-run").model_dump(mode="json")

    manual_result = _strip_volatile(_rank(manual_required))
    llm_result = _strip_volatile(_rank(llm_required))

    assert manual_result == llm_result, "ranking differed depending on whether the request came from the LLM"
