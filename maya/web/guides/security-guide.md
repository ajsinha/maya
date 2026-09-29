# Security guide

This guide describes how MAYA authenticates people and programs, how it protects sessions and secrets, how it runs code it did not write, and how it makes its own record tamper-evident. It says plainly where a control stops. Settings are named by their key in `config/application.yaml`; the configuration reference gives their defaults.

## The security model in one page

| Concern | What MAYA does |
|---|---|
| Who you are | A password (with lockout), OIDC or SAML single sign-on, and a second factor (TOTP or a security key). Programs use API keys. Every credential resolves to one principal. |
| What you may do | One pure function, `can(principal, action, object)`, called by every surface: role ceiling, API-key scope, object state, then grants and their conditions. |
| What you may see | Grant conditions filter rows, mask columns and cut off dates on every frame returned to you. Data licences limit who may receive data and where it may go. |
| Code MAYA runs | Uploaded model artifacts and Python sources run in a separate, jailed interpreter whose isolation tier is measured, recorded and enforced outside dev. |
| Secrets at rest | Credentials are stored only as hashes. Secrets MAYA must read back are sealed with authenticated encryption under `storage.root/keys`. |
| Evidence | Tokens, certificates, manifests and bundles are signed with Ed25519. The audit log is hash-chained, append-only, and anchored outside the database. |

## Sign-in modes

`auth.mode` decides how people sign in.

| Mode | People | Passwords |
|---|---|---|
| `db` (default) | MAYA passwords | yes |
| `sso` | Single sign-on | refused for everyone but a designated break-glass account |
| `hybrid` | Single sign-on | kept for break-glass and service accounts |

### Break-glass under `auth.mode: sso`

An identity provider that is down takes every sign-in with it, so §13.3 promises
administrators a way in. `auth.break_glass.users` names the accounts — one is usually
enough — that may sign in with a password even in `sso` mode:

```yaml
auth:
  mode: sso
  break_glass:
    users: [breakglass-admin]
    session_minutes: 60
```

Nothing else about those accounts is special, and everything about them is loud:

- the account must be a database account holding the `admin` role, or the sign-in is
  refused and audited as `auth.break_glass_refused` naming which of the two is wrong —
  a misconfiguration must not be discovered during the outage;
- MFA applies exactly as it does to anyone else, so enrol the account before the day
  you need it;
- the session lasts `auth.break_glass.session_minutes` (60), not the usual twelve hours;
- every use writes a durable `auth.break_glass_login` audit entry, an inbox notice to
  every other administrator, and a warning in the log;
- in the browser the password form stays hidden in `sso` mode; `/login?break-glass=1`
  shows it. Showing the form grants nothing — the server decides.

The SSO outage runbook (`docs/runbooks/sso-outage.md`) has the drill. A break-glass account
with no second factor enrolled, a forgotten password or no `admin` role is not a
break-glass account, which is why the runbook asks you to test it at every restore drill.

`auth.sso.protocol` chooses `oidc` or `saml2`. Both end in the same step that turns verified claims into a MAYA principal, so group mapping, provisioning and refusals behave identically. A configuration that could only fail at someone's first sign-in — a missing issuer, client id or redirect URI; a missing SAML setting; SAML libraries not installed — refuses to start instead.

## Passwords

| Control | Behaviour |
|---|---|
| Policy | At least `auth.password.min_length` (8) characters, using `auth.password.require_classes` (2) of: lower case, upper case, digits, symbols. A new password must differ from the old one. |
| History | A new password may not repeat any of the last `auth.password.history` (5), the current one included. Only hashes are kept, and only that many; the refusal says how many MAYA remembers. `0` turns the history off. |
| Maximum age | A password older than `auth.password.max_age_days` (90) must be changed: the sign-in is refused, naming the age and by how much it was passed, and the account is flagged `must_change_password`. An account whose last change MAYA never recorded does not expire — otherwise configuring a maximum age would lock everyone out at once. `0` turns the maximum off. |
| Reset | Single use, time limited (`auth.password.reset_token_minutes`, 60). Anyone may ask at `/login/forgot`, which tells the administrators and says nothing about whether the account exists; an administrator issues the link on `/account/credentials`, and redeeming it ends every session the account has open. MAYA sends no email, so the link is handed over in person. An administrator's direct reset still forces a change at the next sign-in. |
| Storage | Argon2id (memory 64 MB, time 3, parallelism 4) when `argon2` is installed; otherwise scrypt, then PBKDF2-HMAC-SHA512. The algorithm and parameters are stored with each hash, and a sign-in re-hashes an old hash with the strongest available algorithm. |
| Lockout | `auth.lockout.attempts` (5) failures within `window_minutes` (15) lock the account for `duration_minutes` (30). A wrong second-factor code counts as a failure. The lockout is audited as `auth.lockout`. |
| Failures are recorded | A failed or refused sign-in is committed and audited before the refusal is returned, so lockout cannot be dodged by the rollback. |
| Service accounts | Accounts created with `is_service` cannot sign in with a password; they use an API key or a client credential an administrator issues for them. |

