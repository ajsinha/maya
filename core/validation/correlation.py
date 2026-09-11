"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

One cause, and the findings it produced.

## The finding, and where it was answered before

**M-8**, *notification storms*. A shared upstream failure — a feature view that
stopped landing, a vendor whose model reversioned, a snapshot that was restated
— raises one finding per monitor per model. Twelve models on one curve produce
twelve findings with twelve owners, and each owner sees a problem they cannot
fix.

That was answered honestly and at the wrong layer: suppression at the last hop,
one digest per person per run, an unchanged worklist held back. The storm was
damped **where it reached a person** rather than where it was generated, and
`docs/11` says so in those words.

Damping at delivery leaves a cost the honest answer did not remove. The findings
are still twelve independent facts about twelve models. Closing the upstream
cause closes none of them. The ageing report counts twelve overdue items. The
board pack shows twelve open findings in one domain, which reads as twelve
problems — the committee then asks about the wrong thing, and the person who
knows it is one problem is not in the room.

## What this adds, and the three things it refuses to do

A **root**: a cause, named once, with the findings it produced hanging off it.

**It does not merge them.** Each finding stays a finding, keeps its own owner,
its own model and its own due date. That is not a limitation. A model whose
feature stopped landing has a real problem whatever caused it, and dissolving
twelve findings into one would leave eleven models with a live defect and
nothing in their own record saying so. What changes is that all twelve now say
*this is why*, and the estate can be counted by cause as well as by symptom.

**Correlation is asserted, never inferred.** This platform could guess — same
category, same window, same upstream feature — and a guess that grouped two
unrelated findings would hide one behind the other's closure. So somebody names
the root, and the naming goes on the evidence chain with their name on it.
`candidates()` *suggests*, which is a different act: it proposes, and nothing is
grouped until a person says so.

**And addressing a root closes nothing.** It records that the cause was dealt
with; each finding still needs its own closure with its own verifier, because
the point of a finding is that somebody checked *this model* is all right again.
A root that closed its children would be one act discharging obligations that
several different people owe.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger
from core.validation.common import FindingWorkflowError

logger = get_logger(__name__)

#: What a root has to say about itself. A cause with no description is a
#: grouping, and a grouping nobody can read is a way of hiding findings.
REQUIRED: Tuple[Tuple[str, str], ...] = (
    ("title", "what the cause IS, in one line. It appears on every finding "
              "that hangs off it and on the board pack"),
    ("kind", "what sort of cause. The estate view counts by this, and a "
             "programme with forty upstream-data roots has a different "
             "problem from one with forty vendor-change roots"),
    ("detail", "enough that somebody who did not raise it can act"),
)

#: The kinds of cause worth telling apart. A closed list, because a dimension
#: the estate view counts by has to be countable — and free text is how a
#: taxonomy becomes forty spellings of the same word.
KINDS: Tuple[Tuple[str, str], ...] = (
    ("upstream_data", "a feature view, a source or a snapshot stopped being "
                      "what its consumers relied on"),
    ("vendor_change", "somebody else's model or data moved under a version "
                      "this firm had approved"),
    ("platform", "an outage, a migration or a defect in the platform itself"),
    ("population_shift", "the world changed, and several models noticed at "
                         "once"),
    ("control_gap", "a control that should have caught something earlier did "
                    "not, and its absence shows up in several places"),
)

OPEN, ADDRESSED = "open", "addressed"


