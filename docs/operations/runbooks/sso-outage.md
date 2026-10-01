# SSO outage: break-glass sign-in, and how sign-out behaves

For the administrator when people cannot sign in because the identity provider is down or
misbehaving, and for anyone puzzled by what signing out did or did not end. With
`auth.mode: sso`, MAYA refuses password sign-in for everyone **except the accounts named in
`auth.break_glass.users`** — the IdP is the only way in, which is the point of SSO and also
its single point of failure, so §13.3's promise of "a break-glass path for administrators"
is one designated account with a password, not a restart.

A break-glass account is an ordinary database account holding the `admin` role. What is
different is that it works in `sso` mode, its session is short, and using it is loud:
a durable `auth.break_glass_login` audit entry, an inbox notice to every other
administrator, and a warning in the log.

## Symptoms

- SSO sign-in fails for everyone:

  ```json
  {"type": "not_authenticated", "title": "NotAuthenticated", "status": 401,
   "detail": "The identity provider is unreachable: <error>", "context": {}}
  ```

  (OIDC; for SAML the browser simply fails to reach the IdP's sign-in page — MAYA never hears
  about it.)
- In `sso` mode the password form is refused for ordinary accounts: *"This deployment signs
  people in with SSO only"*, audited as `auth.login_refused`. The browser hides the form
  altogether; `/login?break-glass=1` shows it again.
- **People already signed in are unaffected.** MAYA's sessions are its own, in its database;
  they last until `auth.session.idle_timeout_minutes` (30) of inactivity or
  `auth.session.absolute_timeout_hours` (12). API keys keep working — they never touch the IdP.
- MAYA itself starts and serves: nothing at startup contacts the IdP.

## Diagnosis

```bash
curl -s "$MAYA_URL/api/v1/auth/sso/config"          # public
# {"mode":"sso","sso":true,"protocol":"oidc","password_login":false,"issuer":"<issuer>",…}

# From the MAYA host: can it reach the IdP at all? (OIDC)
curl -s "<issuer>/.well-known/openid-configuration" | head -c 300

# What MAYA has refused, and why
curl -s "$MAYA_URL/api/v1/audit?action=auth.sso_refused" -H "Authorization: Bearer $MAYA_API_KEY"
```

If the IdP answers but sign-in still fails, it is not an outage: the audit entries name the
check that refused — an issuer or audience mismatch, a signature that does not verify, no
mapped group under `on_missing_group: deny` — and the fix is on the IdP or in `auth.sso`.

## Break-glass: before the outage

A break-glass account has to exist before it is needed; in `sso` mode nobody can create one
by signing in. Create a database account with the administrator role and a long random
password kept offline, then name it in the configuration:

```python
import maya.sdk as maya

my = maya.connect()  # an administrator's API key
my.admin.create_user("breakglass-admin", password="<long random secret>", roles=["admin"])
```

```yaml
# config/application.yaml (or the local overlay), in place before the outage
auth:
  mode: sso
  break_glass:
    users: [breakglass-admin]
    session_minutes: 60
```

Then sign in with it once — `/login?break-glass=1` — to enrol its TOTP authenticator or
security key; outside `dev`, `admin` requires a second factor at password sign-in. Keep the
password and the enrolled device apart, and test the whole path at every
[restore drill](restore-drill.md). Three things make a break-glass account useless on the
day, and all three are silent until then: it is not named in `auth.break_glass.users`, it
does not hold the `admin` role (MAYA refuses it and audits `auth.break_glass_refused`), or
nobody can find its password.

## Steps during an outage

1. **Sign in as the break-glass account.** In the browser, open
   `https://<maya>/login?break-glass=1` — in `sso` mode the password form is hidden until
   asked for, because it is refused for everyone else — and sign in with the password and the
   second factor. From a script, `POST /api/v1/auth/login` needs nothing special:

   ```python
   anon = maya.connect(base_url="https://maya.example.com")  # no API key: anonymous
   out = anon.auth.login("breakglass-admin", "<the password>")  # out["break_glass"] is True
   ```

   No restart, no configuration change, and nobody else gains a password sign-in.
