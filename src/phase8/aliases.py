"""Skill alias resolution — never fuzzy-match into a live skill_id at ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, TYPE_CHECKING

from phase8.workbook import normalize_label, slug_skill_id

if TYPE_CHECKING:
    from shared.db import HermesDB


@dataclass(frozen=True)
class AliasResolution:
    skill_id: Optional[str]
    match_confidence: float
    mapped_by: str  # auto | human | pending
    alias_label: str


class SkillAliasResolver:
    def __init__(self, db: "HermesDB", ontology_ids: Optional[Dict[str, str]] = None) -> None:
        self.db = db
        # normalized_label -> skill_id from ontology
        self._ontology = dict(ontology_ids or {})
        self._cache: Dict[str, AliasResolution] = {}

    def resolve(self, raw_label: str) -> AliasResolution:
        label = raw_label.strip()
        key = normalize_label(label)
        if key in self._cache:
            return self._cache[key]

        # 1. Exact match against ontology skill_id or name (normalized)
        if key in self._ontology:
            res = AliasResolution(self._ontology[key], 1.0, "auto", label)
            self._cache[key] = res
            return res

        # 2. Alias table
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT skill_id, match_confidence, mapped_by FROM skill_aliases WHERE alias_label = ?",
                (key,),
            ).fetchone()
        if row and row["mapped_by"] in {"auto", "human"}:
            res = AliasResolution(row["skill_id"], float(row["match_confidence"]), row["mapped_by"], label)
            self._cache[key] = res
            return res

        # 3. Normalised-string match against ontology keys already done; try slug id equality
        slug = slug_skill_id(label)
        if slug in self._ontology.values():
            res = AliasResolution(slug, 0.95, "auto", label)
            self._cache[key] = res
            return res
        # reverse: ontology values are skill_ids
        if slug in set(self._ontology.values()):
            res = AliasResolution(slug, 0.95, "auto", label)
            self._cache[key] = res
            return res

        # 4. pending — never fuzzy into live skill_id
        res = AliasResolution(None, 0.0, "pending", label)
        self._cache[key] = res
        # Persist pending stub so it is counted/reported
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO skill_aliases (alias_label, skill_id, match_confidence, mapped_by)
                VALUES (?, '', 0.0, 'pending')
                ON CONFLICT(alias_label) DO NOTHING
                """,
                (key,),
            )
        return res


def ontology_lookup_map(taxonomy) -> Dict[str, str]:
    """normalized name/id -> skill_id."""
    out: Dict[str, str] = {}
    for skill in taxonomy.all_skills():
        out[normalize_label(skill.skill_id)] = skill.skill_id
        out[normalize_label(skill.name)] = skill.skill_id
    return out