!!! warning "Change the bootstrap admin password"
    A fresh database has an `admin` account with a known default password. The startup banner and the health page warn while it is still in use, and with `auth.password.force_change` on (off by default) the first sign-in must change it. Outside dev, MAYA refuses to start until it is changed, unless `app.allow_default_admin_password` is set.

## Sessions

A sign-in opens a server-side session and returns a session token (`maya_s_…`, 256 bits of randomness). MAYA stores only its SHA-256.

| Property | Value |
|---|---|
| Idle timeout | `auth.session.idle_timeout_minutes` (30); each use extends it, never past the absolute limit |
| Absolute timeout | `auth.session.absolute_timeout_hours` (12) after sign-in |
| Concurrent sessions | `auth.session.concurrent_sessions` (3) per person. A further sign-in ends their oldest session rather than refusing the new one, audited as `auth.session_evicted`. `0` lifts the cap. Service accounts are exempt: a fleet sharing one credential holds a token each by design. |
| Ending | `POST /auth/logout`; an administrator can list and end any session |
| Second-factor state | `ok`, `challenge` or `enroll`. Until it is `ok`, the session reaches only the MFA endpoints, `/auth/me` and `/auth/logout`. |

In the browser, the web tier keeps the session token in a signed cookie named `maya_session`: `SameSite=Lax`, a 12-hour lifetime, and marked `Secure` outside dev. It is signed with `app.secret_key`, which must be set outside dev and must stay secret.

### CSRF and browser hardening

- **CSRF.** Every state-changing request from the web UI must carry the per-session synchronizer token, as the `csrf_token` form field or the `X-CSRF-Token` header, compared in constant time. A missing or wrong token is refused with 403. The REST API is not cookie-authenticated — it takes bearer credentials only — so it is not exposed to cross-site request forgery.
- **Content Security Policy.** `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:; frame-ancestors 'none'` on every response except the interactive API docs. No inline script runs.
- **Other headers.** `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- **Assets.** Bootstrap and jQuery are vendored and served by MAYA itself; the UI loads nothing from a third party.

## Single sign-on with OIDC

MAYA uses the authorization code flow with PKCE. Before it believes an ID token:

- the signature is by a key the issuer publishes, and asymmetric — `none` and HMAC algorithms are refused;
- `iss` equals `auth.sso.issuer`; `aud` contains `auth.sso.client_id`;
- `exp` is in the future and `iat` is not, with 120 seconds of clock skew allowed;
- `nonce` is the one MAYA issued for this sign-in.

### Signing out, both directions

| Who starts | What happens |
|---|---|
| You, signing out of MAYA | The MAYA session ends at once. If `auth.sso.post_logout_redirect_uri` is set — and registered with the IdP as a valid post-logout redirect — and the issuer's discovery document publishes an `end_session_endpoint`, the browser then goes there with `client_id` and that address (OpenID Connect RP-Initiated Logout 1.0); the IdP ends its own session and sends the browser back. Empty, sign-out is local: the IdP's session survives, and the next SSO sign-in is silent while it lasts. |
| The IdP, server to server | It POSTs a logout token, form field `logout_token`, to `POST /api/v1/auth/sso/oidc/backchannel-logout` (OpenID Connect Back-Channel Logout 1.0). MAYA ends every session of the token's `sub` — only the session named, when the token carries a `sid` — and audits `auth.sso_logout`. |

The back-channel endpoint is public, because the IdP holds no MAYA credential: the token's signature is the only thing that authenticates the call, so it is checked as strictly as an ID token's and then some. The signature must be by a key the issuer publishes, with an asymmetric algorithm; `iss` must be `auth.sso.issuer` and `aud` must contain `auth.sso.client_id`; `iat` must be no more than 300 seconds old, plus the clock skew; the token must carry the back-channel-logout event, a `sub` or a `sid`, and a `jti`; it must **not** carry a `nonce`, which would make it an ID token presented as a logout token; and its `jti` is single use. A token that fails any of these is answered `400` with `Cache-Control: no-store`, is audited as `auth.sso_refused`, and ends nothing. The detail names the check, for example:

```json
{"type": "not_authenticated", "title": "NotAuthenticated", "status": 400,
 "detail": "The logout token was already used (replay)", "context": {}}
