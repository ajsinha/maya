"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Challenge, measurement and the things they raise.

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
    # The shared cause, when somebody named one. NULL is the ordinary state:
    # most findings are about one model and have no root, and correlation is
    # ASSERTED rather than inferred — a guess that grouped two unrelated
    # findings would hide one behind the other's closure.
    Column("root_id", Text),
    Index("ix_finding_open", "model_id", "status", "severity"),
    Index("ix_finding_root", "root_id"),
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
    # Who computed this number. MAYA takes results from an MLOps platform, a
    # quant notebook or a vendor dashboard, because insisting on recomputing
    # them would make the firm run everything twice. It never takes the
    # verdict: the threshold is this firm's and the comparison happens here.
    # Provenance is a column rather than a detail string because an estate
    # where most numbers cannot be replayed is a finding about the programme,
    # and one that is invisible if the two kinds of number print the same.
    Column("source", Text, nullable=False, server_default=text("'maya'")),
    Column("computed_by", Text, nullable=False, server_default=text("''")),
    Column("method", Text, nullable=False, server_default=text("''")),
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

# What a firm has done about a model it did not build.
#
# SR 26-2 VII and SS1/23 2.6 both say the same thing and it is the thing firms
# get wrong: **you cannot validate what you cannot see, so what is validated is
# your USE of the model, not the model.** A vendor's validation report describes
# the vendor's development on the vendor's data; filing it and calling the model
# validated is validating somebody else's work.
#
# So the register keeps three things apart. A **due-diligence item** is a
# question the firm answered about the vendor. A **vendor attestation** is
# evidence that the vendor SAID something — recorded with its date and its
# scope, and going stale — and it discharges nothing that only the firm's own
# outcomes can discharge. **Customisation** is what the firm changed, which
# matters because a customised vendor model is neither the vendor's model nor
# the firm's, and both parties will say so when it goes wrong.
VENDOR_ASSESSMENT = Table(
    "vendor_assessment", METADATA,
    Column("id", Text, primary_key=True),
    Column("model_id", Text, nullable=False),
    Column("reference", Text, nullable=False),
    Column("vendor", Text, nullable=False),
    Column("product", Text, nullable=False),
    Column("vendor_version", Text, nullable=False),
    # The digest of what was actually installed, where the firm can compute it.
    # A vendor version string identifies what the vendor calls it; this
    # identifies what is running — and the two part company at every silent
    # upgrade, which is the failure this column exists for.
    Column("artifact_digest", Text),
    Column("kind", Text, nullable=False),
    Column("state", Text, nullable=False, server_default=text("'open'")),
    # Free text answering "what did you change", or empty. Empty is a real
    # answer and a different one from unanswered, which is why the column is
    # NOT NULL and the checklist item is what records whether anybody said.
    Column("customisation", Text, nullable=False, server_default=text("''")),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("concluded_at", Double),
    Column("concluded_by", Text),
    Column("conclusion", Text),
    Column("conclusion_note", Text, nullable=False, server_default=text("''")),
    Index("uq_vendor_assessment_reference", "reference", unique=True),
    Index("ix_vendor_assessment_model", "model_id", "state"),
)


