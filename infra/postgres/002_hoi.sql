-- Hermes Opportunity Intelligence (HOI) — migration 002.
-- Additive only: no existing table is altered. Money is stored as decimal TEXT (never float).
-- Finance-controlled storage is the fin_* tables; their amount columns are encrypted at rest and are
-- read only through hoi.finance.FinanceVault.

CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id   TEXT NOT NULL PRIMARY KEY,
    owner            TEXT NOT NULL,
    client_alias     TEXT NOT NULL,
    name             TEXT NOT NULL,
    stage            TEXT NOT NULL DEFAULT 'intake',
    status           TEXT NOT NULL DEFAULT 'open',
    bid_deadline     TEXT,
    geography        TEXT,
    currency         TEXT NOT NULL CHECK (length(currency) = 3),
    contract_type    TEXT NOT NULL CHECK (contract_type IN ('time_and_materials','fixed_fee','managed_service','blended')),
    duration_months  INTEGER CHECK (duration_months IS NULL OR duration_months BETWEEN 1 AND 120),
    start_date       TEXT,
    end_date         TEXT,
    access_scope     TEXT NOT NULL DEFAULT 'deal_team',
    is_synthetic     INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    updated_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);

CREATE TABLE IF NOT EXISTS opportunity_members (
    opportunity_id   TEXT NOT NULL,
    sub              TEXT NOT NULL,
    member_role      TEXT NOT NULL CHECK (member_role IN ('owner','sales','manager','finance','hr')),
    added_by         TEXT NOT NULL,
    added_at         TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    PRIMARY KEY (opportunity_id, sub),
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
);

CREATE TABLE IF NOT EXISTS opportunity_documents (
    document_id      TEXT NOT NULL PRIMARY KEY,
    opportunity_id   TEXT NOT NULL,
    doc_type         TEXT NOT NULL CHECK (doc_type IN ('rfp','sow','jd')),
    filename         TEXT NOT NULL,
    version          INTEGER NOT NULL,
    mime             TEXT NOT NULL,
    size_bytes       INTEGER NOT NULL CHECK (size_bytes >= 0),
    checksum         TEXT NOT NULL,
    restricted_uri   TEXT NOT NULL,
    scan_status      TEXT NOT NULL,
    text_status      TEXT NOT NULL CHECK (text_status IN ('ok','needs_ocr','empty')),
    uploaded_by      TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
);
CREATE INDEX IF NOT EXISTS IX_opp_docs ON opportunity_documents(opportunity_id);

CREATE TABLE IF NOT EXISTS requirement_versions (
    version_id       TEXT NOT NULL PRIMARY KEY,
    opportunity_id   TEXT NOT NULL,
    version_no       INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','superseded')),
    source_doc_ids_json TEXT NOT NULL DEFAULT '[]',
    parser_version   TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    created_by       TEXT NOT NULL,
    reviewed_by      TEXT,
    approved_by      TEXT,
    approved_at      TEXT,
    content_hash     TEXT,
    notes_json       TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    UNIQUE (opportunity_id, version_no),
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
);

CREATE TABLE IF NOT EXISTS resource_requirements (
    requirement_id   TEXT NOT NULL PRIMARY KEY,
    version_id       TEXT NOT NULL,
    position         INTEGER NOT NULL,
    role_name        TEXT NOT NULL,
    headcount        INTEGER CHECK (headcount IS NULL OR headcount >= 1),
    fte              TEXT,
    location         TEXT,
    start_date       TEXT,
    end_date         TEXT,
    skills_json      TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '{}',
    provenance_json  TEXT NOT NULL DEFAULT '{}',
    origin           TEXT NOT NULL DEFAULT 'extracted',
    FOREIGN KEY (version_id) REFERENCES requirement_versions(version_id)
);
CREATE INDEX IF NOT EXISTS IX_resreq_version ON resource_requirements(version_id);

