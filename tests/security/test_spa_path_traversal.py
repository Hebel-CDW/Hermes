"""C-1 regression: the unauthenticated SPA fallback must not serve files outside web/dist.

The Phase 1 audit reproduced an unauthenticated arbitrary file read via
``GET /%2e%2e/%2e%2e/<path>`` which exfiltrated ``data/hermes_phase8.db``
(identity_vault for 310 real people), ``config/client_names.txt``, and the raw
2025 workbook. These tests pin the containment fix.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

from api.main import WEB_DIST, app  # noqa: E402

needs_dist = pytest.mark.skipif(
    not WEB_DIST.is_dir(), reason="SPA fallback is only registered when web/dist exists"
)

# Paths that must never be reachable, expressed the way an attacker would send them.
TRAVERSAL_PROBES = [
    "/../PROJECT_BIBLE.md",
    "/%2e%2e/%2e%2e/PROJECT_BIBLE.md",
    "/..%2f..%2fPROJECT_BIBLE.md",
    "/%2e%2e/%2e%2e/config/client_names.txt",
    "/%2e%2e/%2e%2e/data/hermes.db",
    "/%2e%2e/%2e%2e/data/hermes_phase8.db",
    "/%2e%2e/%2e%2e/data/source/Skill_Matrix_2025.xlsx",
    "/%2e%2e/%2e%2e/.env.example",
    "/%2e%2e/%2e%2e/%2e%2e/.zshrc",
    "/%2e%2e/%2e%2e/api/main.py",
]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@needs_dist
@pytest.mark.parametrize("probe", TRAVERSAL_PROBES)
def test_traversal_never_returns_repository_file(client, probe):
    """Traversal must fall through to index.html (or 404) — never the target file."""
    resp = client.get(probe)
    assert resp.status_code in (200, 404), f"unexpected status for {probe}"
    if resp.status_code == 404:
        return
    # A 200 is only acceptable when it is the SPA shell, not the requested file.
    index_bytes = (WEB_DIST / "index.html").read_bytes()
    assert resp.content == index_bytes, (
        f"{probe} leaked a non-index file ({len(resp.content)} bytes) — path traversal regression"
    )


@needs_dist
def test_sensitive_repo_content_never_appears_in_response(client):
    """Content-level assertion: known markers from protected files must not be served."""
    markers = {
        "/%2e%2e/%2e%2e/PROJECT_BIBLE.md": b"PROJECT BIBLE",
        "/%2e%2e/%2e%2e/api/main.py": b"IdentityResolutionGateway",
        "/%2e%2e/%2e%2e/data/hermes_phase8.db": b"identity_vault",
    }
    for probe, marker in markers.items():
        resp = client.get(probe)
        assert marker not in resp.content, f"{probe} leaked content marker {marker!r}"


@needs_dist
def test_legitimate_asset_is_still_served(client):
    """The fix must not break real static serving."""
    assets = WEB_DIST / "assets"
    files = sorted(p for p in assets.iterdir() if p.is_file()) if assets.is_dir() else []
    if not files:
        pytest.skip("no built assets to serve")
    target = files[0]
    resp = client.get(f"/assets/{target.name}")
    assert resp.status_code == 200
    assert resp.content == target.read_bytes()


@needs_dist
def test_spa_route_still_returns_index(client):
    """Client-side routes still resolve to the SPA shell."""
    resp = client.get("/staff")
    assert resp.status_code == 200
    assert resp.content == (WEB_DIST / "index.html").read_bytes()


@needs_dist
def test_api_and_health_are_not_swallowed_by_fallback(client):
    """/api/* and /health must not be captured by the catch-all."""
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/health").status_code == 200
