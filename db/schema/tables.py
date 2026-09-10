"""
MAYA — the schema, declared once and typed.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

**This module is the schema.** There are no migrations and there is no ORM;
these are SQLAlchemy Core table definitions, and the DDL for each dialect is
generated from them rather than written twice.

It replaces two hand-maintained files. `sqlite.sql` and `postgres.sql` had to
declare the same fifty tables with the same columns in the same order and
equivalent types, and a test compared them mechanically — which is a good test
and a bad arrangement, because it can only report a divergence somebody has
already shipped. One declaration cannot diverge from itself. The two files are
still written out, as generated reference for a DBA who wants to read the DDL
without running Python, and a test regenerates and compares them so they cannot
rot into fiction.

**Truth values are `Boolean` and no longer integer 0/1.** The old rule existed
for a real reason: fourteen columns were once declared `BOOLEAN` on the
PostgreSQL side while the write path coerced every Python `bool` to `int`, and
PostgreSQL does not implicitly cast integer to boolean, so every insert
touching one of those tables failed — silently, because nothing ran against
that dialect. The rule fixed the symptom. The cause was that a column's type
was written twice, in two files, and known to neither the driver nor the code
that wrote to it.

A typed column removes the cause. `Boolean` compiles to `BOOLEAN` in both
dialects here, sqlite3 stores a Python `bool` as 0/1, and psycopg sends one as
a boolean — so the value and the column agree by construction rather than by a
list of column names somebody maintains.

**Timestamps stay epoch seconds** (`Double` — `DOUBLE PRECISION` in PostgreSQL,
`DOUBLE` in SQLite). Not an oversight: MAYA is bitemporal, `event_ts` and
`ingest_ts` are compared and arithmetic'd throughout, the point-in-time rule is
`min(label_ts, as_of)`, and Delta holds the same values outside the database
entirely. A date type would have to agree with all of that, and SQLite has no
native one. `REAL` in PostgreSQL is float4 and truncates an epoch second, which
is why the pairing is `Double` rather than `Float`.

**No foreign keys, no triggers, no CHECK constraints**, unchanged. Referential
integrity and immutability are properties of the application. That is a real
weakness and it is documented as one in `docs/11-adversarial-review.md` §4.5
rather than defended here.
"""
from __future__ import annotations

from sqlalchemy import (BigInteger, Boolean, Column, Double, Index, Integer,
                        MetaData,
                        Table, Text, text)
from sqlalchemy.sql.expression import false, true

#: Every table in MAYA. `Database` applies it and compares against it; nothing
#: else should build DDL.
METADATA = MetaData()


