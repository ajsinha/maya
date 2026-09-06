"""
MAYA — the facts a gate judges on, gathered from the registers that hold them.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A gate publishes the facts a policy may be written against. Four call sites
supplied between them twenty-two of the thirty-six, and `complete()` filled in
the rest from defaults — so a published, in-force rule reading
`blocking_findings` had never been able to fire, and three of the missing facts
default to the PERMISSIVE value.

The reason they were missing is layering rather than oversight: the version
service holds versions, and whether a model has an open blocking finding is the
finding register's answer. Rather than give the register a dependency on the
whole estate, it is given **this** — a callable it can ask.

Every provider here returns only facts it can actually establish. A fact nobody
can supply is a fact the gate should not advertise, and `decide()` now refuses
rather than defaulting, so an unsupplied fact is loud at the first call rather
than silent forever.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.log import get_logger, swallowed

logger = get_logger(__name__)


class GateFacts:
    """What the registers know, per gate.

    Constructed once at wiring time and handed to the services that hold gates.
    Each method takes what the caller already has and returns the rest.
    """

    def __init__(self, findings=None, documents=None, validation=None,
                 approvals=None, parameters=None, attachments=None):
        self.findings = findings
        self.documents = documents
        self.validation = validation
        self.approvals = approvals
        self.parameters = parameters
        self.attachments = attachments

    # ------------------------------------------------------------- findings
    def _findings(self, model_id: str) -> Dict[str, Any]:
        """Open findings, and how many of them block.

        Fails CLOSED on error. This decides whether a version may be approved
        over an open blocking finding, and a subsystem that is down must not
        read as "there are none" — which is precisely how the defaulted value
        behaved for the life of the gate.
        """
        if not self.findings or not model_id:
            return {"blocking_findings": 0, "open_findings": []}
        try:
            opened = self.findings.open_for(model_id)
            return {
                "blocking_findings": sum(1 for f in opened if f.get("blocking")),
                "open_findings": [f.get("severity") for f in opened],
            }
        except Exception as exc:                          # pragma: no cover
            swallowed(logger, exc, f"read open findings for {model_id}",
                      detail="reported as one blocking finding so the gate "
                             "refuses; a finding register that is down must "
                             "not read as an estate with nothing open")
            return {"blocking_findings": 1, "open_findings": ["unknown"]}

    # ---------------------------------------------------------------- gates
    def version_approve(self, model: Dict[str, Any], version: Dict[str, Any],
                        actor_roles: Optional[list] = None) -> Dict[str, Any]:
        """Everything `version:approve` advertises and the call site cannot see."""
        model_id = model.get("id", "")
        facts: Dict[str, Any] = {
            **self._findings(model_id),
            "actor_roles": list(actor_roles or []),
            "validated": False, "validation_outcome": None,
            "documents": 0, "accepted_documents": 0, "quorum_signatures": 0,
        }
        if self.validation:
            try:
                episodes = self.validation.for_model(model["urn"])
                concluded = [e for e in episodes if e.get("outcome")]
                facts["validated"] = bool(concluded)
                facts["validation_outcome"] = (concluded[-1].get("outcome")
                                               if concluded else None)
            except Exception as exc:                      # pragma: no cover
                swallowed(logger, exc, f"read validations for {model['urn']}",
                          detail="left as not validated, which is the "
                                 "conservative reading")
        if self.attachments:
            try:
                status = self.attachments.status(model_id)
                facts["documents"] = status.get("attached", 0)
                facts["accepted_documents"] = status.get("accepted", 0)
            except Exception as exc:                      # pragma: no cover
                swallowed(logger, exc, f"read attachments for {model_id}",
                          detail="left at zero")
        if self.approvals:
            try:
                needed = self.approvals.needed(model["urn"], version["semver"])
                facts["quorum_signatures"] = len(needed.get("signatures") or [])
            except Exception as exc:                      # pragma: no cover
                swallowed(logger, exc, "read the open quorum",
                          detail="left at zero")
        return facts

    def alias_move(self, model: Dict[str, Any],
                   actor_roles: Optional[list] = None) -> Dict[str, Any]:
        return {**self._findings(model.get("id", "")),
                "actor_roles": list(actor_roles or []),
                "record_status": model.get("status")}

    def model_mutate(self, model: Dict[str, Any],
                     actor_roles: Optional[list] = None) -> Dict[str, Any]:
        return {"actor_roles": list(actor_roles or [])}

    def warrant_resolve(self, model: Dict[str, Any],
                        version: Dict[str, Any]) -> Dict[str, Any]:
        facts = {**self._findings(model.get("id", "")),
                 "has_approved_parameters": False}
        if self.parameters:
            try:
                status = self.parameters.status(model["urn"], version["semver"])
                facts["has_approved_parameters"] = bool(status.get("approved"))
            except Exception as exc:                      # pragma: no cover
                swallowed(logger, exc, "read approved parameters",
                          detail="left as none, which is the conservative "
                                 "reading for a gate about running a model")
        return facts