CREATE TABLE IF NOT EXISTS candidate_shortlists (
    shortlist_id     TEXT NOT NULL PRIMARY KEY,
    match_run_id     TEXT NOT NULL,
    opportunity_id   TEXT NOT NULL,
    version_id       TEXT NOT NULL,
    requirement_id   TEXT NOT NULL,
    coded_identity   TEXT NOT NULL,
    rank             INTEGER NOT NULL,
    fitness_score    DOUBLE PRECISION NOT NULL,
    eligibility      TEXT NOT NULL CHECK (eligibility IN ('eligible','ineligible','unverified')),
    eligibility_json TEXT NOT NULL DEFAULT '{}',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    fitness_run_id   TEXT NOT NULL DEFAULT '',
    staffing_request_id TEXT NOT NULL,
    requested_by     TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
);
CREATE INDEX IF NOT EXISTS IX_shortlist_run ON candidate_shortlists(match_run_id);
CREATE INDEX IF NOT EXISTS IX_shortlist_opp ON candidate_shortlists(opportunity_id);

CREATE TABLE IF NOT EXISTS capacity_snapshots (
    snapshot_id      TEXT NOT NULL PRIMARY KEY,
    match_run_id     TEXT NOT NULL,
    coded_identity   TEXT NOT NULL,
    period           TEXT NOT NULL,
    available_fte    DOUBLE PRECISION NOT NULL,
    source           TEXT NOT NULL,
    captured_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS IX_capacity_run ON capacity_snapshots(match_run_id);

CREATE TABLE IF NOT EXISTS cost_parameters (
    parameter_id     TEXT NOT NULL PRIMARY KEY,
    kind             TEXT NOT NULL CHECK (kind IN ('policy','rate_card')),
    name             TEXT NOT NULL,
    version          INTEGER NOT NULL CHECK (version >= 1),
    status           TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('draft','approved')),
    payload_json     TEXT NOT NULL,
    effective_from   TEXT,
    effective_to     TEXT,
    created_by       TEXT NOT NULL,
    approved_by      TEXT,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    UNIQUE (kind, name, version)
);

-- Finance vault: individual or role-band loaded cost. Amount is Fernet-encrypted.
CREATE TABLE IF NOT EXISTS fin_loaded_costs (
    cost_id          TEXT NOT NULL PRIMARY KEY,
    scope            TEXT NOT NULL CHECK (scope IN ('individual','role_band')),
    subject_key      TEXT NOT NULL,
    monthly_cost_enc TEXT NOT NULL,
    currency         TEXT NOT NULL,
    cost_basis       TEXT NOT NULL CHECK (cost_basis IN ('fully_loaded_monthly')),
    effective_from   TEXT NOT NULL,
    effective_to     TEXT,
    source           TEXT NOT NULL,
    entered_by       TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);
CREATE INDEX IF NOT EXISTS IX_fin_cost_subject ON fin_loaded_costs(scope, subject_key);

CREATE TABLE IF NOT EXISTS market_benchmarks (
    benchmark_id     TEXT NOT NULL PRIMARY KEY,
    role             TEXT NOT NULL,
    geography        TEXT NOT NULL,
    seniority        TEXT NOT NULL,
    engagement_type  TEXT NOT NULL CHECK (engagement_type IN ('permanent','contractor','vendor')),
    basis            TEXT NOT NULL CHECK (basis IN ('salary','contractor_cost','bill_rate')),
    currency         TEXT NOT NULL CHECK (length(currency) = 3),
    unit             TEXT NOT NULL CHECK (unit IN ('month','year','hour')),
    p25              TEXT,
    p50              TEXT,
    p75              TEXT,
    sample_count     INTEGER CHECK (sample_count IS NULL OR sample_count >= 0),
    source           TEXT NOT NULL,
    as_of            TEXT NOT NULL,
    time_to_fill_weeks INTEGER,
    is_synthetic     INTEGER NOT NULL DEFAULT 0 CHECK (is_synthetic IN (0,1)),
    import_batch     TEXT NOT NULL,
    imported_by      TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
);
CREATE INDEX IF NOT EXISTS IX_bench_role ON market_benchmarks(role, geography);

