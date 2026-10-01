# ADR-027 — OIDC logout both ways: RP-initiated, and back-channel logout tokens

**Status:** Accepted, 0.3.0 (2026-09-19).

## Context

With OIDC, signing out of MAYA ended the MAYA session and nothing else, so the next visit
signed the person straight back in through the IdP's live session. And ending a person's
session at the IdP — the usual first act when someone leaves or a laptop is lost — did not
reach MAYA at all; their MAYA session ran on until it expired. SAML had just gained single
logout (ADR-024); OIDC had to match it.

## Decision

- **RP-initiated logout.** With `auth.sso.post_logout_redirect_uri` set and registered at the
  IdP, and the IdP publishing an `end_session_endpoint`, signing out of MAYA ends the MAYA
  session and sends the browser to the IdP to end its own. Unset, sign-out is MAYA's only.
- **Back-channel logout.** The IdP posts a logout token to
  `POST /api/v1/auth/sso/oidc/backchannel-logout`. The token is verified like an ID token
  (signature against the IdP's keys, issuer, audience) and must be fresh (`iat` within five
  minutes, two minutes' skew), carry the back-channel logout event and a `jti`, carry no
  `nonce`, and name a `sub` or a `sid`. It is single-use by `jti`. It ends the sessions of its
  `sub`, narrowed to its `sid` when it names one. Every refusal is audited as
  `auth.sso_refused`.

## Consequences

- The MAYA session always ends first. If the IdP cannot be reached at sign-out, the web tier
  still clears the session and returns to the landing page; only the IdP session survives.
- A back-channel logout reaches other web processes within the principal-cache window
  (ADR-026).
- Keycloak's "sign out all sessions" of a user was seen to send a logout token for one of that
  user's sessions only. MAYA ends what the token names.
- Proven against Keycloak 26.4 only.

## References

- Specification §12; README *Not yet*.
- Code: `maya/security/oidc.py` (`logout_url`, `validate_logout_token`),
  `maya/services/sso.py` (`logout`, `oidc_backchannel_logout`, `_consume_jti`),
  `maya/api/routers/identity.py`, `maya/web/routes/auth.py` (`logout`),
  `config/application.yaml` (`auth.sso.post_logout_redirect_uri`).
- Tests: `tests/test_oidc_logout.py` — `test_signing_out_of_maya_signs_out_at_the_idp`,
  `test_a_logout_token_ends_that_sign_in_and_nothing_else`,
  `test_a_token_naming_only_a_sid_ends_that_session`,
  `test_each_logout_token_check_refuses_on_its_own`, `test_a_logout_token_is_single_use`;
  `tests/test_sso_keycloak.py::test_oidc_sign_out_ends_the_keycloak_session_too`,
  `::test_oidc_keycloak_admin_sign_out_reaches_maya_by_back_channel`.