# One question the firm answered about a model it did not build, or one thing
# the vendor said. Kept in one table because both are *findings of the same
# assessment* — and separated by `kind`, because what discharges them differs
# absolutely.
VENDOR_ITEM = Table(
    "vendor_item", METADATA,
    Column("id", Text, primary_key=True),
    Column("assessment_id", Text, nullable=False),
    Column("item", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("answer", Text, nullable=False, server_default=text("''")),
    Column("evidence", Text, nullable=False, server_default=text("'[]'")),
    Column("answered_by", Text),
    Column("answered_at", Double),
    # For a vendor attestation: when the vendor said it and what it covered.
    # A statement with no date is one nobody can tell is current.
    Column("stated_at", Double),
    Column("covers_version", Text),
    Column("state", Text, nullable=False, server_default=text("'outstanding'")),
    Index("uq_vendor_item", "assessment_id", "item", unique=True),
    Index("ix_vendor_item_assessment", "assessment_id", "state"),
)

# Something a scanner found that might be a model.
#
# **A candidate is not a model, and registering everything a scanner finds is
# how an inventory becomes noise.** The whole value of a discovery programme is
# in the triage, and the failure mode is not missing things — it is raising the
# same spreadsheet every sweep because nobody recorded that it was looked at and
# dismissed. So a candidate carries a decision, and a dismissed one stays
# dismissed against its own fingerprint.
#
# `fingerprint` is what makes a sweep idempotent: the same artifact found again
# A matter raised by a supervisor, and the two dates that are not the same date.
#
# Every finding in this register hangs off ONE model, and a supervisory matter
# routinely does not: a thematic MRA about model documentation reaches forty
# models at once. So a matter is its own object and the findings under it are
# derived from its scope — which also means its status is derived, and a firm
# cannot mark a matter closed while a finding under it is open. Telling a
# supervisor something is done when it is not is the specific failure this
# shape prevents.
#
# `committed_at` is the date the FIRM GAVE THE SUPERVISOR. It is not the
# internal remediation date, which comes from severity like every other
# finding's. Conflating them is how a firm discovers on the day that its
# internal plan ran past its regulatory commitment, so both are held and the
# gap between them is computed.
SUPERVISORY_MATTER = Table(
    "supervisory_matter", METADATA,
    Column("id", Text, primary_key=True),
    Column("reference", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("supervisor", Text, nullable=False),
    Column("examination", Text, nullable=False, server_default=text("''")),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    Column("severity", Text, nullable=False, server_default=text("'High'")),
    # Which models it reaches. A thematic matter names many, and the scope is
    # recorded rather than left to whoever raised the findings.
    Column("scope", Text, nullable=False, server_default=text("'[]'")),
    Column("owner", Text, nullable=False),
    Column("raised_at", Double, nullable=False),
    Column("committed_at", Double),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("closed_at", Double),
    Column("closure_note", Text, nullable=False, server_default=text("''")),
    Column("closed_by", Text),
    Index("uq_supervisory_reference", "reference", unique=True),
)


# What one validator can take on, declared. Workload is derived; capacity
# cannot be — a platform that guessed at it would produce a forecast nobody
# could dispute, which is worse than no forecast.
VALIDATOR_CAPACITY = Table(
    "validator_capacity", METADATA,
    Column("id", Text, primary_key=True),
    Column("validator", Text, nullable=False),
    Column("episodes_per_quarter", Double, nullable=False),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("declared_by", Text, nullable=False),
    Column("declared_at", Double, nullable=False),
    Index("uq_validator_capacity", "validator", unique=True),
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


# A cause, named once, with the findings it produced hanging off it.
#
# **M-8** was answered honestly and at the wrong layer: suppression at the last
# hop, one digest per person per run. That damped the storm where it REACHED A
# PERSON rather than where it was generated, and left the findings as twelve
# independent facts about twelve models — so the ageing report counts twelve
# overdue items and the board pack shows twelve open findings in one domain,
# which reads as twelve problems.
#
# This table is the cause. It does NOT merge anything: the findings keep their
# own owners, models and due dates, and `finding.root_id` points here. A model
# whose feature stopped landing has a real problem whatever caused it, and
# dissolving twelve findings into one would leave eleven models with a live
# defect and nothing in their own record saying so.
#
# `status` reaching `addressed` closes no finding, and the service says so in
# the answer. A root that closed its children would be one act discharging
# obligations several different people owe.
FINDING_ROOT = Table(
    "finding_root", METADATA,
    Column("id", Text, primary_key=True),
    Column("title", Text, nullable=False),
    # A closed list, because the estate view counts by it and free text is how
    # a taxonomy becomes forty spellings of one word.
    Column("kind", Text, nullable=False),
    Column("detail", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'open'")),
    Column("opened_by", Text, nullable=False),
    Column("opened_at", Double, nullable=False),
    Column("addressed_at", Double),
    Column("addressed_by", Text, nullable=False, server_default=text("''")),
    Column("addressed_note", Text, nullable=False, server_default=text("''")),
    Index("ix_finding_root_open", "status", "kind"),
)
