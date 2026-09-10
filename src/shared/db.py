"""SQLite persistence for local-first Hermes."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence

from shared.models import (
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    SkillRecord,
    utc_now,
)


def default_db_path() -> Path:
    env = os.getenv("HERMES_DB_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "hermes.db"


def schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "infra" / "sqlite" / "001_schema.sql"


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)


def hash_audit_row(
    prev_hash: str,
    event_id: str,
    event_type: str,
    actor: str,
    payload: Mapping[str, Any],
    created_at: str,
) -> str:
    material = "|".join(
        [prev_hash, event_id, event_type, actor, _canonical_json(payload), created_at]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class HermesDB:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        ddl = schema_path().read_text(encoding="utf-8")
        with self.session() as conn:
            conn.executescript(ddl)

    @staticmethod
    def source_hash(employee_key: str) -> str:
        return hashlib.sha256(employee_key.strip().lower().encode("utf-8")).hexdigest()

    def upsert_identity(
        self,
        coded_identity: str,
        employee_key: str,
        display_name: Optional[str] = None,
    ) -> None:
        src = self.source_hash(employee_key)
        name = display_name or employee_key
        with self.session() as conn:
            existing = conn.execute(
                "SELECT coded_identity FROM identity_map WHERE source_hash = ?",
                (src,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO identity_map (coded_identity, source_hash) VALUES (?, ?)",
                    (coded_identity, src),
                )
            else:
                coded_identity = existing["coded_identity"]
            conn.execute(
                """
                INSERT INTO identity_vault (coded_identity, display_name, source_employee_key)
                VALUES (?, ?, ?)
                ON CONFLICT(coded_identity) DO UPDATE SET
                  display_name=CASE
                    WHEN identity_vault.display_name IS NOT NULL
                     AND identity_vault.display_name != identity_vault.source_employee_key
                     AND excluded.display_name = excluded.source_employee_key
                    THEN identity_vault.display_name
                    ELSE excluded.display_name
                  END,
                  source_employee_key=excluded.source_employee_key,
                  updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                """,
                (coded_identity, name, employee_key.strip().lower()),
            )

    def get_display_name(self, coded_identity: str) -> Optional[str]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT display_name FROM identity_vault WHERE coded_identity = ?",
                (coded_identity,),
            ).fetchone()
            return row["display_name"] if row else None

    def stage_evidence(self, record: EvidenceRecord, payload: Optional[Mapping[str, Any]] = None) -> None:
        meta = payload if payload is not None else record.metadata
        safe_meta: Dict[str, Any] = {}
        if isinstance(meta, Mapping):
            for key in ("matched_keywords", "source_ref", "manager_confirmed", "reopen", "escalation"):
                if key in meta:
                    safe_meta[key] = meta[key]
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO evidence_staging (
                  evidence_id, coded_identity, skill_id, evidence_type, proficiency,
                  occurred_at, source_ref, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                  skill_id=excluded.skill_id,
                  evidence_type=excluded.evidence_type,
                  proficiency=excluded.proficiency,
                  occurred_at=excluded.occurred_at,
                  source_ref=excluded.source_ref,
                  payload_json=excluded.payload_json
                """,
                (
                    record.evidence_id,
                    record.coded_identity,
                    record.skill_id,
                    record.evidence_type.value,
                    int(record.proficiency),
                    record.occurred_at.isoformat(),
                    record.source_ref,
                    json.dumps(safe_meta, default=str),
                ),
            )

    def load_all_evidence(self) -> List[EvidenceRecord]:
        with self.session() as conn:
            rows = conn.execute("SELECT * FROM evidence_staging").fetchall()
        out: List[EvidenceRecord] = []
        for row in rows:
            payload = json.loads(row["payload_json"] or "{}")
            out.append(
                EvidenceRecord(
                    evidence_id=row["evidence_id"],
                    coded_identity=row["coded_identity"],
                    skill_id=row["skill_id"],
                    evidence_type=EvidenceType(row["evidence_type"]),
                    proficiency=ProficiencyLevel(row["proficiency"] or 1),
                    occurred_at=__import__("datetime").datetime.fromisoformat(row["occurred_at"]),
                    source_ref=row["source_ref"],
                    metadata=payload if isinstance(payload, dict) else {},
                )
            )
        return out

    def replace_skills_matrix(self, records: Sequence[SkillRecord], computation_run_id: str = "") -> None:
        run_id = computation_run_id or utc_now().isoformat()
        valid_from = utc_now().isoformat()
        with self.session() as conn:
            conn.execute(
                "UPDATE skills_matrix_history SET valid_to=? WHERE valid_to IS NULL",
                (valid_from,),
            )
            conn.execute("DELETE FROM skills_matrix")
            for rec in records:
                evidence_json = json.dumps(rec.evidence_ids)
                conn.execute(
                    """
                    INSERT INTO skills_matrix (
                      coded_identity, skill_id, proficiency, confidence, freshness,
                      volume_score, evidence_ids_json, scoring_config_version,
                      computation_run_id, computed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.coded_identity,
                        rec.skill_id,
                        int(rec.proficiency),
                        float(rec.confidence),
                        float(rec.freshness),
                        float(rec.volume_score),
                        evidence_json,
                        rec.scoring_config_version,
                        run_id,
                        rec.computed_at.isoformat(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO skills_matrix_history (
                      computation_run_id, coded_identity, skill_id, proficiency,
                      confidence, freshness, volume_score, evidence_ids_json,
                      scoring_config_version, valid_from, valid_to
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        run_id,
                        rec.coded_identity,
                        rec.skill_id,
                        int(rec.proficiency),
                        float(rec.confidence),
                        float(rec.freshness),
                        float(rec.volume_score),
                        evidence_json,
                        rec.scoring_config_version,
                        valid_from,
                    ),
                )

    def load_skills_matrix(self) -> List[SkillRecord]:
        with self.session() as conn:
            rows = conn.execute("SELECT * FROM skills_matrix").fetchall()
        return [
            SkillRecord(
                coded_identity=row["coded_identity"],
                skill_id=row["skill_id"],
                proficiency=ProficiencyLevel(row["proficiency"]),
                confidence=float(row["confidence"]),
                freshness=float(row["freshness"]),
                volume_score=float(row["volume_score"] if "volume_score" in row.keys() else 0),
                evidence_ids=json.loads(row["evidence_ids_json"]),
                scoring_config_version=row["scoring_config_version"],
                computed_at=__import__("datetime").datetime.fromisoformat(row["computed_at"]),
            )
            for row in rows
        ]

    def load_matrix_as_of(self, computation_run_id: str) -> List[Dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM skills_matrix_history WHERE computation_run_id = ?",
                (computation_run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_computation_runs(self) -> List[str]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT computation_run_id FROM skills_matrix_history
                GROUP BY computation_run_id
                ORDER BY MAX(valid_from) DESC
                """
            ).fetchall()
        return [r["computation_run_id"] for r in rows]

    def matrix_records_as_dicts(self) -> List[Dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT coded_identity, skill_id, proficiency, confidence, freshness, "
                "volume_score, evidence_ids_json, computation_run_id "
                "FROM skills_matrix"
            ).fetchall()
        return [dict(r) for r in rows]

    def set_demand(self, weights: Mapping[str, float]) -> None:
        with self.session() as conn:
            for skill_id, weight in weights.items():
                conn.execute(
                    """
                    INSERT INTO demand_signals (skill_id, demand_weight)
                    VALUES (?, ?)
                    ON CONFLICT(skill_id) DO UPDATE SET
                      demand_weight=excluded.demand_weight,
                      updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                    """,
                    (skill_id, float(weight)),
                )

    def get_demand(self) -> Dict[str, float]:
        with self.session() as conn:
            rows = conn.execute("SELECT skill_id, demand_weight FROM demand_signals").fetchall()
        return {r["skill_id"]: float(r["demand_weight"]) for r in rows}

    def upsert_role(
        self,
        role_id: str,
        role_name: str,
        required_skills: Mapping[str, int],
        critical_skills: Optional[Sequence[str]] = None,
        min_coverage_ratio: float = 0.6,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO role_profiles (
                  role_id, role_name, required_skills_json, critical_skills_json, min_coverage_ratio
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(role_id) DO UPDATE SET
                  role_name=excluded.role_name,
                  required_skills_json=excluded.required_skills_json,
                  critical_skills_json=excluded.critical_skills_json,
                  min_coverage_ratio=excluded.min_coverage_ratio,
                  updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                """,
                (
                    role_id,
                    role_name,
                    json.dumps(required_skills),
                    json.dumps(list(critical_skills or [])),
                    float(min_coverage_ratio),
                ),
            )

    def get_role(self, role_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM role_profiles WHERE role_id = ?", (role_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "role_id": row["role_id"],
            "role_name": row["role_name"],
            "required_skills": json.loads(row["required_skills_json"]),
            "critical_skills": json.loads(row["critical_skills_json"] or "[]"),
            "min_coverage_ratio": float(row["min_coverage_ratio"] or 0.6),
        }

    def set_availability(
        self, coded_identity: str, is_available: bool = True, allocation: float = 1.0
    ) -> None:
        alloc = float(allocation if is_available else 0.0)
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO availability (coded_identity, allocation)
                VALUES (?, ?)
                ON CONFLICT(coded_identity) DO UPDATE SET
                  allocation=excluded.allocation,
                  updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                """,
                (coded_identity, alloc),
            )

    def get_availability(self) -> Dict[str, bool]:
        with self.session() as conn:
            rows = conn.execute("SELECT coded_identity, allocation FROM availability").fetchall()
        return {r["coded_identity"]: float(r["allocation"]) > 0 for r in rows}

    def get_allocation(self) -> Dict[str, float]:
        with self.session() as conn:
            rows = conn.execute("SELECT coded_identity, allocation FROM availability").fetchall()
        return {r["coded_identity"]: float(r["allocation"]) for r in rows}

    def save_staffing_request(
        self,
        request_id: str,
        requester_id: str,
        shortlist: Sequence[str],
        computation_run_id: str = "",
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO staffing_requests (
                  request_id, requester_id, shortlist_json, computation_run_id, status
                )
                VALUES (?, ?, ?, ?, 'open')
                ON CONFLICT(request_id) DO UPDATE SET
                  requester_id=excluded.requester_id,
                  shortlist_json=excluded.shortlist_json,
                  computation_run_id=excluded.computation_run_id
                """,
                (request_id, requester_id, json.dumps(list(shortlist)), computation_run_id),
            )

    def get_staffing_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM staffing_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "request_id": row["request_id"],
            "requester_id": row["requester_id"],
            "shortlist": json.loads(row["shortlist_json"]),
            "status": row["status"],
            "approved_by": row["approved_by"],
            "decided_at": row["decided_at"],
            "chosen_coded_identity": row["chosen_coded_identity"],
            "rejection_reason": row["rejection_reason"],
            "override_note": row["override_note"],
            "engine_rank_of_choice": row["engine_rank_of_choice"],
            "computation_run_id": row["computation_run_id"],
        }

    def append_audit(
        self, event_id: str, event_type: str, actor: str, payload: Mapping[str, Any]
    ) -> Dict[str, str]:
        created_at = utc_now().isoformat()
        with self.session() as conn:
            prev = conn.execute(
                "SELECT row_hash FROM audit_ledger ORDER BY created_at DESC, event_id DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev["row_hash"] if prev else ""
            row_hash = hash_audit_row(prev_hash, event_id, event_type, actor, payload, created_at)
            conn.execute(
                """
                INSERT INTO audit_ledger (
                  event_id, event_type, actor, payload_json, prev_hash, row_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    actor,
                    json.dumps(dict(payload), default=str),
                    prev_hash,
                    row_hash,
                    created_at,
                ),
            )
        return {"prev_hash": prev_hash, "row_hash": row_hash}

    def verify_audit_chain(self) -> List[str]:
        errors: List[str] = []
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_ledger ORDER BY created_at ASC, event_id ASC"
            ).fetchall()
        expected_prev = ""
        for row in rows:
            payload = json.loads(row["payload_json"])
            if row["prev_hash"] != expected_prev:
                errors.append(f"{row['event_id']}: prev_hash mismatch")
            expected = hash_audit_row(
                row["prev_hash"],
                row["event_id"],
                row["event_type"],
                row["actor"],
                payload,
                row["created_at"],
            )
            if row["row_hash"] != expected:
                errors.append(f"{row['event_id']}: row_hash mismatch")
            expected_prev = row["row_hash"]
        return errors

    def pilot_coverage(self) -> Dict[str, Any]:
        with self.session() as conn:
            pop = conn.execute("SELECT COUNT(*) AS n FROM identity_map").fetchone()["n"]
            demo = conn.execute(
                """
                SELECT COUNT(DISTINCT coded_identity) AS n FROM evidence_staging
                WHERE evidence_type = 'demonstrated'
                """
            ).fetchone()["n"]
        pct = (demo / pop * 100.0) if pop else 0.0
        return {"pilot_size": pop, "with_demonstrated": demo, "coverage_pct": round(pct, 2)}

    def is_direct_report(self, manager_coded_id: str, report_coded_id: str) -> bool:
        with self.session() as conn:
            row = conn.execute(
                "SELECT 1 FROM org_edges WHERE manager_coded_id=? AND report_coded_id=?",
                (manager_coded_id, report_coded_id),
            ).fetchone()
        return row is not None

    def add_org_edge(self, manager_coded_id: str, report_coded_id: str) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO org_edges (manager_coded_id, report_coded_id) VALUES (?, ?)",
                (manager_coded_id, report_coded_id),
            )

    def resolve_coded_for_source(self, employee_key: str) -> Optional[str]:
        src = self.source_hash(employee_key)
        with self.session() as conn:
            row = conn.execute(
                "SELECT coded_identity FROM identity_map WHERE source_hash=?",
                (src,),
            ).fetchone()
        return row["coded_identity"] if row else None

    def record_staffing_decision(
        self,
        request_id: str,
        status: str,
        approved_by: str,
        chosen_coded_identity: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        override_note: Optional[str] = None,
        engine_rank_of_choice: Optional[int] = None,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                UPDATE staffing_requests SET
                  status=?, approved_by=?, decided_at=?, chosen_coded_identity=?,
                  rejection_reason=?, override_note=?, engine_rank_of_choice=?
                WHERE request_id=?
                """,
                (
                    status,
                    approved_by,
                    utc_now().isoformat(),
                    chosen_coded_identity,
                    rejection_reason,
                    override_note,
                    engine_rank_of_choice,
                    request_id,
                ),
            )

    def add_contest(
        self, contest_id: str, coded_identity: str, skill_id: Optional[str], reason: str
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO evidence_contests (contest_id, coded_identity, skill_id, reason)
                VALUES (?, ?, ?, ?)
                """,
                (contest_id, coded_identity, skill_id, reason),
            )

    def evidence_for_identity(self, coded_identity: str) -> List[Dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence_staging WHERE coded_identity = ? ORDER BY occurred_at DESC",
                (coded_identity,),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_account_context(
        self,
        coded_identity: str,
        account_label: str,
        familiarity_raw: Optional[float],
        source_sheet: str,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO account_context (coded_identity, account_label, familiarity_raw, source_sheet)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(coded_identity, account_label) DO UPDATE SET
                  familiarity_raw=excluded.familiarity_raw,
                  source_sheet=excluded.source_sheet,
                  ingested_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                """,
                (coded_identity, account_label, familiarity_raw, source_sheet),
            )

    def insert_baseline(
        self,
        baseline_id: str,
        coded_identity: str,
        raw_label: str,
        raw_value: Optional[float],
        normalised_level: Optional[int],
        source_sheet: str,
        source_scale: str,
        skill_id: Optional[str] = None,
        assessed_at: Optional[str] = None,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO baseline_assessments (
                  baseline_id, coded_identity, skill_id, raw_label, raw_value,
                  normalised_level, source_sheet, source_scale, assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(baseline_id) DO UPDATE SET
                  skill_id=excluded.skill_id,
                  raw_value=excluded.raw_value,
                  normalised_level=excluded.normalised_level
                """,
                (
                    baseline_id,
                    coded_identity,
                    skill_id,
                    raw_label,
                    raw_value,
                    normalised_level,
                    source_sheet,
                    source_scale,
                    assessed_at,
                ),
            )

    def count_baseline(self) -> int:
        with self.session() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM baseline_assessments").fetchone()["n"])

    def clear_baseline(self) -> None:
        with self.session() as conn:
            conn.execute("DELETE FROM baseline_assessments")

