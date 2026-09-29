-- Project Hermes SQLite schema (local-first, hardened)
-- Classification: Internal, Confidential
-- NOTE: No protected demographic attributes are permitted in this schema.

PRAGMA foreign_keys = ON;

-- Database trust + integrity metadata (data_classification, identity secret
-- fingerprint, audit anchor adoption). Never holds secrets or personal data.
CREATE TABLE IF NOT EXISTS hermes_meta (
    key              TEXT NOT NULL PRIMARY KEY,
    value            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_map (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    source_hash      TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS identity_vault (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    display_name     TEXT NOT NULL,
    source_employee_key TEXT NOT NULL,
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
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
    ingested_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
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
    computed_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (coded_identity, skill_id),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS skills_matrix_history (
    history_id               INTEGER PRIMARY KEY AUTOINCREMENT,
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
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS demand_signals (
    skill_id         TEXT NOT NULL PRIMARY KEY,
    demand_weight    REAL NOT NULL CHECK (demand_weight BETWEEN 0 AND 1),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS availability (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    allocation       REAL NOT NULL DEFAULT 1.0 CHECK (allocation BETWEEN 0 AND 1),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS audit_ledger (
    event_id         TEXT NOT NULL PRIMARY KEY,
    event_type       TEXT NOT NULL,
    actor            TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    prev_hash        TEXT NOT NULL DEFAULT '',
    row_hash         TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
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
    -- Machine-readable exclusion reasons captured at ranking time; used to reject
    -- decisions that pick an excluded candidate.
    excluded_json    TEXT NOT NULL DEFAULT '[]',
    -- Verbatim ranking response and its inputs (UI read model; never recomputed).
    result_json      TEXT NOT NULL DEFAULT '{}',
    requirements_json TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS evidence_contests (
    contest_id       TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    skill_id         TEXT,
    reason           TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'open',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS IX_audit_type_time ON audit_ledger(event_type, created_at);
CREATE INDEX IF NOT EXISTS IX_evidence_identity ON evidence_staging(coded_identity);
CREATE INDEX IF NOT EXISTS IX_matrix_skill ON skills_matrix(skill_id);
CREATE INDEX IF NOT EXISTS IX_matrix_history_run ON skills_matrix_history(computation_run_id);


-- Phase 8: client familiarity (never used in fitness scoring)
CREATE TABLE IF NOT EXISTS account_context (
    coded_identity   TEXT NOT NULL,
    account_label    TEXT NOT NULL,
    familiarity_raw  REAL,
    source_sheet     TEXT NOT NULL,
    ingested_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (coded_identity, account_label),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

-- Phase 8: manager-assessed baseline (isolated from scoring path)
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
    ingested_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS skill_aliases (
    alias_label      TEXT NOT NULL PRIMARY KEY,
    skill_id         TEXT NOT NULL,
    match_confidence REAL NOT NULL CHECK (match_confidence BETWEEN 0 AND 1),
    mapped_by        TEXT NOT NULL,
    mapped_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS manager_aliases (
    alias_name       TEXT NOT NULL PRIMARY KEY,
    canonical_name   TEXT NOT NULL,
    mapped_by        TEXT NOT NULL,
    mapped_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS cert_staging (
    staging_id       TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    cert_label       TEXT NOT NULL,
    cert_code        TEXT,
    earned_at        TEXT,
    source_sheet     TEXT NOT NULL DEFAULT 'Certificates',
    promoted         INTEGER NOT NULL DEFAULT 0,
    ingested_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE INDEX IF NOT EXISTS IX_baseline_identity ON baseline_assessments(coded_identity);
CREATE INDEX IF NOT EXISTS IX_baseline_skill ON baseline_assessments(skill_id);

-- Phase 8: one row per governed real-workbook ingestion. Aggregate counts ONLY
-- (no names, no raw rows, no client labels) so the data-quality view can be
-- served from the database rather than from files or hardcoded numbers.
CREATE TABLE IF NOT EXISTS phase8_ingest_runs (
    run_id           TEXT NOT NULL PRIMARY KEY,
    source_name      TEXT NOT NULL,
    source_sha256    TEXT NOT NULL,
    ingested_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    summary_json     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS principal_bindings (
    sub              TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    mapped_by        TEXT NOT NULL,
    mapped_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);
