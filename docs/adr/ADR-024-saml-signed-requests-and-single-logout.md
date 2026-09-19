# ADR-024 — SAML: signed requests, and single logout in both directions

**Status:** Accepted, revision 2.3 (2026-09-19).

## Context

SAML sign-in as first built was SP-initiated, with the IdP's assertion verified, but MAYA's
own AuthnRequests unsigned and no logout at all. Two gaps followed. IdPs configured to require
signed requests refused MAYA. And signing out of MAYA left the IdP session alive, so the next
visit signed the person straight back in; signing someone out at the IdP left their MAYA
session running until it expired.

## Decision

- **Sign-in stays SP-initiated only.** An unsolicited Response cannot be tied to a request,
  so it is refused.
- **Requests may be signed** with MAYA's own key pair (`auth.sso.saml.sign_requests`,
  `sp_cert`/`sp_cert_file`, `sp_key`/`sp_key_file`; RSA-SHA256). The key comes from the
  environment or a file, never from the tracked configuration.
- **Single logout in both directions over HTTP-Redirect**, when `auth.sso.saml.idp_slo_url`
  is set: signing out of MAYA ends the MAYA session and sends the browser to the IdP to end
  its own; the IdP's LogoutRequest, received at `sls_url`, ends every MAYA session of the
  person it names — only the named IdP session, when it names one — **and only when the IdP
  signed it**.

## Consequences

- **Front channel only.** SAML back-channel (SOAP) logout is not supported, so an IdP that
  signs someone out without their browser does not reach MAYA. Against Keycloak 26.4, an
  administrator's sign-out of a user was seen not to reach MAYA for exactly this reason.
- A password session (hybrid mode) signs out locally; there is no IdP session to end.
- `sign_requests` switched on without MAYA's certificate and key is refused at startup,
  naming `auth.sso.saml.sp_cert` and `auth.sso.saml.sp_key`. Without `idp_slo_url`, the
  single logout endpoint refuses and logout stays local.
- Proven against one real IdP, Keycloak 26.4, over http on loopback; no commercial IdP.

## References

- Specification §12 (revision 2.3 note); README *Not yet*.
- Code: `maya/security/saml.py`, `maya/services/sso.py` (`logout`, `saml_sls`,
  `_end_sso_sessions`), `maya/api/routers/identity.py`, `maya/web/routes/auth.py`,
  `config/application.yaml` (`auth.sso.saml`).
- Tests: `tests/test_saml_slo.py` —
  `test_authn_requests_are_signed_with_the_sp_key_and_metadata_names_slo`,
  `test_signing_out_of_maya_signs_out_at_the_idp`,
  `test_the_idps_logout_request_ends_exactly_that_sign_in`,
  `test_logout_requests_the_idp_did_not_properly_send_end_nothing`,
  `test_a_password_session_signs_out_locally_only`,
  `test_without_slo_the_sls_is_refused_and_logout_stays_local`;
  `tests/test_sso_keycloak.py` (opt-in with `MAYA_TEST_KEYCLOAK_URL`).
