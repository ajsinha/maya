"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Hook issuance and resolution.

MAYA does not execute models. It issues a signed, expiring, entitlement-bound
execution CONTRACT, and an execution engine acts on it. A consumer holds only a
URN; artifact location, schemas, operating boundaries and policy are resolved at
runtime, so a governed version move never requires a consumer to redeploy.

Two properties are load-bearing:

  * The revocation floor. A descriptor on the local revocation list is refused
    regardless of grace state. Grace extends authorisation currency; it never
    extends revocation ignorance (adversarial review, finding C-1).
  * Fail closed. No entitlement, no approved use, no approved version, or a
    blocking finding, and resolution refuses with a reason and a remediation
    hint rather than degrading quietly.
"""
from __future__ import annotations

import hmac
import random
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple

from core.evidence import EvidenceEngine
from core.registry import ModelRegistry, RegistryError
from core.store import Store, _ulid, canonical_digest, hook


class HookError(RuntimeError):
    """Resolution or issuance refused. ``code`` maps to the error taxonomy."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, Any]:
        return {"error": self.code, "detail": self.detail, "remediation": self.remediation}


def parse_urn(urn: str) -> Tuple[str, Optional[str], Optional[str]]:
    """``maya://model/<name>[@<semver>][#<alias>]`` -> (name, semver, alias)."""
    if not urn.startswith("maya://model/"):
        raise HookError("validation_failed", f"not a MAYA model URN: {urn}",
                        "expected maya://model/<name>[@<semver>|#<alias>]")
    body = urn[len("maya://model/"):]
    aliasname = semver = None
    if "#" in body:
        body, aliasname = body.split("#", 1)
    if "@" in body:
        body, semver = body.split("@", 1)
    if not body:
        raise HookError("validation_failed", f"empty model name in {urn}", "")
    return body, semver, aliasname


