"""Employee self-service and manager approvals: the in-app replacement for the Excel update loop.

Nothing here scores, ranks or changes evidence rules. An employee *proposes* (a skill, a
certificate, a skill check, a growth goal); a manager decides. Approval goes through the same
governed paths that already exist (``declare_skill`` and the certificate date/promote pair), so
a proposal never counts for anything until a manager has accepted it, and every step is audited.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence

from shared.errors import (
    DecisionValidationError,
    RequestNotFound,
    RequestStateConflict,
    UnknownSkillError,
)

if TYPE_CHECKING:
    from shared.service import HermesService

KINDS = ("skill_claim", "certificate", "skill_check")
MAX_PENDING_PER_PERSON = 25

#: Audit events an employee should see on their own timeline, in plain words.
TIMELINE_TITLES: Dict[str, str] = {
    "employee_request_submitted": "You sent a request to your manager",
    "employee_request_withdrawn": "You withdrew a request",
    "manager_request_decided": "Your manager answered a request",
    "manager_declared_skill": "A skill was confirmed on your record",
    "evidence_contest": "You raised a dispute",
    "manager_contest_resolved": "Your manager answered a dispute",
    "certificate_dated": "A certificate date was recorded",
    "certificate_promoted": "A certificate now counts as proof",
    "employee_goal_set": "You set a growth goal",
    "employee_goal_cleared": "You cleared your growth goal",
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_earned_at(value: str) -> str:
    """Accept YYYY-MM-DD (or a full ISO time); return a UTC ISO timestamp. Never in the future."""
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionValidationError("earned_at must be a date like 2024-05-31") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed > datetime.now(timezone.utc):
        raise DecisionValidationError("earned_at cannot be in the future")
    if parsed.year < 1990:
        raise DecisionValidationError("earned_at is not a plausible certificate date")
    return parsed.astimezone(timezone.utc).isoformat()


class Workflow:
    def __init__(self, svc: "HermesService") -> None:
        self.svc = svc
        self.db = svc.db
        self._ensure_table()

    # ------------------------------------------------------------------ storage
    def _ensure_table(self) -> None:
        with self.db.session() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS change_requests (
                    request_id      TEXT NOT NULL PRIMARY KEY,
                    coded_identity  TEXT NOT NULL,
                    kind            TEXT NOT NULL,
                    payload_json    TEXT NOT NULL DEFAULT '{{}}',
                    status          TEXT NOT NULL DEFAULT 'pending',
                    created_at      TEXT NOT NULL DEFAULT ({self.db._now_sql()}),
                    decided_by      TEXT,
                    decided_at      TEXT,
                    decision_note   TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS IX_change_requests_identity "
                "ON change_requests(coded_identity, status)"
            )

    @staticmethod
    def _row(row: Mapping[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["payload"] = json.loads(out.pop("payload_json") or "{}")
        return out

    def _get(self, request_id: str) -> Dict[str, Any]:
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM change_requests WHERE request_id = ?", (request_id,)).fetchone()
        if not row:
            raise RequestNotFound("unknown request")
        return self._row(row)

    def _skill_name(self, skill_id: Optional[str]) -> str:
        skill = self.svc.inference.taxonomy.skill_by_id(skill_id) if skill_id else None
        return skill.name if skill else (skill_id or "")

    def cert_catalog(self) -> List[Dict[str, str]]:
        out = []
        for skill in self.svc.inference.taxonomy.all_skills():
            for code in skill.cert_codes:
                out.append({"code": code, "skill_id": skill.skill_id, "skill_name": skill.name})
        return sorted(out, key=lambda c: (c["skill_name"], c["code"]))

    # ----------------------------------------------------------------- employee
    def submit(self, coded_identity: str, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if kind not in KINDS:
            raise DecisionValidationError(f"unknown request kind: {kind}")
        if not self.db.has_coded_identity(coded_identity):
            raise RequestNotFound("unknown coded identity")
        clean = dict(payload)
        if kind in ("skill_claim", "skill_check"):
            skill_id = clean.get("skill_id")
            if self.svc.inference.taxonomy.skill_by_id(skill_id) is None:
                raise UnknownSkillError(f"unknown skill id: {skill_id}")
        if kind == "skill_claim":
            level = clean.get("proficiency")
            if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 5:
                raise DecisionValidationError("proficiency must be an integer 1-5")
        if kind == "certificate":
            catalog = {c["code"]: c for c in self.cert_catalog()}
            code = clean.get("cert_code")
            if code not in catalog:
                raise DecisionValidationError("choose a certificate from the list")
            clean["earned_at"] = normalise_earned_at(clean.get("earned_at") or "")
            clean["skill_id"] = catalog[code]["skill_id"]

        existing = [r for r in self.for_person(coded_identity) if r["status"] == "pending" and r["kind"] != "goal"]
        if len(existing) >= MAX_PENDING_PER_PERSON:
            raise RequestStateConflict("too many requests are waiting; wait for your manager to answer some")
        key = clean.get("cert_code") or clean.get("skill_id")
        if any(
            r["kind"] == kind and (r["payload"].get("cert_code") or r["payload"].get("skill_id")) == key
            for r in existing
        ):
            raise RequestStateConflict("you already have this request waiting for your manager")

        request_id = f"chg-{uuid.uuid4()}"
        with self.db.session() as conn:
            conn.execute(
                "INSERT INTO change_requests (request_id, coded_identity, kind, payload_json) VALUES (?, ?, ?, ?)",
                (request_id, coded_identity, kind, json.dumps(clean)),
            )
        self.svc.audit.append(
            "employee_request_submitted",
            actor=coded_identity,
            payload={
                "request_id": request_id,
                "coded_identity": coded_identity,
                "kind": kind,
                **{k: v for k, v in clean.items() if k in ("skill_id", "cert_code", "proficiency")},
            },
        )
        return self._get(request_id)

    def for_person(self, coded_identity: str) -> List[Dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM change_requests WHERE coded_identity = ? ORDER BY created_at DESC, request_id",
                (coded_identity,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def withdraw(self, coded_identity: str, request_id: str) -> Dict[str, Any]:
        record = self._get(request_id)
        if record["coded_identity"] != coded_identity or record["kind"] == "goal":
            raise RequestNotFound("unknown request")
        self._flip(request_id, "withdrawn", decided_by=coded_identity, note=None)
        self.svc.audit.append(
            "employee_request_withdrawn",
            actor=coded_identity,
            payload={"request_id": request_id, "coded_identity": coded_identity, "kind": record["kind"]},
        )
        return self._get(request_id)

    def set_goal(self, coded_identity: str, role_id: str) -> Dict[str, Any]:
        role = self.db.get_role(role_id)
        if role is None:
            raise RequestNotFound("unknown role")
        with self.db.session() as conn:
            conn.execute(
                "UPDATE change_requests SET status = 'superseded' "
                "WHERE coded_identity = ? AND kind = 'goal' AND status = 'active'",
                (coded_identity,),
            )
            conn.execute(
                "INSERT INTO change_requests (request_id, coded_identity, kind, payload_json, status) "
                "VALUES (?, ?, 'goal', ?, 'active')",
                (
                    f"goal-{uuid.uuid4()}",
                    coded_identity,
                    json.dumps({"role_id": role_id, "role_name": role["role_name"]}),
                ),
            )
        self.svc.audit.append(
            "employee_goal_set",
            actor=coded_identity,
            payload={"coded_identity": coded_identity, "role_id": role_id},
        )
        return self.goal(coded_identity) or {}

    def clear_goal(self, coded_identity: str) -> None:
        with self.db.session() as conn:
            conn.execute(
                "UPDATE change_requests SET status = 'superseded' "
                "WHERE coded_identity = ? AND kind = 'goal' AND status = 'active'",
                (coded_identity,),
            )
        self.svc.audit.append(
            "employee_goal_cleared", actor=coded_identity, payload={"coded_identity": coded_identity}
        )

    def goal(self, coded_identity: str) -> Optional[Dict[str, Any]]:
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT * FROM change_requests WHERE coded_identity = ? AND kind = 'goal' AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                (coded_identity,),
            ).fetchone()
        if not row:
            return None
        rec = self._row(row)
        role = self.db.get_role(rec["payload"]["role_id"])
        if role is None:
            return None
        return {
            "role_id": role["role_id"],
            "role_name": role["role_name"],
            "required_skills": role["required_skills"],
            "set_at": rec["created_at"],
        }

    def timeline(self, coded_identity: str, limit: int = 40) -> List[Dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT seq, event_type, actor, payload_json, created_at FROM audit_ledger "
                "ORDER BY seq DESC LIMIT 2000"
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            title = TIMELINE_TITLES.get(r["event_type"])
            if not title:
                continue
            payload = json.loads(r["payload_json"] or "{}")
            if payload.get("coded_identity") != coded_identity and r["actor"] != coded_identity:
                continue
            skill_id = payload.get("skill_id")
            detail = self._skill_name(skill_id) if skill_id else ""
            if r["event_type"] == "manager_request_decided":
                detail = f"{payload.get('decision', '').title()}: {detail or payload.get('kind', '')}".strip(": ")
            elif payload.get("cert_code"):
                detail = payload["cert_code"]
            elif payload.get("role_id") and not detail:
                role = self.db.get_role(payload["role_id"])
                detail = role["role_name"] if role else ""
            out.append(
                {
                    "seq": int(r["seq"] or 0),
                    "at": r["created_at"],
                    "event_type": r["event_type"],
                    "title": title,
                    "detail": detail,
                }
            )
            if len(out) >= limit:
                break
        return out

    # ------------------------------------------------------------------ manager
    def team_scope(self, principal: Any) -> List[str]:
        if principal.is_admin:
            return [d["coded_identity"] for d in self.db.list_identity_directory()]
        if principal.coded_identity:
            return self.db.direct_reports(principal.coded_identity)
        return []

    def inbox(self, scope: Sequence[str]) -> Dict[str, Any]:
        scope_set = set(scope)
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM change_requests WHERE status = 'pending' AND kind != 'goal' "
                "ORDER BY created_at ASC, request_id"
            ).fetchall()
        requests = []
        for r in rows:
            rec = self._row(r)
            if rec["coded_identity"] not in scope_set:
                continue
            rec["skill_name"] = self._skill_name(rec["payload"].get("skill_id"))
            requests.append(rec)
        contests = []
        for coded in scope:
            for c in self.db.list_open_contests(coded):
                c = dict(c)
                c["skill_name"] = self._skill_name(c.get("skill_id"))
                contests.append(c)
        return {"requests": requests, "contests": contests}

    def _flip(self, request_id: str, status: str, decided_by: str, note: Optional[str]) -> None:
        with self.db.session() as conn:
            cur = conn.execute(
                "UPDATE change_requests SET status = ?, decided_by = ?, decided_at = ?, decision_note = ? "
                "WHERE request_id = ? AND status = 'pending'",
                (status, decided_by, _utc_iso(), note, request_id),
            )
            if cur.rowcount != 1:
                raise RequestStateConflict("this request has already been answered")

    def _revert(self, request_id: str) -> None:
        with self.db.session() as conn:
            conn.execute(
                "UPDATE change_requests SET status = 'pending', decided_by = NULL, decided_at = NULL, "
                "decision_note = NULL WHERE request_id = ?",
                (request_id,),
            )

    def decide(
        self,
        actor_sub: str,
        request_id: str,
        decision: str,
        proficiency: Optional[int] = None,
        earned_at: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = self._get(request_id)
        if record["kind"] == "goal":
            raise RequestNotFound("unknown request")
        if record["status"] != "pending":
            raise RequestStateConflict("this request has already been answered")
        coded = record["coded_identity"]
        payload = record["payload"]
        if decision == "decline":
            self._flip(request_id, "declined", actor_sub, note)
        else:
            self._flip(request_id, "approved", actor_sub, note)
            try:
                self._apply(actor_sub, record, proficiency, earned_at, note)
            except Exception:
                self._revert(request_id)
                raise
        self.svc.audit.append(
            "manager_request_decided",
            actor=actor_sub,
            payload={
                "request_id": request_id,
                "coded_identity": coded,
                "kind": record["kind"],
                "decision": "approved" if decision == "approve" else "declined",
                "skill_id": payload.get("skill_id"),
                **({"note": note} if note else {}),
            },
        )
        return self._get(request_id)

    def _apply(
        self,
        actor_sub: str,
        record: Dict[str, Any],
        proficiency: Optional[int],
        earned_at: Optional[str],
        note: Optional[str],
    ) -> None:
        coded, payload, kind = record["coded_identity"], record["payload"], record["kind"]
        if kind in ("skill_claim", "skill_check"):
            level = proficiency if proficiency is not None else payload.get("proficiency")
            if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 5:
                raise DecisionValidationError("choose the level you are confirming (1-5)")
            label = "employee-proposed" if kind == "skill_claim" else "employee-requested check"
            self.svc.declare_skill(actor_sub, coded, payload["skill_id"], level, note=note or label)
        elif kind == "certificate":
            when = normalise_earned_at(earned_at) if earned_at else payload["earned_at"]
            staging_id = f"selfcert-{record['request_id']}"
            self.db.insert_cert_stagings([(staging_id, coded, payload["cert_code"], payload["cert_code"])])
            self.svc.date_certificate(staging_id, when, actor_sub)
            self.svc.promote_certificate(staging_id, actor_sub)

    def save_custom_role(
        self,
        actor_sub: str,
        role_name: str,
        required_skills: Mapping[str, int],
        critical_skills: Sequence[str],
        min_coverage_ratio: float,
    ) -> Dict[str, Any]:
        """Save a manager-built role template. Always a new ``custom_`` id: seeded roles are never overwritten."""
        for skill_id in required_skills:
            if self.svc.inference.taxonomy.skill_by_id(skill_id) is None:
                raise UnknownSkillError(f"unknown skill id: {skill_id}")
        stray = sorted(set(critical_skills) - set(required_skills))
        if stray:
            raise DecisionValidationError(f"critical skills must also be required skills: {stray}")
        role_id = f"custom_{uuid.uuid4().hex[:10]}"
        self.db.upsert_role(
            role_id, role_name.strip(), dict(required_skills), list(critical_skills), float(min_coverage_ratio)
        )
        self.svc.audit.append(
            "manager_custom_role_saved",
            actor=actor_sub,
            payload={"role_id": role_id, "role_name": role_name.strip(), "skills": len(required_skills)},
        )
        return self.db.get_role(role_id) or {}

    def delete_custom_role(self, actor_sub: str, role_id: str) -> None:
        if not role_id.startswith("custom_") or self.db.get_role(role_id) is None:
            raise RequestNotFound("unknown custom role")
        with self.db.session() as conn:
            conn.execute("DELETE FROM role_profiles WHERE role_id = ?", (role_id,))
        self.svc.audit.append("manager_custom_role_deleted", actor=actor_sub, payload={"role_id": role_id})

    def team_grid(self, scope: Sequence[str]) -> Dict[str, Any]:
        scope_set = set(scope)
        cells: Dict[str, Dict[str, Dict[str, float]]] = {c: {} for c in scope}
        for rec in self.db.load_skills_matrix():
            if rec.coded_identity in scope_set:
                cells[rec.coded_identity][rec.skill_id] = {
                    "level": int(rec.proficiency),
                    "confidence": round(float(rec.confidence), 3),
                    "freshness": round(float(rec.freshness), 3),
                }
        return {"people": list(scope), "cells": cells}

    def bulk_declare(self, actor_sub: str, items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        for it in items:
            if self.svc.inference.taxonomy.skill_by_id(it["skill_id"]) is None:
                raise UnknownSkillError(f"unknown skill id: {it['skill_id']}")
            if not self.db.has_coded_identity(it["coded_identity"]):
                raise RequestNotFound("unknown coded identity")
        saved = 0
        for it in items:
            self.svc.declare_skill(
                actor_sub,
                it["coded_identity"],
                it["skill_id"],
                int(it["proficiency"]),
                note=it.get("note") or "bulk update",
            )
            saved += 1
        self.svc.audit.append("manager_bulk_update", actor=actor_sub, payload={"count": saved})
        return {"saved": saved}
