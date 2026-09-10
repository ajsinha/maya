"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The jobs: where a computed condition becomes a recorded consequence.

Almost everything in this platform is derived rather than remembered — expiry,
staleness, maturity, debt. That is the right design, and it has one hole in it:
a condition that is true and that nobody has looked at has had no consequence.
An attestation that lapsed on Tuesday is visible on Wednesday to whoever opens
the page, and invisible to everybody else.

These jobs close that. They do not compute anything new; they take conditions
the platform already computes and turn them into things that are *recorded* — a
finding, a state change, an evidence entry. After this, a lapsed attestation
raises a finding, and a finding can block.

Every job is **idempotent**. Running one twice changes nothing more than running
it once, because a schedule that must not be run twice is a schedule that will
be, and the first duplicate run will be at three in the morning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

# How far past its cadence a monitor must be before the platform treats the
# absence of monitoring as a finding in its own right. A monitor that is a day
# late is a batch that ran late; one that is a month late is a control that has
# stopped operating.
MONITOR_GRACE_MULTIPLE = 3.0


@dataclass(frozen=True)
class Job:
    """One scheduled act, and what it is for."""
    key: str
    what: str
    why: str
    run: Callable[["JobContext"], Dict[str, Any]]


@dataclass
class JobContext:
    """The services a job may reach, and the moment it is running at."""
    registry: Any
    now: float
    lifecycle: Any = None
    findings: Any = None
    monitoring: Any = None
    overlays: Any = None
    debts: Any = None
    documents: Any = None
    notifications: Any = None
    finding_workflow: Any = None
    evidence: Any = None
    risk: Any = None
    waivers: Any = None
    uses: Any = None
    pipeline: Any = None
    immaterial: Any = None
    lifecycle_profiles: Any = None
    canaries: Any = None
    break_glass: Any = None
    idempotency: Any = None
    inference: Any = None
    subscriptions: Any = None
    adaptive: Any = None
    discovery: Any = None
    actor: str = "scheduler"

    def models(self) -> List[Dict[str, Any]]:
        return self.registry.list()


def _already_raised(findings, model_id: str, title: str) -> bool:
    """Idempotence: the same condition must not raise the same finding twice."""
    return any(f["title"] == title for f in findings.open_for(model_id))


# ---------------------------------------------------------------------------
# Attestation lapse
# ---------------------------------------------------------------------------
def attestation_lapsed(ctx: JobContext) -> Dict[str, Any]:
    """An expired attestation is a model in force on a signature nobody renewed."""
    if not (ctx.lifecycle and ctx.findings):
        return {"skipped": "lifecycle or findings not available"}
    raised = []
    for model in ctx.models():
        state = ctx.lifecycle.state(model["urn"])
        if not state.get("attestation_expired"):
            continue
        title = "Attestation has lapsed"
        if _already_raised(ctx.findings, model["id"], title):
            continue
        ctx.findings.raise_finding(
            model["id"], "High", title, model["owner"] or "unassigned",
            description=("This model is in force on an attestation that has passed "
                         "its validity period. Either renew it or withdraw the "
                         "model from use; a model in force on a lapsed attestation "
                         "is in force on nobody's current signature."),
            # BLOCKING. `BLOCKING_BY_DEFAULT` is ("Critical",) and every job
            # here raises High or Medium, so every finding the governance batch
            # has ever raised was advisory — a model whose attestation lapsed
            # could still be moved to production, and the platform's own
            # description of the condition is "in force on nobody's current
            # signature". A control that raises a row nobody has to act on is
            # the defect this codebase is named for.
            blocking=True,
            category="attestation", source="self_identified", actor=ctx.actor)
        raised.append(model["urn"])
    return {"raised": raised, "count": len(raised)}