```

Back-channel logout needs the IdP to reach MAYA's API server to server, which a MAYA on a private network may not allow.

## Single sign-on with SAML 2.0

!!! warning "Tested against one real identity provider"
    SAML sign-in, signed requests and single logout have been exercised end to end against Keycloak 26.4 (see [Tested against Keycloak 26.4](#tested-against-keycloak-264)) and against a simulated IdP in the test suite. No other identity provider has been tried; treat yours as unproven until you have signed in and out with it.

What is built:

- **SP-initiated sign-in.** MAYA sends an AuthnRequest by HTTP-Redirect and accepts the Response by HTTP-POST at its assertion consumer service. IdP-initiated sign-in is refused by design: an unsolicited Response cannot be tied to a request.
- **Signed requests (optional).** With `auth.sso.saml.sign_requests: true`, MAYA signs its AuthnRequests and logout messages with RSA-SHA256, using a key pair from `sp_cert`/`sp_cert_file` and `sp_key`/`sp_key_file` (the key from the environment or a file, never the configuration file). The SP metadata then publishes the certificate. Turning signing on without both is refused at startup.
- **Signed assertions required.** The assertion must be signed by the certificate configured for the IdP, with a non-deprecated algorithm; python3-saml runs in strict mode.
- **Checked:** `Issuer` is the IdP entity id; the `Audience` names MAYA's entity id; `Destination` and `Recipient` are MAYA's ACS URL (taken from configuration, not the request's Host header); `NotBefore`/`NotOnOrAfter` hold now.
- **One answer per request.** Each AuthnRequest is recorded server-side and valid for ten minutes. A Response must carry `InResponseTo` naming an outstanding request, which the first Response consumes. A missing `InResponseTo`, an unknown or expired one, or a second Response to the same request is refused.
- **No assertion twice.** Each assertion id is recorded; a replayed assertion is refused.

### Single logout

Set `auth.sso.saml.idp_slo_url` (the IdP's logout endpoint) and MAYA's own single logout service, `sls_url` (default `…/auth/sso/saml/sls`). Both directions use HTTP-Redirect.

| Who starts | What happens |
|---|---|
| You, signing out of MAYA | The MAYA session ends at once. The browser then goes to the IdP with a LogoutRequest naming the NameID and SessionIndex of your sign-in. The IdP's LogoutResponse must answer that request; an answer to no request, or a second answer, is refused. |
| The IdP | Its LogoutRequest must be **signed** with the IdP's certificate, come from the configured issuer and be addressed to MAYA's SLS. MAYA ends every session of that NameID (only the named SessionIndex, when there is one), audits `auth.sso_logout`, and redirects back with a LogoutResponse. An unsigned request is refused: it would let anyone end anyone's sessions. |

Redirect signatures are checked over the query string exactly as received, so an IdP's own URL encoding cannot break them. A session opened by password signs out locally only; one opened by OIDC follows the OIDC rules above.

Every refusal is audited as `auth.sso_refused`. Not supported for SAML: IdP-initiated sign-in, and back-channel (server-to-server SOAP) logout — MAYA's SLS takes front-channel redirects only, so a SAML IdP that signs people out without their browser does not reach MAYA, and the MAYA session lasts until its own timeout or sign-out. (OIDC has a back channel; see [Signing out, both directions](#signing-out-both-directions).) An attribute sent as several same-named elements (Keycloak sends one `Role` element per role, for example) has its values merged. SAML needs the `python3-saml` and `xmlsec` packages; with `protocol: saml2` and either missing, MAYA refuses to start.

### Groups, roles and provisioning

For both protocols:

- **Mapping.** `auth.sso.group_role_map` maps identity-provider groups to MAYA roles. It is re-applied at every sign-in: someone removed from a group loses the role at their next session with no manual step.
- **Unmapped people.** With `on_missing_group: deny`, a person none of whose groups maps to a role is refused.
- **Provisioning.** With `jit_provision: true`, the account is created at first sign-in with the mapped roles and no object grants. With `false`, a person without an account is refused.
- **Name clashes.** If a local password account already has the username, SSO is refused until an administrator reconciles the two.
- **Second factor.** SSO sessions take their second factor from the identity provider; MAYA does not challenge them again.

## Tested against Keycloak 26.4

MAYA's SSO was driven end to end in headless Chrome against Keycloak 26.4.7 in dev mode, with MAYA started by `run_maya_web.py` in `hybrid` mode on another host name, so the SAML POST and the logout redirects were cross-site as in production. `tests/test_sso_keycloak.py` repeats it against any Keycloak you point `MAYA_TEST_KEYCLOAK_URL` at; it builds the realm below through the admin REST API. Keycloak must be able to reach MAYA server to server for the back-channel test (the test's docstring runs it with `--network host`); without that, those two tests fail and the rest pass. This is one IdP at one version. Other IdPs, and other Keycloak versions, have not been tested.

| Flow | Result with Keycloak 26.4.7 |
|---|---|
| OIDC sign-in (code flow, PKCE S256, confidential client) | Works; the `groups` claim maps to roles; a person in no mapped group is refused. |
| OIDC sign-out from MAYA (RP-initiated) | Works with `auth.sso.post_logout_redirect_uri` set: the browser goes to Keycloak's end-session endpoint, Keycloak asks the person to confirm (MAYA sends no ID token hint), ends its session and returns to MAYA; the next sign-in asks for the password. With it empty, sign-out is local only. |
| Keycloak administrator ends one OIDC session (back channel) | Works: Keycloak POSTs a logout token to MAYA and the MAYA session ends. Keycloak's "sign out all sessions" of a user was seen to send a token for one of that user's sessions only, so do not rely on it to end them all; end each session. |
| SAML sign-in, signed AuthnRequest | Works; groups arrive as one `groups` element per group or as one multi-valued element, both merged. |
| SAML sign-out from MAYA (single logout) | Works: signed LogoutRequest to Keycloak, its signed LogoutResponse back to the SLS, Keycloak's session ended (the next sign-in asks for the password). |
| Keycloak ends the session in the browser (its end-session page, or another application's logout) | Works: Keycloak redirects the browser to MAYA's SLS with a signed LogoutRequest, MAYA ends the session and answers. |
| Keycloak administrator "Sign out" of a SAML user | Does **not** reach MAYA: that is Keycloak's SAML back channel (SOAP), which MAYA does not offer (Keycloak logs "Some clients have not been logged out"). |

**OIDC client** (Clients → Create, OpenID Connect):

- Client ID `maya` (whatever `auth.sso.client_id` says); **Client authentication** on (confidential), its secret in `MAYA_OIDC_CLIENT_SECRET`; **Standard flow** only.
- Valid redirect URI: exactly `auth.sso.redirect_uri`, e.g. `https://maya.example.com/auth/sso/callback`.
- Advanced → **PKCE method `S256`**.
- A **group membership** mapper, token claim name `groups`, **Full group path off** (with it on the claim carries `/maya-admins`, which `group_role_map` must then name), added to the ID token.
- MAYA asks for the scopes `openid profile email groups`, and Keycloak refuses a scope it does not know (`invalid_scope`). Either create a client scope named `groups` holding the mapper and add it to the client (optional or default), or put the mapper on the client and set `auth.sso.scopes: "openid profile email"`. Both were tested.
- `auth.sso.issuer` is the realm URL, `https://keycloak.example.com/realms/<realm>`, exactly as the discovery document's `issuer` says (the host name the browser uses).
- For sign-out at Keycloak: **Valid post logout redirect URIs** (`post.logout.redirect.uris`) holds exactly `auth.sso.post_logout_redirect_uri`, e.g. `https://maya.example.com/login?signed_out=1`.
- For back-channel logout: **Backchannel logout URL** (`backchannel.logout.url`) is `https://maya.example.com/api/v1/auth/sso/oidc/backchannel-logout`, and **Backchannel logout session required** (`backchannel.logout.session.required`) is on, so each token names the session (`sid`) and ends only that one.

