"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Controls a model is not meeting, and who said that was acceptable.

Every estate has these. Most keep them in a spreadsheet, which is how a
temporary exception reaches its fourth year and how a supervisor finds out that
the tier 1 model in front of them has not been independently validated since
2023 — a fact that was written down, agreed, and then never looked at again.

Four rules are enforced here rather than trusted to process. They are the
overlay register's four rules pointed at a different object, and that is not
laziness: a waiver and a management adjustment are the same governance animal,
in that both are a temporary departure from what the framework says, and both
fail by quietly becoming permanent.

**Mandatory expiry.** There is no way to record a waiver without an end date and
no way to set one beyond the configured maximum. *No indefinite exceptions* is
the requirement's own phrase and it is the whole point: an exception with no end
date is not an exception, it is a decision to stop applying a control.

**A compensating control is required.** A waiver saying only *we are not doing
this* records the gap and not the containment. What is being done instead is the
half a reviewer needs, and refusing a waiver without one is the difference
between a register of exceptions and a list of excuses.

**The proposer may not approve.** One person who can both ask for a control to
be relaxed and grant it is not a control.

**Approval scales with the tier.** A tier 1 model's waiver takes two signatures
in two roles; a tier 3 or 4 model's takes one. The requirement asks for "an
approval level scaled to risk", and relaxing a control on the estate's most
material model on one person's say-so is exactly what that phrase is about.

And one rule the overlays taught: **renewal is not free.** Past the limit the
register raises a finding, because a waiver renewed four times is not a
temporary exception, it is the framework the institution actually operates.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.authz.common import same_person
from core.evidence import EvidenceEngine
from core.risk.designations import DESIGNATION_CONTROLS
from core.risk.lattices import CONTROLS
from core.waivers.common import (DAY, DEFAULT_MAX_DAYS, DEFAULT_RENEWAL_LIMIT,
                                 PROPOSED, WaiverError)

#: Every control anything requires — the tiers' and the designations' both.
#:
#: A waiver names one of these and nothing else: a waiver of a control nothing
#: requires is a waiver of nothing, and it would read on a report as though
#: something had been relaxed. And the designation half has to be here, or a
#: bank that cannot yet reconcile its submissions has nowhere to SAY so — which
#: would leave a designation-driven requirement as something people meet on
#: paper, which is the failure the whole register exists to prevent.
WAIVABLE: tuple = tuple(sorted(
    {c for controls in CONTROLS.values() for c in controls}
    | set(DESIGNATION_CONTROLS)))

#: How many signatures, in how many distinct roles, by tier. This is the
#: "approval level scaled to risk" the requirement asks for, and it is a
#: separate table from the version quorum on purpose: relaxing a control and
#: approving mathematics are different acts and an institution may well want
#: them to need different people.
QUORUM_BY_TIER: Dict[int, int] = {1: 2, 2: 2, 3: 1, 4: 1}