# ---------------------------------------------------------------------------
# Periodic review
# ---------------------------------------------------------------------------
def review_overdue(ctx: JobContext) -> Dict[str, Any]:
    """A model past the review date its own tier set.

    `TieringEngine.persist` computes `next_review_due` from the tier — twelve
    months at Tier 1, thirty-six at Tier 4 — writes it to every assessment, and
    until now NOTHING read it. Not a job, not a screen, not an endpoint. The
    cadence that is the whole reason the engine carries a review map was a
    column nobody selected.

    That is the quietest kind of gap: periodic review is the obligation SR 11-7
    is most explicit about, MAYA knew exactly when each one fell due, and an
    estate could pass every other control while its Tier 1 models went four
    years unreviewed.

    Raised against the LATEST assessment only. An older one being overdue says
    nothing — reassessing is what discharges the obligation, and the newest row
    is the one that carries the current date.
    """
    if not (ctx.risk and ctx.findings):
        return {"skipped": "risk register or findings not available"}
    raised = []
    for model in ctx.models():
        assessments = ctx.risk.many(model_id=model["id"])
        if not assessments:
            continue
        latest = max(assessments, key=lambda a: a.get("assessed_at") or 0)
        due = latest.get("next_review_due")
        if not due or ctx.now < due:
            continue
        title = "Periodic review is overdue"
        if _already_raised(ctx.findings, model["id"], title):
            continue
        overdue_days = int((ctx.now - due) / 86400)
        ctx.findings.raise_finding(
            model["id"],
            "High" if (latest.get("tier") or 4) <= 2 else "Medium",
            title, model["owner"] or "unassigned",
            description=(
                f"This model's risk assessment set a review date "
                f"{overdue_days} days ago and no reassessment has happened "
                f"since. Tier {latest.get('tier')} carries a review cadence, "
                f"and a tier is a claim about how closely something is watched; "
                f"a model past its review date is running on an assessment "
                f"nobody has confirmed still describes it. Reassess it, or "
                f"retire it."),
            # BLOCKING on the tiers whose review cadence is the control. A
            # review 1,285 days overdue used to let an alias move to production
            # through with a 200: the finding was raised, listed, and stopped
            # nothing. Tiers 3 and 4 stay advisory, because a low-materiality
            # model past its review date is a housekeeping matter and blocking
            # it would teach people to ignore the flag.
            blocking=(latest.get("tier") or 4) <= 2,
            category="periodic_review", source="self_identified",
            actor=ctx.actor)
        raised.append(model["urn"])
    return {"raised": raised, "count": len(raised)}


# ---------------------------------------------------------------------------
# Monitoring that has stopped
# ---------------------------------------------------------------------------
def monitoring_stalled(ctx: JobContext) -> Dict[str, Any]:
    """A monitor far past its cadence is a control that has stopped operating.

    The platform cannot evaluate it — that needs data it does not hold — but it
    can say that nobody has. Silence from a monitor reads identically to a
    passing monitor on every dashboard, and that is the failure this catches.
    """
    if not (ctx.monitoring and ctx.findings):
        return {"skipped": "monitoring or findings not available"}
    raised = []
    for model in ctx.models():
        for monitor in ctx.monitoring.registry.for_model(model["id"]):
            if monitor["status"] != "active":
                continue
            last = monitor["last_evaluated_at"] or monitor["created_at"]
            overdue_by = (ctx.now - last) / DAY - monitor["cadence_days"]
            if overdue_by < monitor["cadence_days"] * (MONITOR_GRACE_MULTIPLE - 1):
                continue
            title = f"Monitoring has stopped: {monitor['name']}"
            if _already_raised(ctx.findings, model["id"], title):
                continue
            ctx.findings.raise_finding(
                model["id"], "Medium", title, monitor["owner"],
                description=(f"'{monitor['name']}' has a {monitor['cadence_days']:g}-day "
                             f"cadence and has not been evaluated for "
                             f"{(ctx.now - last) / DAY:.0f} days. A monitor that is "
                             "not running looks exactly like a monitor that is "
                             "passing."),
                category="monitoring", source="self_identified", actor=ctx.actor)
            raised.append(f"{model['urn']}:{monitor['name']}")
    return {"raised": raised, "count": len(raised)}


# ---------------------------------------------------------------------------
# Overlays whose window has elapsed
# ---------------------------------------------------------------------------
def expire_overlays(ctx: JobContext) -> Dict[str, Any]:
    """Make the stored status agree with the computed one.

    Expiry was already computed, so nothing depended on this running. What it
    changes is that the overlay register now *says* expired rather than leaving
    a reader to work it out.
    """
    if not ctx.overlays:
        return {"skipped": "overlays not available"}
    closed = []
    for model in ctx.models():
        for row in ctx.overlays.sweep_expired(model["id"], ctx.now, ctx.actor):
            closed.append(f"{model['urn']}:{row['reference']}")
    return {"expired": closed, "count": len(closed)}


