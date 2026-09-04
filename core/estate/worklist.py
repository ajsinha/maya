"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What needs doing, and who can do it.

The platform computes a great deal — outstanding attestation signatures, monitors
past their cadence, overlays whose window has elapsed, debt approaching its
expiry, documents that have gone stale — and until now surfaced almost none of
it. A control nobody is told about is a control that operates when somebody
happens to look.

**Work is computed, not assigned.** There is no task table. Every item here is
derived from the same state the rest of the platform reads, which means it cannot
go stale, cannot disagree with the register, and cannot accumulate orphans when
something is completed by another route. A task table would be a second source of
truth about what is outstanding, and it would be wrong within a week.

Items are filtered by what a principal can actually act on — their permissions
and their scope — because a list of work somebody cannot do is a list they learn
to ignore.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

# How close to a deadline something has to be before it is "due soon" rather
# than simply scheduled.
HORIZON_DAYS = 30.0


@dataclass(frozen=True)
class Item:
    """One piece of outstanding work."""
    kind: str
    urn: str
    title: str
    detail: str
    permission: str
    urgency: str            # overdue | due | open
    due_at: Optional[float] = None
    role: Optional[str] = None
    href: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "urn": self.urn, "title": self.title,
                "detail": self.detail, "permission": self.permission,
                "urgency": self.urgency, "due_at": self.due_at, "role": self.role,
                "href": self.href or f"/model/{self.urn.rsplit('/', 1)[-1]}"}


def _urgency(due_at: Optional[float], now: float) -> str:
    if due_at is None:
        return "open"
    if due_at < now:
        return "overdue"
    return "due" if due_at - now < HORIZON_DAYS * DAY else "open"


ORDER = {"overdue": 0, "due": 1, "open": 2}


