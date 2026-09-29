"""Immutable domain models for Hermes. No protected demographic attributes."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceType(str, Enum):
    DEMONSTRATED = "demonstrated"
    CERTIFIED = "certified"
    DECLARED = "declared"


class ProficiencyLevel(int, Enum):
    AWARENESS = 1
    WORKING = 2
    PROFICIENT = 3
    ADVANCED = 4
    EXPERT = 5


class CodedIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str = Field(..., pattern=r"^EMP-[0-9a-fA-F]{8}$")


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    coded_identity: str
    skill_id: str
    evidence_type: EvidenceType
    proficiency: ProficiencyLevel
    occurred_at: datetime
    source_ref: str
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DemonstratedEvidence(EvidenceRecord):
    evidence_type: EvidenceType = EvidenceType.DEMONSTRATED


class CertifiedEvidence(EvidenceRecord):
    evidence_type: EvidenceType = EvidenceType.CERTIFIED


class DeclaredEvidence(EvidenceRecord):
    evidence_type: EvidenceType = EvidenceType.DECLARED
    manager_confirmed: bool = True


class SkillRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    coded_identity: str
    skill_id: str
    proficiency: ProficiencyLevel
    confidence: float = Field(..., ge=0.0, le=1.0)
    freshness: float = Field(..., ge=0.0, le=1.0)
    volume_score: float = Field(0.0, ge=0.0, le=1.0)
    evidence_ids: List[str]
    computed_at: datetime = Field(default_factory=utc_now)
    scoring_config_version: str
    # Which inference run produced this row. Mirrors skills_matrix.computation_run_id.
    # Empty string means "not recorded" (rows written before run ids were threaded).
    computation_run_id: str = ""


class StaffingRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    requester_id: str
    required_skills: Dict[str, ProficiencyLevel]
    shortlist_size: int = Field(3, ge=1, le=10)
    availability_required: bool = True


class TargetRoleProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    role_id: str
    role_name: str
    required_skills: Dict[str, ProficiencyLevel]
    critical_skills: List[str] = Field(default_factory=list)
    min_coverage_ratio: float = 0.6


class SkillContribution(BaseModel):
    """Per-skill calculation trace — every operand of the contribution formula.

    Serialised into ``RankedCandidate.reasoning_detail[skill_id]`` so a reviewer
    can recompute the number by hand:

        level_ratio  = min(1, actual_level / required_level)
        contribution = level_ratio * confidence * volume_score
                       * freshness * adjacency_discount

    ``status='missing'`` means no record and no adjacent substitute was found;
    every numeric operand is then None and the skill contributes 0.
    """

    model_config = ConfigDict(frozen=True)

    skill_id: str
    status: str  # matched | adjacent | missing
    required_level: Optional[int] = None
    actual_level: Optional[int] = None
    level_ratio: Optional[float] = None
    confidence: Optional[float] = None
    volume_score: Optional[float] = None
    freshness: Optional[float] = None
    decay_class: Optional[str] = None
    half_life_days: Optional[float] = None
    adjacency_discount: float = 0.0
    adjacency_source_skill: Optional[str] = None
    contribution: Optional[float] = None
    evidence_ids: List[str] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    # Backwards-compatible aliases retained for existing consumers/tests.
    level: Optional[int] = None
    required: Optional[int] = None


class CalculationDetail(BaseModel):
    """Candidate-level calculation envelope — how per-skill contributions combine.

    Kept separate from ``reasoning_detail`` so that map stays purely skill-keyed
    (previously it carried ``_allocation``/``_exclusion`` magic keys alongside
    real skill ids, which forced consumers to type-guard every value).
    """

    model_config = ConfigDict(frozen=True)

    required_skill_count: int = 0
    matched_skill_count: int = 0
    coverage_ratio: float = 0.0
    min_coverage_ratio: float = 0.0
    contribution_sum: float = 0.0
    mean_contribution: float = 0.0
    allocation: float = 1.0
    allocation_weight: float = 0.0
    allocation_multiplier: float = 1.0
    fitness_score: float = 0.0
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    scoring_config_version: str = ""
    computation_run_id: str = ""
    formula: str = (
        "fitness = mean(level_ratio * confidence * volume_score * freshness * "
        "adjacency_discount) * ((1 - allocation_weight) + allocation_weight * allocation)"
    )


class RankedCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    coded_identity: str
    fitness_score: float
    rank: int
    per_skill_reasoning: Dict[str, str]
    reasoning_detail: Dict[str, Any] = Field(default_factory=dict)
    calculation: Optional[CalculationDetail] = None
    evidence_ids: List[str]


class FitnessResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    candidates: List[RankedCandidate]
    scoring_config_version: str
    computed_at: datetime = Field(default_factory=utc_now)
    # Which matrix run the ranking read from — pairs with scoring_config_version
    # to make a result reproducible.
    computation_run_id: str = ""
    # Machine-readable reasons for every candidate the engine dropped. Previously
    # these were computed and discarded, so "why was X not shortlisted?" had no answer.
    excluded_candidates: List[Dict[str, Any]] = Field(default_factory=list)


class GapItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_id: str
    required_level: ProficiencyLevel
    current_level: Optional[ProficiencyLevel]
    demand_impact: float
    reasoning: str
    evidence_ids: List[str]


class GapResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    coded_identity: str
    role_id: str
    gaps: List[GapItem]
    scoring_config_version: str
    computed_at: datetime = Field(default_factory=utc_now)


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str
    actor: str
    payload: Dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)


PROTECTED_ATTRIBUTE_FIELDS = frozenset(
    {
        "age",
        "gender",
        "ethnicity",
        "race",
        "religion",
        "disability",
        "sexual_orientation",
        "national_origin",
        "marital_status",
        "pregnancy",
        "date_of_birth",
        "dob",
    }
)

IDENTITY_PII_FIELDS = frozenset(
    {
        "name",
        "full_name",
        "first_name",
        "last_name",
        "display_name",
        "email",
        "employee_id",
        "employee_number",
        "user_id",
        "sys_id",
        "upn",
        "sam_account_name",
        "phone",
        "mobile",
    }
)


def load_client_name_blocklist(path: Optional[Path] = None) -> frozenset:
    """Load confidential account labels from config/client_names.txt (gitignored)."""
    from pathlib import Path as _Path

    candidates = []
    if path is not None:
        candidates.append(_Path(path))
    else:
        root = _Path(__file__).resolve().parents[2]
        candidates.append(root / "config" / "client_names.txt")
        candidates.append(root / "config" / "client_names.example")
    labels: set = set()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            labels.add(s.lower())
        break
    return frozenset(labels)


CLIENT_NAME_BLOCKLIST = load_client_name_blocklist()


# Soft-skill / non-technical assessment columns — never enter Hermes
EXCLUDED_ASSESSMENT_FIELDS = frozenset(
    {
        "customer service",
        "written & verbal communication",
        "written and verbal communication",
        "email etiquette",
        "email ethiquette",
        "meeting effectiveness",
        "culture fit",
        "flexibility",
        "knowledge sharing",
        "communication with coworkers",
        "responsibility/accountability",
        "responsibility / accountability",
        "soft-skills",
        "soft skills",
        "tools expertise",
        "technical expertise",
        "additional skills",
        "process awareness",
    }
)


class CultureFitForbiddenError(ValueError):
    """Raised when a culture-fit column is encountered at ingestion."""


def is_excluded_assessment_label(label: str) -> bool:
    return label.strip().lower() in EXCLUDED_ASSESSMENT_FIELDS


def is_culture_fit_label(label: str) -> bool:
    return label.strip().lower() == "culture fit"


def is_client_name_label(label: str, blocklist: Optional[frozenset] = None) -> bool:
    bl = blocklist if blocklist is not None else CLIENT_NAME_BLOCKLIST
    return label.strip().lower() in bl