# ---------------------------------------------------------------------------
# Baseline debt
# ---------------------------------------------------------------------------
def reconcile_debt(ctx: JobContext) -> Dict[str, Any]:
    """Close debt whose evidence arrived; expire what is overdue into breaches."""
    if not (ctx.debts and ctx.documents):
        return {"skipped": "debt register or context builder not available"}
    closed = breached = 0
    touched = []
    for model in ctx.models():
        if not ctx.debts.open_for(model["id"]):
            continue
        state = ctx.documents.build_context(model["urn"])
        report = ctx.debts.reconcile(model["id"], state, ctx.actor)
        if report["closed"] or report["breached"]:
            touched.append(model["urn"])
        closed += len(report["closed"])
        breached += len(report["breached"])
    return {"models": touched, "closed": closed, "breached": breached}


# ---------------------------------------------------------------------------
# Findings past their remediation window
# ---------------------------------------------------------------------------
def escalate_overdue_findings(ctx: JobContext) -> Dict[str, Any]:
    """An overdue finding on a Tier 1 model is not the same as a note.

    Severity is not raised — that would rewrite what a validator concluded.
    What is recorded is a *separate* finding that the remediation window was
    missed, which is a different failure and belongs to a different owner.
    """
    if not ctx.findings:
        return {"skipped": "findings not available"}
    raised = []
    for model in ctx.models():
        overdue = ctx.findings.overdue(model["id"], ctx.now)
        for finding in overdue:
            if finding["category"] == "remediation_sla":
                continue                      # do not escalate an escalation
            title = f"Remediation overdue: {finding['title']}"
            if _already_raised(ctx.findings, model["id"], title):
                continue
            days = (ctx.now - finding["due_at"]) / DAY
            ctx.findings.raise_finding(
                model["id"], "High", title, finding["owner"],
                description=(f"A {finding['severity']} finding passed its "
                             f"remediation date {days:.0f} days ago and is still "
                             "open. The original finding stands; this records that "
                             "the window agreed for closing it was missed."),
                category="remediation_sla", source="self_identified",
                actor=ctx.actor)
            raised.append(f"{model['urn']}:{finding['id']}")
    return {"raised": raised, "count": len(raised)}


def unacknowledged_findings(ctx: JobContext) -> Dict[str, Any]:
    """A finding nobody has accepted is not being worked on.

    The reminder cycle itself is delivery, and delivery already exists: the
    worklist derives an unaccepted finding and the notification job posts it. So
    this job is not a reminder — it is what happens when the reminders have been
    ignored. Past the acknowledgement window with no owner having accepted it,
    the silence stops being an oversight and becomes a fact worth recording,
    because on every dashboard an unaccepted finding looks exactly like one
    somebody is working on.

    Idempotent the same way the others are: the same condition raises the same
    finding once, matched on its title.
    """
    if not (ctx.findings and ctx.finding_workflow):
        return {"skipped": "findings workflow not available"}
    raised = []
    for model in ctx.models():
        for finding in ctx.findings.open_for(model["id"]):
            if finding["category"] in ("remediation_acknowledgement",
                                       "remediation_sla", "remediation_extension"):
                continue                     # do not escalate an escalation
            reading = ctx.finding_workflow.reading(finding["id"], now=ctx.now)
            if reading["acknowledgement"]["acknowledged"]:
                continue
            waiting = (ctx.now - reading["owned_since"]) / DAY
            if waiting <= ctx.finding_workflow.acknowledge_days:
                continue
            title = f"Finding never accepted: {finding['title']}"
            if _already_raised(ctx.findings, model["id"], title):
                continue
            ctx.findings.raise_finding(
                model["id"], "Medium", title, finding["owner"],
                description=(f"A {finding['severity']} finding has been open for "
                             f"{waiting:.0f} days and its owner has never accepted "
                             "it or recorded what will be done about it. The "
                             "original finding stands; this records that nobody "
                             "has agreed to fix it, which is a different failure "
                             "and one an unaccepted remediation date hides."),
                category="remediation_acknowledgement", source="self_identified",
                actor=ctx.actor)
            raised.append(f"{model['urn']}:{finding['id']}")
    return {"raised": raised, "count": len(raised)}


def notify_outstanding(ctx) -> Dict[str, Any]:
    """Tell people what is outstanding for them.

    The work is already derived; this is delivery. A worklist unchanged since
    the last message is suppressed, because a message that repeats yesterday's
    is a message somebody filters — and a control everybody filters has stopped
    operating.
    """
    notifications = getattr(ctx, "notifications", None)
    if notifications is None:
        return {"sent": 0, "detail": "no notification service on this instance"}
    out = notifications.run(now=ctx.now, actor=ctx.actor)
    return {"sent": out["sent"], "suppressed": out["suppressed"],
            "failed": out["failed"], "detail": out["detail"]}


