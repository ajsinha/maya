# Default-password remediation

For whoever is installing MAYA, or has just been told a production instance is still running on
the password it shipped with. MAYA seeds one account, `admin`, with the password
`maya-dev-admin` — a value that is in the source, in this repository, and therefore public.
Anybody who can reach the instance can sign in as an administrator until it is changed.

MAYA is loud about this on purpose: outside `dev` it **refuses to start** while that password is
in place, and in `dev` it says so in the banner, on every page and on the health page. This
runbook is the fix, and the parts of it that are easy to get subtly wrong.

## Symptoms

- **Startup is refused** outside `dev`:

  ```text
  maya.core.errors.CapabilityRefused: The bootstrap admin still has the default password in a
  non-dev environment. Change it, or set app.allow_default_admin_password: true.
  ```

- The startup banner, in `dev`:

  ```text
    !! The bootstrap admin still uses the default password 'maya-dev-admin'. Change it now.
  ```

- A red band on every web page: *"The bootstrap **admin** still uses the default password
  `maya-dev-admin`. Change it now."*
- `/admin/health` shows the same in red, and `GET /api/v1/system/health` carries
  `"default_admin_password": true`.
- `/metrics` reports `maya_default_admin_password 1`, and the `MayaDefaultAdminPassword` alert
  fires ([the rules file](../../../config/prometheus/maya-slo.rules.yml)).
- A login as `admin` answers with the flags that say it:

  ```json
  {"token":"maya_s_…","username":"admin","must_change_password":true,"default_password":true,"mfa":"ok"}
  ```

## Diagnosis

There is nothing to diagnose: either the flag is true or it is not.

```bash
curl -s "$MAYA_URL/api/v1/system/health" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import json,sys; print('default_admin_password =', json.load(sys.stdin)['default_admin_password'])"
# default_admin_password = True
```

What *does* need establishing is whether the window was used. A public password on a reachable
instance is an exposure, not a tidiness problem, so before you close it, find out what happened
through it:

```bash
# Every sign-in as admin, with the address it came from
curl -s "$MAYA_URL/api/v1/audit?actor=admin" -H "Authorization: Bearer $MAYA_API_KEY"
# Grants, users, roles and keys created while it was open — the things an intruder would leave behind
for a in access.granted user.created api_key.created role.updated; do
  curl -s "$MAYA_URL/api/v1/audit?action=$a" -H "Authorization: Bearer $MAYA_API_KEY"
done
# Sessions still open as admin
curl -s "$MAYA_URL/api/v1/auth/sessions?all=true" -H "Authorization: Bearer $MAYA_API_KEY"
```

If any of it is unexplained, this stops being a password change and becomes an incident: go to
[audit chain and custody](audit-chain-and-custody.md) to establish the log has not been edited,
and revoke every API key and session as below.

## Steps

1. **Change the password.** Through the UI — sign in as `admin`, *Account → Password* — or over
   the API:

   ```bash
   T=$(curl -s -X POST "$MAYA_URL/api/v1/auth/login" -H 'Content-Type: application/json' \
        -d '{"username":"admin","password":"maya-dev-admin"}' \
        | python -c "import json,sys; print(json.load(sys.stdin)['token'])")
   curl -s -X POST "$MAYA_URL/api/v1/auth/password" -H "Authorization: Bearer $T" \
     -H 'Content-Type: application/json' \
     -d '{"old_password":"maya-dev-admin","new_password":"<a real one>"}'
   # {"ok":true}
   ```

   The new password must satisfy `auth.password.min_length` (12 by default). The change is
   audited as `auth.password_changed`.

2. **Confirm the flag cleared before doing anything else:**

   ```bash
   curl -s "$MAYA_URL/api/v1/system/health" -H "Authorization: Bearer $T" \
     | python -c "import json,sys; print('default_admin_password =', json.load(sys.stdin)['default_admin_password'])"
   # default_admin_password = False
   curl -s "$MAYA_URL/metrics" | grep '^maya_default_admin_password'
   # maya_default_admin_password 0
   ```

