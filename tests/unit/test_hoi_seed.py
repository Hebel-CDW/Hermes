"""The HOI demo seed: one synthetic Azure-certified engineer; eligibility and scoring rules unchanged."""

import os

import pytest

from hoi.scenarios import Scenarios
from hoi.service import HoiService
from scripts.seed_demo_org import seed as seed_org
from scripts.seed_hoi_demo import seed as seed_hoi
from shared.auth import AuthPrincipal
from shared.db import HermesDB
from shared.service import HermesService

M = AuthPrincipal("demo-manager", ("manager",), None)
A = AuthPrincipal("demo-admin", ("admin",), None)


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOI_STORAGE_DIR", str(tmp_path / "store"))
    db_path = tmp_path / "s.db"
    seed_org(db_path)
    out = seed_hoi(db_path, "matched")
    svc = HermesService(db=HermesDB(db_path), mapping_secret=os.getenv("IDENTITY_MAP_SECRET"))
    return svc, HoiService(svc), out


def test_exactly_one_eligible_cloud_candidate_and_ranking_unchanged(seeded):
    svc, hoi, out = seeded
    oid = out["opportunity_id"]
    cloud = hoi.shortlist(M, oid)["requirements"][0]
    assert cloud["role_name"] == "Senior Cloud Engineer"
    eligible = [c for c in cloud["candidates"] if c["eligibility"] == "eligible"]
    assert len(eligible) == 1 and len(cloud["candidates"]) >= 5
    # the certified engineer is not pushed up the ranking: they sit where the unchanged scoring formula puts them
    assert eligible[0]["rank"] > 1
    assert all(k["status"] == "pass" for k in eligible[0]["checks"] if k["check"].startswith("certification"))
    # every non-eligible candidate fails for a stated reason, and certificate checks pass only with certified evidence
    with svc.db.session() as conn:
        holders = {r["coded_identity"] for r in conn.execute(
            "SELECT coded_identity FROM evidence_staging WHERE evidence_type='certified' AND source_ref='AZ-104'")}
    for c in cloud["candidates"]:
        cert = next(k for k in c["checks"] if k["check"].startswith("certification"))
        assert (cert["status"] == "pass") == (c["coded_identity"] in holders)
        if c["eligibility"] != "eligible":
            assert any(k["status"] == "fail" for k in c["checks"]), c["coded_identity"]
    # certificate evidence is a CERTIFIED record (the cert_staging table is real-workbook-only and must stay empty here)
    with svc.db.session() as conn:
        staged = conn.execute("SELECT COUNT(*) AS n FROM cert_staging").fetchone()["n"]
        cert = conn.execute("SELECT COUNT(*) AS n FROM evidence_staging WHERE evidence_type='certified' AND source_ref='AZ-104' AND coded_identity=?",
                            (eligible[0]["coded_identity"],)).fetchone()["n"]
    assert staged == 0 and cert == 1


def test_certificate_matching_is_whole_token_not_fuzzy():
    from hoi.service import cert_held
    assert cert_held("Azure Administrator Associate (AZ-104)", ["AZ-104"])
    assert cert_held("AZ-104", ["az-104"]) and cert_held("Azure Administrator Associate", ["Azure Administrator Associate"])
    assert not cert_held("Azure Administrator Associate", ["AZ-104"])  # a name alone does not imply a code
    assert not cert_held("AZ-1045", ["AZ-104"]) and not cert_held("AZ-10", ["AZ-104"])
    assert not cert_held("Azure Administrator Associate (AZ-104)", [])


def test_hybrid_uses_the_certified_engineer_and_requires_hr(seeded):
    svc, hoi, out = seeded
    oid = out["opportunity_id"]
    res = Scenarios(hoi).compare(M, oid, {"cost_policy_id": "POL-2026", "rate_card_id": "RATE-01"})
    kinds = {s["kind"]: s for s in res["scenarios"]}
    assert set(kinds) == {"internal", "external", "hybrid"}
    hy = kinds["hybrid"]
    assert hy["uses_individual_cost"] is True and hy["approvals"]["required"] == ["delivery", "finance", "hr"]
    assert hy["unresolved_constraints"] == [] and hy["no_automatic_assignment"] is True
