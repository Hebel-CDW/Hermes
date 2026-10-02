"""Deterministic identity tokenization and PII stripping."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Set, Union

from shared.models import (
    CLIENT_NAME_BLOCKLIST,
    IDENTITY_PII_FIELDS,
    PROTECTED_ATTRIBUTE_FIELDS,
    is_client_name_label,
)


CODED_ID_PATTERN = re.compile(r"^EMP-[0-9a-fA-F]{8}$")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass(frozen=True)
class AbstractionResult:
    coded_identity: str
    record: Dict[str, Any]
    stripped_fields: tuple


def _walk_strings(value: Any, path: str = "") -> List[tuple]:
    """Yield (path, string_value) recursively."""
    out: List[tuple] = []
    if isinstance(value, Mapping):
        for k, v in value.items():
            child = f"{path}.{k}" if path else str(k)
            if str(k).lower() in IDENTITY_PII_FIELDS | PROTECTED_ATTRIBUTE_FIELDS:
                out.append((child, f"__FIELD__{k}"))
            out.extend(_walk_strings(v, child))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            out.extend(_walk_strings(v, f"{path}[{i}]"))
    elif isinstance(value, str):
        out.append((path, value))
    return out


class IdentityAbstractionGate:
    """Sole ingress for records entering the shared skills matrix."""

    def __init__(self, mapping_secret: str, existing_map: Optional[Mapping[str, str]] = None) -> None:
        if not mapping_secret:
            raise ValueError("mapping_secret is required")
        self._secret = mapping_secret.encode("utf-8")
        self._forward: Dict[str, str] = dict(existing_map or {})
        self._reverse: Dict[str, str] = {v: k for k, v in self._forward.items()}
        self._display_names: Dict[str, str] = {}

    def tokenize(self, raw_employee_key: str) -> str:
        """Stable EMP- + 8 hex from HMAC. Reuses existing forward map entries."""
        key = raw_employee_key.strip().lower()
        if key in self._forward:
            return self._forward[key]
        digest = hmac.new(self._secret, key.encode("utf-8"), hashlib.sha256).hexdigest()
        token = f"EMP-{digest[:8]}"
        # Extremely rare collision on 8 hex: walk further digest slices
        n = 8
        while token in self._reverse and self._reverse[token] != key:
            token = f"EMP-{digest[n : n + 8]}"
            n += 8
            if n + 8 > len(digest):
                token = f"EMP-{digest[-8:]}"
                break
        self._forward[key] = token
        self._reverse[token] = key
        return token

    def resolve_for_gateway(self, coded_identity: str) -> Optional[str]:
        if coded_identity not in self._reverse:
            return None
        return self._display_names.get(coded_identity, self._reverse[coded_identity])

    def abstract_record(self, raw: Mapping[str, Any], employee_key_field: str = "employee_id") -> AbstractionResult:
        if employee_key_field not in raw or not raw[employee_key_field]:
            raise ValueError(f"missing employee key field: {employee_key_field}")

        # Reject protected attributes at any nesting depth (field names)
        for path, val in _walk_strings(raw):
            leaf = path.split(".")[-1].split("[")[0].lower()
            if leaf in PROTECTED_ATTRIBUTE_FIELDS or val.startswith("__FIELD__"):
                field = val.replace("__FIELD__", "") if val.startswith("__FIELD__") else leaf
                if field.lower() in PROTECTED_ATTRIBUTE_FIELDS or leaf in PROTECTED_ATTRIBUTE_FIELDS:
                    raise ValueError(f"protected attributes are forbidden: {leaf}")

        coded = self.tokenize(str(raw[employee_key_field]))
        cleaned: Dict[str, Any] = {"coded_identity": coded}
        stripped: Set[str] = set()

        for name_field in ("name", "full_name", "display_name"):
            if name_field in raw and raw[name_field]:
                self._display_names[coded] = str(raw[name_field])
                break
        else:
            self._display_names.setdefault(coded, str(raw[employee_key_field]))

        for key, value in raw.items():
            lk = str(key).lower()
            if lk in IDENTITY_PII_FIELDS or lk == employee_key_field.lower():
                stripped.add(key)
                continue
            if lk in PROTECTED_ATTRIBUTE_FIELDS:
                stripped.add(key)
                continue
            cleaned[key] = value

        return AbstractionResult(
            coded_identity=coded,
            record=cleaned,
            stripped_fields=tuple(sorted(stripped)),
        )

    def assert_no_pii(self, record: Mapping[str, Any]) -> None:
        for path, value in _walk_strings(record):
            leaf = path.split(".")[-1].split("[")[0].lower()
            if leaf in IDENTITY_PII_FIELDS:
                raise AssertionError(f"PII field present in coded record: {path}")
            if leaf in PROTECTED_ATTRIBUTE_FIELDS:
                raise AssertionError(f"protected attribute present: {path}")
            if value.startswith("__FIELD__"):
                continue
            if EMAIL_RE.search(value):
                raise AssertionError(f"email-like value leaked into coded record at {path}")

    def export_map(self) -> Dict[str, str]:
        return dict(self._forward)


def scan_for_identity_leakage(
    records: list,
    blocklist: Optional[Set[str]] = None,
    client_blocklist: Optional[Set[str]] = None,
) -> list:
    """Return list of leakage findings; recursively scans nested structures.

    Also flags client/account labels in skill_id, raw_label, and nested metadata
    against CLIENT_NAME_BLOCKLIST (D2 / Phase 8).
    """
    findings = []
    names = {n.lower() for n in (blocklist or set())}
    clients = {c.lower() for c in (client_blocklist if client_blocklist is not None else CLIENT_NAME_BLOCKLIST)}
    skill_label_keys = {"skill_id", "raw_label", "skill", "label", "account_label", "name"}
    for idx, record in enumerate(records):
        if not isinstance(record, (Mapping, MutableMapping)):
            continue
        for path, value in _walk_strings(record):
            leaf = path.split(".")[-1].split("[")[0].lower()
            if leaf in IDENTITY_PII_FIELDS:
                findings.append({"index": idx, "field": path, "reason": "pii_field"})
            if value.startswith("__FIELD__"):
                continue
            if value.lower() in names and value.lower():
                findings.append({"index": idx, "field": path, "reason": "blocklist_hit", "value": value})
            if EMAIL_RE.search(value):
                findings.append({"index": idx, "field": path, "reason": "email_pattern"})
            # Client names must never appear as skill labels or account labels in matrix payloads
            if leaf in skill_label_keys or "skill" in leaf or "label" in leaf:
                if is_client_name_label(value, frozenset(clients)):
                    findings.append(
                        {
                            "index": idx,
                            "field": path,
                            "reason": "client_name_label",
                            "value": value,
                        }
                    )
            elif is_client_name_label(value, frozenset(clients)):
                findings.append(
                    {
                        "index": idx,
                        "field": path,
                        "reason": "client_name_in_metadata",
                        "value": value,
                    }
                )
        coded = record.get("coded_identity")
        if coded and not CODED_ID_PATTERN.match(str(coded)):
            findings.append({"index": idx, "field": "coded_identity", "reason": "invalid_token"})
    return findings


def scan_real_database_for_leakage(db: "HermesDB") -> List[Dict[str, Any]]:
    """Scan the tables real scoring reads/writes for leaked real identity (Phase 6 gate).

    Unlike :func:`scan_for_identity_leakage`'s other callers (which scan seeded
    *synthetic* fixtures), this pulls its name blocklist from the database's own
    ``identity_vault`` at call time — never from a committed file — and scans
    ``skills_matrix``, ``evidence_staging`` and every ``audit_ledger`` payload.

    Intended as an operational gate (``scripts/audit_real_db_leakage.py``) run
    before any demo or UI mode that could surface real-backed data: a non-empty
    result means real identity or client/account labels reached a table that
    scoring or the audit trail exposes, and the run must not proceed.
    """
    import json as _json

    with db.session() as conn:
        names = {
            (row["display_name"] or "").strip().lower()
            for row in conn.execute("SELECT display_name FROM identity_vault").fetchall()
        }
        tables = {
            "skills_matrix": [dict(row) for row in conn.execute("SELECT * FROM skills_matrix").fetchall()],
            "evidence_staging": [dict(row) for row in conn.execute("SELECT * FROM evidence_staging").fetchall()],
        }
        audit_rows = [
            dict(row)
            for row in conn.execute("SELECT event_id, actor, payload_json FROM audit_ledger").fetchall()
        ]

    findings: List[Dict[str, Any]] = []
    for table, rows in tables.items():
        for finding in scan_for_identity_leakage(rows, blocklist=names):
            findings.append({**finding, "table": table})

    for row in audit_rows:
        try:
            payload = _json.loads(row["payload_json"] or "{}")
        except ValueError:
            payload = {"_unparseable_payload": True}
        if not isinstance(payload, Mapping):
            payload = {"_value": payload}
        for finding in scan_for_identity_leakage([payload], blocklist=names):
            findings.append(
                {**finding, "table": "audit_ledger", "event_id": row["event_id"], "actor": row["actor"]}
            )

    return findings
