"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A matter that stops things being deleted.

**This is the one control in the platform that overrides the platform's own
deletion**, and everything about it follows from that.

`core/execution/inference.py` deletes when a retention period ends, and it is
right to: its content is somebody else's personal data, and a period enforced by
a column somebody could select around is not a period. A legal hold has to be
able to stop it — and a hold a retention job can race is not a hold, so the check
happens inside the deletion rather than beside it.

**A legal hold has no end date, and that is correct.** This inverts the rule
every other bounded thing here follows: a waiver with no end date reaches its
fourth year, a conditional approval with none is an unconditional approval that
has not noticed, an overlay with none is permanent. A hold ends when the *matter*
ends, and when the matter ends is not knowable when the hold is placed. Putting a
date on it would be guessing at a litigation timetable and calling the guess a
control. What replaces the deadline is a **named owner and a stated matter**: a
hold nobody owns is one nobody will lift, and one with no matter recorded is one
nobody can tell has ended.

**Estate-wide is a real scope and a blunt one.** A regulator's document request
does not arrive scoped to the models somebody would have chosen, so the widest
scope is available — and reported as widest, because a hold over everything is a
decision with a cost and should read like one.

**Lifting is the act that needs the ceremony, not placing.** Placing a hold keeps
more than necessary, which is recoverable. Lifting one lets deletion resume on
material somebody may be about to ask for, which is not. So placing takes a
matter and an owner; lifting takes a reason, and the hold is never deleted —
what was held, and when, is the answer to *why is this still here* and to *why
is this not*.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.retention.common import RetentionError

logger = get_logger(__name__)

#: What a hold can be scoped to. `estate` is deliberately available: a document
#: request does not arrive scoped to the models you would have chosen.
SCOPES: Dict[str, str] = {
    "estate": "everything this register holds. Blunt, and sometimes exactly "
              "right — a regulator's request does not arrive scoped to the "
              "models somebody would have chosen",
    "model": "one model and everything recorded about it",
    "legal_entity": "every model used in one entity",
}