def verify_evidence_chain(ctx: JobContext) -> Dict[str, Any]:
    """Walk the WHOLE chain and move the verification checkpoint.

    Readiness asks the cheap question -- has anything broken since the last full
    verification -- because walking and re-hashing every node on every probe was
    2.9 seconds at forty thousand nodes and would have taken a busy instance out
    of service. That trade is only honest if the full walk actually happens, so
    it happens here, on a cadence somebody chose.

    A broken chain is reported and NOT checkpointed: advancing the mark past a
    break would bless it, and every subsequent cheap check would start after the
    damage and report health.
    """
    if ctx.evidence is None:
        return {"verified": False, "detail": "no evidence engine is wired"}
    report = ctx.evidence.verify_chain()
    if report["valid"]:
        ctx.evidence._record_checkpoint(report["length"], report["head"],
                                        actor=ctx.actor)
        return {"verified": True, "length": report["length"],
                "head": report["head"],
                "detail": f"{report['length']:,} nodes verified and checkpointed"}
    logger.error("evidence chain is broken at seq %s: %s",
                 report.get("broken_at"), report.get("reason"))
    return {"verified": False, "broken_at": report.get("broken_at"),
            "reason": report.get("reason"),
            "detail": "the chain is broken; the checkpoint was NOT advanced, "
                      "because moving it past a break would bless it"}


def anchor_evidence_chain(ctx) -> Dict[str, Any]:
    """Write the chain head to the anchor root, outside the database.

    `evidence.verify` walks the chain and compares it against itself, which is
    exactly what a rewritten chain passes. This writes the head somewhere the
    database cannot reach, so that a later comparison asks a question an
    attacker holding the database alone cannot answer.

    It verifies first and refuses to anchor a broken chain — writing the broken
    state down would make every subsequent comparison agree with it.
    """
    if ctx.evidence is None:
        return {"anchored": 0, "detail": "no evidence engine is wired"}
    if getattr(ctx.evidence, "anchors", None) is None:
        return {"anchored": 0,
                "detail": "no anchor root is configured, so the chain is "
                          "self-certified; set data.worm to change that"}
    agreement = ctx.evidence.verify_against_anchors()
    if not agreement["agrees"]:
        logger.error("chain disagrees with %d anchor(s); refusing to anchor "
                     "again over the top", len(agreement.get("broken", [])))
        return {"anchored": 0, "agrees": 0, "broken": agreement.get("broken"),
                "detail": "the chain disagrees with what was anchored before. "
                          "Nothing further was written: the existing anchors "
                          "are the evidence, and overwriting them would destroy "
                          "it"}
    written = ctx.evidence.anchor_head(actor=ctx.actor)
    return {"anchored": written.get("written", 0), "agrees": 1,
            "seq": written.get("seq"),
            "detail": written.get("detail")
                      or (f"head anchored at seq {written.get('seq')}"
                          if written.get("written")
                          else "already anchored at this head")}


def expire_waivers(ctx: "JobContext") -> Dict[str, Any]:
    """Close every waiver whose window has ended.

    Mandatory expiry is only a control if something acts on the date. A waiver
    that expired and that nothing marked expired is indistinguishable on every
    screen from one still in force — the date was always there, and nobody read
    it. That is the exact failure the requirement's phrase *no indefinite
    exceptions* is about, arriving by the back door.
    """
    if ctx.waivers is None:
        return {"expired": [], "count": 0,
                "detail": "no waiver register is wired into this instance"}
    out = ctx.waivers.expire_due(now=ctx.now, actor=ctx.actor)
    return {**out,
            "detail": (f"{out['count']} waiver(s) expired: "
                       f"{', '.join(out['expired'])}" if out["count"]
                       else "no waiver reached its end date")}


