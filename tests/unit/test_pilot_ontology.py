"""Pilot ontology: 40–80 canonical skills, no client labels, existing five preserved."""

from __future__ import annotations

from phase8.aliases import ontology_lookup_map
from phase8.workbook import normalize_label
from shared.excel_sunset import load_alias_proposals
from shared.taxonomy import load_taxonomy, validate_taxonomy_completeness


CORE = {
    "container_orchestration",
    "azure_networking",
    "azure_compute",
    "incident_management",
    "infrastructure_as_code",
}


def test_pilot_ontology_covers_staffing_without_client_columns():
    tax = load_taxonomy()
    ids = {s.skill_id for s in tax.all_skills()}
    assert CORE <= ids
    assert 40 <= len(ids) <= 80
    assert validate_taxonomy_completeness(tax) == []
    for skill in tax.all_skills():
        blob = f"{skill.skill_id} {skill.name}".lower()
        assert "llc" not in blob
        assert "inc." not in blob
        assert skill.ticket_keywords


def test_alias_proposals_point_only_at_governed_skills():
    tax = load_taxonomy()
    ids = {s.skill_id for s in tax.all_skills()}
    proposals = load_alias_proposals()
    assert len(proposals) >= 20
    for alias, skill_id in proposals.items():
        assert skill_id in ids, f"{alias} -> {skill_id}"
        assert normalize_label(alias)
    lookup = ontology_lookup_map(tax)
    assert lookup[normalize_label("Container Orchestration")] == "container_orchestration"
