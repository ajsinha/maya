"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a deleted model leaves behind, and why the hole has to have a shape.

`LifecycleService.delete` was careful about the things that are easy to be
careful about. Administrators only. A reason. A legal hold consulted. Evidence
appended *before* the rows go, so a half-finished removal still says who
intended it. Then `models.remove(id=...)` and the record is gone.

What it left is a hole shaped exactly like a model that never existed, and
those two things must never look the same.

## The three failures of a deletion with no marker

**A historical reference resolves to nothing.** Nineteen tables carry a
`model_id`. Blocking references are refused at the route — `refuse_if_referenced`
does that work and does it well — but *historical* ones are deliberately not
grounds to refuse, because a register in which nothing may be deleted because
something once happened is a register that grows without bound. So they stay,
and the thing they name stops resolving. A closed finding about a model
somebody can no longer look up is not a record; it is a puzzle.

**The URN can be taken by something else.** This is the serious one. The URN is
derived from the name. Register a second model with the deleted one's name and
it gets the same URN — and every evidence node, every closed finding, every
amendment naming that URN now reads as though it were about the new model. The
chain still verifies. `verify_chain` re-derives every hash and finds nothing
wrong, because nothing *is* wrong with the chain. It is describing the wrong
model, and no integrity check that operates on hashes can ever see that.

**Nobody can say what the deletion removed.** After the cleanup there is
nothing left to count. An examiner asking how large an act of destruction was
has no source at all, and "we deleted a model" is not an answer.

## What a tombstone is, and what it is not

It is **the row that stays** — identity, the lifecycle state the model was in
when it went, who destroyed it, when, why, and a count per table of what went
with it. It is written inside the same evidence recording as the deletion, so
there is no window in which the model is gone and unmarked.

It is **not a soft delete**. The model row is really removed; it does not
appear in listings, it cannot be transitioned, attested or approved, and the
tombstone carries none of the operational fields that would let it pretend to
be one. The distinction is deliberate: a soft delete leaves a thing that some
queries see and others do not, and the failure mode of that pattern is a record
that is alive in one screen and dead in another.

And it is **not reversible**. A tombstone cannot be lifted into a model again.
Restoring would mean recreating rows whose contents are gone; what it would
actually produce is an empty model wearing a dead one's identity, which is the
confusion this module exists to prevent, arriving through the front door.

## Deletion from `draft` and deletion from `retired` are different acts

Only `status` records which one happened. Deleting a draft nobody ever used is
housekeeping. Deleting a retired model that made decisions for six years is an
act with a regulatory character, and the tombstone is the only place the
difference survives.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.log import get_logger
from core.retention.common import RetentionError

logger = get_logger(__name__)

#: How long the bytes stay after the row goes.
#:
#: Compaction is the irreversible half — the row is already gone, but the
#: artifacts, the attachments and the Delta directories are still on disk and
#: still readable. Reclaiming them the same second as the deletion means a
#: mistaken deletion and an unrecoverable one are the same event, and the
#: person who realises at 4pm that they deleted the wrong model has nothing to
#: go to their backup *about*.
#:
#: Thirty days is not a compliance figure and this module does not pretend it
#: is one. It is a window long enough that somebody notices.
QUARANTINE_DAYS = 30

#: Fields copied off the model onto the marker. Enough to say what it was to
#: somebody holding a reference; not enough to operate on.
CARRIED = ("urn", "name", "model_class", "domain", "owner", "legal_entity",
           "status", "tier")


class Tombstones:
    """Marks a destroyed model so its identity cannot be silently reused."""

    def __init__(self, repo, evidence=None, holds=None):
        self.repo, self.evidence, self.holds = repo, evidence, holds

    # ------------------------------------------------------------------ write
    def mark(self, model: Dict[str, Any], *, reason: str, actor: str,
             destroyed: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Record that this model existed and was destroyed.

        Called by the deleter inside the evidence recording that removes the
        rows, so the marker and the removal succeed or fail together. A
        deletion that committed without one would leave the URN free.
        """
        row = {"model_id": model["id"],
               "deleted_at": time.time(), "deleted_by": actor,
               "reason": reason,
               "registered_at": model.get("created_at"),
               "destroyed": dict(destroyed or {}), "reclaimed": {}}
        for field in CARRIED:
            value = model.get(field)
            row[field] = value if value is not None else (
                None if field == "tier" else "")
        self.repo.add(row)
        logger.warning("tombstone raised over %s (%s), deleted by %s: %s",
                       model["urn"], model.get("status"), actor, reason)
        return row

    # ------------------------------------------------------------------ query
    def of(self, urn: str) -> Optional[Dict[str, Any]]:
        return self.repo.one(urn=urn)

    def by_model_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        """A historical row carries the id, not the urn."""
        return self.repo.one(model_id=model_id)

    def list(self, *, compacted: Optional[bool] = None) -> List[Dict[str, Any]]:
        rows = self.repo.many()
        if compacted is None:
            return rows
        return [r for r in rows
                if bool(r.get("compacted_at")) is bool(compacted)]

    def resolve(self, urn: str) -> Optional[Dict[str, Any]]:
        """What a reference to this URN resolves to now.

        The whole point is that this is not `None`. A screen that finds nothing
        says *no such model*, which is the answer for a name somebody mistyped;
        the true answer is *there was one, and here is what happened to it*.
        """
        stone = self.of(urn)
        if not stone:
            return None
        return {
            "urn": stone["urn"], "name": stone["name"],
            "deleted": True,
            "status_when_deleted": stone["status"],
            "deleted_at": stone["deleted_at"],
            "deleted_by": stone["deleted_by"],
            "reason": stone["reason"],
            "owner": stone.get("owner") or "",
            "storage_reclaimed": bool(stone.get("compacted_at")),
            "detail": (f"{stone['name']} was deleted from "
                       f"{stone['status']} by {stone['deleted_by']}"),
        }

    # ---------------------------------------------------------------- refusal
    def refuse_reuse(self, urn: str) -> None:
        """Refuse to register a model over a destroyed one's identity.

        This is the reason the table exists.

        Without it the sequence is: delete `urn:maya:model:pd-retail`, register
        a new model called the same thing, and six years of evidence about the
        destroyed model is now indistinguishable from evidence about the new
        one. Every hash still checks. The chain is intact and the history is
        wrong, which is a worse failure than a chain that breaks, because a
        broken chain announces itself.

        Refused with no override, and the remediation is to pick another name.
        An identity that a register can hand out twice is not an identity.
        """
        stone = self.of(urn)
        if not stone:
            return
        raise RetentionError(
            "urn_was_deleted",
            f"{urn} belonged to a model deleted on "
            f"{_when(stone['deleted_at'])} by {stone['deleted_by']} "
            f"({stone['reason']}); the identifier is not available again",
            "register under a different name. Evidence naming this URN "
            "describes the destroyed model, and a second model wearing the "
            "same identity would silently inherit its history")


def _when(at: Optional[float]) -> str:
    if not at:
        return "an unrecorded date"
    return time.strftime("%Y-%m-%d", time.gmtime(float(at)))
