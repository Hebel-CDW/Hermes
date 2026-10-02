"""Request-schema validation shared across routers.

``SKILL_IDS``, the two id patterns, and the two validator functions are used by
Pydantic request bodies in several routers (skills, people, requests,
candidates, evidence, certificates, team) — none of them owns these, so they
live here rather than being duplicated or given an arbitrary single owner.
Extracted verbatim from ``api/main.py``; no validation behavior changed.
"""

from __future__ import annotations

from typing import Dict, List

from shared.taxonomy import load_taxonomy

SKILL_IDS = frozenset(s.skill_id for s in load_taxonomy().all_skills())
REQUEST_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
CODED_ID_PATTERN = r"^EMP-[0-9a-f]{8}$"


def validate_levels(v: Dict[str, int]) -> Dict[str, int]:
    """Reject empty maps, unknown skills, and levels outside 1-5 with 422."""
    if not v:
        raise ValueError("required_skills must not be empty")
    unknown = sorted(k for k in v if k not in SKILL_IDS)
    if unknown:
        raise ValueError(f"unknown skill ids (not in the governed ontology): {unknown}")
    bad = {
        k: lvl
        for k, lvl in v.items()
        if isinstance(lvl, bool) or not isinstance(lvl, int) or not 1 <= lvl <= 5
    }
    if bad:
        raise ValueError(f"proficiency levels must be integers 1-5; got {bad}")
    return v


def validate_skill_list(v: List[str]) -> List[str]:
    unknown = sorted(k for k in v if k not in SKILL_IDS)
    if unknown:
        raise ValueError(f"unknown skill ids (not in the governed ontology): {unknown}")
    return v