class LegalHolds:
    """Places, lifts and answers holds. Nothing is deleted while one applies."""

    def __init__(self, repo, evidence, registry=None):
        self.repo, self.evidence, self.registry = repo, evidence, registry

    # --------------------------------------------------------------- place
    def place(self, *, matter: str, owner: str, scope_kind: str = "estate",
              scope_id: Optional[str] = None,
              classes: Optional[Sequence[str]] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Stop things being deleted, for a stated matter."""
        if scope_kind not in SCOPES:
            raise RetentionError(
                "unknown_scope", f"'{scope_kind}' is not a hold scope",
                "one of " + ", ".join(f"{k} ({v})" for k, v in SCOPES.items()))
        if not (matter or "").strip():
            raise RetentionError(
                "matter_required",
                "a legal hold with no matter recorded is one nobody can tell "
                "has ended — and since a hold has no end date, that is the "
                "only thing that will ever end it",
                "name the matter: the case, the request, the investigation")
        if not (owner or "").strip():
            raise RetentionError(
                "owner_required",
                "a hold nobody owns is a hold nobody will lift",
                "name the person answerable for it")
        if scope_kind != "estate" and not (scope_id or "").strip():
            raise RetentionError(
                "scope_required",
                f"a {scope_kind} hold must say which {scope_kind}",
                "give the identifier, or place it over the estate — which is "
                "blunt and sometimes exactly right")

        rows = self.repo.many()
        row = {
            "reference": f"HOLD-{len(rows) + 1:04d}", "matter": matter.strip(),
            "scope_kind": scope_kind, "scope_id": (scope_id or "").strip() or None,
            "classes": sorted(set(classes or ())), "owner": owner.strip(),
            "placed_by": actor, "placed_at": time.time(), "state": "active",
            "lifted_at": None, "lifted_by": None, "lift_reason": "",
        }
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append(
                "legal_hold_placed", "hold", stored["id"],
                {"reference": row["reference"], "matter": matter,
                 "scope_kind": scope_kind, "scope_id": row["scope_id"],
                 "classes": row["classes"], "owner": owner}, actor=actor)
        logger.warning("legal hold %s placed over %s%s by %s: %s",
                       row["reference"], scope_kind,
                       f" {row['scope_id']}" if row["scope_id"] else "",
                       actor, matter)
        return stored

    # ---------------------------------------------------------------- lift
    def lift(self, reference: str, reason: str,
             actor: str = "system") -> Dict[str, Any]:
        """Let deletion resume. The act that needs the ceremony.

        Placing a hold keeps more than necessary, which is recoverable. Lifting
        one lets deletion resume on material somebody may be about to ask for,
        which is not. The hold is never deleted: what was held, and when, is the
        answer both to *why is this still here* and to *why is this not*.
        """
        row = self.require(reference)
        if row["state"] != "active":
            raise RetentionError("not_active", f"{reference} is {row['state']}",
                                 "a hold is lifted once")
        if not (reason or "").strip():
            raise RetentionError(
                "reason_required",
                "lifting a hold with no reason resumes deletion on material "
                "somebody may be about to ask for, and records nothing about "
                "why that was safe",
                "say what ended the matter")
        with self.evidence.recording():
            self.repo.set({"state": "lifted", "lifted_at": time.time(),
                           "lifted_by": actor,
                           "lift_reason": reason.strip()}, id=row["id"])
            self.evidence.append(
                "legal_hold_lifted", "hold", row["id"],
                {"reference": reference, "reason": reason}, actor=actor)
        logger.warning("legal hold %s lifted by %s: %s", reference, actor,
                       reason)
        return self.require(reference)

    # --------------------------------------------------------------- answer
    def applies(self, *, artifact_class: str = "",
                model_id: Optional[str] = None,
                legal_entity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Every active hold covering this thing.

        Called from inside a deletion rather than beside it: a hold a retention
        job can race is not a hold.
        """
        found = []
        for row in self.repo.many(state="active"):
            classes = row.get("classes") or []
            if classes and artifact_class and artifact_class not in classes:
                continue
            kind, scope = row["scope_kind"], row.get("scope_id")
            if kind == "estate":
                found.append(row)
            elif kind == "model" and model_id and scope == model_id:
                found.append(row)
            elif (kind == "legal_entity" and legal_entity
                  and scope == legal_entity):
                found.append(row)
        return found

    def held(self, **where: Any) -> bool:
        """Whether anything is holding this. The question a deleter asks."""
        return bool(self.applies(**where))

    # ------------------------------------------------------------------ read
    def require(self, reference: str) -> Dict[str, Any]:
        row = self.repo.one(reference=reference)
        if not row:
            raise RetentionError("no_hold", f"no legal hold '{reference}'",
                                 "references look like HOLD-0001")
        return row

    def active(self) -> List[Dict[str, Any]]:
        return self.repo.many(state="active")

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every hold, and how long each has been in force."""
        moment = now if now is not None else time.time()
        rows = []
        for row in self.repo.many():
            rows.append({
                **row,
                "days_in_force": round(
                    ((row.get("lifted_at") or moment) - row["placed_at"])
                    / 86400.0, 1),
            })
        rows.sort(key=lambda r: (r["state"] != "active", -r["days_in_force"]))
        active = [r for r in rows if r["state"] == "active"]
        estate = [r for r in active if r["scope_kind"] == "estate"]
        return {
            "holds": rows, "count": len(rows), "active": len(active),
            "estate_wide": len(estate),
            "scopes": SCOPES,
            "detail": (
                f"{len(active)} hold(s) in force"
                + (f", {len(estate)} of them over the whole estate — blunt, "
                   f"and sometimes exactly right, but a hold over everything "
                   f"is a decision with a cost and should read like one"
                   if estate else "")
                + ". A hold has no end date, which inverts the rule every "
                  "other bounded thing here follows: it ends when the matter "
                  "ends, and when that is cannot be known when it is placed. "
                  "Putting a date on it would be guessing at a litigation "
                  "timetable and calling the guess a control"
                if active else
                "nothing is under legal hold, so every retention period below "
                "applies as written"),
        }
