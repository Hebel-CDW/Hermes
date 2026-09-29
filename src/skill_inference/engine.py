"""Convert coded evidence into scored skill records with confidence, volume, freshness."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shared.config import ScoringConfig, load_scoring_config
from shared.errors import UnknownSkillError
from shared.models import (
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    SkillRecord,
)
from shared.taxonomy import SkillsTaxonomy, load_taxonomy


def _days_between(later: datetime, earlier: datetime) -> float:
    if later.tzinfo is None:
        later = later.replace(tzinfo=timezone.utc)
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=timezone.utc)
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


DEPTH_KEYWORDS = {
    "migration",
    "cluster",
    "architecture",
    "design",
    "production",
    "sev1",
    "sev2",
    "p1",
    "outage",
    "rollback",
    "upgrade",
}
SURFACE_KEYWORDS = {
    "password",
    "reset",
    "access",
    "login",
    "unlock",
    "mention",
}


class SkillInferenceEngine:
    """Deterministic evidence merge and skill scoring."""

    def __init__(
        self,
        taxonomy: Optional[SkillsTaxonomy] = None,
        config: Optional[ScoringConfig] = None,
    ) -> None:
        self.taxonomy = taxonomy or load_taxonomy()
        self.config = config or load_scoring_config()

    def _negative_penalty(self, metadata: Mapping) -> int:
        """Lower demonstrated ceiling when reopen/escalation flags exist."""
        penalty = 0
        if metadata.get("reopen") or metadata.get("reopened"):
            penalty += 1
        if metadata.get("escalation") or metadata.get("escalated"):
            penalty += 1
        return penalty

    def _demonstrated_level(self, ticket_text: str, skill_id: str, metadata: Optional[Mapping] = None) -> ProficiencyLevel:
        lowered = ticket_text.lower()
        depth_hits = sum(1 for k in DEPTH_KEYWORDS if k in lowered)
        surface_hits = sum(1 for k in SURFACE_KEYWORDS if k in lowered)
        skill = self.taxonomy.skill_by_id(skill_id)
        tier = 0
        if skill:
            for kw in skill.ticket_keywords:
                if kw.lower() in lowered:
                    tier = max(tier, 2 if " " in kw.strip() or len(kw) > 12 else 1)
        if depth_hits >= 2 or (depth_hits >= 1 and tier >= 2):
            level = int(ProficiencyLevel.ADVANCED)
        elif depth_hits >= 1 or tier >= 2:
            level = int(ProficiencyLevel.PROFICIENT)
        elif surface_hits and not depth_hits:
            level = int(ProficiencyLevel.WORKING)
        else:
            level = int(ProficiencyLevel.WORKING if tier else ProficiencyLevel.AWARENESS)
        if metadata:
            level = max(1, level - self._negative_penalty(metadata))
        return ProficiencyLevel(level)

    def infer_from_ticket(
        self,
        coded_identity: str,
        ticket_text: str,
        occurred_at: datetime,
        source_ref: str,
        evidence_id: str,
    ) -> List[EvidenceRecord]:
        skill_ids = self.taxonomy.match_keywords(ticket_text)
        lowered = ticket_text.lower()
        records: List[EvidenceRecord] = []
        for skill_id in skill_ids:
            skill = self.taxonomy.skill_by_id(skill_id)
            matched = [kw for kw in (skill.ticket_keywords if skill else []) if kw.lower() in lowered]
            records.append(
                EvidenceRecord(
                    evidence_id=f"{evidence_id}:{skill_id}",
                    coded_identity=coded_identity,
                    skill_id=skill_id,
                    evidence_type=EvidenceType.DEMONSTRATED,
                    proficiency=self._demonstrated_level(ticket_text, skill_id),
                    occurred_at=occurred_at,
                    source_ref=source_ref,
                    weight=1.0,
                    metadata={
                        "matched_keywords": matched,
                        "source_ref": source_ref,
                    },
                )
            )
        return records

    def weight_for_type(self, evidence_type: EvidenceType) -> float:
        if evidence_type == EvidenceType.DEMONSTRATED:
            return self.config.demonstrated_weight
        if evidence_type == EvidenceType.CERTIFIED:
            return self.config.certified_weight
        return self.config.declared_weight

    def half_life_for_skill(self, skill_id: str) -> float:
        """Effective half-life: ontology override if present, else the configured class value.

        Both inputs are versioned: the override through ``taxonomy_fingerprint`` and the
        class half-lives as explicit config fields. Unknown skills are rejected rather
        than decayed with an unversioned default.
        """
        skill = self.taxonomy.skill_by_id(skill_id)
        if skill is None:
            raise UnknownSkillError(f"skill {skill_id!r} is not in the governed ontology")
        if skill.freshness_half_life_days:
            return float(skill.freshness_half_life_days)
        return float(self.config.half_life_for_class(skill.decay_class or ""))

    def freshness_score(
        self,
        occurred_at: datetime,
        skill_id: str = "",
        as_of: Optional[datetime] = None,
    ) -> float:
        now = as_of or datetime.now(timezone.utc)
        days = _days_between(now, occurred_at)
        # No skill: utility use only (never a scored record) — medium class half-life.
        half = self.half_life_for_skill(skill_id) if skill_id else self.config.half_life_medium_days
        return max(0.0, min(1.0, math.pow(0.5, days / half)))

    def merge_evidence(
        self,
        evidence: Sequence[EvidenceRecord],
        as_of: Optional[datetime] = None,
    ) -> List[SkillRecord]:
        grouped: Dict[Tuple[str, str], List[EvidenceRecord]] = defaultdict(list)
        for item in evidence:
            if self.taxonomy.skill_by_id(item.skill_id) is None:
                raise UnknownSkillError(
                    f"evidence {item.evidence_id!r} references unknown skill {item.skill_id!r}"
                )
            if item.evidence_type == EvidenceType.DECLARED:
                confirmed = getattr(item, "manager_confirmed", None)
                if confirmed is False:
                    continue
                if confirmed is None and not item.metadata.get("manager_confirmed", True):
                    continue
            grouped[(item.coded_identity, item.skill_id)].append(item)

        results: List[SkillRecord] = []
        for (coded_id, skill_id), items in grouped.items():
            results.append(self._score_group(coded_id, skill_id, items, as_of=as_of))
        return results

    def _score_group(
        self,
        coded_id: str,
        skill_id: str,
        items: Sequence[EvidenceRecord],
        as_of: Optional[datetime] = None,
    ) -> SkillRecord:
        now = as_of or datetime.now(timezone.utc)
        by_type: Dict[EvidenceType, List[EvidenceRecord]] = defaultdict(list)
        for item in items:
            by_type[item.evidence_type].append(item)

        level_scores: Dict[int, float] = defaultdict(float)
        freshness_parts: List[float] = []
        evidence_ids: List[str] = []
        types_present = set()

        for item in items:
            tw = self.weight_for_type(item.evidence_type)
            fr = self.freshness_score(item.occurred_at, skill_id=skill_id, as_of=now)
            # Level vote uses type weight only (freshness applied once on record freshness)
            contribution = tw * item.weight
            level_scores[int(item.proficiency)] += contribution
            freshness_parts.append(fr)
            evidence_ids.append(item.evidence_id)
            types_present.add(item.evidence_type)

        best_level = max(level_scores.items(), key=lambda kv: (kv[1], kv[0]))[0]
        if EvidenceType.DEMONSTRATED in by_type:
            demo_levels = [int(e.proficiency) for e in by_type[EvidenceType.DEMONSTRATED]]
            demo_mode = max(set(demo_levels), key=demo_levels.count)
            if abs(demo_mode - best_level) <= 1:
                best_level = max(best_level, demo_mode)

        # Confidence = agreement across evidence types (not accumulation)
        type_count = len(types_present)
        confidence = max(self.config.min_confidence, min(1.0, 0.35 * type_count))
        if EvidenceType.DEMONSTRATED in types_present and EvidenceType.CERTIFIED in types_present:
            confidence = min(1.0, confidence + 0.2)

        n_demo = len(by_type.get(EvidenceType.DEMONSTRATED, []))
        volume_score = 1.0 - math.exp(-self.config.volume_k * n_demo)
        freshness = sum(freshness_parts) / len(freshness_parts)

        return SkillRecord(
            coded_identity=coded_id,
            skill_id=skill_id,
            proficiency=ProficiencyLevel(best_level),
            confidence=round(confidence, 4),
            freshness=round(freshness, 4),
            volume_score=round(volume_score, 4),
            evidence_ids=sorted(evidence_ids),
            scoring_config_version=self.config.version,
        )

    def ensure_coverage(self, evidence: Iterable[EvidenceRecord]) -> Mapping[str, int]:
        merged = self.merge_evidence(list(evidence))
        counts: Dict[str, int] = defaultdict(int)
        for record in merged:
            counts[record.coded_identity] += 1
        return dict(counts)
