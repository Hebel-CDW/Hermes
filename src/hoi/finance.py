"""Finance-controlled storage and service: loaded costs, cost policies, rate cards.

The ONLY path that reads individual or role-band loaded cost. Amounts are Fernet-encrypted at rest with a
key separate from the document key. Every read of raw amounts by a person is written to ``fin_access_log``
(action + actor, never values). Callers outside this module receive Decimals only inside the costing
pipeline; the API layer never serialises them for non-finance roles.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence

from hoi.costing import CostPolicy, dec
from hoi.crypto import decrypt_text, encrypt_text
from hoi.errors import HoiConflict, HoiValidation
from shared.models import utc_now

import json

COST_BASES = ("fully_loaded_monthly",)
SCOPES = ("individual", "role_band")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _d(s: Any, label: str) -> str:
    try:
        return date.fromisoformat(str(s)).isoformat()
    except ValueError as exc:
        raise HoiValidation(f"{label} must be an ISO date (YYYY-MM-DD)") from exc


class FinanceVault:
    def __init__(self, db: Any) -> None:
        self.db = db

    # ------------------------------------------------------------------ access log
    def log_access(self, actor: str, action: str, context: str = "") -> None:
        with self.db.session() as conn:
            conn.execute(
                "INSERT INTO fin_access_log (access_id, actor, action, context, created_at) VALUES (?,?,?,?,?)",
                (f"fa-{uuid.uuid4().hex[:12]}", actor, action, context[:200], utc_now().isoformat()),
            )

    def access_log(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM fin_access_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ loaded cost
    def add_costs(self, actor: str, rows: Sequence[Mapping[str, Any]]) -> int:
        if not rows:
            raise HoiValidation("no cost rows supplied")
        clean = []
        for i, r in enumerate(rows, start=1):
            scope = r.get("scope")
            if scope not in SCOPES:
                raise HoiValidation(f"row {i}: scope must be one of {list(SCOPES)}")
            subject = norm(r.get("subject") or "") if scope == "role_band" else str(r.get("subject") or "").strip()
            if not subject:
                raise HoiValidation(f"row {i}: subject is required")
            if scope == "individual" and not re.match(r"^EMP-[0-9a-f]{8}$", subject):
                raise HoiValidation(f"row {i}: individual cost must be keyed by coded identity")
            try:
                amount = dec(r.get("monthly_cost"), "monthly_cost")
            except ValueError as exc:
                raise HoiValidation(f"row {i}: {exc}") from exc
            if amount <= 0:
                raise HoiValidation(f"row {i}: monthly_cost must be positive")
            cur = str(r.get("currency") or "").upper()
            if not re.match(r"^[A-Z]{3}$", cur):
                raise HoiValidation(f"row {i}: currency must be a 3-letter code")
            basis = r.get("cost_basis", "fully_loaded_monthly")
            if basis not in COST_BASES:
                raise HoiValidation(f"row {i}: cost_basis must be one of {list(COST_BASES)} (labelled, never mixed)")
            eff_from = _d(r.get("effective_from"), f"row {i}: effective_from")
            eff_to = _d(r["effective_to"], f"row {i}: effective_to") if r.get("effective_to") else None
            if eff_to and eff_to < eff_from:
                raise HoiValidation(f"row {i}: effective_to precedes effective_from")
            if not str(r.get("source") or "").strip():
                raise HoiValidation(f"row {i}: source (approved cost reference) is required")
            clean.append((scope, subject, amount, cur, basis, eff_from, eff_to, str(r["source"])[:200]))
        with self.db.session() as conn:
            for scope, subject, amount, cur, basis, ef, et, src in clean:
                conn.execute(
                    "INSERT INTO fin_loaded_costs (cost_id, scope, subject_key, monthly_cost_enc, currency, cost_basis, "
                    "effective_from, effective_to, source, entered_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (f"fc-{uuid.uuid4().hex[:12]}", scope, subject, encrypt_text("finance", str(amount)), cur, basis,
                     ef, et, src, actor, utc_now().isoformat()),
                )
        return len(clean)

    def list_costs(self, actor: str) -> List[Dict[str, Any]]:
        """Finance-only raw view. Access is logged."""
        self.log_access(actor, "list_loaded_costs")
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM fin_loaded_costs ORDER BY created_at, cost_id").fetchall()
        return [{"cost_id": r["cost_id"], "scope": r["scope"], "subject": r["subject_key"],
                 "monthly_cost": decrypt_text("finance", r["monthly_cost_enc"]), "currency": r["currency"],
                 "cost_basis": r["cost_basis"], "effective_from": r["effective_from"],
                 "effective_to": r["effective_to"], "source": r["source"]} for r in rows]

    def summary(self) -> Dict[str, Any]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT scope, COUNT(*) AS n FROM fin_loaded_costs GROUP BY scope").fetchall()
        return {r["scope"]: int(r["n"]) for r in rows}

    def resolve(self, coded_identity: Optional[str], role_name: str, as_of: str) -> Optional[Dict[str, Any]]:
        """Costing-pipeline lookup: individual first, then role band, valid on ``as_of``. None == unresolved."""
        keys = []
        if coded_identity:
            keys.append(("individual", coded_identity))
        keys.append(("role_band", norm(role_name)))
        with self.db.session() as conn:
            for scope, key in keys:
                row = conn.execute(
                    "SELECT * FROM fin_loaded_costs WHERE scope=? AND subject_key=? AND effective_from<=? "
                    "AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC, cost_id DESC LIMIT 1",
                    (scope, key, as_of, as_of),
                ).fetchone()
                if row:
                    return {"amount": Decimal(decrypt_text("finance", row["monthly_cost_enc"])),
                            "currency": row["currency"], "cost_ref": row["cost_id"], "scope": scope,
                            "source": row["source"], "effective_from": row["effective_from"]}
        return None

    # ------------------------------------------------------------------ policies and rate cards
    def put_parameter(self, actor: str, kind: str, name: str, payload: Mapping[str, Any],
                      effective_from: Optional[str], effective_to: Optional[str]) -> Dict[str, Any]:
        if kind not in ("policy", "rate_card"):
            raise HoiValidation("kind must be policy or rate_card")
        name = name.strip()
        if not re.match(r"^[A-Za-z0-9._-]{2,64}$", name):
            raise HoiValidation("name must be 2-64 characters of letters, digits, . _ -")
        if kind == "policy":
            try:
                CostPolicy.from_payload(name, payload)
            except ValueError as exc:
                raise HoiValidation(str(exc)) from exc
        else:
            self._validate_rate_card(payload)
        ef = _d(effective_from, "effective_from") if effective_from else None
        et = _d(effective_to, "effective_to") if effective_to else None
        with self.db.session() as conn:
            row = conn.execute("SELECT MAX(version) AS v FROM cost_parameters WHERE kind=? AND name=?", (kind, name)).fetchone()
            version = (int(row["v"]) if row and row["v"] is not None else 0) + 1
            pid = f"cp-{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO cost_parameters (parameter_id, kind, name, version, status, payload_json, effective_from, "
                "effective_to, created_by, approved_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, kind, name, version, "approved", json.dumps(payload, sort_keys=True), ef, et, actor, actor,
                 utc_now().isoformat()),
            )
        return {"parameter_id": pid, "kind": kind, "name": name, "version": version}

    @staticmethod
    def _validate_rate_card(p: Mapping[str, Any]) -> None:
        cur = str(p.get("currency") or "")
        if not re.match(r"^[A-Z]{3}$", cur):
            raise HoiValidation("rate card currency must be a 3-letter code")
        if p.get("unit") != "month":
            raise HoiValidation("rate card unit must be 'month' (bill_rate_basis per_month)")
        rates = p.get("rates")
        if not isinstance(rates, dict) or not rates:
            raise HoiValidation("rate card needs a non-empty 'rates' object of role -> monthly bill rate")
        for role, v in rates.items():
            try:
                if dec(v, role) <= 0:
                    raise ValueError
            except ValueError as exc:
                raise HoiValidation(f"rate for '{role}' must be a positive number") from exc

    def get_parameter(self, kind: str, name: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with self.db.session() as conn:
            if version is None:
                row = conn.execute("SELECT * FROM cost_parameters WHERE kind=? AND name=? AND status='approved' "
                                   "ORDER BY version DESC LIMIT 1", (kind, name)).fetchone()
            else:
                row = conn.execute("SELECT * FROM cost_parameters WHERE kind=? AND name=? AND version=?",
                                   (kind, name, version)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["payload"] = json.loads(d.pop("payload_json"))
        return d

    def list_parameters(self, kind: str, include_payload: bool) -> List[Dict[str, Any]]:
        with self.db.session() as conn:
            rows = conn.execute("SELECT * FROM cost_parameters WHERE kind=? ORDER BY name, version", (kind,)).fetchall()
        out = []
        for r in rows:
            d = {k: r[k] for k in ("parameter_id", "kind", "name", "version", "status", "effective_from",
                                   "effective_to", "created_by", "created_at")}
            if include_payload:
                d["payload"] = json.loads(r["payload_json"])
            out.append(d)
        return out
