-- Project Hermes PostgreSQL schema — dialect translation of
-- infra/sqlite/001_schema.sql. Every table, column, type, and constraint is
-- preserved exactly. Only genuine syntax differences changed:
--   * strftime('%Y-%m-%dT%H:%M:%fZ','now')  ->  to_char(clock_timestamp() AT TIME ZONE 'UTC', ...)
--     (produces the byte-identical 'YYYY-MM-DDTHH:MM:SS.mmmZ' string SQLite emits —
--     verified against a running SQLite and PostgreSQL side by side during this
--     migration spike — so a column read back by the app is indistinguishable
--     from either backend.)
--   * INTEGER PRIMARY KEY AUTOINCREMENT  ->  BIGINT GENERATED ALWAYS AS IDENTITY
--   * `PRAGMA foreign_keys = ON;` dropped — PostgreSQL always enforces FKs.
-- Classification: Internal, Confidential
-- NOTE: No protected demographic attributes are permitted in this schema.

CREATE TABLE IF NOT EXISTS hermes_meta (
    key              TEXT NOT NULL PRIMARY KEY,
    value            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_map (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    source_hash      TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE TABLE IF NOT EXISTS identity_vault (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    display_name     TEXT NOT NULL,
    source_employee_key TEXT NOT NULL,
    updated_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS org_edges (
    manager_coded_id TEXT NOT NULL,
    report_coded_id  TEXT NOT NULL,
    PRIMARY KEY (manager_coded_id, report_coded_id),
    FOREIGN KEY (manager_coded_id) REFERENCES identity_map(coded_identity),
    FOREIGN KEY (report_coded_id) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS evidence_staging (
    evidence_id      TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    skill_id         TEXT,
    evidence_type    TEXT NOT NULL CHECK (evidence_type IN ('demonstrated','certified','declared')),
    proficiency      INTEGER CHECK (proficiency IS NULL OR (proficiency BETWEEN 1 AND 5)),
    occurred_at      TEXT NOT NULL,
    source_ref       TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    ingested_at      TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS skills_matrix (
    coded_identity           TEXT NOT NULL,
    skill_id                 TEXT NOT NULL,
    proficiency              INTEGER NOT NULL CHECK (proficiency BETWEEN 1 AND 5),
    confidence               REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    freshness                REAL NOT NULL CHECK (freshness BETWEEN 0 AND 1),
    volume_score             REAL NOT NULL DEFAULT 0 CHECK (volume_score BETWEEN 0 AND 1),
    evidence_ids_json        TEXT NOT NULL,
    scoring_config_version   TEXT NOT NULL,
    computation_run_id       TEXT,
    computed_at              TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    PRIMARY KEY (coded_identity, skill_id),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS skills_matrix_history (
    history_id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    computation_run_id       TEXT NOT NULL,
    coded_identity           TEXT NOT NULL,
    skill_id                 TEXT NOT NULL,
    proficiency              INTEGER NOT NULL,
    confidence               REAL NOT NULL,
    freshness                REAL NOT NULL,
    volume_score             REAL NOT NULL DEFAULT 0,
    evidence_ids_json        TEXT NOT NULL,
    scoring_config_version   TEXT NOT NULL,
    valid_from               TEXT NOT NULL,
    valid_to                 TEXT
);

CREATE TABLE IF NOT EXISTS role_profiles (
    role_id          TEXT NOT NULL PRIMARY KEY,
    role_name        TEXT NOT NULL,
    required_skills_json TEXT NOT NULL,
    critical_skills_json TEXT NOT NULL DEFAULT '[]',
    min_coverage_ratio REAL NOT NULL DEFAULT 0.6,
    updated_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE TABLE IF NOT EXISTS demand_signals (
    skill_id         TEXT NOT NULL PRIMARY KEY,
    demand_weight    REAL NOT NULL CHECK (demand_weight BETWEEN 0 AND 1),
    updated_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE TABLE IF NOT EXISTS availability (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    allocation       REAL NOT NULL DEFAULT 1.0 CHECK (allocation BETWEEN 0 AND 1),
    updated_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS audit_ledger (
    event_id         TEXT NOT NULL PRIMARY KEY,
    event_type       TEXT NOT NULL,
    actor            TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    prev_hash        TEXT NOT NULL DEFAULT '',
    row_hash         TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    -- Monotonic chain position; the only ordering verify_audit_chain trusts.
    -- Unique index UX_audit_seq is created in HermesDB._migrate_audit_seq so that
    -- pre-existing databases can be migrated before the index is applied.
    seq              INTEGER
);

CREATE TABLE IF NOT EXISTS staffing_requests (
    request_id       TEXT NOT NULL PRIMARY KEY,
    requester_id     TEXT NOT NULL,
    shortlist_json   TEXT NOT NULL DEFAULT '[]',
    status           TEXT NOT NULL DEFAULT 'open',
    approved_by      TEXT,
    decided_at       TEXT,
    chosen_coded_identity TEXT,
    rejection_reason TEXT,
    override_note    TEXT,
    engine_rank_of_choice INTEGER,
    computation_run_id TEXT,
    excluded_json    TEXT NOT NULL DEFAULT '[]',
    result_json      TEXT NOT NULL DEFAULT '{}',
    requirements_json TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE TABLE IF NOT EXISTS evidence_contests (
    contest_id       TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    skill_id         TEXT,
    reason           TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'open',
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE INDEX IF NOT EXISTS IX_audit_type_time ON audit_ledger(event_type, created_at);
CREATE INDEX IF NOT EXISTS IX_evidence_identity ON evidence_staging(coded_identity);
CREATE INDEX IF NOT EXISTS IX_matrix_skill ON skills_matrix(skill_id);
CREATE INDEX IF NOT EXISTS IX_matrix_history_run ON skills_matrix_history(computation_run_id);

CREATE TABLE IF NOT EXISTS account_context (
    coded_identity   TEXT NOT NULL,
    account_label    TEXT NOT NULL,
    familiarity_raw  REAL,
    source_sheet     TEXT NOT NULL,
    ingested_at      TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    PRIMARY KEY (coded_identity, account_label),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS baseline_assessments (
    baseline_id      TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    skill_id         TEXT,
    raw_label        TEXT NOT NULL,
    raw_value        REAL,
    normalised_level INTEGER CHECK (normalised_level IS NULL OR (normalised_level BETWEEN 1 AND 5)),
    source_sheet     TEXT NOT NULL,
    source_scale     TEXT NOT NULL,
    assessed_at      TEXT,
    ingested_at      TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS skill_aliases (
    alias_label      TEXT NOT NULL PRIMARY KEY,
    skill_id         TEXT NOT NULL,
    match_confidence REAL NOT NULL CHECK (match_confidence BETWEEN 0 AND 1),
    mapped_by        TEXT NOT NULL,
    mapped_at        TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE TABLE IF NOT EXISTS manager_aliases (
    alias_name       TEXT NOT NULL PRIMARY KEY,
    canonical_name   TEXT NOT NULL,
    mapped_by        TEXT NOT NULL,
    mapped_at        TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE TABLE IF NOT EXISTS cert_staging (
    staging_id       TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    cert_label       TEXT NOT NULL,
    cert_code        TEXT,
    earned_at        TEXT,
    source_sheet     TEXT NOT NULL DEFAULT 'Certificates',
    promoted         INTEGER NOT NULL DEFAULT 0,
    ingested_at      TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE INDEX IF NOT EXISTS IX_baseline_identity ON baseline_assessments(coded_identity);
CREATE INDEX IF NOT EXISTS IX_baseline_skill ON baseline_assessments(skill_id);

CREATE TABLE IF NOT EXISTS phase8_ingest_runs (
    run_id           TEXT NOT NULL PRIMARY KEY,
    source_name      TEXT NOT NULL,
    source_sha256    TEXT NOT NULL,
    ingested_at      TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    summary_json     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS principal_bindings (
    sub              TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    mapped_by        TEXT NOT NULL,
    mapped_at        TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

-- PostgreSQL-only: SQLite deployments are always single-process, so they keep
-- shared.rate_limit.RateLimiter's original in-memory bucket unchanged. A
-- multi-instance PostgreSQL deployment needs one shared budget per principal
-- instead of one per replica — confirmed as a real gap via a two-instance
-- test during the PostgreSQL migration spike (the same principal got a full,
-- separate 10-call budget on each replica).
CREATE TABLE IF NOT EXISTS rate_limit_hits (
    limiter_name     TEXT NOT NULL,
    key              TEXT NOT NULL,
    hit_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS IX_rate_limit_hits_lookup ON rate_limit_hits(limiter_name, key, hit_at);