CREATE TABLE IF NOT EXISTS commercial_scenarios (
    scenario_id      TEXT NOT NULL PRIMARY KEY,
    opportunity_id   TEXT NOT NULL,
    version_id       TEXT NOT NULL,
    parent_id        TEXT,
    version_no       INTEGER NOT NULL DEFAULT 1,
    kind             TEXT NOT NULL CHECK (kind IN ('internal','external','hybrid','custom')),
    currency         TEXT NOT NULL CHECK (length(currency) = 3),
    months           INTEGER NOT NULL CHECK (months BETWEEN 1 AND 120),
    assumption_json  TEXT NOT NULL,
    calc_version     TEXT NOT NULL,
    input_hash       TEXT NOT NULL,
    calculable       INTEGER NOT NULL DEFAULT 0,
    revenue          TEXT,
    cogs             TEXT,
    profit           TEXT,
    margin_pct       TEXT,
    result_json      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','partially_approved','approved','rejected')),
    override_required INTEGER NOT NULL DEFAULT 0,
    auto_generated   INTEGER NOT NULL DEFAULT 0,
    created_by       TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
);
CREATE INDEX IF NOT EXISTS IX_scen_opp ON commercial_scenarios(opportunity_id);

CREATE TABLE IF NOT EXISTS scenario_assignments (
    assignment_id    TEXT NOT NULL PRIMARY KEY,
    scenario_id      TEXT NOT NULL,
    requirement_id   TEXT NOT NULL,
    resource_type    TEXT NOT NULL CHECK (resource_type IN ('internal','external')),
    coded_identity   TEXT,
    external_slot    TEXT,
    fte              TEXT NOT NULL,
    fitness_rank     INTEGER,
    cost_ref         TEXT,
    FOREIGN KEY (scenario_id) REFERENCES commercial_scenarios(scenario_id)
);
CREATE INDEX IF NOT EXISTS IX_assign_scen ON scenario_assignments(scenario_id);

CREATE TABLE IF NOT EXISTS approval_events (
    approval_id      TEXT NOT NULL PRIMARY KEY,
    opportunity_id   TEXT NOT NULL,
    object_type      TEXT NOT NULL CHECK (object_type IN ('scenario')),
    object_id        TEXT NOT NULL,
    approver_role    TEXT NOT NULL CHECK (approver_role IN ('delivery','finance','hr')),
    outcome          TEXT NOT NULL CHECK (outcome IN ('approved','rejected')),
    reason           TEXT,
    override_reason  TEXT,
    actor            TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(opportunity_id)
);
CREATE INDEX IF NOT EXISTS IX_appr_obj ON approval_events(object_type, object_id);

-- Per-opportunity hash-chained audit. Details never contain compensation values.
CREATE TABLE IF NOT EXISTS opportunity_audit (
    audit_id         TEXT NOT NULL PRIMARY KEY,
    opportunity_id   TEXT NOT NULL,
    seq              INTEGER NOT NULL CHECK (seq >= 1),
    event_type       TEXT NOT NULL,
    actor            TEXT NOT NULL,
    object_ref       TEXT NOT NULL,
    version          TEXT NOT NULL DEFAULT '',
    evidence_hash    TEXT NOT NULL DEFAULT '',
    detail_json      TEXT NOT NULL DEFAULT '{}',
    prev_hash        TEXT NOT NULL DEFAULT '',
    row_hash         TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    UNIQUE (opportunity_id, seq)
);

-- Finance-vault access log (who read individual cost data, never the values).
CREATE TABLE IF NOT EXISTS fin_access_log (
    access_id        TEXT NOT NULL PRIMARY KEY,
    actor            TEXT NOT NULL,
    action           TEXT NOT NULL,
    context          TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);
