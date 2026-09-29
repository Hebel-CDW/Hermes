"""Scoring configuration. ``version`` is a hash of everything that can change a score.

Fidelity contract (enforced by ``tests/unit/test_config_fidelity.py``):
the version changes **if and only if** a score can change. Therefore the hash covers

* every numeric scoring constant below, including the adjacency discount
  (previously hard-coded and unversioned);
* ``effective_half_lives`` — the half-life each ontology skill actually decays at
  (its override if present, else its configured decay class). Hashing the effective
  values, not the raw class table, means a class half-life that no skill uses cannot
  move the version; and
* ``taxonomy_fingerprint`` — ticket keywords and adjacency relations, which change
  evidence matching and partial credit.

Removed: ``HERMES_HALF_LIFE`` / ``freshness_half_life_days``. Every ontology skill
has a decay class, so that global default could never affect a scored record while
still moving the version hash. Setting it now raises instead of being silently ignored.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from shared.errors import ConfigurationError


def taxonomy_scoring_fingerprint(path: Optional[Path] = None) -> str:
    """Hash of keyword and adjacency fields (half-lives are hashed as effective values)."""
    from shared.taxonomy import load_taxonomy

    tax = load_taxonomy(path)
    projection = [
        {
            "skill_id": s.skill_id,
            "ticket_keywords": sorted(k.lower() for k in s.ticket_keywords),
            "adjacency": sorted(set(s.related_skills) | set(s.relations)),
        }
        for s in sorted(tax.all_skills(), key=lambda x: x.skill_id)
    ]
    raw = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ScoringConfig:
    demonstrated_weight: float
    certified_weight: float
    declared_weight: float
    half_life_fast_days: float
    half_life_medium_days: float
    half_life_slow_days: float
    volume_k: float
    allocation_weight: float
    adjacency_discount: float
    min_confidence: float
    min_coverage_ratio: float
    max_shortlist_size: int
    taxonomy_fingerprint: str
    effective_half_lives: Tuple[Tuple[str, float], ...] = ()

    def half_life_for_class(self, decay_class: str) -> float:
        table = {
            "fast": self.half_life_fast_days,
            "medium": self.half_life_medium_days,
            "slow": self.half_life_slow_days,
        }
        if decay_class not in table:
            raise ConfigurationError(f"unknown decay_class {decay_class!r}")
        return table[decay_class]

    @property
    def version(self) -> str:
        payload = {
            "demonstrated_weight": self.demonstrated_weight,
            "certified_weight": self.certified_weight,
            "declared_weight": self.declared_weight,
            "volume_k": self.volume_k,
            "allocation_weight": self.allocation_weight,
            "adjacency_discount": self.adjacency_discount,
            "min_confidence": self.min_confidence,
            "min_coverage_ratio": self.min_coverage_ratio,
            "max_shortlist_size": self.max_shortlist_size,
            "taxonomy_fingerprint": self.taxonomy_fingerprint,
            "effective_half_lives": [list(item) for item in self.effective_half_lives],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


#: (env var, field, default, lower bound, upper bound, type)
_ENV_FIELDS = (
    ("HERMES_W_DEMO", "demonstrated_weight", 0.55, 0.0, 1.0, float),
    ("HERMES_W_CERT", "certified_weight", 0.30, 0.0, 1.0, float),
    ("HERMES_W_DECL", "declared_weight", 0.15, 0.0, 1.0, float),
    ("HERMES_HALF_LIFE_FAST", "half_life_fast_days", 90.0, 1.0, 36500.0, float),
    ("HERMES_HALF_LIFE_MEDIUM", "half_life_medium_days", 365.0, 1.0, 36500.0, float),
    ("HERMES_HALF_LIFE_SLOW", "half_life_slow_days", 1095.0, 1.0, 36500.0, float),
    ("HERMES_VOLUME_K", "volume_k", 0.35, 0.0001, 10.0, float),
    ("HERMES_ALLOC_W", "allocation_weight", 0.15, 0.0, 1.0, float),
    ("HERMES_ADJACENCY_DISCOUNT", "adjacency_discount", 0.5, 0.0, 1.0, float),
    ("HERMES_MIN_COVERAGE", "min_coverage_ratio", 0.6, 0.0, 1.0, float),
    ("HERMES_MAX_SHORTLIST", "max_shortlist_size", 10, 1, 10, int),
)

REMOVED_ENV_VARS = {
    "HERMES_HALF_LIFE": "removed: it could not affect any ontology skill; "
    "use HERMES_HALF_LIFE_FAST / _MEDIUM / _SLOW",
}


def load_scoring_config(env: Optional[Mapping[str, str]] = None) -> ScoringConfig:
    source = os.environ if env is None else env
    for var, why in REMOVED_ENV_VARS.items():
        if source.get(var, "").strip():
            raise ConfigurationError(f"{var} is set but {why}")
    values: Dict[str, Any] = {}
    for var, field, default, low, high, cast in _ENV_FIELDS:
        raw = source.get(var)
        try:
            value = cast(raw) if raw not in (None, "") else default
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{var} must be a {cast.__name__}") from exc
        if not (low <= value <= high):
            raise ConfigurationError(f"{var}={value} outside allowed range [{low}, {high}]")
        values[field] = value
    partial = ScoringConfig(min_confidence=0.1, taxonomy_fingerprint=taxonomy_scoring_fingerprint(), **values)
    from dataclasses import replace

    from shared.taxonomy import load_taxonomy

    effective = tuple(
        (s.skill_id, float(s.freshness_half_life_days or partial.half_life_for_class(s.decay_class or "")))
        for s in sorted(load_taxonomy().all_skills(), key=lambda x: x.skill_id)
    )
    return replace(partial, effective_half_lives=effective)


DEFAULT_SCORING = load_scoring_config(env={})