**SAML client** (Clients → Create, SAML):

- Client ID = `auth.sso.saml.sp_entity_id`. Valid redirect URIs: MAYA's origin followed by `/*`.
- **Name ID format** `username` with **Force name ID format** on (the NameID becomes the MAYA username).
- **Sign documents** on and **Sign assertions** on, algorithm RSA_SHA256. Sign documents is what signs Keycloak's own LogoutRequests; with it off MAYA refuses them as unsigned and the MAYA session survives the IdP's logout.
- **Force POST binding** on; **Front channel logout** on; Encrypt assertions off.
- Advanced → Assertion Consumer Service POST Binding URL = `acs_url`; Logout Service Redirect Binding URL = `sls_url`.
- With `sign_requests: true`: Keys → **Client signature required** on, and import MAYA's certificate (`sp_cert_file`). Unsigned requests (`sign_requests: false` with Client signature required off) were tested too.
- A **Group list** mapper, SAML attribute name `groups`, Full group path off; a **User Property** mapper `email` → attribute `email`. Keycloak's default role-list scope adds `Role` attributes; MAYA ignores them.
- MAYA's side: `idp_entity_id` is the realm URL; `idp_sso_url` and `idp_slo_url` are both `<realm URL>/protocol/saml`; `idp_cert_file` holds the realm's signing certificate from `<realm URL>/protocol/saml/descriptor`.

