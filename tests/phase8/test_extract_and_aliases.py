import csv
import os
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from phase8.aliases import SkillAliasResolver, ontology_lookup_map
from shared.db import HermesDB
from shared.taxonomy import load_taxonomy


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "phase8" / "candidate_skills.csv"
SOURCE = ROOT / "data" / "source" / "Skill_Matrix_2025.xlsx"


@pytest.mark.skipif(not SOURCE.exists(), reason="source workbook not present")
def test_candidate_skills_csv_membership_invariant():
    assert CSV_PATH.exists()
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    membership = {}
    for row in rows:
        for m in row["member_labels"].split("|"):
            if not m:
                continue
            membership[m] = membership.get(m, 0) + 1
    assert membership
    assert all(v == 1 for v in membership.values())
    excluded = [r for r in rows if r["status"] == "excluded"]
    assert any(r["exclusion_reason"] == "soft_skill_excluded" for r in excluded)
    assert any("culture" in r["exclusion_reason"] for r in excluded) or any(
        "culture fit" in r["member_labels"].lower() for r in excluded
    )


def test_alias_pending_not_fuzzy(tmp_path):
    db = HermesDB(tmp_path / "alias.db")
    tax = load_taxonomy()
    resolver = SkillAliasResolver(db, ontology_lookup_map(tax))
    res = resolver.resolve("totally_unknown_skill_xyz")
    assert res.mapped_by == "pending"
    assert res.skill_id is None
    assert db.count_pending_aliases() >= 1


def test_alias_exact_ontology_match(tmp_path):
    db = HermesDB(tmp_path / "alias2.db")
    tax = load_taxonomy()
    resolver = SkillAliasResolver(db, ontology_lookup_map(tax))
    res = resolver.resolve("Container Orchestration")
    assert res.mapped_by == "auto"
    assert res.skill_id == "container_orchestration"
