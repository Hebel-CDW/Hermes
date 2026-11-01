"""Persistence for Hermes — SQLite (development, default) or PostgreSQL
(production), selected by DATABASE_URL.

Dialect boundary, kept deliberately small: a connection-level shim
(_PgConnection) makes a psycopg2 connection look enough like a sqlite3
connection — same `.execute()`/`.executemany()`/`.commit()`/`.rollback()`/
`.close()` surface, dict-like rows via RealDictCursor — that every one of the
~80 query call sites below is UNCHANGED for the SQLite path and needs no
per-site rewrite for the PostgreSQL path either, except the handful that
embed a SQLite-only SQL function (`strftime`, `PRAGMA table_info`,
`executescript`) directly in the SQL text — those are explicitly dialect-
branched at each call site, not hidden inside the shim.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from shared.errors import ConfigurationError, RequestOwnershipError, RequestStateConflict
from shared.models import (
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    SkillRecord,
    utc_now,
)

#: SQLite's strftime('%Y-%m-%dT%H:%M:%fZ','now') and this produce byte-identical
#: 'YYYY-MM-DDTHH:MM:SS.mmmZ' strings — verified against a running instance of
#: each during the Postgres migration spike. Used only in the handful of SQL
#: strings that embed a "now" default/update directly (see _now_sql below);
#: everywhere else a timestamp is supplied, it comes from Python (utc_now()).
_NOW_SQL_POSTGRES = "to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"')"
_NOW_SQL_SQLITE = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def _resolve_dialect(database_url: Optional[str]) -> str:
    if not database_url:
        return "sqlite"
    scheme = urlparse(database_url).scheme
    if scheme.startswith("postgres"):
        return "postgres"
    if scheme.startswith("sqlite") or scheme == "":
        return "sqlite"
    raise ValueError(f"unsupported DATABASE_URL scheme: {scheme!r} (expected sqlite:// or postgresql://)")


def default_db_path() -> Path:
    env = os.getenv("HERMES_DB_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "hermes.db"


def extra_schema_paths(dialect: str = "sqlite") -> List[Path]:
    """Ordered additive migrations (002_*.sql, 003_*.sql ...) applied after the base schema."""
    root = Path(__file__).resolve().parents[2] / "infra" / ("postgres" if dialect == "postgres" else "sqlite")
    return sorted(p for p in root.glob("[0-9][0-9][0-9]_*.sql") if not p.name.startswith("001_"))


def schema_path(dialect: str = "sqlite") -> Path:
    root = Path(__file__).resolve().parents[2] / "infra"
    return (root / "postgres" / "001_schema.sql") if dialect == "postgres" else (root / "sqlite" / "001_schema.sql")


class _PgConnection:
    """Makes a psycopg2 connection look enough like a sqlite3.Connection for
    every call site below to work unmodified: `.execute()` returns a cursor
    you can `.fetchone()`/`.fetchall()`/iterate exactly as before, with
    dict-like row access (RealDictCursor), and `?` placeholders are translated
    to psycopg2's `%s` — verified safe (no literal '?' appears inside any SQL
    string literal in this file) rather than assumed.
    """

    def __init__(self, raw_conn: Any) -> None:
        self._conn = raw_conn

    @staticmethod
    def _adapt(sql: str) -> str:
        if sql.startswith("PRAGMA table_info("):
            table = sql[len("PRAGMA table_info("):-1]
            return (
                "SELECT column_name AS name FROM information_schema.columns "
                f"WHERE table_name = '{table}' ORDER BY ordinal_position"
            )
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: Sequence[Any] = ()):
        import psycopg2.extras

        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(self._adapt(sql), tuple(params) if params else None)
        return cur

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]):
        cur = self._conn.cursor()
        cur.executemany(self._adapt(sql), [tuple(p) for p in seq_of_params])
        return cur

    def executescript(self, sql: str) -> None:
        # The Postgres schema file contains only CREATE TABLE/INDEX statements
        # (no PL/pgSQL, no semicolons-in-strings) — but comment lines in the
        # schema file's header DO contain a literal ';' (inside backticked
        # example SQL), which broke a naive split before comments were
        # stripped first. Found by actually applying
        # infra/postgres/001_schema.sql to a real instance, not assumed safe.
        cur = self._conn.cursor()
        code_only = "\n".join(
            line for line in sql.splitlines() if not line.strip().startswith("--")
        )
        for statement in code_only.split(";"):
            statement = statement.strip()
            if statement:
                cur.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


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



_BASELINE_UPSERT = """
INSERT INTO baseline_assessments (
  baseline_id, coded_identity, skill_id, raw_label, raw_value,
  normalised_level, source_sheet, source_scale, assessed_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(baseline_id) DO UPDATE SET
  skill_id=excluded.skill_id,
  raw_value=excluded.raw_value,
  normalised_level=excluded.normalised_level
"""

#: {now_sql} is filled in per-dialect at the call site (HermesDB._now_sql()).
_ACCOUNT_CONTEXT_UPSERT = """
INSERT INTO account_context (coded_identity, account_label, familiarity_raw, source_sheet)
VALUES (?, ?, ?, ?)
ON CONFLICT(coded_identity, account_label) DO UPDATE SET
  familiarity_raw=excluded.familiarity_raw,
  source_sheet=excluded.source_sheet,
  ingested_at={now_sql}
"""

class HermesDB:
    def __init__(self, path: Optional[Path] = None, database_url: Optional[str] = None) -> None:
        # An explicit `path` always means SQLite, regardless of an ambient
        # DATABASE_URL — every existing caller (tests included) passes `path`
        # positionally and must keep getting exactly the SQLite behavior they
        # already had. Only when neither is given does the environment decide.
        if path is not None:
            self.database_url = None
            self.dialect = "sqlite"
        else:
            self.database_url = database_url or os.getenv("DATABASE_URL")
            self.dialect = _resolve_dialect(self.database_url)
        if self.dialect == "postgres":
            self.path = None
        else:
            self.path = Path(path) if path else default_db_path()
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self):
        if self.dialect == "postgres":
            import psycopg2

            return _PgConnection(psycopg2.connect(self.database_url))
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _now_sql(self) -> str:
        return _NOW_SQL_POSTGRES if self.dialect == "postgres" else _NOW_SQL_SQLITE

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
        ddl = schema_path(self.dialect).read_text(encoding="utf-8")
        with self.session() as conn:
            conn.executescript(ddl)
            for extra in extra_schema_paths(self.dialect):
                conn.executescript(extra.read_text(encoding="utf-8"))
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(staffing_requests)")}
            if "excluded_json" not in cols:
                conn.execute(
                    "ALTER TABLE staffing_requests ADD COLUMN excluded_json TEXT NOT NULL DEFAULT '[]'"
                )
            # Read models for the UI: the exact ranking payload and its inputs, stored
            # verbatim so detail views never recompute or re-rank.
            for col in ("result_json", "requirements_json"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE staffing_requests ADD COLUMN {col} TEXT NOT NULL DEFAULT '{{}}'")
        self._migrate_audit_seq()
        self._ensure_audit_anchor()
        self._ensure_principal_bindings()

    def _ensure_principal_bindings(self) -> None:
        # Also defined in both schema files now; this idempotent IF NOT EXISTS
        # is a harmless pre-existing redundancy, kept as-is rather than removed
        # in a migration spike whose job is dialect compatibility, not cleanup.
        with self.session() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS principal_bindings (
                    sub              TEXT NOT NULL PRIMARY KEY,
                    coded_identity   TEXT NOT NULL,
                    mapped_by        TEXT NOT NULL,
                    mapped_at        TEXT NOT NULL DEFAULT ({self._now_sql()}),
                    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
                )
                """
            )
    def get_meta(self, key: str) -> Optional[str]:
        with self.session() as conn:
            row = conn.execute("SELECT value FROM hermes_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO hermes_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # ------------------------------------------------------------ audit anchor
    @property
    def label(self) -> str:
        """Safe, non-secret identifier for logs/errors — never credentials."""
        if self.dialect == "postgres":
            parsed = urlparse(self.database_url)
            return f"{parsed.hostname}:{parsed.port}{parsed.path}"
        return self.path.name

    def anchor_path(self) -> Path:
        """Location of the external integrity anchor for this database.

        Defaults to ``<db>.audit-anchor.json`` beside the database. Set
        ``HERMES_AUDIT_ANCHOR_DIR`` to keep anchors on storage the database writer
        cannot modify — the anchor only defends against tampering by someone who
        cannot also rewrite it.
        """
        anchor_dir = os.getenv("HERMES_AUDIT_ANCHOR_DIR", "").strip()
        if self.dialect == "postgres":
            # No filesystem path exists "beside" a network database, so the
            # anchor directory cannot be optional here the way it is for
            # SQLite — fail closed rather than silently skip tamper evidence.
            if not anchor_dir:
                raise ConfigurationError(
                    "HERMES_AUDIT_ANCHOR_DIR is required when DATABASE_URL is a PostgreSQL URL"
                )
            parsed = urlparse(self.database_url)
            identity = f"{parsed.hostname}:{parsed.port}{parsed.path}"  # never the credentials
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            return Path(anchor_dir) / f"{digest}.audit-anchor.json"
        if anchor_dir:
            digest = hashlib.sha256(str(self.path.resolve()).encode("utf-8")).hexdigest()[:24]
            return Path(anchor_dir) / f"{digest}.audit-anchor.json"
        return self.path.with_name(self.path.name + ".audit-anchor.json")

    @staticmethod
    def _anchor_key() -> bytes:
        key = os.getenv("HERMES_AUDIT_ANCHOR_KEY") or os.getenv("IDENTITY_MAP_SECRET") or ""
        return key.encode("utf-8")

    @classmethod
    def _sign_anchor(cls, body: Mapping[str, Any]) -> Optional[str]:
        key = cls._anchor_key()
        if not key:
            return None
        return hmac.new(key, _canonical_json(body).encode("utf-8"), hashlib.sha256).hexdigest()

    def _chain_state(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        head = conn.execute(
            "SELECT seq, row_hash FROM audit_ledger ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        count = conn.execute("SELECT COUNT(*) AS n FROM audit_ledger").fetchone()["n"]
        return {
            "seq": int(head["seq"]) if head and head["seq"] is not None else 0,
            "chain_head": head["row_hash"] if head else "",
            "event_count": int(count),
        }

    def _write_anchor(self, state: Mapping[str, Any]) -> None:
        path = self.anchor_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._read_anchor()
        if existing and int(existing.get("seq", 0)) > int(state["seq"]):
            return  # never move the anchor backwards
        body = {
            "seq": int(state["seq"]),
            "chain_head": state["chain_head"],
            "event_count": int(state["event_count"]),
            "updated_at": utc_now().isoformat(),
        }
        doc = dict(body, signature=self._sign_anchor(body))
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _read_anchor(self) -> Optional[Dict[str, Any]]:
        path = self.anchor_path()
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _ensure_audit_anchor(self) -> None:
        """Create the anchor exactly once per database (explicit, recorded adoption).

        If the anchor is missing but the database records that one was already
        established, the anchor has been removed — ``verify_audit_chain`` reports it.
        """
        if self.anchor_path().is_file() or self.get_meta("audit_anchor_initialised"):
            return
        with self.session() as conn:
            state = self._chain_state(conn)
        self._write_anchor(state)
        self.set_meta("audit_anchor_initialised", utc_now().isoformat())

    def _migrate_audit_seq(self) -> None:
        """Give audit_ledger a monotonic `seq` and backfill it (G-2).

        The chain used to be ordered by (created_at, event_id) with random UUID
        event ids, so two events sharing a timestamp could replay in a different
        order than they were written and fail verification. `seq` is allocated
        inside an exclusive-locked transaction at append time and is the only
        ordering the verifier trusts. Existing rows are backfilled in rowid
        order, which is SQLite's insertion order for this table — PostgreSQL has
        no equivalent (no implicit row-order column), so this backfill only
        runs against SQLite. A fresh PostgreSQL database's schema already
        defines `seq` (infra/postgres/001_schema.sql), so there is nothing to
        backfill there; migrating pre-existing SQLite audit history into
        PostgreSQL is the dedicated SQLite->Postgres migration tool's job
        (it copies seq values directly, preserving order explicitly rather
        than inferring it).
        """
        with self.session() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(audit_ledger)")}
            if "seq" not in cols:
                conn.execute("ALTER TABLE audit_ledger ADD COLUMN seq INTEGER")
            if self.dialect == "sqlite":
                missing = conn.execute(
                    "SELECT rowid FROM audit_ledger WHERE seq IS NULL ORDER BY rowid"
                ).fetchall()
                if missing:
                    start = conn.execute(
                        "SELECT COALESCE(MAX(seq), 0) AS m FROM audit_ledger"
                    ).fetchone()["m"]
                    for offset, row in enumerate(missing, start=1):
                        conn.execute(
                            "UPDATE audit_ledger SET seq = ? WHERE rowid = ?",
                            (start + offset, row["rowid"]),
                        )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS UX_audit_seq ON audit_ledger(seq)"
            )

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
                f"""
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
                  updated_at={self._now_sql()}
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

    def list_identity_directory(self) -> List[Dict[str, str]]:
        """Synthetic demo overlay: vault names keyed by coded identity. Not a scoring input."""
        with self.session() as conn:
            # Portable case-insensitive ordering: SQLite's COLLATE NOCASE is
            # ASCII-only case folding, which lower() matches exactly on both
            # dialects (Postgres has no NOCASE collation) — genuine dialect
            # bug found via a real Postgres test-parity run.
            rows = conn.execute(
                "SELECT coded_identity, display_name FROM identity_vault ORDER BY lower(display_name)"
            ).fetchall()
        return [{"coded_identity": r["coded_identity"], "display_name": r["display_name"]} for r in rows]

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
            # Full delete-then-reinsert of a derived table: two concurrent callers
            # must never interleave, or the second's unqualified DELETE can miss
            # rows the first just committed (each transaction's DELETE only sees
            # its own as-of-start snapshot under READ COMMITTED), and the second's
            # INSERT then collides with the first's still-present row — a real
            # psycopg2.errors.UniqueViolation on skills_matrix_pkey, found via a
            # live concurrent /api/team/declare test against PostgreSQL during
            # this migration spike. SQLite's whole-database IMMEDIATE lock already
            # serializes this; PostgreSQL needs the same explicit table lock
            # append_audit() uses for the same reason.
            if self.dialect == "postgres":
                conn.execute("LOCK TABLE skills_matrix IN SHARE ROW EXCLUSIVE MODE")
            else:
                conn.execute("BEGIN IMMEDIATE")
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
                computation_run_id=(
                    row["computation_run_id"]
                    if "computation_run_id" in row.keys() and row["computation_run_id"]
                    else ""
                ),
            )
            for row in rows
        ]

    def evidence_source_refs_by_skill(self) -> Dict[tuple, List[str]]:
        """(coded_identity, skill_id) -> distinct source_refs, for the inspector.

        Keyed per person, not per skill: a candidate's drill-down must cite only
        that candidate's own evidence. Source refs are ticket numbers / cert codes
        already persisted on evidence_staging — no ticket text is stored or
        returned (Guardrail 12).
        """
        with self.session() as conn:
            rows = conn.execute(
                "SELECT DISTINCT coded_identity, skill_id, source_ref FROM evidence_staging "
                "WHERE skill_id IS NOT NULL ORDER BY coded_identity, skill_id, source_ref"
            ).fetchall()
        out: Dict[tuple, List[str]] = {}
        for row in rows:
            out.setdefault((row["coded_identity"], row["skill_id"]), []).append(
                row["source_ref"]
            )
        return out

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
                    f"""
                    INSERT INTO demand_signals (skill_id, demand_weight)
                    VALUES (?, ?)
                    ON CONFLICT(skill_id) DO UPDATE SET
                      demand_weight=excluded.demand_weight,
                      updated_at={self._now_sql()}
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
                f"""
                INSERT INTO role_profiles (
                  role_id, role_name, required_skills_json, critical_skills_json, min_coverage_ratio
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(role_id) DO UPDATE SET
                  role_name=excluded.role_name,
                  required_skills_json=excluded.required_skills_json,
                  critical_skills_json=excluded.critical_skills_json,
                  min_coverage_ratio=excluded.min_coverage_ratio,
                  updated_at={self._now_sql()}
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
                f"""
                INSERT INTO availability (coded_identity, allocation)
                VALUES (?, ?)
                ON CONFLICT(coded_identity) DO UPDATE SET
                  allocation=excluded.allocation,
                  updated_at={self._now_sql()}
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
        excluded: Optional[Sequence[Mapping[str, Any]]] = None,
        result: Optional[Mapping[str, Any]] = None,
        requirements: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Create a request, or update the ranking of an open request the caller owns.

        Ownership is immutable: ``requester_id`` is written once on insert and is never
        part of the update clause. The update is conditioned on the stored owner and
        an ``open`` status inside one statement, so a second principal reusing a
        request_id cannot take it over even under concurrent writes.
        """
        excluded_json = json.dumps(list(excluded or []), default=str)
        result_json = json.dumps(dict(result or {}), default=str)
        requirements_json = json.dumps(dict(requirements or {}), default=str)
        with self.session() as conn:
            # SQLite: take the write lock before the ownership-guarded UPSERT below.
            # PostgreSQL: a plain transaction is sufficient here — the UPSERT's own
            # WHERE guard (requester_id/status) is already atomic at the row level
            # without needing a table-wide lock, verified against a real instance.
            if self.dialect == "sqlite":
                conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """
                INSERT INTO staffing_requests (
                  request_id, requester_id, shortlist_json, computation_run_id, status, excluded_json,
                  result_json, requirements_json
                )
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                  shortlist_json=excluded.shortlist_json,
                  computation_run_id=excluded.computation_run_id,
                  excluded_json=excluded.excluded_json,
                  result_json=excluded.result_json,
                  requirements_json=excluded.requirements_json
                WHERE staffing_requests.requester_id = excluded.requester_id
                  AND staffing_requests.status = 'open'
                """,
                (
                    request_id,
                    requester_id,
                    json.dumps(list(shortlist)),
                    computation_run_id,
                    excluded_json,
                    result_json,
                    requirements_json,
                ),
            )
            if cur.rowcount == 1:
                return
            row = conn.execute(
                "SELECT requester_id, status FROM staffing_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is not None and row["requester_id"] != requester_id:
            raise RequestOwnershipError("staffing request is owned by another principal")
        raise RequestStateConflict("staffing request is no longer open")

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
            "excluded": json.loads(row["excluded_json"] or "[]")
            if "excluded_json" in row.keys()
            else [],
            "result": json.loads(row["result_json"] or "{}") if "result_json" in row.keys() else {},
            "requirements": json.loads(row["requirements_json"] or "{}")
            if "requirements_json" in row.keys()
            else {},
            "created_at": row["created_at"],
        }

    def list_staffing_requests(self, requester_id: str) -> List[Dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT request_id FROM staffing_requests WHERE requester_id = ? "
                "ORDER BY created_at DESC, request_id",
                (requester_id,),
            ).fetchall()
        return [self.get_staffing_request(r["request_id"]) for r in rows]

    def append_audit(
        self, event_id: str, event_type: str, actor: str, payload: Mapping[str, Any]
    ) -> Dict[str, str]:
        created_at = utc_now().isoformat()
        with self.session() as conn:
            # Both forms serialize concurrent appenders before reading the chain
            # head, so two writers cannot both read the same predecessor and
            # fork the chain — SQLite's whole-database IMMEDIATE lock, or an
            # explicit PostgreSQL table lock acquired as the transaction's
            # first statement (verified under real concurrent writers against
            # a running PostgreSQL instance during this migration spike).
            if self.dialect == "postgres":
                conn.execute("LOCK TABLE audit_ledger IN SHARE ROW EXCLUSIVE MODE")
            else:
                conn.execute("BEGIN IMMEDIATE")
            prev = conn.execute(
                "SELECT row_hash, seq FROM audit_ledger ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev["row_hash"] if prev else ""
            seq = (int(prev["seq"]) if prev and prev["seq"] is not None else 0) + 1
            row_hash = hash_audit_row(prev_hash, event_id, event_type, actor, payload, created_at)
            conn.execute(
                """
                INSERT INTO audit_ledger (
                  event_id, event_type, actor, payload_json, prev_hash, row_hash, created_at, seq
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    actor,
                    json.dumps(dict(payload), default=str),
                    prev_hash,
                    row_hash,
                    created_at,
                    seq,
                ),
            )
            state = self._chain_state(conn)
        # Anchor is written only after the event is durably committed.
        self._write_anchor(state)
        return {"prev_hash": prev_hash, "row_hash": row_hash, "seq": str(seq)}

    def verify_audit_chain(self) -> List[str]:
        errors: List[str] = []
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_ledger ORDER BY seq ASC"
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
        errors.extend(self._verify_anchor(rows))
        return errors

    def _verify_anchor(self, rows: Sequence[sqlite3.Row]) -> List[str]:
        """Compare the ledger with the external anchor.

        Detects what a hash chain alone cannot: deletion of the most recent events,
        deletion of every event, and a chain recomputed end-to-end after tampering.
        """
        errors: List[str] = []
        anchor = self._read_anchor()
        if anchor is None:
            if rows or self.get_meta("audit_anchor_initialised"):
                errors.append("anchor: external integrity anchor is missing")
            return errors
        body = {k: anchor.get(k) for k in ("seq", "chain_head", "event_count", "updated_at")}
        expected_sig = self._sign_anchor(body)
        if expected_sig is not None and anchor.get("signature") != expected_sig:
            errors.append("anchor: signature invalid (anchor forged or signed with a different key)")
        head_seq = int(rows[-1]["seq"]) if rows else 0
        head_hash = rows[-1]["row_hash"] if rows else ""
        if len(rows) != int(anchor.get("event_count", -1)):
            errors.append(
                f"anchor: event count {len(rows)} != anchored {anchor.get('event_count')} "
                "(events deleted or inserted)"
            )
        if head_seq < int(anchor.get("seq", 0)):
            errors.append(
                f"anchor: ledger head seq {head_seq} is behind anchored seq {anchor.get('seq')} "
                "(most recent events deleted)"
            )
        elif head_hash != anchor.get("chain_head"):
            errors.append("anchor: chain head hash differs from anchor (chain rewritten)")
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
        # Portable form (SQLite and PostgreSQL both support this upsert syntax) —
        # "INSERT OR IGNORE" was SQLite-only and the one genuine dialect bug this
        # migration spike's own test-parity run caught that static forensics missed.
        with self.session() as conn:
            conn.execute(
                "INSERT INTO org_edges (manager_coded_id, report_coded_id) VALUES (?, ?) "
                "ON CONFLICT (manager_coded_id, report_coded_id) DO NOTHING",
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
        """Write a decision atomically: only the owner, only while the request is open."""
        with self.session() as conn:
            cur = conn.execute(
                """
                UPDATE staffing_requests SET
                  status=?, approved_by=?, decided_at=?, chosen_coded_identity=?,
                  rejection_reason=?, override_note=?, engine_rank_of_choice=?
                WHERE request_id=? AND requester_id=? AND status='open'
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
                    approved_by,
                ),
            )
            if cur.rowcount != 1:
                raise RequestStateConflict("request is not open for a decision by this principal")

    def direct_reports(self, manager_coded_id: str) -> List[str]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT report_coded_id FROM org_edges WHERE manager_coded_id = ? ORDER BY 1",
                (manager_coded_id,),
            ).fetchall()
        return [r["report_coded_id"] for r in rows]

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

    def has_coded_identity(self, coded_identity: str) -> bool:
        with self.session() as conn:
            row = conn.execute(
                "SELECT 1 FROM identity_map WHERE coded_identity = ?",
                (coded_identity,),
            ).fetchone()
        return row is not None

    def list_open_contests(self, coded_identity: str) -> List[Dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT contest_id, coded_identity, skill_id, reason, status, created_at
                FROM evidence_contests
                WHERE coded_identity = ? AND status = 'open'
                ORDER BY created_at
                """,
                (coded_identity,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_contest(self, contest_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT contest_id, coded_identity, skill_id, reason, status, created_at "
                "FROM evidence_contests WHERE contest_id = ?",
                (contest_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_contest_status(self, contest_id: str, status: str) -> None:
        with self.session() as conn:
            cur = conn.execute(
                "UPDATE evidence_contests SET status = ? WHERE contest_id = ? AND status = 'open'",
                (status, contest_id),
            )
            if cur.rowcount != 1:
                raise RequestStateConflict("contest is not open for this principal")

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
        self.upsert_account_contexts([(coded_identity, account_label, familiarity_raw, source_sheet)])

    def upsert_account_contexts(self, rows: Sequence[Tuple[str, str, Optional[float], str]]) -> None:
        """Write many account-context rows in ONE transaction (all or nothing)."""
        if not rows:
            return
        with self.session() as conn:
            conn.executemany(_ACCOUNT_CONTEXT_UPSERT.format(now_sql=self._now_sql()), list(rows))

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
        self.insert_baselines(
            [(baseline_id, coded_identity, skill_id, raw_label, raw_value, normalised_level, source_sheet, source_scale, assessed_at)]
        )

    def insert_baselines(self, rows: Sequence[Tuple[Any, ...]]) -> None:
        """Write many baseline rows in ONE transaction (all or nothing).

        Row order: baseline_id, coded_identity, skill_id, raw_label, raw_value,
        normalised_level, source_sheet, source_scale, assessed_at.
        """
        if not rows:
            return
        with self.session() as conn:
            conn.executemany(_BASELINE_UPSERT, list(rows))

    def insert_cert_stagings(self, rows: Sequence[Tuple[str, str, str, Optional[str]]]) -> None:
        """Stage certificates in ONE transaction: (staging_id, coded_identity, cert_label, cert_code).

        ``earned_at`` is always NULL here — dates are never invented at ingestion.
        """
        if not rows:
            return
        with self.session() as conn:
            conn.executemany(
                """
                INSERT INTO cert_staging (
                  staging_id, coded_identity, cert_label, cert_code, earned_at, source_sheet, promoted
                ) VALUES (?, ?, ?, ?, NULL, 'Certificates', 0)
                ON CONFLICT(staging_id) DO UPDATE SET
                  cert_code = COALESCE(cert_staging.cert_code, excluded.cert_code)
                """,
                list(rows),
            )

    def record_ingest_run(self, run_id: str, source_name: str, source_sha256: str, summary: Mapping[str, Any]) -> None:
        """Persist an aggregate-only ingestion summary (counts, codes; never names or raw rows)."""
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO phase8_ingest_runs (run_id, source_name, source_sha256, summary_json)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, source_name, source_sha256, json.dumps(summary, sort_keys=True)),
            )

    def latest_ingest_run(self) -> Optional[Dict[str, Any]]:
        # rowid is SQLite-only; a real-data ingestion run happens at most a few
        # times ever, so a timestamp tie is not realistically expected, and
        # this table has no bearing on scoring or audit determinism either way.
        order = "ingested_at DESC, rowid DESC" if self.dialect == "sqlite" else "ingested_at DESC"
        with self.session() as conn:
            row = conn.execute(
                "SELECT run_id, source_name, source_sha256, ingested_at, summary_json "
                f"FROM phase8_ingest_runs ORDER BY {order} LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "source_name": row["source_name"],
            "source_sha256": row["source_sha256"],
            "ingested_at": row["ingested_at"],
            "summary": json.loads(row["summary_json"]),
        }

    def count_baseline(self) -> int:
        with self.session() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM baseline_assessments").fetchone()["n"])

    def clear_baseline(self) -> None:
        with self.session() as conn:
            conn.execute("DELETE FROM baseline_assessments")

    def count_pending_aliases(self) -> int:
        with self.session() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM skill_aliases WHERE mapped_by = 'pending'"
            ).fetchone()
        return int(row["n"])

    def upsert_skill_alias(
        self, alias_label: str, skill_id: str, match_confidence: float, mapped_by: str
    ) -> None:
        with self.session() as conn:
            conn.execute(
                f"""
                INSERT INTO skill_aliases (alias_label, skill_id, match_confidence, mapped_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(alias_label) DO UPDATE SET
                  skill_id=excluded.skill_id,
                  match_confidence=excluded.match_confidence,
                  mapped_by=excluded.mapped_by,
                  mapped_at={self._now_sql()}
                """,
                (alias_label, skill_id, match_confidence, mapped_by),
            )

    def get_manager_alias(self, alias_name: str):
        with self.session() as conn:
            return conn.execute(
                "SELECT * FROM manager_aliases WHERE alias_name = ?",
                (alias_name.strip().lower(),),
            ).fetchone()

    def upsert_manager_alias(self, alias_name: str, canonical_name: str, mapped_by: str) -> None:
        with self.session() as conn:
            conn.execute(
                f"""
                INSERT INTO manager_aliases (alias_name, canonical_name, mapped_by)
                VALUES (?, ?, ?)
                ON CONFLICT(alias_name) DO UPDATE SET
                  canonical_name=excluded.canonical_name,
                  mapped_by=excluded.mapped_by,
                  mapped_at={self._now_sql()}
                """,
                (alias_name.strip().lower(), canonical_name, mapped_by),
            )

    def list_pending_aliases(self) -> List[Dict[str, str]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT alias_label, skill_id, mapped_by, mapped_at FROM skill_aliases "
                "WHERE mapped_by = 'pending' ORDER BY alias_label"
            ).fetchall()
        return [dict(r) for r in rows]

    def bind_principal(self, sub: str, coded_identity: str, mapped_by: str) -> None:
        with self.session() as conn:
            conn.execute(
                f"""
                INSERT INTO principal_bindings (sub, coded_identity, mapped_by)
                VALUES (?, ?, ?)
                ON CONFLICT(sub) DO UPDATE SET
                  coded_identity=excluded.coded_identity,
                  mapped_by=excluded.mapped_by,
                  mapped_at={self._now_sql()}
                """,
                (sub, coded_identity, mapped_by),
            )

    def coded_for_principal(self, sub: str) -> Optional[str]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT coded_identity FROM principal_bindings WHERE sub = ?", (sub,)
            ).fetchone()
        return row["coded_identity"] if row else None

    def rebind_baseline_skill_ids(self, alias_label: str, skill_id: str) -> int:
        """Point isolated baseline rows at a newly approved skill. Never touches skills_matrix."""
        from phase8.workbook import normalize_label

        key = normalize_label(alias_label)
        with self.session() as conn:
            rows = conn.execute(
                "SELECT baseline_id, raw_label FROM baseline_assessments "
                "WHERE skill_id IS NULL OR skill_id = ''"
            ).fetchall()
            n = 0
            for row in rows:
                if normalize_label(row["raw_label"]) == key:
                    conn.execute(
                        "UPDATE baseline_assessments SET skill_id=? WHERE baseline_id=?",
                        (skill_id, row["baseline_id"]),
                    )
                    n += 1
        return n

    def get_cert_staging(self, staging_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM cert_staging WHERE staging_id=?", (staging_id,)).fetchone()
        return dict(row) if row else None

    def set_cert_earned_at(self, staging_id: str, earned_at: str) -> None:
        with self.session() as conn:
            conn.execute("UPDATE cert_staging SET earned_at=? WHERE staging_id=?", (earned_at, staging_id))

    def mark_cert_promoted(self, staging_id: str, cert_code: Optional[str] = None) -> None:
        with self.session() as conn:
            conn.execute(
                "UPDATE cert_staging SET promoted=1, cert_code=COALESCE(?, cert_code) WHERE staging_id=?",
                (cert_code, staging_id),
            )
