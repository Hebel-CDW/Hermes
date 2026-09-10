-- Project Hermes Azure SQL schema
-- Classification: Internal, Confidential
-- NOTE: No protected demographic attributes are permitted in this schema.

CREATE TABLE identity_map (
    coded_identity   VARCHAR(32)  NOT NULL PRIMARY KEY,
    source_hash      CHAR(64)     NOT NULL UNIQUE, -- HMAC hash of source employee key; not reversible without vault secret
    created_at       DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME()
);
-- Real display names are NEVER stored in identity_map; resolution uses Key Vault-backed map service.

CREATE TABLE evidence_staging (
    evidence_id      VARCHAR(128) NOT NULL PRIMARY KEY,
    coded_identity   VARCHAR(32)  NOT NULL,
    skill_id         VARCHAR(64)  NULL,
    evidence_type    VARCHAR(32)  NOT NULL,
    proficiency      TINYINT      NULL,
    occurred_at      DATETIME2    NOT NULL,
    source_ref       VARCHAR(256) NOT NULL,
    payload_json     NVARCHAR(MAX) NOT NULL,
    ingested_at      DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_evidence_identity FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity),
    CONSTRAINT CK_evidence_type CHECK (evidence_type IN ('demonstrated','certified','declared')),
    CONSTRAINT CK_proficiency CHECK (proficiency IS NULL OR (proficiency BETWEEN 1 AND 5))
);

CREATE TABLE skills_matrix (
    coded_identity           VARCHAR(32)  NOT NULL,
    skill_id                 VARCHAR(64)  NOT NULL,
    proficiency              TINYINT      NOT NULL,
    confidence               DECIMAL(6,4) NOT NULL,
    freshness                DECIMAL(6,4) NOT NULL,
    evidence_ids_json        NVARCHAR(MAX) NOT NULL,
    scoring_config_version   VARCHAR(32)  NOT NULL,
    computed_at              DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
    PRIMARY KEY (coded_identity, skill_id),
    CONSTRAINT FK_matrix_identity FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity),
    CONSTRAINT CK_matrix_proficiency CHECK (proficiency BETWEEN 1 AND 5),
    CONSTRAINT CK_matrix_confidence CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT CK_matrix_freshness CHECK (freshness BETWEEN 0 AND 1)
);

CREATE TABLE role_profiles (
    role_id          VARCHAR(64)  NOT NULL PRIMARY KEY,
    role_name        NVARCHAR(256) NOT NULL,
    required_skills_json NVARCHAR(MAX) NOT NULL,
    updated_at       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE demand_signals (
    skill_id         VARCHAR(64)  NOT NULL PRIMARY KEY,
    demand_weight    DECIMAL(6,4) NOT NULL,
    updated_at       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_demand CHECK (demand_weight BETWEEN 0 AND 1)
);

CREATE TABLE availability (
    coded_identity   VARCHAR(32) NOT NULL PRIMARY KEY,
    is_available     BIT NOT NULL DEFAULT 1,
    updated_at       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_avail_identity FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE audit_ledger (
    event_id         UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    event_type       VARCHAR(64)  NOT NULL,
    actor            VARCHAR(128) NOT NULL,
    payload_json     NVARCHAR(MAX) NOT NULL,
    created_at       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE INDEX IX_audit_type_time ON audit_ledger(event_type, created_at);
CREATE INDEX IX_evidence_identity ON evidence_staging(coded_identity);
CREATE INDEX IX_matrix_skill ON skills_matrix(skill_id);
