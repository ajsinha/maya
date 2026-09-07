"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

How a service authenticates without a password.

A service principal signing in over HTTP Basic has three problems a key does
not. The password is a shared secret somebody typed and can retype elsewhere;
it carries **every** permission the principal holds, for as long as the account
exists; and rotating it means changing it in the register and in whatever holds
it at the same instant, or something stops working.

Five properties, and each of them is the reason for a decision below.

**The secret is shown once.** What is stored is a SHA-256 of it. Not a password
KDF: the key is 256 bits from `secrets.token_urlsafe`, so there is no dictionary
to attack and a slow hash would buy nothing while costing a comparison on every
request. A password is different and is hashed differently — `principals.py`
uses PBKDF2 — because a password is something a person chose.

**Every key expires.** A key with no expiry is a credential nobody ever reviews,
and *we will rotate it later* is the sentence before an incident. The maximum is
a year and the default is ninety days.

**A key holds a subset, never a superset.** It may narrow what its principal
can do and may not widen it — and the narrowing is checked **at use**, against
what the principal holds *now*. So a role removed, or a principal suspended,
reaches every key that principal issued, immediately, without anybody
remembering to revoke them.

**Rotation is two keys, briefly.** There is no `PUT` that swaps a secret: issue
the new one, move the caller, revoke the old one. A rotation that is one atomic
act is a rotation with a window in which nothing works.

**Revoked, never deleted.** The row is what says a key existed, who issued it
and when it stopped — and `last_used_at` is what says whether anybody noticed.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Dict, List, Optional

from core.authz.common import require_known
from core.evidence import EvidenceEngine

#: Every key starts with this. It makes one recognisable in a log somebody is
#: about to paste into a ticket, and it is what a secret scanner matches on.
PREFIX = "maya_sk_"

#: Bytes of entropy behind the secret. 32 is 256 bits, which is why the stored
#: hash can be a plain SHA-256 rather than a password KDF.
ENTROPY_BYTES = 32

#: How much of the key is stored in clear, so two can be told apart in a list.
#: Short enough to be useless on its own.
VISIBLE_PREFIX = len(PREFIX) + 6

DEFAULT_LIFETIME_DAYS = 90
MAX_LIFETIME_DAYS = 365


