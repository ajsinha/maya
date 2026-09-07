"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Amendments: the only way to change an attested model.

An attested record is immutable. That is not obstruction — it is what makes the
record mean something, because "this is the model" and "this is what we said
about the model" are the same document only while nobody can edit one of them
quietly.

So change is a **declared act**. Opening an amendment states what is being
changed and why, returns the record to a mutable state, and creates an
obligation: the amendment must itself be submitted, approved and attested before
the model is back in force. Nothing is lost and nothing is edited in place; the
amendment is a record of its own.

One amendment is open at a time, per model. Two concurrent amendments to the
same record produce a document nobody can reconstruct.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.lifecycle.common import LifecycleError
from core.log import get_logger
from db import AmendmentRepository

logger = get_logger(__name__)


class AmendmentService:
    """Opens, tracks and closes amendments against attested models."""

    def __init__(self, amendments: AmendmentRepository, evidence: EvidenceEngine):
        self.amendments, self.evidence = amendments, evidence

    def open(self, model_id: str, reason: str, scope: Optional[Sequence[str]] = None,
             actor: str = "system") -> Dict[str, Any]:
        if not reason.strip():
            raise LifecycleError(
                "reason_required",
                "an amendment must say what is being changed and why",
                "supply a reason; it becomes part of the attestation record")
        if self.current(model_id):
            raise LifecycleError(
                "amendment_open",
                "an amendment is already open for this model",
                "complete or withdraw the open amendment before opening another")
        row = {"model_id": model_id, "reference": self._reference(model_id),
               "reason": reason, "scope": list(scope or []), "status": "open",
               "opened_by": actor, "opened_at": time.time(),
               "closed_at": None, "closed_by": None}
        with self.evidence.recording():
            self.amendments.add(row)
            self.evidence.append("amendment_opened", "model", model_id,
                                 {"amendment_id": row["id"], "reference": row["reference"],
                                  "reason": reason, "scope": row["scope"]}, actor=actor)
        logger.info("amendment %s opened against model %s", row["reference"], model_id)
        return self.amendments.one(id=row["id"])

    def _reference(self, model_id: str) -> str:
        """A short, human reference. Amendments get quoted in minutes."""
        return f"AMD-{len(self.amendments.many(model_id=model_id)) + 1:03d}"

    def mark(self, amendment_id: str, status: str, actor: str = "system") -> Dict[str, Any]:
        row = self.require(amendment_id)
        closing = status in ("attested", "withdrawn")
        with self.evidence.recording():
            self.amendments.set(
                {"status": status,
                 **({"closed_at": time.time(), "closed_by": actor} if closing else {})},
                id=amendment_id)
            self.evidence.append(f"amendment_{status}", "model", row["model_id"],
                                 {"amendment_id": amendment_id,
                                  "reference": row["reference"]}, actor=actor)
        return self.amendments.one(id=amendment_id)

    def withdraw(self, model_id: str, actor: str = "system") -> Optional[Dict[str, Any]]:
        """Abandon the open amendment. The record of it stays."""
        open_one = self.current(model_id)
        return self.mark(open_one["id"], "withdrawn", actor) if open_one else None

    # ----------------------------------------------------------------- query
    def get(self, amendment_id: str) -> Optional[Dict[str, Any]]:
        return self.amendments.one(id=amendment_id)

    def require(self, amendment_id: str) -> Dict[str, Any]:
        row = self.get(amendment_id)
        if row is None:
            raise LifecycleError("no_amendment", f"no amendment {amendment_id}", "")
        return row

    def current(self, model_id: str) -> Optional[Dict[str, Any]]:
        """The amendment still in flight, if any."""
        for row in self.amendments.many(model_id=model_id):
            if row["status"] in ("open", "submitted"):
                return row
        return None

    def history(self, model_id: str) -> List[Dict[str, Any]]:
        return self.amendments.many(model_id=model_id)