# ==========================================================================
# MAYA — SQLite schema (development default)
# Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
# ==========================================================================
# There are no migrations. This file and postgres.sql are the schema; both are
# applied with CREATE TABLE IF NOT EXISTS, so starting against an existing
# database is a no-op.
#
# Only column types with the same meaning in both dialects are used:
#   TEXT     identifiers, enumerations, and JSON documents held as text
#   INTEGER  counts, sequence numbers, and booleans (0/1)
#   REAL     epoch-second timestamps and scores
# Timestamps are epoch seconds rather than a date type, because SQLite has no
# native one and the two dialects disagree about time zones.
# ==========================================================================
MODEL = Table(
    "model", METADATA,
    Column("id", Text, primary_key=True),
    Column("urn", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("model_class", Text, nullable=False),
    Column("domain", Text, nullable=False),
    Column("owner", Text, nullable=False),
    Column("legal_entity", Text, nullable=False),
    Column("purpose", Text, nullable=False),
    Column("origin", Text, nullable=False, server_default=text("'internal'")),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("tier", Integer),
    # What the model is ALSO subject to, beside its tier. Orthogonal and
    # additive: these do not enter `tau` and do not move a model up or down the
    # lattice — they name controls required in addition, which is the whole of
    # what "driving additional control sets" means. A tag that changes nothing
    # is a label.
    Column("designations", Text, nullable=False, server_default=text("'[]'")),
    Column("attributes", Text, nullable=False, server_default=text("'{}'")),
    Column("created_at", Double, nullable=False),
    Column("created_by", Text, nullable=False),
    Index("ix_model_domain", "domain"),
    Index("ix_model_tier", "tier"),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_model_urn", "urn", unique=True),
)


# Versions are immutable. There is no UPDATE path other than `status`, which
# ------------------------------------------------------------------ model edges
# How one model stands to another. Two relations, and they are not the same:
#
#   derives_from  B was built FROM A -- a variant, a recalibration for another
#                 book, a challenger sharing A's shape. B is its own model with
#                 its own versions; the edge records where it came from.
#   feeds         A's OUTPUT is an input to B. This is the network edge, and it
#                 is the one aggregate risk turns on: a curve feeding a pricer,
#                 a PD model feeding an ECL stack.
#
# The distinction matters because they answer different questions. "What did we
# base this on" is lineage; "what breaks if this changes" is blast radius, and
# only `feeds` propagates. Conflating them makes a challenger look like a
# dependency and a dependency look like a family resemblance.
#
# Edges are between MODELS, not versions. A version-level graph would have to be
# rebuilt on every release and would answer a question nobody asks: the estate
# question is which models depend on this one, not which builds did.
MODEL_EDGE = Table(
    "model_edge", METADATA,
    Column("id", Text, primary_key=True),
    Column("from_model", Text, nullable=False),  # the model the edge points FROM
    Column("to_model", Text, nullable=False),  # and the one it points TO
    Column("kind", Text, nullable=False),
    Column("note", Text, nullable=False, server_default=text("''")),
    # 0 or 1, never BOOLEAN. Whether the schemas at the two ends were actually
    # compared when this edge was recorded.
    #
    # An `input_to` edge is type-checked, unless one end has no version yet —
    # and refusing then would make the register harder to build than the estate
    # is to describe. But an unchecked edge that looks exactly like a checked
    # one is a claim nobody made, propagating through blast radius as though
    # somebody had. So the distinction is recorded rather than lost.
    Column("type_checked", Boolean, nullable=False, server_default=false()),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Index("uq_model_edge_from_model_to_model_kind", "from_model", "to_model", "kind", unique=True),
    Index("ix_edge_from", "from_model"),
    Index("ix_edge_to", "to_model"),
)


# is deliberately excluded from manifest_digest.
MODEL_VERSION = Table(
    "model_version", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("semver", Text, nullable=False),
    Column("manifest", Text, nullable=False),
    Column("manifest_digest", Text, nullable=False),
    Column("trainability_class", Text, nullable=False),
    Column("parameter_kind", Text, nullable=False),
    Column("fit_procedure", Text, nullable=False),
    Column("deterministic", Boolean, nullable=False, server_default=true()),
    Column("input_schema", Text, nullable=False, server_default=text("'[]'")),
    # P, beside X. A kernel is `f : P (x) X -> D(Y)` and could declare only X,
    # so a calibrated or fitted model had to put its parameters in the input
    # schema to have them typeset and generated into code — which then made
    # L-W10 require the FEATURESET to supply them, and refuse the fit warrant
    # for a reason that was not true. Defaults to `[]`, so every version
    # written before this column existed reads as "declares no parameters",
    # which is what those versions meant.
    Column("parameter_schema", Text, nullable=False, server_default=text("'[]'")),
    Column("output_schema", Text, nullable=False, server_default=text("'[]'")),
    Column("contract", Text, nullable=False, server_default=text("'{}'")),
    Column("artifact_digest", Text),
    # Where the artifact is, so an engine can locate it. The digest says WHAT
    # should be there; this says where to look. Both are needed: a digest with
    # no location cannot be fetched, and a location with no digest cannot be
    # checked against what was approved.
    Column("artifact_uri", Text),
    # How big, so a warrant can tell an engine what it is about to
    # fetch before it starts fetching it.
    Column("artifact_size", Integer),
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("created_at", Double, nullable=False),
    Column("created_by", Text, nullable=False),
    Index("uq_model_version_model_id_semver", "model_id", "semver", unique=True),
    Index("ix_version_model", "model_id"),
)


ALIAS = Table(
    "alias", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("environment", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("version_id", Text, nullable=False),
    Column("moved_at", Double, nullable=False),
    Column("moved_by", Text, nullable=False),
    Index("uq_alias_model_id_environment_name", "model_id", "environment", "name", unique=True),
)


ALIAS_HISTORY = Table(
    "alias_history", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("environment", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("from_version_id", Text),
    Column("to_version_id", Text, nullable=False),
    Column("refinement", Text, nullable=False, server_default=text("'{}'")),
    Column("variance", Text, nullable=False, server_default=text("'{}'")),
    Column("moved_at", Double, nullable=False),
    Column("moved_by", Text, nullable=False),
    Column("justification", Text),
    Index("ix_alias_history_model", "model_id"),
)


# How far the evidence chain has been verified, and what its head hash was at
# that point. Readiness asks "has anything broken SINCE we last checked", which
# is O(new nodes); the full walk stays available and runs on a schedule,
# because only the full walk can answer "is the whole chain intact".
#
# Verifying the whole chain on every readiness probe was O(chain): 2.9 seconds
# and 83 MB at forty thousand nodes, and a busy instance reaches a million in
# half an hour. Kubernetes would have taken the node out of service for being
# slow to answer whether it was healthy.
EVIDENCE_CHECKPOINT = Table(
    "evidence_checkpoint", METADATA,
    Column("id", Text, primary_key=True),
    Column("seq", Integer, nullable=False),
    Column("chain_hash", Text, nullable=False),
    Column("verified_at", Double, nullable=False),
    Column("verified_by", Text, nullable=False, server_default=text("'system'")),
)


# Append-only and hash-chained. The application role gets INSERT and SELECT.
EVIDENCE_NODE = Table(
    "evidence_node", METADATA,
    Column("id", Text, primary_key=True),
    Column("seq", Integer, nullable=False),
    Column("kind", Text, nullable=False),
    Column("subject_type", Text, nullable=False),
    Column("subject_id", Text, nullable=False),
    Column("payload", Text, nullable=False, server_default=text("'{}'")),
    Column("parents", Text, nullable=False, server_default=text("'[]'")),
    Column("contains_personal_data", Boolean, nullable=False, server_default=false()),
    Column("content_hash", Text, nullable=False),
    Column("prev_hash", Text, nullable=False),
    Column("chain_hash", Text, nullable=False),
    Column("trust", Double, nullable=False, server_default=text('1.0')),
    Column("recorded_at", Double, nullable=False),
    Column("recorded_by", Text, nullable=False),
    Index("ix_evidence_subject", "subject_id"),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_evidence_node_seq", "seq", unique=True),
)


RISK_ASSESSMENT = Table(
    "risk_assessment", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("tier", Integer, nullable=False),
    Column("materiality", Text, nullable=False),
    Column("complexity", Text, nullable=False),
    Column("facts", Text, nullable=False, server_default=text("'{}'")),
    Column("required_controls", Text, nullable=False, server_default=text("'[]'")),
    Column("rationale", Text, nullable=False),
    Column("ruleset_version", Text, nullable=False),
    Column("next_review_due", Double),
    Column("assessed_at", Double, nullable=False),
    Index("ix_risk_model", "model_id"),
)


WARRANT = Table(
    "warrant", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("environment", Text, nullable=False),
    Column("binding_kind", Text, nullable=False),
    Column("alias_name", Text),
    Column("version_id", Text),
    Column("flavour", Text, nullable=False),
    Column("principal", Text, nullable=False),
    Column("declared_use", Text, nullable=False),
    Column("ttl_seconds", Integer, nullable=False),
    Column("grace_seconds", Integer, nullable=False, server_default=text('0')),
    # What this grant may spend, and the three are different things.
    #
    # `rate_per_minute` protects the DOWNSTREAM SYSTEM from a loop. `quota` per
    # window protects the AUTHORISATION from being used more than anybody
    # intended. `cost_budget` protects the INVOICE, which is the one that
    # matters for a token-metered generative model and the only one whose unit
    # is not calls.
    #
    # On the GRANT rather than on the principal, which is what "per grant"
    # means and is the right unit: a service account holding four grants should
    # not have one runaway use exhaust the other three.
    #
    # Null means unlimited on that axis, and the estate view reports how many
    # grants are unlimited rather than treating it as normal.
    Column("rate_per_minute", Integer),
    Column("quota", Integer),
    Column("quota_window_hours", Double, nullable=False, server_default=text('24.0')),
    Column("cost_budget", Double),
    Column("revoked", Boolean, nullable=False, server_default=false()),
    Column("revoke_reason", Text),
    Column("epoch", Integer, nullable=False, server_default=text('0')),
    Column("created_at", Double, nullable=False),
    Index("ix_warrant_model", "model_id"),
)


# ---------------------------------------------------------- feature platform
FEATURE = Table(
    "feature", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("entity", Text, nullable=False),
    Column("dtype", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("business_definition", Text),
    Column("owner", Text, nullable=False),
    Column("source_system", Text),
    Column("sensitivity", Text, nullable=False, server_default=text("'internal'")),
    Column("pii", Boolean, nullable=False, server_default=false()),
    Column("protected_basis", Boolean, nullable=False, server_default=false()),
    Column("proxy_risk", Text, nullable=False, server_default=text("'none'")),
    # What must be TRUE of this feature's values, checked on every
    # materialisation. A claim about the feature rather than about one view,
    # because a null rate that is unacceptable in one table is unacceptable in
    # the next — and an assertion attached to a view would have to be restated
    # every time somebody built another one, which is how they stop being
    # restated.
    Column("assertions", Text, nullable=False, server_default=text("'[]'")),
    Column("defaults", Text, nullable=False, server_default=text("'{}'")),
    Column("shape", Text, nullable=False, server_default=text("'[]'")),
    Column("components", Text, nullable=False, server_default=text("'[]'")),
    Column("composes", Text, nullable=False, server_default=text("'[]'")),
    Column("operations", Text, nullable=False, server_default=text("'[]'")),
    Column("definition_version", Integer, nullable=False, server_default=text('1')),
    Column("sealed_at", Double),
    Column("sealed_by", Text),
    Column("seal_note", Text, nullable=False, server_default=text("''")),
    Column("ephemeral", Boolean, nullable=False, server_default=false()),
    Column("expires_at", Double),
    Column("created_by", Text, nullable=False, server_default=text("'system'")),
    Column("certification", Text, nullable=False, server_default=text("'experimental'")),
    Column("created_at", Double, nullable=False),
    # Retirement, which the refusals have named since they were written and
    # which nothing implemented: `destroy` on a durable feature says "it is not
    # destroyed but retired", and there was no retire endpoint anywhere. A
    # feature created by mistake could therefore never be removed, and the two
    # refusals pointed at each other -- delete the featureset, told to remove
    # what refers to it; delete the feature, told to correct the view version.
    # A timestamp rather than a flag, per the no-BOOLEAN rule, and it doubles
    # as WHEN.
    Column("retired_at", Double),
    Column("retired_by", Text),
    Column("retire_reason", Text),
    Index("ix_feature_entity", "entity"),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_feature_name", "name", unique=True),
)


FEATURE_VIEW = Table(
    "feature_view", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("entity", Text, nullable=False),
    Column("owner", Text, nullable=False),
    Column("description", Text),
    Column("delta_table", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_feature_view_name", "name", unique=True),
)


# A view version pins a transformation to a Delta table version. Serving reads
# the namespace PINNED BY THE CONTRACT, never "latest" (adversarial finding C-2).
FEATURE_VIEW_VERSION = Table(
    "feature_view_version", METADATA,
    Column("id", Text, primary_key=True),
    Column("feature_view_id", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("features", Text, nullable=False, server_default=text("'[]'")),
    # BigInteger, and the reason is a number rather than a preference. This is
    # the TABLE FORMAT's own version coordinate, and the two formats number
    # very differently: a Delta version is sequential and small (0, 1, 2), an
    # Iceberg snapshot id is a 19-digit int64 — 2775452360009792490 was the
    # first one a test produced. PostgreSQL INTEGER stops at 2,147,483,647, so
    # an Iceberg id overflows it while SQLite swallows the same value without
    # complaint. That is the dialect divergence this codebase has been bitten
    # by before: right on the database somebody develops against, wrong on the
    # one they deploy to.
    Column("delta_version", BigInteger, nullable=False, server_default=text('0')),
    Column("valid_time_column", Text, nullable=False, server_default=text("'event_ts'")),
    Column("ingest_time_column", Text, nullable=False, server_default=text("'ingest_ts'")),
    Column("row_count", Integer, nullable=False, server_default=text('0')),
    # Whether every declared assertion held, and which did not. A version that
    # failed one is QUARANTINED: it is written, recorded and readable — because
    # deleting the evidence of a bad load is how nobody finds out what arrived
    # — but nothing may pin it. A featureset that could bind a quarantined
    # version would make the assertion advisory.
    Column("quarantined", Boolean, nullable=False, server_default=false()),
    Column("assertion_report", Text, nullable=False, server_default=text("'{}'")),
    Column("quality_report", Text, nullable=False, server_default=text("'{}'")),
    Column("materialised_at", Double, nullable=False),
    Index("uq_feature_view_version_feature_view_id_version", "feature_view_id", "version", unique=True),
    Index("ix_fvv_view", "feature_view_id"),
)


# Binds a model version to exact feature view versions. Serving with a
# non-matching contract fails closed.
FEATURE_CONTRACT = Table(
    "feature_contract", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_version_id", Text, nullable=False),
    Column("digest", Text, nullable=False),
    Column("items", Text, nullable=False, server_default=text("'[]'")),
    Column("created_at", Double, nullable=False),
    Index("uq_feature_contract_model_version_id", "model_version_id", unique=True),
)


# ------------------------------------------------------- serving attestation
# What an engine says it READ, against what the contract says it must.
#
# L-17 is contract-serving agreement, and half of it existed: `serving_namespaces`
# computes the namespaces a version's contract pins. The other half was said to
# need an online feature store, which MAYA deliberately does not own -- putting
# governance on the serving path makes it the bank's single point of failure
# (10 section 7). The engine already knows what it read, so it declares it; MAYA
# compares and records. That is the same shape as every other claim here: the
# platform does not do the thing, it holds whoever did to what they said.
#
# Append-only in practice. A disagreement is recorded rather than corrected,
# because "we served the wrong namespace and then said we had not" is precisely
# the event this exists to make impossible to lose.
SERVING_ATTESTATION = Table(
    "serving_attestation", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_version_id", Text, nullable=False),
    Column("warrant_id", Text),
    Column("descriptor_id", Text),
    # What the engine says it read: view name to namespace.
    Column("served", Text, nullable=False, server_default=text("'{}'")),
    # What the contract pinned at the moment of comparison, kept so the answer
    # survives the contract being rebound afterwards.
    Column("pinned", Text, nullable=False, server_default=text("'{}'")),
    # 0/1 rather than BOOLEAN: the two dialects and Delta all take an integer,
    # and a BOOLEAN here once broke the whole PostgreSQL dialect.
    Column("agrees", Boolean, nullable=False, server_default=false()),
    # The views that disagreed, and how.
    Column("divergence", Text, nullable=False, server_default=text("'[]'")),
    Column("detail", Text, nullable=False, server_default=text("''")),
    Column("attested_by", Text, nullable=False),
    Column("attested_at", Double, nullable=False),
    Index("ix_serving_version", "model_version_id"),
)


# ---------------------------------------------------------------- derived features
# A feature whose values are computed from other features: Z = f(X, Y). The
# definition lives here so lineage, the leakage check and the retirement guard
# all work whether or not MAYA is the thing that evaluates it.
# A version approval that needs more than one signature. The depth of control
# follows the risk tier, which is the same adjunction (L-5) that decides every
# other control set: a Tier 1 model's version is not approved by one person.
# Ingested telemetry batches, by the digest of their own rows. Real collectors
# deliver at least once; a monitor that double-counts a redelivered batch
# reports a population that never existed.
# What was sent to whom, and what happened. Not a copy of the work: the work is
# derived from the register, and this records only that a delivery was
# attempted. A failed delivery is kept because silence about a failed send is
# how somebody concludes they were never told.
# A versioned gate. A policy carries its own test cases and cannot be published
# until they pass: a gate that can be changed without a release is a gate that
# can be weakened without one, and the cases are what stops that being silent.
POLICY_RULE = Table(
    "policy_rule", METADATA,
    Column("id", Text, primary_key=True),
    Column("gate", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("rule", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("cases", Text, nullable=False, server_default=text("'[]'")),
    Column("facts_read", Text, nullable=False, server_default=text("'[]'")),
    Column("test_report", Text, nullable=False, server_default=text("'{}'")),
    Column("state", Text, nullable=False, server_default=text("'draft'")),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("digest", Text, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("published_at", Double),
    Column("published_by", Text),
    Index("uq_policy_rule_gate_version", "gate", "version", unique=True),
    Index("ix_policy_gate", "gate", "state"),
)


# A warrant profile: named, versioned defaults for the REQUEST a warrant is
# built from. Selected by a predicate over facts the platform derives -- the
# trainability class, the parameter kind, the runtime -- never by a category
# somebody attached to the model. A declared taxonomy sitting beside a derived
# one is two answers to one question, and they will disagree.
#
# A profile may only fill in what a caller could have typed. It can never widen
# authority: the keys that decide who may act, for what, and until when are
# refused at creation rather than defended at use.
WARRANT_PROFILE = Table(
    "warrant_profile", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("when_facts", Text, nullable=False, server_default=text("'{}'")),
    Column("defaults", Text, nullable=False, server_default=text("'{}'")),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("specificity", Integer, nullable=False, server_default=text('0')),
    Column("retired", Boolean, nullable=False, server_default=false()),
    Column("digest", Text, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("retired_at", Double),
    Column("retired_by", Text),
    Index("uq_warrant_profile_name_version", "name", "version", unique=True),
    Index("ix_warrant_profile", "retired", "specificity"),
)


# A declared risk-appetite limit. Versions accumulate; nothing is edited, because
# a limit that can be changed without a record is a limit that can be RELAXED
# without one, and the relaxation is the event a reader six months later needs
# to find.
RISK_APPETITE = Table(
    "risk_appetite", METADATA,
    Column("id", Text, primary_key=True),
    Column("metric", Text, nullable=False),
    Column("scope_key", Text, nullable=False, server_default=text("'*'")),
    Column("scope", Text, nullable=False, server_default=text("'{}'")),
    Column("version", Integer, nullable=False),
    Column("limit_value", Double, nullable=False),
    Column("amber_value", Double),
    Column("direction", Text, nullable=False),
    Column("unit", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("owner", Text, nullable=False, server_default=text("''")),
    Column("review_at", Double),
    Column("retired", Boolean, nullable=False, server_default=false()),
    Column("digest", Text, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("retired_at", Double),
    Column("retired_by", Text),
    Index("uq_risk_appetite_metric_scope_key_version", "metric", "scope_key", "version", unique=True),
    Index("ix_appetite_metric", "metric", "retired"),
)


# A board pack as it was read. Kept rather than recomputed: a committee minute
# referring to "the March pack" needs the March pack, and a pack recomputed
# today is a different document with the same name.
BOARD_PACK = Table(
    "board_pack", METADATA,
    Column("id", Text, primary_key=True),
    Column("period", Text, nullable=False),
    Column("scope", Text, nullable=False, server_default=text("'{}'")),
    Column("as_at", Double, nullable=False),
    Column("models", Integer, nullable=False, server_default=text('0')),
    Column("indicators", Text, nullable=False, server_default=text("'[]'")),
    Column("exceptions", Text, nullable=False, server_default=text("'[]'")),
    Column("unmeasured", Text, nullable=False, server_default=text("'{}'")),
    Column("digest", Text, nullable=False),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Index("ix_board_pack_at", "as_at"),
)


NOTIFICATION = Table(
    "notification", METADATA,
    Column("id", Text, primary_key=True),
    Column("principal", Text, nullable=False),
    Column("channel", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("digest", Text, nullable=False),
    Column("item_count", Integer, nullable=False, server_default=text('0')),
    Column("overdue", Integer, nullable=False, server_default=text('0')),
    Column("summary", Text, nullable=False, server_default=text("''")),
    Column("detail", Text, nullable=False, server_default=text("''")),
    Column("sent_at", Double, nullable=False),
    Index("ix_notification_principal", "principal"),
)


TELEMETRY_BATCH = Table(
    "telemetry_batch", METADATA,
    Column("id", Text, primary_key=True),
    Column("digest", Text, nullable=False),
    Column("delta_table", Text, nullable=False),
    Column("row_count", Integer, nullable=False, server_default=text('0')),
    Column("at", Double, nullable=False),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_telemetry_batch_digest", "digest", unique=True),
)


VERSION_APPROVAL = Table(
    "version_approval", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text, nullable=False),
    Column("tier", Integer),
    Column("required_roles", Text, nullable=False, server_default=text("'[]'")),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("statement", Text, nullable=False, server_default=text("''")),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("completed_at", Double),
    Index("uq_version_approval_model_version_id_opened_at", "model_version_id", "opened_at", unique=True),
    Index("ix_version_approval", "model_version_id"),
)


VERSION_APPROVAL_SIGNATURE = Table(
    "version_approval_signature", METADATA,
    Column("id", Text, primary_key=True),
    Column("version_approval_id", Text, nullable=False),
    Column("principal", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("decision", Text, nullable=False, server_default=text("'approve'")),
    Column("statement", Text, nullable=False, server_default=text("''")),
    Column("signed_at", Double, nullable=False),
    # A quorum is a number of PEOPLE, not a number of hats.
    #
    # `sign` enforced that with a read-then-write and nothing behind it, so two
    # requests from one dual-hatted principal raced each other: 1 trial in 25 put
    # both signatures of a Tier 1 quorum on one person, and the approval record and
    # the evidence chain both say a quorum approved it. Nothing anywhere said the
    # two signatures were the same person. A transaction alone is not enough on a
    # read-committed store, and `model_risk_manager` is a superset of `validator`,
    # so holding both is a supported configuration and exactly the one this
    # refuses.
    #
    # Both uniqueness rules on this table are INDEXES rather than clauses in the
    # CREATE TABLE above, and that is the load-bearing part. The schema is applied
    # with CREATE TABLE IF NOT EXISTS, so a table that already exists is skipped
    # whole: a constraint added to a table body reaches a fresh database and never
    # reaches a deployed one. The commit said the quorum was fixed, the suite
    # proved it on a fresh database, and the bank running that release was
    # unchanged -- one dual-hatted principal was still a Tier 1 quorum. CREATE
    # UNIQUE INDEX IF NOT EXISTS does apply to a table that already exists, in both
    # dialects, with no migration step.
    Index("uq_version_approval_signature_role", "version_approval_id", "role", unique=True),
    Index("uq_version_approval_signature_principal", "version_approval_id", "principal", unique=True),
)


DERIVED_FEATURE = Table(
    "derived_feature", METADATA,
    Column("id", Text, primary_key=True),
    Column("feature_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("expression", Text, nullable=False),
    Column("inputs", Text, nullable=False, server_default=text("'[]'")),
    Column("evaluator", Text, nullable=False, server_default=text("'internal'")),  # internal | external
    Column("on_error", Text, nullable=False, server_default=text("'null'")),
    Column("definition_version", Integer, nullable=False, server_default=text('1')),
    Column("digest", Text, nullable=False),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Index("uq_derived_feature_name_definition_version", "name", "definition_version", unique=True),
    Index("ix_derived_feature", "feature_id"),
)


# ---------------------------------------------------------------- featuresets
# A featureset declares a SCHEMA -- named slots with types. That schema is what
# a kernel is defined over, which is what lets two versions draw on entirely
# different features and still be the same input space.
FEATURESET = Table(
    "featureset", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("entity", Text, nullable=False),
    Column("owner", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("slots", Text, nullable=False, server_default=text("'{}'")),  # slot -> {dtype, nullable}
    Column("label_slot", Text),
    Column("outcome_window_days", Integer, nullable=False, server_default=text('0')),
    Column("defaults", Text, nullable=False, server_default=text("'{}'")),
    Column("composes", Text, nullable=False, server_default=text("'[]'")),
    Column("operations", Text, nullable=False, server_default=text("'[]'")),
    Column("definition_version", Integer, nullable=False, server_default=text('1')),
    Column("sealed_at", Double),
    Column("sealed_by", Text),
    Column("seal_note", Text, nullable=False, server_default=text("''")),
    Column("ephemeral", Boolean, nullable=False, server_default=false()),
    Column("expires_at", Double),
    Column("grain", Text, nullable=False, server_default=text("''")),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    # Retirement, which the refusals have named since they were written and
    # which nothing implemented: `destroy` on a durable feature says "it is not
    # destroyed but retired", and there was no retire endpoint anywhere. A
    # feature created by mistake could therefore never be removed, and the two
    # refusals pointed at each other -- delete the featureset, told to remove
    # what refers to it; delete the feature, told to correct the view version.
    # A timestamp rather than a flag, per the no-BOOLEAN rule, and it doubles
    # as WHEN.
    Column("retired_at", Double),
    Column("retired_by", Text),
    Column("retire_reason", Text),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_featureset_name", "name", unique=True),
)


# A version FILLS the schema. Every binding pins a feature AND the feature view
# version supplying its values, so the same version always resolves to the same
# bytes -- finding C-2, one level out from the view.
FEATURESET_VERSION = Table(
    "featureset_version", METADATA,
    Column("id", Text, primary_key=True),
    Column("featureset_id", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("bindings", Text, nullable=False, server_default=text("'{}'")),  # slot -> resolved binding
    Column("label_binding", Text, nullable=False, server_default=text("'{}'")),
    Column("digest", Text, nullable=False),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Index("uq_featureset_version_featureset_id_version", "featureset_id", "version", unique=True),
    Index("ix_fsv_set", "featureset_id"),
)


# ---------------------------------------------------------------- parameters
# An inhabitant of P. Training does not change the kernel; it picks a point in
# the parameter object, so a fit produces one of these and NOT a model version.
PARAMETER_SET = Table(
    "parameter_set", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("version", Integer, nullable=False, server_default=text('1')),
    Column("kind", Text, nullable=False),
    Column("provenance", Text, nullable=False),  # fitted | calibrated | declared
    Column("values_inline", Text, nullable=False, server_default=text("'{}'")),
    Column("values_uri", Text),
    Column("cardinality", Integer, nullable=False, server_default=text('0')),
    Column("diagnostics", Text, nullable=False, server_default=text("'{}'")),
    Column("featureset_version_id", Text),
    Column("window_from", Double),
    Column("window_to", Double),
    Column("as_of", Double),
    Column("snapshot_id", Text),
    Column("warrant_id", Text),
    Column("digest", Text, nullable=False),
    Column("state", Text, nullable=False, server_default=text("'proposed'")),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("approved_by", Text),
    Column("approved_at", Double),
    Column("review_note", Text, nullable=False, server_default=text("''")),
    Column("superseded_by", Text),
    Index("uq_parameter_set_model_version_id_name_version", "model_version_id", "name", "version", unique=True),
    Index("ix_parameter_set_version", "model_version_id"),
)


DATASET_SNAPSHOT = Table(
    "dataset_snapshot", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False, server_default=text("'training'")),
    Column("delta_table", Text, nullable=False),
    # BigInteger, and the reason is a number rather than a preference. This is
    # the TABLE FORMAT's own version coordinate, and the two formats number
    # very differently: a Delta version is sequential and small (0, 1, 2), an
    # Iceberg snapshot id is a 19-digit int64 — 2775452360009792490 was the
    # first one a test produced. PostgreSQL INTEGER stops at 2,147,483,647, so
    # an Iceberg id overflows it while SQLite swallows the same value without
    # complaint. That is the dialect divergence this codebase has been bitten
    # by before: right on the database somebody develops against, wrong on the
    # one they deploy to.
    Column("delta_version", BigInteger, nullable=False, server_default=text('0')),
    Column("row_count", Integer, nullable=False, server_default=text('0')),
    Column("as_of", Double, nullable=False),
    Column("pit_verified", Boolean, nullable=False, server_default=false()),
    Column("pit_report", Text, nullable=False, server_default=text("'{}'")),
    # Which featureset version produced this snapshot. Recorded rather than
    # recomputed: a fit warrant pins the snapshot, and 'which schema did
    # these columns come from' has to survive reading the row back.
    Column("featureset", Text),
    Column("featureset_version", Integer),
    Column("digest", Text, nullable=False),
    Column("created_at", Double, nullable=False),
)


# Emergency elevation, with a second signature, an end and a review.
#
# The `admin` role is *described* as break-glass and is exempt from the
# incompatible-roles check, which is not break-glass — it is a standing account
# that happens to be powerful, and a standing powerful account is the thing
# break-glass exists to replace. Break-glass is defined by being **closed by
# default**: it is asked for, agreed to by somebody else, it ends on its own, and
# somebody reads afterwards what was done under it.
#
# There is no `permissions` column, and that is deliberate. A grant does not
# hand out rights; the role does. What the grant establishes is a **window with
# a reason and a second signature**, and the platform's answer to *what was done
# under it* is a fold of the evidence chain over that window by that actor —
# derived rather than kept in a second log that could disagree with the first.
BREAK_GLASS = Table(
    "break_glass", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("principal", Text, nullable=False),
    Column("requested_by", Text, nullable=False),
    Column("reason", Text, nullable=False),
    # Null while the second signature is outstanding, and null forever on a
    # unilateral grant — which is allowed, because refusing outright at 3am is
    # how people end up sharing passwords instead.
    Column("authorised_by", Text),
    Column("unilateral", Boolean, nullable=False, server_default=false()),
    Column("opened_at", Double),
    # A moment, not a flag. Expiry that depends on a batch having run is expiry
    # that has not happened, so every read derives it from this.
    Column("expires_at", Double),
    Column("closed_at", Double),
    Column("closed_by", Text),
    Column("close_reason", Text, nullable=False, server_default=text("''")),
    # The review is mandatory in the only sense that means anything: an
    # unreviewed grant refuses the next one.
    Column("review_due", Double),
    Column("reviewed_at", Double),
    Column("reviewed_by", Text),
    Column("review_outcome", Text),
    Column("review_note", Text, nullable=False, server_default=text("''")),
    Column("state", Text, nullable=False, server_default=text("'requested'")),
    Index("ix_break_glass_principal", "principal", "state"),
    Index("uq_break_glass_reference", "reference", unique=True),
)

# An approval that carries conditions, each of which something checks.
#
# SR 26-2 V permits use before validation *with compensating controls*, and this
# is the table that makes those controls machine-enforced rather than promised.
#
# The design turns on one distinction, recorded per condition: **enforced** means
# something in this platform refuses when it is broken; **attested** means
# somebody has to confirm periodically that it still holds, because MAYA cannot
# see the thing it is about. An exposure cap is the honest example — the register
# does not see the exposure of a call, so a firm told its exposure cap is
# machine-enforced would be worse off than one told it is a diary entry with a
# name on it.
#
# `expires_at` is NOT NULL on purpose. A conditional approval with no end date is
# an unconditional approval that has not noticed yet, which is exactly how a
# temporary state becomes the permanent one.
APPROVAL_CONDITION = Table(
    "approval_condition", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    Column("reference", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("enforcement", Text, nullable=False, server_default=text("'enforced'")),
    Column("parameters", Text, nullable=False, server_default=text("'{}'")),
    Column("rationale", Text, nullable=False),
    Column("imposed_by", Text, nullable=False),
    Column("imposed_at", Double, nullable=False),
    Column("expires_at", Double, nullable=False),
    # For an attested condition: who last confirmed it holds, and when. Null
    # means nobody has, which is a different fact from its being broken.
    Column("confirmed_by", Text),
    Column("confirmed_at", Double),
    Column("confirm_every_days", Double, nullable=False, server_default=text('30.0')),
    Column("state", Text, nullable=False, server_default=text("'active'")),
    Column("discharged_at", Double),
    Column("discharged_by", Text),
    Column("discharge_reason", Text, nullable=False, server_default=text("''")),
    Index("ix_approval_condition_model", "model_id", "state"),
    Index("uq_approval_condition_reference", "reference", unique=True),
)

# What a model was asked and what it answered — kept apart from the invocation
# record on purpose.
#
# `warrant_invocation` holds the SHAPE of a call: who, what for, which version,
# how long, how it ended. That can be kept for years without anybody having to
# think about it. This holds the CONTENT, and content carries personal data, so
# it has a retention period, a sampling rate and a classification, and none of
# those is optional.
#
# **The digest is the default and the values are the exception.** A digest
# proves what was asked and what was answered without holding either, which is
# what AI Act Art. 12 traceability actually needs. Holding the values is a
# decision somebody takes per model, with a reason and an end date.
#
# The digest is **keyed**, and that is not decoration. An unkeyed digest of a
# small feature vector — an age, a postcode, a band — is a lookup table anybody
# with the same hash function can enumerate. A key the platform holds and the
# row does not makes the digest a comparison token rather than a disclosure.
INFERENCE = Table(
    "inference", METADATA,
    Column("id", Text, primary_key=True),
    Column("invocation_id", Text),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    Column("request_id", Text),
    Column("principal", Text, nullable=False),
    # Always present. What was asked and what came back, as keyed digests.
    Column("feature_digest", Text, nullable=False),
    Column("prediction_digest", Text, nullable=False),
    # Present only where somebody decided to retain content for this model, and
    # only until `retain_until`.
    Column("features", Text),
    Column("prediction", Text),
    Column("explanation", Text),
    Column("latency_ms", Double),
    Column("outcome", Text, nullable=False, server_default=text("'ok'")),
    # Why this row exists when most calls produce none: `sampled`, `refused`,
    # `boundary` or `always`. A sample nobody can explain is a sample nobody
    # trusts, and the interesting rows are kept for a different reason from the
    # ordinary ones.
    Column("reason", Text, nullable=False, server_default=text("'sampled'")),
    Column("classification", Text, nullable=False, server_default=text("'internal'")),
    Column("retain_until", Double),
    Column("at", Double, nullable=False),
    Index("ix_inference_model", "model_id", "at"),
    Index("ix_inference_retention", "retain_until"),
)

# A mutating request somebody may send twice.
#
# Scoped to the **principal as well as the key**, because a key is chosen by the
# caller and a well-chosen UUID does not protect you from somebody else's badly
# chosen one.
#
# `request_digest` is the part that makes this safe rather than dangerous. An
# idempotency store that ignores the body will happily replay the first
# response to a *different* second request — so a client that retried with a
# corrected payload is told the correction succeeded when it was never applied.
# A key reused with a different body is a conflict, not a replay.
IDEMPOTENCY = Table(
    "idempotency", METADATA,
    Column("id", Text, primary_key=True),
    Column("idempotency_key", Text, nullable=False),
    Column("principal", Text, nullable=False),
    Column("method", Text, nullable=False),
    Column("path", Text, nullable=False),
    Column("request_digest", Text, nullable=False),
    # `in_flight` while the work is running. A second request arriving
    # concurrently must not run it again, and must not be told the first one
    # succeeded either — it has not finished.
    Column("state", Text, nullable=False, server_default=text("'in_flight'")),
    Column("status", Integer),
    Column("body", Text),
    Column("started_at", Double, nullable=False),
    Column("completed_at", Double),
    Index("uq_idempotency", "idempotency_key", "principal", unique=True),
    Index("ix_idempotency_started", "started_at"),
)

# --------------------------------------------------------------------------
# Validation, test results and findings
# --------------------------------------------------------------------------
# A validation is an episode of independent challenge against one version.
# Test results are the measurements it produced. Findings are what it concluded
# that somebody now has to do something about.
#
# `blocking` on a finding is the load-bearing column in this file. An open
# blocking finding stops an alias move and refuses warrant resolution, so a model
# that failed challenge cannot reach production by a route that does not pass
# through the register. That is the difference between a findings log and a
# control.
VALIDATION = Table(
    "validation", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text, nullable=False),
    Column("kind", Text, nullable=False, server_default=text("'initial'")),
    Column("scope", Text, nullable=False, server_default=text("'[]'")),
    Column("plan", Text, nullable=False, server_default=text("'{}'")),
    Column("validators", Text, nullable=False, server_default=text("'[]'")),
    Column("independence", Text, nullable=False, server_default=text("'{}'")),
    Column("status", Text, nullable=False, server_default=text("'planned'")),
    Column("outcome", Text),
    Column("conditions", Text, nullable=False, server_default=text("'[]'")),
    Column("snapshot_id", Text),
    # SS1/23 1.3(e) asks that the tier be re-assessed during validation and
    # that the answer be recorded. Both halves are here, and they are two
    # columns rather than one because *what the tier was when the validator
    # started* and *what the validator thinks of it* are different facts —
    # without the first, a verdict of "remains appropriate" cannot be checked
    # against a tier that moved underneath the episode.
    Column("tier_at_open", Integer),
    Column("tier_verdict", Text),
    Column("tier_note", Text, nullable=False, server_default=text("''")),
    Column("started_at", Double, nullable=False),
    Column("completed_at", Double),
    Column("due_at", Double),
)


TEST_RESULT = Table(
    "test_result", METADATA,
    Column("id", Text, primary_key=True),
    Column("validation_id", Text, nullable=False),
    Column("test_key", Text, nullable=False),
    Column("parameters", Text, nullable=False, server_default=text("'{}'")),
    Column("slice", Text, nullable=False, server_default=text("'{}'")),
    Column("value", Double),
    Column("threshold", Text, nullable=False, server_default=text("'{}'")),
    Column("passed", Boolean, nullable=False, server_default=false()),
    Column("detail", Text, nullable=False, server_default=text("''")),
    Column("digest", Text, nullable=False),
    Column("computed_at", Double, nullable=False),
    Index("ix_test_result_validation", "validation_id", "test_key"),
)


FINDING = Table(
    "finding", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    Column("validation_id", Text),
    Column("source", Text, nullable=False, server_default=text("'validation'")),
    Column("severity", Text, nullable=False),
    Column("category", Text, nullable=False, server_default=text("'general'")),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("affected_component", Text),
    Column("blocking", Boolean, nullable=False, server_default=false()),
    Column("owner", Text, nullable=False),
    Column("raised_at", Double, nullable=False),
    Column("due_at", Double, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("closed_at", Double),
    Column("closure_verified_by", Text),
    Column("closure_evidence", Text, nullable=False, server_default=text("'{}'")),
    Index("ix_finding_open", "model_id", "status", "severity"),
)


# Everything that happened to a finding between being raised and being closed:
# handed to somebody else, accepted by its owner, planned, or given a later
# date. Append-only, and deliberately NOT a status table -- ageing,
# overdue-ness, whether the current owner ever accepted it, how many times the
# date has moved and whether it should be escalated are all COMPUTED from these
# rows and the finding itself. A status column and a log can disagree, and when
# they do it is the column that gets believed and the log that is right.
FINDING_ACTION = Table(
    "finding_action", METADATA,
    Column("id", Text, primary_key=True),
    Column("finding_id", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("act", Text, nullable=False),  # assigned | acknowledged | planned | extended
    Column("actor", Text, nullable=False),
    Column("from_owner", Text),
    Column("to_owner", Text),
    Column("reason", Text, nullable=False, server_default=text("''")),
    Column("plan", Text, nullable=False, server_default=text("''")),
    Column("committed_at", Double),  # the date the owner said they would fix it by
    Column("due_before", Double),  # the remediation date an extension moved
    Column("due_after", Double),  # and where it moved it to
    Column("acted_at", Double, nullable=False),
    Index("ix_finding_action", "finding_id", "acted_at"),
)


# --------------------------------------------------------------------------
# Principals: identity, roles and scope
# --------------------------------------------------------------------------
# A principal is a person or a service. Roles carry permissions; scope narrows
# WHICH models those permissions reach, by legal entity and by domain. An empty
# scope list means unrestricted for that dimension, because the alternative --
# enumerating every entity for every user -- is the design that makes people
# grant `*` to get on with their day.
#
# Passwords are PBKDF2-HMAC-SHA256 with a per-principal salt. Service
# principals have no password and cannot sign in to the interface; they are
# addressed by warrants.
PRINCIPAL = Table(
    "principal", METADATA,
    Column("id", Text, primary_key=True),
    Column("username", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("kind", Text, nullable=False, server_default=text("'person'")),
    Column("email", Text),
    Column("roles", Text, nullable=False, server_default=text("'[]'")),
    Column("legal_entities", Text, nullable=False, server_default=text("'[]'")),
    Column("domains", Text, nullable=False, server_default=text("'[]'")),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("password_hash", Text),
    Column("password_salt", Text),
    # The durable identity a directory login is bound to. A username is not
    # one: a directory user submitting preferred_username 'admin' was signed in
    # AS the local admin, because the username was what carried the roles. The
    # binding is made once, deliberately, and a login whose (issuer, subject)
    # disagrees with the stored pair is refused rather than resolved by name.
    Column("sso_issuer", Text),
    Column("sso_subject", Text),
    Column("created_at", Double, nullable=False),
    Column("last_seen_at", Double),
    Index("ix_principal_status", "status"),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_principal_username", "username", unique=True),
)


# --------------------------------------------------------------------------
# Lifecycle: amendments and attestation
# --------------------------------------------------------------------------
# A model record moves draft -> submitted -> approved -> attested. An attested
# record is IMMUTABLE: no field changes and no new versions until an amendment
# is opened, which returns it to a mutable state and must itself be attested
# before the model is back in force.
#
# Attestation is a quorum, not a signature. Each required role signs, and the
# model becomes attested only when every one of them has. A single decline ends
# it. That is what makes attestation a committee act rather than a button.
#
# Nothing is ever deleted here. Retirement is a state; the deletion of a model
# is an administrator-only act that still leaves its evidence behind.
AMENDMENT = Table(
    "amendment", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("reference", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("scope", Text, nullable=False, server_default=text("'[]'")),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("closed_at", Double),
    Column("closed_by", Text),
    Index("ix_amendment_model", "model_id", "status"),
)


ATTESTATION = Table(
    "attestation", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("amendment_id", Text),
    Column("kind", Text, nullable=False, server_default=text("'initial'")),
    Column("required_roles", Text, nullable=False, server_default=text("'[]'")),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("statement", Text, nullable=False, server_default=text("''")),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("completed_at", Double),
    Column("expires_at", Double),
    Index("ix_attestation_model", "model_id", "status"),
)


ATTESTATION_SIGNATURE = Table(
    "attestation_signature", METADATA,
    Column("id", Text, primary_key=True),
    Column("attestation_id", Text, nullable=False),
    Column("principal", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("decision", Text, nullable=False),
    Column("statement", Text, nullable=False, server_default=text("''")),
    Column("signed_at", Double, nullable=False),
    Index("ix_signature_attestation", "attestation_id"),
    # A quorum is a number of PEOPLE. One-per-role is not enough on its own:
    # `model_risk_manager` is a superset of `validator`, so one principal can hold
    # both required hats and sign twice, and for a wave one did -- putting a model
    # in force on one person's judgement while the record and the evidence chain
    # both called it a quorum.
    #
    # An INDEX rather than a UNIQUE clause inside the CREATE TABLE, and that is the
    # load-bearing part. The schema is applied with CREATE TABLE IF NOT EXISTS, so
    # a table that already exists is skipped whole: a constraint added to a table
    # body reaches new databases and never reaches a deployed one. The commit says
    # the quorum was fixed, the suite proves it on a fresh database, and the bank
    # running last month's release is unchanged. CREATE UNIQUE INDEX IF NOT EXISTS
    # does apply to a table that already exists, in both dialects, with no
    # migration step -- so a constraint expressed this way arrives everywhere.
    Index("uq_signature_attestation_principal", "attestation_id", "principal", unique=True),
    Index("uq_signature_attestation_role", "attestation_id", "role", unique=True),
)


# --------------------------------------------------------------------------
# Monitoring: monitors, observations and breaches
# --------------------------------------------------------------------------
# A monitor is a standing question asked of a model version on a cadence. An
# observation is one answer. A breach is an answer outside the threshold, and
# it raises a finding -- which closes the loop, because a finding can block
# warrant resolution and alias promotion.
#
# `label_delay_days` is the column that makes performance monitoring honest. A
# 12-month PD model's outcome is not known for 12 months, so a cohort scored
# last week has no measurable discrimination. Monitors declare the delay, and
# an evaluation over an immature cohort is refused rather than reported as a
# number nobody should act on.
MONITOR = Table(
    "monitor", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("test_key", Text, nullable=False),
    Column("threshold", Text, nullable=False, server_default=text("'{}'")),
    Column("slice", Text, nullable=False, server_default=text("'{}'")),
    Column("reference", Text, nullable=False, server_default=text("'{}'")),
    Column("cadence_days", Double, nullable=False, server_default=text('1.0')),
    Column("label_delay_days", Double, nullable=False, server_default=text('0.0')),
    Column("breach_severity", Text, nullable=False, server_default=text("'Medium'")),
    Column("escalate_after", Integer, nullable=False, server_default=text('3')),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("owner", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("last_evaluated_at", Double),
    Index("ix_monitor_model", "model_id", "status"),
)


OBSERVATION = Table(
    "observation", METADATA,
    Column("id", Text, primary_key=True),
    Column("monitor_id", Text, nullable=False),
    Column("value", Double),
    Column("passed", Boolean, nullable=False, server_default=false()),
    Column("detail", Text, nullable=False, server_default=text("''")),
    Column("sample_size", Integer, nullable=False, server_default=text('0')),
    Column("window_start", Double),
    Column("window_end", Double),
    Column("matured", Boolean, nullable=False, server_default=true()),
    Column("digest", Text, nullable=False),
    Column("computed_at", Double, nullable=False),
    Index("ix_observation_monitor", "monitor_id", "computed_at"),
)


BREACH = Table(
    "breach", METADATA,
    Column("id", Text, primary_key=True),
    Column("monitor_id", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("observation_id", Text, nullable=False),
    Column("severity", Text, nullable=False),
    Column("consecutive", Integer, nullable=False, server_default=text('1')),
    Column("detail", Text, nullable=False, server_default=text("''")),
    Column("finding_id", Text),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("opened_at", Double, nullable=False),
    Column("closed_at", Double),
    Index("ix_breach_model", "model_id", "status"),
)


# --------------------------------------------------------------------------
# Compiled documents
# --------------------------------------------------------------------------
# A model development document, a validation report, a model card or an Annex IV
# pack is COMPILED from the register and the evidence graph, not typed into a
# word processor. Two columns make that worth doing.
#
# `citations` records which evidence nodes each section rested on, so "this
# document is supported" becomes a claim that can be evaluated rather than
# trusted. `evidence_head` records how far the chain had got when it was
# compiled, so staleness is COMPUTED -- new evidence about the subject after
# that point means the document no longer describes the model.
DOCUMENT = Table(
    "document", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    # What this document is ABOUT, beyond the model and version it hangs
    # under. Documentation arrives at different moments about different
    # objects: a methodology paper is about the model, a training record is
    # about one parameter set, a data dictionary is about a featureset
    # VERSION. Binding everything to the model made the last two
    # unfilable, and a document filed against a featureset rather than a
    # featureset version would describe something that has since moved.
    Column("subject_type", Text, nullable=False, server_default=text("'model_version'")),
    Column("subject_id", Text),
    Column("kind", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("sections", Text, nullable=False, server_default=text("'[]'")),
    Column("citations", Text, nullable=False, server_default=text("'[]'")),
    Column("coverage", Text, nullable=False, server_default=text("'{}'")),
    Column("digest", Text, nullable=False),
    # The subjects this document was compiled FROM: the model and each of its
    # versions. Staleness is measured against the same set, because measuring
    # it against the model alone meant a new version taken through a full
    # quorum approval left the document reporting that nothing had happened.
    Column("subjects", Text, nullable=False, server_default=text("'[]'")),
    Column("evidence_head", Integer, nullable=False, server_default=text('0')),
    Column("status", Text, nullable=False, server_default=text("'compiled'")),
    Column("compiled_at", Double, nullable=False),
    Column("compiled_by", Text, nullable=False),
    Index("ix_document_model", "model_id", "kind"),
)


# --------------------------------------------------------------------------
# Overlays: post-model adjustments
# --------------------------------------------------------------------------
# An overlay is a human adjustment applied on top of a model's output. Every
# bank has them; almost none can say how large they are in aggregate, how long
# they have been running, or which of them have quietly become permanent.
#
# Three columns carry the design. `expires_at` because an overlay with no end
# date is a model change nobody versioned. `renewals` because an overlay renewed
# again and again is evidence the MODEL is wrong, not that the overlay is
# needed -- and that is the signal this register exists to surface. And
# `approved_by`, separate from the proposer, because an adjustment that one
# person can both propose and approve is not a control.
OVERLAY = Table(
    "overlay", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    Column("reference", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("direction", Text, nullable=False, server_default=text("'increase'")),
    Column("rationale", Text, nullable=False),
    Column("basis", Text, nullable=False, server_default=text("'{}'")),
    Column("owner", Text, nullable=False),
    Column("proposed_by", Text, nullable=False),
    Column("approved_by", Text),
    Column("status", Text, nullable=False, server_default=text("'proposed'")),
    Column("effective_from", Double),
    Column("expires_at", Double),
    Column("renewals", Integer, nullable=False, server_default=text('0')),
    Column("finding_id", Text),
    Column("created_at", Double, nullable=False),
    Column("closed_at", Double),
    Column("closure_reason", Text),
    Index("ix_overlay_model", "model_id", "status"),
)


OVERLAY_MEASUREMENT = Table(
    "overlay_measurement", METADATA,
    Column("id", Text, primary_key=True),
    Column("overlay_id", Text, nullable=False),
    Column("period", Text, nullable=False),
    Column("base_value", Double, nullable=False),
    Column("adjusted_value", Double, nullable=False),
    Column("magnitude", Double, nullable=False),
    Column("pct_of_base", Double),
    Column("measured_by", Text, nullable=False),
    Column("measured_at", Double, nullable=False),
    Index("ix_measurement_overlay", "overlay_id", "period"),
)


# --------------------------------------------------------------------------
# Machine assistance
# --------------------------------------------------------------------------
# The platform's own AI. A capability declares what it produces, which tier it
# is admissible at, and — for Tier A — which oracle checks it.
#
# `rejected_claims` is the column that matters. A claim whose citations do not
# resolve is REMOVED from the output before anyone sees it, and kept here. The
# alternative, flagging it in place, means the flag is what gets skimmed past.
#
# `edit_distance` records how much a reviewer changed on attestation. A FALL in
# it over time is the signal for automation bias: a reviewer who has approved
# forty correct drafts is not reviewing the forty-first.
AI_CAPABILITY = Table(
    "ai_capability", METADATA,
    Column("id", Text, primary_key=True),
    Column("capability_key", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("tier", Text, nullable=False),
    Column("oracle_key", Text),
    Column("autonomy", Text, nullable=False, server_default=text("'human_approved_automation'")),
    Column("base_model", Text, nullable=False),
    Column("prompt_digest", Text, nullable=False),
    Column("review_sample", Double, nullable=False, server_default=text('0.1')),
    # What this capability may spend, per rolling window. Three numbers rather
    # than one, because they bound different failures: tokens bound a prompt
    # that grew, cost bounds the invoice, and STEPS bound a loop — a runaway
    # agent is a large number of small calls, which passes a token budget and a
    # cost budget for a long time before either notices.
    #
    # Nullable, and null means "the default applies" rather than "unlimited".
    # A capability running on a number nobody chose is reported as such.
    Column("token_budget", Integer),
    Column("cost_budget", Double),
    Column("step_budget", Integer),
    # A rolling window, never a lifetime cap. A lifetime cap is reached once and
    # then the capability is dead forever, which is how budgets end up raised to
    # a number that means nothing.
    Column("budget_window_days", Double, nullable=False, server_default=text('30.0')),
    # The canary fingerprint: what a fixed set of trivial probes produced when
    # this capability was last evaluated. A base model moves underneath its own
    # version string, and nothing else here would notice.
    #
    # Null means never taken. `canary_probes` holds the probes that proved
    # STABLE at baseline — a probe the model disagrees with itself about is
    # excluded by name, and a capability where none survive is recorded as
    # unfingerprintable, which is a better answer than a digest that changes
    # every time and teaches everybody to ignore the alarm.
    Column("canary_digest", Text),
    Column("canary_probes", Text, nullable=False, server_default=text("'[]'")),
    Column("canary_taken_at", Double),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("owner", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    # Uniqueness as an INDEX, never as a UNIQUE clause inside the table: a
    # CREATE TABLE is skipped whole on a database that already has the
    # table, so a constraint written there reaches a fresh install and never
    # a deployed one.
    Index("uq_ai_capability_capability_key", "capability_key", unique=True),
)


AI_GENERATION = Table(
    "ai_generation", METADATA,
    Column("id", Text, primary_key=True),
    Column("capability_id", Text, nullable=False),
    Column("subject_type", Text, nullable=False),
    Column("subject_id", Text, nullable=False),
    Column("prompt_digest", Text, nullable=False),
    Column("base_model", Text, nullable=False),
    Column("output", Text, nullable=False, server_default=text("'{}'")),
    Column("claims", Text, nullable=False, server_default=text("'[]'")),
    Column("rejected_claims", Text, nullable=False, server_default=text("'[]'")),
    Column("oracle_verdict", Text, nullable=False, server_default=text("'{}'")),
    Column("state", Text, nullable=False, server_default=text("'drafted'")),
    Column("sampled", Boolean, nullable=False, server_default=false()),
    Column("attested_by", Text),
    Column("attested_at", Double),
    Column("edit_distance", Double),
    Column("created_at", Double, nullable=False),
    Column("created_by", Text, nullable=False),
    Index("ix_generation_capability", "capability_id", "state"),
)


# What a capability actually consumed, one row per provider call.
#
# **Separate from the generation log, and the separation is the point.** A
# generation whose claims ground nothing is never recorded at all — the gate
# refuses it and no row is written. The provider was still called and the tokens
# were still spent. Counting spend from generation rows would therefore mean a
# capability whose output never grounds has no measurable cost, which is exactly
# backwards: the capability failing most often is the one burning the most.
#
# `generation_id` is null for precisely those calls, and that null is the useful
# column — it is the spend that bought nothing.
AI_SPEND = Table(
    "ai_spend", METADATA,
    Column("id", Text, primary_key=True),
    Column("capability_id", Text, nullable=False),
    Column("generation_id", Text),
    Column("tokens", Integer, nullable=False, server_default=text('0')),
    Column("cost", Double, nullable=False, server_default=text('0.0')),
    Column("steps", Integer, nullable=False, server_default=text('1')),
    # Why the call produced nothing, when it produced nothing. A refusal code
    # rather than prose, so the estate view can group by it: a capability
    # burning its budget on `oracle_failed` is a different problem from one
    # burning it on `nothing_grounded`.
    Column("outcome", Text, nullable=False, server_default=text("'recorded'")),
    Column("spent_at", Double, nullable=False),
    Column("spent_by", Text, nullable=False),
    # The budget question is "what has this capability spent since a moment",
    # and without this it is a full scan of every call ever made.
    Index("ix_ai_spend_capability", "capability_id", "spent_at"),
)


# --------------------------------------------------------------------------
# Baseline import and compliance debt
# --------------------------------------------------------------------------
# Adversarial review, finding C-5: on import day 1,200 existing models arrive
# with no evidence graph, no feature contracts and documentation in Word files.
# Every gate fails, every dashboard is red, and the programme dies in month
# seven. That was judged the single most likely cause of total failure.
#
# The answer is not to lower the gates. It is to make the register HONEST about
# what it does not know. A baselined model is in the inventory and governed
# going forward, and carries explicit debt for each piece of evidence it does
# not have — dated, tiered, and burning down.
#
# Debt is not breach. A Tier 1 model with baseline debt and a Tier 1 model with
# a missed validation must never render the same colour. Debt becomes a
# breach only when it passes its expiry.
BASELINE_IMPORT = Table(
    "baseline_import", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("models", Integer, nullable=False, server_default=text('0')),
    Column("debt_items", Integer, nullable=False, server_default=text('0')),
    Column("imported_by", Text, nullable=False),
    Column("imported_at", Double, nullable=False),
)


COMPLIANCE_DEBT = Table(
    "compliance_debt", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("import_id", Text),
    Column("gap_key", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("materiality", Text, nullable=False, server_default=text("'Medium'")),
    Column("tier", Integer),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("plan", Text, nullable=False, server_default=text("''")),
    Column("owner", Text, nullable=False),
    Column("finding_id", Text),
    Column("raised_at", Double, nullable=False),
    Column("expires_at", Double, nullable=False),
    Column("closed_at", Double),
    Column("closed_by", Text),
    Index("ix_debt_model", "model_id", "status"),
)


# --------------------------------------------------------------------------
# Scheduled runs
# --------------------------------------------------------------------------
# What the scheduler did, and when. Not a queue and not a task list: every job
# is idempotent and derives its own work from the register, so this table is a
# record of activity rather than a source of it. Deleting every row here would
# change nothing about what the next run does.
SCHEDULED_RUN = Table(
    "scheduled_run", METADATA,
    Column("id", Text, primary_key=True),
    Column("job", Text, nullable=False),
    Column("outcome", Text, nullable=False, server_default=text("'{}'")),
    Column("ok", Boolean, nullable=False, server_default=true()),
    Column("error", Text),
    Column("duration_ms", Double, nullable=False, server_default=text('0')),
    Column("ran_by", Text, nullable=False),
    Column("ran_at", Double, nullable=False),
    Index("ix_scheduled_run_job", "job", "ran_at"),
)


# --------------------------------------------------------------------------
# Attached documents
# --------------------------------------------------------------------------
# The documents somebody wrote, as opposed to the ones the platform compiles: a
# model development document in Word, a vendor's validation report, a committee
# minute, a signed attestation. A register that holds only what it can compute
# quietly excludes most of the evidence a supervisor will ask to see.
#
# `model_version_id` is the point. "The model development document" is about a
# particular version, and one filed at model level floats free of what it
# describes -- which is how a bank ends up with an MDD for v2.1 against a model
# serving v2.4. Version-level is the default; model-level has to be asked for.
#
# `digest` is content-addressed storage, so the same board paper across forty
# models is one object, and editing a document in place is impossible: a changed
# byte is a changed digest, which is a supersession somebody declares.
ATTACHMENT = Table(
    "attachment", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    # What this document is ABOUT. A methodology paper is about the
    # model, a convergence study about one parameter set, a data
    # dictionary about a featureset VERSION — and a document filed
    # against a featureset rather than a version would describe
    # something that has since moved.
    Column("subject_type", Text, nullable=False, server_default=text("'model_version'")),
    Column("subject_id", Text),
    Column("kind", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("filename", Text, nullable=False),
    Column("media_type", Text, nullable=False, server_default=text("'application/octet-stream'")),
    Column("digest", Text, nullable=False),
    Column("size_bytes", Integer, nullable=False, server_default=text('0')),
    Column("text_indexed", Boolean, nullable=False, server_default=false()),
    Column("state", Text, nullable=False, server_default=text("'attached'")),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("attached_by", Text, nullable=False),
    Column("attached_at", Double, nullable=False),
    Column("reviewed_by", Text),
    Column("reviewed_at", Double),
    Column("review_note", Text, nullable=False, server_default=text("''")),
    Column("supersedes", Text),
    Column("superseded_by", Text),
    Index("ix_attachment_model", "model_id", "state"),
    Index("ix_attachment_version", "model_version_id", "kind"),
)


# A model's stated limitations, structured rather than buried in a document.
#
# The operating CONTRACT already carries what can be checked: `dscr` between
# -5 and 20, refused at execution. What it cannot carry is everything a model
# risk manager actually writes — "calibrated on 2019-2024 and never through a
# rate shock above 400bp", "assumes the sector mix is stable", "the LGD is a
# flat haircut and not modelled". Those live in a PDF nobody can query, and
# the question a supervisor asks is exactly a query: WHICH of this model's
# limitations are enforced and which are only written down?
#
# So each row says which it is. `bound_key` names the contract clause that
# enforces it, or is null — and null is the interesting value, because it is
# the count of things this platform is trusting a person to remember.
MODEL_LIMITATION = Table(
    "model_limitation", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text, nullable=False),
    Column("reference", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("statement", Text, nullable=False),
    # The contract clause that enforces this, if one does. Null means the
    # limitation is stated and not enforced, which is a fact worth counting.
    Column("bound_key", Text),
    Column("basis", Text, nullable=False, server_default=text("''")),
    # SS1/23 1.2(c)(ii) asks for more than the statement. `raised_by` is who
    # wrote it down; `owner` is who is accountable for it, and they are
    # routinely not the same person — a validator raises what an owner then
    # carries. `materiality` is why one of forty limitations is read first.
    # `mitigation` is what compensates when the limitation bites, and its
    # emptiness is the interesting value: a material limitation with no
    # mitigation is a risk nobody has decided about.
    Column("owner", Text, nullable=False, server_default=text("''")),
    Column("materiality", Text, nullable=False, server_default=text("'moderate'")),
    Column("mitigation", Text, nullable=False, server_default=text("''")),
    # When somebody must look again. A limitation is stated against an
    # immutable version, but the world it describes moves.
    Column("review_due", Double),
    # The finding raised about this, and the overlay compensating for it. Both
    # null by default: an unlinked limitation is the common case and the links
    # exist so that "what are we doing about it" is a query rather than an
    # interview.
    Column("finding_id", Text),
    Column("overlay_id", Text),
    Column("raised_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("withdrawn_at", Double),
    Column("withdrawn_by", Text),
    Column("withdrawal_reason", Text),
    Index("uq_model_limitation_model_version_id_reference", "model_version_id", "reference", unique=True),
)


# What a model RELIES ON being true, as against what it cannot do.
#
# The distinction is not pedantry and it decides where a row belongs. A
# limitation is a boundary of competence: "LGD is a flat haircut and is not
# modelled". An assumption is a claim about the world the model reads: "the
# sector mix is stable". The difference that matters to a supervisor is that an
# assumption CAN STOP BEING TRUE while the model is running, and a limitation
# cannot — it is simply what the model is.
#
# So the sibling question is different too. The limitation register counts what
# is enforced against what is only written down. This one counts what is
# MONITORED against what is merely believed: `monitor_id` names the monitor
# that tests whether the assumption still holds, and null is the value worth
# having, because it is the count of things this platform believes on nobody's
# authority and would not notice becoming false.
MODEL_ASSUMPTION = Table(
    "model_assumption", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text, nullable=False),
    Column("reference", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("statement", Text, nullable=False),
    # The monitor that TESTS this assumption, if one does. Null means the
    # assumption is believed and unwatched.
    Column("monitor_id", Text),
    Column("basis", Text, nullable=False, server_default=text("''")),
    Column("owner", Text, nullable=False, server_default=text("''")),
    Column("materiality", Text, nullable=False, server_default=text("'moderate'")),
    Column("mitigation", Text, nullable=False, server_default=text("''")),
    Column("review_due", Double),
    Column("finding_id", Text),
    Column("overlay_id", Text),
    Column("raised_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("withdrawn_at", Double),
    Column("withdrawn_by", Text),
    Column("withdrawal_reason", Text),
    Index("uq_model_assumption_model_version_id_reference", "model_version_id", "reference", unique=True),
)






# What a model is used FOR, as a thing rather than as a string.
#
# `declared_use` on a warrant grant is a string, checked at resolution against
# the grant that carries it. That is enough to authorise a call and not enough
# for anything else: a use has no owner, no dates, no product and no legal
# entity, so risk cannot attach to one and *which models fed the Q2 provision*
# has no answer.
#
# The distinction that makes this worth a table: the same model used for two
# purposes is TWO RISK PROPOSITIONS. A PD model used at origination and used
# for provisioning carries different materiality, different regulatory
# expectations and different consequences of being wrong, and a register that
# holds one row for the model holds one answer for both.
#
# `effective_from` and `effective_to` are the other half. SR 26-2 asks about
# models being "misapplied or misused", and the commonest form of that is not a
# use nobody approved — it is a use somebody approved, for a period that ended,
# which nobody switched off.
MODEL_USE = Table(
    "model_use", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("reference", Text, nullable=False),
    # The string a warrant grant carries, so a grant and a use can be matched.
    Column("declared_use", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("purpose", Text, nullable=False, server_default=text("''")),
    # The dimensions the requirement names. Each is prose because each is the
    # institution's own vocabulary — a closed list here would be this
    # platform's opinion about how a bank divides itself up.
    Column("product", Text, nullable=False, server_default=text("''")),
    Column("legal_entity", Text, nullable=False, server_default=text("''")),
    Column("geography", Text, nullable=False, server_default=text("''")),
    Column("channel", Text, nullable=False, server_default=text("''")),
    Column("segment", Text, nullable=False, server_default=text("''")),
    # Who decides on the back of this model's output, which is not the same
    # person as its owner and is the one a supervisor asks for.
    Column("decision_authority", Text, nullable=False, server_default=text("''")),
    Column("owner", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Column("effective_from", Double, nullable=False),
    Column("effective_to", Double),
    Column("created_at", Double, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("retired_at", Double),
    Column("retired_by", Text),
    Column("retire_reason", Text),
    Index("uq_model_use_model_id_reference", "model_id", "reference", unique=True),
    Index("ix_model_use_declared_use", "declared_use"),
)

# What this model will be watched for, written down BEFORE it goes anywhere.
#
# A monitoring plan and a monitored model are different statements, and the
# gap between them is where estates actually fail. The plan is written at
# development time, argued over in validation, approved — and then somebody
# else, months later, creates whatever monitors seem reasonable. Nothing ever
# compared the two.
#
# So the plan is a row against a VERSION, and `inherited_at` is the column that
# matters: null means this model has a monitoring plan and is not monitored,
# which is a sentence no estate wants to be able to say about itself and every
# estate can.
MONITORING_PLAN = Table(
    "monitoring_plan", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text, nullable=False),
    # The monitors this model is to have, in the shape `monitors.define` takes.
    Column("items", Text, nullable=False, server_default=text("'[]'")),
    Column("rationale", Text, nullable=False, server_default=text("''")),
    Column("authored_by", Text, nullable=False),
    Column("authored_at", Double, nullable=False),
    # When the plan became actual monitors, and which ones. Null is the
    # interesting value.
    Column("inherited_at", Double),
    Column("inherited_by", Text),
    Column("monitor_ids", Text, nullable=False, server_default=text("'[]'")),
    Index("uq_monitoring_plan_model_version_id", "model_version_id", unique=True),
)

# Every time a warrant was actually USED, and how it went.
#
# Resolutions were evidence nodes and invocations were not recorded at all, so
# the register could say who was ENTITLED to run a model and never who did.
# Three questions had no answer: how much is this model actually used, when was
# this standing authorisation last exercised, and which grants has nobody used
# at all. The last one is a security question rather than a reporting one — a
# grant nobody has exercised in a year is an authorisation the estate is
# carrying for no reason, and least privilege says to withdraw it.
#
# What is recorded is deliberately the SHAPE of the call and not its content.
# No feature values, no prediction: those are `FR-MON-008`'s business, they
# carry personal data, and a table that quietly accumulated them would be a
# retention problem nobody decided to take on. What is here is who called,
# under what use, against which version, how long it took and how it ended.
WARRANT_INVOCATION = Table(
    "warrant_invocation", METADATA,
    Column("id", Text, primary_key=True),
    Column("warrant_id", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    Column("semver", Text),
    Column("principal", Text, nullable=False),
    Column("declared_use", Text, nullable=False),
    Column("environment", Text, nullable=False),
    Column("verb", Text, nullable=False, server_default=text("'score'")),
    # `ok`, `refused` or `error`. A refusal is a normal outcome and is recorded
    # as one — a log that only held successes would make a model look healthier
    # the more often it was refused.
    Column("outcome", Text, nullable=False),
    Column("refusal_code", Text),
    Column("latency_ms", Double),
    # What this call cost, where the caller can say. Nullable, and null means
    # "not reported" rather than "free" — a cost budget over a column that
    # silently reads zero would never be reached, which is the failure mode
    # worth designing against for a token-metered model.
    Column("cost", Double),
    Column("boundary_ok", Boolean),
    Column("request_id", Text),
    Column("at", Double, nullable=False),
    Index("ix_warrant_invocation_warrant_id", "warrant_id"),
    Index("ix_warrant_invocation_model_id_at", "model_id", "at"),
)

# A control this model is NOT meeting, and who said that was acceptable.
#
# Every estate has these and most keep them in a spreadsheet, which is how a
# temporary exception reaches its fourth year. Four rules are enforced here
# rather than trusted to process, and they are the overlay register's four
# rules pointed at a different object, because a waiver and a management
# adjustment fail in the same ways.
#
# MANDATORY EXPIRY. `expires_at` is not nullable. An exception with no end date
# is not an exception, it is a decision to stop applying a control, and it will
# outlive everybody who agreed to it.
#
# A COMPENSATING CONTROL IS REQUIRED. A waiver saying only "we are not doing
# this" records the gap and not the containment. What is being done instead is
# the half a reviewer needs, and its absence is the thing worth refusing.
#
# THE PROPOSER MAY NOT APPROVE. Same reason as everywhere else in this
# platform: one person who can both ask and grant is a preference.
#
# APPROVAL SCALES WITH THE TIER. A tier 1 model's waiver needs two signatures
# in two roles; a tier 4 model's needs one. The requirement calls this "an
# approval level scaled to risk", and the platform already has the quorum it
# needs for it.
CONTROL_WAIVER = Table(
    "control_waiver", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    # Nullable: a waiver can be about the model rather than one version of it —
    # "this model is not independently validated" outlives a version bump, and
    # forcing a version here would make it look as though it did not.
    Column("model_version_id", Text),
    Column("reference", Text, nullable=False),
    # WHICH control. Closed, and drawn from the controls the tiering engine
    # already requires per tier — a waiver naming a control nothing requires is
    # a waiver of nothing, and it would read on a report as though something
    # had been relaxed.
    Column("control", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("compensating_control", Text, nullable=False),
    Column("tier_at_grant", Integer),
    Column("status", Text, nullable=False, server_default=text("'proposed'")),
    Column("proposed_by", Text, nullable=False),
    Column("approved_by", Text),
    Column("approvals", Text, nullable=False, server_default=text("'[]'")),
    Column("granted_at", Double),
    Column("expires_at", Double, nullable=False),
    Column("renewals", Integer, nullable=False, server_default=text("0")),
    Column("finding_id", Text),
    Column("created_at", Double, nullable=False),
    Column("closed_at", Double),
    Column("closure_reason", Text),
    Index("uq_control_waiver_model_id_reference", "model_id", "reference", unique=True),
)

# API keys: how a service or a script authenticates without a password.
#
# A service principal signing in with a username and password over Basic has
# three problems a key does not. The password is a shared secret somebody typed
# and can retype elsewhere; it carries every permission the principal holds,
# forever; and rotating it means changing it in the register and in whatever
# holds it, at the same instant, or something stops working.
#
# What is stored here is a HASH. The secret is shown once, at creation, and
# never again — not in a log, not in the evidence chain, not on this table.
# `prefix` is the first characters of the key, stored in clear so a person can
# tell two keys apart in a list and match one to a leaked string without
# holding either.
API_KEY = Table(
    "api_key", METADATA,
    Column("id", Text, primary_key=True),
    Column("principal_id", Text, nullable=False),
    Column("username", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("prefix", Text, nullable=False),
    Column("key_hash", Text, nullable=False),
    # A key may hold a SUBSET of what its principal holds, never a superset —
    # checked at USE rather than only at creation, so a role change or a
    # suspension reaches every key immediately. Empty means "everything the
    # principal holds", which is the honest default for a key that replaces a
    # password and is stated rather than implied.
    Column("scopes", Text, nullable=False, server_default=text("'[]'")),
    Column("created_at", Double, nullable=False),
    Column("created_by", Text, nullable=False),
    # Every key expires. A key with no expiry is a credential nobody ever
    # reviews, and "we will rotate it later" is the sentence before an
    # incident.
    Column("expires_at", Double, nullable=False),
    Column("last_used_at", Double),
    # Kept so a key that has never been used, or has stopped being used, is
    # visible as such: an unused credential is one nobody would notice losing.
    Column("use_count", Integer, nullable=False, server_default=text('0')),
    Column("revoked_at", Double),
    Column("revoked_by", Text),
    Column("revoke_reason", Text),
    Index("uq_api_key_key_hash", "key_hash", unique=True),
    Index("uq_api_key_username_name", "username", "name", unique=True),
)


# Roles, in the register rather than in the source.
#
# They were a Python dictionary. That is fine for the eight this platform
# ships and wrong for everything a bank actually has: a "Model Validation Team
# Lead", a "Regional MRM", a "Quant Developer with production read" — each of
# which meant editing `core/authz/roles.py` and redeploying. Administration
# that requires a release is not administration.
#
# The eight built-in roles are seeded here from the definitions that used to be
# the whole story, and are marked `built_in`. They may be READ and they may not
# be edited or removed: they are what every document, tutorial and test in this
# repository refers to by name, and a platform whose vocabulary can be renamed
# underneath its own documentation is one where the documentation is wrong.
ROLE = Table(
    "role", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    # The permissions this role grants, as a JSON array. Every one is checked
    # against the closed permission set on the way in: a role granting a
    # permission nothing checks is a role that reads as authority and is not.
    Column("permissions", Text, nullable=False, server_default=text("'[]'")),
    # 0 or 1, never BOOLEAN. Whether this is one of the eight the platform
    # ships, which may not be edited.
    Column("built_in", Boolean, nullable=False, server_default=false()),
    Column("created_at", Double, nullable=False),
    Column("created_by", Text, nullable=False, server_default=text("'system'")),
    Column("updated_at", Double),
    Column("updated_by", Text),
    Index("uq_role_name", "name", unique=True),
)


# ------------------------------------------------------------- feature sources
# Where a feature view's values come FROM, when they are not uploaded.
#
# A source is PULLED, never read through. MAYA fetches from the SQL query, the
# file or the object store, and writes what it got into its own Delta table as
# a new version — so integrity, versioning and the two clocks stay MAYA's.
# Serving a model straight off somebody's warehouse table would give away every
# guarantee this platform exists to make: a table that has been overwritten
# cannot answer "what was knowable as of March", and a training set built from
# a live query is not reproducible.
#
# No secret is stored here. `credential_ref` NAMES a credential the deployment
# has configured; resolving it is the connector's job, and a register that held
# a warehouse password would be a register nobody could export.
FEATURE_SOURCE = Table(
    "feature_source", METADATA,
    Column("id", Text, primary_key=True),
    Column("view_name", Text, nullable=False),
    # sql | file | s3 | gcs — what to talk to, which decides how to read it.
    Column("kind", Text, nullable=False),
    # The connection URL, the path, or the s3://bucket/key. Never a secret.
    Column("locator", Text, nullable=False),
    # For a SQL source: the statement. Read-only by construction — the
    # connector refuses anything that is not a SELECT, because a "source" that
    # can UPDATE is not a source.
    Column("statement", Text, nullable=False, server_default=text("''")),
    # csv | jsonl | parquet | arrow, for a file or object source.
    Column("format", Text, nullable=False, server_default=text("''")),
    # Column mapping, CSV delimiter, region, and anything else a connector
    # needs. JSON as text, like every other document in this schema.
    Column("options", Text, nullable=False, server_default=text("'{}'")),
    # The NAME of a credential the deployment configured, not the credential.
    Column("credential_ref", Text),
    Column("enabled", Boolean, nullable=False, server_default=true()),
    # What the last pull actually did. Kept on the row so the screen can say
    # "last pulled, how many rows, and whether the bytes were the same" without
    # walking the evidence chain for it.
    Column("last_pulled_at", Double),
    Column("last_pull_rows", Integer),
    Column("last_pull_digest", Text),
    Column("last_pull_detail", Text, nullable=False, server_default=text("''")),
    Column("last_pull_version", Integer),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("retired_at", Double),
    Column("retired_by", Text),
    Column("retire_reason", Text),
    # One live source per view. A view filled from two places at once is a view
    # whose provenance is a question rather than a record — declare a second
    # view instead. As an INDEX and not a UNIQUE clause, so it reaches a
    # database that already exists.
    Index("uq_feature_source_view", "view_name", unique=True),
    Index("ix_feature_source_kind", "kind"),
)


#: Sorted, so a reader can find one and a diff stays legible.
TABLES = tuple(sorted(METADATA.tables))

__all__ = [
    "AI_CAPABILITY",
    "AI_GENERATION",
    "ALIAS",
    "ALIAS_HISTORY",
    "AMENDMENT",
    "API_KEY",
    "ATTACHMENT",
    "ATTESTATION",
    "ATTESTATION_SIGNATURE",
    "BASELINE_IMPORT",
    "BOARD_PACK",
    "BREACH",
    "COMPLIANCE_DEBT",
    "DATASET_SNAPSHOT",
    "DERIVED_FEATURE",
    "DOCUMENT",
    "EVIDENCE_CHECKPOINT",
    "EVIDENCE_NODE",
    "FEATURE",
    "FEATURESET",
    "FEATURESET_VERSION",
    "FEATURE_CONTRACT",
    "FEATURE_SOURCE",
    "FEATURE_VIEW",
    "FEATURE_VIEW_VERSION",
    "FINDING",
    "FINDING_ACTION",
    "METADATA",
    "MODEL",
    "MODEL_EDGE",
    "MODEL_LIMITATION",
    "MODEL_VERSION",
    "MONITOR",
    "NOTIFICATION",
    "OBSERVATION",
    "OVERLAY",
    "OVERLAY_MEASUREMENT",
    "PARAMETER_SET",
    "POLICY_RULE",
    "PRINCIPAL",
    "RISK_APPETITE",
    "RISK_ASSESSMENT",
    "ROLE",
    "SCHEDULED_RUN",
    "SERVING_ATTESTATION",
    "TABLES",
    "TELEMETRY_BATCH",
    "TEST_RESULT",
    "VALIDATION",
    "VERSION_APPROVAL",
    "VERSION_APPROVAL_SIGNATURE",
    "WARRANT",
    "WARRANT_PROFILE",
]