def lifecycle_stalled(ctx: "JobContext") -> Dict[str, Any]:
    """Records that have been mid-move longer than their tier allows.

    Nothing else in this platform can see this. The submission succeeded, every
    gate passed, and no control is watching the clock — which is exactly how a
    governance queue becomes a place things go to wait. A model sitting
    `submitted` for four months is not blocked by anything and appears on no
    report, because the only thing that would show it is a state carrying an
    expected duration.

    Advisory at every tier, and deliberately so. A queue is allowed to have a
    queue: the reviewer may be right to be taking their time, the model may be
    genuinely contentious, and blocking on it would punish the second line for
    doing the job carefully. What is not allowed is for nobody to know.
    """
    if not (ctx.lifecycle_profiles and ctx.findings):
        return {"skipped": "lifecycle profiles or findings not available"}
    report = ctx.lifecycle_profiles.stalled(now=ctx.now)
    raised = []
    for row in report["stalled"]:
        model = ctx.registry.get(row["urn"]) or {}
        if not model:
            continue
        title = f"Record has been {row['status']} for {row['days_in_state']:.0f} days"
        if _already_raised(ctx.findings, model["id"], title):
            continue
        ctx.findings.raise_finding(
            model["id"], "Medium" if (row.get("tier") or 4) <= 2 else "Low",
            title, row.get("owner") or model.get("owner") or "unassigned",
            description=(
                f"This record entered '{row['status']}' {row['days_in_state']:.0f} "
                f"days ago, against the {row['limit_days']:.0f} days a tier "
                f"{row.get('tier')} record is expected to take — over by "
                f"{row['days_over']:.0f}. Nothing has refused anything: the "
                f"submission succeeded and every gate passed. That is the "
                f"point. A queue with no expected duration is one nobody can "
                f"tell is stuck, and this is the only thing here that looks at "
                f"the clock. Move it on, or say why it is waiting."),
            blocking=False,
            category="lifecycle_delay", source="self_identified",
            actor=ctx.actor)
        raised.append(row["urn"])
    return {"raised": raised, "count": len(raised),
            "stalled": report["count"],
            "not_measurable": len(report["not_measurable"]),
            "detail": report["detail"]}


def discovery_backlog(ctx: "JobContext") -> Dict[str, Any]:
    """Discovery candidates nobody has looked at.

    A sweep that runs and is never triaged is worse than no sweep: the estate
    believes it has a discovery programme, and what it has is a table filling
    up. This is the point at which that becomes somebody's work rather than a
    page nobody opens.

    Advisory, and per scanner rather than per candidate: four thousand findings
    is not four thousand pieces of work, it is one — *nobody is reading the
    output of this scanner* — and raising it four thousand times is the same
    failure the triage record exists to prevent.
    """
    if not (ctx.discovery and ctx.findings and ctx.registry):
        return {"skipped": "discovery register or findings not available"}
    report = ctx.discovery.outstanding(now=ctx.now)
    if not report["stale"]:
        return {"raised": [], "count": 0, "detail": report["detail"]}
    # No model to hang it on: a candidate is not a model, which is the whole
    # point. Reported rather than raised as a finding.
    return {"raised": [], "count": 0, "stale": report["stale"],
            "detail": report["detail"]}


def check_adaptive_change(ctx: "JobContext") -> Dict[str, Any]:
    """Models that have changed themselves past a bound.

    A T4 model has no version bump for anything to notice, so nothing in the
    register's ordinary machinery sees it move. Without this the trajectory is
    computed only when somebody opens a page, and an adaptive model that
    wandered between two people looking at it wandered unobserved.

    The finding is BLOCKING at tier 1 and 2. Cumulative drift past the bound
    means the model is materially not the one that was approved, and a warning
    nobody has to act on is how it stays that way.
    """
    if not (ctx.adaptive and ctx.findings):
        return {"skipped": "adaptive monitoring or findings not available"}
    report = ctx.adaptive.sweep(now=ctx.now)
    raised = []
    for row in report["models"]:
        if not row["excursion"]:
            continue
        model = ctx.registry.get(row["urn"])
        if not model:
            continue
        title = f"Adaptive model has drifted from what was approved ({row['semver']})"
        if _already_raised(ctx.findings, model["id"], title):
            continue
        drift = (f"{row['cumulative']:.1%} away from the last approved "
                 f"parameters" if row.get("cumulative") is not None
                 else f"{row['changes']} autonomous change(s), magnitude "
                      f"unmeasurable because the parameters are not in the "
                      f"register")
        ctx.findings.raise_finding(
            model["id"], "High" if (row.get("tier") or 4) <= 2 else "Medium",
            title, row.get("owner") or "unassigned",
            description=(
                f"This version has changed its own parameters "
                f"{row['changes']} time(s) and is {drift}. No version was "
                f"created and nothing was re-approved, which is why no other "
                f"control here saw it: every one of them fires on a version. "
                f"The figure that matters is the cumulative one — a model "
                f"moving a tenth of a percent a night moves three percent in a "
                f"month, and every single step passes a per-change threshold "
                f"comfortably. Re-approve the current parameters, or roll back "
                f"to the ones somebody agreed to."),
            blocking=(row.get("tier") or 4) <= 2,
            category="adaptive_drift", source="self_identified",
            actor=ctx.actor)
        raised.append(row["urn"])
    return {"raised": raised, "count": len(raised),
            "excursions": report["excursions"], "detail": report["detail"]}