2. **Expect the noise.** The sign-in writes `auth.break_glass_login` durably, notifies every
   other administrator's inbox, and logs a warning. If you did not expect it, treat it as a
   compromise (see the security guide's compromise table).
3. Do only what cannot wait. Everything the account does is audited under its name, and the
   session lasts `auth.break_glass.session_minutes` (60) whatever the ordinary timeouts say —
   sign in again if you need longer.
4. **When the IdP is back**, review and close:

   ```python
   my.admin.audit(action="auth.break_glass_login")  # every use, with its ip
   my.admin.audit(action="auth.login")  # every password sign-in in the window
   my.admin.update_user("breakglass-admin", status="disabled")  # or rotate its password
   ```

   Rotating the password: issue a reset link with `my.auth.issue_password_reset(
   "breakglass-admin")` and redeem it at `/login/reset`, or set one with
   `my.admin.reset_password(...)`. The password history refuses a return to the old one.

### If the account was never set up

`auth.mode: hybrid` is still the fallback of last resort: it restores password sign-in for
**every** database account, which is wider than break-glass and should be a decision, not a
reflex.

```bash
python run_maya_web.py --auth.mode=hybrid    # or auth.mode: hybrid in the local overlay
```

Sessions survive the restart — they are rows in MAYA's own database — and
`GET /api/v1/auth/sso/config` then answers `"mode":"hybrid","password_login":true`. Restart
without the override once the IdP is back, and set up a break-glass account before the next
outage.

## How sign-out behaves

The MAYA session always ends first; what else ends depends on the protocol and configuration.

| Sign-in | Configured | Signing out of MAYA does |
|---|---|---|
| Password (`db`, `hybrid`) | — | Ends the MAYA session only |
| OIDC | `auth.sso.post_logout_redirect_uri` empty, or the IdP publishes no `end_session_endpoint` | Ends the MAYA session only; the IdP session lives on, so the next visit signs straight back in |
| OIDC | `post_logout_redirect_uri` set and registered at the IdP | Ends the MAYA session, then sends the browser to the IdP's end-session endpoint |
| SAML | `auth.sso.saml.idp_slo_url` empty | Ends the MAYA session only |
| SAML | `idp_slo_url` set | Ends the MAYA session, sends a LogoutRequest to the IdP; its answer returns to `sls_url` with *"You are signed out of MAYA and of your identity provider."* |

And from the IdP's side:

- **OIDC back-channel logout** — the IdP posts a logout token to
  `POST /api/v1/auth/sso/oidc/backchannel-logout`; MAYA ends the sessions of its `sub`,
  narrowed to its `sid`. Refusals are audited as `auth.sso_refused`.
- **SAML front-channel logout** — the IdP's LogoutRequest, through the person's browser to
  `sls_url`, ends that person's sessions, **only if the IdP signed it**.
- **SAML back-channel (SOAP) logout is not supported.** An IdP administrator signing a user out
  without their browser — Keycloak's admin console, for one — does not reach MAYA; the MAYA
  session runs until it expires or someone ends it.

During an outage: the MAYA session still ends, but the browser is sent to an IdP that is not
there (or, if MAYA cannot fetch the IdP's discovery document, straight back to `/login`), and the
IdP session — if the IdP still holds one — is untouched. Logout requests from the IdP cannot
arrive while it is down, so **end sessions by hand** for anyone who must lose access now:

```python
[s for s in my.auth.sessions() if s["username"] == "<username>"]  # administrators
my.auth.end_session("<session-id>")
```

or `DELETE /api/v1/auth/sessions/<session-id>`, or `/admin/users`. With several web
processes, an ended session can still be served by another process for up to
`auth.session.principal_cache_seconds` (2) — [ADR-026](../../design/adr/ADR-026-principal-cache-window.md).

## Verification

- Before (at every restore drill): the break-glass account signs in through
  `/login?break-glass=1` while `auth.mode` is `sso`, and `GET /api/v1/auth/me` names it with
  the `admin` role.
- During: the sign-in succeeds, `auth.break_glass_login` is in the audit trail with the
  operator's address, and the other administrators have the notice in their inbox.
- After: `GET /api/v1/auth/sso/config` shows the original mode, an SSO sign-in succeeds, and
  the break-glass account is disabled or its password rotated.

## What this does not reach

- **No outage has been rehearsed against a real IdP.** The refusals above were produced with an
  issuer on a closed port; SSO itself is proven against Keycloak 26.4 only, over http on
  loopback, and against no commercial IdP. Break-glass sign-in itself is tested
  (`tests/test_break_glass_login.py`), including the refusal of a designated account that is
  not an administrator's.
- **The notice to other administrators is an inbox notice.** There is no email or pager: MAYA
  has no mailer. Watch the log line or the audit trail if nobody is reading the inbox.
- A person removed from an IdP group loses the MAYA role at their *next* sign-in; a session
  already open keeps it until it ends.
- Keycloak's "sign out all sessions" of a user was seen to send a back-channel logout token for
  one session only. MAYA ends what the token names.
