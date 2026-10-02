"""Structured capability-check models. Raw Teams Activity payloads are never
trusted as application state — they are parsed into these and validated, or
the caller gets a typed exception, same discipline as src/ai/schemas.py.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

#: Hard cap matching the explicit "5-10 questions maximum" requirement —
#: enforced here, not left to whatever happens to be passed in.
MAX_QUESTIONS = 10


class CapabilityQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str = Field(..., min_length=1, max_length=128)
    skill_label: str = Field(..., min_length=1, max_length=200)


class AssessmentInvite(BaseModel):
    """What Hermes sends. Deliberately short — a handful of governed skills,
    not a 50-question HR survey."""

    model_config = ConfigDict(extra="forbid")
    coded_identity: str = Field(..., pattern=r"^EMP-[0-9a-fA-F]{8}$")
    questions: List[CapabilityQuestion] = Field(..., min_length=1, max_length=MAX_QUESTIONS)


class SkillAnswer(BaseModel):
    """One answered skill from the card: active use, self-rated experience,
    recency, and whether it was used in real delivered work. All four map
    directly onto the engine's existing confidence/freshness inputs — this
    does not invent a new scoring dimension."""

    model_config = ConfigDict(extra="forbid")
    skill_id: str = Field(..., min_length=1, max_length=128)
    actively_used: bool
    experience: Literal["beginner", "working", "advanced", "expert"]
    recency: Literal["under_30_days", "1_to_6_months", "6_to_12_months", "over_1_year"]
    delivered_in_real_work: bool


class AssessmentResponse(BaseModel):
    """What comes back from Teams. ``manager_coded_identity`` is who sent the
    invite and therefore who the resulting DECLARED evidence is attributed to
    as the confirming actor in the audit trail — never client-asserted
    identity, same rule as every other evidence-writing path in this app."""

    model_config = ConfigDict(extra="forbid")
    coded_identity: str = Field(..., pattern=r"^EMP-[0-9a-fA-F]{8}$")
    answers: List[SkillAnswer] = Field(..., max_length=MAX_QUESTIONS)
    submitted_at: Optional[str] = None
