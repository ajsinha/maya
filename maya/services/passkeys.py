"""
Security keys and passkeys as a second factor (§12), alongside TOTP.

**Registration** needs a session that has already passed its second factor (or
one that is being made to enroll): a session waiting on a challenge can never
add a key, or a stolen password would be enough to add one. **Authentication**
answers the challenge a password login leaves; a failure counts toward lockout
and ends that sign-in attempt, exactly like a wrong TOTP code.

Every challenge is issued by MAYA, stored server-side, bound to its user and
session, single-use (consumed *before* the response is verified, so even a
failed attempt burns it) and short-lived. A signature counter that fails to
rise — a cloned key — is refused. An administrator's MFA reset removes a
person's keys along with their TOTP secret.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from maya.core.errors import (ConflictError, NotAuthenticated, NotFound, PermissionDenied,
                              ValidationFailed)
from maya.persistence.types import utcnow
from maya.security import passkeys
from maya.security.authz import Principal

CHALLENGE_SECONDS = 300
PUBLIC = ("id", "credential_id", "name", "transports", "aaguid", "backed_up", "sign_count",
          "created_at", "last_used_at")


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in PUBLIC}


class PasskeyService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def rp(self) -> passkeys.RelyingParty:
        return passkeys.relying_party(self.p.settings.props)

    def _session_user(self, uow: Any, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
        sess = self.p.sso._session(uow, token)
        return sess, uow.repo("users").require(sess["user_id"])

    def _consume(self, kind: str, handle: str, *, user_id: str, session_id: str,
                 ip: str | None) -> None:
        """Burn a challenge before its response is verified: single use even on failure."""
        with self.p.uow("system") as uow:
            row = uow.repo("auth_challenges").find_one(kind=kind, handle=handle)
            problem = None
            if row is None:
                problem = "no such challenge was issued"
            elif row["user_id"] != user_id or row["session_id"] != session_id:
                problem = "the challenge belongs to another sign-in"
            elif row["consumed_at"] is not None:
                problem = "the challenge was already used (replay)"
            elif row["expires_at"] < utcnow():
                problem = "the challenge has expired"
            if problem:
                uow.audit("auth.webauthn_refused", object_ref=f"user-id:{user_id}", ip=ip,
                          detail={"kind": kind, "reason": problem}, durable=True)
                raise NotAuthenticated(f"Security key refused: {problem}; start again")
            uow.repo("auth_challenges").update(row["id"], {"consumed_at": utcnow()})

    def _issue(self, uow: Any, kind: str, challenge: bytes, user_id: str,
               session_id: str) -> None:
        uow.repo("auth_challenges").add({
            "kind": kind, "handle": passkeys.b64u(challenge), "user_id": user_id,
            "session_id": session_id,
            "expires_at": utcnow() + dt.timedelta(seconds=CHALLENGE_SECONDS)})

    # -- registration ------------------------------------------------------------------
    def register_options(self, p: Principal, token: str) -> dict[str, Any]:
        rp = self.rp()
        with self.p.uow(p.username) as uow:
            sess, user = self._session_user(uow, token)
            self._may_register(sess, user)
            existing = uow.repo("webauthn_credentials").list(user_id=user["id"])
            options, challenge = rp.registration_options(
                uuid.UUID(str(user["id"])).bytes, user["username"],
                user["display_name"] or user["username"], existing)
            self._issue(uow, "webauthn_register", challenge, user["id"], sess["id"])
            uow.audit("auth.webauthn_registration_started", object_ref=f"user:{p.username}")
        return {"options": options, "expires_in": CHALLENGE_SECONDS}

    @staticmethod
    def _may_register(sess: dict[str, Any], user: dict[str, Any]) -> None:
        if sess["mfa_state"] == "challenge":
            raise PermissionDenied("Answer the second-factor challenge before adding a key")
        if user["auth_source"] != "db":
            raise ValidationFailed("SSO accounts take their second factor from the identity "
                                   "provider")

    def register(self, p: Principal, token: str, credential: dict[str, Any], *,
                 name: str = "security key", ip: str | None = None) -> dict[str, Any]:
        rp = self.rp()
        handle = passkeys.challenge_of(credential)
        with self.p.uow() as uow:
            sess, user = self._session_user(uow, token)
            self._may_register(sess, user)
        self._consume("webauthn_register", handle, user_id=user["id"], session_id=sess["id"],
                      ip=ip)
        data = rp.verify_registration(credential, passkeys.unb64u(handle))
        with self.p.uow(p.username) as uow:
            if uow.repo("webauthn_credentials").find_one(credential_id=data["credential_id"]):
                raise ConflictError("That security key is already registered")
            row = uow.repo("webauthn_credentials").add({
                **data, "user_id": user["id"], "name": (name or "security key")[:128]})
            state = "ok" if sess["mfa_state"] == "enroll" else sess["mfa_state"]
            uow.repo("sessions").update(sess["id"], {"mfa_state": state})
            uow.audit("auth.webauthn_registered", object_ref=f"user:{p.username}", ip=ip,
                      detail={"name": row["name"], "aaguid": data["aaguid"],
                              "credential": data["credential_id"][:16]})
        return {**_public(row), "mfa": state}

    # -- authentication -------------------------------------------------------------------
    def login_options(self, token: str) -> dict[str, Any]:
        rp = self.rp()
        with self.p.uow() as uow:
            sess, user = self._session_user(uow, token)
            uow.actor = user["username"]
            if sess["mfa_state"] != "challenge":
                raise ValidationFailed("This session is not awaiting a second factor")
            creds = uow.repo("webauthn_credentials").list(user_id=user["id"])
            if not creds:
                raise ValidationFailed("No security key is registered for this account")
            options, challenge = rp.authentication_options(creds)
            self._issue(uow, "webauthn_login", challenge, user["id"], sess["id"])
        return {"options": options, "expires_in": CHALLENGE_SECONDS}

    def login(self, token: str, credential: dict[str, Any], *,
              ip: str | None = None) -> dict[str, Any]:
        rp = self.rp()
        handle = passkeys.challenge_of(credential)
        with self.p.uow() as uow:
            sess, user = self._session_user(uow, token)
            if sess["mfa_state"] != "challenge":
                raise ValidationFailed("This session is not awaiting a second factor")
        self._consume("webauthn_login", handle, user_id=user["id"], session_id=sess["id"],
                      ip=ip)
        refusal: NotAuthenticated | None = None
        with self.p.uow(user["username"]) as uow:
            stored = uow.repo("webauthn_credentials").find_one(
                user_id=user["id"], credential_id=str(credential.get("id") or ""))
            try:
                if stored is None:
                    raise NotAuthenticated("That security key is not registered to you")
                count = rp.verify_authentication(credential, passkeys.unb64u(handle), stored)
            except NotAuthenticated as exc:
                self.p.auth._record_failure(uow, user, utcnow(), ip, "web")
                uow.repo("sessions").update(sess["id"], {"revoked_at": utcnow()})
                uow.audit("auth.webauthn_refused", object_ref=f"user:{user['username']}", ip=ip,
                          detail={"reason": exc.message[:300]})
                refusal = NotAuthenticated(f"{exc.message}; log in again")
            else:
                uow.repo("webauthn_credentials").update(stored["id"], {
                    "sign_count": count, "last_used_at": utcnow()})
                uow.repo("users").update(user["id"], {"failed_attempts": 0})
                uow.repo("sessions").update(sess["id"], {"mfa_state": "ok"})
                uow.audit("auth.mfa_verified", object_ref=f"user:{user['username']}", ip=ip,
                          detail={"factor": "webauthn", "key": stored["name"]})
        if refusal is not None:
            raise refusal
        return {"mfa": "ok"}

    # -- management -----------------------------------------------------------------------
    def list(self, p: Principal) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return [_public(r) for r in uow.repo("webauthn_credentials").list(
                user_id=p.user_id, order_by=["created_at"])]

    def remove(self, p: Principal, key_id: str) -> None:
        with self.p.uow(p.username) as uow:
            row = uow.repo("webauthn_credentials").find_one(id=key_id, user_id=p.user_id)
            if row is None:
                raise NotFound("No such security key on your account")
            uow.repo("webauthn_credentials").delete_where(id=key_id)
            uow.audit("auth.webauthn_removed", object_ref=f"user:{p.username}",
                      detail={"name": row["name"], "credential": row["credential_id"][:16]})

    def count(self, uow: Any, user_id: str) -> int:
        return uow.repo("webauthn_credentials").count(user_id=user_id)
