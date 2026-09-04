-- ==========================================================================
-- MAYA — SQLite schema (development default)
-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
-- ==========================================================================
-- There are no migrations. This file and postgres.sql are the schema; both are
-- applied with CREATE TABLE IF NOT EXISTS, so starting against an existing
-- database is a no-op.
--
-- Only column types with the same meaning in both dialects are used:
--   TEXT     identifiers, enumerations, and JSON documents held as text
--   INTEGER  counts, sequence numbers, and booleans (0/1)
--   REAL     epoch-second timestamps and scores
-- Timestamps are epoch seconds rather than a date type, because SQLite has no
-- native one and the two dialects disagree about time zones.
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
    status        TEXT NOT NULL DEFAULT 'draft',
    tier          INTEGER,
    attributes    TEXT NOT NULL DEFAULT '{}',
    created_at    REAL NOT NULL,
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
    deterministic      INTEGER NOT NULL DEFAULT 1,
    input_schema       TEXT NOT NULL DEFAULT '[]',
    output_schema      TEXT NOT NULL DEFAULT '[]',
    contract           TEXT NOT NULL DEFAULT '{}',
    artifact_digest    TEXT,
    status             TEXT NOT NULL DEFAULT 'draft',
    created_at         REAL NOT NULL,
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
    moved_at    REAL NOT NULL,
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
    moved_at        REAL NOT NULL,
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
    contains_personal_data INTEGER NOT NULL DEFAULT 0,
    content_hash           TEXT NOT NULL,
    prev_hash              TEXT NOT NULL,
    chain_hash             TEXT NOT NULL,
    trust                  REAL NOT NULL DEFAULT 1.0,
    recorded_at            REAL NOT NULL,
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
    next_review_due   REAL,
    assessed_at       REAL NOT NULL
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
    revoked       INTEGER NOT NULL DEFAULT 0,
    revoke_reason TEXT,
    epoch         INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
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
    pii                INTEGER NOT NULL DEFAULT 0,
    protected_basis    INTEGER NOT NULL DEFAULT 0,
    proxy_risk         TEXT NOT NULL DEFAULT 'none',
    certification      TEXT NOT NULL DEFAULT 'experimental',
    created_at         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_feature_entity ON feature (entity);

CREATE TABLE IF NOT EXISTS feature_view (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    entity       TEXT NOT NULL,
    owner        TEXT NOT NULL,
    description  TEXT,
    delta_table  TEXT NOT NULL,
    created_at   REAL NOT NULL
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
    materialised_at    REAL NOT NULL,
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
    created_at       REAL NOT NULL,
    UNIQUE (model_version_id)
);

CREATE TABLE IF NOT EXISTS dataset_snapshot (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL DEFAULT 'training',
    delta_table    TEXT NOT NULL,
    delta_version  INTEGER NOT NULL DEFAULT 0,
    row_count      INTEGER NOT NULL DEFAULT 0,
    as_of          REAL NOT NULL,
    pit_verified   INTEGER NOT NULL DEFAULT 0,
    pit_report     TEXT NOT NULL DEFAULT '{}',
    digest         TEXT NOT NULL,
    created_at     REAL NOT NULL
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
    started_at       REAL NOT NULL,
    completed_at     REAL,
    due_at           REAL
);

CREATE TABLE IF NOT EXISTS test_result (
    id            TEXT PRIMARY KEY,
    validation_id TEXT NOT NULL,
    test_key      TEXT NOT NULL,
    parameters    TEXT NOT NULL DEFAULT '{}',
    slice         TEXT NOT NULL DEFAULT '{}',
    value         REAL,
    threshold     TEXT NOT NULL DEFAULT '{}',
    passed        INTEGER NOT NULL DEFAULT 0,
    detail        TEXT NOT NULL DEFAULT '',
    digest        TEXT NOT NULL,
    computed_at   REAL NOT NULL
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
    blocking           INTEGER NOT NULL DEFAULT 0,
    owner              TEXT NOT NULL,
    raised_at          REAL NOT NULL,
    due_at             REAL NOT NULL,
    status             TEXT NOT NULL DEFAULT 'open',
    closed_at          REAL,
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
    created_at      REAL NOT NULL,
    last_seen_at    REAL
);

CREATE INDEX IF NOT EXISTS ix_principal_status ON principal (status);

-- --------------------------------------------------------------------------
-- Lifecycle: amendments and attestation
-- --------------------------------------------------------------------------
-- A model record moves draft -> submitted -> approved -> attested. An attested
-- record is IMMUTABLE: no field changes and no new versions until an amendment
-- is opened, which returns it to a mutable state and must itself be attested
-- before the model is back in force.
--
-- Attestation is a quorum, not a signature. Each required role signs, and the
-- model becomes attested only when every one of them has. A single decline ends
-- it. That is what makes attestation a committee act rather than a button.
--
-- Nothing is ever deleted here. Retirement is a state; the deletion of a model
-- is an administrator-only act that still leaves its evidence behind.

CREATE TABLE IF NOT EXISTS amendment (
    id          TEXT PRIMARY KEY,
    model_id    TEXT NOT NULL,
    reference   TEXT NOT NULL,
    reason      TEXT NOT NULL,
    scope       TEXT NOT NULL DEFAULT '[]',
    status      TEXT NOT NULL DEFAULT 'open',
    opened_by   TEXT NOT NULL,
    opened_at   REAL NOT NULL,
    closed_at   REAL,
    closed_by   TEXT
);

