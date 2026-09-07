"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The workflow around a finding — everything between raising one and closing it.

The register next door is already a control: an open blocking finding refuses an
alias move and refuses warrant resolution. What it had no answer for was the
year in the middle. A finding was raised with an owner and a date derived from
its severity, and then nothing happened to it until somebody closed it. There was
no way to hand it over, no record that its owner had ever agreed it was theirs,
nowhere to write down what would be done, and no way to move a date except by
writing a new one into the row.

Five acts close that, and each exists because of a way findings actually go wrong.

**Ownership can move; the record of the handover cannot.** A finding passed
quietly between three people is a finding nobody owned. Every handover names who
gave it up, who took it on, and why.

**An owner accepts, or nobody is working on it.** A remediation date nobody
agreed to is a date somebody else invented, and on every dashboard it looks
exactly like a date somebody is working to. Acknowledgement is the difference,
and it is refused without a plan: a receipt is not a commitment.

**The plan is what will be done, by when.** Written the same way the compliance
debt register writes one, because two idioms for the same idea is one more than
anybody can hold.

**Extension is legitimate and must not be silent.** Dates move for good reasons.
So an extension needs a reason, may not be granted by the person whose deadline
it is, may not be granted at all before the owner has accepted the finding, and
is counted — and past the limit the extension itself becomes a finding. That is
the overlay register's answer to the same shape of problem: a thing renewed often
enough has stopped being temporary, and the platform should say so rather than
leave somebody to notice.

**Escalation is computed, never set.** See ``ageing.py``: an escalation somebody
has to remember to flag is an escalation that happens when somebody remembers.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.validation import ageing
from core.validation.common import (ACKNOWLEDGED, ASSIGNED, DAY,
                                    DEFAULT_ACKNOWLEDGE_DAYS,
                                    DEFAULT_ESCALATE_DAYS,
                                    DEFAULT_EXTENSION_LIMIT, EXTENDED, PLANNED,
                                    REMEDIATION_DAYS, FindingWorkflowError,
                                    same_person)
from core.validation.findings import FindingRegister
from db import FindingActionRepository

logger = get_logger(__name__)

# The title of the finding a serial extension raises, so that raising it is
# idempotent in exactly the way the scheduler's jobs are.
EXTENSION_FINDING = "Remediation date moved repeatedly: {title}"


