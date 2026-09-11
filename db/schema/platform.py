"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Identity, evidence, documents, reporting and the platform's own AI.

One part of the schema. `db/schema/tables.py` still re-exports every
table and remains the only thing anything imports from — this split is
about a file somebody has to read, not about a new interface.
"""
from __future__ import annotations

from sqlalchemy import (Boolean, Column, Double, Index, Integer,
                        Table, Text, text)
from sqlalchemy.sql.expression import false, true

from db.schema.metadata import METADATA



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

# A matter that stops things being deleted.
#
# **This is the one control in the platform that must override the platform's
# own deletion**, and it is therefore the one place where the usual rule is
# inverted. Everywhere else an unbounded window is the failure — a waiver with
# no end date reaches its fourth year, a conditional approval with none is an
# unconditional approval that has not noticed. A legal hold has **no end date
# and that is correct**: it ends when the matter ends, and when the matter ends
# is not knowable when the hold is placed. Putting a date on it would be
# guessing at a litigation timetable and calling the guess a control.
#
# What replaces the deadline is a **named person and a stated matter**. A hold
# nobody owns is one nobody will lift, and a hold with no matter recorded is one
# nobody can tell has ended.
LEGAL_HOLD = Table(
    "legal_hold", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("matter", Text, nullable=False),
    Column("scope_kind", Text, nullable=False),
    # Null when the scope is the whole estate, which is a real and blunt
    # instrument: a regulator's document request does not arrive scoped to the
    # models you would have chosen.
    Column("scope_id", Text),
    Column("classes", Text, nullable=False, server_default=text("'[]'")),
    Column("owner", Text, nullable=False),
    Column("placed_by", Text, nullable=False),
    Column("placed_at", Double, nullable=False),
    Column("state", Text, nullable=False, server_default=text("'active'")),
    Column("lifted_at", Double),
    Column("lifted_by", Text),
    Column("lift_reason", Text, nullable=False, server_default=text("''")),
    Index("uq_legal_hold_reference", "reference", unique=True),
    Index("ix_legal_hold_state", "state", "scope_kind"),
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


# A query somebody wants to keep, and never the rows it returned.
#
# The rows are deliberately not here. A saved view that stored its result set
# would make sharing one a disclosure decision nobody realised they were
# making: the author's scope reaches models the reader's does not, and the
# stored rows would carry them across. Storing the QUERY means a shared view
# re-runs under whoever opens it, and two people running the same view
# legitimately see different numbers — which is the correct behaviour and the
# reason the answer says how many rows a scope removed.
SAVED_VIEW = Table(
    "saved_view", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("entity", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    # The structured query: selected fields, comparisons, order. Never text.
    Column("query", Text, nullable=False, server_default=text("'{}'")),
    Column("owner", Text, nullable=False),
    Column("shared", Boolean, nullable=False, server_default=false()),
    Column("created_at", Double, nullable=False),
    Column("last_run_at", Double),
    Index("uq_saved_view_name", "owner", "name", unique=True),
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

# Who wants to be told what, and where they have got to.
#
# **There is no event table.** The evidence chain already records every domain
# act, in a total order, hash-linked — so a subscription is a *cursor over the
# chain* rather than a copy of it. A second event log would be a second thing to
# keep in step, and the first time the two disagreed nobody would know which was
# true.
#
# `kinds` is required and `*` is refused. A chain node's payload carries model
# inventory, findings and exposure figures, so what may leave the institution is
# a deployment decision — and a subscription that receives everything is one
# nobody decided the content of.
EVENT_SUBSCRIPTION = Table(
    "event_subscription", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("kinds", Text, nullable=False, server_default=text("'[]'")),
    # Write-only. Returned on creation and never on a read: a secret a listing
    # endpoint hands back is a secret anybody with read access holds.
    Column("secret", Text, nullable=False),
    # Where this subscriber has got to in the chain. Per subscription, so one
    # failing receiver falls behind on its own rather than holding up the rest
    # or being silently skipped.
    Column("cursor", Integer, nullable=False, server_default=text('0')),
    Column("state", Text, nullable=False, server_default=text("'active'")),
    Column("failures", Integer, nullable=False, server_default=text('0')),
    Column("last_delivery_at", Double),
    Column("last_failure_at", Double),
    Column("last_failure", Text, nullable=False, server_default=text("''")),
    Column("owner", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("created_by", Text, nullable=False),
    Index("uq_event_subscription_reference", "reference", unique=True),
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


# A periodic activity, its population and the moment that population was fixed.
#
# The population is DERIVED at launch and then FROZEN, and the derivation is
# kept beside it. A campaign whose population is a live query silently changes
# size: a model retired mid-campaign turns 47 of 50 into 47 of 49 and the
# completion figure goes UP without anybody doing anything, which is the one
# number a campaign exists to produce. So completion is measured against the
# frozen population, coverage against re-running the derivation, and the drift
# between them is reported rather than resolved.
CAMPAIGN = Table(
    "campaign", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("instruction", Text, nullable=False, server_default=text("''")),
    # The structured query the population came from, kept so it can be re-run.
    Column("derivation", Text, nullable=False, server_default=text("'{}'")),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("due_at", Double),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("closed_at", Double),
    Column("closed_by", Text),
    Index("uq_campaign_reference", "reference", unique=True),
)


# One model's place in one campaign, and who it fell to.
#
# The assignee is derived from the register at launch — the model's own owner —
# and never typed. A campaign with typed assignees is one that ends up assigned
# to people who left, and the reassignment is recorded as an act rather than an
# edit, because "who was this originally for" is the question asked when it was
# not done.
CAMPAIGN_ITEM = Table(
    "campaign_item", METADATA,
    Column("id", Text, primary_key=True),
    Column("campaign_id", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("urn", Text, nullable=False),
    Column("assignee", Text, nullable=False),
    Column("assigned_at", Double, nullable=False),
    Column("state", Text, nullable=False, server_default=text("'outstanding'")),
    Column("response", Text, nullable=False, server_default=text("''")),
    Column("responded_by", Text),
    Column("responded_at", Double),
    Index("uq_campaign_item", "campaign_id", "model_id", unique=True),
)


# A proposal, which is not a model.
#
# It has no version, no artifact and nothing that can resolve it, and keeping it
# in the model table would be the fastest way to turn a register into an
# inventory of ideas. Triage answers three questions and the most valuable
# answer is "this is not a model at all" — a register that admits everything is
# one nobody can read.
INTAKE_PROPOSAL = Table(
    "intake_proposal", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("proposed_by", Text, nullable=False),
    Column("business_area", Text, nullable=False, server_default=text("''")),
    Column("proposed_at", Double, nullable=False),
    # What triage concluded, and on what facts. Held even when the answer is
    # "not a model": a proposal declined and forgotten comes back next year.
    Column("in_scope", Boolean),
    Column("sourcing", Text),
    Column("generative", Boolean),
    Column("rationale", Text, nullable=False, server_default=text("'{}'")),
    Column("state", Text, nullable=False, server_default=text("'proposed'")),
    Column("triaged_by", Text),
    Column("triaged_at", Double),
    Column("registered_urn", Text),
    Index("uq_intake_reference", "reference", unique=True),
)


# A remark on one section of a compiled document, and the state it is in.
#
# Deliberately NOT an edit. A compiled document is assembled from evidence and
# every sentence in it cites a node; editing the prose would break the citation
# without changing the record it cites, producing a document that reads
# correctly and is no longer traceable to anything. So a reviewer comments, and
# the fix for a wrong sentence is a fix to the record it was compiled from.
#
# Comments attach to a document by DIGEST rather than by id, because a document
# is recompiled and the question a reviewer is answering is about the version
# they read. A comment carried forward onto a recompilation would be a remark
# about text that may no longer be there.
DOCUMENT_COMMENT = Table(
    "document_comment", METADATA,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, nullable=False),
    Column("document_digest", Text, nullable=False),
    Column("section", Text, nullable=False),
    Column("quote", Text, nullable=False, server_default=text("''")),
    Column("body", Text, nullable=False),
    # What the commenter wants done. A closed list, because "please look at
    # this" and "this is factually wrong" are different obligations and a free
    # text field makes them the same one.
    Column("asks_for", Text, nullable=False, server_default=text("'comment'")),
    Column("raised_by", Text, nullable=False),
    Column("raised_at", Double, nullable=False),
    Column("state", Text, nullable=False, server_default=text("'open'")),
    Column("resolution", Text, nullable=False, server_default=text("''")),
    Column("resolved_by", Text),
    Column("resolved_at", Double),
    # Where a comment led to a change in the RECORD rather than in the prose.
    Column("evidence_id", Text),
    Index("ix_document_comment", "document_id", "state"),
)


# A pack handed to somebody who has no login here.
#
# An examiner portal that authenticated examiners INTO the register would give a
# third party a session in the bank's governance system, with whatever that
# session can reach. This is the other shape: a time-boxed, scope-limited link
# to bytes that were already sealed. The pack is content-addressed and
# self-contained, so what the reader sees cannot drift from what was cut — and
# a share is a read of one archive rather than a view of a live estate.
#
# Every access is recorded. "Who read what, and when" is the question asked
# after something has gone wrong, and by then the answer has to already exist.
EXPORT_SHARE = Table(
    "export_share", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("model_id", Text),
    Column("urn", Text, nullable=False),
    # The pack this share serves, by content. Not a path: a share pointing at a
    # location would serve whatever is at that location later.
    Column("content_digest", Text, nullable=False),
    Column("pack_digest", Text, nullable=False),
    Column("filename", Text, nullable=False, server_default=text("''")),
    Column("recipient", Text, nullable=False),
    Column("purpose", Text, nullable=False, server_default=text("''")),
    # Mandatory and bounded, like every other window in this platform. A share
    # with no end is a standing grant of a bank's model record to somebody
    # outside it.
    Column("expires_at", Double, nullable=False),
    Column("max_reads", Integer),
    Column("reads", Integer, nullable=False, server_default=text('0')),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("created_by", Text, nullable=False),
    Column("created_at", Double, nullable=False),
    Column("revoked_at", Double),
    Column("revoked_by", Text),
    Column("revoke_reason", Text, nullable=False, server_default=text("''")),
    Index("uq_export_share_reference", "reference", unique=True),
)


# One read of a shared pack. Append-only in practice.
EXPORT_SHARE_READ = Table(
    "export_share_read", METADATA,
    Column("id", Text, primary_key=True),
    Column("share_id", Text, nullable=False),
    Column("at", Double, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("detail", Text, nullable=False, server_default=text("''")),
    Index("ix_export_share_read", "share_id", "at"),
)


# One attested cost figure, attributed from the register.
#
# **M-6**, and the shape is forced by what MAYA is: it does not run models, so
# it cannot observe what one costs. A figure arrives attested — from a named
# source, over a stated period — the same way an external monitoring
# observation does, and MAYA does the half it can: attribution, from ownership
# the register already holds.
#
# `owner`, `legal_entity` and `domain` are COPIED from the model at record time
# rather than joined at read time, and that is deliberate. A showback report for
# last quarter must say who owned the model last quarter; joining live would
# re-attribute a historical cost to whoever holds it today, which is how a cost
# report quietly stops agreeing with the one issued three months ago.
#
# `state` carries `unattributed` as a first-class outcome. A bill line nobody
# can tie to a registered model is the finding this whole table exists to
# surface, and refusing the row would delete it.
ESTATE_COST = Table(
    "estate_cost", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text),
    Column("urn", Text, nullable=False, server_default=text("''")),
    Column("amount", Double, nullable=False),
    # Stated rather than assumed. An estate spanning entities spans currencies,
    # and a total summed across them silently is wrong by the exchange rate.
    Column("currency", Text, nullable=False),
    Column("period_start", Double, nullable=False),
    Column("period_end", Double, nullable=False),
    Column("source", Text, nullable=False),
    Column("reference", Text, nullable=False, server_default=text("''")),
    Column("owner", Text, nullable=False, server_default=text("''")),
    Column("legal_entity", Text, nullable=False, server_default=text("''")),
    Column("domain", Text, nullable=False, server_default=text("''")),
    Column("state", Text, nullable=False,
           server_default=text("'attributed'")),
    Column("recorded_by", Text, nullable=False),
    Column("recorded_at", Double, nullable=False),
    Index("ix_estate_cost_period", "period_start", "period_end"),
    Index("ix_estate_cost_model", "model_id", "period_start"),
)


# --------------------------------------------------------------------------
# FR-LC-005. The delegated authority matrix, and what an amount MAYA does not
# have counts as.
#
# Two tables because they are two different kinds of fact. A BAND is a rule the
# firm published — which signatures a decision of this shape needs. A
# DELEGATION is an authority a named person holds, granted by an instrument
# MAYA cannot read. Conflating them produces the thing this feature exists to
# prevent: a matrix that looks enforced because everyone in it holds a role.
AUTHORITY_BAND = Table(
    "authority_band", METADATA,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    # NULL means every tier. The dimensions are nullable on purpose: a firm
    # adds a row for one entity without restating the estate, and bands are
    # matched most-specific-first.
    Column("tier", Integer, nullable=True),
    Column("at_or_above", Double, nullable=False, server_default=text("0")),
    Column("legal_entity", Text, nullable=True),
    # A list of lists: roles that sign together, stages that sign in order. A
    # flat role list cannot express sequencing, and sequencing is the half of
    # this requirement a quorum does not cover.
    Column("stages", Text, nullable=False, server_default=text("'[]'")),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("published_by", Text, nullable=False),
    Column("published_at", Double, nullable=False),
    Index("uq_authority_band", "name", unique=True),
)

AUTHORITY_DELEGATION = Table(
    "authority_delegation", METADATA,
    Column("id", Text, primary_key=True),
    Column("principal", Text, nullable=False),
    Column("ceiling", Double, nullable=False),
    Column("currency", Text, nullable=False, server_default=text("'USD'")),
    # NULL means every entity. Authority is granted by an entity's board and
    # does not travel, so a row scoped to one is the normal case.
    Column("legal_entity", Text, nullable=True),
    # The resolution, charter or letter. Required, because MAYA holds the
    # reference rather than the document, and a delegation with no reference is
    # indistinguishable from somebody's recollection.
    Column("instrument", Text, nullable=False),
    Column("granted_by", Text, nullable=False),
    Column("granted_at", Double, nullable=False),
    # An expired delegation grants nothing. MAYA cannot check whether the
    # instrument still says what it said, so the register makes somebody look.
    Column("expires_at", Double, nullable=False),
    Index("ix_authority_delegation_principal", "principal", "expires_at"),
)