CREATE INDEX IF NOT EXISTS ix_amendment_model ON amendment (model_id, status);

CREATE TABLE IF NOT EXISTS attestation (
    id             TEXT PRIMARY KEY,
    model_id       TEXT NOT NULL,
    amendment_id   TEXT,
    kind           TEXT NOT NULL DEFAULT 'initial',
    required_roles TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL DEFAULT 'open',
    statement      TEXT NOT NULL DEFAULT '',
    opened_by      TEXT NOT NULL,
    opened_at      REAL NOT NULL,
    completed_at   REAL,
    expires_at     REAL
);

CREATE INDEX IF NOT EXISTS ix_attestation_model ON attestation (model_id, status);

CREATE TABLE IF NOT EXISTS attestation_signature (
    id             TEXT PRIMARY KEY,
    attestation_id TEXT NOT NULL,
    principal      TEXT NOT NULL,
    role           TEXT NOT NULL,
    decision       TEXT NOT NULL,
    statement      TEXT NOT NULL DEFAULT '',
    signed_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_signature_attestation ON attestation_signature (attestation_id);

-- --------------------------------------------------------------------------
-- Monitoring: monitors, observations and breaches
-- --------------------------------------------------------------------------
-- A monitor is a standing question asked of a model version on a cadence. An
-- observation is one answer. A breach is an answer outside the threshold, and
-- it raises a finding -- which closes the loop, because a finding can block
-- warrant resolution and alias promotion.
--
-- `label_delay_days` is the column that makes performance monitoring honest. A
-- 12-month PD model's outcome is not known for 12 months, so a cohort scored
-- last week has no measurable discrimination. Monitors declare the delay, and
-- an evaluation over an immature cohort is refused rather than reported as a
-- number nobody should act on.

CREATE TABLE IF NOT EXISTS monitor (
    id                TEXT PRIMARY KEY,
    model_id          TEXT NOT NULL,
    model_version_id  TEXT,
    name              TEXT NOT NULL,
    kind              TEXT NOT NULL,
    test_key          TEXT NOT NULL,
    threshold         TEXT NOT NULL DEFAULT '{}',
    slice             TEXT NOT NULL DEFAULT '{}',
    reference         TEXT NOT NULL DEFAULT '{}',
    cadence_days      REAL NOT NULL DEFAULT 1.0,
    label_delay_days  REAL NOT NULL DEFAULT 0.0,
    breach_severity   TEXT NOT NULL DEFAULT 'Medium',
    escalate_after    INTEGER NOT NULL DEFAULT 3,
    status            TEXT NOT NULL DEFAULT 'active',
    owner             TEXT NOT NULL,
    created_at        REAL NOT NULL,
    last_evaluated_at REAL
);

CREATE INDEX IF NOT EXISTS ix_monitor_model ON monitor (model_id, status);

CREATE TABLE IF NOT EXISTS observation (
    id           TEXT PRIMARY KEY,
    monitor_id   TEXT NOT NULL,
    value        REAL,
    passed       INTEGER NOT NULL DEFAULT 0,
    detail       TEXT NOT NULL DEFAULT '',
    sample_size  INTEGER NOT NULL DEFAULT 0,
    window_start REAL,
    window_end   REAL,
    matured      INTEGER NOT NULL DEFAULT 1,
    digest       TEXT NOT NULL,
    computed_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_observation_monitor ON observation (monitor_id, computed_at);

CREATE TABLE IF NOT EXISTS breach (
    id             TEXT PRIMARY KEY,
    monitor_id     TEXT NOT NULL,
    model_id       TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    severity       TEXT NOT NULL,
    consecutive    INTEGER NOT NULL DEFAULT 1,
    detail         TEXT NOT NULL DEFAULT '',
    finding_id     TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    opened_at      REAL NOT NULL,
    closed_at      REAL
);

CREATE INDEX IF NOT EXISTS ix_breach_model ON breach (model_id, status);

-- --------------------------------------------------------------------------
-- Compiled documents
-- --------------------------------------------------------------------------
-- A model development document, a validation report, a model card or an Annex IV
-- pack is COMPILED from the register and the evidence graph, not typed into a
-- word processor. Two columns make that worth doing.
--
-- `citations` records which evidence nodes each section rested on, so "this
-- document is supported" becomes a claim that can be evaluated rather than
-- trusted. `evidence_head` records how far the chain had got when it was
-- compiled, so staleness is COMPUTED -- new evidence about the subject after
-- that point means the document no longer describes the model.

CREATE TABLE IF NOT EXISTS document (
    id               TEXT PRIMARY KEY,
    model_id         TEXT NOT NULL,
    model_version_id TEXT,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL,
    sections         TEXT NOT NULL DEFAULT '[]',
    citations        TEXT NOT NULL DEFAULT '[]',
    coverage         TEXT NOT NULL DEFAULT '{}',
    digest           TEXT NOT NULL,
    evidence_head    INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'compiled',
    compiled_at      REAL NOT NULL,
    compiled_by      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_document_model ON document (model_id, kind);
