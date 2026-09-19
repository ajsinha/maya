"""
Authentication (§12): database login with lockout, server-side sessions,
session tokens for the web tier, and API keys.

Both credential forms resolve to the same ``Principal``. A session token is
``maya_s_<secret>``; an API key is ``maya_<env>_<key_id>_<secret>``, where
the environment segment stops a UAT key being accepted in production and the
key id is the audit handle. Only hashes are stored: sha256 for session tokens
(they are 256-bit random), the recorded KDF for API-key secrets.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import threading
import time
from typing import Any

from maya.core import kdf
from maya.core.errors import (NotAuthenticated, NotFound, PermissionDenied, ValidationFailed)
from maya.core.clock import utcnow
from maya.security.authz import Principal, merge_capabilities

DEFAULT_ADMIN_PASSWORD = "maya-dev-admin"
KEY_CACHE_TTL = 5.0


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuthService:
    """Logins, sessions, API keys and principal resolution."""

    def __init__(self, platform: Any) -> None:
        self.p = platform
        self._default_pw: tuple[str | None, bool] = (None, False)
        # token hash -> (monotonic expiry, principal); see _session_principal
        self._principals: dict[str, tuple[float, Principal]] = {}
        self.principal_ttl = float(platform.settings.get(
            "auth.session.principal_cache_seconds", "2") or 0)
        platform.db.on_identity_change = self.forget_principals
        s = platform.settings
        self.idle = dt.timedelta(minutes=s.int("auth.session.idle_timeout_minutes", 30))
        self.absolute = dt.timedelta(hours=s.int("auth.session.absolute_timeout_hours", 12))
        self.min_length = s.int("auth.password.min_length", 12)
        self.lock_attempts = s.int("auth.lockout.attempts", 5)
        self.lock_window = dt.timedelta(minutes=s.int("auth.lockout.window_minutes", 15))
        self.lock_duration = dt.timedelta(minutes=s.int("auth.lockout.duration_minutes", 30))
        self.env = s.environment
        self._key_cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    # -- login -------------------------------------------------------------
    def login(self, username: str, password: str, *, ip: str | None = None,
              user_agent: str | None = None, channel: str = "web") -> dict[str, Any]:
        """Authenticate. A refusal is raised only *after* its record commits: raising
        inside the unit of work would roll back the failed-attempt count and its audit
        entry, and lockout would never engage."""
        refusal: NotAuthenticated | None = None
        result: dict[str, Any] = {}
        with self.p.uow(username) as uow:
            user = uow.repo("users").find_one(username=username)
            refusal = self._precheck(uow, user, username, ip, channel)
            if refusal is None and (not user["password_hash"] or
                                    not kdf.verify_password(password, user["password_hash"])):
                self._record_failure(uow, user, utcnow(), ip, channel)
                refusal = NotAuthenticated("Invalid username or password")
            if refusal is None:
                result = self._succeed(uow, user, password, ip, user_agent, channel)
        if refusal is not None:
            raise refusal
        return result

    def _precheck(self, uow: Any, user: dict[str, Any] | None, username: str,
                  ip: str | None, channel: str) -> NotAuthenticated | None:
        if self.p.settings.auth_mode == "sso":
            uow.audit("auth.login_refused", object_ref=f"user:{username}", ip=ip,
                      channel=channel, detail={"reason": "password login disabled (sso)"})
            return NotAuthenticated("This deployment signs people in with SSO only")
        if user is None or user["auth_source"] != "db" or user["is_service"]:
            uow.audit("auth.login_failed", detail={"reason": "unknown user",
                                                   "username": username}, ip=ip, channel=channel)
            return NotAuthenticated("Invalid username or password")
        if user["status"] != "active":
            uow.audit("auth.login_refused", object_ref=f"user:{username}",
                      detail={"status": user["status"]}, ip=ip, channel=channel)
            return NotAuthenticated(f"Account is {user['status']}")
        if user["locked_until"] and user["locked_until"] > utcnow():
            uow.audit("auth.login_locked", object_ref=f"user:{username}", ip=ip, channel=channel)
            return NotAuthenticated("Account is locked after repeated failures; try again "
                                    f"after {user['locked_until']:%H:%M} UTC")
        return None

    def _succeed(self, uow: Any, user: dict[str, Any], password: str, ip: str | None,
                 user_agent: str | None, channel: str) -> dict[str, Any]:
        changes: dict[str, Any] = {"failed_attempts": 0, "first_failed_at": None,
                                   "locked_until": None, "last_login_at": utcnow()}
        if kdf.needs_rehash(user["password_hash"]):
            changes["password_hash"] = kdf.hash_password(password)
        uow.repo("users").update(user["id"], changes)
        mfa = self.p.sso.initial_mfa_state(uow, user)
        token = self._open_session(uow, user, ip, user_agent, channel, mfa_state=mfa)
        uow.audit("auth.login", object_ref=f"user:{user['username']}", ip=ip, channel=channel,
                  detail={"rehashed": "password_hash" in changes, "mfa": mfa})
        return {"token": token, "username": user["username"],
                "must_change_password": user["must_change_password"],
                "default_password": password == DEFAULT_ADMIN_PASSWORD, "mfa": mfa}

    def _record_failure(self, uow: Any, user: dict[str, Any], now: dt.datetime,
                        ip: str | None, channel: str) -> None:
        first = user["first_failed_at"]
        count = user["failed_attempts"] + 1 if first and now - first < self.lock_window else 1
        changes: dict[str, Any] = {"failed_attempts": count,
                                   "first_failed_at": first if count > 1 else now}
        if count >= self.lock_attempts:
            changes["locked_until"] = now + self.lock_duration
            uow.audit("auth.lockout", object_ref=f"user:{user['username']}", ip=ip,
                      channel=channel)
        uow.repo("users").update(user["id"], changes)
        uow.audit("auth.login_failed", object_ref=f"user:{user['username']}", ip=ip,
                  channel=channel, detail={"attempt": count})

    def _open_session(self, uow: Any, user: dict[str, Any], ip: str | None,
                      user_agent: str | None, channel: str, *, auth_method: str = "password",
                      mfa_state: str = "ok", extra: dict[str, Any] | None = None) -> str:
        token = "maya_s_" + secrets.token_urlsafe(32)
        now = utcnow()
        uow.repo("sessions").add({
            "user_id": user["id"], "token_hash": _sha(token), "channel": channel,
            "auth_method": auth_method, "mfa_state": mfa_state,
            "last_seen_at": now, "expires_at": now + self.idle,
            "absolute_expires_at": now + self.absolute, "ip": ip,
            "user_agent": (user_agent or "")[:500], **(extra or {})})
        return token

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
    def principal(self, token: str | None, *, ip: str | None = None,
                  path: str | None = None) -> Principal:
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
            return hit[1]
        principal, fully_signed_in = self._resolve_session(token, path)
        if self.principal_ttl > 0 and fully_signed_in:
            if len(self._principals) > 10_000:
                self._principals.clear()
            self._principals[key] = (time.monotonic() + self.principal_ttl, principal)
        return principal

    def _resolve_session(self, token: str, path: str | None = None
                         ) -> tuple[Principal, bool]:
        from maya.services.sso import MFA_OPEN_PATHS
        with self.p.uow() as uow:
            sess = uow.repo("sessions").find_one(token_hash=_sha(token))
            now = utcnow()
            if sess is None or sess["revoked_at"]:
                raise NotAuthenticated("Session has ended; log in again")
            if sess["mfa_state"] != "ok" and not (path or "").endswith(MFA_OPEN_PATHS):
                raise NotAuthenticated(
                    "A second factor is required: " + ("enter the code from your "
                    "authenticator" if sess["mfa_state"] == "challenge" else
                    "enroll an authenticator first"), mfa=sess["mfa_state"])
            if sess["expires_at"] < now or sess["absolute_expires_at"] < now:
                uow.repo("sessions").update(sess["id"], {"revoked_at": now})
                raise NotAuthenticated("Session expired; log in again")
            if not sess["last_seen_at"] or (now - sess["last_seen_at"]).total_seconds() > 30:
                uow.repo("sessions").update(sess["id"], {
                    "last_seen_at": now, "expires_at": min(now + self.idle,
                                                           sess["absolute_expires_at"])})
            return (self.build_principal(uow, sess["user_id"], channel=sess["channel"]),
                    sess["mfa_state"] == "ok")

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
            if not self._key_secret_ok(key_id, secret, row["secret_hash"]):
                uow.audit("auth.api_key_failed", object_ref=f"api_key:{key_id}", ip=ip,
                          durable=True)
                raise NotAuthenticated("API key is invalid")
            if row["cidrs"] and not _ip_allowed(ip, row["cidrs"]):
                raise NotAuthenticated("API key is not allowed from this address")
            if not row["last_used_at"] or (now - row["last_used_at"]).total_seconds() > 60:
                uow.repo("api_keys").update(row["id"], {"last_used_at": now})
            p = self.build_principal(uow, row["user_id"], channel="api",
                                     principal_type="api_key")
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
                return True
        ok = kdf.verify_password(secret, stored)
        if ok:
            with self._lock:
                self._key_cache[key_id] = (time.monotonic(), probe)
        return ok

    def build_principal(self, uow: Any, user_id: str, *, channel: str = "api",
                        principal_type: str = "user") -> Principal:
        user = uow.repo("users").require(user_id)
        if user["status"] != "active":
            raise NotAuthenticated(f"Account is {user['status']}")
        role_ids = [ur["role_id"] for ur in uow.repo("user_roles").list(user_id=user_id)]
        group_ids = [g["group_id"] for g in uow.repo("group_members").list(user_id=user_id)]
        for gid in group_ids:
            role_ids += [gr["role_id"] for gr in uow.repo("group_roles").list(group_id=gid)]
        roles = uow.repo("roles").list(id__in=set(role_ids)) if role_ids else []
        groups = [g["name"] for g in uow.repo("groups").list(id__in=group_ids)] if group_ids else []
        return Principal(user_id=user_id, username=user["username"],
                         roles=sorted(r["name"] for r in roles),
                         capabilities=merge_capabilities([r["capabilities"] for r in roles]),
                         groups=groups, principal_type=principal_type, channel=channel,
                         desk=user.get("desk"))

    @staticmethod
    def _role_caps(uow: Any, names: list[str]) -> list[dict[str, str]]:
        return [r["capabilities"] for r in uow.repo("roles").list(name__in=names)] if names else []

    # -- passwords -------------------------------------------------------------
    def check_policy(self, password: str) -> None:
        classes = sum([any(c.islower() for c in password), any(c.isupper() for c in password),
                       any(c.isdigit() for c in password),
                       any(not c.isalnum() for c in password)])
        if len(password) < self.min_length or classes < 3:
            raise ValidationFailed(f"Password must be at least {self.min_length} characters "
                                   "and use three of: lower, upper, digit, symbol")

    def change_password(self, p: Principal, old: str, new: str) -> None:
        self.check_policy(new)
        with self.p.uow(p.username) as uow:
            user = uow.repo("users").require(p.user_id)
            if not kdf.verify_password(old, user["password_hash"] or ""):
                raise NotAuthenticated("Current password is incorrect")
            if new == old:
                raise ValidationFailed("The new password must differ from the old one")
            uow.repo("users").update(p.user_id, {"password_hash": kdf.hash_password(new),
                                                 "must_change_password": False,
                                                 "password_changed_at": utcnow()})
            uow.audit("auth.password_changed", object_ref=f"user:{p.username}")

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
    def create_api_key(self, p: Principal, *, name: str, roles: list[str] | None = None,
                       namespaces: list[str] | None = None, actions: list[str] | None = None,
                       cidrs: list[str] | None = None, days: int = 90) -> dict[str, Any]:
        max_days = self.p.settings.int("auth.api_keys.max_days", 365)
        if days < 1 or days > max_days:
            raise ValidationFailed(f"Key expiry must be 1–{max_days} days")
        extra = set(roles or []) - set(p.roles)
        if extra:
            raise PermissionDenied("A key cannot carry roles you do not hold: " + ", ".join(extra))
        key_id, secret = secrets.token_hex(6), secrets.token_urlsafe(24).replace("_", "-")
        full = f"maya_{self.env}_{key_id}_{secret}"
        with self.p.uow(p.username) as uow:
            row = uow.repo("api_keys").add({
                "key_id": key_id, "user_id": p.user_id, "name": name, "env": self.env,
                "secret_hash": kdf.hash_password(secret), "roles": roles or [],
                "namespaces": namespaces or [], "actions": actions or [], "cidrs": cidrs or [],
                "expires_at": utcnow() + dt.timedelta(days=days)})
            uow.audit("auth.api_key_created", object_ref=f"api_key:{key_id}",
                      detail={"name": name, "roles": roles, "days": days})
        row.pop("secret_hash")
        return {**row, "api_key": full, "shown_once": True}

    def list_api_keys(self, p: Principal, all_users: bool = False) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            rows = uow.repo("api_keys").list(order_by=["-created_at"]) if all_users \
                else uow.repo("api_keys").list(user_id=p.user_id, order_by=["-created_at"])
        for r in rows:
            r.pop("secret_hash", None)
        return rows

    def revoke_api_key(self, p: Principal, key_id: str) -> None:
        with self.p.uow(p.username) as uow:
            row = uow.repo("api_keys").find_one(key_id=key_id)
            if row is None:
                raise NotFound(f"API key '{key_id}' does not exist")
            if row["user_id"] != p.user_id and not p.is_admin:
                raise PermissionDenied("You can revoke only your own keys")
            uow.repo("api_keys").update(row["id"], {"revoked_at": utcnow()})
            uow.audit("auth.api_key_revoked", object_ref=f"api_key:{key_id}")
        with self._lock:
            self._key_cache.pop(key_id, None)

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
