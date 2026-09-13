"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What happens to the other thirty-seven tables when a model is deleted.

## The defect that produced this module

`ReferenceIndex._to_model` decides whether a model may be deleted. It queries
**thirty-three** tables. Thirty-eight carry a `model_id`.

The module's own docstring said *"nineteen tables carry a `model_id`"*, which
was true when it was written. The five it misses did not announce themselves,
because the check's failure mode is silence: a model with an **unfinished
validation** or a **version approval still being collected** reported
`deletable: true` with zero references, and the deletion succeeded.
`model_assumption` and `model_limitation` were orphaned outright.

Worse than the gap: the test guarding against exactly this asserted that each
table's name appeared *somewhere in `index.py`*, and every one of the five is
mentioned — in prose, in a `why` clause, as a `Reference` kind. The guard
passed for a reason other than its name, which is the most expensive kind of
test to own, because it turns an absent control into a reported one.

## Why a declaration rather than a query

The obvious repair is to add the missing twenty-five queries. That fixes the
instance and leaves the mechanism: the thirty-ninth table arrives, nobody
remembers this file, and the check is stale again with nothing to notice.

So each table gets a **declared disposition**, and
`tests/test_cascade_dispositions.py` walks the schema and fails if any table
carrying a `model_id` is missing from `CASCADE`. Adding a table now forces the
decision instead of defaulting to *silently unchecked*, which is the only
default that is never right.

## The three dispositions

**BLOCKS** — the row would be left broken, so the deletion is refused while it
is live. `live` is the SQL predicate for *still live*; `None` means always
blocking.

**GOES** — the row is part of the model's record and is destroyed with it. Not
a judgement about importance: a parameter set is meaningless without the model
whose parameter space it names.

**STAYS** — the row records something that happened, and reads correctly
afterwards *because the tombstone makes the URN resolve*. This disposition is
only honest with a tombstone behind it. Without one these rows point at
nothing, which is how the register ends up holding a closed finding against a
model no reader can identify.

## Live-ness is read from timestamps, not from status strings

Where a table has a `closed_at`, `completed_at` or `withdrawn_at`, the
predicate uses it. Status vocabularies differ per module and drift; a NULL
closure timestamp means the same thing everywhere, and getting a status string
wrong here fails **open** — the check silently stops blocking. Predicates that
cannot be got subtly wrong are worth more than expressive ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# The state names are IMPORTED, not spelled again here.
#
# `export_share.status` was written as `'active'` in the first draft of this
# file. Its vocabulary is open/expired/revoked/exhausted, so the predicate
# matched nothing and the check failed **open** — a live external share of a
# deleted model's record, and no refusal at all. That is this module's own
# failure mode arriving inside the module built to end it, which is reason
# enough to stop retyping strings that are defined somewhere else.
from core.log import get_logger
from core.export.sharing import OPEN as SHARE_OPEN
from core.lifecycle.campaigns import OUTSTANDING as ITEM_OUTSTANDING
from core.parameters.elicitation import OPEN as ELICITATION_OPEN
from core.parameters.retraining import ACTIVE as RETRAIN_ACTIVE

logger = get_logger(__name__)

BLOCKS, GOES, STAYS = "blocks", "goes", "stays"


@dataclass(frozen=True)
class Disposition:
    """What one table does when the model it references is deleted."""
    table: str
    kind: str            #: BLOCKS, GOES or STAYS
    label: str           #: how to name a row of it to a person
    why: str             #: what the row IS, in one clause
    live: Optional[str] = None   #: SQL predicate for "still live"; BLOCKS only

    def blocking_sql(self) -> str:
        where = "model_id = :m" + (f" AND ({self.live})" if self.live else "")
        return f"SELECT id FROM {self.table} WHERE {where}"