3. **If MAYA will not start, you cannot use step 1** — there is no server to talk to. Start it
   once in `dev`, change the password, stop it, and start it in the real environment:

   ```bash
   python run_maya_web.py --app.environment=dev --server.host=127.0.0.1 --server.port=8699
   # change the password, then stop it and start normally
   ```

   Bind it to `127.0.0.1` while you do that. Do **not** reach for
   `--app.allow_default_admin_password=true`: it starts a production instance with a public
   administrator password, which is the exact thing the refusal exists to prevent. It is there
   for an installation still being wired up, on a network nobody else is on, and it belongs in a
   change record with a date by which it will be removed.

4. **Then finish the account properly**, because a changed password is not a secured
   administrator:
   - **Enrol a second factor.** `auth.mfa.required_for_roles` includes `admin` by default, and
     outside `dev` `auth.mfa.enforce: auto` enforces it — but only once somebody enrols.
     *Account → Security* does it.
   - **Make a named administrator and stop using `admin`.** `admin` is a bootstrap account: it
     belongs to nobody, so nothing it does is attributable to a person. Create real accounts
     with real roles, and keep `admin` as the break-glass account
     ([SSO outage](sso-outage.md)) with its password in the same escrow as the rest of the
     break-glass procedure.
   - **In `auth.mode: sso`, password logins are refused entirely** — including `admin`'s. Change
     this password *before* switching to SSO, and read the SSO runbook on what break-glass means
     there, because it is currently a gap: MAYA refuses all password logins in `sso` mode.

5. **If the window may have been used**, revoke everything issued in it:

   ```bash
   curl -s "$MAYA_URL/api/v1/auth/api-keys?all=true" -H "Authorization: Bearer $T"      # then revoke each
   curl -s -X DELETE "$MAYA_URL/api/v1/auth/api-keys/<key-id>" -H "Authorization: Bearer $T"
   ```

   Ending every session of the account is the *Sessions* panel under *Account → Security*.
   Recertify grants (`/access/recertification`) rather than assuming they are all intended.

## Verification

- `default_admin_password` is `false` in the health payload, `maya_default_admin_password` is `0`
  in `/metrics`, the red band is gone from the web pages, and the banner no longer warns.
- MAYA starts in the real environment with no refusal, and `/readyz` is ready.
- Signing in as `admin` with `maya-dev-admin` fails with *"Invalid username or password"*.
- The change is in the audit log as `auth.password_changed`.
- `admin` has a second factor enrolled, and at least one named administrator exists.

**Commands run while this runbook was written.** All of the diagnosis and remediation against a
throwaway `MAYA_HOME` on SQLite: the login (whose JSON above is the actual response, including
`must_change_password` and `default_password`), the `POST /api/v1/auth/password` change, the
health flag going from `True` to `False`, `maya_default_admin_password` going from `1` to `0`,
and the non-dev startup refusal — whose text above is quoted from the actual failure, produced by
starting with `--app.environment=uat` before the change and succeeding after it. The API-key and
session revocations, and the audit queries, are **not exercised** (the throwaway estate had
neither keys nor a second administrator).

## What this does not reach

- **It does not tell you whether the password was used by somebody else.** MAYA audits every
  sign-in with its address, but a legitimate-looking sign-in from an expected address is
  indistinguishable from an intruder who knew where to come from.
- **`maya-dev-admin` is in the source.** Changing it in a deployment does not change that every
  new MAYA installation starts with the same known value, and nothing forces a change at
  install time other than the refusal above.
- **No password history or maximum age** (§12). The new password may be the old one's neighbour,
  and nothing will ever ask for it to be rotated. `must_change_password` is reported at login but
  MAYA does not force the change.
- **No admin break-glass login in `auth.mode: sso`** (§13.3 asks for one). In `sso` mode every
  password login is refused, `admin` included, so the account this runbook secures cannot be
  used at all there.
- **Nothing scans for other weak passwords.** Only `admin`'s shipped value is checked, and only
  against that one string.
