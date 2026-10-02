"""Natural-language work-request -> governed skill proposal (Phase 3/4).

The LLM's job ends at producing candidate skill labels. Mapping a label onto a
governed skill_id reuses the exact-match-only resolver the real-data pipeline
already uses (src/phase8/aliases.ontology_lookup_map) — never a fuzzy match,
and never a new taxonomy entry. A label that doesn't match exactly goes into
``ambiguities`` for a human to resolve, the same governance path pending
baseline-workbook labels already go through (docs/phase8/BLOCKED.md).

This module never calls the scoring engine and never writes evidence. Its only
output is a WorkRequirementProposal a manager can edit or discard before it
reaches the existing, unchanged /api/fitness/rank request body.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set

from ai.provider import LLMProvider
from ai.schemas import SkillProposal, WorkRequirementProposal
from phase8.aliases import ontology_lookup_map
from phase8.workbook import normalize_label
from shared.taxonomy import SkillsTaxonomy, load_taxonomy

SYSTEM_PROMPT = (
    "You translate a manager's plain-language description of work into a list of "
    "skills. Reply with JSON only, no prose, no markdown fences, matching exactly: "
    '{"skills": [{"skill": "<name>", "importance": "required"|"preferred"}]}. '
    "Prefer names from the provided governed skill list when the work clearly needs "
    "one of them. You may also propose a skill not on the list if the work clearly "
    "needs it — it will be reviewed by a human before use, never acted on directly."
)


class LLMExtractionError(Exception):
    """Raised when the model's output cannot be parsed/validated. Callers must
    fail safely — e.g. fall back to manual skill entry — never guess."""


def _build_prompt(description: str, taxonomy: SkillsTaxonomy) -> str:
    skill_names = sorted({s.name for s in taxonomy.all_skills()})
    return (
        f"Governed skills: {', '.join(skill_names)}\n\n"
        f"Work description: {description}\n\n"
        "JSON:"
    )


def _extract_json(raw: str) -> Dict[str, Any]:
    """Models routinely wrap JSON in markdown fences or add a stray sentence.
    Take the first {...} block rather than requiring a perfectly bare response."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise LLMExtractionError(f"no JSON object found in model output: {raw!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMExtractionError(f"model output was not valid JSON: {exc}") from exc


def extract_work_requirement(
    provider: LLMProvider,
    description: str,
    taxonomy: Optional[SkillsTaxonomy] = None,
) -> WorkRequirementProposal:
    """Raises LLMUnavailableError if the provider itself fails, or
    LLMExtractionError if it answered but the answer couldn't be validated.
    Both are caller-visible so the API layer can return a clean "assist
    unavailable, continue manually" response rather than a 500.
    """
    tax = taxonomy or load_taxonomy()
    prompt = _build_prompt(description, tax)
    raw = provider.generate(prompt, system=SYSTEM_PROMPT)  # LLMUnavailableError propagates
    payload = _extract_json(raw)

    raw_skills = payload.get("skills")
    if not isinstance(raw_skills, list):
        raise LLMExtractionError(f"expected a 'skills' list, got: {payload!r}")

    lookup = ontology_lookup_map(tax)
    proposals: List[SkillProposal] = []
    ambiguities: List[str] = []
    seen_skill_ids: Set[str] = set()
    for item in raw_skills:
        if not isinstance(item, dict):
            continue
        label = str(item.get("skill") or "").strip()
        importance = item.get("importance") if item.get("importance") in ("required", "preferred") else "required"
        if not label:
            continue
        skill_id = lookup.get(normalize_label(label))
        if skill_id is None:
            ambiguities.append(label)
            continue
        if skill_id in seen_skill_ids:
            continue
        seen_skill_ids.add(skill_id)
        proposals.append(SkillProposal(skill=label, importance=importance, mapped_skill_id=skill_id))

    return WorkRequirementProposal(skills=proposals, ambiguities=ambiguities)