class HookService:
    """Issues and resolves hook descriptors. Signs them; never runs a model."""

    def __init__(self, store: Store, registry: ModelRegistry, evidence: EvidenceEngine,
                 signing_key: str = "maya-dev-key",
                 ttl_by_tier: Optional[Dict[int, int]] = None,
                 grace_by_tier: Optional[Dict[int, int]] = None,
                 jitter_pct: int = 20):
        self.store, self.registry, self.evidence = store, registry, evidence
        self._key = signing_key.encode()
        self._ttl = ttl_by_tier or {1: 60, 2: 300, 3: 3600, 4: 3600}
        self._grace = grace_by_tier or {1: 0, 2: 0, 3: 900, 4: 900}
        self._jitter = max(0, min(jitter_pct, 50))
        self._epoch = 0

    # ------------------------------------------------------------------ issue
    def issue(self, urn: str, environment: str, principal: str, declared_use: str,
              flavour: str = "descriptor_only", actor: str = "system") -> Dict[str, Any]:
        name, semver, aliasname = parse_urn(urn)
        m = self.registry.require(f"maya://model/{name}")
        tier = m.get("tier") or 1
        if semver is None and aliasname is None:
            aliasname = "champion"
        row = {"id": _ulid(), "model_id": m["id"], "environment": environment,
               "binding_kind": "pinned_version" if semver else "alias",
               "alias_name": aliasname, "version_id": None, "flavour": flavour,
               "principal": principal, "declared_use": declared_use,
               "ttl_seconds": self._ttl.get(tier, 300),
               "grace_seconds": self._grace.get(tier, 0),
               "revoked": False, "revoke_reason": None, "epoch": self._epoch,
               "created_at": time.time()}
        if semver:
            v = self.registry.version(m["urn"], semver)
            if not v:
                raise HookError("validation_failed", f"no version {semver} for {m['urn']}", "")
            row["version_id"] = v["id"]
        self.store.insert(hook, row)
        self.evidence.append("hook_issued", "model", m["id"],
                             {"urn": urn, "principal": principal, "use": declared_use,
                              "environment": environment}, actor=actor)
        return row

    # ---------------------------------------------------------------- resolve
    def resolve(self, urn: str, environment: str, principal: str,
                declared_use: str) -> Dict[str, Any]:
        """Return a signed descriptor, or refuse with a reason. Never executes."""
        name, semver, aliasname = parse_urn(urn)
        model_urn = f"maya://model/{name}"
        try:
            m = self.registry.require(model_urn)
        except RegistryError as exc:
            raise HookError("not_found", str(exc), "register the model first") from exc

        grant = self.store.one(hook, (hook.c.model_id == m["id"])
                               & (hook.c.environment == environment)
                               & (hook.c.principal == principal))
        if grant is None:
            raise HookError("no_entitlement",
                            f"{principal} holds no hook for {model_urn} in {environment}",
                            "request a hook grant for this principal and approved use")
        if grant["revoked"]:
            raise HookError("revoked", grant["revoke_reason"] or "hook revoked",
                            "the hook was withdrawn; do not retry")
        if grant["declared_use"] != declared_use:
            raise HookError("use_not_approved",
                            f"declared use '{declared_use}' is not the approved use "
                            f"'{grant['declared_use']}'",
                            "seek approval for this use, or declare the approved one")

        version = (self.registry.version(model_urn, semver) if semver
                   else self.registry.resolve_alias(model_urn, environment,
                                                    aliasname or grant["alias_name"] or "champion"))
        if version is None:
            raise HookError("not_found", f"nothing bound for {urn} in {environment}",
                            "point the alias at an approved version")
        if version["status"] != "approved":
            raise HookError("restricted",
                            f"version {version['semver']} is '{version['status']}'",
                            "an approved version is required in this environment")

        ttl = self._jittered(grant["ttl_seconds"])
        now = time.time()
        descriptor = {
            "maya_descriptor_version": "1.0",
            "descriptor_id": _ulid(),
            "urn": urn,
            "resolved": {"model_urn": model_urn, "version": version["semver"],
                         "version_id": version["id"],
                         "manifest_digest": version["manifest_digest"],
                         "binding_kind": grant["binding_kind"],
                         "trainability_class": version["trainability_class"]},
            "authorization": {"principal": principal, "declared_use": declared_use,
                              "environment": environment, "granted_at": now,
                              "expires_at": now + ttl, "grace_seconds": grant["grace_seconds"]},
            "execution": {"flavour": grant["flavour"],
                          "artifact_digest": version["artifact_digest"],
                          "deterministic": version["deterministic"]},
            "io_contract": {"input_schema": version["input_schema"],
                            "output_schema": version["output_schema"]},
            "constraints": version["contract"],
            "governance_snapshot": {"tier": m.get("tier"), "model_status": m["status"],
                                    "version_status": version["status"]},
            "revocation": {"epoch": self._epoch},
        }
        descriptor["signature"] = self.sign(descriptor)
        return descriptor

    # ----------------------------------------------------------------- crypto
    def sign(self, descriptor: Dict[str, Any]) -> str:
        body = {k: v for k, v in descriptor.items() if k != "signature"}
        return hmac.new(self._key, canonical_digest(body).encode(), sha256).hexdigest()

    def verify(self, descriptor: Dict[str, Any]) -> bool:
        claimed = descriptor.get("signature", "")
        return hmac.compare_digest(claimed, self.sign(descriptor))

    def _jittered(self, ttl: int) -> int:
        """+/- jitter so a fleet does not expire in lockstep and stampede."""
        if not self._jitter:
            return ttl
        delta = ttl * self._jitter / 100.0
        return max(1, int(ttl + random.uniform(-delta, delta)))

    # ------------------------------------------------------------- revocation
    def revoke(self, hook_id: str, reason: str, actor: str = "system") -> Dict[str, Any]:
        row = self.store.one(hook, hook.c.id == hook_id)
        if not row:
            raise HookError("not_found", f"no hook {hook_id}", "")
        self._epoch += 1
        self.store.update(hook, hook.c.id == hook_id,
                          {"revoked": True, "revoke_reason": reason, "epoch": self._epoch})
        self.evidence.append("hook_revoked", "model", row["model_id"],
                             {"hook_id": hook_id, "reason": reason}, actor=actor)
        return {"hook_id": hook_id, "revoked": True, "reason": reason, "epoch": self._epoch}

    def revoke_model(self, urn: str, reason: str, actor: str = "system") -> int:
        """Kill switch for every hook on a model."""
        m = self.registry.require(urn)
        rows = self.store.many(hook, hook.c.model_id == m["id"])
        for r in rows:
            self.revoke(r["id"], reason, actor)
        return len(rows)

    def is_expired(self, descriptor: Dict[str, Any], now: Optional[float] = None) -> bool:
        auth = descriptor["authorization"]
        return (now or time.time()) > auth["expires_at"] + auth.get("grace_seconds", 0)

    def grants(self, urn: str) -> List[Dict[str, Any]]:
        m = self.registry.require(urn)
        return self.store.many(hook, hook.c.model_id == m["id"])
