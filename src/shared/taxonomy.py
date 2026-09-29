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


def _merge_pilot(raw: Dict[str, Any], taxonomy_path: Path) -> Dict[str, Any]:
    """Append governed pilot skills from taxonomy/pilot_ontology.yaml when present."""
    if taxonomy_path.name != "skills_ontology.yaml":
        return raw
    pilot_path = taxonomy_path.with_name("pilot_ontology.yaml")
    if not pilot_path.is_file():
        return raw
    extra = yaml.safe_load(pilot_path.read_text(encoding="utf-8")) or {}
    by_id = {d["domain_id"]: d for d in raw.get("domains") or []}
    existing_skills = {
        s["skill_id"] for d in raw.get("domains") or [] for s in d.get("skills") or []
    }
    for domain in extra.get("domains") or []:
        target = by_id.get(domain["domain_id"])
        new_skills = [s for s in domain.get("skills") or [] if s["skill_id"] not in existing_skills]
        if target is None:
            raw.setdefault("domains", []).append({**domain, "skills": new_skills})
            by_id[domain["domain_id"]] = raw["domains"][-1]
        else:
            target["skills"] = list(target.get("skills") or []) + new_skills
        existing_skills.update(s["skill_id"] for s in new_skills)
    return raw


def load_taxonomy(path: Optional[Path] = None) -> SkillsTaxonomy:
    taxonomy_path = path or default_taxonomy_path()
    with taxonomy_path.open("r", encoding="utf-8") as handle:
        raw: Dict[str, Any] = yaml.safe_load(handle)
    raw = _merge_pilot(raw, taxonomy_path)
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
