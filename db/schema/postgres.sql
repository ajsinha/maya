-- ==========================================================================
-- MAYA — PostgreSQL schema (production target)
-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
-- ==========================================================================
-- There are no migrations. This file and postgres.sql are the schema; both are
-- applied with CREATE TABLE IF NOT EXISTS, so starting against an existing
-- database is a no-op.
--
-- The same tables as sqlite.sql, with the ONE type substitution PostgreSQL
-- requires: DOUBLE PRECISION where SQLite uses REAL. Everything else is
-- identical, so a model row written by one dialect reads correctly under the
-- other.
--
-- There are deliberately NO BOOLEAN columns, here or in sqlite.sql or in any
-- Delta table. Truth values are integer 0 and 1 in every dialect. This file
-- once declared fourteen columns BOOLEAN while db/repositories.py coerced every
-- boolean to int on the way in -- and PostgreSQL does not implicitly cast
-- integer to boolean, so every insert touching one of those tables failed and
-- the whole dialect was unusable. Nothing tested it. Integer everywhere removes
-- the divergence rather than papering over it, and the service layer converts
-- to a real bool at its boundary so no consumer has to know how one is stored.
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
    status        TEXT NOT NULL DEFAULT 'draft',
    tier          INTEGER,
    attributes    TEXT NOT NULL DEFAULT '{}',
    created_at    DOUBLE PRECISION NOT NULL,
    created_by    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_model_domain ON model (domain);
CREATE INDEX IF NOT EXISTS ix_model_tier   ON model (tier);

-- Versions are immutable. There is no UPDATE path other than `status`, which
-- ------------------------------------------------------------------ model edges
-- How one model stands to another. Two relations, and they are not the same:
--
--   derives_from  B was built FROM A -- a variant, a recalibration for another
--                 book, a challenger sharing A's shape. B is its own model with
--                 its own versions; the edge records where it came from.
--   feeds         A's OUTPUT is an input to B. This is the network edge, and it
--                 is the one aggregate risk turns on: a curve feeding a pricer,
--                 a PD model feeding an ECL stack.
--
-- The distinction matters because they answer different questions. "What did we
-- base this on" is lineage; "what breaks if this changes" is blast radius, and
-- only `feeds` propagates. Conflating them makes a challenger look like a
-- dependency and a dependency look like a family resemblance.
--
-- Edges are between MODELS, not versions. A version-level graph would have to be
-- rebuilt on every release and would answer a question nobody asks: the estate
-- question is which models depend on this one, not which builds did.
CREATE TABLE IF NOT EXISTS model_edge (
    id           TEXT PRIMARY KEY,
    from_model   TEXT NOT NULL,          -- the model the edge points FROM
    to_model     TEXT NOT NULL,          -- and the one it points TO
    kind         TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    -- 0 or 1, never BOOLEAN. Whether the schemas at the two ends were actually
    -- compared when this edge was recorded.
    --
    -- An `input_to` edge is type-checked, unless one end has no version yet —
    -- and refusing then would make the register harder to build than the estate
    -- is to describe. But an unchecked edge that looks exactly like a checked
    -- one is a claim nobody made, propagating through blast radius as though
    -- somebody had. So the distinction is recorded rather than lost.
    type_checked INTEGER NOT NULL DEFAULT 0,
    created_by   TEXT NOT NULL,
    created_at   DOUBLE PRECISION NOT NULL,
    UNIQUE (from_model, to_model, kind)
);
CREATE INDEX IF NOT EXISTS ix_edge_from ON model_edge (from_model);
CREATE INDEX IF NOT EXISTS ix_edge_to   ON model_edge (to_model);

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
    deterministic      integer NOT NULL DEFAULT 1,
    input_schema       TEXT NOT NULL DEFAULT '[]',
    output_schema      TEXT NOT NULL DEFAULT '[]',
    contract           TEXT NOT NULL DEFAULT '{}',
    artifact_digest    TEXT,
    -- Where the artifact is, so an engine can locate it. The digest says WHAT
    -- should be there; this says where to look. Both are needed: a digest with
    -- no location cannot be fetched, and a location with no digest cannot be
    -- checked against what was approved.
    artifact_uri       TEXT,
    -- How big, so a warrant can tell an engine what it is about to
    -- fetch before it starts fetching it.
    artifact_size      integer,
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

-- How far the evidence chain has been verified, and what its head hash was at
-- that point. Readiness asks "has anything broken SINCE we last checked", which
-- is O(new nodes); the full walk stays available and runs on a schedule,
-- because only the full walk can answer "is the whole chain intact".
--
-- Verifying the whole chain on every readiness probe was O(chain): 2.9 seconds
-- and 83 MB at forty thousand nodes, and a busy instance reaches a million in
-- half an hour. Kubernetes would have taken the node out of service for being
-- slow to answer whether it was healthy.
CREATE TABLE IF NOT EXISTS evidence_checkpoint (
    id             TEXT PRIMARY KEY,
    seq            integer NOT NULL,
    chain_hash     TEXT NOT NULL,
    verified_at    DOUBLE PRECISION NOT NULL,
    verified_by    TEXT NOT NULL DEFAULT 'system'
);

