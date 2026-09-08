"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Principals: people and services.

Passwords are PBKDF2-HMAC-SHA256 with a per-principal salt and a high iteration
count. Not because this is the last word in credential storage — a real
deployment should be behind SSO — but because a development default that stores
plaintext is a default somebody ships.

Comparison is constant-time throughout, including the miss. An authentication
path that returns faster for an unknown username than for a wrong password
leaks the user list, and the user list of a model risk platform is an
organisational chart.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any, Dict, List, Optional, Sequence

from core.authz.common import AuthzError
from core.authz.roles import conflicts, permissions_for
from core.evidence import EvidenceEngine
from core.log import get_logger
from db import PrincipalRepository

logger = get_logger(__name__)

#: The floor for a credential that can act on the register.
MIN_PASSWORD = 12

ITERATIONS = 200_000
ALGORITHM = "sha256"
# How long a successful Basic verification is trusted without re-deriving.
VERIFICATION_TTL = 60.0
# Compared against on a miss, so an unknown username costs the same as a wrong
# password. The value is irrelevant; the work it forces is the point.
DUMMY_SALT = "0" * 32


class PrincipalService:
    """Creates, authenticates and describes principals."""

    def __init__(self, principals: PrincipalRepository, evidence: EvidenceEngine,
                 iterations: int = ITERATIONS, verification_ttl: float = VERIFICATION_TTL):
        self.principals, self.evidence = principals, evidence
        #: Set at start-up when roles live in the register. Without one, roles
        #: come from `roles.py` — which is what every unit test constructing
        #: this directly relies on, and what a fresh instance uses before its
        #: first seed.
        self.roles = None
        self.iterations = iterations
        self.verification_ttl = verification_ttl
        # A deliberately expensive KDF is right for a login form and wrong for
        # an API called a thousand times a minute: at 200k iterations every
        # request would spend more time deriving a key than doing the work.
        # Successful verifications are therefore trusted for a short window,
        # keyed by a peppered digest of the presented secret rather than by the
        # secret itself, so the cache never holds a password. A revoked or
        # suspended principal is still re-read from the store on every request,
        # so the cache shortens the KDF and never the authorisation decision.
        self._pepper = secrets.token_bytes(32)
        self._verified: Dict[str, float] = {}

    # ------------------------------------------------------------ credentials
    def hash_password(self, password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(ALGORITHM, password.encode(), salt.encode(),
                                   self.iterations).hex()

    def _cache_key(self, username: str, password: str) -> str:
        return hmac.new(self._pepper, f"{username}\x00{password}".encode(),
                        hashlib.sha256).hexdigest()

    def _recently_verified(self, key: str, now: float) -> bool:
        expiry = self._verified.get(key)
        if expiry is None:
            return False
        if expiry < now:
            del self._verified[key]
            return False
        return True

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """The principal, or None. Never says which half was wrong."""
        now = time.time()
        row = self.principals.one(username=username)
        key = self._cache_key(username, password)

        if row is None or not row.get("password_hash"):
            # Do the work anyway: a fast negative is a username oracle.
            self.hash_password(password, DUMMY_SALT)
            logger.info("authentication failed for an unknown or passwordless principal")
            return None

        if not self._recently_verified(key, now):
            if not hmac.compare_digest(self.hash_password(password, row["password_salt"]),
                                       row["password_hash"]):
                logger.info("authentication failed for %s: password mismatch", username)
                return None
            self._verified[key] = now + self.verification_ttl

        # Status is re-read every time, cache or no cache: suspending a
        # principal must take effect on the next request, not in a minute.
        if row["status"] != "active":
            logger.warning("authentication refused for %s: status is %s",
                           username, row["status"])
            return None
        self.principals.set({"last_seen_at": now}, id=row["id"])
        return row

    def still_opens_the_door(self, username: str, password: str) -> bool:
        """Does this exact credential still authenticate? Asked, not attempted.

        The sign-in page wants to state whether the SHIPPED password still
        works, and start-up asks once. Calling `authenticate` to find out is
        wrong twice over: it logs "authentication failed for admin: password
        mismatch" on every boot of an instance whose password was properly
        changed — training the reader to ignore exactly the line that matters
        when it is real — and on an instance where it DOES still work it
        stamps `last_seen_at` and seeds the verification cache, so the
        register records a sign-in that never happened.

        So: compare, and touch nothing.
        """
        row = self.principals.one(username=username)
        if row is None or not row.get("password_hash"):
            return False
        return hmac.compare_digest(
            self.hash_password(password, row["password_salt"]), row["password_hash"])

    def forget(self, username: str) -> None:
        """Drop cached verifications. Called when a credential or status changes."""
        self._verified.clear()
        logger.info("cleared cached credential verifications after a change to %s",
                    username)

    # ---------------------------------------------------------------- create
    # ------------------------------------------------------------- the roles
    #
    # One source at a time. A role store means roles are in the register and a
    # bank can define one; without it they are the eight in `roles.py`. Reading
    # both would be two places permissions come from, and they disagree
    # eventually in the direction of permitting more.
    def _permissions_for(self, roles):
        if self.roles is not None:
            return self.roles.permissions_for(roles)
        return permissions_for(roles)

    def _conflicts(self, roles):
        if self.roles is not None:
            return self.roles.conflicts(roles)
        return conflicts(roles)

    def create(self, username: str, display_name: str, roles: Sequence[str],
               password: Optional[str] = None, kind: str = "person",
               email: Optional[str] = None,
               legal_entities: Optional[Sequence[str]] = None,
               domains: Optional[Sequence[str]] = None,
               actor: str = "system", allow_conflicts: bool = False) -> Dict[str, Any]:
        if self.principals.one(username=username):
            raise AuthzError("duplicate_principal",
                             f"a principal named '{username}' already exists",
                             "choose another username, or update the existing principal")
        roles = list(roles)
        # The same floor `set_password` applies. It did not apply here, so the
        # rule was enforceable only on a password CHANGE — every account was
        # created without it, and the one moment a weak password is most likely
        # to be chosen is the moment the account is made.
        if password is not None and len(password) < MIN_PASSWORD:
            raise AuthzError(
                "password_too_short",
                f"a password is at least {MIN_PASSWORD} characters",
                "choose a longer one; this is the credential for a principal "
                "that can act on the register")
        self._permissions_for(roles)                 # refuses an unknown role
        found_at_create = self._conflicts(roles)
        if found_at_create and not allow_conflicts:
            raise AuthzError(
                "incompatible_roles",
                f"{username} would hold incompatible roles: "
                f"{'; '.join(found_at_create)}",
                "split the duties between two principals, or grant explicitly "
                "with allow_conflicts if this is a deliberate, documented exception")

        salt = secrets.token_hex(16)
        row = {"username": username, "display_name": display_name, "kind": kind,
               "email": email, "roles": roles,
               "legal_entities": list(legal_entities or []),
               "domains": list(domains or []), "status": "active",
               "password_hash": self.hash_password(password, salt) if password else None,
               "password_salt": salt if password else None,
               "created_at": time.time(), "last_seen_at": None}
        with self.evidence.recording():
            self.principals.add(row)
            self.evidence.append("principal_created", "principal", row["id"],
                                 {"username": username, "roles": roles, "kind": kind,
                                  "legal_entities": row["legal_entities"],
                                  "domains": row["domains"],
                                  # The override, on the record. `allow_conflicts`
                                  # is the escape hatch the refusal itself
                                  # recommends -- and it was written nowhere, so
                                  # an estate could hold a dozen principals with
                                  # separated duties in one pair of hands and
                                  # nothing said any exception had been made.
                                  # An exception nobody can enumerate is not an
                                  # exception; it is a gap.
                                  "conflicts_allowed": found_at_create or None},
                                 actor=actor)
        return self.public(self.principals.one(id=row["id"]))

    def set_roles(self, username: str, roles: Sequence[str], actor: str = "system",
                  allow_conflicts: bool = False) -> Dict[str, Any]:
        row = self.require(username)
        roles = list(roles)
        self._permissions_for(roles)
        found = self._conflicts(roles)
        if found and not allow_conflicts:
            raise AuthzError("incompatible_roles",
                             f"{username} would hold incompatible roles: {'; '.join(found)}",
                             "split the duties between two principals")
        with self.evidence.recording():
            self.principals.set({"roles": roles}, id=row["id"])
            self.evidence.append("principal_roles_changed", "principal", row["id"],
                                 {"username": username, "from": row["roles"],
                                  "to": roles,
                                  # See `create`: the override is the record.
                                  "conflicts_allowed": found or None},
                                 actor=actor)
        return self.public(self.principals.one(id=row["id"]))

    def suspend(self, username: str, actor: str = "system") -> Dict[str, Any]:
        """Take a principal out of service. Not yourself, and not the last
        person who can undo it.

        The screen rendered a Suspend button on every active row including the
        administrator's own, and clicking it worked. Reinstating requires
        `principal:manage`, which the suspended account no longer has — so on a
        single-administrator instance the only route back was an UPDATE against
        `principal` in the database, which is precisely the act this platform
        exists to make unnecessary. The confirm dialog said "reinstating is a
        separate act, so this is not a one-way door", and it was true of
        everybody except the person clicking.
        """
        row = self.require(username)
        if username == actor:
            raise AuthzError(
                "self_suspension",
                "you cannot suspend yourself: reinstating needs "
                "'principal:manage', which you would no longer have",
                "ask another administrator to suspend you, or hand over first")
        if self._is_last_administrator(username):
            raise AuthzError(
                "last_administrator",
                f"{username} is the only active principal who can administer "
                f"principals, and suspending them would leave nobody able to "
                f"reinstate anyone",
                "give somebody else a role carrying 'principal:manage' first")
        with self.evidence.recording():
            self.principals.set({"status": "suspended"}, id=row["id"])
            self.forget(username)
            self.evidence.append("principal_suspended", "principal", row["id"],
                                 {"username": username}, actor=actor)
        return self.public(self.principals.one(id=row["id"]))

    def _is_last_administrator(self, username: str) -> bool:
        """Whether taking this principal out of service leaves nobody who can
        put anyone back.

        Only a principal who actually administers principals can be the last
        one — suspending an ordinary user on an instance that happens to have a
        single account is not a lockout, it is a Tuesday.
        """
        row = self.principals.one(username=username)
        if "principal:manage" not in self._permissions_for(
                (row or {}).get("roles") or []):
            return False
        others = [p for p in self.principals.many()
                  if p["username"] != username and p.get("status") == "active"]
        return not any("principal:manage" in self._permissions_for(
            p.get("roles") or []) for p in others)

    def reinstate(self, username: str, actor: str = "system") -> Dict[str, Any]:
        """Undo a suspension.

        Administration here was one-way: create, set roles, suspend. Suspending
        somebody by mistake — or suspending them for a fortnight's leave, which
        is the ordinary case — could not be undone through the product at all,
        so the only route back was an UPDATE against the database, which is
        exactly the thing this platform exists to make unnecessary.

        Recorded like every other governed act, so the pair reads as what it
        was: suspended on Tuesday, reinstated on Thursday, by whom.
        """
        row = self.require(username)
        if row["status"] == "active":
            raise AuthzError("already_active",
                             f"{username} is not suspended",
                             "no action is needed")
        with self.evidence.recording():
            self.principals.set({"status": "active"}, id=row["id"])
            self.evidence.append("principal_reinstated", "principal", row["id"],
                                 {"username": username, "from": row["status"]},
                                 actor=actor)
        logger.info("reinstated %s", username)
        return self.public(self.principals.one(id=row["id"]))

    def set_password(self, username: str, password: str,
                     actor: str = "system") -> Dict[str, Any]:
        """Set a principal's password, with a fresh salt.

        There was no way to do this. A forgotten password meant a new account,
        which loses the identity every prior act was recorded against — and an
        evidence chain whose actors are `j.okafor` and `j.okafor.2` is one
        nobody can read.

        The password is never logged and never lands on the chain; the *fact*
        that it was reset does, because an administrator who can silently take
        over an account is an administrator nobody can audit.
        """
        row = self.require(username)
        if not password or len(password) < MIN_PASSWORD:
            raise AuthzError(
                "password_too_short",
                f"a password is at least {MIN_PASSWORD} characters",
                "choose a longer one; this is the credential for a principal "
                "that can act on the register")
        salt = secrets.token_hex(16)
        with self.evidence.recording():
            self.principals.set({"password_hash": self.hash_password(password, salt),
                                 "password_salt": salt}, id=row["id"])
            self.forget(username)
            self.evidence.append("principal_password_set", "principal", row["id"],
                                 {"username": username, "by": actor}, actor=actor)
        logger.info("password set for %s by %s", username, actor)
        return self.public(self.principals.one(id=row["id"]))

    # ----------------------------------------------------------------- query
    def get(self, username: str) -> Optional[Dict[str, Any]]:
        return self.principals.one(username=username)

    def require(self, username: str) -> Dict[str, Any]:
        row = self.get(username)
        if row is None:
            raise AuthzError("no_such_principal", f"no principal '{username}'", "")
        return row

    def list(self) -> List[Dict[str, Any]]:
        return [self.public(r) for r in self.principals.many()]

    @staticmethod
    def public(row: Dict[str, Any]) -> Dict[str, Any]:
        """A principal without its credential material. The only shape that
        leaves this service, so a hash cannot escape through a new endpoint."""
        return {k: v for k, v in row.items()
                if k not in ("password_hash", "password_salt")}

    # ------------------------------------------------- directory identity
    def by_directory(self, issuer: str, subject: str) -> Optional[Dict[str, Any]]:
        """The principal a directory login resolves to, by the pair that is
        actually stable.

        The subject is the one claim an identity provider guarantees unique
        within its issuer. A username is a display convenience the directory may
        reuse, and resolving a login by username is how somebody signs in as an
        administrator by claiming to be called one.
        """
        if not issuer or not subject:
            return None
        row = self.principals.one(sso_issuer=issuer, sso_subject=subject)
        return self.public(row) if row else None

    def bind_directory(self, username: str, issuer: str, subject: str,
                       actor: str = "system") -> Dict[str, Any]:
        """Link this principal to a directory identity. Deliberate, and once."""
        row = self.require(username)
        if row.get("sso_subject") and (row.get("sso_issuer") != issuer
                                       or row.get("sso_subject") != subject):
            raise AuthzError(
                "already_linked",
                f"{username} is already bound to a different directory identity",
                "unlink it deliberately before binding another; silently "
                "rebinding would move an account between two humans")
        self.principals.set({"sso_issuer": issuer, "sso_subject": subject},
                            id=row["id"])
        logger.info("bound principal %s to %s subject %s", username, issuer, subject)
        return self.public(self.principals.one(id=row["id"]))

    # ------------------------------------------------------------- bootstrap
    def bootstrap(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Create the first administrator, once, if there are no principals.

        Returns None when principals already exist, so restarting a live
        deployment can never resurrect a development password.
        """
        if self.principals.many():
            return None
        logger.warning("no principals exist; creating bootstrap administrator '%s'. "
                       "Change this password before exposing the instance.", username)
        return self.create(username, "Administrator", ["admin"], password=password,
                           actor="system")
