"""Scoring and runtime configuration (version = hash of values)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScoringConfig:
    demonstrated_weight: float
    certified_weight: float
    declared_weight: float
    freshness_half_life_days: float
    volume_k: float
    allocation_weight: float
    min_confidence: float
    min_coverage_ratio: float
    max_shortlist_size: int

    @property
    def version(self) -> str:
        payload = {
            "demonstrated_weight": self.demonstrated_weight,
            "certified_weight": self.certified_weight,
            "declared_weight": self.declared_weight,
            "freshness_half_life_days": self.freshness_half_life_days,
            "volume_k": self.volume_k,
            "allocation_weight": self.allocation_weight,
            "min_confidence": self.min_confidence,
            "min_coverage_ratio": self.min_coverage_ratio,
            "max_shortlist_size": self.max_shortlist_size,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


DEFAULT_SCORING = ScoringConfig(
    demonstrated_weight=0.55,
    certified_weight=0.30,
    declared_weight=0.15,
    freshness_half_life_days=180.0,
    volume_k=0.35,
    allocation_weight=0.15,
    min_confidence=0.1,
    min_coverage_ratio=0.6,
    max_shortlist_size=10,
)


def load_scoring_config() -> ScoringConfig:
    # Env overrides optional for ops; version always derives from actual values
    return ScoringConfig(
        demonstrated_weight=float(os.getenv("HERMES_W_DEMO", DEFAULT_SCORING.demonstrated_weight)),
        certified_weight=float(os.getenv("HERMES_W_CERT", DEFAULT_SCORING.certified_weight)),
        declared_weight=float(os.getenv("HERMES_W_DECL", DEFAULT_SCORING.declared_weight)),
        freshness_half_life_days=float(
            os.getenv("HERMES_HALF_LIFE", DEFAULT_SCORING.freshness_half_life_days)
        ),
        volume_k=float(os.getenv("HERMES_VOLUME_K", DEFAULT_SCORING.volume_k)),
        allocation_weight=float(os.getenv("HERMES_ALLOC_W", DEFAULT_SCORING.allocation_weight)),
        min_confidence=DEFAULT_SCORING.min_confidence,
        min_coverage_ratio=float(os.getenv("HERMES_MIN_COVERAGE", DEFAULT_SCORING.min_coverage_ratio)),
        max_shortlist_size=int(os.getenv("HERMES_MAX_SHORTLIST", DEFAULT_SCORING.max_shortlist_size)),
    )
