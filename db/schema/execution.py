"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Warrants, what they authorise, and what was actually asked.

One part of the schema. `db/schema/tables.py` still re-exports every
table and remains the only thing anything imports from — this split is
about a file somebody has to read, not about a new interface.
"""
from __future__ import annotations

from sqlalchemy import (Boolean, Column, Double, Index, Integer,
                        Table, Text, text)
from sqlalchemy.sql.expression import false

from db.schema.metadata import METADATA



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

# A challenger running beside the champion, and what each was asked.
#
# **MAYA runs neither.** It registers that a parallel run is happening, takes
# delivery of what both produced, and reports the shape of the disagreement —
# which is the same position it takes on every other execution.
#
# The pairing is keyed on the INPUT, and that is not bookkeeping: a parallel run
# whose champion and challenger were not asked the same question is not a
# parallel run, it is two unrelated series printed side by side. Rows arrive one
# observation at a time and are matched on `input_key`.
#
# `outcome` is nullable and usually null when the row is written. That is the
# whole difficulty of the requirement: the two models disagreeing is knowable
# immediately, and which of them was RIGHT is not knowable until the label
# arrives — often months later. A dashboard that conflates the two is the
# commonest failure in shadow deployment.
PARALLEL_RUN = Table(
    "parallel_run", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("champion_version_id", Text, nullable=False),
    Column("challenger_version_id", Text, nullable=False),
    Column("champion_semver", Text, nullable=False),
    Column("challenger_semver", Text, nullable=False),
    Column("purpose", Text, nullable=False),
    Column("tolerance", Double, nullable=False, server_default=text('1e-9')),
    Column("state", Text, nullable=False, server_default=text("'running'")),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("closed_at", Double),
    Column("closed_by", Text),
    Column("conclusion", Text),
    Column("close_note", Text, nullable=False, server_default=text("''")),
    Index("uq_parallel_run_reference", "reference", unique=True),
    Index("ix_parallel_run_model", "model_id", "state"),
)


# One observation: what both were asked, what each answered, and — later, if
# ever — what actually happened.
PARALLEL_OBSERVATION = Table(
    "parallel_observation", METADATA,
    Column("id", Text, primary_key=True),
    Column("run_id", Text, nullable=False),
    Column("input_key", Text, nullable=False),
    Column("champion", Double),
    Column("challenger", Double),
    # Null until the label arrives, which is the point. Recorded separately from
    # the predictions because it comes from somewhere else and at another time.
    Column("outcome", Double),
    Column("outcome_at", Double),
    Column("at", Double, nullable=False),
    Index("uq_parallel_observation", "run_id", "input_key", unique=True),
    Index("ix_parallel_observation_run", "run_id"),
)


# An activity somebody else executed, declared before it ran.
#
# MAYA is always the callee: it does not submit jobs and does not fetch logs.
# Fetching them would make the register a client of every compute backend and
# put it on the failure path of the thing it exists to observe, so the log
# location is recorded and never read.
#
# The important word is BEFORE. A run recorded only on success is a register of
# successes, and the runs that matter most are the ones that failed or never
# came back — a fit that started, consumed a warrant and vanished is invisible
# in every training tracker that writes its row at the end. An open run past
# its expected duration is `lost`, and lost is a state rather than an absence.
RUN = Table(
    "run", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("model_id", Text),
    Column("model_version_id", Text),
    # One of the ten warrant verbs. The same vocabulary, because a run and the
    # authority for it must not be able to describe the activity differently.
    Column("verb", Text, nullable=False),
    Column("warrant_id", Text),
    # A hyperparameter search is a parent with children. The number nobody
    # reports is how many children were run and discarded, and it is the number
    # that makes a multiple-comparisons problem visible.
    Column("parent_id", Text),
    Column("purpose", Text, nullable=False, server_default=text("''")),
    Column("resource_profile", Text, nullable=False, server_default=text("'{}'")),
    Column("environment", Text, nullable=False, server_default=text("'{}'")),
    Column("inputs", Text, nullable=False, server_default=text("'{}'")),
    Column("hyperparameters", Text, nullable=False, server_default=text("'{}'")),
    Column("seeds", Text, nullable=False, server_default=text("'{}'")),
    Column("log_uri", Text, nullable=False, server_default=text("''")),
    Column("metrics", Text, nullable=False, server_default=text("'{}'")),
    Column("parameter_set_id", Text),
    Column("state", Text, nullable=False, server_default=text("'open'")),
    Column("outcome_note", Text, nullable=False, server_default=text("''")),
    Column("expected_seconds", Double),
    Column("cost", Double),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("closed_at", Double),
    Column("closed_by", Text),
    Index("uq_run_reference", "reference", unique=True),
    Index("ix_run_parent", "parent_id", "state"),
)


# The standing policy under which a re-fit may be accepted without a person.
#
# It approves a PROCEDURE and never a result: a committee cannot meet every
# morning, and the alternative to a standing approval is a recalibration that
# happens anyway with nobody's name on it. Tier 1 is never eligible and the
# ceiling is enforced rather than documented, because the first thing anybody
# asks of an auto-promotion policy is whether it can be widened.
RETRAIN_POLICY = Table(
    "retrain_policy", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("triggers", Text, nullable=False, server_default=text("'[]'")),
    Column("tolerance", Text, nullable=False, server_default=text("'{}'")),
    Column("auto_accept", Boolean, nullable=False, server_default=false()),
    Column("rationale", Text, nullable=False, server_default=text("''")),
    Column("declared_by", Text, nullable=False),
    Column("approved_by", Text),
    Column("declared_at", Double, nullable=False),
    Column("expires_at", Double),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    Index("uq_retrain_policy_model", "model_id", unique=True),
)
