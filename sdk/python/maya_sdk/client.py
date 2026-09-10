"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The client, and the one rule it exists to keep.

**The SDK never decides anything.** It carries requests and translates refusals.
It holds no rule about who may act, no local view of whether a version is
approved, no copy of the tiering bands, no idea which verbs a trainability class
admits. Every one of those would be a second implementation of a governance rule,
and a second implementation is a thing that can disagree with the first — quietly,
in the direction of permitting more, because that is the direction in which
nobody files a bug.

What it is for is the other half of the same principle: **the compliant path has
to be the fast path.** If registering a model properly takes forty lines of
`urllib` and getting it wrong takes four, the register fills with models nobody
registered properly. So the operations a model developer actually performs are
one call each, they raise on refusal rather than returning something ignorable,
and the refusal carries the remediation the platform wrote.

Usage::

    from maya_sdk import Maya

    maya = Maya("https://maya.internal", "d.raman", "…")
    maya.models.register(urn="maya://model/credit.pd.smallbiz", name="SB PD",
                         model_class="credit.pd.scorecard", domain="credit",
                         owner="person/j.okafor", legal_entity="LE-US-01",
                         purpose="12-month PD at origination")

Everything is keyword-only past the first argument, deliberately: these calls
carry six to ten fields, several of them strings that would swap silently.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from maya_sdk import (artifacts, documents, features, governance, models,
                      parameters, warrants)
from maya_sdk import assist as assist_module
from maya_sdk import principals as principals_module
from maya_sdk.errors import Refused, Unreachable, refusal
from maya_sdk.transport import HttpTransport, REQUEST_HEADER, new_request_id

API = "/api/v1"


class Maya:
    """One MAYA instance, addressed as one principal."""

    def __init__(self, base_url: str = "http://localhost:5006",
                 username: str = "", password: str = "", *,
                 api_key: str = "", transport: Any = None, timeout: float = 30.0,
                 verify_tls: bool = True):
        """A client, addressed as one principal.

        `api_key` is how a service should connect. A password names a person and
        carries everything they hold; a key names a credential that expires, can
        be narrowed to a subset, and can be revoked without touching the
        account:

            Maya("https://maya.internal", api_key=os.environ["MAYA_API_KEY"])

        A transport may be supplied instead of either. That is how the SDK is
        tested against the real application in-process rather than against a
        mock of its routes — a mock of the thing under test proves only that the
        mock agrees with itself.
        """
        self.transport = transport or HttpTransport(
            base_url, username, password, timeout=timeout,
            verify_tls=verify_tls, api_key=api_key)
        self.api = API
        self.last_request_id: str = ""

        self.models = models.Models(self)
        self.versions = models.Versions(self)
        # The two registers a model risk manager actually writes into.
        # Neither had a client surface, so every worked example in this
        # repository put its limitations in a free-text diagnostics blob
        # where nothing could count them.
        self.limitations = models.Limitations(self)
        self.assumptions = models.Assumptions(self)
        self.waivers = models.Waivers(self)
        self.features = features.Features(self)
        self.featuresets = features.Featuresets(self)
        self.warrants = warrants.Warrants(self)
        self.artifacts = artifacts.Artifacts(self)
        self.parameters = parameters.Parameters(self)
        self.assist = assist_module.Assist(self)
        # Filled in by the SDK completion pass. Attached here rather than
        # discovered, because a client that grows subjects dynamically is one
        # whose surface nobody can read.
        self.attachments = documents.Attachments(self)
        self.documents = documents.Documents(self)
        self.packages = documents.Packages(self)
        self.rules = governance.Rules(self)
        self.lifecycle = governance.Lifecycle(self)
        self.fibres = governance.Fibres(self)
        # The rest of `governance`, which was written and then not attached.
        #
        # Ten of seventeen subjects were reachable only by constructing them by
        # hand — including the point-in-time query, the featureset algebra,
        # findings, monitors and validations. They worked; nothing named them.
        # The shipped documentation routed around the gap three inconsistent
        # ways, and a tutorial fell back to raw `client.call()` for methods the
        # SDK already had, which reads to a new joiner as *the SDK cannot do
        # this* rather than *nobody wired it up*.
        self.approvals = governance.VersionApprovals(self)
        self.relations = governance.Relations(self)
        self.catalogue = governance.FeatureCatalogue(self)
        self.views = governance.FeatureViews(self)
        self.contracts = governance.FeatureContracts(self)
        self.training_sets = governance.TrainingSets(self)
        self.featureset_algebra = governance.FeaturesetAlgebra(self)
        self.validations = governance.Validations(self)
        self.findings = governance.Findings(self)
        self.monitors = governance.Monitors(self)
        self.reports = governance.Reports(self)
        self.validation_aid = governance.ValidationAssistance(self)
        self.regime_encoding = governance.RegimeEncoding(self)
        self.probes = governance.Probes(self)
        self.remediation = governance.Remediation(self)
        self.migrations = governance.Migrations(self)
        self.supervisory = governance.SupervisoryMatters(self)
        self.backlog = governance.ValidationBacklog(self)
        # Administering people, roles and keys. Reachable before this only by
        # constructing raw calls, which reads as "the SDK cannot do this"
        # rather than "nobody wired it up" — the same gap that once left ten
        # governance subjects unattached.
        self.principals = principals_module.Principals(self)
        self.api_keys = principals_module.ApiKeys(self)

    # ------------------------------------------------------------- the wire
    def call(self, method: str, path: str, *, json: Any = None,
             content: Optional[bytes] = None,
             params: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None,
             raw: bool = False, absolute: bool = False) -> Any:
        """One request. Returns the decoded body, or raises.

        The request id is minted here and sent, so the identifier in a traceback
        is the identifier in the server's log for the same call. When the server
        answers with one of its own it wins — it is the one that was written
        down — and either way the caller can read it off `last_request_id`.
        """
        request_id = new_request_id()
        response = self.transport.request(
            method, path if absolute else f"{self.api}{path}",
            json=json, content=content, params=params,
            headers={**(headers or {}), REQUEST_HEADER: request_id})

        headers = getattr(response, "headers", {}) or {}
        self.last_request_id = (
            headers.get(REQUEST_HEADER.lower()) or headers.get(REQUEST_HEADER)
            or request_id)

        if response.status_code >= 400:
            raise refusal(response.status_code, self._body(response),
                          self.last_request_id)
        if raw:
            return response.content
        return self._body(response)

    @staticmethod
    def _body(response: Any) -> Any:
        """The decoded body, or the raw text when it is not JSON.

        A 502 from a proxy answers in HTML, and an SDK that raised a JSON
        decoding error over it would replace a legible failure with an illegible
        one — at the exact moment somebody is trying to find out what happened.
        """
        try:
            return response.json()
        except Exception:
            return getattr(response, "text", "") or ""

    # -------------------------------------------------------------- helpers
    def whoami(self) -> Dict[str, Any]:
        """Who the platform thinks you are, and what you may do.

        Worth calling first in any script. The permissions come from the
        platform rather than from anything here, so a tool can hide an action
        the caller may not take without ever deciding that for itself.
        """
        return self.call("GET", "/me")

    def health(self) -> Dict[str, Any]:
        """Readiness, including whether the evidence chain verifies.

        Outside the versioned API, because liveness is not a governed operation
        and a monitoring probe should not have to track an API version.
        """
        return self.call("GET", "/health/ready", absolute=True)

    def verify_evidence(self) -> Dict[str, Any]:
        """Verify the whole chain. Slow and worth it before an examination."""
        return self.call("GET", "/evidence/chain")


__all__ = ["Maya", "Refused", "Unreachable"]
