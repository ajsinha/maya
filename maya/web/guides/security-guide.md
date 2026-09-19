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
| `sso` | Single sign-on | refused for everyone |
| `hybrid` | Single sign-on | kept for break-glass and service accounts |

`auth.sso.protocol` chooses `oidc` or `saml2`. Both end in the same step that turns verified claims into a MAYA principal, so group mapping, provisioning and refusals behave identically. A configuration that could only fail at someone's first sign-in — a missing issuer, client id or redirect URI; a missing SAML setting; SAML libraries not installed — refuses to start instead.

## Passwords

| Control | Behaviour |
|---|---|
| Policy | At least `auth.password.min_length` (12) characters, using three of: lower case, upper case, digits, symbols. A new password must differ from the old one. |
| Storage | Argon2id (memory 64 MB, time 3, parallelism 4) when `argon2` is installed; otherwise scrypt, then PBKDF2-HMAC-SHA512. The algorithm and parameters are stored with each hash, and a sign-in re-hashes an old hash with the strongest available algorithm. |
| Lockout | `auth.lockout.attempts` (5) failures within `window_minutes` (15) lock the account for `duration_minutes` (30). A wrong second-factor code counts as a failure. The lockout is audited as `auth.lockout`. |
| Failures are recorded | A failed or refused sign-in is committed and audited before the refusal is returned, so lockout cannot be dodged by the rollback. |
| Service accounts | Accounts created with `is_service` cannot sign in with a password; they use API keys. |

!!! warning "Change the bootstrap admin password"
    A fresh database has an `admin` account with a known default password, flagged `must_change_password`. The startup banner and the health page warn while it is still in use. Outside dev, MAYA refuses to start until it is changed, unless `app.allow_default_admin_password` is set.

## Sessions

A sign-in opens a server-side session and returns a session token (`maya_s_…`, 256 bits of randomness). MAYA stores only its SHA-256.

| Property | Value |
|---|---|
| Idle timeout | `auth.session.idle_timeout_minutes` (30); each use extends it, never past the absolute limit |
| Absolute timeout | `auth.session.absolute_timeout_hours` (12) after sign-in |
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

## Single sign-on with SAML 2.0

!!! warning "SAML has not yet been tested against a real identity provider"
    The SAML service provider is built and tested against a test IdP, not a commercial one. Treat it as unproven until it has been exercised with yours.

What is built:

- **SP-initiated only.** MAYA sends an unsigned AuthnRequest by HTTP-Redirect and accepts the Response by HTTP-POST at its assertion consumer service. IdP-initiated sign-in is refused by design: an unsolicited Response cannot be tied to a request.
- **Signed assertions required.** The assertion must be signed by the certificate configured for the IdP, with a non-deprecated algorithm; python3-saml runs in strict mode.
- **Checked:** `Issuer` is the IdP entity id; the `Audience` names MAYA's entity id; `Destination` and `Recipient` are MAYA's ACS URL (taken from configuration, not the request's Host header); `NotBefore`/`NotOnOrAfter` hold now.
- **One answer per request.** Each AuthnRequest is recorded server-side and valid for ten minutes. A Response must carry `InResponseTo` naming an outstanding request, which the first Response consumes. A missing `InResponseTo`, an unknown or expired one, or a second Response to the same request is refused.
- **No assertion twice.** Each assertion id is recorded; a replayed assertion is refused.

Every refusal is audited as `auth.sso_refused`. Not built: signed AuthnRequests, single logout, IdP-initiated sign-in. SAML needs the `python3-saml` and `xmlsec` packages; with `protocol: saml2` and either missing, MAYA refuses to start.

### Groups, roles and provisioning

For both protocols:

- **Mapping.** `auth.sso.group_role_map` maps identity-provider groups to MAYA roles. It is re-applied at every sign-in: someone removed from a group loses the role at their next session with no manual step.
- **Unmapped people.** With `on_missing_group: deny`, a person none of whose groups maps to a role is refused.
- **Provisioning.** With `jit_provision: true`, the account is created at first sign-in with the mapped roles and no object grants. With `false`, a person without an account is refused.
- **Name clashes.** If a local password account already has the username, SSO is refused until an administrator reconciles the two.
- **Second factor.** SSO sessions take their second factor from the identity provider; MAYA does not challenge them again.

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
| Expiry | 1 to `auth.api_keys.max_days` (365) days, 90 by default. |
| Revocation | By the owner or an administrator; takes effect at once. |
| Failed use | A key with a wrong secret is refused and audited as `auth.api_key_failed`. |

The Python SDK refuses to send a key or token over plain HTTP to anything but localhost.

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
- **Anchored outside.** A consistent rewrite — history changed and every later hash recomputed — still verifies as a chain. Anchors close that gap: every `custody.anchor.interval_seconds` (hourly) the chain head is signed, appended to `custody.anchor.file`, announced as an `audit.anchored` event, and optionally timestamped by an RFC 3161 authority. `GET /api/v1/custody/verify` checks every anchor against the live chain and reports `TAMPERING` when they disagree. MAYA checks a timestamp token's status and imprint; checking the authority's own signature is left to `openssl ts -verify`.

!!! tip "Make the anchors independent"
    On the same disk as the database, the anchor file only raises the bar. Put it on write-once or off-host storage, subscribe a system your MAYA administrators do not control to `audit.anchored` webhooks, or enable `rfc3161`.

## Outbound connections

| Connection | Guard |
|---|---|
| Webhooks | HTTPS only. The host may not resolve to a private, loopback, link-local or reserved address, checked at creation and again at every delivery; redirects are not followed. Only dev with `observability.webhooks.allow_private` relaxes this. Each delivery is HMAC-SHA256-signed over `<timestamp>.<body>`. |
| RFC 3161 timestamps | Off by default; enabling `rfc3161` sends the audit head hash to `custody.anchor.tsa_url`. |
| The assistant | `rules` (default) makes no network call. `claude` sends definitions, specifications and formulas — never data rows — to Anthropic's API. |
| `/metrics` | Open by default; name a token variable in `observability.metrics.token_env` to require a bearer token. A named but unset variable refuses every scrape rather than opening the endpoint. |

## Security events to watch

These audit actions are the ones a security reviewer usually filters for. Those marked *event* also reach webhook subscribers.

| Audit action | Meaning |
|---|---|
| `auth.login_failed`, `auth.login_refused`, `auth.login_locked` | A failed password, a refused account (status, SSO-only), a sign-in while locked |
| `auth.lockout` (*event*) | An account locked after repeated failures |
| `auth.sso_refused` | A single sign-on refused: unmapped groups, a name clash, an unsolicited or replayed SAML Response |
| `auth.api_key_failed` | An API key presented with a wrong secret |
| `auth.api_key_created`, `auth.api_key_revoked` | Key lifecycle |
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
| A leaked API key | Revoke it: `my.auth.revoke_api_key(key_id)`. It is refused from the next request. List everyone's keys with `my.auth.api_keys(all=True)`. |
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
| Short-lived, narrow API keys | `days`, `namespaces`, `actions`, `cidrs` |