#: Every table carrying a `model_id`, and what happens to it.
CASCADE: Tuple[Disposition, ...] = (
    # ---------------------------------------------------------- blocking
    Disposition("model_version", BLOCKS, "version",
                "an immutable version of this model"),
    Disposition("alias", BLOCKS, "alias",
                "a name consumers bind to instead of a semver"),
    Disposition("warrant", BLOCKS, "warrant",
                "a live grant to run this model",
                "revoked = 0"),
    Disposition("parameter_set", BLOCKS, "parameter set",
                "an approved point of P this model runs at",
                "state = 'approved'"),
    Disposition("finding", BLOCKS, "finding",
                "an open finding against this model",
                "status NOT IN ('closed', 'withdrawn')"),
    Disposition("monitor", BLOCKS, "monitor",
                "an active monitor on this model",
                "status = 'active'"),
    Disposition("model_use", BLOCKS, "declared use",
                "a use this model is currently declared for",
                "status = 'active'"),
    Disposition("monitoring_plan", BLOCKS, "monitoring plan",
                "a plan whose monitors were never inherited",
                "inherited_at IS NULL"),
    Disposition("regulatory_approval", BLOCKS, "regulatory approval",
                "an approval a supervisor granted for this model"),
    # The two that were never asked, and are live commitments.
    #
    # `attestation` and the rest below ARE reached by hand in `index.py`; they
    # are declared here because the declaration has to be complete to be
    # checkable, and because `index.py` defers to its own query where both
    # cover a table.
    Disposition("attestation", BLOCKS, "attestation",
                "an attestation round in flight over this model",
                "completed_at IS NULL"),
    Disposition("campaign_item", BLOCKS, "campaign item",
                "an unanswered item in a live campaign — a campaign completes "
                "when every item is answered, and an item naming a deleted "
                "model can never be",
                f"state = '{ITEM_OUTSTANDING}'"),
    Disposition("validation", BLOCKS, "validation",
                "a validation that has not reported",
                "completed_at IS NULL"),
    Disposition("version_approval", BLOCKS, "version approval",
                "an approval still being collected",
                "completed_at IS NULL"),
    Disposition("approval_condition", BLOCKS, "approval condition",
                "a condition attached to an approval and not yet discharged",
                "state = 'active'"),
    Disposition("control_waiver", BLOCKS, "control waiver",
                "a live waiver — deleting the model would retire the "
                "compensating control with nothing recording that it lapsed",
                "closed_at IS NULL"),
    Disposition("overlay", BLOCKS, "overlay",
                "a live overlay adjusting this model's output",
                "closed_at IS NULL"),
    Disposition("breach", BLOCKS, "breach",
                "an open breach against this model",
                "closed_at IS NULL"),
    Disposition("amendment", BLOCKS, "amendment",
                "an open amendment to this model's attested record",
                "closed_at IS NULL"),
    Disposition("compliance_debt", BLOCKS, "compliance debt",
                "dated debt that has not closed or expired",
                "closed_at IS NULL"),
    Disposition("parallel_run", BLOCKS, "parallel run",
                "a parallel run still going",
                "closed_at IS NULL"),
    Disposition("run", BLOCKS, "run",
                "a run that has not finished",
                "closed_at IS NULL"),
    Disposition("elicitation", BLOCKS, "elicitation",
                "an expert elicitation still open",
                f"state = '{ELICITATION_OPEN}'"),
    Disposition("retrain_policy", BLOCKS, "retrain policy",
                "a live retraining policy",
                f"status = '{RETRAIN_ACTIVE}'"),
    Disposition("export_share", BLOCKS, "export share",
                "a share of this model's record that is still readable by "
                "somebody outside — deleting the model does not withdraw it",
                f"status = '{SHARE_OPEN}'"),

    # -------------------------------------------------------------- goes
    # Meaningless without the model. Not unimportant — dependent.
    Disposition("alias_history", GOES, "alias movement",
                "where an alias of this model used to point"),
    Disposition("model_assumption", GOES, "assumption",
                "an assumption this model was built on"),
    Disposition("model_limitation", GOES, "limitation",
                "a limitation declared for this model"),
    Disposition("risk_assessment", GOES, "risk assessment",
                "the assessment that produced this model's tier"),
    Disposition("tiering_fact_source", GOES, "tiering fact",
                "where a fact behind the tier came from"),
    Disposition("finding_action", GOES, "finding action",
                "an action on a finding against this model"),
    Disposition("estate_cost", GOES, "cost line",
                "an attributed cost for this model"),
    Disposition("attachment", GOES, "attachment",
                "a file attached to this model's record"),

    # ------------------------------------------------------------- stays
    # Reads correctly afterwards ONLY because the tombstone resolves the URN.
    Disposition("inference", STAYS, "inference record",
                "a decision this model actually made, and the record of who "
                "relied on it — the thing a deletion must not be able to erase"),
    Disposition("warrant_invocation", STAYS, "invocation",
                "a record of this model being run, and by whom"),
    Disposition("document", STAYS, "document",
                "a compiled document that cited this model when it was cut"),
    Disposition("model_decommission", STAYS, "decommissioning record",
                "the record that this model was withdrawn from service, and "
                "on what terms — a completed act, not one in flight"),
    Disposition("vendor_assessment", STAYS, "vendor assessment",
                "an assessment of the third party that supplied it, which "
                "outlives any one model bought from them"),
    Disposition("model_tombstone", STAYS, "tombstone",
                "the marker for this deletion itself"),
)

