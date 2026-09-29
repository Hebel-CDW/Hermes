"""Deterministic fitness ranking and skill-gap computation."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from shared.audit import AuditLedger
from shared.config import DEFAULT_SCORING, ScoringConfig, load_scoring_config
from shared.models import (
    CalculationDetail,
    FitnessResult,
    GapItem,
    GapResult,
    ProficiencyLevel,
    RankedCandidate,
    SkillContribution,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
)

MAX_SHORTLIST = 10

# Default partial credit when a required skill is evidenced only via a related skill.
# The engine reads the versioned value from ScoringConfig.adjacency_discount; this
# alias exists for callers that cite the default.
ADJACENCY_DISCOUNT = DEFAULT_SCORING.adjacency_discount


class FitnessGapEngine:
    def __init__(
        self,
        config: Optional[ScoringConfig] = None,
        audit: Optional[AuditLedger] = None,
        demand_weights: Optional[Mapping[str, float]] = None,
        adjacency: Optional[Mapping[str, Sequence[str]]] = None,
        skill_decay: Optional[Mapping[str, Mapping[str, Any]]] = None,
        evidence_source_refs: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        self.config = config or load_scoring_config()
        self.audit = audit or AuditLedger()
        self.demand_weights = dict(demand_weights or {})
        self.adjacency = {k: list(v) for k, v in (adjacency or {}).items()}
        # Display-only metadata for the calculation inspector. Never affects scores.
        self.skill_decay = {k: dict(v) for k, v in (skill_decay or {}).items()}
        self.evidence_source_refs = {
            k: list(v) for k, v in (evidence_source_refs or {}).items()
        }

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

        excluded_detail: List[Dict[str, Any]] = []
        for coded_id, skills in by_identity.items():
            score, reasoning, detail, evidence_ids, covered, envelope = self._fitness(
                required, skills, allocation.get(coded_id, 1.0), coded_identity=coded_id
            )
            envelope["min_coverage_ratio"] = min_cov
            envelope["computation_run_id"] = computation_run_id
            envelope["fitness_score"] = round(score, 4)

            def _exclude(reason: str) -> None:
                """Record why a candidate was dropped instead of discarding the trace."""
                envelope["excluded"] = True
                envelope["exclusion_reason"] = reason
                insufficient.append(coded_id)
                excluded_detail.append({"coded_identity": coded_id, "reason": reason})

            if not evidence_ids:
                _exclude("no_evidence_on_any_required_skill")
                continue
            if envelope["coverage_ratio"] < min_cov:
                _exclude("below_min_coverage")
                continue
            if critical and not all(
                self._lookup_skill(skills, sid)[0] is not None for sid in critical
            ):
                _exclude("missing_critical_skill")
                continue
            scored.append(
                RankedCandidate(
                    coded_identity=coded_id,
                    fitness_score=round(score, 4),
                    rank=0,
                    per_skill_reasoning=reasoning,
                    reasoning_detail=detail,
                    calculation=CalculationDetail(**envelope),
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
                    calculation=cand.calculation,
                    evidence_ids=cand.evidence_ids,
                )
            )

        result = FitnessResult(
            request_id=request.request_id,
            candidates=shortlist,
            scoring_config_version=self.config.version,
            computation_run_id=computation_run_id,
            excluded_candidates=excluded_detail,
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
        """Return (record, adjacency_discount, source_skill_id).

        ``discount == 1.0`` for a direct match; ``config.adjacency_discount`` when only a
        related skill is present; ``(None, 0.0, None)`` when nothing matches.
        ``source_skill_id`` names which skill actually supplied the evidence, so
        the inspector can show "credited via azure_compute" rather than implying
        direct evidence.
        """
        if skill_id in skills:
            return skills[skill_id], 1.0, skill_id
        for adj in self.adjacency.get(skill_id, []):
            if adj in skills:
                return skills[adj], self.config.adjacency_discount, adj
        for src, targets in self.adjacency.items():
            if skill_id in targets and src in skills:
                return skills[src], self.config.adjacency_discount, src
        return None, 0.0, None

    def _skill_decay(self, skill_id: str) -> tuple:
        """Return (decay_class, half_life_days) for inspector display, or (None, None)."""
        meta = self.skill_decay.get(skill_id) or {}
        return meta.get("decay_class"), meta.get("half_life_days")

    def _fitness(
        self,
        required: Mapping[str, ProficiencyLevel],
        skills: Mapping[str, SkillRecord],
        allocation: float,
        coded_identity: str = "",
    ):
        total = 0.0
        reasoning = {}
        detail: Dict[str, Any] = {}
        evidence_ids: List[str] = []
        source_refs: List[str] = []
        covered = 0
        for skill_id, required_level in required.items():
            record, discount, source_skill = self._lookup_skill(skills, skill_id)
            if record is None:
                reasoning[skill_id] = "missing skill evidence"
                detail[skill_id] = SkillContribution(
                    skill_id=skill_id,
                    status="missing",
                    required_level=int(required_level),
                    required=int(required_level),
                    adjacency_discount=0.0,
                    contribution=0.0,
                ).model_dump()
                continue
            covered += 1
            level_ratio = min(1.0, int(record.proficiency) / max(1, int(required_level)))
            # Freshness applied exactly once here — it is NOT folded into confidence.
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
            decay_class, half_life = self._skill_decay(record.skill_id)
            record_refs = list(
                self.evidence_source_refs.get((coded_identity, record.skill_id), [])
            )
            detail[skill_id] = SkillContribution(
                skill_id=skill_id,
                status="matched" if discount >= 1.0 else "adjacent",
                required_level=int(required_level),
                actual_level=int(record.proficiency),
                level_ratio=round(level_ratio, 6),
                confidence=record.confidence,
                volume_score=record.volume_score,
                freshness=record.freshness,
                decay_class=decay_class,
                half_life_days=half_life,
                adjacency_discount=discount,
                adjacency_source_skill=None if discount >= 1.0 else source_skill,
                contribution=round(contrib, 6),
                evidence_ids=list(record.evidence_ids),
                source_refs=record_refs,
                # Backwards-compatible aliases
                level=int(record.proficiency),
                required=int(required_level),
            ).model_dump()
            evidence_ids.extend(record.evidence_ids)
            source_refs.extend(record_refs)
        contribution_sum = total
        if required:
            total = total / len(required)
        mean_contribution = total
        # Graduated allocation (not a boolean filter bonus).
        # w == config.allocation_weight, so the multiplier spans [1-w, 1.0].
        # At the default w=0.15 this is the historical 0.85 + 0.15*allocation.
        # Sourcing w from config (rather than hardcoding it) keeps the
        # scoring_config_version hash faithful: changing HERMES_ALLOC_W now
        # actually changes scores, and leaving it alone cannot change them.
        w = max(0.0, min(1.0, self.config.allocation_weight))
        clamped_allocation = max(0.0, min(1.0, allocation))
        allocation_multiplier = (1.0 - w) + w * clamped_allocation
        total *= allocation_multiplier
        envelope = {
            "required_skill_count": len(required),
            "matched_skill_count": covered,
            "coverage_ratio": round(covered / max(1, len(required)), 6),
            "contribution_sum": round(contribution_sum, 6),
            "mean_contribution": round(mean_contribution, 6),
            "allocation": allocation,
            "allocation_weight": w,
            "allocation_multiplier": round(allocation_multiplier, 6),
            "scoring_config_version": self.config.version,
        }
        return total, reasoning, detail, evidence_ids, covered, envelope

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