## Two-factor authentication

Password sign-ins can require a second factor: a TOTP code or a security key. Either answers a challenge.

| `auth.mfa.enforce` | Who is challenged or made to enroll |
|---|---|
| `auto` (default) | Anyone who has enrolled is challenged. Outside dev, anyone holding a role in `required_for_roles` must enroll first. |
| `true` | As `auto`, but the role requirement applies in dev too. |
| `false` | Nobody. |

`auth.mfa.required_for_roles` defaults to `[admin, model_owner]`.

### TOTP

RFC 6238: HMAC-SHA1, 30-second steps, six digits, one step of clock drift allowed either way. The last accepted step is recorded, so a code cannot be replayed inside its window. The seed is sealed at rest. A wrong code ends that sign-in attempt and counts toward lockout.

### Security keys and passkeys (WebAuthn)

- MAYA is the relying party `auth.webauthn.rp_id`, accepting only the origins in `auth.webauthn.origins`. Algorithms: EdDSA, ES256, RS256.
- Every challenge is issued by MAYA, stored server-side, bound to the user and session, single-use (consumed before the response is checked, so even a failed attempt burns it) and valid for five minutes.
- A signature counter that fails to rise — what a cloned key does — is refused.
- A failed ceremony ends the sign-in attempt and counts toward lockout.
- Registration needs a session that has passed its second factor (or one being made to enroll): a session still owing a challenge can neither add a key nor replace its authenticator, so a stolen password is never enough.
- Attestation is not requested. MAYA records the model a key reports (its AAGUID) but does not claim the key is hardware-backed.

An administrator can reset a person's second factor; that removes their TOTP seed and every security key, and is audited as `auth.mfa_reset`.

## API keys

A key is `maya_<env>_<key id>_<secret>`. The secret is stored only as a KDF hash; the full key is shown once.

| Control | Behaviour |
|---|---|
| Environment | The key names its environment; a key presented to a MAYA in another environment is refused. |
| Roles | A key can carry fewer roles than its owner, never more. |
| Namespaces and actions | Allowlists that narrow every authorization decision the key takes part in. |
| Networks | `cidrs`: the key is refused from any other client address. |
| Expiry | 1 to `auth.api_keys.max_days` (365) days, 90 by default — and no further out than the shortest `api_key_max_days` of the namespaces the key is scoped to. |
| Rate limit | A key may carry its own budget in requests a minute (`rate_per_minute`, default `auth.api_keys.rate_per_minute`, 0 for none). The whole minute may be spent at once; beyond it the key is refused with `quota_exceeded` (429) and how long to wait. This is charged where the key is resolved, so it holds for the API, the SDK and the CLI alike, on top of the per-process request limits. |
| Rotation | `my.auth.rotate_api_key(key_id)` issues a successor with the same roles, namespaces, actions, networks and budget, and pulls the old key's expiry in to the end of the overlap window (`auth.api_keys.rotation_overlap_days`, 7). Both work during the overlap, so a deployment needs no timing; `overlap_days=0` cuts over at once. A key is rotated once — its successor is rotated next. |
| Reminders | `my.auth.api_key_report()` (the **Credentials** page) names keys unused for `auth.api_keys.unused_days` (90), keys within `auth.api_keys.remind_days_before_expiry` (14) of expiring, and keys already rotated, each with the reason. |
| Revocation | By the owner or an administrator; takes effect at once. |
| Failed use | A key with a wrong secret is refused and audited as `auth.api_key_failed`. |

