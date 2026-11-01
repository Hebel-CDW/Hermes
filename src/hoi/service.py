"""HOI application service: opportunities, documents, requirements, internal matching, audit.

Boundaries: fitness is computed ONLY by the existing HermesService.rank (unchanged); this module adds
approval gating and separate pass/fail eligibility around it. Costs are never read here (see finance.py).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import uuid
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from hoi import documents as docs
from hoi import extraction
from hoi.errors import HoiConflict, HoiValidation, OpportunityNotFound
from hoi.finance import FinanceVault, norm
from hoi.market import MarketStore
from phase8.workbook import normalize_label
from shared.auth import AuthPrincipal
from shared.demo_identities import ADMIN, FINANCE, HR, MANAGER, SALES
from shared.errors import AuthorizationError
from shared.models import ProficiencyLevel, StaffingRequest, utc_now

CONTRACT_TYPES = ("time_and_materials", "fixed_fee", "managed_service", "blended")
DEAL_ROLES = (SALES, MANAGER, FINANCE, HR)
_FORBIDDEN_AUDIT_TOKENS = frozenset({"salary", "salaries", "compensation", "pay", "cost", "costs", "amount", "profit", "margin",
                                     "revenue", "price", "rate", "rates"})


def _monetary_key(key: str) -> bool:
    return bool(set(re.split(r"[^a-z]+", key.lower())) & _FORBIDDEN_AUDIT_TOKENS)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def cert_held(required: str, held: Sequence[str]) -> bool:
    """Deterministic, whole-token match (no fuzzy matching): the requirement equals a held certificate, or it cites a held
    certificate's code/name as a contiguous run of whole tokens (e.g. 'Azure Administrator Associate (AZ-104)' cites 'AZ-104')."""
    req = _tokens(required)
    for h in held:
        ht = _tokens(h)
        if not ht or not req:
            continue
        if req == ht or any(req[i:i + len(ht)] == ht for i in range(len(req) - len(ht) + 1)):
            return True
    return False


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _json(o: Any) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)


def _date(v: Any, label: str, required: bool = False) -> Optional[str]:
    if v in (None, ""):
        if required:
            raise HoiValidation(f"{label} is required")
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError as exc:
        raise HoiValidation(f"{label} must be YYYY-MM-DD") from exc


def need_roles(p: AuthPrincipal, *roles: str) -> None:
    if not p.has_any_role(*roles):
        raise AuthorizationError(f"role not permitted for this operation (requires one of {sorted(roles)})")


