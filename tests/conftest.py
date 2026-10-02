import json
import os
from pathlib import Path

import pytest

# Fail-closed secrets allow fixture defaults only in test mode
os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

from identity_abstraction.gate import IdentityAbstractionGate
from shared.audit import AuditLedger
from skill_inference.engine import SkillInferenceEngine
from fitness_gap.engine import FitnessGapEngine
from identity_resolution.gateway import IdentityResolutionGateway

# Phase 6 Postgres-parity verification ONLY — inert unless an operator
# explicitly sets HERMES_TEST_POSTGRES_URL (a server/admin DSN with CREATE
# DATABASE privilege, e.g. postgresql://postgres:pw@host:5432/postgres).
# Every test that constructs HermesDB(some_tmp_path) expects a FRESH,
# isolated database — this redirects that same "fresh database per
# HermesDB() call" pattern to a real, newly-created Postgres database
# instead of a fresh SQLite file, without touching any of the ~400 call
# sites that build HermesDB(tmp_path / "x.db") across the test suite.
# Leftover per-test databases are NOT dropped here — this is a one-off
# parity-verification mechanism, not permanent CI infrastructure; an
# operator running this drops/recreates the test Postgres instance after.
_PG_TEST_URL = os.getenv("HERMES_TEST_POSTGRES_URL", "").strip()
if _PG_TEST_URL:
    import uuid

    import psycopg2

    from shared import db as _db_module

    os.environ.setdefault("HERMES_AUDIT_ANCHOR_DIR", "/tmp/hermes_pg_test_anchors")
    Path(os.environ["HERMES_AUDIT_ANCHOR_DIR"]).mkdir(parents=True, exist_ok=True)
    _original_init = _db_module.HermesDB.__init__
    # Several tests (and scripts.ingest_fixtures) open the SAME path twice and
    # expect the SAME underlying data back — SQLite's file identity gives them
    # that for free. A naive "new database every call" redirect broke that:
    # found live, when test_rank_and_resolve got an empty shortlist because its
    # second HermesDB(db_path) call silently landed on a brand new, empty
    # database instead of the one ingest_fixtures had just populated. Cache by
    # the resolved path string so the same path always maps to the same
    # Postgres database within one test process — mirroring file identity.
    _path_to_database_url: dict = {}

    def _pg_redirect_init(self, path=None, database_url=None):  # noqa: ANN001
        key = str(Path(path).resolve()) if path is not None else None
        if key is not None and key in _path_to_database_url:
            _original_init(self, path=None, database_url=_path_to_database_url[key])
            return
        admin = psycopg2.connect(_PG_TEST_URL)
        admin.autocommit = True
        dbname = f"hermes_test_{uuid.uuid4().hex[:16]}"
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {dbname}")
        admin.close()
        base = _PG_TEST_URL.rsplit("/", 1)[0]
        url = f"{base}/{dbname}"
        if key is not None:
            _path_to_database_url[key] = url
        _original_init(self, path=None, database_url=url)

    _db_module.HermesDB.__init__ = _pg_redirect_init


FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "pilot_population.json"


@pytest.fixture
def fixture_data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def gate():
    return IdentityAbstractionGate("hermes-test-mode-secret-not-for-prod")


@pytest.fixture
def audit():
    return AuditLedger()


@pytest.fixture
def inference():
    return SkillInferenceEngine()


@pytest.fixture
def fitness(audit):
    return FitnessGapEngine(audit=audit, demand_weights={
        "container_orchestration": 0.9,
        "azure_networking": 0.85,
        "infrastructure_as_code": 0.55,
    })


@pytest.fixture
def resolution(gate, audit):
    return IdentityResolutionGateway(gate, audit=audit)