class WaiverRegister:
    """Proposes, approves, renews, revokes and expires control waivers."""

    def __init__(self, waivers, evidence: EvidenceEngine, registry,
                 findings=None, max_days: int = DEFAULT_MAX_DAYS,
                 renewal_limit: int = DEFAULT_RENEWAL_LIMIT):
        self.waivers, self.evidence, self.registry = waivers, evidence, registry
        self.findings = findings
        self.max_days, self.renewal_limit = max_days, renewal_limit

    # ------------------------------------------------------------- propose
    def propose(self, urn: str, control: str, rationale: str,
                compensating_control: str, days: float, *,
                model_version_id: Optional[str] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Ask for a control to be relaxed, for a bounded time."""
        model = self.registry.require(urn)
        if control not in WAIVABLE:
            raise WaiverError(
                "unknown_control",
                f"'{control}' is not a control any tier requires, so waiving "
                f"it would relax nothing while reading on a report as though "
                f"it had",
                f"name one of {', '.join(WAIVABLE)}")
        if not (rationale or "").strip():
            raise WaiverError(
                "no_rationale",
                "a waiver with no rationale records that a control is not "
                "being met and not why anybody agreed to that",
                "say what makes this acceptable")
        if not (compensating_control or "").strip():
            raise WaiverError(
                "no_compensating_control",
                "a waiver with nothing compensating records the gap and not "
                "the containment, which is the half a reviewer needs",
                "say what is being done instead — and if the answer is "
                "nothing, this is not a waiver, it is an accepted risk and "
                "belongs in a finding somebody owns")
        if days <= 0:
            raise WaiverError(
                "no_expiry",
                "a waiver must expire. An exception with no end date is not an "
                "exception, it is a decision to stop applying a control",
                f"set a window of up to {self.max_days} days")
        if days > self.max_days:
            raise WaiverError(
                "window_too_long",
                f"{days:g} days exceeds the {self.max_days}-day limit for a "
                f"single waiver. Longer exceptions are not forbidden — they "
                f"are renewed, which is a decision somebody takes again rather "
                f"than one that lapses into permanence",
                f"propose up to {self.max_days} days and renew if it is still "
                f"needed")

        now = time.time()
        existing = self.waivers.many(model_id=model["id"])
        row = {"model_id": model["id"], "model_version_id": model_version_id,
               "reference": f"WVR-{len(existing) + 1:04d}",
               "control": control, "rationale": rationale.strip(),
               "compensating_control": compensating_control.strip(),
               "tier_at_grant": model.get("tier"), "status": PROPOSED,
               "proposed_by": actor, "approved_by": None, "approvals": [],
               "granted_at": None, "expires_at": now + days * DAY,
               "renewals": 0, "finding_id": None, "created_at": now,
               "closed_at": None, "closure_reason": None}
        with self.evidence.recording():
            stored = self.waivers.add(row)
            self.evidence.append(
                "waiver_proposed", "model", model["id"],
                {"reference": row["reference"], "control": control,
                 "days": days, "tier": model.get("tier")}, actor=actor)
        return stored

    # ------------------------------------------------------------- approve
    def approve(self, waiver_id: str, role: str, *,
                actor: str = "system") -> Dict[str, Any]:
        """Sign one. Takes as many signatures, in as many roles, as the tier says.

        The signatures accumulate on the row and the waiver becomes active on
        the last one, so a tier 1 waiver that got one signature is visibly a
        waiver that got one signature — rather than an approved one or an
        absent one, which are the two things a half-signed exception otherwise
        looks like.
        """
        row = self.require(waiver_id)
        if row["status"] != PROPOSED:
            raise WaiverError(
                "not_proposed",
                f"{row['reference']} is '{row['status']}', so there is nothing "
                f"to approve",
                "propose a new waiver, or renew this one if it is active")
        if same_person(row["proposed_by"], actor):
            raise WaiverError(
                "proposer_may_not_approve",
                f"{actor} proposed {row['reference']} and may not also grant "
                f"it. One person who can both ask for a control to be relaxed "
                f"and relax it is not a control",
                "have somebody else approve it")

        approvals = list(row.get("approvals") or [])
        if any(same_person(a.get("actor", ""), actor) for a in approvals):
            raise WaiverError(
                "already_signed",
                f"{actor} has already signed {row['reference']}; a second "
                f"signature from one person is one signature",
                "a different person must sign")
        if any(a.get("role") == role for a in approvals):
            raise WaiverError(
                "role_already_signed",
                f"{role} has already signed {row['reference']}. A quorum in "
                f"two roles means two DIFFERENT roles, or it is one opinion "
                f"held twice",
                "sign under a role that has not signed")

        approvals.append({"actor": actor, "role": role, "at": time.time()})
        needed = self.quorum_for(row.get("tier_at_grant"))
        complete = len(approvals) >= needed
        patch: Dict[str, Any] = {"approvals": approvals}
        if complete:
            patch.update({"status": "active", "approved_by": actor,
                          "granted_at": time.time()})
        with self.evidence.recording():
            self.waivers.set(patch, id=waiver_id)
            self.evidence.append(
                "waiver_approved" if complete else "waiver_signed",
                "model", row["model_id"],
                {"reference": row["reference"], "role": role,
                 "signatures": len(approvals), "needed": needed}, actor=actor)
        return self.require(waiver_id)

    def quorum_for(self, tier: Optional[int]) -> int:
        """How many signatures this tier's waiver takes.

        An untiered model takes the strictest, not the loosest. A model nobody
        has tiered is not a safe model — the same reading the risk lattice
        applies to an unassessed component.
        """
        if tier is None:
            return max(QUORUM_BY_TIER.values())
        return QUORUM_BY_TIER.get(int(tier), 1)

    # -------------------------------------------------------------- renew
    def renew(self, waiver_id: str, days: float, *,
              actor: str = "system") -> Dict[str, Any]:
        """Extend an active waiver, and count that it happened.

        Renewal is deliberately not free. Past the limit this raises a finding,
        because a waiver renewed four times is not a temporary exception — it
        is the framework the institution actually operates, and it should be
        argued for as one.
        """
        row = self.require(waiver_id)
        if row["status"] != "active":
            raise WaiverError(
                "not_active", f"{row['reference']} is '{row['status']}'",
                "only an active waiver can be renewed")
        if days <= 0 or days > self.max_days:
            raise WaiverError(
                "window_too_long",
                f"a renewal runs up to {self.max_days} days",
                f"renew for up to {self.max_days} days")
        renewals = int(row.get("renewals") or 0) + 1
        with self.evidence.recording():
            self.waivers.set({"expires_at": time.time() + days * DAY,
                              "renewals": renewals}, id=waiver_id)
            self.evidence.append("waiver_renewed", "model", row["model_id"],
                                 {"reference": row["reference"],
                                  "renewals": renewals, "days": days},
                                 actor=actor)
            if renewals > self.renewal_limit:
                self._raise_persistent(row, renewals, actor)
        return self.require(waiver_id)

    def _raise_persistent(self, row: Dict[str, Any], renewals: int,
                          actor: str) -> None:
        if self.findings is None:
            return
        finding = self.findings.raise_finding(
            row["model_id"], "High",
            title=f"Waiver renewed past its limit: {row['control']}",
            owner=row.get("approved_by") or row["proposed_by"],
            description=(
                f"{row['reference']} waives '{row['control']}' and has been "
                f"renewed {renewals} times, past the limit of "
                f"{self.renewal_limit}. A control relaxed this many times in "
                f"succession is not a temporary exception; it is the framework "
                f"this model is actually governed under, and it should be "
                f"argued for as one — either by meeting the control or by "
                f"changing what the tier requires."),
            # `self_identified`: the institution's own register noticed,
            # which is the honest source and a materially better one to
            # show a supervisor than the same finding raised by an audit.
            category="waiver", source="self_identified",
            model_version_id=row.get("model_version_id"), actor=actor)
        self.waivers.set({"finding_id": finding["id"]}, id=row["id"])

    # ------------------------------------------------------------- revoke
    def revoke(self, waiver_id: str, reason: str, *,
               actor: str = "system") -> Dict[str, Any]:
        """End one early. Never deleted: what was relaxed, and when, is history."""
        row = self.require(waiver_id)
        if row["status"] in ("revoked", "expired"):
            raise WaiverError("already_closed",
                              f"{row['reference']} is already "
                              f"'{row['status']}'", "nothing to revoke")
        if not (reason or "").strip():
            raise WaiverError(
                "no_reason", "revoking a waiver needs a reason",
                "say whether the control is now met or the exception was "
                "withdrawn — they are different facts")
        with self.evidence.recording():
            self.waivers.set({"status": "revoked", "closed_at": time.time(),
                              "closure_reason": reason.strip()}, id=waiver_id)
            self.evidence.append("waiver_revoked", "model", row["model_id"],
                                 {"reference": row["reference"],
                                  "reason": reason}, actor=actor)
        return self.require(waiver_id)

    # -------------------------------------------------------------- expire
    def expire_due(self, now: Optional[float] = None,
                   actor: str = "system") -> Dict[str, Any]:
        """Close every active waiver whose window has passed.

        Run from the governance batch. A waiver that expired and that nothing
        marked expired is indistinguishable from one still in force, which is
        the failure mandatory expiry exists to prevent — the date was always
        there and nobody read it.
        """
        moment = now if now is not None else time.time()
        expired = []
        for row in self.waivers.many(status="active"):
            if (row.get("expires_at") or 0) > moment:
                continue
            with self.evidence.recording():
                self.waivers.set({"status": "expired", "closed_at": moment,
                                  "closure_reason": "the window ended"},
                                 id=row["id"])
                self.evidence.append(
                    "waiver_expired", "model", row["model_id"],
                    {"reference": row["reference"],
                     "control": row["control"]}, actor=actor)
            expired.append(row["reference"])
        return {"expired": expired, "count": len(expired)}

    # ---------------------------------------------------------------- read
    def require(self, waiver_id: str) -> Dict[str, Any]:
        row = self.waivers.one(id=waiver_id)
        if not row:
            raise WaiverError("no_such_waiver", f"no waiver '{waiver_id}'",
                              "check the id")
        return row

    def for_model(self, urn: str) -> Dict[str, Any]:
        model = self.registry.require(urn)
        rows = list(self.waivers.many(model_id=model["id"]))
        return {"urn": urn, "waivers": rows, **self._counts(rows)}

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every control the estate is currently not meeting.

        Worst first, and 'worst' is the tier: a relaxed control on a tier 1
        model is a different sentence from the same control relaxed on a tier 4
        one, and a list sorted by date buries it.
        """
        rows = list(self.waivers.many())
        active = [r for r in rows if r["status"] == "active"]
        by_model: Dict[str, List[Dict[str, Any]]] = {}
        for row in active:
            by_model.setdefault(row["model_id"], []).append(row)
        models = []
        for model_id, found in by_model.items():
            model = self.registry.by_id(model_id) or {}
            models.append({
                "model_id": model_id, "urn": model.get("urn"),
                "name": model.get("name"), "tier": model.get("tier"),
                "waivers": found,
                "controls": sorted({r["control"] for r in found})})
        models.sort(key=lambda m: (m.get("tier") or 99, m.get("urn") or ""))
        return {"models": models, **self._counts(rows, now)}

    def _counts(self, rows: List[Dict[str, Any]],
                now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        active = [r for r in rows if r["status"] == "active"]
        # Active and past its date: the register has not run its expiry yet, and
        # the reader should not be told these are in force.
        overdue = [r for r in active if (r.get("expires_at") or 0) <= moment]
        renewed = [r for r in active
                   if int(r.get("renewals") or 0) > self.renewal_limit]
        return {
            "total": len(rows), "active": len(active),
            "proposed": sum(1 for r in rows if r["status"] == PROPOSED),
            "overdue": len(overdue),
            "renewed_past_limit": len(renewed),
            "by_control": {c: sum(1 for r in active if r["control"] == c)
                           for c in WAIVABLE
                           if any(r["control"] == c for r in active)},
            "detail": self._detail(len(active), len(overdue), len(renewed)),
        }

    @staticmethod
    def _detail(active: int, overdue: int, renewed: int) -> str:
        if not active:
            return "no control is currently waived anywhere on the estate"
        out = f"{active} control(s) currently waived"
        if overdue:
            out += (f"; {overdue} of them are past their end date and have not "
                    f"been expired, which means the batch has not run")
        if renewed:
            out += (f"; {renewed} have been renewed past the limit and are no "
                    f"longer temporary exceptions in anything but name")
        return out
