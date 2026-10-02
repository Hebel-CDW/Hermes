"""The real send -> answer -> DECLARED-evidence pipeline. Provider-agnostic:
works identically with MockTeamsProvider or (once built) MicrosoftTeamsProvider
— both implement the same TeamsProvider protocol.

Governance (Phase: "Do NOT treat self-declaration as demonstrated capability"):
every record this module creates is EvidenceType.DECLARED. It never calls
anything that writes CERTIFIED or DEMONSTRATED evidence. The scoring engine's
existing weighting (demonstrated 0.55 / certified 0.30 / declared 0.15,
shared/config.py) already treats declared evidence as the weakest signal —
this module relies on that existing policy rather than re-implementing it.
A skill the employee did not mark "actively used" gets no evidence record at
all, rather than a zero-confidence one cluttering the profile.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping

from integrations.teams.models import AssessmentInvite, AssessmentResponse, CapabilityQuestion
from integrations.teams.provider import TeamsProvider
from shared.models import DeclaredEvidence, EvidenceType, ProficiencyLevel
from shared.service import HermesService
from shared.taxonomy import SkillsTaxonomy

_EXPERIENCE_TO_LEVEL: Mapping[str, ProficiencyLevel] = {
    "beginner": ProficiencyLevel.AWARENESS,
    "working": ProficiencyLevel.WORKING,
    "advanced": ProficiencyLevel.ADVANCED,
    "expert": ProficiencyLevel.EXPERT,
}

#: Teams gives a recency bucket, not an exact date. These are documented
#: midpoint approximations for the freshness-decay input, not invented precision.
_RECENCY_TO_DAYS_AGO: Mapping[str, int] = {
    "under_30_days": 15,
    "1_to_6_months": 90,
    "6_to_12_months": 270,
    "over_1_year": 400,
}


def send_capability_check(
    provider: TeamsProvider,
    taxonomy: SkillsTaxonomy,
    coded_identity: str,
    skill_ids: List[str],
) -> str:
    """Build and send a capability-check assessment for a handful of governed
    skills. Raises UnknownSkillError if any skill_id isn't governed — the same
    rule the rest of the app enforces, not a Teams-specific exception."""
    from shared.errors import UnknownSkillError

    questions: List[CapabilityQuestion] = []
    for skill_id in skill_ids:
        skill = taxonomy.skill_by_id(skill_id)
        if skill is None:
            raise UnknownSkillError(f"unknown skill id: {skill_id}")
        questions.append(CapabilityQuestion(skill_id=skill_id, skill_label=skill.name))
    invite = AssessmentInvite(coded_identity=coded_identity, questions=questions)
    return provider.send_assessment(invite)


def record_assessment_response(
    svc: HermesService,
    raw_response: Dict[str, Any],
    source_ref: str,
) -> List[DeclaredEvidence]:
    """Validate ``raw_response`` (whatever the webhook/mock handed back) against
    AssessmentResponse, convert each actively-used answer into DeclaredEvidence,
    and stage it exactly the way every other evidence path in this app does
    (HermesService.stage_and_merge — unknown skill_ids raise UnknownSkillError
    there too, so this module does not special-case that check twice).

    Returns the merged skill records actually produced (may be fewer than the
    number of answers, since non-actively-used skills create no evidence).
    """
    response = AssessmentResponse.model_validate(raw_response)  # raises ValidationError on malformed input
    now = datetime.now(timezone.utc)
    evidence: List[DeclaredEvidence] = []
    for answer in response.answers:
        if not answer.actively_used:
            continue
        occurred = now - timedelta(days=_RECENCY_TO_DAYS_AGO[answer.recency])
        evidence.append(
            DeclaredEvidence(
                evidence_id=f"teams-{response.coded_identity}-{answer.skill_id}-{int(now.timestamp())}",
                coded_identity=response.coded_identity,
                skill_id=answer.skill_id,
                evidence_type=EvidenceType.DECLARED,
                proficiency=_EXPERIENCE_TO_LEVEL[answer.experience],
                occurred_at=occurred,
                source_ref=source_ref,
                metadata={
                    "channel": "teams_capability_check",
                    "delivered_in_real_work": answer.delivered_in_real_work,
                },
            )
        )
    if not evidence:
        return []
    # stage_and_merge returns the FULL recomputed system-wide matrix (every
    # coded identity with any evidence at all), not a diff of what this call
    # just submitted — found live, during the golden-path run, where it made
    # a 1-skill response look like 12. Filter back down to what this
    # submission actually produced before handing it to the caller.
    submitted_ids = {item.skill_id for item in evidence}
    full_matrix = svc.stage_and_merge(evidence)  # UnknownSkillError -> propagates
    return [
        r for r in full_matrix
        if r.coded_identity == response.coded_identity and r.skill_id in submitted_ids
    ]
