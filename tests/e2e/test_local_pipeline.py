from pathlib import Path

from scripts.dashboard_export import export
from scripts.ingest_fixtures import ingest
from scripts.narrate import assert_grounded_staffing, narrate_staffing
from shared.db import HermesDB
from shared.models import ProficiencyLevel, StaffingRequest, TargetRoleProfile
from shared.service import HermesService


def test_ingest_rank_resolve_dashboard(tmp_path):
    db_path = tmp_path / "e2e.db"
    report = ingest(Path("data/fixtures/pilot_population.json"), db_path)
    assert report["coverage"]["coverage_pct"] >= 80

    svc = HermesService(db=HermesDB(db_path), mapping_secret="fixture-secret")
    result = svc.rank(
        StaffingRequest(
            request_id="e2e-k8s",
            requester_id="mgr-e2e",
            required_skills={"container_orchestration": ProficiencyLevel.PROFICIENT},
        )
    )
    payload = result.model_dump(mode="json")
    assert_grounded_staffing(payload)
    resolved = svc.resolve("e2e-k8s", "mgr-e2e")
    text = narrate_staffing(payload, resolved)
    assert "manager approval required" in text
    assert resolved[0]["display_name"] == "Alex Rivera"

    # learning path for E1003
    token = svc.gate.tokenize("E1003")
    role = svc.db.get_role("senior_cloud_engineer")
    gaps = svc.gaps(
        token,
        TargetRoleProfile(
            role_id=role["role_id"],
            role_name=role["role_name"],
            required_skills={k: ProficiencyLevel(v) for k, v in role["required_skills"].items()},
        ),
    )
    assert gaps.gaps

    html = export(db_path, tmp_path / "reports")
    content = html.read_text(encoding="utf-8")
    assert "Alex Rivera" not in content
    assert "coded identities only" in content.lower() or "Coded" in content
