"""FastAPI local runtime for Hermes judgment components + web UI (server-side RBAC).

Authorization model (prototype):
* Authentication: HS256 token carrying only ``sub``; roles and coded identity are
  derived server-side (``shared.auth.build_principal``).
* Roles: ``employee``, ``manager``, ``admin`` — enforced per route in each router. The
  frontend hides nothing that the server does not also refuse.
* Request ownership: staffing requests belong to the manager who created them;
  rank, resolve and decide all verify ownership in the service layer.

This module is intentionally thin: app creation, middleware, lifecycle, the global
exception handler, router registration, and the built-SPA fallback. Every route
lives in ``api/routers/*`` — see api/ROUTER_SPLIT.md for the ownership map.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.dependencies import get_service, reset_service_for_tests  # noqa: F401  (re-exported)
from api.routers import (
    assist,
    auth,
    candidates,
    certificates,
    data_quality,
    evidence,
    health,
    people,
    requests,
    skills,
    team,
)
from shared.errors import HermesError
from shared.secrets import require_identity_map_secret, require_jwt_secret


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Fail closed on secrets outside test mode.
    require_jwt_secret()
    require_identity_map_secret()
    yield


app = FastAPI(title="Hermes Local API", version="0.3.0", lifespan=_lifespan)

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def _cors_origins() -> list:
    """Allowed browser origins; hosted deployments set HERMES_CORS_ORIGINS (comma-separated)."""
    raw = os.getenv("HERMES_CORS_ORIGINS", "").strip()
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip() and o.strip() != "*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers.setdefault("Content-Security-Policy", _CSP)
    if os.getenv("HERMES_ENV", "").strip().lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(HermesError)
def _hermes_error_handler(_request: Request, exc: HermesError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={"detail": str(exc), "error": exc.code})


WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

for _router_module in (
    health,
    auth,
    skills,
    people,
    requests,
    candidates,
    evidence,
    data_quality,
    certificates,
    team,
    assist,
):
    app.include_router(_router_module.router)


# Serve built SPA when present (after API routes so /api wins)
if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    def _safe_static_candidate(full_path: str) -> Optional[Path]:
        """Resolve full_path under WEB_DIST, or None if it escapes the directory.

        Guardrail: this route is unauthenticated, so it must never be able to read
        a file outside web/dist. Traversal attempts (``../``, percent-encoded
        variants, absolute paths, symlinks) all resolve outside WEB_DIST and are
        rejected here instead of being served.
        """
        if not full_path:
            return None
        root = WEB_DIST.resolve()
        candidate = (root / full_path).resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate if candidate.is_file() else None

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api") or full_path == "health":
            raise HTTPException(status_code=404)
        candidate = _safe_static_candidate(full_path)
        if candidate is not None:
            return FileResponse(candidate)
        index = WEB_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="frontend not built")