def deliver_events(ctx: "JobContext") -> Dict[str, Any]:
    """Push each subscriber's backlog, from its own cursor.

    On the batch rather than at the moment of the act, and that is deliberate:
    a governance act must not fail because somebody's webhook receiver is down.
    An act that could be rolled back by a failed notification would make an
    outside system's availability part of this register's integrity.

    Each subscriber has its own cursor, so one that is failing falls behind
    alone rather than holding up the rest or being silently skipped past.
    """
    if ctx.subscriptions is None:
        return {"delivered": 0,
                "detail": "no subscription register is wired into this "
                          "instance"}
    return ctx.subscriptions.deliver_all(now=ctx.now)


def expire_inference(ctx: "JobContext") -> Dict[str, Any]:
    """Delete inference records nobody may keep any longer.

    The one place in this platform where deleting is the correct behaviour.
    Everything else is append-only because its content *is* the record; this
    table's content is somebody else's personal data, and a retention period
    enforced by a column that a query could select around is not a retention
    period.

    Which makes this the job whose *absence* is the finding. A register that
    stops running its batch quietly starts holding personal data past the point
    it decided it could — and nothing else here would notice, because every
    other lapse this scheduler records is derived rather than stored.
    """
    if ctx.inference is None:
        return {"dropped": 0,
                "detail": "no inference log is wired into this instance"}
    return ctx.inference.expire_due(now=ctx.now)


def sweep_idempotency(ctx: "JobContext") -> Dict[str, Any]:
    """Drop idempotency records nobody can still be waiting on.

    The table is a copy of every successful response a caller asked to be able
    to retry, and without this it becomes a permanent one. The retention window
    is the honest bound: a client still retrying a day later is retrying
    something it should be told about rather than quietly handed an old answer
    to.
    """
    if ctx.idempotency is None:
        return {"dropped": 0,
                "detail": "no idempotency store is wired into this instance"}
    return ctx.idempotency.sweep(now=ctx.now)


def expire_break_glass(ctx: "JobContext") -> Dict[str, Any]:
    """Close every emergency elevation whose window has ended.

    Housekeeping rather than the control, and the distinction matters. Expiry
    is derived from the window on every read, so a grant is closed to the
    platform the instant its window ends whether or not this has run — a grant
    that is only closed when a batch runs is open whenever the batch is not,
    which is exactly when it would matter.

    What this adds is the *record*: a row that still says `open` three weeks
    later reads, to anybody looking at the table rather than calling the API,
    like an elevation somebody left running.
    """
    if ctx.break_glass is None:
        return {"expired": [], "count": 0,
                "detail": "no break-glass register is wired into this instance"}
    return ctx.break_glass.expire_due(now=ctx.now, actor=ctx.actor)


def check_base_models(ctx: "JobContext") -> Dict[str, Any]:
    """Whether the model under each capability's version string has moved.

    A `base_model` string identifies nothing on its own. A hosted model is
    re-trained, quantised and rolled forward while the string it answers to
    stays the same, and nobody is told — so this has to be something that
    happens on a schedule rather than something somebody remembers.

    The probe calls are deliberately **not charged to the capability's budget**.
    A control that consumes the resource it is protecting would refuse to run
    once that resource ran out, which is precisely the moment you would want it
    to.
    """
    if not (ctx.canaries and ctx.findings and ctx.registry):
        return {"skipped": "canary register or findings not available"}
    report = ctx.canaries.across_the_estate(actor=ctx.actor)
    # No finding is raised against a model, because a capability is not one.
    # The consequence has already happened inside `check`: the review sample is
    # back to 1.0, which is the eval gate re-running.
    return {"count": report["changed"], "checked": report["checked"],
            "without_a_baseline": report["without_a_baseline"],
            "unfingerprintable": report["unfingerprintable"],
            "detail": report["detail"]}


