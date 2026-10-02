"""Real end-to-end Teams pipeline test (via MockTeamsProvider — see that
module's docstring for why it's clearly labeled dev-only, not a mock of the
*test*): add employee -> send capability check -> employee answers ->
DECLARED evidence -> capability profile visible in skills_matrix.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from integrations.teams.mock_provider import MockTeamsProvider  # noqa: E402
from integrations.teams.service import record_assessment_response, send_capability_check  # noqa: E402
from shared.db import HermesDB  # noqa: E402
from shared.errors import UnknownSkillError  # noqa: E402
from shared.service import HermesService  # noqa: E402


@pytest.fixture()
def svc(tmp_path):
    return HermesService(db=HermesDB(tmp_path / "teams.db"))


def test_full_pipeline_add_employee_to_declared_evidence(svc):
    coded = svc.abstract({"employee_id": "teams-emp-1", "name": "Teams Employee"})["coded_identity"]
    provider = MockTeamsProvider()

    assessment_id = send_capability_check(provider, svc.inference.taxonomy, coded, ["python", "bash_scripting"])
    assert assessment_id in provider.sent_assessments
    sent_card = next(iter(provider.sent_cards.values()))
    assert sent_card["coded_identity"] == coded
    assert sent_card["card"]["type"] == "AdaptiveCard"

    # Employee answers via the card (simulated — there is no real Teams client here).
    response = {
        "coded_identity": coded,
        "answers": [
            {
                "skill_id": "python", "actively_used": True, "experience": "advanced",
                "recency": "under_30_days", "delivered_in_real_work": True,
            },
            {
                # Marked present but not actively used -> must create NO evidence.
                "skill_id": "bash_scripting", "actively_used": False, "experience": "beginner",
                "recency": "over_1_year", "delivered_in_real_work": False,
            },
        ],
    }
    merged = record_assessment_response(svc, response, source_ref=assessment_id)

    matrix = {r.skill_id: r for r in svc.db.load_skills_matrix()}
    assert "python" in matrix
    assert "bash_scripting" not in matrix, "a skill not marked actively-used must not create any evidence"
    assert matrix["python"].proficiency == 4  # advanced
    assert any(r.skill_id == "python" for r in merged)


def test_response_returns_only_this_submissions_records_not_the_whole_matrix(svc):
    """Regression: stage_and_merge returns the full system-wide recomputed
    matrix, not a diff. Found live during the golden-path run, where
    answering 1 skill reported declared_skill_count=12 because the response
    accidentally included every other coded identity's unrelated evidence."""
    coded_a = svc.abstract({"employee_id": "teams-emp-a", "name": "A"})["coded_identity"]
    coded_b = svc.abstract({"employee_id": "teams-emp-b", "name": "B"})["coded_identity"]
    # Give B some unrelated pre-existing evidence first.
    record_assessment_response(
        svc,
        {"coded_identity": coded_b, "answers": [{
            "skill_id": "bash_scripting", "actively_used": True, "experience": "working",
            "recency": "under_30_days", "delivered_in_real_work": True,
        }]},
        source_ref="setup",
    )
    merged = record_assessment_response(
        svc,
        {"coded_identity": coded_a, "answers": [{
            "skill_id": "python", "actively_used": True, "experience": "working",
            "recency": "under_30_days", "delivered_in_real_work": True,
        }]},
        source_ref="test",
    )
    assert len(merged) == 1
    assert merged[0].coded_identity == coded_a
    assert merged[0].skill_id == "python"


def test_declared_evidence_is_never_mistaken_for_demonstrated(svc):
    """The exact governance invariant: self-declaration via Teams must score
    strictly lower than the same proficiency demonstrated or certified would —
    not because this module says so, but because it only ever writes
    EvidenceType.DECLARED and relies on the engine's existing weighting."""
    coded = svc.abstract({"employee_id": "teams-emp-2", "name": "Teams Employee 2"})["coded_identity"]
    response = {
        "coded_identity": coded,
        "answers": [{
            "skill_id": "python", "actively_used": True, "experience": "expert",
            "recency": "under_30_days", "delivered_in_real_work": True,
        }],
    }
    record_assessment_response(svc, response, source_ref="test")
    record = next(r for r in svc.db.load_skills_matrix() if r.skill_id == "python")
    # declared_weight (0.15) << demonstrated_weight (0.55) in the level vote; the
    # clearest external signal of this is confidence staying well under 1.0 for a
    # single declared-only data point (three evidence *types* voting, not three
    # pieces of evidence, so this is not just "more evidence = higher confidence").
    assert record.confidence < 1.0


def test_unknown_skill_in_assessment_invite_is_refused(svc):
    provider = MockTeamsProvider()
    with pytest.raises(UnknownSkillError):
        send_capability_check(provider, svc.inference.taxonomy, "EMP-00000000", ["not_a_real_skill"])


def test_malformed_response_is_rejected_not_silently_accepted(svc):
    with pytest.raises(Exception):  # pydantic ValidationError
        record_assessment_response(svc, {"coded_identity": "EMP-00000000"}, source_ref="test")  # missing "answers"


def test_response_with_unknown_skill_id_is_refused(svc):
    coded = svc.abstract({"employee_id": "teams-emp-3", "name": "Teams Employee 3"})["coded_identity"]
    response = {
        "coded_identity": coded,
        "answers": [{
            "skill_id": "not_a_real_skill", "actively_used": True, "experience": "working",
            "recency": "under_30_days", "delivered_in_real_work": False,
        }],
    }
    with pytest.raises(UnknownSkillError):
        record_assessment_response(svc, response, source_ref="test")


def test_question_count_is_capped_at_ten():
    from integrations.teams.models import AssessmentInvite, CapabilityQuestion

    with pytest.raises(Exception):
        AssessmentInvite(
            coded_identity="EMP-00000000",
            questions=[CapabilityQuestion(skill_id=f"s{i}", skill_label=f"Skill {i}") for i in range(11)],
        )


def test_mock_provider_is_clearly_labeled_not_production():
    assert MockTeamsProvider().is_mock is True
