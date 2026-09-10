"""Load and validate the skills ontology / taxonomy."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from shared.models import ProficiencyLevel


class ProficiencyDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: ProficiencyLevel
    label: str
    behavioural_definition: str


class SkillDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_id: str
    name: str
    description: str
    ticket_keywords: List[str] = Field(default_factory=list)
    cert_codes: List[str] = Field(default_factory=list)
    freshness_half_life_days: Optional[float] = None
    relations: List[str] = Field(default_factory=list)
    related_skills: List[str] = Field(default_factory=list)
    decay_class: Optional[str] = None  # fast | medium | slow
    proficiency_levels: List[ProficiencyDefinition]


class SkillDomain(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain_id: str
    name: str
    skills: List[SkillDefinition]


class SkillsTaxonomy(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    domains: List[SkillDomain]

    def skill_by_id(self, skill_id: str) -> Optional[SkillDefinition]:
        for domain in self.domains:
            for skill in domain.skills:
                if skill.skill_id == skill_id:
                    return skill
        return None

    def all_skills(self) -> List[SkillDefinition]:
        return [s for d in self.domains for s in d.skills]

    def match_keywords(self, text: str) -> List[str]:
        lowered = text.lower()
        matched: List[str] = []
        for skill in self.all_skills():
            if any(kw.lower() in lowered for kw in skill.ticket_keywords):
                matched.append(skill.skill_id)
        return matched


def default_taxonomy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "taxonomy" / "skills_ontology.yaml"


def load_taxonomy(path: Optional[Path] = None) -> SkillsTaxonomy:
    taxonomy_path = path or default_taxonomy_path()
    with taxonomy_path.open("r", encoding="utf-8") as handle:
        raw: Dict[str, Any] = yaml.safe_load(handle)
    return SkillsTaxonomy.model_validate(raw)


DECAY_HALF_LIFE_DAYS = {
    "fast": 90.0,
    "medium": 365.0,
    "slow": 1095.0,
}


def validate_taxonomy_completeness(taxonomy: SkillsTaxonomy) -> List[str]:
    """Return list of validation errors; empty means approved-ready."""
    errors: List[str] = []
    expected = {1, 2, 3, 4, 5}
    for skill in taxonomy.all_skills():
        levels = {p.level.value for p in skill.proficiency_levels}
        if levels != expected:
            errors.append(f"{skill.skill_id}: missing proficiency levels {expected - levels}")
        for p in skill.proficiency_levels:
            if not p.behavioural_definition.strip():
                errors.append(f"{skill.skill_id} L{p.level}: empty behavioural definition")
        if not skill.decay_class or skill.decay_class not in DECAY_HALF_LIFE_DAYS:
            errors.append(f"{skill.skill_id}: decay_class must be fast|medium|slow")
        if not skill.ticket_keywords:
            errors.append(f"{skill.skill_id}: at least one ticket_keyword required")
    return errors
