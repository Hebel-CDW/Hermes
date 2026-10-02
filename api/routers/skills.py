"""Skill catalog, role profiles, and taxonomy governance. Extracted verbatim from main.py."""

from __future__ import annotations

import json
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.dependencies import get_service, require_api_key, require_roles
from api.validation import SKILL_IDS
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, EMPLOYEE, MANAGER
from shared.service import HermesService
from shared.taxonomy import load_taxonomy

router = APIRouter()


@router.get("/api/roles")
def list_roles(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    with svc.db.session() as conn:
        rows = conn.execute(
            "SELECT role_id, role_name, required_skills_json, critical_skills_json, min_coverage_ratio "
            "FROM role_profiles"
        ).fetchall()
    roles = [
        {
            "role_id": r["role_id"],
            "role_name": r["role_name"],
            "required_skills": json.loads(r["required_skills_json"]),
            "critical_skills": json.loads(r["critical_skills_json"] or "[]"),
            "min_coverage_ratio": float(r["min_coverage_ratio"] or 0.6),
        }
        for r in rows
    ]
    return {"roles": roles}


@router.get("/api/skills")
def list_skills(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(EMPLOYEE, MANAGER, ADMIN)),
) -> Dict[str, Any]:
    tax = load_taxonomy()
    skills = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "domain_id": d.domain_id,
            "domain_name": d.name,
            "relations": list(getattr(s, "relations", []) or []),
        }
        for d in tax.domains
        for s in d.skills
    ]
    return {"skills": skills}


@router.get("/api/skills/{skill_id}")
def skill_view(
    skill_id: str = PathParam(..., min_length=1, max_length=128),
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from shared import read_models

    summary = read_models.skill_summary(svc.db, svc.inference.taxonomy, svc.inference.config, skill_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"unknown skill id: {skill_id}")
    return summary


@router.get("/api/taxonomy/pending")
def taxonomy_pending(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(MANAGER, ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    del principal
    return svc.taxonomy_pending()


class TaxonomyResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    skill_id: Optional[str] = Field(None, min_length=1, max_length=128)

    @field_validator("skill_id")
    @classmethod
    def check_skill(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SKILL_IDS:
            raise ValueError(f"unknown skill id: {v}")
        return v


@router.post("/api/taxonomy/aliases/{alias_label}/resolve")
def taxonomy_resolve(
    alias_label: str,
    body: TaxonomyResolveBody,
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(ADMIN)),
    svc: HermesService = Depends(get_service),
) -> Dict[str, str]:
    return svc.resolve_taxonomy_alias(principal.sub, alias_label, body.decision, skill_id=body.skill_id)
