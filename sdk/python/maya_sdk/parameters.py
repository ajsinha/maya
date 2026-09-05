"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Parameter sets: the point of `P` a run happens at.

The distinction this module exists to keep visible: **recording new parameters
does not create a new model version.** The kernel did not change. That is what
lets a daily recalibration procedure be approved once rather than pretending a
committee meets every morning, and it is the thing people coming from an
experiment tracker most often get wrong.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class Parameters:
    """Fitting, delivering, and the four eyes that accept the numbers."""

    def __init__(self, maya):
        self._maya = maya

    def fit(self, *, urn: str, snapshot_id: str, principal: str,
            window: Dict[str, float], name: str = "fitted",
            environment: str = "lab", kind: str = "coefficients",
            declared_use: str = "model_development",
            note: str = "") -> Dict[str, Any]:
        """Let MAYA fit it, where the kernel names the `estimator` runtime.

        Four things happen in this order, and the order is the point: the warrant
        is resolved **first** (authority before data — a read performed under an
        authority that turns out not to exist has already happened), the snapshot
        is read at its pinned Delta version rather than at the head, the estimator
        runs through the ordinary runtime dispatch, and the result lands
        `proposed` rather than approved.
        """
        return self._maya.call("POST", "/parameter-fits", json={
            "urn": urn, "snapshot_id": snapshot_id, "principal": principal,
            "environment": environment, "window": window, "name": name,
            "kind": kind, "declared_use": declared_use, "note": note})

    def record(self, *, urn: str, semver: str, name: str, kind: str,
               values: Dict[str, Any], warrant_id: str,
               provenance: str = "fitted",
               featureset: Optional[str] = None,
               featureset_version: Optional[int] = None,
               window: Optional[Dict[str, float]] = None,
               as_of: Optional[float] = None,
               snapshot_id: Optional[str] = None,
               diagnostics: Optional[Dict[str, Any]] = None,
               note: str = "") -> Dict[str, Any]:
        """Deliver parameters fitted in your own engine.

        `warrant_id` is not optional in practice: a fitted set is accepted only
        against a warrant MAYA issued, because without one *"which data produced
        these numbers"* has no answer. The keyword is here rather than buried in
        a dictionary so that omitting it is a visible mistake.

        Send the diagnostics. They are what a reviewer reads — the condition
        number before the R², the convergence flag, the residual — and a set
        delivered without them asks somebody to approve a number on trust.
        """
        return self._maya.call("POST", "/parameters", json={
            "urn": urn, "semver": semver, "name": name, "kind": kind,
            "values": values, "provenance": provenance,
            "featureset": featureset, "featureset_version": featureset_version,
            "window": window, "as_of": as_of, "snapshot_id": snapshot_id,
            "warrant_id": warrant_id, "diagnostics": diagnostics or {},
            "note": note})

    def get(self, parameter_set_id: str) -> Dict[str, Any]:
        return self._maya.call("GET", f"/parameter-sets/{parameter_set_id}")

    def review(self, parameter_set_id: str, *, accept: bool,
               note: str = "") -> Dict[str, Any]:
        """Accept or reject, and never as whoever recorded them.

        A number one person can both produce and bless is a preference, not an
        estimate. The platform refuses it; this method cannot make that easier
        and does not try.
        """
        return self._maya.call("POST", f"/parameter-sets/{parameter_set_id}/review",
                               json={"accept": accept, "note": note})

    def provenance(self) -> Dict[str, Any]:
        """What each provenance means: fitted, calibrated, declared."""
        return self._maya.call("GET", "/parameter-provenance")