class FindingWorkflow:
    """Assigns, acknowledges, plans and extends. Escalation it only computes."""

    def __init__(self, register: FindingRegister, actions: FindingActionRepository,
                 evidence: EvidenceEngine,
                 extension_limit: int = DEFAULT_EXTENSION_LIMIT,
                 acknowledge_days: float = DEFAULT_ACKNOWLEDGE_DAYS,
                 escalate_days: float = DEFAULT_ESCALATE_DAYS):
        self.register, self.actions, self.evidence = register, actions, evidence
        self.extension_limit = extension_limit
        self.acknowledge_days, self.escalate_days = acknowledge_days, escalate_days

    # ------------------------------------------------------------------ assign
    def assign(self, finding_id: str, to: str, reason: str,
               actor: str = "system") -> Dict[str, Any]:
        """Hand a finding to somebody else, on the record.

        Whoever raised a finding is fixed for ever; whoever owns it is not. What
        must not happen is the handover leaving no trace, because a finding that
        has been through three owners with nothing written down is a finding
        nobody owned.
        """
        row = self.open_finding(finding_id)
        if not to.strip():
            raise FindingWorkflowError(
                "owner_required",
                "a finding cannot be handed to nobody",
                "name the person or team taking it on; a finding with no owner "
                "is a finding nobody will fix")
        if same_person(to, row["owner"]):
            raise FindingWorkflowError(
                "already_owned", f"{row['owner']} already owns this finding",
                "name a different owner, or leave it where it is")
        if not reason.strip():
            raise FindingWorkflowError(
                "reason_required", "a handover needs a reason",
                "say why ownership is moving; 'reassigned' explains nothing to "
                "whoever reads this at the next committee")
        before = row["owner"]
        with self.evidence.recording():
            self.register.findings.set({"owner": to}, id=finding_id)
            self._record(row, ASSIGNED, actor, from_owner=before, to_owner=to,
                         reason=reason)
            self.evidence.append("finding_assigned", "model", row["model_id"],
                                 {"finding_id": finding_id, "from": before, "to": to,
                                  "reason": reason}, actor=actor)
        logger.info("finding %s handed from %s to %s", finding_id, before, to)
        return self.register.get(finding_id)

    # ------------------------------------------------------------- acknowledge
    def acknowledge(self, finding_id: str, actor: str,
                    committed_at: Optional[float] = None,
                    days: Optional[float] = None, plan: str = "",
                    now: Optional[float] = None) -> Dict[str, Any]:
        """The owner accepts the finding and names the date they will fix it by.

        Only the owner may do this, and not on anybody's behalf: an
        acknowledgement somebody else recorded for you is the paperwork of a
        commitment without the commitment.

        The committed date may not be later than the finding's due date. That is
        the hole this closes — an owner who could acknowledge to any date they
        liked would have an extension mechanism that needed nobody's agreement
        and left no count.
        """
        row = self.open_finding(finding_id)
        moment = now if now is not None else time.time()
        if not same_person(actor, row["owner"]):
            raise FindingWorkflowError(
                "not_the_owner",
                f"{actor} does not own this finding; {row['owner']} does",
                "an acknowledgement recorded by somebody else is not an "
                "acceptance — have the owner acknowledge it, or reassign it first")
        recorded = ageing.plan(self.actions_for(finding_id))
        if plan.strip():
            self.plan_for(finding_id, plan, actor)
        elif not recorded["planned"]:
            raise FindingWorkflowError(
                "plan_required",
                "acknowledging a finding without saying what will be done is a "
                "receipt, not a commitment",
                "record a dated plan for how this will be closed, then acknowledge it")

        target = committed_at if committed_at is not None else (
            moment + days * DAY if days is not None else row["due_at"])
        if target <= moment:
            raise FindingWorkflowError(
                "date_in_the_past",
                "the date you are committing to has already passed",
                "commit to a date in the future, or close the finding if the work "
                "is already done")
        if target > row["due_at"]:
            raise FindingWorkflowError(
                "beyond_the_due_date",
                f"you cannot commit to a date after this finding's remediation "
                f"date; it is due in "
                f"{(row['due_at'] - moment) / DAY:.0f} day(s)",
                "commit within the window, or ask somebody who does not own this "
                "finding to extend it — an extension is counted and needs a reason")

        self._record(row, ACKNOWLEDGED, actor, committed_at=target, acted_at=moment)
        self.evidence.append("finding_acknowledged", "model", row["model_id"],
                             {"finding_id": finding_id, "owner": row["owner"],
                              "committed_at": target}, actor=actor)
        if row["status"] == "open":
            # The status column now agrees with what was actually done. It is a
            # summary of the acts, never a substitute for them.
            self.register.set_status(finding_id, "in_remediation", actor=actor)
        return self.reading(finding_id, now=moment)

    # --------------------------------------------------------------- the plan
    def plan_for(self, finding_id: str, plan: str,
                 actor: str = "system") -> Dict[str, Any]:
        """Record how and by when this finding will be closed.

        Named and shaped after ``DebtRegister.plan_for``: the compliance debt
        register already had this idea and a second idiom for it would be one
        more than anybody can hold in their head.
        """
        row = self.open_finding(finding_id)
        if not plan.strip():
            raise FindingWorkflowError(
                "plan_required", "a finding needs a dated plan to close it",
                "say what will be done and by when; 'will fix' is not a plan")
        self._record(row, PLANNED, actor, plan=plan)
        self.evidence.append("finding_planned", "model", row["model_id"],
                             {"finding_id": finding_id, "plan": plan}, actor=actor)
        return self.register.get(finding_id)

    # ---------------------------------------------------------------- extend
    def extend(self, finding_id: str, actor: str, reason: str,
               days: Optional[float] = None, due_at: Optional[float] = None,
               now: Optional[float] = None) -> Dict[str, Any]:
        """Move a remediation date. Legitimate, never silent, and counted.

        Three refusals, each of them a hole somebody would otherwise walk
        through: an extension with no reason is a date that changed by itself;
        an extension granted by the owner is a deadline that person sets for
        themselves; and an extension of a finding nobody has accepted is moving
        a date that was never agreed in the first place.

        Past the limit the extension itself becomes a finding, because a date
        moved often enough is not a date, and that is a governance failure
        distinct from whatever the original finding was about.
        """
        row = self.open_finding(finding_id)
        moment = now if now is not None else time.time()
        if not reason.strip():
            raise FindingWorkflowError(
                "reason_required", "moving a remediation date needs a reason",
                "say what changed; a date that moves without one is a date "
                "nobody is accountable for")
        if same_person(actor, row["owner"]):
            raise FindingWorkflowError(
                "self_extension",
                f"{actor} owns this finding and cannot extend their own deadline",
                "an extension is the point at which somebody independent asks "
                "whether the date was ever realistic; route it to the second line")
        state = self.reading(finding_id, now=moment)
        if not state["acknowledgement"]["acknowledged"]:
            raise FindingWorkflowError(
                "not_acknowledged",
                "this finding has not been accepted by its owner, so there is no "
                "agreed date to extend",
                "have the owner acknowledge it with a plan first; extending a "
                "date nobody agreed to moves a number, not a commitment")

        window = REMEDIATION_DAYS.get(row["severity"], 90)
        target = due_at if due_at is not None else (
            row["due_at"] + (days if days is not None else window) * DAY)
        if target <= row["due_at"]:
            raise FindingWorkflowError(
                "not_an_extension",
                "the date you gave is not later than the current one",
                "an extension moves a date outwards; to bring one forward, "
                "record a plan that says so and close the finding sooner")
        granted = (target - row["due_at"]) / DAY
        if granted > window:
            raise FindingWorkflowError(
                "extension_too_long",
                f"{granted:.0f} days is longer than the {window}-day remediation "
                f"window a {row['severity']} finding gets in the first place",
                "grant a shorter extension and look at it again; an extension "
                "longer than the original window is a new remediation date "
                "nobody has justified")

        with self.evidence.recording():
            self.register.findings.set({"due_at": target}, id=finding_id)
            self._record(row, EXTENDED, actor, reason=reason, due_before=row["due_at"],
                         due_after=target, acted_at=moment)
            self.evidence.append("finding_extended", "model", row["model_id"],
                                 {"finding_id": finding_id, "from": row["due_at"],
                                  "to": target, "days": round(granted, 1),
                                  "reason": reason}, actor=actor)
        logger.info("finding %s extended by %.0f days by %s", finding_id, granted,
                    actor)
        self._escalate_if_repeatedly_extended(finding_id, actor, moment)
        return self.reading(finding_id, now=moment)

    def _escalate_if_repeatedly_extended(self, finding_id: str, actor: str,
                                         now: float) -> None:
        """Past the limit, this is a governance failure. Say so, once."""
        row = self.register.require(finding_id)
        counted = ageing.extensions(self.actions_for(finding_id),
                                    self.extension_limit)
        if not counted["over_limit"]:
            return
        title = EXTENSION_FINDING.format(title=row["title"])
        if any(f["title"] == title
               for f in self.register.open_for(row["model_id"])):
            return                     # already said; saying it again is noise
        self.register.raise_finding(
            row["model_id"], "High", title, row["owner"],
            description=(f"{counted['detail']}. The original finding stands; this "
                         "records that its remediation date has been moved often "
                         "enough that it no longer means anything. Either the "
                         "work is not being done, or the date was never "
                         "realistic — and both are decisions somebody has to make "
                         "rather than defer again."),
            category="remediation_extension", source="self_identified",
            model_version_id=row.get("model_version_id"), actor=actor)
        logger.warning("finding %s escalated after %d extensions", finding_id,
                       counted["count"])

    # ------------------------------------------------------------------ query
    def require(self, finding_id: str) -> Dict[str, Any]:
        """The finding, in the coded form the route layer maps onto a 404."""
        row = self.register.get(finding_id)
        if row is None:
            raise FindingWorkflowError(
                "no_finding", f"no finding {finding_id}",
                "check the identifier against the register for this model")
        return row

    def open_finding(self, finding_id: str) -> Dict[str, Any]:
        """The finding, refusing if it is missing or already closed."""
        row = self.require(finding_id)
        if row["status"] == "closed":
            raise FindingWorkflowError(
                "finding_closed",
                f"finding {finding_id} was closed and its workflow has ended",
                "a closed finding is a matter of record; raise a new one if the "
                "problem has come back")
        return row

    def actions_for(self, finding_id: str) -> List[Dict[str, Any]]:
        return self.actions.for_finding(finding_id)

    def reading(self, finding_id: str,
                now: Optional[float] = None) -> Dict[str, Any]:
        """One finding, its acts, and everything derived from them."""
        row = self.require(finding_id)
        moment = now if now is not None else time.time()
        return {**row, "actions": self.actions_for(finding_id),
                **ageing.reading(row, self.actions_for(finding_id), moment,
                                 self.escalate_days, self.acknowledge_days,
                                 self.extension_limit)}

    def escalated(self, model_id: str,
                  now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Open findings that are no longer only their owner's problem."""
        moment = now if now is not None else time.time()
        out = []
        for row in self.register.open_for(model_id):
            reading = ageing.reading(row, self.actions_for(row["id"]), moment,
                                     self.escalate_days, self.acknowledge_days,
                                     self.extension_limit)
            if reading["escalation"]["escalate"]:
                out.append({**reading, "title": row["title"],
                            "model_id": model_id})
        return out

    def ageing(self, model_id: str, now: Optional[float] = None,
               include_closed: bool = True) -> Dict[str, Any]:
        """The ageing profile for one model's register."""
        moment = now if now is not None else time.time()
        rows = (self.register.findings.many(model_id=model_id) if include_closed
                else self.register.open_for(model_id))
        return {"model_id": model_id,
                **ageing.profile(rows,
                                 {r["id"]: self.actions_for(r["id"]) for r in rows},
                                 moment, self.escalate_days, self.acknowledge_days,
                                 self.extension_limit)}

    def across(self, model_ids, now: Optional[float] = None) -> Dict[str, Any]:
        """The profile across an estate, which is the number a committee asks for."""
        moment = now if now is not None else time.time()
        wanted = list(model_ids)
        rows: List[Dict[str, Any]] = []
        for model_id in wanted:
            rows.extend(self.register.findings.many(model_id=model_id))
        return {"models": len(wanted),
                **ageing.profile(rows,
                                 {r["id"]: self.actions_for(r["id"]) for r in rows},
                                 moment, self.escalate_days, self.acknowledge_days,
                                 self.extension_limit)}

    # ----------------------------------------------------------------- record
    def _record(self, finding: Dict[str, Any], act: str, actor: str,
                from_owner: Optional[str] = None, to_owner: Optional[str] = None,
                reason: str = "", plan: str = "",
                committed_at: Optional[float] = None,
                due_before: Optional[float] = None,
                due_after: Optional[float] = None,
                acted_at: Optional[float] = None) -> Dict[str, Any]:
        """Append one act. Nothing here is ever updated or removed."""
        row = {"finding_id": finding["id"], "model_id": finding["model_id"],
               "act": act, "actor": actor, "from_owner": from_owner,
               "to_owner": to_owner, "reason": reason, "plan": plan,
               "committed_at": committed_at, "due_before": due_before,
               "due_after": due_after,
               "acted_at": acted_at if acted_at is not None else time.time()}
        self.actions.add(row)
        return row
