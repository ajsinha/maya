"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Warrant resolution — the platform's boundary with anything that runs a model.

MAYA does not execute models. It issues a signed, expiring, entitlement-bound
execution CONTRACT, and an execution engine acts on it. That separation is the
reason a governed version move never requires a consumer to redeploy: the
consumer holds a URN, and everything else is resolved here, at the moment of
use, against the policy in force at that moment.

Resolution fails closed. No entitlement, no approved use, no approved version —
and it refuses with a reason and a remediation hint rather than degrading
quietly into something that looks like it worked.

The work is delegated: WarrantGrants owns entitlements and revocation, the
WarrantSigner owns signatures and expiry, the DescriptorFactory owns the
shape of what an engine receives. What lives here is the ORDER of the checks,
which is the part that has to be right.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.execution.builder import WarrantBuilder
from core.execution.errors import WarrantError
from core.execution.grants import WarrantGrants
from core.execution.signing import WarrantSigner
from core.execution.urn import DEFAULT_ALIAS, model_urn, parse_urn
from core.log import get_logger
from core.ports import BlockingSource
from core.registry import ModelRegistry, RegistryError
from db import WarrantRepository

logger = get_logger(__name__)


class WarrantService:
    """Issues and resolves warrant descriptors. Signs them; never runs a model."""

    def __init__(self, repo: WarrantRepository, registry: ModelRegistry,
                 evidence: EvidenceEngine, signing_key: str = "maya-dev-key",
                 ttl_by_tier: Optional[Dict[int, int]] = None,
                 grace_by_tier: Optional[Dict[int, int]] = None,
                 jitter_pct: int = 20, blocking: Optional[BlockingSource] = None):
        self.registry, self.blocking = registry, blocking
        self.grants = WarrantGrants(repo, registry, evidence, ttl_by_tier, grace_by_tier)
        self.signer = WarrantSigner(signing_key, jitter_pct)
        self.builder = WarrantBuilder(self.signer)

    @property
    def epoch(self) -> int:
        """Bumped by every revocation. Descriptors carry the epoch they were
        minted under, so an engine can tell a stale credential from a current one."""
        return self.grants.epoch

    # ---------------------------------------------------------------- resolve
    def resolve(self, urn: str, environment: str, principal: str,
                declared_use: str, verb: str = "score") -> Dict[str, Any]:
        """Return a signed descriptor, or refuse with a reason. Never executes."""
        name, semver, aliasname = parse_urn(urn)
        m = self._model(urn, model_urn(name))
        self._check_not_blocked(m)
        grant = self._grant(m, environment, principal, declared_use)
        version = self._version(m["urn"], environment, semver,
                                aliasname or grant["alias_name"], urn)
        return self.builder.build(urn, m, version, grant, principal,
                                  declared_use, environment, self.epoch, verb=verb)

    def _model(self, urn: str, model_urn_: str) -> Dict[str, Any]:
        try:
            return self.registry.require(model_urn_)
        except RegistryError as exc:
            logger.info("warrant resolution for %s hit an unregistered model: %s", urn, exc)
            raise WarrantError("not_found", str(exc), "register the model first") from exc

    def _check_not_blocked(self, model: Dict[str, Any]) -> None:
        """Fail closed on an open blocking finding.

        A model that failed challenge must not be servable, and the only way to
        guarantee that is to check at resolution — the one point every consumer
        passes through, however it was entitled.
        """
        if not self.blocking:
            return
        if open_findings := self.blocking.blocking_for(model["id"]):
            titles = "; ".join(f["title"] for f in open_findings)
            logger.warning("resolution refused for %s: %d blocking finding(s)",
                           model["urn"], len(open_findings))
            raise WarrantError("blocked",
                            f"{len(open_findings)} blocking finding(s) open against "
                            f"{model['urn']} ({titles})",
                            "close the blocking findings, or withdraw the model from service")

    def _grant(self, model: Dict[str, Any], environment: str, principal: str,
               declared_use: str) -> Dict[str, Any]:
        """Entitlement, then withdrawal, then declared use — in that order.

        Revocation is checked before the use comparison on purpose: a withdrawn
        warrant is withdrawn whatever the caller claims to be doing with it.
        """
        grant = self.grants.find(model["id"], environment, principal)
        if grant is None:
            raise WarrantError("no_entitlement",
                            f"{principal} holds no warrant for {model['urn']} in {environment}",
                            "request a warrant grant for this principal and approved use")
        if grant["revoked"]:
            raise WarrantError("revoked", grant["revoke_reason"] or "warrant revoked",
                            "the warrant was withdrawn; do not retry")
        if grant["declared_use"] != declared_use:
            raise WarrantError("use_not_approved",
                            f"declared use '{declared_use}' is not the approved use "
                            f"'{grant['declared_use']}'",
                            "seek approval for this use, or declare the approved one")
        return grant

    def _version(self, model_urn_: str, environment: str, semver: Optional[str],
                 aliasname: Optional[str], urn: str) -> Dict[str, Any]:
        version = (self.registry.version(model_urn_, semver) if semver
                   else self.registry.resolve_alias(model_urn_, environment,
                                                    aliasname or DEFAULT_ALIAS))
        if version is None:
            raise WarrantError("not_found", f"nothing bound for {urn} in {environment}",
                            "point the alias at an approved version")
        if version["status"] != "approved":
            raise WarrantError("restricted",
                            f"version {version['semver']} is '{version['status']}'",
                            "an approved version is required in this environment")
        return version

    # ------------------------------------------------------- delegated surface
    def issue(self, *a, **kw) -> Dict[str, Any]:
        return self.grants.issue(*a, **kw)

    def grants_for(self, urn: str) -> List[Dict[str, Any]]:
        return self.grants.of_model(urn)

    def revoke(self, warrant_id: str, reason: str, actor: str = "system") -> Dict[str, Any]:
        return self.grants.revoke(warrant_id, reason, actor)

    def revoke_model(self, urn: str, reason: str, actor: str = "system") -> int:
        return self.grants.revoke_model(urn, reason, actor)

    def sign(self, descriptor: Dict[str, Any]) -> str:
        return self.signer.sign(descriptor)

    def verify(self, descriptor: Dict[str, Any]) -> bool:
        return self.signer.verify(descriptor)

    def is_expired(self, descriptor: Dict[str, Any], now: Optional[float] = None) -> bool:
        return self.signer.is_expired(descriptor, now)
