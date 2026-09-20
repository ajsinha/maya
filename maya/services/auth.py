"""
Authentication (§12): database login with lockout, server-side sessions,
session tokens for the web tier, API keys and client credentials.

Both credential forms resolve to the same ``Principal``. A session token is
``maya_s_<secret>``; an API key is ``maya_<env>_<key_id>_<secret>``, where
the environment segment stops a UAT key being accepted in production and the
key id is the audit handle. Only hashes are stored: sha256 for session tokens
(they are 256-bit random), the recorded KDF for API-key secrets.

A service account never signs in. It holds either an API key, used as a bearer
credential, or an OAuth2 client credential, exchanged at the token endpoint for a
short-lived token that is no wider than the credential and dies with it.

The password rules, the per-key budget and the break-glass decision live in
``maya/security/`` so that this file stays what it says it is: the place where a
credential becomes a principal.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import secrets
import threading
import time
from typing import Any

from maya.core import kdf
from maya.core.errors import (
    ConflictError,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from maya.core.clock import utcnow
from maya.observability import caches
from maya.security import breakglass, keys as key_rules
from maya.security.authz import Principal, merge_capabilities
from maya.security.passwords import PasswordRules

DEFAULT_ADMIN_PASSWORD = "maya-dev-admin"
KEY_CACHE_TTL = 5.0
RESET_KIND = "password_reset"
logger = logging.getLogger(__name__)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuthService:
    """Logins, sessions, API keys and principal resolution."""

    def __init__(self, platform: Any) -> None:
        self.p = platform
        self._default_pw: tuple[str | None, bool] = (None, False)
        # token hash -> (monotonic expiry, principal); see _session_principal
        self._principals: dict[str, tuple[float, Principal]] = {}
        self.principal_ttl = float(
            platform.settings.get("auth.session.principal_cache_seconds", "2") or 0
        )
        platform.db.on_identity_change = self.forget_principals
        s = platform.settings
        self.idle = dt.timedelta(minutes=s.int("auth.session.idle_timeout_minutes", 30))
        self.absolute = dt.timedelta(hours=s.int("auth.session.absolute_timeout_hours", 12))
        self.concurrent = s.int("auth.session.concurrent_sessions", 3)
        self.rules = PasswordRules(s)
        self.min_length = self.rules.min_length
        self.glass_session = dt.timedelta(minutes=s.int("auth.break_glass.session_minutes", 60))
        self.token_life = dt.timedelta(minutes=s.int("auth.client_credentials.token_minutes", 60))
        self.budgets = key_rules.KeyBudgets()
        self.lock_attempts = s.int("auth.lockout.attempts", 5)
        self.lock_window = dt.timedelta(minutes=s.int("auth.lockout.window_minutes", 15))
        self.lock_duration = dt.timedelta(minutes=s.int("auth.lockout.duration_minutes", 30))
        self.env = s.environment
        self._key_cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        caches.register("session_principal")
        caches.register("api_key_secret")

    # -- login -------------------------------------------------------------
    def login(
        self,
        username: str,
        password: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
        channel: str = "web",
    ) -> dict[str, Any]:
        """Authenticate. A refusal is raised only *after* its record commits: raising
        inside the unit of work would roll back the failed-attempt count and its audit
        entry, and lockout would never engage."""
        refusal: NotAuthenticated | None = None
        result: dict[str, Any] = {}
        with self.p.uow(username) as uow:
            user = uow.repo("users").find_one(username=username)
            refusal = self._precheck(uow, user, username, ip, channel)
            if refusal is None and (
                not user["password_hash"]
                or not kdf.verify_password(password, user["password_hash"])
            ):
                self._record_failure(uow, user, utcnow(), ip, channel)
                refusal = NotAuthenticated("Invalid username or password")
            if refusal is None:
                refusal = self._age_refusal(uow, user, ip, channel)
            if refusal is None:
                result = self._succeed(uow, user, password, ip, user_agent, channel)
        if refusal is not None:
            raise refusal
        return result

    def _precheck(
        self, uow: Any, user: dict[str, Any] | None, username: str, ip: str | None, channel: str
    ) -> NotAuthenticated | None:
        sso_only = self.p.settings.auth_mode == "sso"
        designated = breakglass.is_designated(self.p.settings, username)
        if sso_only and not designated:
            uow.audit(
                "auth.login_refused",
                object_ref=f"user:{username}",
                ip=ip,
                channel=channel,
                detail={"reason": "password login disabled (sso)"},
            )
            return NotAuthenticated("This deployment signs people in with SSO only")
        if user is None or user["auth_source"] != "db" or user["is_service"]:
            uow.audit(
                "auth.login_failed",
                detail={"reason": "unknown user", "username": username},
                ip=ip,
                channel=channel,
            )
            return NotAuthenticated("Invalid username or password")
        if user["status"] != "active":
            uow.audit(
                "auth.login_refused",
                object_ref=f"user:{username}",
                detail={"status": user["status"]},
                ip=ip,
                channel=channel,
            )
            return NotAuthenticated(f"Account is {user['status']}")
        if user["locked_until"] and user["locked_until"] > utcnow():
            uow.audit("auth.login_locked", object_ref=f"user:{username}", ip=ip, channel=channel)
            return NotAuthenticated(
                "Account is locked after repeated failures; try again "
                f"after {user['locked_until']:%H:%M} UTC"
            )
        if sso_only:
            return self._break_glass_allowed(uow, user, ip, channel)
        return None

    def _break_glass_allowed(
        self, uow: Any, user: dict[str, Any], ip: str | None, channel: str
    ) -> NotAuthenticated | None:
        """A designated account is getting in under ``mode: sso``; make sure it is the
        account the configuration meant (§13.3). A name in ``auth.break_glass.users`` that
        is not an administrator's database account is a misconfiguration, and finding that
        out during an outage is exactly what must not happen — so the refusal says which
        of the two it is, durably."""
        roles = self.build_principal(uow, user["id"]).roles
        why = breakglass.why_refused(self.p.settings, user, roles)
        if why is None:
            return None
        uow.audit(
            "auth.break_glass_refused",
            object_ref=f"user:{user['username']}",
            ip=ip,
            channel=channel,
            detail={"reason": why},
            durable=True,
        )
        return NotAuthenticated(f"Break-glass sign-in is not available: {why}")

    def _age_refusal(
        self, uow: Any, user: dict[str, Any], ip: str | None, channel: str
    ) -> NotAuthenticated | None:
        """Refuse a password past ``auth.password.max_age_days`` (§12) and record that the
        account owes a change, so an administrator sees why the person cannot get in."""
        over = self.rules.past_its_age(user)
        if over is None:
            return None
        if not user["must_change_password"]:
            uow.repo("users").update(user["id"], {"must_change_password": True})
        uow.audit(
            "auth.login_refused",
            object_ref=f"user:{user['username']}",
            ip=ip,
            channel=channel,
            detail={"reason": "password expired", "days_over": over},
        )
        return NotAuthenticated(self.rules.age_refusal(over))

    def _succeed(
        self,
        uow: Any,
        user: dict[str, Any],
        password: str,
        ip: str | None,
        user_agent: str | None,
        channel: str,
    ) -> dict[str, Any]:
        changes: dict[str, Any] = {
            "failed_attempts": 0,
            "first_failed_at": None,
            "locked_until": None,
            "last_login_at": utcnow(),
        }
        if kdf.needs_rehash(user["password_hash"]):
            changes["password_hash"] = kdf.hash_password(password)
        uow.repo("users").update(user["id"], changes)
        mfa = self.p.sso.initial_mfa_state(uow, user)
        glass = breakglass.is_designated(self.p.settings, user["username"])
        token = self._open_session(
            uow,
            user,
            ip,
            user_agent,
            channel,
            mfa_state=mfa,
            absolute=self.glass_session if glass else None,
        )
        uow.audit(
            "auth.login",
            object_ref=f"user:{user['username']}",
            ip=ip,
            channel=channel,
            detail={"rehashed": "password_hash" in changes, "mfa": mfa, "break_glass": glass},
        )
        if glass:
            self._announce_break_glass(uow, user, ip, channel)
        return {
            "token": token,
            "username": user["username"],
            "must_change_password": user["must_change_password"],
            "default_password": password == DEFAULT_ADMIN_PASSWORD,
            "mfa": mfa,
            "break_glass": glass,
        }

    def _announce_break_glass(
        self, uow: Any, user: dict[str, Any], ip: str | None, channel: str
    ) -> None:
        """Make the emergency door loud: a durable audit entry of its own, an inbox notice
        for every other administrator, and a warning in the log the operator is watching
        during the outage. A break-glass sign-in nobody hears about is indistinguishable
        from a stolen password."""
        uow.audit(
            "auth.break_glass_login",
            object_ref=f"user:{user['username']}",
            ip=ip,
            channel=channel,
            detail={"mode": self.p.settings.auth_mode, "minutes": self.glass_session.seconds // 60},
            durable=True,
        )
        message = breakglass.notice(user["username"])
        for other in self._administrators(uow):
            if other["id"] != user["id"]:
                uow.repo("notifications").add(
                    {
                        "user_id": other["id"],
                        "kind": "break_glass",
                        "message": message,
                        "object_ref": f"user:{user['username']}",
                    }
                )
        logger.warning("%s ip=%s channel=%s", message, ip or "-", channel)

    @staticmethod
    def _administrators(uow: Any) -> list[dict[str, Any]]:
        role = uow.repo("roles").find_one(name=breakglass.ADMIN_ROLE)
        if role is None:
            return []
        ids = [ur["user_id"] for ur in uow.repo("user_roles").list(role_id=role["id"])]
        return uow.repo("users").list(id__in=ids, status="active") if ids else []

    def _record_failure(
        self, uow: Any, user: dict[str, Any], now: dt.datetime, ip: str | None, channel: str
    ) -> None:
        first = user["first_failed_at"]
        count = user["failed_attempts"] + 1 if first and now - first < self.lock_window else 1
        changes: dict[str, Any] = {
            "failed_attempts": count,
            "first_failed_at": first if count > 1 else now,
        }
        if count >= self.lock_attempts:
            changes["locked_until"] = now + self.lock_duration
            uow.audit("auth.lockout", object_ref=f"user:{user['username']}", ip=ip, channel=channel)
        uow.repo("users").update(user["id"], changes)
        uow.audit(
            "auth.login_failed",
            object_ref=f"user:{user['username']}",
            ip=ip,
            channel=channel,
            detail={"attempt": count},
        )

    def _open_session(
        self,
        uow: Any,
        user: dict[str, Any],
        ip: str | None,
        user_agent: str | None,
        channel: str,
        *,
        auth_method: str = "password",
        mfa_state: str = "ok",
        absolute: dt.timedelta | None = None,
        idle: dt.timedelta | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        token = "maya_s_" + secrets.token_urlsafe(32)
        now = utcnow()
        life = absolute or self.absolute
        self._enforce_session_cap(uow, user)
        uow.repo("sessions").add(
            {
                "user_id": user["id"],
                "token_hash": _sha(token),
                "channel": channel,
                "auth_method": auth_method,
                "mfa_state": mfa_state,
                "last_seen_at": now,
                "expires_at": now + min(idle or self.idle, life),
                "absolute_expires_at": now + life,
                "ip": ip,
                "user_agent": (user_agent or "")[:500],
                **(extra or {}),
            }
        )
        return token

    def _enforce_session_cap(self, uow: Any, user: dict[str, Any]) -> None:
        """``auth.session.concurrent_sessions`` (§12): a person's oldest session makes way
        for their newest, rather than the newest being refused — someone whose laptop went
        to sleep three times must still be able to sign in.

        Service accounts are exempt. A fleet of workers sharing one credential holds one
        token each by design, and evicting them in turn would make a deployment flap."""
        if self.concurrent <= 0 or user["is_service"]:
            return
        now = utcnow()
        live = [
            s
            for s in uow.repo("sessions").list(
                user_id=user["id"], revoked_at__isnull=True, order_by=["created_at"]
            )
            if s["expires_at"] > now and s["absolute_expires_at"] > now
        ]
        for sess in live[: max(0, len(live) - self.concurrent + 1)]:
            uow.repo("sessions").update(sess["id"], {"revoked_at": now})
            uow.audit(
                "auth.session_evicted",
                object_ref=f"session:{sess['id']}",
                detail={
                    "username": user["username"],
                    "reason": f"over the {self.concurrent}-session cap",
                },
            )
            uow.after_commit(self.forget_principals)

    @staticmethod
    def token_hash(token: str) -> str:
        """How a session token is stored: never the token itself."""
        return _sha(token)

    def forget_principals(self) -> None:
        """Access changed in this process: resolve every session afresh."""
        self._principals.clear()

    def logout(self, token: str) -> None:
        self._principals.pop(_sha(token), None)
        with self.p.uow() as uow:
            sess = uow.repo("sessions").find_one(token_hash=_sha(token))
            if sess and not sess["revoked_at"]:
                uow.repo("sessions").update(sess["id"], {"revoked_at": utcnow()})
                uow.audit("auth.logout", object_ref=f"session:{sess['id']}")

    # -- principal resolution -------------------------------------------------
    def principal(
        self, token: str | None, *, ip: str | None = None, path: str | None = None
    ) -> Principal:
        if not token:
            raise NotAuthenticated("Authentication required: send a bearer token or API key")
        if token.startswith("maya_s_"):
            return self._session_principal(token, path)
        if token.startswith("maya_"):
            return self._key_principal(token, ip)
        raise NotAuthenticated("Unrecognised credential")

    def _session_principal(self, token: str, path: str | None = None) -> Principal:
        """The principal a session token stands for.

        One web page makes several internal API calls, each resolving the same session;
        a fully signed-in session's principal is therefore kept for
        ``auth.session.principal_cache_seconds`` (default 2; 0 turns it off). The price,
        accepted deliberately: a sign-out in *another* process, a revocation, or a role
        change reaches a session at most that many seconds late. A sign-out in this
        process clears the entry at once, and sessions still owing a second factor are
        never kept."""
        key = _sha(token)
        hit = self._principals.get(key)
        if hit and hit[0] > time.monotonic():
            caches.hit("session_principal")
            return hit[1]
        caches.miss("session_principal")
        principal, fully_signed_in = self._resolve_session(token, path)
        if self.principal_ttl > 0 and fully_signed_in:
            if len(self._principals) > 10_000:
                self._principals.clear()
            self._principals[key] = (time.monotonic() + self.principal_ttl, principal)
        return principal

    def _resolve_session(self, token: str, path: str | None = None) -> tuple[Principal, bool]:
        """The principal behind a session token, or the reason there is none.

        An expired session is closed as it is found, and the refusal is raised only after
        that closure has committed: raising inside the unit of work would roll the
        revocation back, and every later request would have to expire the session again."""
        from maya.services.sso import MFA_OPEN_PATHS

        expired = False
        with self.p.uow() as uow:
            sess = uow.repo("sessions").find_one(token_hash=_sha(token))
            now = utcnow()
            if sess is None or sess["revoked_at"]:
                raise NotAuthenticated("Session has ended; log in again")
            if sess["mfa_state"] != "ok" and not (path or "").endswith(MFA_OPEN_PATHS):
                raise NotAuthenticated(
                    "A second factor is required: "
                    + (
                        "enter the code from your authenticator"
                        if sess["mfa_state"] == "challenge"
                        else "enroll an authenticator first"
                    ),
                    mfa=sess["mfa_state"],
                )
            if sess["expires_at"] < now or sess["absolute_expires_at"] < now:
                uow.repo("sessions").update(sess["id"], {"revoked_at": now})
                expired = True
            else:
                if not sess["last_seen_at"] or (now - sess["last_seen_at"]).total_seconds() > 30:
                    uow.repo("sessions").update(
                        sess["id"],
                        {
                            "last_seen_at": now,
                            "expires_at": min(now + self.idle, sess["absolute_expires_at"]),
                        },
                    )
                principal = self.build_principal(uow, sess["user_id"], channel=sess["channel"])
                if sess["api_key_id"]:
                    principal = self._as_credential(uow, principal, sess["api_key_id"])
        if expired:
            raise NotAuthenticated("Session expired; log in again")
        return principal, sess["mfa_state"] == "ok"

    def _as_credential(self, uow: Any, p: Principal, key_id: str) -> Principal:
        """A token from the client-credentials grant carries the credential's authority and
        not the service account's: the credential can be scoped more narrowly than the
        account, and revoking it must kill the tokens it issued at once (§12)."""
        row = uow.repo("api_keys").find_one(key_id=key_id)
        if row is None or row["revoked_at"] or row["expires_at"] < utcnow():
            raise NotAuthenticated("The credential behind this token is revoked or expired")
        self.budgets.charge(key_id, row["rate_per_minute"])
        p.principal_type = "api_key"
        return self._scope_to_key(uow, p, row)

    def _key_principal(self, key: str, ip: str | None) -> Principal:
        parts = key.split("_", 3)
        if len(parts) != 4:
            raise NotAuthenticated("Malformed API key")
        _, env, key_id, secret = parts
        if env != self.env:
            raise NotAuthenticated(f"This API key is for '{env}', not '{self.env}'")
        with self.p.uow() as uow:
            row = uow.repo("api_keys").find_one(key_id=key_id)
            now = utcnow()
            if row is None or row["revoked_at"] or row["expires_at"] < now:
                raise NotAuthenticated("API key is unknown, revoked or expired")
            if row["kind"] == "client":
                raise NotAuthenticated(
                    "This is a client credential, not an API key: exchange it for a token "
                    "at POST /auth/token with grant_type=client_credentials"
                )
            if not self._key_secret_ok(key_id, secret, row["secret_hash"]):
                uow.audit(
                    "auth.api_key_failed", object_ref=f"api_key:{key_id}", ip=ip, durable=True
                )
                raise NotAuthenticated("API key is invalid")
            if row["cidrs"] and not _ip_allowed(ip, row["cidrs"]):
                raise NotAuthenticated("API key is not allowed from this address")
            self.budgets.charge(key_id, row["rate_per_minute"])
            if not row["last_used_at"] or (now - row["last_used_at"]).total_seconds() > 60:
                uow.repo("api_keys").update(row["id"], {"last_used_at": now})
            p = self.build_principal(uow, row["user_id"], channel="api", principal_type="api_key")
            return self._scope_to_key(uow, p, row)

    def _scope_to_key(self, uow: Any, p: Principal, row: dict[str, Any]) -> Principal:
        """Narrow a principal to what one credential carries: its role subset, its
        namespaces and its action allowlist."""
        if row["roles"]:
            p.roles = [r for r in p.roles if r in row["roles"]]
            p.capabilities = merge_capabilities(self._role_caps(uow, p.roles))
        p.key_namespaces, p.key_actions = row["namespaces"], row["actions"]
        return p

    def _key_secret_ok(self, key_id: str, secret: str, stored: str) -> bool:
        probe = _sha(secret)
        with self._lock:
            cached = self._key_cache.get(key_id)
            if cached and cached[1] == probe and time.monotonic() - cached[0] < KEY_CACHE_TTL:
                caches.hit("api_key_secret")
                return True
        caches.miss("api_key_secret")
        ok = kdf.verify_password(secret, stored)
        if ok:
            with self._lock:
                self._key_cache[key_id] = (time.monotonic(), probe)
        return ok

    def build_principal(
        self, uow: Any, user_id: str, *, channel: str = "api", principal_type: str = "user"
    ) -> Principal:
        user = uow.repo("users").require(user_id)
        if user["status"] != "active":
            raise NotAuthenticated(f"Account is {user['status']}")
        role_ids = [ur["role_id"] for ur in uow.repo("user_roles").list(user_id=user_id)]
        group_ids = [g["group_id"] for g in uow.repo("group_members").list(user_id=user_id)]
        for gid in group_ids:
            role_ids += [gr["role_id"] for gr in uow.repo("group_roles").list(group_id=gid)]
        roles = uow.repo("roles").list(id__in=set(role_ids)) if role_ids else []
        groups = [g["name"] for g in uow.repo("groups").list(id__in=group_ids)] if group_ids else []
        return Principal(
            user_id=user_id,
            username=user["username"],
            roles=sorted(r["name"] for r in roles),
            capabilities=merge_capabilities([r["capabilities"] for r in roles]),
            groups=groups,
            principal_type=principal_type,
            channel=channel,
            desk=user.get("desk"),
        )

    @staticmethod
    def _role_caps(uow: Any, names: list[str]) -> list[dict[str, str]]:
        return [r["capabilities"] for r in uow.repo("roles").list(name__in=names)] if names else []

    # -- passwords -------------------------------------------------------------
    def check_policy(self, password: str) -> None:
        """Shape alone: what a password must look like for anyone. History belongs to an
        account, so a caller who knows whose password this is uses ``_accept_password``."""
        self.rules.check(password)

    def _accept_password(self, uow: Any, user: dict[str, Any], new: str) -> dict[str, Any]:
        """Check the new password against the whole policy and return the changes that set
        it, remembering the one it replaces."""
        self.rules.check(new)
        self.rules.check_history(uow, user, new)
        self.rules.remember(uow, user)
        return {
            "password_hash": kdf.hash_password(new),
            "must_change_password": False,
            "password_changed_at": utcnow(),
        }

    def change_password(self, p: Principal, old: str, new: str) -> None:
        with self.p.uow(p.username) as uow:
            user = uow.repo("users").require(p.user_id)
            if not kdf.verify_password(old, user["password_hash"] or ""):
                raise NotAuthenticated("Current password is incorrect")
            if new == old:
                raise ValidationFailed("The new password must differ from the old one")
            uow.repo("users").update(p.user_id, self._accept_password(uow, user, new))
            uow.audit("auth.password_changed", object_ref=f"user:{p.username}")

    # -- password reset (§12: single-use, time-limited tokens) --------------------
    def request_password_reset(
        self, username: str, *, ip: str | None = None, channel: str = "web"
    ) -> None:
        """Someone says they cannot get in. Every administrator is told, and the answer to
        the caller is the same whether or not the account exists — a reset form that says
        "no such user" is a user directory for anyone who asks.

        MAYA has no mailer (§25 lists email among the integrations that do not exist), so
        the token itself is issued by an administrator with ``issue_password_reset`` and
        handed over out of band. Pretending to send an email would be worse than saying so.
        """
        with self.p.uow("reset") as uow:
            user = uow.repo("users").find_one(username=username)
            uow.audit(
                "auth.password_reset_requested",
                object_ref=f"user:{username}",
                ip=ip,
                channel=channel,
                detail={"known": user is not None},
            )
            if user is None or user["auth_source"] != "db":
                return
            for admin in self._administrators(uow):
                # one unread notice per account: the endpoint is open, and a caller who
                # asks a thousand times must not be able to bury an administrator's inbox
                if uow.repo("notifications").find_one(
                    user_id=admin["id"],
                    kind="password_reset",
                    object_ref=f"user:{username}",
                    read_at__isnull=True,
                ):
                    continue
                uow.repo("notifications").add(
                    {
                        "user_id": admin["id"],
                        "kind": "password_reset",
                        "message": f"'{username}' asked for a password reset; issue a "
                        "reset token and hand it over in person.",
                        "object_ref": f"user:{username}",
                    }
                )

    def issue_password_reset(self, p: Principal, username: str) -> dict[str, Any]:
        """A single-use, time-limited reset token, shown once to the administrator issuing
        it. Only its hash is stored, so a stolen database yields no reset."""
        self.p.access.require_capability(p, "users", "U")
        token = secrets.token_urlsafe(32)
        expires = utcnow() + self.rules.reset_token_life
        with self.p.uow(p.username) as uow:
            user = uow.repo("users").find_one(username=username)
            if user is None:
                raise NotFound(f"User '{username}' does not exist")
            if user["auth_source"] != "db":
                raise ValidationFailed(
                    f"'{username}' signs in through the identity provider; a MAYA password "
                    "reset would do nothing"
                )
            uow.repo("auth_challenges").add(
                {
                    "kind": RESET_KIND,
                    "handle": _sha(token),
                    "user_id": user["id"],
                    "expires_at": expires,
                    "detail": {"issued_by": p.username},
                }
            )
            uow.audit(
                "auth.password_reset_issued",
                object_ref=f"user:{username}",
                detail={"minutes": int(self.rules.reset_token_life.total_seconds() // 60)},
            )
        return {
            "username": username,
            "token": token,
            "expires_at": expires,
            "shown_once": True,
        }

    def complete_password_reset(
        self, token: str, new_password: str, *, ip: str | None = None, channel: str = "web"
    ) -> dict[str, Any]:
        """Redeem a reset token: once, before it expires, and never again afterwards.

        Every session of the account ends with the reset. Whoever locked the owner out
        may be holding one, and a password nobody can use is not a recovery."""
        refusal: NotAuthenticated | None = None
        username = ""
        with self.p.uow("reset") as uow:
            row = uow.repo("auth_challenges").find_one(kind=RESET_KIND, handle=_sha(token))
            problem = self._reset_problem(row)
            if problem or row is None:
                uow.audit(
                    "auth.password_reset_refused",
                    ip=ip,
                    channel=channel,
                    detail={"reason": problem or "unknown token"},
                    durable=True,
                )
                refusal = NotAuthenticated(problem or "That reset link is not valid")
            else:
                user = uow.repo("users").require(row["user_id"])
                username = user["username"]
                changes = self._accept_password(uow, user, new_password)
                uow.repo("users").update(
                    user["id"],
                    {
                        **changes,
                        "failed_attempts": 0,
                        "first_failed_at": None,
                        "locked_until": None,
                    },
                )
                uow.repo("auth_challenges").update(row["id"], {"consumed_at": utcnow()})
                ended = self._end_all_sessions(uow, user["id"])
                uow.audit(
                    "auth.password_reset_completed",
                    object_ref=f"user:{username}",
                    ip=ip,
                    channel=channel,
                    detail={"sessions_ended": ended},
                    durable=True,
                )
        if refusal is not None:
            raise refusal
        self.forget_principals()
        return {"username": username, "ok": True}

    @staticmethod
    def _reset_problem(row: dict[str, Any] | None) -> str | None:
        if row is None:
            return None
        if row["consumed_at"] is not None:
            return "That reset link has already been used; ask for another"
        if row["expires_at"] < utcnow():
            return "That reset link has expired; ask for another"
        return None

    @staticmethod
    def _end_all_sessions(uow: Any, user_id: str) -> int:
        now = utcnow()
        rows = uow.repo("sessions").list(user_id=user_id, revoked_at__isnull=True)
        for sess in rows:
            uow.repo("sessions").update(sess["id"], {"revoked_at": now})
        return len(rows)

    def default_admin_password_active(self) -> bool:
        """Does 'admin' still have the shipped password? The answer is remembered per
        stored hash, so the deliberately slow key derivation runs once per change."""
        with self.p.uow() as uow:
            admin = uow.repo("users").find_one(username="admin")
        stored = admin["password_hash"] if admin else None
        if not stored:
            return False
        if self._default_pw[0] != stored:
            self._default_pw = (stored, kdf.verify_password(DEFAULT_ADMIN_PASSWORD, stored))
        return self._default_pw[1]

    # -- API keys ----------------------------------------------------------------
    def create_api_key(
        self,
        p: Principal,
        *,
        name: str,
        roles: list[str] | None = None,
        namespaces: list[str] | None = None,
        actions: list[str] | None = None,
        cidrs: list[str] | None = None,
        days: int = 90,
        rate_per_minute: int = 0,
        for_user: str | None = None,
    ) -> dict[str, Any]:
        """Issue a key. ``for_user`` names a service account to issue it *for*: §11.5 asks
        service accounts to be principals with credentials, and until this existed a key
        could be created only by its holder, which a service account cannot do because it
        never signs in."""
        with self.p.uow(p.username) as uow:
            holder = self._key_holder(uow, p, for_user)
            secret, row = self._issue_key(
                uow,
                p,
                holder,
                kind="key",
                name=name,
                roles=roles or [],
                namespaces=namespaces or [],
                actions=actions or [],
                cidrs=cidrs or [],
                days=days,
                rate_per_minute=rate_per_minute,
            )
        return {
            **row,
            "api_key": f"maya_{self.env}_{row['key_id']}_{secret}",
            "shown_once": True,
        }

    def _key_holder(self, uow: Any, p: Principal, for_user: str | None) -> dict[str, Any]:
        """Whose key this is. Someone else's is allowed only for a service account, and
        only for a caller who may manage users — a person's credential is theirs alone."""
        if for_user is None or for_user == p.username:
            return uow.repo("users").require(p.user_id)
        self.p.access.require_capability(p, "users", "U")
        target = uow.repo("users").find_one(username=for_user)
        if target is None:
            raise NotFound(f"User '{for_user}' does not exist")
        if not target["is_service"]:
            raise PermissionDenied(
                f"'{for_user}' is a person, not a service account: only they can create "
                "their own credentials"
            )
        return target

    def _issue_key(
        self,
        uow: Any,
        p: Principal,
        holder: dict[str, Any],
        *,
        kind: str,
        name: str,
        roles: list[str],
        namespaces: list[str],
        actions: list[str],
        cidrs: list[str],
        days: int,
        rate_per_minute: int,
    ) -> tuple[str, dict[str, Any]]:
        """The common part of every credential: a role subset nobody widens, an expiry the
        namespace policy permits, a hashed secret and an audit entry."""
        max_days = self._max_key_days(uow, namespaces)
        if days < 1 or days > max_days:
            raise ValidationFailed(f"Key expiry must be 1–{max_days} days")
        self._check_roles(uow, p, holder, roles)
        if rate_per_minute < 0:
            raise ValidationFailed("A key's rate limit is requests a minute, or 0 for none")
        key_id, secret = secrets.token_hex(6), secrets.token_urlsafe(24).replace("_", "-")
        row = uow.repo("api_keys").add(
            {
                "key_id": key_id,
                "user_id": holder["id"],
                "name": name,
                "env": self.env,
                "kind": kind,
                "secret_hash": kdf.hash_password(secret),
                "roles": roles,
                "namespaces": namespaces,
                "actions": actions,
                "cidrs": cidrs,
                "rate_per_minute": rate_per_minute
                or self.p.settings.int("auth.api_keys.rate_per_minute", 0),
                "expires_at": utcnow() + dt.timedelta(days=days),
            }
        )
        uow.audit(
            "auth.api_key_created",
            object_ref=f"api_key:{key_id}",
            detail={
                "name": name,
                "kind": kind,
                "roles": roles,
                "days": days,
                "holder": holder["username"],
                "rate_per_minute": row["rate_per_minute"],
            },
        )
        row.pop("secret_hash")
        row["username"] = holder["username"]
        return secret, row

    def _check_roles(
        self, uow: Any, p: Principal, holder: dict[str, Any], roles: list[str]
    ) -> None:
        """No credential widens anyone: not past its holder's roles, and — §11.5, "a user
        can grant a service account no more access than they hold" — not past the caller's.

        An administrator is the exception on that second rule, and only when issuing for
        someone else: they already decide who holds which role, so refusing them a
        credential for a role the account holds would stop nothing."""
        extra = set(roles) - set(p.roles)
        if extra and not (p.is_admin and holder["id"] != p.user_id):
            raise PermissionDenied(
                "A key cannot carry roles you do not hold: " + ", ".join(sorted(extra))
            )
        if holder["id"] != p.user_id:
            held = set(self.build_principal(uow, holder["id"]).roles)
            beyond = set(roles) - held
            if beyond:
                raise PermissionDenied(
                    f"'{holder['username']}' does not hold: " + ", ".join(sorted(beyond))
                )

    def _max_key_days(self, uow: Any, namespaces: list[str]) -> int:
        """The longest life a key may have: the global maximum, tightened by every namespace
        it is scoped to (§12 "no further out than the namespace policy permits")."""
        days = self.p.settings.int("auth.api_keys.max_days", 365)
        for name in namespaces:
            ns = uow.repo("namespaces").find_one(name=name)
            if ns and ns["api_key_max_days"]:
                days = min(days, int(ns["api_key_max_days"]))
        return days

    def rotate_api_key(
        self, p: Principal, key_id: str, *, overlap_days: int | None = None, days: int | None = None
    ) -> dict[str, Any]:
        """Issue a successor with the same authority, let both work for the overlap window,
        and retire the old one at the end of it (§12 "creating, rotating, scoping and
        revoking keys is itself an SDK capability").

        The overlap is what makes rotation possible without an outage: the caller deploys
        the new secret while the old one still answers, then nothing has to be timed."""
        overlap = (
            self.p.settings.int("auth.api_keys.rotation_overlap_days", 7)
            if overlap_days is None
            else overlap_days
        )
        if overlap < 0:
            raise ValidationFailed("The overlap window is a number of days, 0 or more")
        with self.p.uow(p.username) as uow:
            old = self._own_key(uow, p, key_id)
            if old["successor_key_id"]:
                raise ConflictError(
                    f"Key '{key_id}' was already rotated; its successor is "
                    f"'{old['successor_key_id']}'"
                )
            life = days if days is not None else max((old["expires_at"] - utcnow()).days, 1)
            max_days = self._max_key_days(uow, old["namespaces"])
            if life < 1 or life > max_days:
                raise ValidationFailed(f"Key expiry must be 1–{max_days} days")
            secret = secrets.token_urlsafe(24).replace("_", "-")
            new_id = secrets.token_hex(6)
            row = uow.repo("api_keys").add(
                key_rules.successor(
                    old, key_id=new_id, secret_hash=kdf.hash_password(secret), days=life
                )
            )
            retires = key_rules.retirement(old, overlap)
            uow.repo("api_keys").update(
                old["id"],
                {"successor_key_id": new_id, "rotated_at": utcnow(), "expires_at": retires},
            )
            uow.audit(
                "auth.api_key_rotated",
                object_ref=f"api_key:{key_id}",
                detail={"successor": new_id, "retires_at": retires, "overlap_days": overlap},
            )
        row.pop("secret_hash", None)
        return {
            **row,
            "api_key": f"maya_{self.env}_{new_id}_{secret}",
            "shown_once": True,
            "retired": key_id,
            "retires_at": retires,
        }

    def _own_key(self, uow: Any, p: Principal, key_id: str) -> dict[str, Any]:
        row = uow.repo("api_keys").find_one(key_id=key_id)
        if row is None:
            raise NotFound(f"API key '{key_id}' does not exist")
        if row["user_id"] != p.user_id and not p.is_admin:
            raise PermissionDenied("You can manage only your own keys")
        if row["revoked_at"]:
            raise ValidationFailed(f"Key '{key_id}' is revoked; create a new one instead")
        return row

    def list_api_keys(
        self, p: Principal, all_users: bool = False, kind: str = "key"
    ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            where: dict[str, Any] = {"kind": kind} if kind else {}
            if not all_users:
                where["user_id"] = p.user_id
            rows = uow.repo("api_keys").list(order_by=["-created_at"], **where)
            names = {u["id"]: u["username"] for u in uow.repo("users").list()}
        for r in rows:
            r.pop("secret_hash", None)
            r["username"] = names.get(r["user_id"])
        return rows

    def api_key_report(self, p: Principal, all_users: bool = False) -> list[dict[str, Any]]:
        """Keys wanting attention: unused for too long, near expiry, or already rotated
        (§12 "keys unused for a configurable period are reported for revocation" and the
        rotation reminder)."""
        rows = self.list_api_keys(p, all_users=all_users and p.is_admin, kind="")
        return key_rules.report(
            rows,
            unused_days=self.p.settings.int("auth.api_keys.unused_days", 90),
            remind_days=self.p.settings.int("auth.api_keys.remind_days_before_expiry", 14),
        )

    def revoke_api_key(self, p: Principal, key_id: str) -> None:
        with self.p.uow(p.username) as uow:
            row = uow.repo("api_keys").find_one(key_id=key_id)
            if row is None:
                raise NotFound(f"API key '{key_id}' does not exist")
            if row["user_id"] != p.user_id and not p.is_admin:
                raise PermissionDenied("You can revoke only your own keys")
            uow.repo("api_keys").update(row["id"], {"revoked_at": utcnow()})
            # a client credential's tokens are no wider than the credential, so they go too
            for sess in uow.repo("sessions").list(api_key_id=key_id, revoked_at__isnull=True):
                uow.repo("sessions").update(sess["id"], {"revoked_at": utcnow()})
            uow.audit("auth.api_key_revoked", object_ref=f"api_key:{key_id}")
        with self._lock:
            self._key_cache.pop(key_id, None)
        self.budgets.forget(key_id)
        self.forget_principals()

    # -- client credentials for service accounts (§12) -----------------------------
    def create_client_credential(
        self,
        p: Principal,
        *,
        username: str,
        name: str = "client credential",
        roles: list[str] | None = None,
        namespaces: list[str] | None = None,
        actions: list[str] | None = None,
        days: int = 90,
        rate_per_minute: int = 0,
    ) -> dict[str, Any]:
        """An OAuth2 client credential for a service account: a client id and a secret shown
        once, with the mandatory expiry §11.5 asks of every service-account credential."""
        with self.p.uow(p.username) as uow:
            holder = self._key_holder(uow, p, username)
            if holder["id"] == p.user_id:
                raise ValidationFailed(
                    "Client credentials belong to service accounts; use an API key for yourself"
                )
            secret, row = self._issue_key(
                uow,
                p,
                holder,
                kind="client",
                name=name,
                roles=roles or [],
                namespaces=namespaces or [],
                actions=actions or [],
                cidrs=[],
                days=days,
                rate_per_minute=rate_per_minute,
            )
        return {
            **row,
            "client_id": row["key_id"],
            "client_secret": secret,
            "shown_once": True,
            "token_url": "/api/v1/auth/token",
        }

    def list_client_credentials(self, p: Principal) -> list[dict[str, Any]]:
        self.p.access.require_capability(p, "users", "R")
        return self.list_api_keys(p, all_users=True, kind="client")

    def client_credentials_token(
        self, client_id: str, client_secret: str, *, ip: str | None = None
    ) -> dict[str, Any]:
        """The OAuth2 client-credentials grant: a service account's credential for a
        short-lived bearer token carrying that credential's authority and no more.

        No refresh token: the credential itself is the long-lived secret, and asking for a
        new token is one request."""
        refusal: NotAuthenticated | None = None
        out: dict[str, Any] = {}
        with self.p.uow("client_credentials") as uow:
            row = uow.repo("api_keys").find_one(key_id=client_id, kind="client")
            now = utcnow()
            bad = (
                row is None
                or row["revoked_at"] is not None
                or row["expires_at"] < now
                or not kdf.verify_password(client_secret, row["secret_hash"])
            )
            if bad or row is None:
                uow.audit(
                    "auth.client_credentials_refused",
                    object_ref=f"api_key:{client_id}",
                    ip=ip,
                    detail={"reason": "unknown, revoked, expired or wrong secret"},
                    durable=True,
                )
                refusal = NotAuthenticated("invalid_client: unknown or expired client credential")
            else:
                user = uow.repo("users").require(row["user_id"])
                if user["status"] != "active":
                    refusal = NotAuthenticated(f"invalid_client: the account is {user['status']}")
                else:
                    uow.repo("api_keys").update(row["id"], {"last_used_at": now})
                    life = min(self.token_life, row["expires_at"] - now)
                    token = self._open_session(
                        uow,
                        user,
                        ip,
                        f"client_credentials/{client_id}",
                        "api",
                        auth_method="client_credentials",
                        absolute=life,
                        idle=life,  # a machine token is not idle between two calls an hour apart
                        extra={"api_key_id": client_id},
                    )
                    uow.audit(
                        "auth.client_credentials_granted",
                        object_ref=f"api_key:{client_id}",
                        ip=ip,
                        detail={"username": user["username"], "seconds": int(life.total_seconds())},
                    )
                    out = {
                        "access_token": token,
                        "token_type": "Bearer",
                        "expires_in": int(life.total_seconds()),
                    }
        if refusal is not None:
            raise refusal
        return out

    # -- sessions ------------------------------------------------------------------
    def list_sessions(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            rows = uow.repo("sessions").list(revoked_at__isnull=True, order_by=["-created_at"])
            names = {u["id"]: u["username"] for u in uow.repo("users").list()}
        for r in rows:
            r.pop("token_hash", None)
            r["username"] = names.get(r["user_id"])
        return rows

    def terminate_session(self, p: Principal, session_id: str) -> None:
        with self.p.uow(p.username) as uow:
            uow.repo("sessions").update(session_id, {"revoked_at": utcnow()})
            uow.audit("auth.session_terminated", object_ref=f"session:{session_id}")


def _ip_allowed(ip: str | None, cidrs: list[str]) -> bool:
    import ipaddress

    if not ip:
        return False
    addr = ipaddress.ip_address(ip)
    return any(addr in ipaddress.ip_network(c, strict=False) for c in cidrs)