def scan_for_injection(ctx: "JobContext") -> Dict[str, Any]:
    """Register rows carrying content shaped like an instruction to a model.

    Detection that only ran when somebody asked for a draft would miss the row
    nobody has drafted about yet — which is precisely the row an attacker would
    choose, because it sits in the register until the day it is used.

    Advisory, and it has to be. This is a blocklist, and a blocklist run as a
    gate fails open on everything it does not recognise while failing closed on
    somebody who wrote "ignore the above" in a limitation. The structural fence
    in the prompt is the control; this raises a finding so a person reads the
    row.
    """
    if not (ctx.evidence and ctx.findings and ctx.registry):
        return {"skipped": "evidence chain or findings not available"}
    from core.assist import injection

    report = injection.sweep(ctx.evidence)
    raised = []
    for subject in report["subjects"]:
        if subject["subject_type"] != "model":
            continue
        model = ctx.registry.by_id(subject["subject_id"])
        if not model:
            continue
        title = "Register content is shaped like an instruction to a model"
        if _already_raised(ctx.findings, model["id"], title):
            continue
        ctx.findings.raise_finding(
            model["id"], "Low", title, model.get("owner") or "unassigned",
            description=(
                f"{subject['count']} span(s) in this model's record match "
                f"known injection shapes ({', '.join(subject['patterns'])}). "
                f"Nothing has been removed and no draft was refused: the "
                f"prompt fences register content behind a per-call nonce, so "
                f"this is a signal rather than an incident. It is worth "
                f"reading because it is either somebody testing the platform, "
                f"somebody's joke, or a field somebody filled in badly — and "
                f"all three are things you would want to know about a record "
                f"a model will one day be asked to summarise."),
            blocking=False,
            category="prompt_injection", source="self_identified",
            actor=ctx.actor)
        raised.append(model["urn"])
    return {"raised": raised, "count": len(raised),
            "subjects": report["count"], "hits": report["hits"],
            "complete": report["complete"], "detail": report["detail"]}


def check_immaterial(ctx: "JobContext") -> Dict[str, Any]:
    """Every immaterial model, against the conditions that would escalate it.

    Nothing is re-tiered. Materiality is a judgement and the register's job is
    to make sure somebody makes it, not to make it — a platform that silently
    re-tiered a model would be one whose tiers nobody could account for.
    """
    if ctx.immaterial is None:
        return {"count": 0,
                "detail": "no immaterial path is wired into this instance"}
    return ctx.immaterial.sweep(now=ctx.now, actor=ctx.actor)


def check_pipelines(ctx: "JobContext") -> Dict[str, Any]:
    """Every feature view, against its own history.

    Most model failures are data failures, and every other monitor in this
    platform points at a model's scores — which is the last place the problem
    shows up rather than the first.
    """
    if ctx.pipeline is None:
        return {"count": 0,
                "detail": "no pipeline health check is wired into this instance"}
    return ctx.pipeline.sweep(now=ctx.now, actor=ctx.actor)


def reconcile_uses(ctx: "JobContext") -> Dict[str, Any]:
    """Compare what each model is approved for against what it is used for.

    Run as a batch because it is a question about a PATTERN, and a pattern is
    not visible at the moment any one call is made — every call this looks at
    was individually authorised, or individually refused, and correctly so.
    """
    if ctx.uses is None:
        return {"count": 0,
                "detail": "no use reconciliation is wired into this instance"}
    return ctx.uses.sweep(now=ctx.now, actor=ctx.actor)