-- Append-only and hash-chained. The application role gets INSERT and SELECT.
CREATE TABLE IF NOT EXISTS evidence_node (
    id                     TEXT PRIMARY KEY,
    seq                    INTEGER NOT NULL UNIQUE,
    kind                   TEXT NOT NULL,
    subject_type           TEXT NOT NULL,
    subject_id             TEXT NOT NULL,
    payload                TEXT NOT NULL DEFAULT '{}',
    parents                TEXT NOT NULL DEFAULT '[]',
    contains_personal_data integer NOT NULL DEFAULT 0,
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
    revoked       integer NOT NULL DEFAULT 0,
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
    pii                integer NOT NULL DEFAULT 0,
    protected_basis    integer NOT NULL DEFAULT 0,
    proxy_risk         TEXT NOT NULL DEFAULT 'none',
    defaults           text NOT NULL DEFAULT '{}',
    shape              text NOT NULL DEFAULT '[]',
    components         text NOT NULL DEFAULT '[]',
    composes           text NOT NULL DEFAULT '[]',
    operations         text NOT NULL DEFAULT '[]',
    definition_version integer NOT NULL DEFAULT 1,
    sealed_at          double precision,
    sealed_by          text,
    seal_note          text NOT NULL DEFAULT '',
    ephemeral          integer NOT NULL DEFAULT 0,
    expires_at         double precision,
    created_by         text NOT NULL DEFAULT 'system',
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

-- ------------------------------------------------------- serving attestation
-- What an engine says it READ, against what the contract says it must.
--
-- L-17 is contract-serving agreement, and half of it existed: `serving_namespaces`
-- computes the namespaces a version's contract pins. The other half was said to
-- need an online feature store, which MAYA deliberately does not own -- putting
-- governance on the serving path makes it the bank's single point of failure
-- (10 section 7). The engine already knows what it read, so it declares it; MAYA
-- compares and records. That is the same shape as every other claim here: the
-- platform does not do the thing, it holds whoever did to what they said.
--
-- Append-only in practice. A disagreement is recorded rather than corrected,
-- because "we served the wrong namespace and then said we had not" is precisely
-- the event this exists to make impossible to lose.
CREATE TABLE IF NOT EXISTS serving_attestation (
    id               TEXT PRIMARY KEY,
    model_version_id TEXT NOT NULL,
    warrant_id       TEXT,
    descriptor_id    TEXT,
    -- What the engine says it read: view name to namespace.
    served           TEXT NOT NULL DEFAULT '{}',
    -- What the contract pinned at the moment of comparison, kept so the answer
    -- survives the contract being rebound afterwards.
    pinned           TEXT NOT NULL DEFAULT '{}',
    -- 0/1 rather than BOOLEAN: the two dialects and Delta all take an integer,
    -- and a BOOLEAN here once broke the whole PostgreSQL dialect.
    agrees           INTEGER NOT NULL DEFAULT 0,
    -- The views that disagreed, and how.
    divergence       TEXT NOT NULL DEFAULT '[]',
    detail           TEXT NOT NULL DEFAULT '',
    attested_by      TEXT NOT NULL,
    attested_at      DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_serving_version
    ON serving_attestation (model_version_id);

-- ---------------------------------------------------------------- derived features
-- A feature whose values are computed from other features: Z = f(X, Y). The
-- definition lives here so lineage, the leakage check and the retirement guard
-- all work whether or not MAYA is the thing that evaluates it.
-- A version approval that needs more than one signature. The depth of control
-- follows the risk tier, which is the same adjunction (L-5) that decides every
-- other control set: a Tier 1 model's version is not approved by one person.
-- Ingested telemetry batches, by the digest of their own rows. Real collectors
-- deliver at least once; a monitor that double-counts a redelivered batch
-- reports a population that never existed.
-- What was sent to whom, and what happened. Not a copy of the work: the work is
-- derived from the register, and this records only that a delivery was
-- attempted. A failed delivery is kept because silence about a failed send is
-- how somebody concludes they were never told.
-- A versioned gate. A policy carries its own test cases and cannot be published
-- until they pass: a gate that can be changed without a release is a gate that
-- can be weakened without one, and the cases are what stops that being silent.
CREATE TABLE IF NOT EXISTS policy_rule (
    id           text PRIMARY KEY,
    gate         text NOT NULL,
    version      integer NOT NULL,
    rule         text NOT NULL,
    reason       text NOT NULL,
    cases        text NOT NULL DEFAULT '[]',
    facts_read   text NOT NULL DEFAULT '[]',
    test_report  text NOT NULL DEFAULT '{}',
    state        text NOT NULL DEFAULT 'draft',
    note         text NOT NULL DEFAULT '',
    digest       text NOT NULL,
    created_by   text NOT NULL,
    created_at   double precision NOT NULL,
    published_at double precision,
    published_by text,
    UNIQUE (gate, version)
);
CREATE INDEX IF NOT EXISTS ix_policy_gate ON policy_rule (gate, state);

-- A warrant profile: named, versioned defaults for the REQUEST a warrant is
-- built from. Selected by a predicate over facts the platform derives -- the
-- trainability class, the parameter kind, the runtime -- never by a category
-- somebody attached to the model. A declared taxonomy sitting beside a derived
-- one is two answers to one question, and they will disagree.
--
-- A profile may only fill in what a caller could have typed. It can never widen
-- authority: the keys that decide who may act, for what, and until when are
-- refused at creation rather than defended at use.
CREATE TABLE IF NOT EXISTS warrant_profile (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    version     integer NOT NULL,
    when_facts  text NOT NULL DEFAULT '{}',
    defaults    text NOT NULL DEFAULT '{}',
    note        text NOT NULL DEFAULT '',
    specificity integer NOT NULL DEFAULT 0,
    retired     integer NOT NULL DEFAULT 0,
    digest      text NOT NULL,
    created_by  text NOT NULL,
    created_at  double precision NOT NULL,
    retired_at  double precision,
    retired_by  text,
    UNIQUE (name, version)
);
CREATE INDEX IF NOT EXISTS ix_warrant_profile ON warrant_profile (retired, specificity);

-- A declared risk-appetite limit. Versions accumulate; nothing is edited, because
-- a limit that can be changed without a record is a limit that can be RELAXED
-- without one, and the relaxation is the event a reader six months later needs
-- to find.
CREATE TABLE IF NOT EXISTS risk_appetite (
    id           text PRIMARY KEY,
    metric       text NOT NULL,
    scope_key    text NOT NULL DEFAULT '*',
    scope        text NOT NULL DEFAULT '{}',
    version      integer NOT NULL,
    limit_value  double precision NOT NULL,
    amber_value  double precision,
    direction    text NOT NULL,
    unit         text NOT NULL,
    rationale    text NOT NULL,
    owner        text NOT NULL DEFAULT '',
    review_at    double precision,
    retired      integer NOT NULL DEFAULT 0,
    digest       text NOT NULL,
    created_by   text NOT NULL,
    created_at   double precision NOT NULL,
    retired_at   double precision,
    retired_by   text,
    UNIQUE (metric, scope_key, version)
);
CREATE INDEX IF NOT EXISTS ix_appetite_metric ON risk_appetite (metric, retired);

-- A board pack as it was read. Kept rather than recomputed: a committee minute
-- referring to "the March pack" needs the March pack, and a pack recomputed
-- today is a different document with the same name.
CREATE TABLE IF NOT EXISTS board_pack (
    id          text PRIMARY KEY,
    period      text NOT NULL,
    scope       text NOT NULL DEFAULT '{}',
    as_at       double precision NOT NULL,
    models      integer NOT NULL DEFAULT 0,
    indicators  text NOT NULL DEFAULT '[]',
    exceptions  text NOT NULL DEFAULT '[]',
    unmeasured  text NOT NULL DEFAULT '{}',
    digest      text NOT NULL,
    note        text NOT NULL DEFAULT '',
    created_by  text NOT NULL,
    created_at  double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_board_pack_at ON board_pack (as_at);



CREATE TABLE IF NOT EXISTS notification (
    id         text PRIMARY KEY,
    principal  text NOT NULL,
    channel    text NOT NULL,
    state      text NOT NULL,
    digest     text NOT NULL,
    item_count integer NOT NULL DEFAULT 0,
    overdue    integer NOT NULL DEFAULT 0,
    summary    text NOT NULL DEFAULT '',
    detail     text NOT NULL DEFAULT '',
    sent_at    double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notification_principal ON notification (principal);

CREATE TABLE IF NOT EXISTS telemetry_batch (
    id      text PRIMARY KEY,
    digest  text NOT NULL UNIQUE,
    delta_table text NOT NULL,
    row_count integer NOT NULL DEFAULT 0,
    at      double precision NOT NULL
);

CREATE TABLE IF NOT EXISTS version_approval (
    id               text PRIMARY KEY,
    model_id         text NOT NULL,
    model_version_id text NOT NULL,
    tier             integer,
    required_roles   text NOT NULL DEFAULT '[]',
    status           text NOT NULL DEFAULT 'open',
    statement        text NOT NULL DEFAULT '',
    opened_by        text NOT NULL,
    opened_at        double precision NOT NULL,
    completed_at     double precision,
    UNIQUE (model_version_id, opened_at)
);
CREATE INDEX IF NOT EXISTS ix_version_approval ON version_approval (model_version_id);

CREATE TABLE IF NOT EXISTS version_approval_signature (
    id                   text PRIMARY KEY,
    version_approval_id  text NOT NULL,
    principal            text NOT NULL,
    role                 text NOT NULL,
    decision             text NOT NULL DEFAULT 'approve',
    statement            text NOT NULL DEFAULT '',
    signed_at            double precision NOT NULL,
    UNIQUE (version_approval_id, role),
    -- A quorum is a number of PEOPLE, not a number of hats. See sqlite.sql for
    -- the race this refuses: two requests from one dual-hatted principal put
    -- both signatures of a Tier 1 quorum on one person, 1 trial in 25.
    UNIQUE (version_approval_id, principal)
);

CREATE TABLE IF NOT EXISTS derived_feature (
    id                 text PRIMARY KEY,
    feature_id         text NOT NULL,
    name               text NOT NULL,
    expression         text NOT NULL,
    inputs             text NOT NULL DEFAULT '[]',
    evaluator          text NOT NULL DEFAULT 'internal',   -- internal | external
    on_error           text NOT NULL DEFAULT 'null',
    definition_version integer NOT NULL DEFAULT 1,
    digest             text NOT NULL,
    note               text NOT NULL DEFAULT '',
    created_by         text NOT NULL,
    created_at         double precision NOT NULL,
    UNIQUE (name, definition_version)
);
CREATE INDEX IF NOT EXISTS ix_derived_feature ON derived_feature (feature_id);

-- ---------------------------------------------------------------- featuresets
-- A featureset declares a SCHEMA -- named slots with types. That schema is what
-- a kernel is defined over, which is what lets two versions draw on entirely
-- different features and still be the same input space.
CREATE TABLE IF NOT EXISTS featureset (
    id                  text PRIMARY KEY,
    name                text NOT NULL UNIQUE,
    entity              text NOT NULL,
    owner               text NOT NULL,
    description         text NOT NULL DEFAULT '',
    slots               text NOT NULL DEFAULT '{}',        -- slot -> {dtype, nullable}
    label_slot          text,
    outcome_window_days integer NOT NULL DEFAULT 0,
    defaults            text NOT NULL DEFAULT '{}',
    composes            text NOT NULL DEFAULT '[]',
    operations          text NOT NULL DEFAULT '[]',
    definition_version  integer NOT NULL DEFAULT 1,
    sealed_at           double precision,
    sealed_by           text,
    seal_note           text NOT NULL DEFAULT '',
    ephemeral           integer NOT NULL DEFAULT 0,
    expires_at          double precision,
    grain               text NOT NULL DEFAULT '',
    created_by          text NOT NULL,
    created_at          double precision NOT NULL
);

-- A version FILLS the schema. Every binding pins a feature AND the feature view
-- version supplying its values, so the same version always resolves to the same
-- bytes -- finding C-2, one level out from the view.
CREATE TABLE IF NOT EXISTS featureset_version (
    id             text PRIMARY KEY,
    featureset_id  text NOT NULL,
    version        integer NOT NULL,
    bindings       text NOT NULL DEFAULT '{}',             -- slot -> resolved binding
    label_binding  text NOT NULL DEFAULT '{}',
    digest         text NOT NULL,
    note           text NOT NULL DEFAULT '',
    created_by     text NOT NULL,
    created_at     double precision NOT NULL,
    UNIQUE (featureset_id, version)
);
CREATE INDEX IF NOT EXISTS ix_fsv_set ON featureset_version (featureset_id);

-- ---------------------------------------------------------------- parameters
-- An inhabitant of P. Training does not change the kernel; it picks a point in
-- the parameter object, so a fit produces one of these and NOT a model version.
CREATE TABLE IF NOT EXISTS parameter_set (
    id                    text PRIMARY KEY,
    model_id              text NOT NULL,
    model_version_id      text NOT NULL,
    name                  text NOT NULL,
    version               integer NOT NULL DEFAULT 1,
    kind                  text NOT NULL,
    provenance            text NOT NULL,                   -- fitted | calibrated | declared
    values_inline         text NOT NULL DEFAULT '{}',
    values_uri            text,
    cardinality           integer NOT NULL DEFAULT 0,
    diagnostics           text NOT NULL DEFAULT '{}',
    featureset_version_id text,
    window_from           double precision,
    window_to             double precision,
    as_of                 double precision,
    snapshot_id           text,
    warrant_id            text,
    digest                text NOT NULL,
    state                 text NOT NULL DEFAULT 'proposed',
    note                  text NOT NULL DEFAULT '',
    created_by            text NOT NULL,
    created_at            double precision NOT NULL,
    approved_by           text,
    approved_at           double precision,
    review_note           text NOT NULL DEFAULT '',
    superseded_by         text,
    UNIQUE (model_version_id, name, version)
);
CREATE INDEX IF NOT EXISTS ix_parameter_set_version ON parameter_set (model_version_id);

CREATE TABLE IF NOT EXISTS dataset_snapshot (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL DEFAULT 'training',
    delta_table    TEXT NOT NULL,
    delta_version  INTEGER NOT NULL DEFAULT 0,
    row_count      INTEGER NOT NULL DEFAULT 0,
    as_of          DOUBLE PRECISION NOT NULL,
    pit_verified   integer NOT NULL DEFAULT 0,
    pit_report     TEXT NOT NULL DEFAULT '{}',
    -- Which featureset version produced this snapshot. Recorded rather than
    -- recomputed: a fit warrant pins the snapshot, and 'which schema did
    -- these columns come from' has to survive reading the row back.
    featureset          text,
    featureset_version  integer,
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
    passed        integer NOT NULL DEFAULT 0,
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
    blocking           integer NOT NULL DEFAULT 0,
    owner              TEXT NOT NULL,
    raised_at          DOUBLE PRECISION NOT NULL,
    due_at             DOUBLE PRECISION NOT NULL,
    status             TEXT NOT NULL DEFAULT 'open',
    closed_at          DOUBLE PRECISION,
    closure_verified_by TEXT,
    closure_evidence   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_finding_open ON finding (model_id, status, severity);

-- Everything that happened to a finding between being raised and being closed:
-- handed to somebody else, accepted by its owner, planned, or given a later
-- date. Append-only, and deliberately NOT a status table -- ageing,
-- overdue-ness, whether the current owner ever accepted it, how many times the
-- date has moved and whether it should be escalated are all COMPUTED from these
-- rows and the finding itself. A status column and a log can disagree, and when
-- they do it is the column that gets believed and the log that is right.
CREATE TABLE IF NOT EXISTS finding_action (
    id           TEXT PRIMARY KEY,
    finding_id   TEXT NOT NULL,
    model_id     TEXT NOT NULL,
    act          TEXT NOT NULL,          -- assigned | acknowledged | planned | extended
    actor        TEXT NOT NULL,
    from_owner   TEXT,
    to_owner     TEXT,
    reason       TEXT NOT NULL DEFAULT '',
    plan         TEXT NOT NULL DEFAULT '',
    committed_at DOUBLE PRECISION,       -- the date the owner said they would fix it by
    due_before   DOUBLE PRECISION,       -- the remediation date an extension moved
    due_after    DOUBLE PRECISION,       -- and where it moved it to
    acted_at     DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_finding_action ON finding_action (finding_id, acted_at);

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
    -- The durable identity a directory login is bound to. A username is not
    -- one: a directory user submitting preferred_username 'admin' was signed in
    -- AS the local admin, because the username was what carried the roles. The
    -- binding is made once, deliberately, and a login whose (issuer, subject)
    -- disagrees with the stored pair is refused rather than resolved by name.
    sso_issuer      text,
    sso_subject     text,
    created_at      DOUBLE PRECISION NOT NULL,
    last_seen_at    DOUBLE PRECISION
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
    opened_at   DOUBLE PRECISION NOT NULL,
    closed_at   DOUBLE PRECISION,
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
    opened_at      DOUBLE PRECISION NOT NULL,
    completed_at   DOUBLE PRECISION,
    expires_at     DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS ix_attestation_model ON attestation (model_id, status);

CREATE TABLE IF NOT EXISTS attestation_signature (
    id             TEXT PRIMARY KEY,
    attestation_id TEXT NOT NULL,
    principal      TEXT NOT NULL,
    role           TEXT NOT NULL,
    decision       TEXT NOT NULL,
    statement      TEXT NOT NULL DEFAULT '',
    signed_at      DOUBLE PRECISION NOT NULL
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
    cadence_days      DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    label_delay_days  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    breach_severity   TEXT NOT NULL DEFAULT 'Medium',
    escalate_after    INTEGER NOT NULL DEFAULT 3,
    status            TEXT NOT NULL DEFAULT 'active',
    owner             TEXT NOT NULL,
    created_at        DOUBLE PRECISION NOT NULL,
    last_evaluated_at DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS ix_monitor_model ON monitor (model_id, status);

CREATE TABLE IF NOT EXISTS observation (
    id           TEXT PRIMARY KEY,
    monitor_id   TEXT NOT NULL,
    value        DOUBLE PRECISION,
    passed       integer NOT NULL DEFAULT 0,
    detail       TEXT NOT NULL DEFAULT '',
    sample_size  INTEGER NOT NULL DEFAULT 0,
    window_start DOUBLE PRECISION,
    window_end   DOUBLE PRECISION,
    matured      integer NOT NULL DEFAULT 1,
    digest       TEXT NOT NULL,
    computed_at  DOUBLE PRECISION NOT NULL
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
    opened_at      DOUBLE PRECISION NOT NULL,
    closed_at      DOUBLE PRECISION
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
    -- What this document is ABOUT, beyond the model and version it hangs
    -- under. Documentation arrives at different moments about different
    -- objects: a methodology paper is about the model, a training record is
    -- about one parameter set, a data dictionary is about a featureset
    -- VERSION. Binding everything to the model made the last two
    -- unfilable, and a document filed against a featureset rather than a
    -- featureset version would describe something that has since moved.
    subject_type     text NOT NULL DEFAULT 'model_version',
    subject_id       text,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL,
    sections         TEXT NOT NULL DEFAULT '[]',
    citations        TEXT NOT NULL DEFAULT '[]',
    coverage         TEXT NOT NULL DEFAULT '{}',
    digest           TEXT NOT NULL,
    -- The subjects this document was compiled FROM: the model and each of its
    -- versions. Staleness is measured against the same set, because measuring
    -- it against the model alone meant a new version taken through a full
    -- quorum approval left the document reporting that nothing had happened.
    subjects         text NOT NULL DEFAULT '[]',
    evidence_head    INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'compiled',
    compiled_at      DOUBLE PRECISION NOT NULL,
    compiled_by      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_document_model ON document (model_id, kind);

-- --------------------------------------------------------------------------
-- Overlays: post-model adjustments
-- --------------------------------------------------------------------------
-- An overlay is a human adjustment applied on top of a model's output. Every
-- bank has them; almost none can say how large they are in aggregate, how long
-- they have been running, or which of them have quietly become permanent.
--
-- Three columns carry the design. `expires_at` because an overlay with no end
-- date is a model change nobody versioned. `renewals` because an overlay renewed
-- again and again is evidence the MODEL is wrong, not that the overlay is
-- needed -- and that is the signal this register exists to surface. And
-- `approved_by`, separate from the proposer, because an adjustment that one
-- person can both propose and approve is not a control.

CREATE TABLE IF NOT EXISTS overlay (
    id               TEXT PRIMARY KEY,
    model_id         TEXT NOT NULL,
    model_version_id TEXT,
    reference        TEXT NOT NULL,
    name             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    direction        TEXT NOT NULL DEFAULT 'increase',
    rationale        TEXT NOT NULL,
    basis            TEXT NOT NULL DEFAULT '{}',
    owner            TEXT NOT NULL,
    proposed_by      TEXT NOT NULL,
    approved_by      TEXT,
    status           TEXT NOT NULL DEFAULT 'proposed',
    effective_from   DOUBLE PRECISION,
    expires_at       DOUBLE PRECISION,
    renewals         INTEGER NOT NULL DEFAULT 0,
    finding_id       TEXT,
    created_at       DOUBLE PRECISION NOT NULL,
    closed_at        DOUBLE PRECISION,
    closure_reason   TEXT
);

CREATE INDEX IF NOT EXISTS ix_overlay_model ON overlay (model_id, status);

CREATE TABLE IF NOT EXISTS overlay_measurement (
    id             TEXT PRIMARY KEY,
    overlay_id     TEXT NOT NULL,
    period         TEXT NOT NULL,
    base_value     DOUBLE PRECISION NOT NULL,
    adjusted_value DOUBLE PRECISION NOT NULL,
    magnitude      DOUBLE PRECISION NOT NULL,
    pct_of_base    DOUBLE PRECISION,
    measured_by    TEXT NOT NULL,
    measured_at    DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_measurement_overlay ON overlay_measurement (overlay_id, period);

-- --------------------------------------------------------------------------
-- Machine assistance
-- --------------------------------------------------------------------------
-- The platform's own AI. A capability declares what it produces, which tier it
-- is admissible at, and — for Tier A — which oracle checks it.
--
-- `rejected_claims` is the column that matters. A claim whose citations do not
-- resolve is REMOVED from the output before anyone sees it, and kept here. The
-- alternative, flagging it in place, means the flag is what gets skimmed past.
--
-- `edit_distance` records how much a reviewer changed on attestation. A FALL in
-- it over time is the signal for automation bias: a reviewer who has approved
-- forty correct drafts is not reviewing the forty-first.

CREATE TABLE IF NOT EXISTS ai_capability (
    id             TEXT PRIMARY KEY,
    capability_key TEXT NOT NULL UNIQUE,
    description    TEXT NOT NULL,
    tier           TEXT NOT NULL,
    oracle_key     TEXT,
    autonomy       TEXT NOT NULL DEFAULT 'human_approved_automation',
    base_model     TEXT NOT NULL,
    prompt_digest  TEXT NOT NULL,
    review_sample  DOUBLE PRECISION NOT NULL DEFAULT 0.1,
    status         TEXT NOT NULL DEFAULT 'active',
    owner          TEXT NOT NULL,
    created_at     DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_generation (
    id              TEXT PRIMARY KEY,
    capability_id   TEXT NOT NULL,
    subject_type    TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    prompt_digest   TEXT NOT NULL,
    base_model      TEXT NOT NULL,
    output          TEXT NOT NULL DEFAULT '{}',
    claims          TEXT NOT NULL DEFAULT '[]',
    rejected_claims TEXT NOT NULL DEFAULT '[]',
    oracle_verdict  TEXT NOT NULL DEFAULT '{}',
    state           TEXT NOT NULL DEFAULT 'drafted',
    sampled         integer NOT NULL DEFAULT 0,
    attested_by     TEXT,
    attested_at     DOUBLE PRECISION,
    edit_distance   DOUBLE PRECISION,
    created_at      DOUBLE PRECISION NOT NULL,
    created_by      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_generation_capability ON ai_generation (capability_id, state);

-- --------------------------------------------------------------------------
-- Baseline import and compliance debt
-- --------------------------------------------------------------------------
-- Adversarial review, finding C-5: on import day 1,200 existing models arrive
-- with no evidence graph, no feature contracts and documentation in Word files.
-- Every gate fails, every dashboard is red, and the programme dies in month
-- seven. That was judged the single most likely cause of total failure.
--
-- The answer is not to lower the gates. It is to make the register HONEST about
-- what it does not know. A baselined model is in the inventory and governed
-- going forward, and carries explicit debt for each piece of evidence it does
-- not have — dated, tiered, and burning down.
--
-- Debt is not breach. A Tier 1 model with baseline debt and a Tier 1 model with
-- a missed validation must never render the same colour. Debt becomes a
-- breach only when it passes its expiry.

CREATE TABLE IF NOT EXISTS baseline_import (
    id           TEXT PRIMARY KEY,
    reference    TEXT NOT NULL,
    source       TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    models       INTEGER NOT NULL DEFAULT 0,
    debt_items   INTEGER NOT NULL DEFAULT 0,
    imported_by  TEXT NOT NULL,
    imported_at  DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS compliance_debt (
    id          TEXT PRIMARY KEY,
    model_id    TEXT NOT NULL,
    import_id   TEXT,
    gap_key     TEXT NOT NULL,
    description TEXT NOT NULL,
    materiality TEXT NOT NULL DEFAULT 'Medium',
    tier        INTEGER,
    status      TEXT NOT NULL DEFAULT 'open',
    plan        TEXT NOT NULL DEFAULT '',
    owner       TEXT NOT NULL,
    finding_id  TEXT,
    raised_at   DOUBLE PRECISION NOT NULL,
    expires_at  DOUBLE PRECISION NOT NULL,
    closed_at   DOUBLE PRECISION,
    closed_by   TEXT
);

CREATE INDEX IF NOT EXISTS ix_debt_model ON compliance_debt (model_id, status);

-- --------------------------------------------------------------------------
-- Scheduled runs
-- --------------------------------------------------------------------------
-- What the scheduler did, and when. Not a queue and not a task list: every job
-- is idempotent and derives its own work from the register, so this table is a
-- record of activity rather than a source of it. Deleting every row here would
-- change nothing about what the next run does.

CREATE TABLE IF NOT EXISTS scheduled_run (
    id          TEXT PRIMARY KEY,
    job         TEXT NOT NULL,
    outcome     TEXT NOT NULL DEFAULT '{}',
    ok          integer NOT NULL DEFAULT 1,
    error       TEXT,
    duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    ran_by      TEXT NOT NULL,
    ran_at      DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_scheduled_run_job ON scheduled_run (job, ran_at);

-- --------------------------------------------------------------------------
-- Attached documents
-- --------------------------------------------------------------------------
-- The documents somebody wrote, as opposed to the ones the platform compiles: a
-- model development document in Word, a vendor's validation report, a committee
-- minute, a signed attestation. A register that holds only what it can compute
-- quietly excludes most of the evidence a supervisor will ask to see.
--
-- `model_version_id` is the point. "The model development document" is about a
-- particular version, and one filed at model level floats free of what it
-- describes -- which is how a bank ends up with an MDD for v2.1 against a model
-- serving v2.4. Version-level is the default; model-level has to be asked for.
--
-- `digest` is content-addressed storage, so the same board paper across forty
-- models is one object, and editing a document in place is impossible: a changed
-- byte is a changed digest, which is a supersession somebody declares.

CREATE TABLE IF NOT EXISTS attachment (
    id               TEXT PRIMARY KEY,
    model_id         TEXT NOT NULL,
    model_version_id TEXT,
    -- What this document is ABOUT. A methodology paper is about the
    -- model, a convergence study about one parameter set, a data
    -- dictionary about a featureset VERSION — and a document filed
    -- against a featureset rather than a version would describe
    -- something that has since moved.
    subject_type     text NOT NULL DEFAULT 'model_version',
    subject_id       text,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL,
    filename         TEXT NOT NULL,
    media_type       TEXT NOT NULL DEFAULT 'application/octet-stream',
    digest           TEXT NOT NULL,
    size_bytes       INTEGER NOT NULL DEFAULT 0,
    text_indexed     integer NOT NULL DEFAULT 0,
    state            TEXT NOT NULL DEFAULT 'attached',
    note             TEXT NOT NULL DEFAULT '',
    attached_by      TEXT NOT NULL,
    attached_at      DOUBLE PRECISION NOT NULL,
    reviewed_by      TEXT,
    reviewed_at      DOUBLE PRECISION,
    review_note      TEXT NOT NULL DEFAULT '',
    supersedes       TEXT,
    superseded_by    TEXT
);

CREATE INDEX IF NOT EXISTS ix_attachment_model ON attachment (model_id, state);
CREATE INDEX IF NOT EXISTS ix_attachment_version ON attachment (model_version_id, kind);

-- A model's stated limitations, structured rather than buried in a document.
--
-- The operating CONTRACT already carries what can be checked: `dscr` between
-- -5 and 20, refused at execution. What it cannot carry is everything a model
-- risk manager actually writes — "calibrated on 2019-2024 and never through a
-- rate shock above 400bp", "assumes the sector mix is stable", "the LGD is a
-- flat haircut and not modelled". Those live in a PDF nobody can query, and
-- the question a supervisor asks is exactly a query: WHICH of this model's
-- limitations are enforced and which are only written down?
--
-- So each row says which it is. `bound_key` names the contract clause that
-- enforces it, or is null — and null is the interesting value, because it is
-- the count of things this platform is trusting a person to remember.
CREATE TABLE IF NOT EXISTS model_limitation (
    id               TEXT PRIMARY KEY,
    model_id         TEXT NOT NULL,
    model_version_id TEXT NOT NULL,
    reference        TEXT NOT NULL,
    kind             TEXT NOT NULL,
    statement        TEXT NOT NULL,
    -- The contract clause that enforces this, if one does. Null means the
    -- limitation is stated and not enforced, which is a fact worth counting.
    bound_key        TEXT,
    basis            TEXT NOT NULL DEFAULT '',
    raised_by        TEXT NOT NULL,
    created_at       DOUBLE PRECISION NOT NULL,
    withdrawn_at     DOUBLE PRECISION,
    withdrawn_by     TEXT,
    withdrawal_reason TEXT,
    UNIQUE (model_version_id, reference)
);

-- API keys: how a service or a script authenticates without a password.
--
-- A service principal signing in with a username and password over Basic has
-- three problems a key does not. The password is a shared secret somebody typed
-- and can retype elsewhere; it carries every permission the principal holds,
-- forever; and rotating it means changing it in the register and in whatever
-- holds it, at the same instant, or something stops working.
--
-- What is stored here is a HASH. The secret is shown once, at creation, and
-- never again — not in a log, not in the evidence chain, not on this table.
-- `prefix` is the first characters of the key, stored in clear so a person can
-- tell two keys apart in a list and match one to a leaked string without
-- holding either.
CREATE TABLE IF NOT EXISTS api_key (
    id             TEXT PRIMARY KEY,
    principal_id   TEXT NOT NULL,
    username       TEXT NOT NULL,
    name           TEXT NOT NULL,
    prefix         TEXT NOT NULL,
    key_hash       TEXT NOT NULL,
    -- A key may hold a SUBSET of what its principal holds, never a superset —
    -- checked at USE rather than only at creation, so a role change or a
    -- suspension reaches every key immediately. Empty means "everything the
    -- principal holds", which is the honest default for a key that replaces a
    -- password and is stated rather than implied.
    scopes         TEXT NOT NULL DEFAULT '[]',
    created_at     DOUBLE PRECISION NOT NULL,
    created_by     TEXT NOT NULL,
    -- Every key expires. A key with no expiry is a credential nobody ever
    -- reviews, and "we will rotate it later" is the sentence before an
    -- incident.
    expires_at     DOUBLE PRECISION NOT NULL,
    last_used_at   DOUBLE PRECISION,
    -- Kept so a key that has never been used, or has stopped being used, is
    -- visible as such: an unused credential is one nobody would notice losing.
    use_count      INTEGER NOT NULL DEFAULT 0,
    revoked_at     DOUBLE PRECISION,
    revoked_by     TEXT,
    revoke_reason  TEXT,
    UNIQUE (key_hash),
    UNIQUE (username, name)
);

-- Roles, in the register rather than in the source.
--
-- They were a Python dictionary. That is fine for the eight this platform
-- ships and wrong for everything a bank actually has: a "Model Validation Team
-- Lead", a "Regional MRM", a "Quant Developer with production read" — each of
-- which meant editing `core/authz/roles.py` and redeploying. Administration
-- that requires a release is not administration.
--
-- The eight built-in roles are seeded here from the definitions that used to be
-- the whole story, and are marked `built_in`. They may be READ and they may not
-- be edited or removed: they are what every document, tutorial and test in this
-- repository refers to by name, and a platform whose vocabulary can be renamed
-- underneath its own documentation is one where the documentation is wrong.
CREATE TABLE IF NOT EXISTS role (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    -- The permissions this role grants, as a JSON array. Every one is checked
    -- against the closed permission set on the way in: a role granting a
    -- permission nothing checks is a role that reads as authority and is not.
    permissions  TEXT NOT NULL DEFAULT '[]',
    -- 0 or 1, never BOOLEAN. Whether this is one of the eight the platform
    -- ships, which may not be edited.
    built_in     INTEGER NOT NULL DEFAULT 0,
    created_at   DOUBLE PRECISION NOT NULL,
    created_by   TEXT NOT NULL DEFAULT 'system',
    updated_at   DOUBLE PRECISION,
    updated_by   TEXT,
    UNIQUE (name)
);