BY_TABLE: Dict[str, Disposition] = {d.table: d for d in CASCADE}


class Cascade:
    """Runs the declared disposition over one model's dependent rows."""

    def __init__(self, db):
        self.db = db

    # ----------------------------------------------------------- blocking
    def blocking(self, model_id: str) -> List[Dict[str, Any]]:
        """Live rows that would be left broken. Empty means safe to delete."""
        found: List[Dict[str, Any]] = []
        for d in CASCADE:
            if d.kind != BLOCKS:
                continue
            rows = self.db.query(d.blocking_sql(), {"m": model_id})
            if rows:
                found.append({"table": d.table, "label": d.label,
                              "why": d.why, "count": len(rows)})
        return found

    # ------------------------------------------------------------ destroy
    def destroy(self, model_id: str) -> Dict[str, int]:
        """Remove the dependent rows, and count what went.

        The count is the tombstone's `destroyed` field, and it is the only
        record of scale that survives — afterwards there is nothing left to
        count. An examiner asking how large a deletion was has no other source.

        Blocking rows are not touched. The caller refuses before reaching here,
        and a cascade that could destroy a blocking row would make that refusal
        decorative.
        """
        counts: Dict[str, int] = {}
        for d in CASCADE:
            if d.kind != GOES:
                continue
            rows = self.db.query(
                f"SELECT id FROM {d.table} WHERE model_id = :m", {"m": model_id})
            if not rows:
                continue
            self.db.execute(
                f"DELETE FROM {d.table} WHERE model_id = :m", {"m": model_id})
            counts[d.table] = len(rows)
        # Counted but kept, so the tombstone says what remains as well as what
        # went. "Nothing was destroyed" and "nothing was there" differ.
        for d in CASCADE:
            if d.kind != STAYS or d.table == "model_tombstone":
                continue
            rows = self.db.query(
                f"SELECT id FROM {d.table} WHERE model_id = :m", {"m": model_id})
            if rows:
                counts[f"{d.table} (kept)"] = len(rows)
        if counts:
            logger.warning("cascade over model %s: %s", model_id, counts)
        return counts

    # -------------------------------------------------------------- audit
    @staticmethod
    def describe() -> List[Dict[str, str]]:
        """The declaration, for the interface and for an examiner."""
        return [{"table": d.table, "disposition": d.kind, "label": d.label,
                 "why": d.why, "live": d.live or ""} for d in CASCADE]