JOBS: Dict[str, Job] = {j.key: j for j in (
    Job("immaterial.conditions",
        "checks every immaterial model against the conditions that would mean "
        "it is no longer immaterial — usage, dependence and the age of its "
        "assessment",
        "proportionality is what makes the expensive controls affordable where "
        "they are needed, and it only works if something notices when a small "
        "model has stopped being small; materiality was declared once and the "
        "declaration goes stale quietly",
        check_immaterial),
    Job("pipelines.check",
        "checks every feature view against its own loading history — "
        "freshness, volume, schema and null rates",
        "most model failures are data failures, and every other monitor here "
        "points at a model's scores, which is the last place the problem shows "
        "up rather than the first",
        check_pipelines),
    Job("uses.reconcile",
        "compares each model's approved uses against the uses actually "
        "exercised, and raises the persistent off-label ones",
        "every call is individually authorised or individually refused, so "
        "off-label use is a PATTERN of good calls and nothing was looking at "
        "the pattern; a use attempted four hundred times and refused every "
        "time reads on a control report as the platform working perfectly",
        reconcile_uses),
    Job("discovery.backlog",
        "reports discovery candidates nobody has triaged",
        "a sweep that runs and is never triaged is worse than no sweep: the "
        "estate believes it has a discovery programme, and what it has is a "
        "table filling up",
        discovery_backlog),
    Job("adaptive.change",
        "raises a finding for a self-changing model that has drifted from the "
        "parameters somebody approved",
        "an adaptive model has no version bump for anything to notice, so "
        "every other control here — all of which fire on a version — is blind "
        "to it moving",
        check_adaptive_change),
    Job("events.deliver",
        "pushes each subscriber's backlog of domain events",
        "delivery on the batch rather than at the act, because a governance "
        "act must not fail because somebody's webhook receiver is down — that "
        "would make an outside system's availability part of this register's "
        "integrity",
        deliver_events),
    Job("inference.expire",
        "deletes inference records past the retention their classification set",
        "this table holds somebody else's personal data, and a retention "
        "period enforced by a column a query could select around is not a "
        "retention period; an instance whose batch stops quietly starts "
        "holding it past the point it decided it could",
        expire_inference),
    Job("idempotency.sweep",
        "drops idempotency records nobody can still be waiting on",
        "the table is a copy of every successful response somebody asked to be "
        "able to retry, and without this it becomes a permanent one",
        sweep_idempotency),
    Job("break_glass.expire",
        "closes every emergency elevation whose window has ended",
        "expiry is derived on every read so the control does not depend on "
        "this running, but a row that still says open three weeks later reads "
        "to anybody looking at the table like an elevation somebody left on",
        expire_break_glass),
    Job("assist.canaries",
        "checks whether the model under each capability's version string moved",
        "a hosted model is re-trained, quantised and rolled forward while the "
        "string it answers to stays the same, and every piece of evidence "
        "about that capability's quality was gathered against the weights it "
        "had then",
        check_base_models),
    Job("assist.injection",
        "scans the register for content shaped like an instruction to a model",
        "detection that only ran when somebody asked for a draft would miss "
        "the row nobody has drafted about yet, which is exactly the row an "
        "attacker would choose because it sits there until the day it is used",
        scan_for_injection),
    Job("lifecycle.stalled",
        "raises a finding for a record that has been mid-move longer than its "
        "tier allows",
        "no control anywhere here watches the clock on a governance queue — "
        "the submission succeeded and every gate passed, so a record sitting "
        "submitted for four months appears on no report at all",
        lifecycle_stalled),
    Job("waivers.expire",
        "closes every control waiver whose window has ended",
        "mandatory expiry is only a control if something acts on the date; a "
        "waiver that expired and that nothing marked expired reads on every "
        "screen exactly like one still in force",
        expire_waivers),
    Job("evidence.anchor",
        "writes the evidence chain head outside the database, and checks the "
        "chain still agrees with every head written before",
        "verification that compares the chain against itself is passed by a "
        "chain that was rewritten; an anchor on a second medium is the only "
        "check an attacker holding the database alone cannot satisfy",
        anchor_evidence_chain),
    Job("evidence.verify",
        "walks the whole evidence chain and moves the verification checkpoint",
        "readiness only checks what arrived since the last full walk, so the "
        "full walk has to be something that happens rather than something "
        "somebody remembers",
        verify_evidence_chain),
    Job("notify.outstanding",
        "tells each person what is outstanding for them",
        "work nobody is told about is work nobody does; the dashboard only "
        "reaches whoever happens to log in",
        notify_outstanding),
    Job("attestation.lapsed",
        "raises a finding for a model in force on a lapsed attestation",
        "a model in force on a lapsed attestation is in force on nobody's "
        "current signature",
        attestation_lapsed),
    Job("review.overdue",
        "raises a finding for a model past the review date its tier set",
        "`next_review_due` was computed from the tier, written to every "
        "assessment, and read by nothing at all — so the cadence that is the "
        "whole reason the engine carries a review map was a column nobody "
        "selected",
        review_overdue),
    Job("monitoring.stalled",
        "raises a finding for a monitor far past its cadence",
        "a monitor that is not running looks exactly like a monitor that is "
        "passing",
        monitoring_stalled),
    Job("overlays.expire",
        "closes overlays whose approved window has elapsed",
        "expiry is computed either way; this makes the register say so",
        expire_overlays),
    Job("debt.reconcile",
        "closes baseline debt whose evidence arrived, expires what is overdue",
        "the burn-down should be a measurement, and a measurement has to be taken",
        reconcile_debt),
    Job("findings.overdue",
        "records that a finding passed its remediation window",
        "missing the window agreed for closing a finding is a different failure "
        "from the finding itself",
        escalate_overdue_findings),
    Job("findings.unacknowledged",
        "records that a finding's owner never accepted it",
        "a finding nobody has agreed to fix looks identical, on every dashboard, "
        "to one somebody is working on",
        unacknowledged_findings),
)}
