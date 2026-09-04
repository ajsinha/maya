"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reading a findings register: ageing, escalation, and the profile a committee asks
for and rarely gets.

Nothing here is stored. Every number is computed from two things the platform
already records — the finding row and the append-only list of acts against it —
which is why there is no status table to disagree with the register, and why a
finding closed by another route cannot leave a stale row behind saying it is
overdue.

Three judgements are made in the open rather than left to whoever is reading.

**Age is a distribution, not a mean.** One finding open for four years and nine
opened last week average to something reassuring. The buckets are the report.

**A finding nobody accepted is not being worked on.** It looks identical on every
dashboard to one that is. Acknowledgement is what tells the two apart, and an
acknowledgement is only current if it came after the last handover — a new owner
has not agreed to the date the last one named.

**Escalation is by role, not by hierarchy.** MAYA does not know who reports to
whom. What it knows is that an overdue, unactioned finding has stopped being one
person's problem, and it says so to a role.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.validation.common import (ACKNOWLEDGED, AGE_BUCKETS, ASSIGNED,
                                    DAY, DEFAULT_ACKNOWLEDGE_DAYS,
                                    DEFAULT_ESCALATE_DAYS,
                                    DEFAULT_EXTENSION_LIMIT, ESCALATION_ROLE,
                                    EXTENDED, PLANNED, SEVERITIES, same_person,
                                    severity_rank)


# --------------------------------------------------------------------- ageing
def age_days(finding: Dict[str, Any], now: float) -> float:
    """How long this has been open. A closed finding stops ageing when it closed."""
    end = finding.get("closed_at") if finding.get("status") == "closed" else None
    return max(0.0, ((end if end is not None else now) - finding["raised_at"]) / DAY)


def days_overdue(finding: Dict[str, Any], now: float) -> float:
    """Days past the date. Zero rather than negative: 'not overdue' is not a
    quantity, and reporting it as one puts a misleading number in a sum."""
    if finding.get("status") == "closed":
        return 0.0
    return max(0.0, (now - finding["due_at"]) / DAY)


def bucket(days: float) -> str:
    for limit, label in AGE_BUCKETS:
        if limit is None or days <= limit:
            return label
    return AGE_BUCKETS[-1][1]


