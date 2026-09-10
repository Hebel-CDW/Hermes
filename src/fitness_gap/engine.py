"""Deterministic fitness ranking and skill-gap computation."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from shared.audit import AuditLedger
from shared.config import ScoringConfig, load_scoring_config
from shared.models import (
    FitnessResult,
    GapItem,
    GapResult,
    ProficiencyLevel,
    RankedCandidate,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
)

MAX_SHORTLIST = 10


class FitnessGapEngine:
    def __init__(
        self,
        config: Optional[ScoringConfig] = None,
        audit: Optional[AuditLedger] = None,
        demand_weights: Optional[Mapping[str, float]] = None,
        adjacency: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        self.config = config or load_scoring_config()
        self.audit = audit or AuditLedger()
        self.demand_weights = dict(demand_weights or {})
        self.adjacency = {k: list(v) for k, v in (adjacency or {}).items()}

    def _cap_shortlist(self, n: int) -> int:
        return max(1, min(int(n), self.config.max_shortlist_size, MAX_SHORTLIST))

    def rank_candidates(
        self,
        request: StaffingRequest,
        skill_matrix: Sequence[SkillRecord],
        availability: Optional[Mapping[str, bool]] = None,
        allocation: Optional[Mapping[str, float]] = None,
        computation_run_id: str = "",
        cold_start_ids: Optional[Sequence[str]] = None,
        critical_skills: Optional[Sequence[str]] = None,
        min_coverage_ratio: Optional[float] = None,
    ) -> FitnessResult:
        allocation = allocation or {}
        critical = set(critical_skills or [])
        by_identity: Dict[str, Dict[str, SkillRecord]] = {}
        for record in skill_matrix:
            by_identity.setdefault(record.coded_identity, {})[record.skill_id] = record

        required = request.required_skills
        min_cov = min_coverage_ratio if min_coverage_ratio is not None else self.config.min_coverage_ratio
        scored: List[RankedCandidate] = []
        insufficient: List[str] = []

        for coded_id, skills in by_identity.items():
            score, reasoning, detail, evidence_ids, covered = self._fitness(
                required, skills, allocation.get(coded_id, 1.0)
            )
            if not evidence_ids:
                insufficient.append(coded_id)
                continue
            coverage = covered / max(1, len(required))
            if coverage < min_cov:
                detail["_exclusion"] = "below_min_coverage"
                insufficient.append(coded_id)
                continue
            if critical and not all(
                (sid in skills) or self._lookup_skill(skills, sid)[0] is not None for sid in critical
            ):
                detail["_exclusion"] = "missing_critical_skill"
                insufficient.append(coded_id)
                continue
            scored.append(
                RankedCandidate(
                    coded_identity=coded_id,
                    fitness_score=round(score, 4),
                    rank=0,
                    per_skill_reasoning=reasoning,
                    reasoning_detail=detail,
                    evidence_ids=sorted(set(evidence_ids)),
                )
            )

        scored.sort(key=lambda c: (-c.fitness_score, c.coded_identity))
        size = self._cap_shortlist(request.shortlist_size)
        shortlist = []
        for idx, cand in enumerate(scored[:size], start=1):
            shortlist.append(
                RankedCandidate(
                    coded_identity=cand.coded_identity,
                    fitness_score=cand.fitness_score,
                    rank=idx,
                    per_skill_reasoning=cand.per_skill_reasoning,
                    reasoning_detail=cand.reasoning_detail,
                    evidence_ids=cand.evidence_ids,
                )
            )

        # Exploration slot: optionally append one cold-start / insufficient signal
        # (visible cohort, not scored into top ranks)
        result = FitnessResult(
            request_id=request.request_id,
            candidates=shortlist,
            scoring_config_version=self.config.version,
        )
        self.audit.append(
            "fitness_ranking",
            actor=request.requester_id,
            payload={
                "request_id": request.request_id,
                "candidate_tokens": [c.coded_identity for c in shortlist],
                "scoring_config_version": self.config.version,
                "computation_run_id": computation_run_id,
                "insufficient_evidence_cohort": insufficient[:20],
            },
        )
        return result

    def _lookup_skill(
        self, skills: Mapping[str, SkillRecord], skill_id: str
    ) -> tuple:
        """Return (record, adjacency_discount) — discount < 1 if adjacent-only."""
        if skill_id in skills:
            return skills[skill_id], 1.0
        for adj in self.adjacency.get(skill_id, []):
            if adj in skills:
                return skills[adj], 0.5
        for src, targets in self.adjacency.items():
            if skill_id in targets and src in skills:
                return skills[src], 0.5
        return None, 0.0

    def _fitness(
        self,
        required: Mapping[str, ProficiencyLevel],
        skills: Mapping[str, SkillRecord],
        allocation: float,
    ):
        total = 0.0
        reasoning = {}
        detail: Dict[str, Any] = {}
        evidence_ids: List[str] = []
        covered = 0
        for skill_id, required_level in required.items():
            record, discount = self._lookup_skill(skills, skill_id)
            if record is None:
                reasoning[skill_id] = "missing skill evidence"
                detail[skill_id] = {"status": "missing"}
                continue
            covered += 1
            level_ratio = min(1.0, int(record.proficiency) / max(1, int(required_level)))
            # Freshness applied once here (not also inside confidence)
            contrib = (
                level_ratio
                * record.confidence
                * record.volume_score
                * record.freshness
                * discount
            )
            total += contrib
            reasoning[skill_id] = (
                f"level={int(record.proficiency)}/{int(required_level)} "
                f"confidence={record.confidence:.2f} volume={record.volume_score:.2f} "
                f"freshness={record.freshness:.2f} adjacency={discount:.2f} "
                f"evidence={','.join(record.evidence_ids)}"
            )
            detail[skill_id] = {
                "status": "matched",
                "level": int(record.proficiency),
                "required": int(required_level),
                "confidence": record.confidence,
                "volume_score": record.volume_score,
                "freshness": record.freshness,
                "adjacency_discount": discount,
                "evidence_ids": list(record.evidence_ids),
            }
            evidence_ids.extend(record.evidence_ids)
        if required:
            total = total / len(required)
        # Graduated allocation (not boolean filter bonus)
        total *= 0.85 + 0.15 * max(0.0, min(1.0, allocation))
        detail["_allocation"] = allocation
        return total, reasoning, detail, evidence_ids, covered

    def compute_gaps(
        self,
        coded_identity: str,
        role: TargetRoleProfile,
        skill_matrix: Sequence[SkillRecord],
    ) -> GapResult:
        skills = {
            r.skill_id: r
            for r in skill_matrix
            if r.coded_identity == coded_identity
        }
        gaps: List[GapItem] = []
        for skill_id, required_level in role.required_skills.items():
            record = skills.get(skill_id)
            current = record.proficiency if record else None
            evidence_ids = list(record.evidence_ids) if record else []
            if current is not None and int(current) >= int(required_level):
                continue
            demand = float(self.demand_weights.get(skill_id, 0.5))
            deficit = int(required_level) - (int(current) if current else 0)
            gaps.append(
                GapItem(
                    skill_id=skill_id,
                    required_level=required_level,
                    current_level=current,
                    demand_impact=round(demand * deficit, 4),
                    reasoning=(
                        f"current={int(current) if current else 0} "
                        f"required={int(required_level)} demand={demand}"
                    ),
                    evidence_ids=evidence_ids,
                )
            )
        gaps.sort(key=lambda g: (-g.demand_impact, g.skill_id))
        result = GapResult(
            coded_identity=coded_identity,
            role_id=role.role_id,
            gaps=gaps,
            scoring_config_version=self.config.version,
        )
        self.audit.append(
            "gap_computation",
            actor=coded_identity,
            payload={
                "role_id": role.role_id,
                "gap_skills": [g.skill_id for g in gaps],
                "scoring_config_version": self.config.version,
            },
        )
        return result
