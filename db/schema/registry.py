"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The register itself: models, versions, aliases and what a model says about itself.

One part of the schema. `db/schema/tables.py` still re-exports every
table and remains the only thing anything imports from — this split is
about a file somebody has to read, not about a new interface.
"""
from __future__ import annotations

from sqlalchemy import (Boolean, Column, Double, Index, Integer,
                        Table, Text, text)
from sqlalchemy.sql.expression import false, true

from db.schema.metadata import METADATA



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


VERSION_APPROVAL = Table(
    "version_approval", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text, nullable=False),
    Column("tier", Integer),
    Column("required_roles", Text, nullable=False, server_default=text("'[]'")),
    # Which band of the authority matrix this approval was opened under, where
    # one is published, and the ORDER that band required.
    #
    # Both written at open time. The name alone was not enough: sequencing was
    # recomputed from the live matrix at signing time, so withdrawing the band
    # silently changed the order an open approval was held to — the exact thing
    # this column's first version claimed to prevent. The stages travel with
    # the approval so that nothing at signing time needs to consult the matrix.
    Column("band", Text, nullable=True),
    Column("stages", Text, nullable=False, server_default=text("'[]'")),
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


# is the same candidate, not a new one. A path is not enough — files move — so
# it is whatever the scanner can compute that survives being moved.
DISCOVERY_CANDIDATE = Table(
    "discovery_candidate", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("scanner", Text, nullable=False),
    Column("fingerprint", Text, nullable=False),
    Column("location", Text, nullable=False),
    Column("evidence", Text, nullable=False, server_default=text("'{}'")),
    # What the scanner thought it was, and how sure. Recorded because the
    # precision of a scanner is measured against these, and a scanner nobody
    # measures is one nobody should scale up.
    Column("proposed_as", Text, nullable=False, server_default=text("'model'")),
    Column("confidence", Double),
    Column("state", Text, nullable=False, server_default=text("'open'")),
    Column("outcome", Text),
    Column("outcome_note", Text, nullable=False, server_default=text("''")),
    Column("registered_urn", Text),
    Column("triaged_by", Text),
    Column("triaged_at", Double),
    Column("found_at", Double, nullable=False),
    Column("last_seen_at", Double, nullable=False),
    Index("uq_discovery_fingerprint", "scanner", "fingerprint", unique=True),
    Index("ix_discovery_state", "state", "scanner"),
)

# A permission a supervisor gave, with what it covers and when it lapses.
#
# **A regulatory approval is not a tier and not a control**, and putting it in
# either would lose what makes it different: it is somebody else's decision
# about a defined scope, and it expires. IRB permission is granted for named
# portfolios; an FRTB IMA desk approval is granted for a desk and withdrawn when
# the desk fails its P&L attribution. A register that recorded "approved" as a
# flag on a model would be unable to answer the two questions that matter —
# *for what* and *until when*.
#
# `conditions` is free text on purpose: a supervisor's conditions are the
# supervisor's words, and normalising them into a vocabulary this platform
# invented would be paraphrasing a regulator.
REGULATORY_APPROVAL = Table(
    "regulatory_approval", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("model_id", Text),
    Column("kind", Text, nullable=False),
    Column("regulator", Text, nullable=False),
    Column("scope", Text, nullable=False),
    Column("conditions", Text, nullable=False, server_default=text("''")),
    Column("granted_at", Double, nullable=False),
    # Nullable, and null means "no stated end" rather than "forever". IRB
    # permission has no expiry date and is withdrawn rather than lapsing, which
    # is a different fact from a desk approval that runs to a date.
    Column("expires_at", Double),
    Column("state", Text, nullable=False, server_default=text("'in_force'")),
    Column("withdrawn_at", Double),
    Column("withdrawn_by", Text),
    Column("withdrawal_reason", Text, nullable=False, server_default=text("''")),
    Column("recorded_by", Text, nullable=False),
    Column("recorded_at", Double, nullable=False),
    Index("uq_regulatory_approval_reference", "reference", unique=True),
    Index("ix_regulatory_approval_model", "model_id", "state"),
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


# A panel asked a question, and the spread that is the answer.
#
# T7 parameters come out of expert judgement, and the value of an elicitation is
# not the number it produced — it is the DISAGREEMENT it recorded on the way.
# A process that stores only the final weights has destroyed the evidence that
# the panel disagreed, and *how much did they disagree* is the first question a
# validator asks about a judgemental parameter.
ELICITATION = Table(
    "elicitation", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("model_version_id", Text),
    Column("question", Text, nullable=False),
    Column("units", Text, nullable=False, server_default=text("''")),
    Column("panel", Text, nullable=False, server_default=text("'[]'")),
    Column("facilitator", Text, nullable=False),
    Column("method", Text, nullable=False, server_default=text("'delphi'")),
    Column("round", Integer, nullable=False, server_default=text('1')),
    Column("state", Text, nullable=False, server_default=text("'open'")),
    # The number the panel arrived at, and the dissent attached to it. A final
    # weight whose dissent nobody can find is a weight that looks unanimous.
    Column("final_value", Double),
    Column("final_note", Text, nullable=False, server_default=text("''")),
    Column("concluded_by", Text),
    Column("opened_at", Double, nullable=False),
    Column("concluded_at", Double),
    Index("uq_elicitation_reference", "reference", unique=True),
)


# One panellist's answer in one round. Append-only in practice: a response
# revised in place would erase the movement between rounds, which is the only
# thing convergence can be measured from.
ELICITATION_RESPONSE = Table(
    "elicitation_response", METADATA,
    Column("id", Text, primary_key=True),
    Column("elicitation_id", Text, nullable=False),
    Column("round", Integer, nullable=False),
    Column("panellist", Text, nullable=False),
    Column("value", Double),
    Column("confidence", Text, nullable=False, server_default=text("''")),
    Column("reasoning", Text, nullable=False, server_default=text("''")),
    # Recorded rather than refused. In a small firm the only person who
    # understands the model is its developer, and refusing would push the
    # elicitation off the platform entirely — so the conflict is named.
    Column("independent", Boolean, nullable=False, server_default=true()),
    Column("dissented", Boolean, nullable=False, server_default=false()),
    Column("recorded_at", Double, nullable=False),
    Index("uq_elicitation_response", "elicitation_id", "round", "panellist",
          unique=True),
)


# Where a tiering fact came from.
#
# `exposure` is a float on the assessment request and the tier is a monotone
# function of it — so the number deciding how many signatures an approval needs
# is typed in by the person the controls apply to. That is **H-8**, and the
# audit half already worked: the fact snapshot is stored with every assessment,
# so *what was claimed* is on the record.
#
# What was missing is the difference between a claim and a measurement. This
# table is that difference, and it is deliberately an ATTESTATION rather than a
# fetch: MAYA holds no connection to a general ledger and acquiring one would
# be the same standing-access objection the connectors answer.
#
# `reference` is NOT NULL for a reason that is not tidiness. "Finance said so"
# cannot be checked by the person who has to rely on it a year later, and the
# whole value of the row is that somebody can go and look.
#
# Append-only in practice: a fact re-sourced is a new row, so the history of
# what was claimed when survives a correction. The read takes the latest.
TIERING_FACT_SOURCE = Table(
    "tiering_fact_source", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("fact", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("reference", Text, nullable=False),
    Column("value", Text, nullable=False, server_default=text("''")),
    # When the figure was TRUE, as against when somebody recorded it here. A
    # twelve-month-old ledger extract is not a measurement of today's exposure,
    # and this column is what lets the read say `stale` rather than `sourced`.
    Column("as_at", Double, nullable=False),
    Column("recorded_by", Text, nullable=False),
    Column("recorded_at", Double, nullable=False),
    Index("ix_tiering_fact_source", "model_id", "fact", "recorded_at"),
)


# Taking a model out of service, properly.
#
# `retire` was always a governed transition that deletes nothing and requires a
# reason — the hard half, built first. What `FR-INV-018` asks for on top is four
# facts, and every one is a thing a firm discovers it needed MONTHS later: why,
# what does this job now, who was relying on it, and how long do we keep it.
#
# None is hard to store. They go missing because retiring a model is the moment
# everybody involved has stopped caring about it, and a form field nobody is
# required to fill in is a form field left empty. So this table is separate from
# the transition and its service refuses the three silent versions.
#
# `unnotified` is stored ALONGSIDE `notified` rather than derived at read time.
# Who depended on the model at the moment it was withdrawn is a fact about that
# moment; recomputing it later would answer a different question, and would
# answer it differently every time the graph changed.
MODEL_DECOMMISSION = Table(
    "model_decommission", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("urn", Text, nullable=False),
    Column("rationale", Text, nullable=False),
    # A registered URN or the literal 'none'. Not free text: *replaced by the
    # new scorecard* is a sentence, and the question it is meant to answer is
    # asked in two years by somebody who cannot ask you.
    Column("replacement", Text, nullable=False),
    Column("retention_class", Text, nullable=False),
    Column("notified", Text, nullable=False, server_default=text("'[]'")),
    Column("unnotified", Text, nullable=False, server_default=text("'[]'")),
    # Somebody looked at the unnotified list and decided anyway. A different
    # fact from nobody having looked, and the reason the refusal is escapable.
    Column("acknowledged", Boolean, nullable=False, server_default=false()),
    Column("consumers_known", Boolean, nullable=False, server_default=false()),
    Column("decommissioned_by", Text, nullable=False),
    Column("decommissioned_at", Double, nullable=False),
    Index("uq_model_decommission", "model_id", unique=True),
)
