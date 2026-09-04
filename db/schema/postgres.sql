-- ==========================================================================
-- MAYA — PostgreSQL schema (production target)
-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
-- ==========================================================================
-- There are no migrations. This file and postgres.sql are the schema; both are
-- applied with CREATE TABLE IF NOT EXISTS, so starting against an existing
-- database is a no-op.
--
-- The same tables as sqlite.sql, with the two type substitutions PostgreSQL
-- requires: BOOLEAN where SQLite stores 0/1, and DOUBLE PRECISION where SQLite
-- uses REAL. Everything else is identical, so a model row written by one
-- dialect reads correctly under the other.
--
-- JSON documents are held as TEXT rather than JSONB deliberately: the
-- application serialises and parses them, so the two dialects behave alike and
-- no query depends on a dialect-specific operator.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS model (
    id            TEXT PRIMARY KEY,
    urn           TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    description   TEXT,
    model_class   TEXT NOT NULL,
    domain        TEXT NOT NULL,
    owner         TEXT NOT NULL,
    legal_entity  TEXT NOT NULL,
    purpose       TEXT NOT NULL,
    origin        TEXT NOT NULL DEFAULT 'internal',
    status        TEXT NOT NULL DEFAULT 'proposed',
    tier          INTEGER,
    attributes    TEXT NOT NULL DEFAULT '{}',
    created_at    DOUBLE PRECISION NOT NULL,
    created_by    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_model_domain ON model (domain);
CREATE INDEX IF NOT EXISTS ix_model_tier   ON model (tier);

-- Versions are immutable. There is no UPDATE path other than `status`, which
-- is deliberately excluded from manifest_digest.
CREATE TABLE IF NOT EXISTS model_version (
    id                 TEXT PRIMARY KEY,
    model_id           TEXT NOT NULL,
    semver             TEXT NOT NULL,
    manifest           TEXT NOT NULL,
    manifest_digest    TEXT NOT NULL,
    trainability_class TEXT NOT NULL,
    parameter_kind     TEXT NOT NULL,
    fit_procedure      TEXT NOT NULL,
    deterministic      BOOLEAN NOT NULL DEFAULT TRUE,
    input_schema       TEXT NOT NULL DEFAULT '[]',
    output_schema      TEXT NOT NULL DEFAULT '[]',
    contract           TEXT NOT NULL DEFAULT '{}',
    artifact_digest    TEXT,
    status             TEXT NOT NULL DEFAULT 'draft',
    created_at         DOUBLE PRECISION NOT NULL,
    created_by         TEXT NOT NULL,
    UNIQUE (model_id, semver)
);
CREATE INDEX IF NOT EXISTS ix_version_model ON model_version (model_id);

CREATE TABLE IF NOT EXISTS alias (
    id          TEXT PRIMARY KEY,
    model_id    TEXT NOT NULL,
    environment TEXT NOT NULL,
    name        TEXT NOT NULL,
    version_id  TEXT NOT NULL,
    moved_at    DOUBLE PRECISION NOT NULL,
    moved_by    TEXT NOT NULL,
    UNIQUE (model_id, environment, name)
);

CREATE TABLE IF NOT EXISTS alias_history (
    id              TEXT PRIMARY KEY,
    model_id        TEXT NOT NULL,
    environment     TEXT NOT NULL,
    name            TEXT NOT NULL,
    from_version_id TEXT,
    to_version_id   TEXT NOT NULL,
    refinement      TEXT NOT NULL DEFAULT '{}',
    variance        TEXT NOT NULL DEFAULT '{}',
    moved_at        DOUBLE PRECISION NOT NULL,
    moved_by        TEXT NOT NULL,
    justification   TEXT
);
CREATE INDEX IF NOT EXISTS ix_alias_history_model ON alias_history (model_id);

-- Append-only and hash-chained. The application role gets INSERT and SELECT.
CREATE TABLE IF NOT EXISTS evidence_node (
    id                     TEXT PRIMARY KEY,
    seq                    INTEGER NOT NULL UNIQUE,
    kind                   TEXT NOT NULL,
    subject_type           TEXT NOT NULL,
    subject_id             TEXT NOT NULL,
    payload                TEXT NOT NULL DEFAULT '{}',
    parents                TEXT NOT NULL DEFAULT '[]',
    contains_personal_data BOOLEAN NOT NULL DEFAULT FALSE,
    content_hash           TEXT NOT NULL,
    prev_hash              TEXT NOT NULL,
    chain_hash             TEXT NOT NULL,
    trust                  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    recorded_at            DOUBLE PRECISION NOT NULL,
    recorded_by            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_evidence_subject ON evidence_node (subject_id);

CREATE TABLE IF NOT EXISTS risk_assessment (
    id                TEXT PRIMARY KEY,
    model_id          TEXT NOT NULL,
    tier              INTEGER NOT NULL,
    materiality       TEXT NOT NULL,
    complexity        TEXT NOT NULL,
    facts             TEXT NOT NULL DEFAULT '{}',
    required_controls TEXT NOT NULL DEFAULT '[]',
    rationale         TEXT NOT NULL,
    ruleset_version   TEXT NOT NULL,
    next_review_due   DOUBLE PRECISION,
    assessed_at       DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_risk_model ON risk_assessment (model_id);

CREATE TABLE IF NOT EXISTS warrant (
    id            TEXT PRIMARY KEY,
    model_id      TEXT NOT NULL,
    environment   TEXT NOT NULL,
    binding_kind  TEXT NOT NULL,
    alias_name    TEXT,
    version_id    TEXT,
    flavour       TEXT NOT NULL,
    principal     TEXT NOT NULL,
    declared_use  TEXT NOT NULL,
    ttl_seconds   INTEGER NOT NULL,
    grace_seconds INTEGER NOT NULL DEFAULT 0,
    revoked       BOOLEAN NOT NULL DEFAULT FALSE,
    revoke_reason TEXT,
    epoch         INTEGER NOT NULL DEFAULT 0,
    created_at    DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_warrant_model ON warrant (model_id);

-- ---------------------------------------------------------- feature platform
CREATE TABLE IF NOT EXISTS feature (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE,
    entity             TEXT NOT NULL,
    dtype              TEXT NOT NULL,
    description        TEXT NOT NULL,
    business_definition TEXT,
    owner              TEXT NOT NULL,
    source_system      TEXT,
    sensitivity        TEXT NOT NULL DEFAULT 'internal',
    pii                BOOLEAN NOT NULL DEFAULT FALSE,
    protected_basis    BOOLEAN NOT NULL DEFAULT FALSE,
    proxy_risk         TEXT NOT NULL DEFAULT 'none',
    certification      TEXT NOT NULL DEFAULT 'experimental',
    created_at         DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_feature_entity ON feature (entity);

CREATE TABLE IF NOT EXISTS feature_view (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    entity       TEXT NOT NULL,
    owner        TEXT NOT NULL,
    description  TEXT,
    delta_table  TEXT NOT NULL,
    created_at   DOUBLE PRECISION NOT NULL
);

-- A view version pins a transformation to a Delta table version. Serving reads
-- the namespace PINNED BY THE CONTRACT, never "latest" (adversarial finding C-2).
CREATE TABLE IF NOT EXISTS feature_view_version (
    id                 TEXT PRIMARY KEY,
    feature_view_id    TEXT NOT NULL,
    version            INTEGER NOT NULL,
    features           TEXT NOT NULL DEFAULT '[]',
    delta_version      INTEGER NOT NULL DEFAULT 0,
    valid_time_column  TEXT NOT NULL DEFAULT 'event_ts',
    ingest_time_column TEXT NOT NULL DEFAULT 'ingest_ts',
    row_count          INTEGER NOT NULL DEFAULT 0,
    quality_report     TEXT NOT NULL DEFAULT '{}',
    materialised_at    DOUBLE PRECISION NOT NULL,
    UNIQUE (feature_view_id, version)
);
CREATE INDEX IF NOT EXISTS ix_fvv_view ON feature_view_version (feature_view_id);

-- Binds a model version to exact feature view versions. Serving with a
-- non-matching contract fails closed.
CREATE TABLE IF NOT EXISTS feature_contract (
    id               TEXT PRIMARY KEY,
    model_version_id TEXT NOT NULL,
    digest           TEXT NOT NULL,
    items            TEXT NOT NULL DEFAULT '[]',
    created_at       DOUBLE PRECISION NOT NULL,
    UNIQUE (model_version_id)
);

CREATE TABLE IF NOT EXISTS dataset_snapshot (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL DEFAULT 'training',
    delta_table    TEXT NOT NULL,
    delta_version  INTEGER NOT NULL DEFAULT 0,
    row_count      INTEGER NOT NULL DEFAULT 0,
    as_of          DOUBLE PRECISION NOT NULL,
    pit_verified   BOOLEAN NOT NULL DEFAULT FALSE,
    pit_report     TEXT NOT NULL DEFAULT '{}',
    digest         TEXT NOT NULL,
    created_at     DOUBLE PRECISION NOT NULL
);

-- --------------------------------------------------------------------------
-- Validation, test results and findings
-- --------------------------------------------------------------------------
-- A validation is an episode of independent challenge against one version.
-- Test results are the measurements it produced. Findings are what it concluded
-- that somebody now has to do something about.
--
-- `blocking` on a finding is the load-bearing column in this file. An open
-- blocking finding stops an alias move and refuses warrant resolution, so a model
-- that failed challenge cannot reach production by a route that does not pass
-- through the register. That is the difference between a findings log and a
-- control.

CREATE TABLE IF NOT EXISTS validation (
    id               TEXT PRIMARY KEY,
    model_id         TEXT NOT NULL,
    model_version_id TEXT NOT NULL,
    kind             TEXT NOT NULL DEFAULT 'initial',
    scope            TEXT NOT NULL DEFAULT '[]',
    plan             TEXT NOT NULL DEFAULT '{}',
    validators       TEXT NOT NULL DEFAULT '[]',
    independence     TEXT NOT NULL DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'planned',
    outcome          TEXT,
    conditions       TEXT NOT NULL DEFAULT '[]',
    snapshot_id      TEXT,
    started_at       DOUBLE PRECISION NOT NULL,
    completed_at     DOUBLE PRECISION,
    due_at           DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS test_result (
    id            TEXT PRIMARY KEY,
    validation_id TEXT NOT NULL,
    test_key      TEXT NOT NULL,
    parameters    TEXT NOT NULL DEFAULT '{}',
    slice         TEXT NOT NULL DEFAULT '{}',
    value         DOUBLE PRECISION,
    threshold     TEXT NOT NULL DEFAULT '{}',
    passed        BOOLEAN NOT NULL DEFAULT FALSE,
    detail        TEXT NOT NULL DEFAULT '',
    digest        TEXT NOT NULL,
    computed_at   DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_test_result_validation ON test_result (validation_id, test_key);

CREATE TABLE IF NOT EXISTS finding (
    id                 TEXT PRIMARY KEY,
    model_id           TEXT NOT NULL,
    model_version_id   TEXT,
    validation_id      TEXT,
    source             TEXT NOT NULL DEFAULT 'validation',
    severity           TEXT NOT NULL,
    category           TEXT NOT NULL DEFAULT 'general',
    title              TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    affected_component TEXT,
    blocking           BOOLEAN NOT NULL DEFAULT FALSE,
    owner              TEXT NOT NULL,
    raised_at          DOUBLE PRECISION NOT NULL,
    due_at             DOUBLE PRECISION NOT NULL,
    status             TEXT NOT NULL DEFAULT 'open',
    closed_at          DOUBLE PRECISION,
    closure_verified_by TEXT,
    closure_evidence   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_finding_open ON finding (model_id, status, severity);

-- --------------------------------------------------------------------------
-- Principals: identity, roles and scope
-- --------------------------------------------------------------------------
-- A principal is a person or a service. Roles carry permissions; scope narrows
-- WHICH models those permissions reach, by legal entity and by domain. An empty
-- scope list means unrestricted for that dimension, because the alternative --
-- enumerating every entity for every user -- is the design that makes people
-- grant `*` to get on with their day.
--
-- Passwords are PBKDF2-HMAC-SHA256 with a per-principal salt. Service
-- principals have no password and cannot sign in to the interface; they are
-- addressed by warrants.

CREATE TABLE IF NOT EXISTS principal (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'person',
    email           TEXT,
    roles           TEXT NOT NULL DEFAULT '[]',
    legal_entities  TEXT NOT NULL DEFAULT '[]',
    domains         TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'active',
    password_hash   TEXT,
    password_salt   TEXT,
    created_at      DOUBLE PRECISION NOT NULL,
    last_seen_at    DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS ix_principal_status ON principal (status);