The Python SDK refuses to send a key or token over plain HTTP to anything but localhost.

## Credentials for service accounts

A service account has no interactive sign-in, so someone has to issue its credential for
it. An administrator does, and can give it no role the account does not already hold:

```python
my.admin.create_user("nightly-scorer", password=None, roles=["model_developer"], is_service=True)

# either a bearer API key, issued on the account's behalf …
key = my.auth.create_api_key("nightly", for_user="nightly-scorer", days=30)

# … or an OAuth2 client credential, exchanged for a short-lived token
cc = my.auth.create_client_credential("nightly-scorer", days=30, rate_per_minute=600)
token = my.auth.client_credentials_token(cc["client_id"], cc["client_secret"])
```

| Property | Behaviour |
|---|---|
| The grant | `POST /api/v1/auth/token`, form encoded, `grant_type=client_credentials` with `client_id` and `client_secret` (RFC 6749 §4.4). There is no refresh token: the credential is the long-lived secret and asking again is one request. |
| The token | A session token that lives `auth.client_credentials.token_minutes` (60), or less when the credential expires sooner. It carries the credential's role subset, namespaces and action allowlist — never more than the account holds. |
| Revocation | Revoking the credential ends the tokens it issued, in this process at once and in any other within the principal-cache window. A client credential is refused if presented as a bearer key: it must be exchanged. |
| Expiry | Mandatory, like every API key, and rotation works the same way. |

Both forms are listed, with their last use, on the **Credentials** page and through
`my.auth.client_credentials()`.

## Authorization

Every surface — web, REST, SDK, CLI — calls the same decision function. In order:

1. **Role ceiling.** One of your roles must hold the action's capability letter for the object type. No grant lifts you above it.
2. **API-key scope.** A key's action and namespace allowlists narrow further.
3. **Object state.** Sealed and retired objects are read-only to everyone, administrators included.
4. **Scratch namespaces** belong to their owner alone.
5. **Administrators** pass once the ceiling and state checks have.
6. **Grants.** Explicit deny, then your user grant, then the best group or role grant, then an `everyone` grant, then ownership, then the namespace default.

Grant conditions (row filters, column masks, time bounds) then narrow what a read returns, and licences can refuse a read, a download, an export, a derivation or a grant. Separation of duties is enforced by the workflow engine at the namespace's strictness. The roles, access and licences reference covers each of these in full.

## The sandbox for code MAYA did not write

Model artifacts and `python` sources run in a separate interpreter (`python -I`) with an empty working directory, a stripped environment, resource limits where the OS provides them, a wall-clock kill, an output-size cap, and networking disabled in the child. The tier is **measured** by a probe at startup, not assumed:

