"""Hermes Opportunity Intelligence API. Thin: validation and role gates here, logic in src/hoi."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_llm_provider, get_service, require_api_key, require_roles
from hoi import documents as hoi_docs
from hoi.costing import CALC_VERSION
from hoi.market import MarketStore, parse_csv
from hoi.scenarios import Scenarios
from hoi.service import CONTRACT_TYPES, HoiService, need_roles
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, FINANCE, HR, MANAGER, SALES
from shared.rate_limit import PersistentRateLimiter
from shared.service import HermesService

router = APIRouter()

#: Request-body ceilings, enforced from the Content-Length header BEFORE the body is read into memory (FastAPI otherwise
#: buffers and parses the whole body first). First match wins. A write without Content-Length is refused (411) so the
#: limit cannot be sidestepped with chunked transfer encoding.
_BODY_LIMITS = (
    (re.compile(r"^/api/opportunities/[^/]+/documents$"), 15_000_000),  # 10 MB file as base64 JSON
    (re.compile(r"^/api/market/benchmarks/import$"), 2_100_000),
    (re.compile(r"^/api/(opportunities|finance|market)(/|$)"), 3_000_000),
)


async def body_limit(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        for rx, limit in _BODY_LIMITS:
            if rx.match(request.url.path):
                length = request.headers.get("content-length")
                if length is None:
                    return JSONResponse(status_code=411, content={"detail": "Content-Length is required", "error": "length_required"})
                if not length.isdigit() or int(length) > limit:
                    return JSONResponse(status_code=413, content={"detail": f"request body exceeds {limit // 1000} kB", "error": "payload_too_large"})
                break
    return await call_next(request)


ANY_HOI = (ADMIN, SALES, MANAGER, FINANCE, HR)
OID = r"^OPP-\d{4}-[0-9A-F]{6}$"


def hoi_for(svc: HermesService) -> HoiService:
    h = getattr(svc, "_hoi", None)
    if h is None:
        h = svc._hoi = HoiService(svc)
        h._scen = Scenarios(h)
        h.limiter = PersistentRateLimiter(max_calls=120, window_seconds=60.0, name="hoi")  # per service, so test swaps reset it
    return h


def ctx(
    _: None = Depends(require_api_key),
    principal: AuthPrincipal = Depends(require_roles(*ANY_HOI)),
    svc: HermesService = Depends(get_service),
):
    h = hoi_for(svc)
    if not h.limiter.allow(principal.sub, svc.db):
        raise HTTPException(status_code=429, detail="too many requests, slow down a little")
    return principal, h


Ctx = Depends(ctx)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OppBody(Strict):
    client_alias: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=160)
    bid_deadline: Optional[str] = None
    geography: Optional[str] = Field(None, max_length=80)
    currency: str = Field(..., min_length=3, max_length=3)
    contract_type: Literal["time_and_materials", "fixed_fee", "managed_service", "blended"]
    duration_months: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_synthetic: bool = False


class MemberBody(Strict):
    sub: str = Field(..., min_length=1, max_length=64)
    member_role: Literal["sales", "manager", "finance", "hr"]


class DocBody(Strict):
    doc_type: Literal["rfp", "sow", "jd"]
    filename: str = Field(..., min_length=1, max_length=200)
    content_b64: str = Field(..., min_length=4, max_length=14_500_000)


class ExtractBody(Strict):
    document_ids: Optional[List[str]] = Field(None, max_length=50)
    use_llm: bool = False


class SkillIn(Strict):
    text: str = Field("", max_length=160)
    skill_id: Optional[str] = Field(None, max_length=64)
    level: Optional[int] = None
    criticality: Literal["must", "preferred"] = "must"
    source: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    origin: str = "extracted"
    dismissed: bool = False
    taxonomy_status: Optional[str] = None
    skill_name: Optional[str] = None


class RoleIn(Strict):
    requirement_id: Optional[str] = None
    role_name: str = Field(..., max_length=160)
    headcount: Optional[int] = None
    fte: Optional[str] = Field(None, max_length=8)
    location: Optional[str] = Field(None, max_length=120)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    skills: List[SkillIn] = Field(default_factory=list, max_length=60)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    position: Optional[int] = None
    fields: Optional[Dict[str, Any]] = None
    origin: Optional[str] = None


class ReqUpdate(Strict):
    roles: List[RoleIn] = Field(..., max_length=50)


class VersionBody(Strict):
    version_id: str = Field(..., max_length=64)


class MatchBody(Strict):
    version_id: Optional[str] = Field(None, max_length=64)


class AssignmentIn(Strict):
    requirement_id: str
    resource_type: Literal["internal", "external"]
    coded_identity: Optional[str] = Field(None, pattern=r"^EMP-[0-9a-f]{8}$")
    fte: str = Field(..., max_length=8)
    percentile: Optional[Literal["p25", "p50", "p75"]] = None


class ScenarioBody(Strict):
    requirement_version_id: Optional[str] = None
    kind: Optional[Literal["internal", "external", "hybrid", "custom"]] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    months: Optional[int] = None
    bill_rate_basis: Literal["per_month"] = "per_month"
    cost_policy_id: str = Field(..., max_length=64)
    cost_policy_version: Optional[int] = None
    rate_card_id: str = Field(..., max_length=64)
    rate_card_version: Optional[int] = None
    cost_as_of: Optional[str] = None
    project_direct_costs: str = "0"
    assignments: List[AssignmentIn] = Field(..., min_length=1, max_length=200)


class CompareBody(Strict):
    requirement_version_id: Optional[str] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    months: Optional[int] = None
    cost_policy_id: str = Field(..., max_length=64)
    cost_policy_version: Optional[int] = None
    rate_card_id: str = Field(..., max_length=64)
    rate_card_version: Optional[int] = None
    cost_as_of: Optional[str] = None
    project_direct_costs: str = "0"


class ApprovalBody(Strict):
    scenario_id: str = Field(..., max_length=64)
    approver_role: Literal["delivery", "finance", "hr"]
    outcome: Literal["approved", "rejected"]
    reason: Optional[str] = Field(None, max_length=1000)
    override_reason: Optional[str] = Field(None, max_length=1000)


class ExportBody(Strict):
    scenario_id: str = Field(..., max_length=64)
    format: Literal["json", "markdown"] = "json"


# ------------------------------------------------------------------ status
@router.get("/api/hoi/status")
def hoi_status(c=Ctx) -> Dict[str, Any]:
    """Capabilities and pending enterprise integrations, stated honestly."""
    return {
        "module": "Hermes Opportunity Intelligence", "calc_version": CALC_VERSION,
        "implemented": ["opportunities", "document_upload", "rules_extraction", "human_approval", "internal_matching",
                        "finance_vault", "costing", "market_csv_import", "scenarios", "approvals", "audit", "export"],
        "pending_integrations": {
            "malware_scanning": "adapter present; no scanner configured (documents are stored as not_scanned)",
            "ocr": "not implemented; image-only PDFs are reported as needs_ocr",
            "hris_payroll": "not connected; loaded costs are entered by Finance",
            "resource_planning_capacity": "not connected; capacity comes from the Hermes availability table",
            "ats_vendor_market_feeds": "not connected; benchmarks are curated CSV imports",
            "oidc_entra": "production identity provider not wired in this prototype",
            "azure_deployment": "documented target only (docs/future-azure.md)",
        },
        "contract_types": list(CONTRACT_TYPES),
        "limits": {"max_upload_mb": hoi_docs.MAX_BYTES // (1024 * 1024), "formats": list(hoi_docs.EXTENSIONS)},
    }


@router.get("/api/hoi/skills")
def hoi_skills(c=Ctx) -> Dict[str, Any]:
    """Governed skill list for requirement mapping (names only; /api/skills is manager/admin-only)."""
    _, h = c
    return {"skills": sorted(({"skill_id": s.skill_id, "name": s.name} for s in h.taxonomy.all_skills()), key=lambda x: x["name"])}


# ------------------------------------------------------------------ opportunities
@router.post("/api/opportunities", status_code=201)
def create_opportunity(body: OppBody, c=Ctx):
    p, h = c
    return h.create_opportunity(p, body.model_dump())


@router.get("/api/opportunities")
def list_opportunities(c=Ctx):
    p, h = c
    return {"opportunities": h.list_opportunities(p)}


@router.get("/api/opportunities/{oid}")
def get_opportunity(oid: str, c=Ctx):
    p, h = c
    return h.opportunity(p, oid)


@router.post("/api/opportunities/{oid}/members")
def add_member(oid: str, body: MemberBody, c=Ctx):
    p, h = c
    return h.add_member(p, oid, body.sub, body.member_role)


@router.post("/api/opportunities/{oid}/documents", status_code=201)
def upload_document(oid: str, body: DocBody, c=Ctx):
    p, h = c
    return h.upload_document(p, oid, body.doc_type, body.filename, body.content_b64)


@router.get("/api/opportunities/{oid}/documents")
def list_documents(oid: str, c=Ctx):
    p, h = c
    return {"documents": h.list_documents(p, oid)}


@router.post("/api/opportunities/{oid}/extract")
def extract(oid: str, body: ExtractBody, c=Ctx):
    p, h = c
    provider = get_llm_provider if body.use_llm else None
    return h.extract(p, oid, body.document_ids, provider)


@router.get("/api/opportunities/{oid}/requirements")
def requirements(oid: str, version_id: Optional[str] = Query(None, max_length=64), c=Ctx):
    p, h = c
    return h.get_requirements(p, oid, version_id)


@router.put("/api/opportunities/{oid}/requirements/{vid}")
def update_requirements(oid: str, vid: str, body: ReqUpdate, c=Ctx):
    p, h = c
    return h.update_requirements(p, oid, vid, [r.model_dump() for r in body.roles])


@router.post("/api/opportunities/{oid}/requirements/approve")
def approve_requirements(oid: str, body: VersionBody, c=Ctx):
    p, h = c
    return h.approve_requirements(p, oid, body.version_id)


@router.post("/api/opportunities/{oid}/requirements/revise")
def revise_requirements(oid: str, c=Ctx):
    p, h = c
    return h.revise_requirements(p, oid)


@router.post("/api/opportunities/{oid}/internal-match")
def internal_match(oid: str, body: MatchBody, c=Ctx):
    p, h = c
    return h.internal_match(p, oid, body.version_id)


@router.get("/api/opportunities/{oid}/shortlist")
def shortlist(oid: str, run_id: Optional[str] = Query(None, max_length=64), c=Ctx):
    p, h = c
    return h.shortlist(p, oid, run_id)


@router.post("/api/opportunities/{oid}/market-analysis")
def market_analysis(oid: str, c=Ctx):
    p, h = c
    return h._scen.market_analysis(p, oid)


@router.post("/api/opportunities/{oid}/scenarios", status_code=201)
def create_scenario(oid: str, body: ScenarioBody, c=Ctx):
    p, h = c
    return h._scen.create(p, oid, body.model_dump())


@router.post("/api/opportunities/{oid}/scenarios/compare")
def compare_scenarios(oid: str, body: CompareBody, c=Ctx):
    p, h = c
    return h._scen.compare(p, oid, body.model_dump())


@router.get("/api/opportunities/{oid}/scenarios")
def list_scenarios(oid: str, c=Ctx):
    p, h = c
    return {"scenarios": h._scen.list(p, oid)}


@router.get("/api/opportunities/{oid}/scenarios/{sid}")
def get_scenario(oid: str, sid: str, c=Ctx):
    p, h = c
    return h._scen.get(p, oid, sid)


@router.post("/api/opportunities/{oid}/approvals")
def approvals(oid: str, body: ApprovalBody, c=Ctx):
    p, h = c
    return h._scen.approve(p, oid, body.scenario_id, body.approver_role, body.outcome, body.reason, body.override_reason)


@router.post("/api/opportunities/{oid}/export")
def export(oid: str, body: ExportBody, c=Ctx):
    p, h = c
    return h._scen.export(p, oid, body.scenario_id, body.format)


@router.get("/api/opportunities/{oid}/audit")
def audit(oid: str, c=Ctx):
    p, h = c
    return h.audit_trail(p, oid)


# ------------------------------------------------------------------ market intelligence
class CsvBody(Strict):
    csv_text: str = Field(..., min_length=10, max_length=2_000_000)
    declare_synthetic: bool


@router.post("/api/market/benchmarks/import", status_code=201)
def import_benchmarks(body: CsvBody, c=Ctx):
    p, h = c
    need_roles(p, FINANCE, ADMIN)
    rows = parse_csv(body.csv_text, body.declare_synthetic)
    res = h.market.import_rows(p.sub, rows)
    h.svc.audit.append("hoi.market_import", p.sub, {"import_batch": res["import_batch"], "rows": res["rows"]})
    return res


@router.get("/api/market/benchmarks")
def list_benchmarks(role: Optional[str] = Query(None, max_length=120), geography: Optional[str] = Query(None, max_length=120),
                    basis: Optional[Literal["salary", "contractor_cost", "bill_rate"]] = None, c=Ctx):
    p, h = c
    rows = h.market.query(role, geography, basis)
    return {"benchmarks": rows, "note": "Curated imports only; no live feed. Salary, contractor cost and bill rate are separate bases.",
            "synthetic_rows": sum(1 for r in rows if r["is_synthetic"])}


# ------------------------------------------------------------------ finance-controlled
class PolicyBody(Strict):
    payload: Dict[str, Any]
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None


class CostRow(Strict):
    scope: Literal["individual", "role_band"]
    subject: str = Field(..., max_length=80)
    monthly_cost: str = Field(..., max_length=24)
    currency: str = Field(..., min_length=3, max_length=3)
    cost_basis: Literal["fully_loaded_monthly"] = "fully_loaded_monthly"
    effective_from: str
    effective_to: Optional[str] = None
    source: str = Field(..., max_length=200)


class CostsBody(Strict):
    rows: List[CostRow] = Field(..., min_length=1, max_length=2000)


@router.put("/api/finance/cost-policies/{name}")
def put_policy(name: str, body: PolicyBody, c=Ctx):
    p, h = c
    need_roles(p, FINANCE)
    res = h.vault.put_parameter(p.sub, "policy", name, body.payload, body.effective_from, body.effective_to)
    h.svc.audit.append("hoi.cost_policy_saved", p.sub, {"name": name, "version": res["version"]})
    return res


@router.get("/api/finance/cost-policies")
def list_policies(c=Ctx):
    p, h = c
    need_roles(p, FINANCE, MANAGER, ADMIN)
    return {"policies": h.vault.list_parameters("policy", include_payload=p.has_any_role(FINANCE))}


@router.put("/api/finance/rate-cards/{name}")
def put_rate_card(name: str, body: PolicyBody, c=Ctx):
    p, h = c
    need_roles(p, FINANCE)
    res = h.vault.put_parameter(p.sub, "rate_card", name, body.payload, body.effective_from, body.effective_to)
    h.svc.audit.append("hoi.rate_card_saved", p.sub, {"name": name, "version": res["version"]})
    return res


@router.get("/api/rate-cards")
def list_rate_cards(c=Ctx):
    p, h = c
    need_roles(p, FINANCE, MANAGER, SALES, ADMIN)
    return {"rate_cards": h.vault.list_parameters("rate_card", include_payload=True)}


@router.post("/api/finance/loaded-costs", status_code=201)
def add_loaded_costs(body: CostsBody, c=Ctx):
    p, h = c
    need_roles(p, FINANCE)
    n = h.vault.add_costs(p.sub, [r.model_dump() for r in body.rows])
    h.vault.log_access(p.sub, "add_loaded_costs", f"{n} rows")
    h.svc.audit.append("hoi.loaded_costs_added", p.sub, {"rows": n})
    return {"rows_added": n}


@router.get("/api/finance/loaded-costs")
def list_loaded_costs(c=Ctx):
    p, h = c
    need_roles(p, FINANCE)
    return {"costs": h.vault.list_costs(p.sub)}


@router.get("/api/finance/summary")
def finance_summary(c=Ctx):
    p, h = c
    need_roles(p, FINANCE, HR, ADMIN)
    return {"loaded_cost_rows": h.vault.summary(), "policies": len(h.vault.list_parameters("policy", False)),
            "rate_cards": len(h.vault.list_parameters("rate_card", False))}


@router.get("/api/finance/access-log")
def finance_access_log(c=Ctx):
    p, h = c
    need_roles(p, FINANCE, HR, ADMIN)
    return {"events": h.vault.access_log()}
