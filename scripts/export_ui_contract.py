"""Capture real Hermes API payloads for the web UI contract tests (synthetic data only).

Builds a throw-away synthetic database from data/fixtures/pilot_population.json, drives
the real FastAPI app in-process, and writes the responses the React views consume to
web/src/test/fixtures/api-contract.json. The UI tests render these payloads and assert
the screen shows exactly the API values (candidate ids, fitness, contributions,
exclusion reasons, request ids, identity).

Identity resolution output (display names) is deliberately NOT captured.

``real_*`` keys come from an INVENTED workbook (scripts/phase8/synthetic_workbook.py) run
through the real-data ingestion path with a throw-away strong secret, so the UI can be
tested against genuine real-mode payloads without touching confidential data.

    HERMES_TEST_MODE=1 python -m scripts.export_ui_contract
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

os.environ.setdefault("HERMES_TEST_MODE", "1")

from fastapi.testclient import TestClient  # noqa: E402

import api.main as api_main  # noqa: E402
from scripts.demo_svp import REQUIRED_SKILLS  # noqa: E402
from scripts.ingest_fixtures import ingest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "pilot_population.json"
OUT = ROOT / "web" / "src" / "test" / "fixtures" / "api-contract.json"
REQUEST_ID = "ui-contract-1"
RANK_BODY = {"request_id": REQUEST_ID, "required_skills": REQUIRED_SKILLS, "shortlist_size": 3, "min_coverage_ratio": 0.5}


def capture() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "ui-contract.db"
        ingest(FIXTURE, db, write_samples=False)
        previous = os.environ.get("HERMES_DB_PATH")
        os.environ["HERMES_DB_PATH"] = str(db)
        api_main.reset_service_for_tests(None)
        try:
            with TestClient(api_main.app) as client:

                def headers(sub: str) -> Dict[str, str]:
                    token = client.post("/api/auth/token", json={"sub": sub}).json()["access_token"]
                    return {"Authorization": f"Bearer {token}"}

                def get(path: str, sub: str) -> Any:
                    res = client.get(path, headers=headers(sub))
                    res.raise_for_status()
                    return res.json()

                rank = client.post("/api/fitness/rank", json=RANK_BODY, headers=headers("demo-manager"))
                rank.raise_for_status()
                return {
                    "rank_body": RANK_BODY,
                    "rank_response": rank.json(),
                    "session_manager": get("/api/session", "demo-manager"),
                    "session_employee": get("/api/session", "demo-employee"),
                    "overview": get("/api/overview", "demo-manager"),
                    "workforce": get("/api/workforce", "demo-manager"),
                    "skills": get("/api/skills", "demo-manager"),
                    "skill_detail": get("/api/skills/container_orchestration", "demo-manager"),
                    "roles": get("/api/roles", "demo-manager"),
                    "dashboard": get("/api/dashboard", "demo-manager"),
                    "requests": get("/api/staffing/requests", "demo-manager"),
                    "request_detail": get(f"/api/staffing/requests/{REQUEST_ID}", "demo-manager"),
                    "me_employee": get("/api/me", "demo-employee"),
                    "data_quality": get("/api/data-quality", "demo-manager"),
                    "excel_sunset": get("/api/excel-sunset", "demo-manager"),
                    "baseline_matrix": get("/api/baseline/matrix", "demo-manager"),
                    "taxonomy_pending": get("/api/taxonomy/pending", "demo-manager"),
                }
        finally:
            api_main.reset_service_for_tests(None)
            if previous is None:
                os.environ.pop("HERMES_DB_PATH", None)
            else:
                os.environ["HERMES_DB_PATH"] = previous


def capture_real_mode() -> Dict[str, Any]:
    """Real-data-mode payloads from an invented workbook (never the confidential one)."""
    import importlib.util
    import secrets

    import shared.models as models
    from scripts.phase8.synthetic_workbook import CLIENT_LABEL, build

    spec = importlib.util.spec_from_file_location("_contract_ingest_real", ROOT / "scripts" / "phase8" / "ingest_real.py")
    ingest_real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingest_real)  # type: ignore[union-attr]

    keys = ("HERMES_TEST_MODE", "IDENTITY_MAP_SECRET", "HERMES_JWT_SECRET", "HERMES_DB_PATH", "HERMES_ENV")
    saved = {k: os.environ.get(k) for k in keys}
    saved_blocklist = models.CLIENT_NAME_BLOCKLIST
    try:
        os.environ.pop("HERMES_TEST_MODE", None)
        os.environ["IDENTITY_MAP_SECRET"] = secrets.token_urlsafe(48)
        os.environ["HERMES_JWT_SECRET"] = secrets.token_urlsafe(48)
        os.environ["HERMES_ENV"] = "local"
        models.CLIENT_NAME_BLOCKLIST = frozenset({CLIENT_LABEL})
        with tempfile.TemporaryDirectory() as tmp:
            workbook = build(Path(tmp) / "Fake_Skill_Matrix.xlsx")
            db = Path(tmp) / "real.db"
            ingest_real.run(workbook, db, Path(tmp) / "reports")
            os.environ["HERMES_DB_PATH"] = str(db)
            api_main.reset_service_for_tests(None)
            with TestClient(api_main.app) as client:
                token = client.post("/api/auth/token", json={"sub": "demo-manager"}).json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                def get(path: str) -> Any:
                    res = client.get(path, headers=headers)
                    res.raise_for_status()
                    return res.json()

                return {
                    "real_session_manager": get("/api/session"),
                    "real_overview": get("/api/overview"),
                    "real_workforce": get("/api/workforce"),
                    "real_dashboard": get("/api/dashboard"),
                    "real_skills": get("/api/skills"),
                    "real_data_quality": get("/api/data-quality"),
                    "real_excel_sunset": get("/api/excel-sunset"),
                    "real_baseline_matrix": get("/api/baseline/matrix"),
                }
    finally:
        api_main.reset_service_for_tests(None)
        models.CLIENT_NAME_BLOCKLIST = saved_blocklist
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    payload = {**capture(), **capture_real_mode()}
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
