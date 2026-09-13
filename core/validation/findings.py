"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The findings register — and the reason it is a control rather than a log.

Every model risk framework requires findings to be tracked. Most systems track
them in a table that nothing reads. The difference here is ``blocking``: an open
blocking finding refuses an alias move and refuses warrant resolution, so a model
that failed challenge cannot reach production by any route that does not pass
through this register.

That makes closure consequential, which is the point. Closing a finding needs a
verifier who is not the owner and evidence for what changed — because the
cheapest way to clear a blocking finding is otherwise to mark it closed.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.validation.common import (BLOCKING_BY_DEFAULT, DAY, REMEDIATION_DAYS, SEVERITIES,
                                    SOURCES, ValidationError, same_person, worst)
from db import FindingRepository


class FindingRegister:
    """Raises, tracks and closes findings. Implements ports.BlockingSource."""

    def __init__(self, findings: FindingRepository, evidence: EvidenceEngine):
        self.findings, self.evidence = findings, evidence

    # ------------------------------------------------------------------ raise
    def raise_finding(self, model_id: str, severity: str, title: str, owner: str,
                      description: str = "", category: str = "general",
                      source: str = "validation", model_version_id: Optional[str] = None,
                      validation_id: Optional[str] = None,
                      affected_component: Optional[str] = None,
                      blocking: Optional[bool] = None, due_at: Optional[float] = None,
                      actor: str = "system") -> Dict[str, Any]:
        if severity not in SEVERITIES:
            raise ValidationError(f"unknown severity '{severity}'; "
                                  f"expected one of {', '.join(SEVERITIES)}")
        if source not in SOURCES:
            raise ValidationError(f"unknown finding source '{source}'; "
                                  f"expected one of {', '.join(SOURCES)}")
        if not owner:
            raise ValidationError("a finding with no owner is a finding nobody will fix")
        # And a finding with no TITLE is a row in a worklist that says nothing
        # about what is wrong.
        #
        # `owner` was checked and `title` was not, and the title is the only
        # part of a finding that appears in a digest, a worklist and a board
        # pack. `"   "` was accepted, so somebody could be assigned a blocking
        # finding whose entire description of the problem is three spaces.
        #
        # Stripped, not merely truthy: `not "   "` is False, which is exactly
        # how the blank ones got through everywhere else this pass found them.
        if not (title or "").strip():
            raise ValidationError(
                "a finding with no title is a row in a worklist that says "
                "nothing about what is wrong; the title is the only part that "
                "reaches a digest or a board pack")
        now = time.time()
        row = {"model_id": model_id, "model_version_id": model_version_id,
               "validation_id": validation_id, "source": source, "severity": severity,
               "category": category, "title": title, "description": description,
               "affected_component": affected_component,
               "blocking": int(blocking if blocking is not None
                               else severity in BLOCKING_BY_DEFAULT),
               "owner": owner, "raised_at": now,
               "due_at": due_at or now + REMEDIATION_DAYS[severity] * DAY,
               "status": "open", "closed_at": None, "closure_verified_by": None,
               "closure_evidence": {}}
        with self.evidence.recording():
            self.findings.add(row)
            self.evidence.append("finding_raised", "model", model_id,
                                 {"finding_id": row["id"], "severity": severity,
                                  "title": title, "blocking": bool(row["blocking"])}, actor=actor)
        return self.findings.one(id=row["id"])

    # ------------------------------------------------------------------ close
    def close(self, finding_id: str, verified_by: str, evidence: Dict[str, Any],
              actor: str = "system") -> Dict[str, Any]:
        """Close a finding. The verifier may not be its owner.

        Segregation here is not ceremony. A blocking finding is the only thing
        standing between a failed model and production, and the person who owns
        the remediation is the person with the strongest reason to declare it
        done.
        """
        row = self.require(finding_id)
        if row["status"] == "closed":
            raise ValidationError(f"finding {finding_id} is already closed")
        if not verified_by:
            raise ValidationError("closing a finding requires a verifier")
        if same_person(verified_by, row["owner"]):
            # Compared as identities rather than as strings. The platform writes
            # an owner as `person/j.okafor` and authenticates the same human as
            # `j.okafor`, so a `==` here was a duties check anybody could step
            # around by dropping the prefix.
            raise ValidationError(
                f"'{verified_by}' owns this finding and cannot verify its own closure; "
                "closure must be attested by someone else")
        if not evidence:
            raise ValidationError(
                "closing a finding requires closure evidence describing what changed")
        now = time.time()
        with self.evidence.recording():
            self.findings.set({"status": "closed", "closed_at": now,
                               "closure_verified_by": verified_by,
                               "closure_evidence": evidence}, id=finding_id)
            self.evidence.append("finding_closed", "model", row["model_id"],
                                 {"finding_id": finding_id, "verified_by": verified_by,
                                  "was_blocking": bool(row["blocking"])}, actor=actor)
        return self.findings.one(id=finding_id)

    def set_status(self, finding_id: str, status: str, actor: str = "system") -> Dict[str, Any]:
        """Move a finding along without closing it. Closure has its own path."""
        if status == "closed":
            raise ValidationError("use close() — closure needs a verifier and evidence")
        row = self.require(finding_id)
        with self.evidence.recording():
            self.findings.set({"status": status}, id=finding_id)
            self.evidence.append("finding_status_changed", "model", row["model_id"],
                                 {"finding_id": finding_id, "status": status}, actor=actor)
        return self.findings.one(id=finding_id)

    # ------------------------------------------------------------------ query
    def get(self, finding_id: str) -> Optional[Dict[str, Any]]:
        return self.findings.one(id=finding_id)

    def require(self, finding_id: str) -> Dict[str, Any]:
        row = self.get(finding_id)
        if not row:
            raise ValidationError(f"no finding {finding_id}")
        return row

    def open_for(self, model_id: str) -> List[Dict[str, Any]]:
        return self.findings.open_for(model_id)

    def open_across(self, model_ids: Sequence[str]) -> List[Dict[str, Any]]:
        """Every open finding across the models the caller may see.

        The estate-wide question. There was no route to it: `open_for` takes one
        model and the API demanded a `urn`, so "what is outstanding across the
        register" could not be answered by the product at all — which is a
        strange gap in a platform whose worklist tells somebody they are clear.
        """
        return self.findings.open_across(model_ids)

    def blocking_for(self, model_id: str) -> List[Dict[str, Any]]:
        """The BlockingSource port. Open findings that block."""
        return self.findings.open_for(model_id, blocking=True)

    def overdue(self, model_id: str, now: Optional[float] = None) -> List[Dict[str, Any]]:
        moment = now if now is not None else time.time()
        return [f for f in self.open_for(model_id) if f["due_at"] < moment]

    def summary(self, model_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        """What an inventory row needs to show about a model's open issues."""
        opened = self.open_for(model_id)
        blocking = [f for f in opened if f["blocking"]]
        return {"open": len(opened), "blocking": len(blocking),
                "overdue": len(self.overdue(model_id, now)),
                "worst_severity": worst([f["severity"] for f in opened]) if opened else None,
                "by_severity": {s: sum(f["severity"] == s for f in opened)
                                for s in SEVERITIES if any(f["severity"] == s for f in opened)}}