class WorkList:
    """Derives the outstanding work across the estate."""

    def __init__(self, registry, lifecycle=None, findings=None, monitoring=None,
                 overlays=None, documents=None, debts=None, validation=None):
        self.registry, self.lifecycle = registry, lifecycle
        self.findings, self.monitoring = findings, monitoring
        self.overlays, self.documents = overlays, documents
        self.debts, self.validation = debts, validation

    # ------------------------------------------------------------------ build
    def for_model(self, model: Dict[str, Any],
                  now: Optional[float] = None) -> List[Item]:
        moment = now if now is not None else time.time()
        urn = model["urn"]
        items: List[Item] = []
        for source in (self._attestation, self._approval, self._findings,
                       self._monitors, self._overlays, self._debt, self._documents):
            items.extend(self._safely(source, model, urn, moment))
        return items

    @staticmethod
    def _safely(source: Callable, model: Dict[str, Any], urn: str,
                moment: float) -> List[Item]:
        """A subsystem that is absent or refusing must not blank the whole list."""
        try:
            return list(source(model, urn, moment))
        except Exception as exc:                       # noqa: BLE001 — reported
            logger.warning("worklist skipped %s for %s: %s",
                           getattr(source, "__name__", "?"), urn, exc)
            return []

    # ------------------------------------------------------------- the sources
    def _attestation(self, model, urn, now) -> List[Item]:
        """Outstanding signatures. The gap this whole module exists to close."""
        if not self.lifecycle:
            return []
        state = self.lifecycle.state(urn)
        items = []
        attestation = state.get("open_attestation")
        if attestation:
            for role in attestation["outstanding_roles"]:
                items.append(Item(
                    "attestation", urn, f"Attestation outstanding: {role}",
                    f"{model['name']} is approved and waiting for the "
                    f"{role.replace('_', ' ')} signature; it is not in force until "
                    "every required role has signed.",
                    "model:attest", "due", role=role))
        expires = state.get("attestation_expires_at")
        if state.get("attestation_expired"):
            items.append(Item(
                "attestation_renewal", urn, "Attestation has lapsed",
                f"{model['name']} was attested but its attestation has passed its "
                "validity period and must be renewed.",
                "model:attest", "overdue", due_at=expires))
        elif expires and expires - now < HORIZON_DAYS * DAY:
            items.append(Item(
                "attestation_renewal", urn, "Attestation renewal due",
                f"{model['name']}'s attestation expires within "
                f"{HORIZON_DAYS:.0f} days.", "model:attest", "due", due_at=expires))
        return items

    def _approval(self, model, urn, now) -> List[Item]:
        if model["status"] == "submitted":
            return [Item("approval", urn, "Submitted for approval",
                         f"{model['name']} has been put forward and is waiting on "
                         "the second line.", "model:approve", "due")]
        if model["status"] == "draft" and not self.registry.versions(urn):
            return [Item("draft", urn, "Draft with no version",
                         f"{model['name']} cannot be submitted until it has at "
                         "least one version.", "version:create", "open")]
        return []

    def _findings(self, model, urn, now) -> List[Item]:
        if not self.findings:
            return []
        items = []
        for f in self.findings.open_for(model["id"]):
            urgency = _urgency(f["due_at"], now)
            if urgency == "open" and not f["blocking"]:
                continue                      # not yet worth anyone's attention
            items.append(Item(
                "finding", urn,
                f"{f['severity']} finding{' (blocking)' if f['blocking'] else ''}",
                f"{f['title']} — owned by {f['owner']}"
                + ("; this refuses warrant resolution and alias promotion"
                   if f["blocking"] else ""),
                "finding:close", "overdue" if urgency == "overdue" else "due",
                due_at=f["due_at"]))
        return items

    def _monitors(self, model, urn, now) -> List[Item]:
        if not self.monitoring:
            return []
        due = self.monitoring.registry.due(model["id"], now)
        return [Item("monitor", urn, f"Monitor due: {m['name']}",
                     f"{m['name']} has not been evaluated within its "
                     f"{m['cadence_days']:g}-day cadence.",
                     "monitor:evaluate", "due") for m in due]

    def _overlays(self, model, urn, now) -> List[Item]:
        if not self.overlays:
            return []
        items = []
        for row in self.overlays.status(model["id"], now).get("detail_rows", []):
            if row["status"] != "active":
                continue
            assessment = row["assessment"]
            if assessment["expired"]:
                items.append(Item(
                    "overlay", urn, f"Overlay window elapsed: {row['reference']}",
                    f"{row['name']} has passed its approved window and must be "
                    "renewed, absorbed into the model, or withdrawn.",
                    "overlay:approve", "overdue", due_at=row["expires_at"]))
            elif not assessment["materiality"]["measured"]:
                items.append(Item(
                    "overlay", urn, f"Overlay unmeasured: {row['reference']}",
                    f"{row['name']} has no magnitude recorded, so it cannot be "
                    "renewed and its size cannot be challenged.",
                    "overlay:measure", "due"))
            elif assessment["escalate"]:
                items.append(Item(
                    "overlay", urn, f"Overlay is persistent: {row['reference']}",
                    f"{row['name']} has outlived its renewal limit; either the "
                    "model should be corrected or the adjustment built into it.",
                    "overlay:approve", "overdue"))
        return items

    def _debt(self, model, urn, now) -> List[Item]:
        if not self.debts:
            return []
        items = []
        for d in self.debts.open_for(model["id"]):
            urgency = _urgency(d["expires_at"], now)
            if urgency == "open" and d["plan"]:
                continue                      # dated and not yet close
            items.append(Item(
                "debt", urn,
                f"Baseline debt{' unplanned' if not d['plan'] else ''}: {d['gap_key']}",
                d["description"] + ("; no dated plan to close it has been recorded"
                                    if not d["plan"] else ""),
                "baseline:plan", "overdue" if urgency == "overdue" else "due",
                due_at=d["expires_at"]))
        return items

    def _documents(self, model, urn, now) -> List[Item]:
        if not self.documents:
            return []
        items = []
        for doc in self.documents.for_model(model["id"]):
            staleness = self.documents.staleness(doc["id"])
            if staleness["stale"]:
                items.append(Item(
                    "document", urn, f"Document is stale: {doc['kind']}",
                    f"{staleness['events_since']} governance event(s) recorded "
                    "since it was compiled, so it no longer describes the model.",
                    "document:compile", "due",
                    href=f"/document/{doc['id']}"))
        return items

    # -------------------------------------------------------------- the estate
    def across(self, models: Sequence[Dict[str, Any]],
               now: Optional[float] = None) -> List[Item]:
        moment = now if now is not None else time.time()
        items: List[Item] = []
        for model in models:
            items.extend(self.for_model(model, moment))
        return sorted(items, key=lambda i: (ORDER[i.urgency], i.due_at or 0, i.urn))

    def mine(self, principal: Dict[str, Any], authz,
             models: Sequence[Dict[str, Any]],
             now: Optional[float] = None) -> Dict[str, Any]:
        """The work this principal can actually do.

        Filtered by permission and by scope, because a list of work somebody
        cannot act on is a list they learn to ignore — and ignoring the list is
        how the control stops operating.
        """
        visible = authz.visible(principal, models)
        everything = self.across(visible, now)
        mine = [i for i in everything
                if authz.permits(principal, i.permission)
                and (i.role is None or i.role in (principal.get("roles") or []))]
        return {
            "principal": principal.get("username"),
            "items": [i.as_dict() for i in mine],
            "overdue": sum(1 for i in mine if i.urgency == "overdue"),
            "due": sum(1 for i in mine if i.urgency == "due"),
            "others": len(everything) - len(mine),
            "detail": (f"{len(mine)} item(s) you can act on"
                       + (f"; {len(everything) - len(mine)} more are outstanding "
                          "for other roles" if len(everything) > len(mine) else "")
                       if mine else "nothing is outstanding for you"),
        }