class ApiKeyError(RuntimeError):
    """A refusal about a key."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, Any]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class ApiKeyRegister:
    """Issues, authenticates, lists and revokes keys."""

    def __init__(self, repo, principals, authz, evidence: EvidenceEngine):
        self.repo, self.principals = repo, principals
        self.authz, self.evidence = authz, evidence

    # ------------------------------------------------------------------ issue
    def issue(self, username: str, name: str, *,
              scopes: Optional[List[str]] = None,
              lifetime_days: int = DEFAULT_LIFETIME_DAYS,
              actor: str = "system") -> Dict[str, Any]:
        """Mint a key. The secret is in the return value and nowhere else.

        `scopes` narrows what the key may do. Empty means everything its
        principal holds — stated rather than implied, because a key that
        replaces a password legitimately needs that and a reader should not have
        to infer it from a blank field.
        """
        principal = self.principals.get(username)
        if not principal:
            raise ApiKeyError("no_such_principal",
                              f"no principal '{username}' to issue a key for",
                              "create the principal first; a key is a way for "
                              "an identity to authenticate, not an identity")
        if principal.get("status") != "active":
            raise ApiKeyError(
                "principal_not_active",
                f"'{username}' is {principal.get('status')}, and a key issued "
                f"to a suspended principal would be a way around the suspension",
                "reinstate them first")
        if not (name or "").strip():
            raise ApiKeyError(
                "name_required",
                "a key needs a name saying what holds it — 'nightly-scoring', "
                "'ecl-batch'. A list of unnamed keys is a list nobody can "
                "safely revoke from",
                "name it after the thing that will use it")
        if self.repo.one(username=username, name=name.strip()):
            raise ApiKeyError(
                "name_in_use",
                f"'{username}' already has a key named '{name.strip()}'",
                "revoke that one, or name this after what will actually hold it")

        if lifetime_days < 1 or lifetime_days > MAX_LIFETIME_DAYS:
            raise ApiKeyError(
                "lifetime_refused",
                f"a key lives between 1 and {MAX_LIFETIME_DAYS} days, and this "
                f"asked for {lifetime_days}. A key with no practical expiry is "
                f"a credential nobody ever reviews",
                f"ask for at most {MAX_LIFETIME_DAYS} days and rotate")

        held = self.authz.permissions(principal)
        wanted = self._checked_scopes(scopes, held, username)

        secret = PREFIX + secrets.token_urlsafe(ENTROPY_BYTES)
        row = self.repo.add({
            "principal_id": principal["id"], "username": username,
            "name": name.strip(), "prefix": secret[:VISIBLE_PREFIX],
            "key_hash": _digest(secret), "scopes": sorted(wanted),
            "created_at": time.time(), "created_by": actor,
            "expires_at": time.time() + lifetime_days * 86400})
        self.evidence.append(
            "api_key_issued", "principal", principal["id"],
            {"name": row["name"], "prefix": row["prefix"],
             "scopes": sorted(wanted) or "everything the principal holds",
             "expires_at": row["expires_at"]},
            actor=actor)
        # The only time the secret exists outside the caller's memory.
        return {**self._public(row), "secret": secret,
                "detail": "this is the only time the secret is shown; it is "
                          "stored as a hash and cannot be recovered"}

    def _checked_scopes(self, scopes, held, username) -> List[str]:
        """A key narrows what its principal can do and never widens it."""
        if not scopes:
            return []
        wanted = sorted({require_known(s) for s in scopes})
        if excess := sorted(set(wanted) - set(held)):
            raise ApiKeyError(
                "scope_exceeds_principal",
                f"the key would carry {', '.join(excess)}, which '{username}' "
                f"does not hold. A credential cannot grant what the identity "
                f"behind it was never given",
                "narrow the key, or give the principal the role that carries "
                "those permissions — which is a decision about accountability "
                "rather than about a key")
        return wanted

    # --------------------------------------------------------- authentication
    def authenticate(self, secret: str) -> Optional[Dict[str, Any]]:
        """The principal this key acts as, or None.

        Returns the principal with the key's scopes applied, so everything
        downstream authorises the way it already does. The narrowing happens
        HERE rather than at issue, against what the principal holds now: a role
        removed or an account suspended reaches every key that principal issued,
        immediately, with nobody remembering to revoke them.
        """
        if not secret or not secret.startswith(PREFIX):
            return None
        row = self.repo.one(key_hash=_digest(secret))
        if not row or row.get("revoked_at"):
            return None
        if row["expires_at"] <= time.time():
            return None
        principal = self.principals.get(row["username"])
        if not principal or principal.get("status") != "active":
            return None

        # A JSON column that fails to decode is left as raw TEXT, and the scope
        # check downstream was `permission not in scopes` -- a SUBSTRING match
        # on that string, so 'model:read' matched inside '["model:read_only"]'
        # and the key was granted a permission its scope excludes. A malformed
        # cell in a table that decides authorisation refuses; it does not
        # degrade into a weaker check.
        scopes = row.get("scopes") or []
        if not isinstance(scopes, (list, tuple)):
            raise ApiKeyError(
                "key_scope_unreadable",
                f"the stored scope of API key '{row['name']}' is not a list of "
                f"permissions, so nothing can be authorised against it",
                "revoke this key and issue another")

        self.repo.set({"last_used_at": time.time(),
                       "use_count": (row.get("use_count") or 0) + 1},
                      id=row["id"])
        return {**principal, "api_key": row["id"],
                "api_key_name": row["name"],
                "api_key_scopes": list(scopes)}

    # ------------------------------------------------------------------ query
    def for_principal(self, username: str) -> List[Dict[str, Any]]:
        return [self._public(r) for r in self.repo.many(username=username)]

    def all(self) -> List[Dict[str, Any]]:
        return [self._public(r) for r in self.repo.many()]

    def require(self, key_id: str) -> Dict[str, Any]:
        row = self.repo.one(id=key_id)
        if not row:
            raise ApiKeyError("no_such_key", f"no API key '{key_id}'", "")
        return row

    @staticmethod
    def _public(row: Dict[str, Any]) -> Dict[str, Any]:
        """Everything about a key except anything that could be used as one."""
        now = time.time()
        expired = row["expires_at"] <= now
        revoked = bool(row.get("revoked_at"))
        return {
            "id": row["id"], "username": row["username"], "name": row["name"],
            "prefix": row["prefix"] + "…",
            "scopes": row.get("scopes") or [],
            "scope_detail": ("everything the principal holds"
                             if not (row.get("scopes") or [])
                             else f"{len(row['scopes'])} permission(s)"),
            "created_at": row["created_at"], "created_by": row["created_by"],
            "expires_at": row["expires_at"],
            "expires_in_days": round((row["expires_at"] - now) / 86400, 1),
            "last_used_at": row.get("last_used_at"),
            "use_count": row.get("use_count") or 0,
            "revoked_at": row.get("revoked_at"),
            "revoke_reason": row.get("revoke_reason"),
            "state": "revoked" if revoked else ("expired" if expired
                                                else "active"),
            "never_used": int(not row.get("use_count")),
        }

    # ----------------------------------------------------------------- revoke
    def revoke(self, key_id: str, reason: str,
               actor: str = "system") -> Dict[str, Any]:
        """Withdraw a key. The row stays: it is what says the key existed."""
        row = self.require(key_id)
        if row.get("revoked_at"):
            raise ApiKeyError(
                "already_revoked",
                f"'{row['name']}' was revoked "
                f"{'by ' + row['revoked_by'] if row.get('revoked_by') else ''}"
                f" already",
                "")
        if not (reason or "").strip():
            raise ApiKeyError(
                "reason_required",
                "revoking a key needs a reason: an unexplained revocation "
                "during an incident is indistinguishable from one during a "
                "tidy-up",
                "say why — 'rotated', 'leaked in a ticket', 'service retired'")
        self.repo.set({"revoked_at": time.time(), "revoked_by": actor,
                       "revoke_reason": reason.strip()}, id=key_id)
        self.evidence.append(
            "api_key_revoked", "principal", row["principal_id"],
            {"name": row["name"], "prefix": row["prefix"], "reason": reason},
            actor=actor)
        return self._public(self.require(key_id))

    # ------------------------------------------------------------------ hygiene
    def report(self) -> Dict[str, Any]:
        """What an administrator needs to look at, rather than every key."""
        rows = [self._public(r) for r in self.repo.many()]
        active = [r for r in rows if r["state"] == "active"]
        return {
            "keys": rows,
            "active": len(active),
            "expired": sum(1 for r in rows if r["state"] == "expired"),
            "revoked": sum(1 for r in rows if r["state"] == "revoked"),
            # The two that matter. A key nobody has used is one nobody would
            # notice losing; a key expiring this week is an outage somebody
            # should schedule rather than meet.
            "never_used": [r for r in active if r["never_used"]],
            "expiring_soon": [r for r in active if r["expires_in_days"] <= 14],
        }