# ------------------------------------------------------------------- the acts
def acts(actions: Sequence[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    return [a for a in actions if a["act"] == kind]


def last(actions: Sequence[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    found = acts(actions, kind)
    return found[-1] if found else None


def owned_since(finding: Dict[str, Any],
                actions: Sequence[Dict[str, Any]]) -> float:
    """When the current owner became the current owner."""
    handover = last(actions, ASSIGNED)
    return handover["acted_at"] if handover else finding["raised_at"]


def acknowledgement(finding: Dict[str, Any],
                    actions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Has the person who owns this now agreed that it is theirs, and by when?

    Deliberately *not* a column. An acknowledgement recorded before the last
    handover was given by somebody who no longer owns the finding, and treating
    it as current is how a reassignment quietly launders an unaccepted date.
    """
    since = owned_since(finding, actions)
    current = [a for a in acts(actions, ACKNOWLEDGED)
               if a["acted_at"] >= since and same_person(a["actor"], finding["owner"])]
    if not current:
        handed = last(actions, ASSIGNED)
        return {
            "acknowledged": False, "by": None, "at": None, "committed_at": None,
            "detail": ("this finding has been reassigned and the new owner has "
                       "not accepted it" if handed else
                       "nobody has accepted this finding as theirs"),
        }
    latest = current[-1]
    return {"acknowledged": True, "by": latest["actor"], "at": latest["acted_at"],
            "committed_at": latest["committed_at"],
            "detail": (f"{latest['actor']} accepted this finding and committed to "
                       f"closing it")}


def plan(actions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """What will be done. The latest wins; every earlier one is still recorded."""
    latest = last(actions, PLANNED)
    if latest is None:
        return {"planned": False, "plan": "", "by": None, "at": None,
                "revisions": 0,
                "detail": "no remediation plan has been recorded"}
    revisions = len(acts(actions, PLANNED))
    return {"planned": True, "plan": latest["plan"], "by": latest["actor"],
            "at": latest["acted_at"], "revisions": revisions,
            "detail": (f"planned by {latest['actor']}"
                       + (f", revised {revisions - 1} time(s)"
                          if revisions > 1 else ""))}


def extensions(actions: Sequence[Dict[str, Any]],
               limit: int = DEFAULT_EXTENSION_LIMIT) -> Dict[str, Any]:
    """How often the date has moved, and by how much in total.

    Counted rather than stored for the same reason everything else here is: a
    counter and a log can disagree, and when they do it is the counter that gets
    believed and the log that is right.
    """
    moved = acts(actions, EXTENDED)
    added = sum(((a["due_after"] or 0) - (a["due_before"] or 0)) / DAY for a in moved)
    over = len(moved) > limit
    return {
        "count": len(moved), "limit": limit, "days_added": round(added, 1),
        "over_limit": over,
        "history": [{"at": a["acted_at"], "by": a["actor"], "reason": a["reason"],
                     "from": a["due_before"], "to": a["due_after"],
                     "days": round(((a["due_after"] or 0) - (a["due_before"] or 0))
                                   / DAY, 1)}
                    for a in moved],
        "detail": (f"extended {len(moved)} time(s) against a limit of {limit}, "
                   f"adding {added:.0f} days; a date moved this often is not a date"
                   if over else
                   f"extended {len(moved)} time(s), within the limit of {limit}"),
    }


# ---------------------------------------------------------------- escalation
def escalation(finding: Dict[str, Any], actions: Sequence[Dict[str, Any]],
               now: float, escalate_days: float = DEFAULT_ESCALATE_DAYS,
               acknowledge_days: float = DEFAULT_ACKNOWLEDGE_DAYS,
               extension_limit: int = DEFAULT_EXTENSION_LIMIT,
               role: str = ESCALATION_ROLE) -> Dict[str, Any]:
    """Whether this finding has stopped being only its owner's problem.

    By role rather than by hierarchy, and computed rather than flagged: an
    escalation that has to be set by somebody is an escalation that happens when
    somebody remembers.
    """
    reasons: List[str] = []
    if finding.get("status") == "closed":
        return {"escalate": False, "to_role": role, "reasons": [],
                "detail": "closed"}
    late = days_overdue(finding, now)
    if late > escalate_days:
        reasons.append(f"{late:.0f} days past its remediation date")
    if finding.get("blocking") and late > 0:
        reasons.append("it is blocking, so the model cannot be served while it "
                       "is open and past its date")
    unaccepted = (now - owned_since(finding, actions)) / DAY
    if (not acknowledgement(finding, actions)["acknowledged"]
            and unaccepted > acknowledge_days):
        reasons.append(f"nobody has accepted it in {unaccepted:.0f} days, so "
                       "there is no evidence anybody is working on it")
    counted = extensions(actions, extension_limit)
    if counted["over_limit"]:
        reasons.append(counted["detail"])
    return {
        "escalate": bool(reasons), "to_role": role, "reasons": reasons,
        "detail": ("; ".join(reasons) + f" — escalated to the {role.replace('_', ' ')}"
                   if reasons else "within its window and accepted by its owner"),
    }


def reading(finding: Dict[str, Any], actions: Sequence[Dict[str, Any]],
            now: float, escalate_days: float = DEFAULT_ESCALATE_DAYS,
            acknowledge_days: float = DEFAULT_ACKNOWLEDGE_DAYS,
            extension_limit: int = DEFAULT_EXTENSION_LIMIT) -> Dict[str, Any]:
    """The whole state of one finding's workflow, entirely derived."""
    age = age_days(finding, now)
    late = days_overdue(finding, now)
    return {
        "finding_id": finding["id"], "owner": finding["owner"],
        "severity": finding["severity"], "status": finding["status"],
        "blocking": bool(finding["blocking"]),
        "age_days": round(age, 1), "age_bucket": bucket(age),
        "due_at": finding["due_at"], "overdue": late > 0,
        "days_overdue": round(late, 1),
        "owned_since": owned_since(finding, actions),
        "acknowledgement": acknowledgement(finding, actions),
        "plan": plan(actions),
        "extensions": extensions(actions, extension_limit),
        "handovers": [{"at": a["acted_at"], "by": a["actor"],
                       "from": a["from_owner"], "to": a["to_owner"],
                       "reason": a["reason"]} for a in acts(actions, ASSIGNED)],
        "escalation": escalation(finding, actions, now, escalate_days,
                                 acknowledge_days, extension_limit),
    }


# ----------------------------------------------------------------- the profile
def profile(findings: Sequence[Dict[str, Any]],
            actions_by_finding: Dict[str, List[Dict[str, Any]]],
            now: float, escalate_days: float = DEFAULT_ESCALATE_DAYS,
            acknowledge_days: float = DEFAULT_ACKNOWLEDGE_DAYS,
            extension_limit: int = DEFAULT_EXTENSION_LIMIT) -> Dict[str, Any]:
    """The ageing profile: what a risk committee asks for about a findings register.

    Not "how many findings" — every bank has that number. How many at each
    severity, how long they have been open, how many are past their date, and
    how many have had that date moved and how often. The last of those is the
    one nobody reports, and it is the one that says whether the remediation
    dates in the pack mean anything at all.
    """
    opened = [f for f in findings if f["status"] != "closed"]
    readings = [reading(f, actions_by_finding.get(f["id"], []), now,
                        escalate_days, acknowledge_days, extension_limit)
                for f in opened]
    closed = [f for f in findings if f["status"] == "closed"]

    by_severity: Dict[str, Dict[str, Any]] = {}
    for severity in SEVERITIES:
        rows = [r for r in readings if r["severity"] == severity]
        if not rows:
            continue
        by_severity[severity] = {
            "open": len(rows),
            "overdue": sum(1 for r in rows if r["overdue"]),
            "unacknowledged": sum(
                1 for r in rows if not r["acknowledgement"]["acknowledged"]),
            "extended": sum(1 for r in rows if r["extensions"]["count"]),
            "oldest_days": max(r["age_days"] for r in rows),
            "mean_age_days": round(sum(r["age_days"] for r in rows) / len(rows), 1),
        }

    by_age: Dict[str, int] = {}
    for _, label in AGE_BUCKETS:
        count = sum(1 for r in readings if r["age_bucket"] == label)
        if count:
            by_age[label] = count

    moved = [r for r in readings if r["extensions"]["count"]]
    overdue = [r for r in readings if r["overdue"]]
    escalated = [r for r in readings if r["escalation"]["escalate"]]
    oldest = max(readings, key=lambda r: r["age_days"], default=None)
    return {
        "open": len(readings), "closed": len(closed),
        "blocking": sum(1 for r in readings if r["blocking"]),
        "overdue": len(overdue),
        "unacknowledged": sum(
            1 for r in readings if not r["acknowledgement"]["acknowledged"]),
        "unplanned": sum(1 for r in readings if not r["plan"]["planned"]),
        "escalated": len(escalated),
        "worst_severity": min((r["severity"] for r in readings),
                              key=severity_rank, default=None),
        "by_severity": by_severity, "by_age": by_age,
        "extended": {
            "findings": len(moved),
            "extensions": sum(r["extensions"]["count"] for r in moved),
            "over_limit": sum(1 for r in moved if r["extensions"]["over_limit"]),
            "days_added": round(sum(r["extensions"]["days_added"] for r in moved), 1),
            "most_extended": max((r["extensions"]["count"] for r in moved),
                                 default=0),
        },
        "mean_age_days": (round(sum(r["age_days"] for r in readings) / len(readings), 1)
                          if readings else 0.0),
        "oldest": ({"finding_id": oldest["finding_id"], "severity": oldest["severity"],
                    "age_days": oldest["age_days"], "owner": oldest["owner"]}
                   if oldest else None),
        "escalations": [{"finding_id": r["finding_id"], "severity": r["severity"],
                         "owner": r["owner"], "to_role": r["escalation"]["to_role"],
                         "reasons": r["escalation"]["reasons"]}
                        for r in escalated],
        "detail": _detail(readings, overdue, moved, escalated),
    }


def _detail(readings, overdue, moved, escalated) -> str:
    if not readings:
        return "nothing is open"
    parts = [f"{len(readings)} open"]
    if overdue:
        parts.append(f"{len(overdue)} past their date")
    if moved:
        total = sum(r["extensions"]["count"] for r in moved)
        parts.append(f"{len(moved)} extended {total} time(s) between them")
    if escalated:
        parts.append(f"{len(escalated)} escalated")
    return ", ".join(parts)