| Tier | What was verified |
|---|---|
| `strong` | Linux: a bubblewrap jail (fresh user, pid, network, mount, IPC and UTS namespaces; an unmapped uid; a read-only root holding only system libraries and the interpreter — not the home directory, not MAYA's storage), a seccomp-bpf deny-list, and a cgroup v2 scope capping memory, CPU and tasks. All unprivileged. |
| `moderate` | macOS with `sandbox-exec` (network denied by a kernel profile, plus rlimits); or Linux with seccomp and one of the other two verified. |
| `minimal` | rlimits (POSIX) or the wall clock alone (Windows). Network blocking is best-effort: the socket module is disabled in-process, which native code could bypass. |

Outside dev, MAYA refuses to start below `sandbox.min_tier` (default `strong`). The tier is recorded on every validation report, so a reviewer knows what a green tick was worth, and is shown on the health page.

!!! note "Bundles and offline verification"
    The server executes a reproducibility bundle's code only for a bundle signed by its own key whose every file matches its signed hash, and then with its own verifier. `maya.sdk.offline()` never imports code from a bundle. `python -m maya.cli export verify` does run the bundle's own `verify.py`, on your machine, by your choice.

## Secrets, keys and signing

| Material | Where | Protection |
|---|---|---|
| Passwords | database | KDF hash with recorded parameters |
| Session tokens | database | SHA-256 |
| API-key secrets | database | KDF hash |
| TOTP seeds | database | sealed (Fernet: AES-128-CBC with HMAC-SHA256) |
| Webhook signing secrets (`whsec_…`) | database | sealed; shown once at creation |
| SQL source passwords | not stored | a connection names an environment variable (`password_env`) |
| Signing key | `storage.root/keys/signing.pem` | Ed25519, created on first use, never in configuration |
| Sealing key | `storage.root/keys/secretbox.key` | created on first use, never in configuration |
| Session secret (dev only) | `storage.root/keys/session.secret` | generated when `app.secret_key` is empty in dev |

MAYA signs execution-warrant tokens, leakage certificates, reproducibility bundles and custody anchors with Ed25519 through the `cryptography` package. There is no pure-Python fallback: without the package, signing and sealing are refused (`capability_refused`) rather than weakened.

!!! warning "Protect and back up storage.root/keys"
    Whoever reads `keys/` can sign as your MAYA and open sealed secrets. Whoever loses it loses every TOTP enrollment and webhook secret, and the ability to prove later signatures came from the same key.

## Audit and custody

- **Every change is audited** in the same transaction as the change, so a change without its entry cannot commit.
- **Refusals are kept.** Denied approvals, pins, seals, grants and revocations (`authz.denied`), failed API keys, failed and refused sign-ins, SSO refusals and licence refusals on export are written as durable entries that survive the request's rollback.
- **Hash-chained.** Each entry's hash covers its content and the previous hash; altering or deleting any entry breaks every link after it. `GET /api/v1/audit/verify` walks the chain.
- **Append-only in the database.** A trigger refuses any update or delete of `audit_events`, on SQLite and PostgreSQL.
- **Anchored outside.** A consistent rewrite — history changed and every later hash recomputed — still verifies as a chain. Anchors close that gap: every `custody.anchor.interval_seconds` (hourly) the chain head is signed, appended to `custody.anchor.file`, announced as an `audit.anchored` event, and optionally timestamped by an RFC 3161 authority. `GET /api/v1/custody/verify` checks every anchor against the live chain and reports `TAMPERING` when they disagree. MAYA checks a timestamp token's status and imprint. With `custody.anchor.tsa_ca_file` set to the authority's CA certificate, it also checks the authority's own signature, through `openssl ts -verify`, when it anchors and at every verification; configured without the file or without `openssl`, MAYA refuses to start. Without it, the signature is left to you, and the verification report names the command.

!!! tip "Make the anchors independent"
    On the same disk as the database, the anchor file only raises the bar. Put it on write-once or off-host storage, subscribe a system your MAYA administrators do not control to `audit.anchored` webhooks, or enable `rfc3161`.

## Outbound connections

| Connection | Guard |
|---|---|
| Webhooks | HTTPS only. The host may not resolve to a private, loopback, link-local or reserved address, checked at creation and again at every delivery; redirects are not followed. Only dev with `observability.webhooks.allow_private` relaxes this. Each delivery is HMAC-SHA256-signed over `<timestamp>.<body>`. |
| RFC 3161 timestamps | Off by default; enabling `rfc3161` sends the audit head hash to `custody.anchor.tsa_url`. Set `custody.anchor.tsa_ca_file` too, or the TSA's signature is not checked. |
| The assistant | `rules` (default) makes no network call. `llm` (through the AI gateway, to whichever provider its profile names) and `claude` (to Anthropic directly) send definitions, specifications and formulas — never data rows — to that provider. |
| The AI gateway | Drafted document sections send the model's recorded facts, gathered with the requester's own permissions, to the profile's provider; live LLM-application evaluations send the application's own prompts. Every call is audited as `ai.completion` with the prompt's hash, never the prompt. `llm.provider: none` (the default) sends nothing. |
| `/metrics` | Open by default; name a token variable in `observability.metrics.token_env` to require a bearer token. A named but unset variable refuses every scrape rather than opening the endpoint. |

## Security events to watch

These audit actions are the ones a security reviewer usually filters for. Those marked *event* also reach webhook subscribers.

| Audit action | Meaning |
|---|---|
| `auth.login_failed`, `auth.login_refused`, `auth.login_locked` | A failed password, a refused account (status, SSO-only), a sign-in while locked |
| `auth.lockout` (*event*) | An account locked after repeated failures |
| `auth.sso_refused` | A single sign-on refused: unmapped groups, a name clash, an unsolicited or replayed SAML Response |
| `auth.api_key_failed` | An API key presented with a wrong secret |
| `auth.api_key_created`, `auth.api_key_rotated`, `auth.api_key_revoked` | Key lifecycle |
| `auth.break_glass_login`, `auth.break_glass_refused` | A designated account signed in with a password while MAYA is SSO-only, or was refused because it is not an administrator's database account |
| `auth.client_credentials_granted`, `auth.client_credentials_refused` | A service account exchanged a client credential for a token, or failed to |
| `auth.password_reset_requested`, `auth.password_reset_issued`, `auth.password_reset_completed`, `auth.password_reset_refused` | The reset path, end to end |
| `auth.session_evicted` | A session ended to keep a person within the concurrent-session cap |
| `auth.mfa_verified`, `auth.mfa_reset` (*event*) | A second factor answered; an administrator reset one |
| `auth.password_changed`, `auth.session_terminated` | Credential and session changes |
| `authz.denied` | A denied approval, pin, seal, grant or revocation, or any denial on a namespace |
| `access.granted`, `access.revoked` (*events*) | Grants changing |
| `licence.refused` | A licence stopped an export |
| `workflow.break_glass` (*event*) | An administrator forced a transition |
| `policy.activated` (*event*) | A workflow policy went live |
| `integrity.verified` (*event*), `audit.anchored` (*event*) | An integrity run; an anchor of the audit head |

```python
# Recent refused sign-ins, from a script (administrators and techops)
import maya.sdk as maya

my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
for e in my.admin.audit(action="auth.sso_refused", limit=100):
    print(e["at"], e["object_ref"], e["ip"], e["detail"])
```

## Responding to a suspected compromise

| If you suspect… | Do |
|---|---|
| A leaked API key | Revoke it: `my.auth.revoke_api_key(key_id)`. It is refused from the next request, and so is any token it issued. List everyone's keys with `my.auth.api_keys(all=True)`, and what wants rotating with `my.auth.api_key_report(all=True)`. |
| A password you think is known | Issue a reset link (`my.auth.issue_password_reset(username)`) and hand it over: redeeming it sets a new password, which the history refuses to be an old one, and ends every session the account holds. |
| A hijacked session | End it: `my.auth.end_session(session_id)`; list live sessions with `my.auth.sessions()`. |
| A compromised account | Set its status to anything but `active` (`my.admin.update_user(name, status="disabled")`): it can no longer sign in, and its API keys stop working. Reset its password and its second factor. |
| A model running where it should not | Revoke the execution warrant; revoking a training warrant revokes every execution warrant drawn on it. |
| Tampering with the record | Run `GET /api/v1/custody/verify` and `python -m maya.cli admin verify-integrity`. Compare the anchor file and an independent webhook subscriber's `audit.anchored` copies with the live chain. |
| A leaked session secret | Replace `app.secret_key` and restart: every web session cookie becomes invalid. |

## A production checklist

| Check | Setting or action |
|---|---|
| Environment is not dev | `app.environment: prod` (or `uat`) |
| A strong, private session secret | `MAYA_SECRET_KEY` or the local overlay |
| PostgreSQL, not SQLite | `db.dialect: postgresql` (prod refuses SQLite) |
| The bootstrap admin password is changed | enforced outside dev |
| MFA for privileged roles | `auth.mfa.enforce: auto` or `true`; review `required_for_roles` |
| WebAuthn matches the site | `auth.webauthn.rp_id` and `origins` exactly as the browser shows them |
| A strong sandbox | `sandbox.min_tier: strong` on Linux with bubblewrap, seccomp and cgroup v2 |
| TLS in front of MAYA | a reverse proxy; the SDK refuses credentials over plain HTTP |
| `/metrics` protected | `observability.metrics.token_env` |
| Anchors off the host | `custody.anchor.file` on WORM storage; a webhook subscriber for `audit.anchored` |
| `storage.root/keys` backed up and access-controlled | with the database backup |
| Short-lived, narrow API keys | `days`, `namespaces`, `actions`, `cidrs`, `rate_per_minute`; rotate on a schedule and review `my.auth.api_key_report(all=True)` |
| Password history and maximum age set | `auth.password.history`, `auth.password.max_age_days` |
| A break-glass administrator, if `auth.mode: sso` | `auth.break_glass.users`, with a second factor enrolled and tested at every restore drill |