class HoiService:
    def __init__(self, svc: Any) -> None:
        self.svc = svc
        self.db = svc.db
        self.vault = FinanceVault(self.db)
        self.market = MarketStore(self.db)
        self.taxonomy = svc.inference.taxonomy

    # =================================================================== audit
    def audit(self, opp_id: str, event_type: str, actor: str, obj: str, version: str = "",
              evidence: str = "", detail: Optional[Mapping[str, Any]] = None) -> None:
        detail = dict(detail or {})
        bad = [k for k in detail if _monetary_key(k)]
        if bad:  # structural guard: monetary / compensation keys never enter the audit trail
            raise AssertionError(f"audit detail may not carry monetary keys: {bad}")
        created = utc_now().isoformat()
        aid = _id("oa")
        with self.db.session() as conn:
            if self.db.dialect == "postgres":
                conn.execute("LOCK TABLE opportunity_audit IN SHARE ROW EXCLUSIVE MODE")
            else:
                conn.execute("BEGIN IMMEDIATE")
            prev = conn.execute("SELECT seq, row_hash FROM opportunity_audit WHERE opportunity_id=? "
                                "ORDER BY seq DESC LIMIT 1", (opp_id,)).fetchone()
            seq = (int(prev["seq"]) if prev else 0) + 1
            prev_hash = prev["row_hash"] if prev else ""
            row_hash = self._audit_hash(prev_hash, aid, opp_id, seq, event_type, actor, obj, version, evidence,
                                        _json(detail), created)
            conn.execute(
                "INSERT INTO opportunity_audit (audit_id, opportunity_id, seq, event_type, actor, object_ref, version, "
                "evidence_hash, detail_json, prev_hash, row_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, opp_id, seq, event_type, actor, obj, version, evidence, _json(detail), prev_hash, row_hash, created),
            )
        # Also into the platform-wide hash-chained ledger (no detail payload beyond references).
        self.svc.audit.append(f"hoi.{event_type}", actor, {"opportunity_id": opp_id, "object": obj,
                                                           "version": version, "evidence_hash": evidence})

    @staticmethod
    def _audit_hash(prev: str, aid: str, opp: str, seq: int, et: str, actor: str, obj: str, ver: str,
                    ev: str, detail: str, created: str) -> str:
        return hashlib.sha256("|".join([prev, aid, opp, str(seq), et, actor, obj, ver, ev, detail, created]).encode()).hexdigest()

    def audit_trail(self, p: AuthPrincipal, opp_id: str) -> Dict[str, Any]:
        self.opportunity(p, opp_id)
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM opportunity_audit WHERE opportunity_id=? ORDER BY seq", (opp_id,)).fetchall()
        prev, valid, events = "", True, []
        for r in rows:
            expect = self._audit_hash(prev, r["audit_id"], opp_id, r["seq"], r["event_type"], r["actor"], r["object_ref"],
                                      r["version"], r["evidence_hash"], r["detail_json"], r["created_at"])
            if r["prev_hash"] != prev or r["row_hash"] != expect:
                valid = False
            prev = r["row_hash"]
            events.append({"seq": r["seq"], "event_type": r["event_type"], "actor": r["actor"], "object": r["object_ref"],
                           "version": r["version"], "evidence_hash": r["evidence_hash"],
                           "detail": json.loads(r["detail_json"]), "created_at": r["created_at"], "row_hash": r["row_hash"]})
        return {"opportunity_id": opp_id, "chain_valid": valid, "head_hash": prev, "events": events}

    # =================================================================== opportunities
    def create_opportunity(self, p: AuthPrincipal, body: Mapping[str, Any]) -> Dict[str, Any]:
        need_roles(p, SALES, MANAGER)
        ct = body.get("contract_type")
        if ct not in CONTRACT_TYPES:
            raise HoiValidation(f"contract_type must be one of {list(CONTRACT_TYPES)}")
        cur = str(body.get("currency") or "").upper()
        if not re.match(r"^[A-Z]{3}$", cur):
            raise HoiValidation("currency must be a 3-letter code")
        months = body.get("duration_months")
        if not isinstance(months, int) or isinstance(months, bool) or not 1 <= months <= 120:
            raise HoiValidation("duration_months must be an integer between 1 and 120")
        start, end = _date(body.get("start_date"), "start_date"), _date(body.get("end_date"), "end_date")
        if start and end and end < start:
            raise HoiValidation("end_date precedes start_date")
        oid = f"OPP-{date.today().year}-{uuid.uuid4().hex[:6].upper()}"
        with self.db.session() as conn:
            conn.execute(
                "INSERT INTO opportunities (opportunity_id, owner, client_alias, name, stage, status, bid_deadline, "
                "geography, currency, contract_type, duration_months, start_date, end_date, access_scope, is_synthetic, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, p.sub, body["client_alias"], body["name"], "intake", "open", _date(body.get("bid_deadline"), "bid_deadline"),
                 body.get("geography"), cur, ct, months, start, end, "deal_team", 1 if body.get("is_synthetic") else 0,
                 utc_now().isoformat(), utc_now().isoformat()),
            )
            conn.execute("INSERT INTO opportunity_members (opportunity_id, sub, member_role, added_by) VALUES (?,?,?,?)",
                         (oid, p.sub, "owner", p.sub))
        self.audit(oid, "opportunity_created", p.sub, oid, detail={"client_alias": body["client_alias"]})
        return self.opportunity(p, oid)

    def _row(self, opp_id: str) -> Optional[Mapping[str, Any]]:
        with self.db.session() as conn:
            return conn.execute("SELECT * FROM opportunities WHERE opportunity_id=?", (opp_id,)).fetchone()

    def _members(self, opp_id: str) -> List[Dict[str, str]]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT sub, member_role FROM opportunity_members WHERE opportunity_id=? ORDER BY sub", (opp_id,)).fetchall()
        return [{"sub": r["sub"], "member_role": r["member_role"]} for r in rows]

    def has_access(self, p: AuthPrincipal, opp_id: str) -> bool:
        if p.is_admin:
            return True
        with self.db.session() as conn:
            row = conn.execute("SELECT 1 AS x FROM opportunity_members WHERE opportunity_id=? AND sub=?", (opp_id, p.sub)).fetchone()
        return row is not None

    def opportunity(self, p: AuthPrincipal, opp_id: str) -> Dict[str, Any]:
        row = self._row(opp_id)
        if row is None or not self.has_access(p, opp_id):
            raise OpportunityNotFound("opportunity not found")  # same answer for missing and forbidden
        d = {k: row[k] for k in row.keys()}
        d["is_synthetic"] = bool(d["is_synthetic"])
        d["members"] = self._members(opp_id)
        d["readiness"] = self._readiness(opp_id)
        return d

    def _readiness(self, opp_id: str) -> Dict[str, Any]:
        with self.db.session() as conn:
            docs_n = conn.execute("SELECT COUNT(*) AS n FROM opportunity_documents WHERE opportunity_id=?", (opp_id,)).fetchone()["n"]
            rv = conn.execute("SELECT status FROM requirement_versions WHERE opportunity_id=? ORDER BY version_no DESC LIMIT 1", (opp_id,)).fetchone()
            appr = conn.execute("SELECT COUNT(*) AS n FROM requirement_versions WHERE opportunity_id=? AND status IN ('approved')", (opp_id,)).fetchone()["n"]
            sc = conn.execute("SELECT COUNT(*) AS n FROM commercial_scenarios WHERE opportunity_id=?", (opp_id,)).fetchone()["n"]
            ap = conn.execute("SELECT COUNT(*) AS n FROM commercial_scenarios WHERE opportunity_id=? AND status='approved'", (opp_id,)).fetchone()["n"]
        return {"documents": int(docs_n), "requirements_status": rv["status"] if rv else "none",
                "has_approved_requirements": int(appr) > 0, "scenarios": int(sc), "approved_scenarios": int(ap)}

    def list_opportunities(self, p: AuthPrincipal) -> List[Dict[str, Any]]:
        need_roles(p, ADMIN, *DEAL_ROLES)
        with self.db.session() as conn:
            if p.is_admin:
                rows = conn.execute("SELECT opportunity_id FROM opportunities ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute("SELECT o.opportunity_id FROM opportunities o JOIN opportunity_members m "
                                    "ON m.opportunity_id=o.opportunity_id WHERE m.sub=? ORDER BY o.created_at DESC", (p.sub,)).fetchall()
        return [self.opportunity(p, r["opportunity_id"]) for r in rows]

    def add_member(self, p: AuthPrincipal, opp_id: str, sub: str, member_role: str) -> Dict[str, Any]:
        opp = self.opportunity(p, opp_id)
        if opp["owner"] != p.sub:
            raise AuthorizationError("only the opportunity owner can manage the deal team")
        if member_role not in DEAL_ROLES:
            raise HoiValidation(f"member_role must be one of {list(DEAL_ROLES)}")
        with self.db.session() as conn:
            conn.execute("DELETE FROM opportunity_members WHERE opportunity_id=? AND sub=?", (opp_id, sub))
            conn.execute("INSERT INTO opportunity_members (opportunity_id, sub, member_role, added_by) VALUES (?,?,?,?)",
                         (opp_id, sub, member_role, p.sub))
        self.audit(opp_id, "member_added", p.sub, sub, detail={"member_role": member_role})
        return self.opportunity(p, opp_id)

    # =================================================================== documents
    def upload_document(self, p: AuthPrincipal, opp_id: str, doc_type: str, filename: str, content_b64: str) -> Dict[str, Any]:
        need_roles(p, SALES, MANAGER)
        self.opportunity(p, opp_id)
        try:
            data = base64.b64decode(content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise docs.DocumentRejected("content is not valid base64") from exc
        name, ext = docs.validate_upload(filename, data, doc_type)
        scan = docs.scan(data)
        if scan.startswith("infected"):
            raise docs.DocumentRejected("file failed malware scanning")
        digest = docs.checksum(data)
        with self.db.session() as conn:
            dup = conn.execute("SELECT document_id FROM opportunity_documents WHERE opportunity_id=? AND checksum=? ORDER BY created_at LIMIT 1",
                               (opp_id, digest)).fetchone()
        if dup:  # idempotent: identical bytes are never stored twice for the same opportunity
            self.audit(opp_id, "document_duplicate_ignored", p.sub, dup["document_id"], evidence=digest, detail={"filename": name})
            return {**self._doc_view(dup["document_id"]), "duplicate": True}
        text, status = docs.extract_text(ext, data)
        did = _id("doc")
        uri = docs.store_encrypted(opp_id, did, data)
        with self.db.session() as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM opportunity_documents WHERE opportunity_id=? AND doc_type=? AND filename=?",
                             (opp_id, doc_type, name)).fetchone()["n"]
            conn.execute(
                "INSERT INTO opportunity_documents (document_id, opportunity_id, doc_type, filename, version, mime, size_bytes, "
                "checksum, restricted_uri, scan_status, text_status, uploaded_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (did, opp_id, doc_type, name, int(n) + 1, docs.MIME[ext], len(data), docs.checksum(data), uri, scan,
                 status, p.sub, utc_now().isoformat()),
            )
        self.audit(opp_id, "document_uploaded", p.sub, did, version=str(int(n) + 1), evidence=docs.checksum(data),
                   detail={"doc_type": doc_type, "filename": name, "text_status": status, "scan_status": scan})
        return self._doc_view(did)

    def _doc_view(self, did: str) -> Dict[str, Any]:
        with self.db.session() as conn:
            r = conn.execute("SELECT * FROM opportunity_documents WHERE document_id=?", (did,)).fetchone()
        d = {k: r[k] for k in r.keys() if k != "restricted_uri"}  # storage location is never returned
        return d

    def list_documents(self, p: AuthPrincipal, opp_id: str) -> List[Dict[str, Any]]:
        self.opportunity(p, opp_id)
        with self.db.session() as conn:
            ids = conn.execute("SELECT document_id FROM opportunity_documents WHERE opportunity_id=? ORDER BY created_at", (opp_id,)).fetchall()
        return [self._doc_view(r["document_id"]) for r in ids]

    # =================================================================== requirements
    def _skill_name(self, sid: Optional[str]) -> str:
        s = self.taxonomy.skill_by_id(sid) if sid else None
        return s.name if s else (sid or "")

    def extract(self, p: AuthPrincipal, opp_id: str, document_ids: Optional[Sequence[str]],
                llm_provider: Optional[Callable[[], Any]] = None) -> Dict[str, Any]:
        need_roles(p, SALES, MANAGER)
        self.opportunity(p, opp_id)
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM opportunity_documents WHERE opportunity_id=? ORDER BY created_at", (opp_id,)).fetchall()
        picked, seen_sums = [], set()
        for r in rows:
            if document_ids and r["document_id"] not in set(document_ids):
                continue
            if r["checksum"] in seen_sums:
                continue  # same bytes uploaded more than once: read it once
            seen_sums.add(r["checksum"])
            picked.append(r)
        if document_ids:
            missing = set(document_ids) - {r["document_id"] for r in picked}
            if missing:
                raise HoiValidation(f"unknown document ids for this opportunity: {sorted(missing)}")
        texts, notes = [], []
        for r in picked:
            if r["text_status"] != "ok":
                notes.append(f"document_skipped:{r['document_id']}:{r['text_status']}")
                continue
            ext = "." + r["filename"].rsplit(".", 1)[-1].lower()
            text, st = docs.extract_text(ext, docs.load_decrypted(r["restricted_uri"]))
            if st == "ok":
                texts.append((r["document_id"], text))
        if not texts:
            raise HoiValidation("no document with extractable text" + (f" ({'; '.join(notes)})" if notes else ""))
        result = extraction.extract_rules(texts, self.taxonomy)
        if llm_provider is not None:
            try:
                result = extraction.merge_llm(result, llm_provider(), texts, self.taxonomy)
            except Exception as exc:  # noqa: BLE001 - assist is optional
                result["notes"].append(f"llm_unavailable:{type(exc).__name__}")
        result["notes"] = notes + result["notes"]
        # Defence in depth: drop anything whose cited source span does not reproduce verbatim.
        tdict = dict(texts)
        for role in result["roles"]:
            keep = []
            for s in role["skills"]:
                if extraction.verify_source(s["source"], tdict):
                    keep.append(s)
                else:
                    result["notes"].append(f"rejected_unverifiable_skill:{s['text'][:40]}")
            role["skills"] = keep
        vid = self._new_version(opp_id, p.sub, [t[0] for t in texts], result["roles"], result["parser_version"],
                                result["method"], result["notes"])
        self.audit(opp_id, "requirements_extracted", p.sub, vid, evidence=self._version_hash(vid),
                   detail={"method": result["method"], "roles": len(result["roles"]), "parser_version": result["parser_version"]})
        return self.get_requirements(p, opp_id, vid)

    def _new_version(self, opp_id: str, actor: str, doc_ids: Sequence[str], roles: Sequence[Mapping[str, Any]],
                     parser: str, method: str, notes: Sequence[str]) -> str:
        vid = _id("rv")
        with self.db.session() as conn:
            n = conn.execute("SELECT MAX(version_no) AS n FROM requirement_versions WHERE opportunity_id=?", (opp_id,)).fetchone()["n"]
            conn.execute(
                "INSERT INTO requirement_versions (version_id, opportunity_id, version_no, status, source_doc_ids_json, "
                "parser_version, extraction_method, created_by, notes_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (vid, opp_id, (int(n) if n else 0) + 1, "draft", _json(list(doc_ids)), parser, method, actor,
                 _json(list(notes)), utc_now().isoformat()),
            )
            self._write_roles(conn, vid, roles)
        return vid

    def _write_roles(self, conn: Any, vid: str, roles: Sequence[Mapping[str, Any]]) -> None:
        conn.execute("DELETE FROM resource_requirements WHERE version_id=?", (vid,))
        for i, r in enumerate(roles, start=1):
            conn.execute(
                "INSERT INTO resource_requirements (requirement_id, version_id, position, role_name, headcount, fte, location, "
                "start_date, end_date, skills_json, constraints_json, provenance_json, origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.get("requirement_id") or _id("rr"), vid, i, r["role_name"], r.get("headcount"),
                 None if r.get("fte") is None else str(r["fte"]), r.get("location"), r.get("start_date"), r.get("end_date"),
                 _json(r.get("skills", [])), _json(r.get("constraints", {})), _json(r.get("fields", {})), r.get("origin", "extracted")),
            )

    def _roles(self, vid: str) -> List[Dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM resource_requirements WHERE version_id=? ORDER BY position", (vid,)).fetchall()
        out = []
        for r in rows:
            skills = json.loads(r["skills_json"])
            for s in skills:
                s["skill_name"] = self._skill_name(s.get("skill_id"))
            out.append({"requirement_id": r["requirement_id"], "position": r["position"], "role_name": r["role_name"],
                        "headcount": r["headcount"], "fte": r["fte"], "location": r["location"],
                        "start_date": r["start_date"], "end_date": r["end_date"], "skills": skills,
                        "constraints": json.loads(r["constraints_json"]), "fields": json.loads(r["provenance_json"]),
                        "origin": r["origin"]})
        return out

    def _version_hash(self, vid: str) -> str:
        roles = [{k: v for k, v in r.items() if k not in ("requirement_id",)} for r in self._roles(vid)]
        for r in roles:
            for s in r["skills"]:
                s.pop("skill_name", None)
        return hashlib.sha256(_json(roles).encode()).hexdigest()

    def _version_row(self, opp_id: str, vid: Optional[str]) -> Mapping[str, Any]:
        with self.db.session() as conn:
            if vid:
                row = conn.execute("SELECT * FROM requirement_versions WHERE version_id=? AND opportunity_id=?", (vid, opp_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM requirement_versions WHERE opportunity_id=? ORDER BY version_no DESC LIMIT 1", (opp_id,)).fetchone()
        if row is None:
            raise HoiValidation("no requirement version found for this opportunity") if not vid else OpportunityNotFound("requirement version not found")
        return row

    def _version_view(self, row: Mapping[str, Any], with_roles: bool = True) -> Dict[str, Any]:
        d = {k: row[k] for k in row.keys() if k not in ("notes_json", "source_doc_ids_json")}
        d["notes"] = json.loads(row["notes_json"])
        d["source_doc_ids"] = json.loads(row["source_doc_ids_json"])
        if with_roles:
            d["roles"] = self._roles(row["version_id"])
            d["blocking_problems"] = (extraction.validate_for_approval(d["roles"], [s.skill_id for s in self.taxonomy.all_skills()])
                                      if row["status"] == "draft" else [])
        return d

    def get_requirements(self, p: AuthPrincipal, opp_id: str, version_id: Optional[str] = None) -> Dict[str, Any]:
        self.opportunity(p, opp_id)
        with self.db.session() as conn:
            vs = conn.execute("SELECT * FROM requirement_versions WHERE opportunity_id=? ORDER BY version_no", (opp_id,)).fetchall()
        if not vs:
            return {"versions": [], "current": None}
        row = self._version_row(opp_id, version_id)
        return {"versions": [self._version_view(v, with_roles=False) for v in vs], "current": self._version_view(row)}

    def update_requirements(self, p: AuthPrincipal, opp_id: str, version_id: str, roles: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        need_roles(p, SALES, MANAGER)
        self.opportunity(p, opp_id)
        row = self._version_row(opp_id, version_id)
        if row["status"] != "draft":
            raise HoiConflict("only a draft requirement version can be edited; create a revision instead")
        prior = {r["requirement_id"]: r for r in self._roles(version_id)}
        known = {s.skill_id for s in self.taxonomy.all_skills()}
        clean = []
        for r in roles:
            old = prior.get(r.get("requirement_id") or "")
            skills = []
            for s in r.get("skills", []):
                sid = s.get("skill_id") or None
                if sid is not None and sid not in known:
                    raise HoiValidation(f"unknown skill id '{sid}' (not in the governed taxonomy)")
                old_s = next((x for x in (old or {}).get("skills", []) if s.get("source") and x.get("source") == s.get("source")), None)
                changed = old_s is None or any(old_s.get(k) != s.get(k) for k in ("skill_id", "level", "criticality", "text"))
                skills.append({"text": s.get("text") or sid or "", "skill_id": sid, "level": s.get("level"),
                               "criticality": s.get("criticality", "must"),
                               "taxonomy_status": "mapped" if sid else "unmapped", "source": s.get("source"),
                               "confidence": s.get("confidence"),
                               "origin": ("human" if not s.get("source") else
                                          (s.get("origin", "extracted") if not changed else s.get("origin", "extracted") + "+edited"))
                                         if changed else s.get("origin", "extracted"),
                               "dismissed": bool(s.get("dismissed"))})
            cons = dict(r.get("constraints") or {})
            clean.append({"requirement_id": r.get("requirement_id") if old else None, "role_name": str(r.get("role_name") or "").strip(),
                          "headcount": r.get("headcount"), "fte": r.get("fte"), "location": r.get("location"),
                          "start_date": _date(r.get("start_date"), "start_date"), "end_date": _date(r.get("end_date"), "end_date"),
                          "skills": skills, "constraints": cons, "fields": (old or {}).get("fields", {}),
                          "origin": "human" if old is None else ("extracted+edited" if old != r else old["origin"])})
        with self.db.session() as conn:
            self._write_roles(conn, version_id, clean)
            conn.execute("UPDATE requirement_versions SET reviewed_by=? WHERE version_id=?", (p.sub, version_id))
        self.audit(opp_id, "requirements_edited", p.sub, version_id, evidence=self._version_hash(version_id),
                   detail={"roles": len(clean)})
        return self.get_requirements(p, opp_id, version_id)

    def approve_requirements(self, p: AuthPrincipal, opp_id: str, version_id: str) -> Dict[str, Any]:
        need_roles(p, SALES, MANAGER)
        self.opportunity(p, opp_id)
        row = self._version_row(opp_id, version_id)
        if row["status"] != "draft":
            raise HoiConflict("this requirement version is not a draft")
        problems = extraction.validate_for_approval(self._roles(version_id), [s.skill_id for s in self.taxonomy.all_skills()])
        if problems:
            raise HoiValidation("requirements are incomplete: " + "; ".join(problems[:12]))
        h = self._version_hash(version_id)
        now = utc_now().isoformat()
        with self.db.session() as conn:
            conn.execute("UPDATE requirement_versions SET status='superseded' WHERE opportunity_id=? AND status='approved'", (opp_id,))
            conn.execute("UPDATE requirement_versions SET status='approved', approved_by=?, approved_at=?, content_hash=?, "
                         "reviewed_by=COALESCE(reviewed_by, ?) WHERE version_id=?", (p.sub, now, h, p.sub, version_id))
            conn.execute("UPDATE opportunities SET stage='requirements_approved', updated_at=? WHERE opportunity_id=?", (now, opp_id))
        self.audit(opp_id, "requirements_approved", p.sub, version_id, version=str(row["version_no"]), evidence=h)
        return self.get_requirements(p, opp_id, version_id)

    def revise_requirements(self, p: AuthPrincipal, opp_id: str) -> Dict[str, Any]:
        need_roles(p, SALES, MANAGER)
        self.opportunity(p, opp_id)
        cur = self._version_row(opp_id, None)
        if cur["status"] == "draft":
            raise HoiConflict("a draft already exists")
        roles = self._roles(cur["version_id"])
        for r in roles:
            r["requirement_id"] = None
        vid = self._new_version(opp_id, p.sub, json.loads(cur["source_doc_ids_json"]), roles, cur["parser_version"],
                                cur["extraction_method"], ["revision_of:" + cur["version_id"]])
        self.audit(opp_id, "requirements_revision_started", p.sub, vid)
        return self.get_requirements(p, opp_id, vid)

    def approved_version(self, opp_id: str, version_id: Optional[str] = None) -> Mapping[str, Any]:
        """The only door into matching and costing: an APPROVED version, else 409."""
        with self.db.session() as conn:
            if version_id:
                row = conn.execute("SELECT * FROM requirement_versions WHERE version_id=? AND opportunity_id=?", (version_id, opp_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM requirement_versions WHERE opportunity_id=? AND status='approved' "
                                   "ORDER BY version_no DESC LIMIT 1", (opp_id,)).fetchone()
        if row is None or row["status"] != "approved":
            raise HoiConflict("requirements must be approved by a person before matching or costing", "requirements_not_approved")
        return row

    # =================================================================== internal matching
    def internal_match(self, p: AuthPrincipal, opp_id: str, version_id: Optional[str] = None) -> Dict[str, Any]:
        need_roles(p, MANAGER)
        self.opportunity(p, opp_id)
        ver = self.approved_version(opp_id, version_id)
        vid = ver["version_id"]
        roles = self._roles(vid)
        run_id = _id("mr")
        alloc = self.db.get_allocation()
        period = date.today().strftime("%Y-%m")
        captured = utc_now().isoformat()
        out_roles = []
        shortlist_rows, cap_rows, seen_cap = [], [], set()
        for r in roles:
            live = [s for s in r["skills"] if not s.get("dismissed") and s.get("skill_id")]
            required = {s["skill_id"]: ProficiencyLevel(int(s["level"])) for s in live}
            critical = sorted({s["skill_id"] for s in live if s["criticality"] == "must"})
            req_id = f"hoi-{run_id}-{r['position']}"
            result = self.svc.rank(StaffingRequest(request_id=req_id, requester_id=p.sub, required_skills=required,
                                                   shortlist_size=10, availability_required=False),
                                   critical_skills=critical)
            cons = r["constraints"]
            fte = float(r["fte"])
            cands = []
            for c in result.candidates:
                checks = self._eligibility(c.coded_identity, cons, fte, alloc)
                status = ("ineligible" if any(k["status"] == "fail" for k in checks) else
                          "unverified" if any(k["status"] == "unknown" for k in checks) else "eligible")
                cands.append((c, checks, status))
                if c.coded_identity not in seen_cap:
                    seen_cap.add(c.coded_identity)
                    cap_rows.append((_id("cs"), run_id, c.coded_identity, period, alloc.get(c.coded_identity), "hermes.availability", captured))
                shortlist_rows.append((_id("sl"), run_id, opp_id, vid, r["requirement_id"], c.coded_identity, c.rank,
                                       c.fitness_score, status, _json({"checks": checks}),
                                       _json({"evidence_ids": c.evidence_ids, "per_skill_reasoning": c.per_skill_reasoning}),
                                       result.computation_run_id, req_id, p.sub))
            out_roles.append((r, req_id, result, cands))
        with self.db.session() as conn:
            for row in shortlist_rows:
                conn.execute("INSERT INTO candidate_shortlists (shortlist_id, match_run_id, opportunity_id, version_id, requirement_id, "
                             "coded_identity, rank, fitness_score, eligibility, eligibility_json, evidence_refs_json, fitness_run_id, "
                             "staffing_request_id, requested_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             row + (utc_now().isoformat(),))
            for row in cap_rows:
                if row[4] is not None:
                    conn.execute("INSERT INTO capacity_snapshots (snapshot_id, match_run_id, coded_identity, period, available_fte, "
                                 "source, captured_at) VALUES (?,?,?,?,?,?,?)", row)
            conn.execute("UPDATE opportunities SET stage='internal_matched', updated_at=? WHERE opportunity_id=?",
                         (utc_now().isoformat(), opp_id))
        self.audit(opp_id, "internal_match_run", p.sub, run_id, version=str(ver["version_no"]), evidence=ver["content_hash"] or "",
                   detail={"requirement_version_id": vid, "scoring_config_version": out_roles[0][2].scoring_config_version if out_roles else "",
                           "candidates": len(shortlist_rows)})
        return self.shortlist(p, opp_id, run_id)

    def _eligibility(self, coded: str, cons: Mapping[str, Any], fte: float, alloc: Mapping[str, float]) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        if cons.get("require_availability", True):
            if coded not in alloc:
                checks.append({"check": "capacity", "status": "unknown", "detail": "no authoritative availability record"})
            elif alloc[coded] + 1e-9 >= fte:
                checks.append({"check": "capacity", "status": "pass", "detail": f"available {alloc[coded]:.2f} FTE >= required {fte:.2f}"})
            else:
                checks.append({"check": "capacity", "status": "fail", "detail": f"available {alloc[coded]:.2f} FTE < required {fte:.2f}"})
        certs = cons.get("mandatory_certifications") or []
        if certs:
            held = self._held_certificates(coded)
            for c in certs:
                ok = cert_held(c, held)
                checks.append({"check": f"certification:{c}", "status": "pass" if ok else "fail",
                               "detail": "evidenced" if ok else "no evidenced certificate"})
        if cons.get("location_mandatory"):
            checks.append({"check": "location", "status": "unknown", "detail": "Hermes holds no authoritative location data"})
        return checks

    def _held_certificates(self, coded: str) -> List[str]:
        """Certificates evidenced for this identity: promoted workbook certificates (real-data path) and CERTIFIED evidence
        records (their source_ref is the certificate code). Nothing is inferred and nothing is self-declared."""
        with self.db.session() as conn:
            staged = conn.execute("SELECT cert_label, cert_code FROM cert_staging WHERE coded_identity=? AND promoted=1", (coded,)).fetchall()
            certified = conn.execute("SELECT source_ref FROM evidence_staging WHERE coded_identity=? AND evidence_type='certified'", (coded,)).fetchall()
        out = [x for r in staged for x in (r["cert_label"], r["cert_code"]) if x]
        return out + [r["source_ref"] for r in certified if r["source_ref"]]

    def shortlist(self, p: AuthPrincipal, opp_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        self.opportunity(p, opp_id)
        with self.db.session() as conn:
            if not run_id:
                last = conn.execute("SELECT match_run_id FROM candidate_shortlists WHERE opportunity_id=? ORDER BY created_at DESC LIMIT 1", (opp_id,)).fetchone()
                run_id = last["match_run_id"] if last else None
            rows = conn.execute("SELECT * FROM candidate_shortlists WHERE opportunity_id=? AND match_run_id=? ORDER BY requirement_id, rank",
                                (opp_id, run_id)).fetchall() if run_id else []
            caps = {r["coded_identity"]: r["available_fte"] for r in conn.execute(
                "SELECT coded_identity, available_fte FROM capacity_snapshots WHERE match_run_id=?", (run_id,)).fetchall()} if run_id else {}
        if not rows:
            return {"match_run_id": None, "requirements": []}
        version_id = rows[0]["version_id"]
        full = p.has_any_role(MANAGER)
        roles = {r["requirement_id"]: r for r in self._roles(version_id)}
        out = []
        for rid, role in roles.items():
            mine = [r for r in rows if r["requirement_id"] == rid]
            entry: Dict[str, Any] = {"requirement_id": rid, "role_name": role["role_name"], "headcount": role["headcount"],
                                     "fte": role["fte"], "eligible_count": sum(1 for r in mine if r["eligibility"] == "eligible"),
                                     "candidate_count": len(mine)}
            if full:
                entry["staffing_request_id"] = mine[0]["staffing_request_id"] if mine else None
                entry["candidates"] = [{
                    "coded_identity": r["coded_identity"], "rank": r["rank"], "fitness_score": r["fitness_score"],
                    "eligibility": r["eligibility"], "checks": json.loads(r["eligibility_json"])["checks"],
                    "available_fte": caps.get(r["coded_identity"]),
                    "evidence_ids": json.loads(r["evidence_refs_json"]).get("evidence_ids", []),
                    "explanation": json.loads(r["evidence_refs_json"]).get("per_skill_reasoning", {}),
                    "fitness_run_id": r["fitness_run_id"]} for r in mine]
            out.append(entry)
        return {"match_run_id": run_id, "requirement_version_id": version_id, "redacted": not full,
                "note": "Coded identities only. Names are revealed solely through the audited identity-resolution gateway "
                        "(POST /api/identity/resolve with the staffing_request_id).",
                "requirements": out}
