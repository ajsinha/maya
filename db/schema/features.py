"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature platform: what a model reads, and the two clocks it reads it on.

One part of the schema. `db/schema/tables.py` still re-exports every
table and remains the only thing anything imports from — this split is
about a file somebody has to read, not about a new interface.
"""
from __future__ import annotations

from sqlalchemy import (BigInteger, Boolean, Column, Double, Index, Integer,
                        Table, Text, text)
from sqlalchemy.sql.expression import false, true

from db.schema.metadata import METADATA



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
