"""
Single sign-on and multi-factor authentication (§12).

**SSO.** One config switch, ``auth.mode``: ``db`` (passwords), ``sso`` (OIDC for
people; password login refused), or ``hybrid`` (OIDC for people, passwords kept
for break-glass and service accounts). Group-to-role mapping is re-evaluated at
*every* login, so removing someone from an IdP group removes the MAYA capability
at their next session with no manual step. JIT provisioning creates the user on
first login with the mapped roles and no object grants. A user with no mapped
group is refused when ``on_missing_group: deny``. ``auth.sso.protocol`` is
``oidc`` or ``saml2``; SAML (``maya.security.saml``) needs ``python3-saml`` and
``xmlsec`` and is refused at startup without them. Both protocols end in the
same claims-to-principal step, so group mapping, JIT provisioning and refusals
behave identically.

SAML AuthnRequests are recorded server-side: the IdP posts the Response back
cross-site, where the browser's session cookie is not sent, so the request a
Response answers is found by its ``InResponseTo``, must be outstanding and
unexpired, and is consumed by the first Response to it. Each assertion id is
recorded too, so the same assertion is never accepted twice.

**MFA.** TOTP or a security key (WebAuthn, ``maya.services.passkeys``) for
password logins. A user with MFA enrolled gets a *challenge*
session that can do nothing but verify a code; a user whose role requires MFA
but who has not enrolled gets an *enroll* session that can do nothing but enroll.
``auth.mfa.enforce``: ``auto`` enforces the role requirement outside dev (in dev
only users who enrolled are challenged), ``true`` always, ``false`` never. SSO
sessions delegate the second factor to the identity provider.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from maya.core import totp
from maya.core.errors import (CapabilityRefused, NotAuthenticated, PermissionDenied,
                              ValidationFailed)
from maya.core.clock import utcnow
from maya.security.authz import Principal
from maya.security.oidc import OIDCClient, settings_from

# endpoints a session may reach before its MFA state is "ok"
MFA_OPEN_PATHS = ("/auth/mfa", "/auth/mfa/verify", "/auth/mfa/enroll", "/auth/mfa/confirm",
                  "/auth/mfa/webauthn/options", "/auth/mfa/webauthn/verify",
                  "/auth/mfa/webauthn/register/options", "/auth/mfa/webauthn/register",
                  "/auth/me", "/auth/logout")
SAML_REQUEST_SECONDS = 600


class SsoService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        s = platform.settings
        self.mode = s.auth_mode
        self.protocol = (s.get("auth.sso.protocol", "oidc") or "oidc").lower()
        self.transport: Any = None            # tests inject a fake identity provider
        self._client: OIDCClient | None = None
        self._saml: Any = None
        roles = s.props.get_list("auth.mfa.required_for_roles") or []
        self.mfa_roles = set(roles)
        self.mfa_enforce = (s.get("auth.mfa.enforce", "auto") or "auto").lower()
        self.environment = s.environment

    # -- configuration --------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.mode in ("sso", "hybrid")

    def check_startup(self) -> None:
        """Refuse a configuration that would only fail at someone's first login."""
        if not self.enabled:
            return
        if self.protocol == "saml2":
            from maya.security import saml
            saml.require()
            saml.settings_from(self.p.settings.props)
        elif self.protocol != "oidc":
            raise CapabilityRefused(f"auth.sso.protocol is '{self.protocol}'; it must be "
                                    "'oidc' or 'saml2'")
        elif not settings_from(self.p.settings.props).redirect_uri:
            raise CapabilityRefused("auth.sso.redirect_uri must be set for SSO")
        if self.mfa_enforce not in ("auto", "true", "false"):
            raise ValidationFailed("auth.mfa.enforce must be auto, true or false")

    def client(self) -> OIDCClient:
        if not self.enabled:
            raise ValidationFailed("SSO is not enabled (auth.mode is 'db')")
        if self._client is None:
            self._client = OIDCClient(settings_from(self.p.settings.props),
                                      transport=self.transport)
        return self._client

    def public_config(self) -> dict[str, Any]:
        return {"mode": self.mode, "sso": self.enabled, "protocol": self.protocol,
                "password_login": self.mode != "sso",
                "issuer": (self.p.settings.get("auth.sso.saml.idp_entity_id")
                           if self.protocol == "saml2" else
                           self.p.settings.get("auth.sso.issuer")) if self.enabled else None,
                "mfa_enforce": self.mfa_enforce, "mfa_required_for_roles": sorted(self.mfa_roles)}

    def group_role_map(self) -> dict[str, list[str]]:
        prefix = "auth.sso.group_role_map."
        out: dict[str, list[str]] = {}
        for key, value in self.p.settings.props.get_properties_by_pattern(
                r"^auth\.sso\.group_role_map\.").items():
            group = key[len(prefix):]
            if "." in group and group.rsplit(".", 1)[1].isdigit():
                continue                      # indexed list children; the joined form is used
            out[group] = [r.strip() for r in value.split(",") if r.strip()]
        return out

    # -- SSO flow ---------------------------------------------------------------------
    def start(self) -> dict[str, str]:
        return self.client().begin()

    def callback(self, code: str, code_verifier: str, nonce: str, *, ip: str | None = None,
                 user_agent: str | None = None) -> dict[str, Any]:
        claims = self.client().finish(code, code_verifier, nonce)
        return self.login_with_claims(claims, ip=ip, user_agent=user_agent)

    # -- SAML ---------------------------------------------------------------------------
    def saml_sp(self) -> Any:
        from maya.security import saml
        if not self.enabled or self.protocol != "saml2":
            raise ValidationFailed("SAML SSO is not enabled (auth.sso.protocol is not 'saml2')")
        if self._saml is None:
            self._saml = saml.SamlSP(saml.settings_from(self.p.settings.props))
        return self._saml

    def saml_metadata(self) -> str:
        return self.saml_sp().metadata()

    def saml_start(self, relay_state: str = "") -> dict[str, str]:
        out = self.saml_sp().begin(relay_state)
        with self.p.uow("sso") as uow:
            uow.repo("auth_challenges").add({
                "kind": "saml_request", "handle": out["request_id"],
                "expires_at": utcnow() + dt.timedelta(seconds=SAML_REQUEST_SECONDS)})
        return out

    def saml_acs(self, saml_response: str, *, ip: str | None = None,
                 user_agent: str | None = None) -> dict[str, Any]:
        """Validate a posted Response to an outstanding request, then sign the person in."""
        from maya.security import saml
        sp = self.saml_sp()
        request_id = saml.in_response_to(saml_response)
        self._claim_saml_request(request_id, ip)
        try:
            asserted = sp.finish(saml_response, request_id or "")
        except NotAuthenticated as exc:
            self._saml_refused(exc.message, ip)
            raise
        self._record_assertion(asserted, ip)
        return self.login_with_claims(self._saml_claims(asserted), ip=ip, user_agent=user_agent)

    def _saml_refused(self, reason: str, ip: str | None) -> None:
        with self.p.uow("sso") as uow:
            uow.audit("auth.sso_refused", object_ref="saml", ip=ip, channel="web",
                      detail={"protocol": "saml2", "reason": reason[:500]})

    def _claim_saml_request(self, request_id: str | None, ip: str | None) -> None:
        """The Response must answer a request MAYA made, still open and unanswered."""
        problem = None
        with self.p.uow("sso") as uow:
            row = uow.repo("auth_challenges").find_one(kind="saml_request",
                                                       handle=request_id or "")
            if not request_id:
                problem = "unsolicited SAML response: it answers no request MAYA made"
            elif row is None:
                problem = "the SAML response answers a request MAYA did not make"
            elif row["consumed_at"] is not None:
                problem = "the SAML request was already answered (replay)"
            elif row["expires_at"] < utcnow():
                problem = "the SAML request has expired; start the sign-in again"
            else:
                uow.repo("auth_challenges").update(row["id"], {"consumed_at": utcnow()})
        if problem:
            self._saml_refused(problem, ip)
            raise NotAuthenticated(problem[0].upper() + problem[1:])

    def _record_assertion(self, asserted: dict[str, Any], ip: str | None) -> None:
        handle = f"saml-assertion:{asserted.get('assertion_id') or ''}"
        refused = False
        with self.p.uow("sso") as uow:
            if uow.repo("auth_challenges").find_one(kind="saml_assertion", handle=handle):
                refused = True
            else:
                until = asserted.get("not_on_or_after")
                uow.repo("auth_challenges").add({
                    "kind": "saml_assertion", "handle": handle, "consumed_at": utcnow(),
                    "expires_at": dt.datetime.fromtimestamp(until, dt.timezone.utc) if until
                    else utcnow() + dt.timedelta(days=1)})
        if refused:
            self._saml_refused("the SAML assertion was already used (replay)", ip)
            raise NotAuthenticated("The SAML assertion was already used (replay)")

    def _saml_claims(self, asserted: dict[str, Any]) -> dict[str, Any]:
        """SAML attributes in the shape OIDC claims take, under the configured claim names."""
        s = self.p.settings
        attrs = asserted.get("attributes") or {}

        def first(name: str | None) -> str:
            values = attrs.get(name or "") or []
            return str(values[0]) if values else ""
        username = first(s.get("auth.sso.saml.username_attribute")) or asserted["name_id"] or ""
        return {s.get("auth.sso.username_claim") or "preferred_username": username,
                s.get("auth.sso.groups_claim") or "groups":
                    list(attrs.get(s.get("auth.sso.saml.groups_attribute") or "groups") or []),
                s.get("auth.sso.email_claim") or "email":
                    first(s.get("auth.sso.saml.email_attribute") or "email"),
                "sub": asserted["name_id"], "iss": asserted["issuer"],
                "name": first(s.get("auth.sso.saml.name_attribute") or "displayName") or None}

    def login_with_claims(self, claims: dict[str, Any], *, ip: str | None = None,
                          user_agent: str | None = None) -> dict[str, Any]:
        props = self.p.settings.props
        username = str(claims.get(props.get("auth.sso.username_claim") or
                                  "preferred_username") or claims.get("sub") or "")
        groups = claims.get(props.get("auth.sso.groups_claim") or "groups") or []
        groups = [groups] if isinstance(groups, str) else list(groups)
        mapping = self.group_role_map()
        roles = sorted({r for g in groups for r in mapping.get(g, [])})
        refusal: NotAuthenticated | None = None
        result: dict[str, Any] = {}
        with self.p.uow(username or "sso") as uow:
            refusal = self._refuse(uow, username, claims, roles, ip)
            if refusal is None:
                user = self._upsert(uow, username, claims, roles)
                token = self.p.auth._open_session(uow, user, ip, user_agent, "web",
                                                  auth_method="sso")
                uow.audit("auth.sso_login", object_ref=f"user:{username}", ip=ip,
                          channel="web", detail={"groups": groups, "roles": roles,
                                                 "issuer": claims.get("iss")})
                result = {"token": token, "username": username, "roles": roles,
                          "must_change_password": False, "mfa": "ok"}
        if refusal is not None:
            raise refusal
        return result

    def _refuse(self, uow: Any, username: str, claims: dict[str, Any], roles: list[str],
                ip: str | None) -> NotAuthenticated | None:
        def refuse(reason: str) -> NotAuthenticated:
            uow.audit("auth.sso_refused", object_ref=f"user:{username or '?'}", ip=ip,
                      channel="web", detail={"reason": reason, "sub": claims.get("sub")},
                      durable=True)
            return NotAuthenticated(reason)
        if not username:
            return refuse("The identity provider sent no username claim")
        on_missing = (self.p.settings.get("auth.sso.on_missing_group", "deny") or "deny")
        if not roles and on_missing == "deny":
            return refuse("None of your identity-provider groups maps to a MAYA role")
        user = uow.repo("users").find_one(username=username)
        if user is not None and user["auth_source"] == "db":
            return refuse(f"A local password account named '{username}' already exists; "
                          "an administrator must reconcile it before SSO can use the name")
        if user is None and not self.p.settings.bool("auth.sso.jit_provision", True):
            return refuse("Your account has not been provisioned in MAYA")
        if user is not None and user["status"] != "active":
            return refuse(f"Account is {user['status']}")
        return None

    def _upsert(self, uow: Any, username: str, claims: dict[str, Any],
                roles: list[str]) -> dict[str, Any]:
        users = uow.repo("users")
        user = users.find_one(username=username)
        email = claims.get(self.p.settings.get("auth.sso.email_claim") or "email") or ""
        if user is None:
            user = users.add({"username": username, "email": email,
                              "display_name": claims.get("name") or username,
                              "auth_source": "sso", "external_subject": claims.get("sub")})
            uow.audit("user.jit_provisioned", object_ref=f"user:{username}",
                      detail={"roles": roles})
        else:
            user = users.update(user["id"], {"email": email, "last_login_at": utcnow(),
                                             "external_subject": claims.get("sub")})
        # the mapping is re-applied at every login: leaving an IdP group removes the role
        uow.repo("user_roles").delete_where(user_id=user["id"])
        for role in uow.repo("roles").list(name__in=roles):
            uow.repo("user_roles").add({"user_id": user["id"], "role_id": role["id"]})
        return user

    # -- MFA -----------------------------------------------------------------------------
    def mfa_required(self, roles: list[str], enrolled: bool) -> bool:
        if self.mfa_enforce == "false":
            return False
        by_role = bool(self.mfa_roles & set(roles))
        if self.mfa_enforce == "true":
            return by_role or enrolled
        return enrolled or (by_role and self.environment != "dev")

    def enrolled(self, uow: Any, user: dict[str, Any]) -> bool:
        """A second factor is set up: a confirmed TOTP authenticator or a security key."""
        return bool(user["mfa_enabled"]) or \
            uow.repo("webauthn_credentials").count(user_id=user["id"]) > 0

    def initial_mfa_state(self, uow: Any, user: dict[str, Any]) -> str:
        if self.enrolled(uow, user):
            return "challenge"
        roles = self.p.auth.build_principal(uow, user["id"]).roles
        return "enroll" if self.mfa_required(roles, False) else "ok"

    def mfa_status(self, token: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            sess = self._session(uow, token)
            user = uow.repo("users").require(sess["user_id"])
            roles = self.p.auth.build_principal(uow, user["id"]).roles
            keys = uow.repo("webauthn_credentials").count(user_id=user["id"])
            enrolled = bool(user["mfa_enabled"]) or keys > 0
        return {"session_state": sess["mfa_state"], "enrolled": enrolled,
                "totp": bool(user["mfa_enabled"]), "security_keys": keys,
                "required": self.mfa_required(roles, enrolled),
                "auth_method": sess["auth_method"]}

    def _session(self, uow: Any, token: str) -> dict[str, Any]:
        from maya.services.auth import _sha
        sess = uow.repo("sessions").find_one(token_hash=_sha(token))
        if sess is None or sess["revoked_at"]:
            raise NotAuthenticated("Session has ended; log in again")
        return sess

    def verify(self, token: str, code: str, *, ip: str | None = None) -> dict[str, Any]:
        """Answer the challenge. A wrong code counts toward lockout like a wrong password."""
        refusal: NotAuthenticated | None = None
        with self.p.uow() as uow:
            sess = self._session(uow, token)
            user = uow.repo("users").require(sess["user_id"])
            uow.actor = user["username"]
            if sess["mfa_state"] != "challenge" or not user["mfa_secret"]:
                raise ValidationFailed("This session is not awaiting a second factor")
            secret = self._box().open(user["mfa_secret"])
            step = totp.verify(secret, code, last_step=user["mfa_last_step"])
            if step is None:
                self.p.auth._record_failure(uow, user, utcnow(), ip, "web")
                uow.repo("sessions").update(sess["id"], {"revoked_at": utcnow()})
                refusal = NotAuthenticated("The code is wrong or already used; log in again")
            else:
                uow.repo("users").update(user["id"], {"mfa_last_step": step,
                                                      "failed_attempts": 0})
                uow.repo("sessions").update(sess["id"], {"mfa_state": "ok"})
                uow.audit("auth.mfa_verified", object_ref=f"user:{user['username']}", ip=ip)
        if refusal is not None:
            raise refusal
        return {"mfa": "ok"}

    def _not_mid_challenge(self, uow: Any, token: str | None) -> None:
        """A session still owing its second factor may not replace it: otherwise a stolen
        password alone could enroll a new authenticator and walk through the challenge."""
        from maya.services.auth import _sha
        sess = uow.repo("sessions").find_one(token_hash=_sha(token or ""))
        if sess is not None and sess["mfa_state"] == "challenge":
            uow.audit("auth.mfa_refused", object_ref=f"user-id:{sess['user_id']}",
                      detail={"reason": "enrollment attempted during a challenge"},
                      durable=True)
            raise PermissionDenied("Answer the second-factor challenge before changing "
                                   "your authenticator")

    def enroll(self, p: Principal, token: str | None = None) -> dict[str, Any]:
        """Issue a fresh secret; it takes effect only once a code from it is confirmed."""
        secret = totp.new_secret()
        with self.p.uow(p.username) as uow:
            self._not_mid_challenge(uow, token)
            user = uow.repo("users").require(p.user_id)
            if user["auth_source"] != "db":
                raise ValidationFailed("SSO accounts take their second factor from the "
                                       "identity provider")
            uow.repo("users").update(p.user_id, {"mfa_secret": self._box().seal(secret),
                                                 "mfa_enabled": False, "mfa_last_step": None})
            uow.audit("auth.mfa_enrollment_started", object_ref=f"user:{p.username}")
        return {"secret": secret, "otpauth_uri": totp.provisioning_uri(
            secret, p.username, self.p.settings.get("auth.mfa.issuer_name", "MAYA") or "MAYA"),
            "shown_once": True}

    def confirm(self, p: Principal, token: str, code: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            self._not_mid_challenge(uow, token)
            user = uow.repo("users").require(p.user_id)
            if not user["mfa_secret"]:
                raise ValidationFailed("Start enrollment first")
            step = totp.verify(self._box().open(user["mfa_secret"]), code)
            if step is None:
                raise ValidationFailed("That code does not match; check the device clock")
            uow.repo("users").update(p.user_id, {"mfa_enabled": True, "mfa_last_step": step})
            sess = self._session(uow, token)
            uow.repo("sessions").update(sess["id"], {"mfa_state": "ok"})
            uow.audit("auth.mfa_enrolled", object_ref=f"user:{p.username}")
        return {"mfa": "ok", "enrolled": True}

    def reset(self, admin: Principal, username: str) -> None:
        if not admin.is_admin:
            raise PermissionDenied("Only an administrator resets another user's MFA")
        with self.p.uow(admin.username) as uow:
            user = uow.repo("users").find_one(username=username)
            if user is None:
                raise ValidationFailed(f"User '{username}' does not exist")
            uow.repo("users").update(user["id"], {"mfa_secret": None, "mfa_enabled": False,
                                                  "mfa_last_step": None})
            keys = uow.repo("webauthn_credentials").delete_where(user_id=user["id"])
            uow.audit("auth.mfa_reset", object_ref=f"user:{username}",
                      detail={"security_keys_removed": keys})

    def _box(self) -> Any:
        from maya.core.crypto import SecretBox
        return SecretBox(self.p.root / "keys")
