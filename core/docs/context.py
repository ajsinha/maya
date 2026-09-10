"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Gathering what the lenses read.

This is the one place in the documentation package that knows the platform has a
registry, a feature platform, a validation service and the rest. The compiler and
the lenses do not: they are handed a dictionary and go looking in it.

That separation is worth the extra class. A lens that imported nine services
would be a lens nobody could test without standing up nine services, and a
compiler that did the gathering itself would need changing every time a new
subsystem had something to say about a model.

Services are received rather than imported, and every one of them is optional —
a deployment without monitoring should still be able to compile a model
development document, with the monitoring section honestly reporting that there
is nothing to report.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.log import get_logger, swallowed
from core.registry.versions import latest_version

logger = get_logger(__name__)


class ContextBuilder:
    """Assembles the state a document is compiled from."""

    def __init__(self, registry, evidence, risk_repo=None, features=None,
                 validation=None, findings=None, monitoring=None, lifecycle=None,
                 warrants=None, overlays=None, regimes=None, attachments=None,
                 limitations=None, assumptions=None):
        self.registry, self.evidence = registry, evidence
        self.risk_repo, self.features = risk_repo, features
        self.validation, self.findings = validation, findings
        self.monitoring, self.lifecycle, self.warrants = monitoring, lifecycle, warrants
        self.overlays, self.regimes = overlays, regimes
        self.attachments = attachments
        # The two registers the Assumptions lens is named after. It read only
        # the version contract's numeric bounds, so for a model with no numeric
        # contract — a vendor score, a generative assembly, an elicited
        # scorecard — the section rendered NOTHING, and the structured
        # statements a person had taken the trouble to record sat in a register
        # the document could not see.
        self.limitations, self.assumptions = limitations, assumptions

    def __call__(self, urn: str) -> Dict[str, Any]:
        # Which sections could not be READ, as distinct from which had nothing
        # to show. `_optional` returned the same `[]` for both, so a finding
        # register that threw rendered as "No findings are open against this
        # model." -- a fact nobody established, in a document the compiler then
        # persisted, stamped with the evidence head and appended to the chain as
        # `document_compiled`. The docstring on `_optional` already promised
        # "the section reports the gap"; nothing carried the gap to the section.
        self._unreadable: set = set()
        model = self.registry.require(urn)
        versions = self.registry.versions(urn)
        version = self._current(urn, versions)

        ctx: Dict[str, Any] = {
            "model": model, "versions": versions, "version": version,
            # The model AND every version. Approvals, validations, test
            # results and parameter sets are recorded against the version, so a
            # document built from the model's id alone cited none of them: a
            # fully governed model compiled fifteen sections with two citations,
            # and Classification, Methodology, Assumptions and Validation
            # rendered as filled while citing nothing.
            "evidence": self.evidence.for_subjects(
                [model["id"], *(v["id"] for v in versions)]),
            "chain": self.evidence.verify_chain(),
            "alias_history": self.registry.alias_history(urn),
        }
        ctx["assessment"] = self._assessment(model["id"])
        ctx["feature_contract"] = self._optional(
            lambda: self.features.contract_for(version["id"]) if version else None,
            "feature contract")
        ctx["validations"] = self._optional(
            lambda: self.validation.for_model(urn), "validations", default=[])
        ctx["results_by_validation"] = {
            v["id"]: self._optional(lambda v=v: self.validation.results_for(v["id"]),
                                    "validation results", default=[])
            for v in ctx["validations"]}
        ctx["findings"] = self._optional(
            lambda: self.findings.open_for(model["id"]), "findings", default=[])
        ctx["monitoring"] = self._optional(
            lambda: self.monitoring.status(model["id"]), "monitoring", default={})
        ctx["lifecycle"] = self._optional(
            lambda: self.lifecycle.state(urn), "lifecycle")
        ctx["warrants"] = self._optional(
            lambda: self.warrants.grants_for(urn), "warrants", default=[])
        ctx["overlays"] = self._optional(
            lambda: self.overlays.status(model["id"]), "overlays", default={})
        semver = (version or {}).get("semver")
        ctx["limitations"] = self._optional(
            lambda: (self.limitations.for_version(urn, semver)
                     if self.limitations and semver else None),
            "limitations")
        ctx["assumptions"] = self._optional(
            lambda: (self.assumptions.for_version(urn, semver)
                     if self.assumptions and semver else None),
            "assumptions")
        ctx["attachments"] = self._optional(
            lambda: self.attachments.for_model(model["id"]), "attachments", default=[])
        ctx["attachment_status"] = self._optional(
            lambda: self.attachments.status(model["id"]), "attachment status", default={})
        # Regime determinations read the same context, so this is computed last
        # from what the rest of it found.
        ctx["regimes"] = self._optional(
            lambda: self.regimes.determine_all(self.regimes.core_state(ctx)),
            "regime determinations", default={})
        ctx["unreadable"] = sorted(self._unreadable)
        return ctx

    def _current(self, urn: str, versions: List[Dict[str, Any]]) -> Optional[Dict]:
        """The version the document is about: the production champion if there is
        one, otherwise the most recent. A document about 'the model' with no
        version named is a document about nothing in particular."""
        resolved = self._optional(
            lambda: self.registry.resolve_alias(urn, "prod", "champion"),
            "prod champion")
        return resolved or latest_version(versions)

    def _assessment(self, model_id: str) -> Optional[Dict[str, Any]]:
        if self.risk_repo is None:
            return None
        rows = self.risk_repo.many(model_id=model_id)
        return latest_version(rows)

    def _optional(self, fetch, what: str, default=None):
        """Fetch from a service that may be absent, or may have nothing.

        A subsystem that is not wired in, or has nothing recorded, must not stop
        a document compiling — but it must not do so silently either, so the
        reason is logged and the section reports the gap.
        """
        try:
            return fetch() if fetch else default
        except AttributeError as exc:
            swallowed(logger, exc, f"{what} is not available to the compiler",
                      detail="the section will report the gap", level=10)
            self._unreadable.add(what)
            return default
        except Exception as exc:                      # a service refusing is data
            swallowed(logger, exc, f"could not read {what} while compiling",
                      detail="the section will report the gap")
            self._unreadable.add(what)
            return default
