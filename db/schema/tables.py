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

**This file no longer declares the tables.** It declares where they are and
re-exports every one, so `from db.schema.tables import MODEL` still works and
nothing else in the codebase had to move. The split is by subject — registry,
features, execution, assurance, platform — and it happened at the moment the
size discipline said there was still a seam to split on, which is the only
moment splitting a schema is cheap. A file of seventy-two tables has no seam
anybody can find under pressure.
"""
from __future__ import annotations

from db.schema.metadata import METADATA
from db.schema.registry import (  # noqa: F401
    ALIAS,
    ALIAS_HISTORY,
    AMENDMENT,
    ATTESTATION,
    ATTESTATION_SIGNATURE,
    BASELINE_IMPORT,
    COMPLIANCE_DEBT,
    CONTROL_WAIVER,
    DISCOVERY_CANDIDATE,
    ELICITATION,
    ELICITATION_RESPONSE,
    MODEL,
    MODEL_ASSUMPTION,
    MODEL_EDGE,
    MODEL_LIMITATION,
    MODEL_USE,
    MODEL_VERSION,
    REGULATORY_APPROVAL,
    RISK_ASSESSMENT,
    VERSION_APPROVAL,
    VERSION_APPROVAL_SIGNATURE)
from db.schema.features import (
    DATASET_SNAPSHOT,
    DERIVED_FEATURE,
    FEATURE,
    FEATURESET,
    FEATURESET_VERSION,
    FEATURE_CONTRACT,
    FEATURE_SOURCE,
    FEATURE_VIEW,
    FEATURE_VIEW_VERSION,
    PARAMETER_SET)
from db.schema.execution import (  # noqa: F401
    IDEMPOTENCY,
    INFERENCE,
    PARALLEL_OBSERVATION,
    PARALLEL_RUN,
    RETRAIN_POLICY,
    RUN,
    SERVING_ATTESTATION,
    TELEMETRY_BATCH,
    WARRANT,
    WARRANT_INVOCATION,
    WARRANT_PROFILE)
from db.schema.assurance import (  # noqa: F401
    APPROVAL_CONDITION,
    BREACH,
    FINDING,
    FINDING_ACTION,
    MONITOR,
    MONITORING_PLAN,
    OBSERVATION,
    OVERLAY,
    OVERLAY_MEASUREMENT,
    SUPERVISORY_MATTER,
    TEST_RESULT,
    VALIDATION,
    VALIDATOR_CAPACITY,
    VENDOR_ASSESSMENT,
    VENDOR_ITEM)
from db.schema.platform import (  # noqa: F401
    AI_CAPABILITY,
    AI_GENERATION,
    AI_SPEND,
    API_KEY,
    CAMPAIGN,
    CAMPAIGN_ITEM,
    ATTACHMENT,
    BOARD_PACK,
    BREAK_GLASS,
    DOCUMENT,
    DOCUMENT_COMMENT,
    EVENT_SUBSCRIPTION,
    EVIDENCE_CHECKPOINT,
    EVIDENCE_NODE,
    EXPORT_SHARE,
    EXPORT_SHARE_READ,
    INTAKE_PROPOSAL,
    LEGAL_HOLD,
    NOTIFICATION,
    POLICY_RULE,
    PRINCIPAL,
    RISK_APPETITE,
    ROLE,
    SAVED_VIEW,
    SCHEDULED_RUN)

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
    "DOCUMENT_COMMENT",
    "ELICITATION",
    "ELICITATION_RESPONSE",
    "EVIDENCE_CHECKPOINT",
    "EVIDENCE_NODE",
    "EXPORT_SHARE",
    "EXPORT_SHARE_READ",
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
    "RETRAIN_POLICY",
    "RISK_APPETITE",
    "RISK_ASSESSMENT",
    "ROLE",
    "RUN",
    "SAVED_VIEW",
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

