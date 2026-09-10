"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Matters raised by a supervisor, and the two dates that are not the same date.

An MRA, an MRIA, a s166 finding: these look like findings and are not, in two
structural ways that every register that stores them as findings gets wrong.

**A supervisory matter is not about one model.** Every finding in this platform
hangs off a model, and a thematic MRA about model documentation reaches forty at
once. Filing it against one of them makes the other thirty-nine invisible; filing
it forty times makes it forty matters, and the firm then reports forty remediation
programmes to a supervisor who raised one. So a matter is its own object with a
**scope**, and the findings under it are derived from that scope. Closing them
one by one is real work; closing the *matter* is a separate act that requires all
of it.

**And it carries two dates.** Every finding here already has an internal
remediation date derived from severity. A supervisory matter *also* has the date
**the firm gave the supervisor** — a commitment made in a letter, by a person,
often before anybody costed the work. These are different objects and conflating
them is how a firm discovers, on the day, that its internal plan runs past its
regulatory commitment. Both are held, the gap is computed, and a matter whose
findings are now due after its committed date is reported **at risk** —
arithmetic, not judgement, and available months before the letter is due.

**A matter cannot be closed while a finding under it is open.** Telling a
supervisor something is done when it is not is the failure this shape exists to
prevent, and it is a failure of bookkeeping rather than of intent: somebody
closes the programme in one system while two remediations are still running in
another. Here there is one system.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.validation.common import SEVERITIES, ValidationError

logger = get_logger(__name__)

DAY = 86400.0

#: What a supervisor raised, and how hard it binds. Held as data so a firm can
#: read the ladder rather than infer it from a severity.
KINDS: Dict[str, str] = {
    "mria": "Matter Requiring Immediate Attention — the supervisor considers "
            "this a deficiency in a core process, and the remediation date is "
            "not negotiable",
    "mra": "Matter Requiring Attention — a deficiency the firm is expected to "
           "correct, with a date the firm proposes and the supervisor accepts",
    "s166": "a skilled person review under s166 FSMA, whose report the firm "
            "does not control and whose findings arrive as a set",
    "recommendation": "advice the supervisor expects to see considered; not "
                      "binding, and a firm that declines one should be able to "
                      "say why in writing",
    "self_reported": "the firm told the supervisor. Tracked identically, "
                     "because a commitment made voluntarily is still a "
                     "commitment made",
}

OPEN, CLOSED = "open", "closed"
STATUSES = (OPEN, CLOSED)

#: How far ahead of a committed date the internal plan has to finish before the
#: matter stops being reported at risk. A plan landing on the day it is due has
#: no room for the closure verification the firm's own process requires.
HEADROOM_DAYS = 14.0


