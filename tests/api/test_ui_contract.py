"""The web UI contract fixture must match the live API shape and stay free of sensitive data.

web/src/test/fixtures/api-contract.json is rendered by the React tests to prove the UI shows
exactly the API values. If an endpoint's response shape changes, this test fails until the
fixture is regenerated with ``python -m scripts.export_ui_contract``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.export_ui_contract import OUT, capture, capture_real_mode

VOLATILE_KEYS = {"computed_at", "created_at", "decided_at", "occurred_at", "valid_from"}


def _shape(value: Any) -> Any:
    """Structural signature: dict keys (recursively) and scalar types; lists by their first element."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return "str"


def test_committed_fixture_matches_live_api_shape():
    committed = json.loads(OUT.read_text(encoding="utf-8"))
    live = {**capture(), **capture_real_mode()}
    assert set(committed) == set(live)
    for key in live:
        assert _shape(committed[key]) == _shape(live[key]), f"UI contract drift in {key}; regenerate the fixture"


def test_fixture_ranking_values_match_live_api():
    committed = json.loads(OUT.read_text(encoding="utf-8"))["request_detail"]["result"]
    live = capture()["request_detail"]["result"]
    assert [c["coded_identity"] for c in committed["candidates"]] == [c["coded_identity"] for c in live["candidates"]]
    assert committed["excluded_candidates"] == live["excluded_candidates"]
    assert committed["scoring_config_version"] == live["scoring_config_version"]


def test_fixture_contains_no_secrets_names_or_resolution_output():
    text = OUT.read_text(encoding="utf-8")
    for forbidden in ("display_name", "IDENTITY_MAP_SECRET", "HERMES_JWT_SECRET", "identity_vault", "hermes_phase8", "access_token"):
        assert forbidden not in text
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", text), "fixture must not embed a JWT"
    from scripts.phase8.synthetic_workbook import CLIENT_LABEL, FAKE_PEOPLE

    for person in FAKE_PEOPLE:
        assert person not in text, "invented names must not reach API payloads either"
    assert CLIENT_LABEL not in text
    coded = set(re.findall(r"EMP-[0-9a-f]{8}", text))
    assert coded, "fixture should reference coded identities"


def test_real_mode_fixture_reports_no_fake_scoring():
    committed = json.loads(OUT.read_text(encoding="utf-8"))
    dq = committed["real_data_quality"]
    assert dq["data_classification"] == "real"
    assert dq["pipeline"]["scored"] == 0
    assert committed["real_dashboard"]["skill_distribution"] == []
    assert all(i["skill_count"] == 0 for i in committed["real_workforce"]["identities"])
