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
