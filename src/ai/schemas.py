"""Structured LLM output. Raw model text is never trusted as application state
(Phase 15) — it is parsed as JSON and validated against these models, or the
caller gets a typed exception, never a silent best-effort guess.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SkillProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill: str = Field(..., min_length=1, max_length=200)
    importance: Literal["required", "preferred"]
    #: Set only after governed-taxonomy normalization (src/ai/services/work_requirement.py).
    #: None means the LLM's proposed label did not match a governed skill — it must
    #: never be invented into the taxonomy automatically (Phase 17).
    mapped_skill_id: Optional[str] = None


class WorkRequirementProposal(BaseModel):
    """A *proposal* only. Nothing here enters ranking until a human confirms it
    through the existing, unchanged /api/fitness/rank request body."""

    model_config = ConfigDict(extra="forbid")
    skills: List[SkillProposal] = Field(default_factory=list)
    #: Raw skill labels the LLM proposed that do not map to any governed skill_id.
    ambiguities: List[str] = Field(default_factory=list)