class SupervisoryMatters:
    """Matters a supervisor raised, the findings under them, and the two dates."""

    def __init__(self, matters, registry, findings, evidence):
        self.matters, self.registry = matters, registry
        self.findings, self.evidence = findings, evidence

    # ------------------------------------------------------------------ raise
    def raise_matter(self, reference: str, *, kind: str, supervisor: str,
                     title: str, scope: Sequence[str], owner: str,
                     description: str = "", examination: str = "",
                     severity: str = "High",
                     committed_at: Optional[float] = None,
                     now: Optional[float] = None,
                     actor: str = "system") -> Dict[str, Any]:
        """Record a matter and raise one finding against each model in scope."""
        if kind not in KINDS:
            raise ValidationError(
                f"'{kind}' is not a kind of supervisory matter; the five are "
                + ", ".join(KINDS))
        if severity not in SEVERITIES:
            raise ValidationError(
                f"'{severity}' is not a severity; the five are "
                + ", ".join(SEVERITIES))
        if not (reference or "").strip():
            raise ValidationError(
                "a supervisory matter needs the supervisor's own reference — "
                "it is how the firm and the supervisor talk about the same "
                "thing, and a matter tracked under an internal id only is one "
                "nobody can reconcile against the letter")
        if self.matters.one(reference=reference):
            raise ValidationError(
                f"matter '{reference}' is already recorded; a second row under "
                f"one reference is how a firm ends up reporting two remediation "
                f"programmes for one letter")
        if not scope:
            raise ValidationError(
                "a matter with no models in scope has nothing to remediate. If "
                "the supervisor's point is about a process rather than a model, "
                "name the models the process governs — that is what makes it "
                "trackable")

        moment = now if now is not None else time.time()
        models = [self.registry.require(urn) for urn in scope]
        row = {
            "reference": reference.strip(), "kind": kind,
            "supervisor": supervisor, "examination": examination,
            "title": title, "description": description, "severity": severity,
            "scope": [m["urn"] for m in models], "owner": owner,
            "raised_at": moment, "committed_at": committed_at,
            "status": OPEN, "closed_at": None, "closure_note": "",
            "closed_by": None,
        }
        self.matters.add(row)
        for model in models:
            self.findings.raise_finding(
                model["id"], severity, f"[{reference}] {title}", owner,
                description=(f"{description}\n\nRaised by {supervisor} as a "
                             f"{kind.upper()} under matter {reference}."
                             ).strip(),
                category="supervisory", source="regulator",
                blocking=(kind == "mria"), actor=actor)
        with self.evidence.recording():
            self.evidence.append(
                "supervisory_matter_raised", "supervisory_matter", row["id"],
                {"reference": reference, "kind": kind, "supervisor": supervisor,
                 "models": len(models), "severity": severity,
                 "committed_at": committed_at}, actor=actor)
        logger.info("supervisory matter %s (%s) raised by %s over %d model(s)",
                    reference, kind, supervisor, len(models))
        return self.status(reference, now=moment)

    # ------------------------------------------------------------------ close
    def close(self, reference: str, note: str, actor: str = "system",
              now: Optional[float] = None) -> Dict[str, Any]:
        """Close a matter. Refused while anything under it is open."""
        matter = self.require(reference)
        if matter["status"] == CLOSED:
            raise ValidationError(f"matter '{reference}' is already closed")
        if not (note or "").strip():
            raise ValidationError(
                "closing a supervisory matter needs a note saying what was "
                "done — it is the sentence that goes back to the supervisor, "
                "and writing it at closure is easier than reconstructing it "
                "next year")
        moment = now if now is not None else time.time()
        state = self.status(reference, now=moment)
        if state["open_findings"]:
            raise ValidationError(
                f"{state['open_findings']} finding(s) under {reference} are "
                f"still open, so this matter is not remediated. Telling a "
                f"supervisor something is done when it is not is a failure of "
                f"bookkeeping rather than of intent — somebody closes the "
                f"programme in one system while two remediations run in "
                f"another, and this is the one system")
        with self.evidence.recording():
            self.matters.set({"status": CLOSED, "closed_at": moment,
                              "closure_note": note.strip(),
                              "closed_by": actor}, id=matter["id"])
            self.evidence.append(
                "supervisory_matter_closed", "supervisory_matter",
                matter["id"],
                {"reference": reference, "note": note.strip(),
                 "days_open": round((moment - matter["raised_at"]) / DAY, 1),
                 "committed_at": matter.get("committed_at"),
                 "met_commitment": (matter.get("committed_at") is None
                                    or moment <= matter["committed_at"])},
                actor=actor)
        logger.info("supervisory matter %s closed by %s", reference, actor)
        return self.status(reference, now=moment)

    # ----------------------------------------------------------------- status
    def status(self, reference: str,
               now: Optional[float] = None) -> Dict[str, Any]:
        """Where a matter stands, derived from the findings under it."""
        matter = self.require(reference)
        moment = now if now is not None else time.time()
        findings = self._findings_for(matter)
        opened = [f for f in findings if f["status"] != "closed"]
        latest_due = max((f["due_at"] for f in opened), default=None)
        committed = matter.get("committed_at")
        at_risk, why = self._risk(opened, latest_due, committed, moment,
                                  matter["status"])
        return {
            **matter,
            "findings": findings,
            "open_findings": len(opened),
            "closed_findings": len(findings) - len(opened),
            "latest_internal_due": latest_due,
            "days_between_plan_and_commitment": (
                round((committed - latest_due) / DAY, 1)
                if committed and latest_due else None),
            "at_risk": at_risk,
            "detail": why,
        }

    @staticmethod
    def _risk(opened, latest_due, committed, moment, status):
        """Whether the internal plan will finish before the letter is due."""
        if status == CLOSED:
            return False, "this matter is closed"
        # Nothing open comes FIRST. Asked in the other order, a fully
        # remediated matter with no recorded commitment reported the missing
        # commitment as its headline — which is true and is not the thing to
        # say about a matter whose work is done.
        if not opened:
            return False, ("every finding under this matter is closed; the "
                           "matter itself is still open and closing it is a "
                           "separate act, which is the point")
        if committed is None:
            return False, (
                f"{len(opened)} finding(s) open and no date has been committed "
                f"to the supervisor. That is not the same as having time: it "
                f"means the commitment is not recorded here, and the gap "
                f"between the plan and the letter cannot be computed")
        if latest_due is None:
            return True, "an open finding under this matter carries no date"
        slack = (committed - latest_due) / DAY
        if slack < HEADROOM_DAYS:
            return True, (
                f"the last remediation under this matter is due "
                f"{_when(latest_due)} and the firm committed to "
                f"{_when(committed)} — {slack:.0f} day(s) apart, inside the "
                f"{HEADROOM_DAYS:.0f} days closure verification needs. A plan "
                f"landing on the day it is due has no room for the firm's own "
                f"process, and this is arithmetic available months before the "
                f"letter is")
        return False, (
            f"{len(opened)} finding(s) open, the last due {_when(latest_due)}, "
            f"{slack:.0f} day(s) ahead of the {_when(committed)} committed to "
            f"the supervisor")

    def _findings_for(self, matter: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The findings this matter raised, by the reference in their title."""
        marker = f"[{matter['reference']}]"
        out = []
        for urn in matter["scope"]:
            model = self.registry.get(urn)
            if not model:
                continue
            out += [{**f, "urn": urn}
                    for f in self.findings.findings.many(model_id=model["id"])
                    if (f.get("title") or "").startswith(marker)]
        return out

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.matters.one(reference=reference)
        if not row:
            raise ValidationError(f"no supervisory matter '{reference}'")
        return row

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every matter, at-risk first, with the two dates side by side."""
        moment = now if now is not None else time.time()
        rows = [self.status(m["reference"], now=moment)
                for m in self.matters.many()]
        rows.sort(key=lambda r: (not r["at_risk"],
                                 r.get("committed_at") or float("inf")))
        at_risk = [r for r in rows if r["at_risk"]]
        uncommitted = [r for r in rows
                       if r["status"] == OPEN and not r.get("committed_at")]
        by_kind: Dict[str, int] = {}
        for row in rows:
            if row["status"] == OPEN:
                by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        return {
            "matters": rows, "count": len(rows),
            "open": sum(1 for r in rows if r["status"] == OPEN),
            "at_risk": len(at_risk), "by_kind": by_kind,
            "no_committed_date": [r["reference"] for r in uncommitted],
            "models_in_scope": sorted({urn for r in rows for urn in r["scope"]}),
            "detail": self._estate_detail(rows, at_risk, uncommitted, by_kind),
        }

    @staticmethod
    def _estate_detail(rows, at_risk, uncommitted, by_kind) -> str:
        if not rows:
            return ("no supervisory matter is recorded. Worth reading as a fact "
                    "about what has been entered rather than about what has "
                    "been raised")
        out = (f"{sum(1 for r in rows if r['status'] == OPEN)} open matter(s)"
               + (": " + ", ".join(f"{n} {k}" for k, n in sorted(by_kind.items()))
                  if by_kind else ""))
        if at_risk:
            out += (f". {len(at_risk)} will not finish in time for the date "
                    f"committed to the supervisor — computed from the "
                    f"remediation dates already on the findings, and available "
                    f"now rather than on the day")
        if uncommitted:
            out += (f". {len(uncommitted)} carry no committed date at all, so "
                    f"nothing can say whether their plan is late. An absent "
                    f"commitment reads on every screen exactly like a distant "
                    f"one")
        return out

    @staticmethod
    def kinds() -> Dict[str, Any]:
        return {"kinds": [{"kind": k, "means": v} for k, v in KINDS.items()],
                "headroom_days": HEADROOM_DAYS,
                "detail": ("a supervisory matter carries two dates: the "
                           "internal remediation date every finding derives "
                           "from its severity, and the date the FIRM GAVE THE "
                           "SUPERVISOR. Conflating them is how a firm discovers "
                           "on the day that its plan ran past its commitment")}


def _when(stamp: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(stamp)) if stamp else "unknown"
