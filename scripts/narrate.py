"""Narrate-only formatter: prints engine fields, never invents candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


def narrate_staffing(result: Mapping[str, Any], resolved: Optional[List[Dict[str, Any]]] = None) -> str:
    lines = [
        "Hermes recommendation (manager approval required — Hermes does not assign work):",
    ]
    resolved_map = {}
    if resolved:
        for item in resolved:
            resolved_map[item["coded_identity"]] = item.get("display_name", item["coded_identity"])

    for cand in result.get("candidates", []):
        name = resolved_map.get(cand["coded_identity"], cand["coded_identity"])
        lines.append(
            f"- #{cand['rank']} {name} ({cand['coded_identity']}): score {cand['fitness_score']}"
        )
        for skill, reason in (cand.get("per_skill_reasoning") or {}).items():
            lines.append(f"    {skill}: {reason}")
        evidence = ", ".join(cand.get("evidence_ids") or [])
        if evidence:
            lines.append(f"    evidence: {evidence}")
    if not result.get("candidates"):
        lines.append("No grounded candidates available from the fitness engine.")
    return "\n".join(lines)


def narrate_gaps(result: Mapping[str, Any]) -> str:
    lines = [
        f"Learning path gaps for {result.get('coded_identity')} vs role {result.get('role_id')}:",
    ]
    for gap in result.get("gaps", []):
        lines.append(
            f"- {gap['skill_id']}: {gap['reasoning']} (demand impact {gap['demand_impact']})"
        )
    if not result.get("gaps"):
        lines.append("No grounded gaps returned by the engine.")
    return "\n".join(lines)


def assert_grounded_staffing(result: Mapping[str, Any]) -> None:
    for cand in result.get("candidates", []):
        if not cand.get("evidence_ids"):
            raise AssertionError("ungrounded candidate without evidence_ids")
        if not cand.get("per_skill_reasoning"):
            raise AssertionError("ungrounded candidate without reasoning")