class FindingRoots:
    """Names a shared cause, and hangs findings off it. Merges nothing."""

    def __init__(self, roots, findings, evidence=None):
        self.roots, self.findings, self.evidence = roots, findings, evidence

    # --------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What a root is, and the three things it is not."""
        return {
            "merges_findings": False,
            "infers_correlation": False,
            "closing_a_root_closes_findings": False,
            "kinds": [{"kind": k, "means": m} for k, m in KINDS],
            "why_not_merge": (
                "a model whose feature stopped landing has a real problem "
                "whatever caused it. Dissolving twelve findings into one "
                "leaves eleven models with a live defect and nothing in their "
                "own record saying so"),
            "why_not_infer": (
                "a guess that grouped two unrelated findings would hide one "
                "behind the other's closure. Somebody names the root, and the "
                "naming goes on the evidence chain with their name on it. The "
                "register suggests CANDIDATES, which is a different act"),
            "why_addressing_closes_nothing": (
                "a root records that the cause was dealt with. Each finding "
                "still needs its own closure with its own verifier, because "
                "the point of a finding is that somebody checked THIS MODEL "
                "is all right again — a root that closed its children would "
                "be one act discharging obligations several different people "
                "owe"),
            "what_it_changes": (
                "suppression damped the storm where it reached a person. This "
                "damps it where it is COUNTED: the estate can be read by "
                "cause as well as by symptom, so a board pack showing twelve "
                "open findings in one domain can say they are one problem"),
        }

    # ----------------------------------------------------------------- naming
    def open_root(self, *, title: str, kind: str, detail: str,
                  findings: Optional[Sequence[str]] = None,
                  actor: str = "system",
                  now: Optional[float] = None) -> Dict[str, Any]:
        """Name a cause, and optionally attach the findings it produced."""
        known = {k for k, _ in KINDS}
        if kind not in known:
            raise FindingWorkflowError(
                "unknown_root_kind",
                f"'{kind}' is not a kind of cause this counts",
                f"the kinds are {', '.join(sorted(known))}. They are a closed "
                f"list because the estate view counts by them, and free text "
                f"is how a taxonomy becomes forty spellings of one word")
        why = dict(REQUIRED)
        if not str(title).strip():
            raise FindingWorkflowError("root_title_required",
                                       "the cause has no title", why["title"])
        if not str(detail).strip():
            raise FindingWorkflowError(
                "root_detail_required", "the cause is not described",
                why["detail"] + ". A cause with no description is a grouping, "
                "and a grouping nobody can read is a way of hiding findings")
        moment = now if now is not None else time.time()
        row: Dict[str, Any] = {
            "title": title.strip(), "kind": kind, "detail": detail.strip(),
            "status": OPEN, "opened_by": actor, "opened_at": moment,
            "addressed_at": None, "addressed_by": "", "addressed_note": ""}
        self.roots.add(row)
        root_id = str(row["id"])
        attached: Dict[str, Any] = (
            self.attach(root_id, findings, actor=actor, now=moment)
            if findings else {"attached": []})
        if self.evidence is not None:
            self.evidence.append(
                "finding_root_opened", "finding_root", row["id"],
                {"title": row["title"], "kind": kind,
                 "findings": list(attached["attached"])}, actor=actor)
        logger.info("root '%s' (%s) opened over %d finding(s)", row["title"],
                    kind, len(attached["attached"]))
        return {**row, **attached, "merged_anything": False,
                "detail_note": (
                    f"'{row['title']}' names a cause. The "
                    f"{len(attached['attached'])} finding(s) under it keep "
                    f"their own owners, models and due dates — nothing was "
                    f"merged, because a model whose feature stopped landing "
                    f"has a real problem whatever caused it")}

    def attach(self, root_id: str, finding_ids: Sequence[str], *,
               actor: str = "system",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Hang findings off a named cause. Asserted, never inferred."""
        root = self.require(root_id)
        moment = now if now is not None else time.time()
        # Every id is resolved BEFORE anything is written. A root that silently
        # covers fewer findings than somebody listed is a root somebody will
        # rely on, so the whole call is refused rather than part of it.
        resolved: List[Dict[str, Any]] = []
        missing: List[str] = []
        for finding_id in finding_ids:
            finding = self.findings.one(id=finding_id)
            if finding is None:
                missing.append(str(finding_id))
            else:
                resolved.append(finding)
        if missing:
            raise FindingWorkflowError(
                "unknown_finding",
                f"{len(missing)} of these are not findings: "
                + ", ".join(missing[:5]),
                "attach findings that exist. Nothing was attached — the whole "
                "call is refused rather than part of it, because a root that "
                "silently covers fewer findings than somebody listed is a "
                "root somebody will rely on")
        attached: List[str] = []
        already: List[str] = []
        for finding in resolved:
            if finding.get("root_id") == root_id:
                already.append(finding["id"])
                continue
            self.findings.set({"root_id": root_id}, id=finding["id"])
            attached.append(finding["id"])
        if self.evidence is not None and attached:
            self.evidence.append(
                "findings_correlated", "finding_root", root_id,
                {"attached": attached, "root": root["title"]}, actor=actor)
        return {"root_id": root_id, "attached": attached,
                "already_attached": already, "at": moment,
                "merged_anything": False}

    # ---------------------------------------------------------------- reading
    def require(self, root_id: str) -> Dict[str, Any]:
        root: Optional[Dict[str, Any]] = self.roots.one(id=root_id)
        if root is None:
            raise FindingWorkflowError(
                "unknown_root", f"there is no root '{root_id}'",
                "list the open roots, or name a cause of your own")
        return root

    def of(self, root_id: str) -> Dict[str, Any]:
        """One cause, and everything hanging off it."""
        root = self.require(root_id)
        children = self.findings.many(root_id=root_id)
        open_children = [f for f in children if f.get("status") == "open"]
        owners = {f.get("owner", "") for f in children if f.get("owner")}
        return {
            **root, "findings": children, "open": len(open_children),
            "models": len({f.get("model_id") for f in children}),
            "owners": sorted(owners),
            "detail": (
                f"{len(children)} finding(s) across "
                f"{len({f.get('model_id') for f in children})} model(s) share "
                f"this cause, {len(open_children)} still open"
                + (f", owned by {len(owners)} different people — which is what "
                   f"makes a shared cause hard: each owner sees a problem they "
                   f"cannot fix" if len(owners) > 1 else "")),
        }

    def across_the_estate(self) -> Dict[str, Any]:
        """Causes rather than symptoms. The view this exists for."""
        rows = []
        for root in self.roots.many():
            children = self.findings.many(root_id=root["id"])
            rows.append({
                "id": root["id"], "title": root["title"],
                "kind": root["kind"], "status": root["status"],
                "findings": len(children),
                "open": sum(1 for f in children if f.get("status") == "open"),
                "models": len({f.get("model_id") for f in children}),
            })
        rows.sort(key=lambda r: -r["open"])
        by_kind: Dict[str, int] = {}
        for row in rows:
            by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        correlated = sum(r["findings"] for r in rows)
        return {
            "roots": rows, "count": len(rows), "by_kind": by_kind,
            "findings_correlated": correlated,
            "detail": (
                f"{len(rows)} named cause(s) account for {correlated} "
                f"finding(s)"
                + (f". The commonest kind is "
                   f"{max(by_kind, key=lambda k: by_kind[k])}" if by_kind
                   else "")
                + ". Counting causes rather than symptoms is the point: a "
                  "board pack showing twelve open findings in one domain "
                  "reads as twelve problems, and the committee asks about the "
                  "wrong thing"),
        }

    # ------------------------------------------------------------- candidates
    def candidates(self, window_hours: float = 24.0,
                   now: Optional[float] = None) -> Dict[str, Any]:
        """Findings that MIGHT share a cause. A suggestion, never a grouping.

        Same source, same category, raised inside one window, across more than
        one model. That is a weak signal and it is meant to be: this proposes,
        and nothing is grouped until a person says so. A platform that grouped
        on it would eventually hide one finding behind another's closure.
        """
        moment = now if now is not None else time.time()
        since = moment - window_hours * 3600.0
        loose = [f for f in self.findings.many(status="open")
                 if (f.get("raised_at") or 0) >= since and not f.get("root_id")]
        groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for finding in loose:
            groups.setdefault(
                (finding.get("source", ""), finding.get("category", "")),
                []).append(finding)
        suggestions: List[Dict[str, Any]] = []
        for (source, category), members in groups.items():
            models = {m.get("model_id") for m in members}
            if len(models) < 2:
                continue
            suggestions.append({
                "source": source, "category": category,
                "findings": [m["id"] for m in members],
                "count": len(members), "models": len(models),
                "why": (f"{len(members)} open finding(s) from '{source}' in "
                        f"category '{category}' across {len(models)} model(s), "
                        f"raised within {window_hours:g}h of each other"),
            })
        # Keyed on the count rather than on `len(s["findings"])` so the sort
        # does not depend on the dict's value type being Sized.
        suggestions.sort(key=lambda s: -int(s["count"]))
        return {
            "window_hours": window_hours, "suggestions": suggestions,
            "groups_anything": False,
            "detail": (
                f"{len(suggestions)} group(s) of open findings share a source "
                f"and a category across several models. **This is a "
                f"suggestion and nothing has been grouped.** The signal is "
                f"deliberately weak — a platform that grouped on it would "
                f"eventually hide one finding behind another's closure, and a "
                f"correlation nobody asserted is one nobody can be asked about"
                if suggestions else
                "no group of open findings shares a source and a category "
                "across more than one model in this window"),
        }

    # -------------------------------------------------------------- resolving
    def address(self, root_id: str, note: str, *, actor: str = "system",
                now: Optional[float] = None) -> Dict[str, Any]:
        """Record that the cause was dealt with. Closes no finding."""
        root = self.require(root_id)
        if root["status"] == ADDRESSED:
            raise FindingWorkflowError(
                "root_already_addressed",
                f"'{root['title']}' was already addressed",
                "the cause is recorded as dealt with. The findings under it "
                "close individually, each with its own verifier")
        if not str(note).strip():
            raise FindingWorkflowError(
                "root_note_required", "no note was given",
                "say what was done. A cause marked addressed with no account "
                "of how is a row that will be read as an all-clear")
        moment = now if now is not None else time.time()
        self.roots.set({"status": ADDRESSED, "addressed_at": moment,
                        "addressed_by": actor,
                        "addressed_note": note.strip()}, id=root_id)
        children = self.findings.many(root_id=root_id)
        still_open = [f["id"] for f in children if f.get("status") == "open"]
        if self.evidence is not None:
            self.evidence.append(
                "finding_root_addressed", "finding_root", root_id,
                {"note": note.strip(), "still_open": still_open}, actor=actor)
        return {
            "root_id": root_id, "status": ADDRESSED, "findings_closed": 0,
            "still_open": still_open,
            "detail": (
                f"the cause is recorded as addressed. **{len(still_open)} "
                f"finding(s) under it are still open and none was closed by "
                f"this.** Each needs its own closure with its own verifier, "
                f"because the point of a finding is that somebody checked "
                f"THIS MODEL is all right again — a root that closed its "
                f"children would be one act discharging obligations that "
                f"several different people owe"),
        }
