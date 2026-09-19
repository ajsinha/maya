# REST API guide

MAYA's public API is JSON over HTTP under `/api/v1`. The web UI, the Python SDK and the CLI all use exactly these endpoints, so anything they can do, your own client can do too, with the same permissions and the same audit trail. This guide covers authentication, the conventions every endpoint shares, errors, paging, idempotency and jobs, then lists the endpoints by area.

!!! tip "The interactive reference"
    The running server publishes its OpenAPI document at `/api/v1/openapi.json` and an interactive explorer at `/api/v1/docs`. They are generated from the same code that serves the requests, so they are always current.

## Base URL and versioning

| What | Where |
|---|---|
| API | `https://<host>/api/v1/...` |
| OpenAPI document | `/api/v1/openapi.json` |
| Interactive docs | `/api/v1/docs` |
| Liveness | `/healthz` (no authentication) |
| Readiness | `/readyz` (no authentication; 503 when not ready) |
| Prometheus metrics | `/metrics` (open, or a bearer token when `observability.metrics.token_env` is set) |

The version is in the path. Every path in the tables below is relative to `/api/v1`.

## Authentication

Every endpoint except the public ones named below needs a credential in the `Authorization` header:

```bash
# A bearer credential on every call
curl -s https://maya.example.com/api/v1/auth/me -H "Authorization: Bearer $MAYA_API_KEY"
```

MAYA accepts two kinds of credential, and both resolve to the same principal — the same roles, grants and audit identity.

| Credential | Looks like | Where it comes from | Lifetime |
|---|---|---|---|
| Session token | `maya_s_<secret>` | `POST /auth/login`, or a completed single sign-on | Ends after `auth.session.idle_timeout_minutes` (30) without use, or `auth.session.absolute_timeout_hours` (12) after sign-in, or at logout |
| API key | `maya_<env>_<key id>_<secret>` | `POST /auth/api-keys` | 1 to `auth.api_keys.max_days` (365) days; 90 by default |

MAYA stores only hashes: SHA-256 of session tokens, and the recorded password KDF for API-key secrets.

### Signing in with a password

```bash
# Sign in and keep the session token
TOKEN=$(curl -s -X POST https://maya.example.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "val.jones", "password": "…"}' | jq -r .token)
curl -s https://maya.example.com/api/v1/features?namespace=eq -H "Authorization: Bearer $TOKEN"
```

The login response carries `token`, `username`, `must_change_password`, `default_password` and `mfa`. When `mfa` is `challenge`, the session can do nothing until it answers the second factor: `POST /auth/mfa/verify` with `{"code": "123456"}`, or the security-key ceremony. When it is `enroll`, the session can do nothing but enroll. The only endpoints such a session may reach are `/auth/me`, `/auth/logout`, `/auth/mfa`, `/auth/mfa/verify`, `/auth/mfa/enroll`, `/auth/mfa/confirm` and the four security-key ceremony endpoints.

A password login is refused when `auth.mode` is `sso`. Five failures within fifteen minutes lock the account for thirty (the `auth.lockout` settings).

### API keys

```bash
# Create a narrow key: shown once
curl -s -X POST https://maya.example.com/api/v1/auth/api-keys \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "nightly-pins", "roles": ["feature_manager"], "namespaces": ["eq"],
       "actions": ["read", "pin"], "cidrs": ["10.20.0.0/16"], "days": 30}'
```

| Field | Meaning |
|---|---|
| `name` | A label. |
| `roles` | Narrow the key to these of your roles; empty keeps all of them. A key cannot carry a role you do not hold. |
| `namespaces` | Only objects in these namespaces. Empty: no namespace restriction. |
| `actions` | Only these actions (`read`, `download`, `create`, `update`, `submit`, `approve`, `pin`, `seal`, `request_pin`, `grant`, `revoke`). Empty: no action restriction. |
| `cidrs` | Only from these client networks. |
| `days` | Expiry, 1 to `auth.api_keys.max_days`. |

The response holds the full key in `api_key` with `"shown_once": true`; it cannot be read again. The environment segment makes a key valid in one environment only: a `uat` key is refused in `prod`.

### Single sign-on

People normally sign in through the browser. The same flows are exposed for clients that drive them:

| Step | OIDC | SAML 2.0 |
|---|---|---|
| Discover | `GET /auth/sso/config` (public) | `GET /auth/sso/config` (public) |
| Begin | `POST /auth/sso/start` (public) — returns the IdP URL with state, nonce and PKCE verifier to keep | `POST /auth/sso/start` is OIDC only; `POST /auth/sso/saml/start` (public) returns the IdP URL with a recorded AuthnRequest |
| Finish | `POST /auth/sso/callback` with `code`, `code_verifier`, `nonce` (public) | `POST /auth/sso/saml/acs` with `saml_response` (public) |
| Metadata | — | `GET /auth/sso/saml/metadata` (public, XML) |

Both end with a session token, exactly like a password login. SSO sessions take their second factor from the identity provider.

### Headers MAYA reads and writes

| Header | Direction | Meaning |
|---|---|---|
| `Authorization: Bearer …` | request | The credential. |
| `traceparent` | request and response | W3C trace context. Sent: MAYA continues your trace. Absent: MAYA starts one. Always returned. |
| `X-Request-Id` | request and response | Your request id, echoed; when absent, the trace id. |
| `X-Maya-Channel` | request | `web`, `cli` or `sdk`; recorded on audit entries. |
| `X-Maya-Client` | request | `python/<version>` from the SDK. A client older than the server supports is refused with 426. |
| `Idempotency-Key` | request | On pin requests only; see below. |
| `X-Maya-Manifest` | response | On data downloads: the manifest (rows, content hash, licence) as JSON. |

Every response also carries `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and, except on `/api/v1/docs`, a Content-Security-Policy.

## Conventions

- **JSON in, JSON out.** Request bodies are JSON unless the endpoint takes a file upload (multipart). Responses are `application/json`, encoded so that dates, decimals and numeric arrays are stable.
- **Dates and instants.** Dates are `YYYY-MM-DD`. Instants are ISO 8601; a trailing `Z` is accepted, and an instant without a zone is taken as UTC. A malformed value is a 422 naming the parameter.
- **References.** Objects are addressed as `maya://<kind>/<namespace>/<name>` with an optional `@v<n>` version or `#<pin>/<date>` pin, or in paths as `{namespace}/{name}`.
- **Status codes on success.** `200` for reads and most actions, `201` when something is created, `202` when work was queued as a job (pins, artifact upload, shadow replay, a challenge memo).
- **Actions return the object.** A transition returns the outcome: whether it moved, the state, a message, each check's result and outstanding approvals.
- **Downloads.** Data endpoints return the bytes with a `Content-Disposition` filename and the `X-Maya-Manifest` header. Formats: `parquet` (default), `arrow`, `csv`, `json`, `ndjson`.

## Errors

Every refusal is an RFC 9457 problem document, served as `application/problem+json`:

```json
{
  "type": "permission_denied",
  "title": "PermissionDenied",
  "status": 403,
  "detail": "You may not approve feature 'prices': role ceiling: no 'A' on feature in roles feature_designer",
  "context": {}
}
```

`type` is a stable code: branch on it, not on `detail`. `context` carries machine-readable specifics, such as the failed checks of a blocked transition or the term and source of a licence refusal.

| `type` | Status | Meaning |
|---|---|---|
| `invalid_cursor` | 400 | A paging cursor was altered, truncated or reused for a different query. |
| `not_authenticated` | 401 | No credential, or an ended, expired, locked, malformed or wrong-environment one; or a session still owing its second factor. |
| `permission_denied` | 403 | Role ceiling, grant, API-key scope, separation of duties or an administrator-only action. |
| `not_found` | 404 | No such object. |
| `conflict` | 409 | The object already exists or changed underneath you. |
| `not_approved` | 409 | The object's state does not allow it: a transition from the wrong state, a blocked check, an unsealed or revoked warrant. |
| `warrant_expired` | 410 | A warrant is past its validity. |
| `validation_failed` | 422 | The request or a definition is invalid; also every request-shape error (a missing field, a wrong type). |
| `contract_mismatch` | 422 | Inputs do not satisfy a model's input contract. |
| `quality_check_failed` | 422 | A data quality contract failed. |
| `warrant_suspended` | 423 | An execution warrant is suspended by a covenant breach. |
| `client_too_old` | 426 | The SDK is older than the server supports. |
| `quota_exceeded` | 429 | An execution warrant's daily allowance is used. |
| `licence_breach` | 451 | A data licence forbids the action; `context` names the term and the source that imposed it. |
| `configuration_error` | 500 | A setting is wrong. |
| `capability_refused` | 503 | A required capability is not installed (for example the `cryptography` package for signing). MAYA refuses rather than substituting a weaker one. |

!!! note "Refusals are audited"
    Denied approvals, pins, seals, grants and revocations, failed API-key checks, SSO refusals and licence refusals on export are written to the audit log even though the request itself rolled back.

## Paging

List endpoints that can grow return the whole list by default. Pass `page_size` or `cursor` and they return one page instead:

| Parameter | Meaning |
|---|---|
| `page_size` | 1 to 1000. Default 100 once paging is on. |
| `cursor` | The `next_cursor` of the previous page. |
| `sort` | One of the list's sort names; `-` in front means descending. |
| `total` | `true` adds `total`, the count of matching rows before per-row authorization. |

```json
{"items": [ … ], "next_cursor": "eyJ…", "page_size": 100, "sort": "name"}
```

`next_cursor` is `null` on the last page. Paging is keyset-based — the sort column then the primary key — so a page is stable while rows are added elsewhere, and rows you may not read are filtered before the page is cut.

| List | Endpoint | Sorts (default first) |
|---|---|---|
| Features | `GET /features` | `name`, `-name`, `updated`, `-updated`, `created`, `-created` |
| Feature sets | `GET /featuresets` | the same |
| Models | `GET /models` | the same |
| Training warrants | `GET /warrants/training` | `-created`, `created`, `name`, `-name` |
| Execution warrants | `GET /warrants/execution` | `-created`, `created`, `name`, `-name` |
| Jobs | `GET /jobs` | `-created`, `created` |
| Audit | `GET /audit` | `-seq`, `seq` |
| Inbox | `GET /inbox` | `-created`, `created` |
| Grants | `GET /grants` | `created`, `-created` |
| Events | `GET /events` | `seq`, `-seq` |

A cursor is opaque and signed with the server's secret. It is bound to the query that issued it — its table, sort, filters and search — so a tampered cursor, or one replayed with a different filter or sort, is refused with `invalid_cursor` rather than answering some other page. Start again without a cursor.

```bash
# Walk every feature in namespace eq, 500 at a time
cursor=""
while :; do
  page=$(curl -s -G https://maya.example.com/api/v1/features \
    -H "Authorization: Bearer $MAYA_API_KEY" \
    --data-urlencode namespace=eq --data-urlencode page_size=500 \
    ${cursor:+--data-urlencode cursor=$cursor})
  echo "$page" | jq -r '.items[].name'
  cursor=$(echo "$page" | jq -r '.next_cursor // empty')
  [ -z "$cursor" ] && break
done
```

## Idempotency and retries

Pin requests take an `Idempotency-Key` header. A second request with the same key returns the job the first one created instead of pinning twice, so a retried or double-clicked pin is safe.

```bash
# A pin that is safe to retry
curl -s -X POST https://maya.example.com/api/v1/features/eq/prices/pins \
  -H "Authorization: Bearer $MAYA_API_KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: prices-eod-2026-09-18" \
  -d '{"version_no": 3, "pin_name": "eod", "as_of": "2026-09-18"}'
```

No other write takes the header. `GET`, `PUT` and `DELETE` are safe to repeat; other `POST`s are not. The Python SDK retries only the safe ones, plus any call with an `Idempotency-Key`.

## Jobs

Slow operations run as jobs in a database-backed queue and answer `202` with the job. A pin answers `{"pin": …, "job": …}`; the job is `null` when your role can only request the pin and it awaits approval.

| Job state | Meaning |
|---|---|
| `queued` | Waiting for a worker. |
| `running` | A worker holds it; `progress` (0–100) and `message` move. |
| `succeeded` | Finished; `result` holds the outcome. |
| `failed` | A deliberate refusal (a quality failure, a contract mismatch): not retried, because it would refuse again. `result.problem` holds the problem document. |
| `cancelled` | Cancelled on request: at once when queued, between stages when running. |
| `dead_letter` | An unexpected error kept recurring: MAYA requeued it with backoff until `jobs.max_attempts` ran out, then kept the failure and traceback. |

Poll `GET /jobs/{id}`, or follow `GET /jobs/{id}/events`, a server-sent event stream that sends the job's `id`, `state`, `progress`, `message` and `error` whenever they change and closes at a terminal state.

```bash
# Follow a job as it runs
curl -N https://maya.example.com/api/v1/jobs/$JOB/events -H "Authorization: Bearer $MAYA_API_KEY"
```

`POST /jobs/{id}/retry` requeues a failed or dead-lettered job (administrators and techops).

## Endpoints by area

### Authentication and your account

| Method and path | Purpose |
|---|---|
| `POST /auth/login` | Password sign-in (public). |
| `POST /auth/logout` | End this session. |
| `GET /auth/me` | You: roles, capabilities, groups, channel. |
| `POST /auth/password` | Change your password (`old_password`, `new_password`). |
| `GET /auth/sso/config`, `POST /auth/sso/start`, `POST /auth/sso/callback` | OIDC (public). |
| `GET /auth/sso/saml/metadata`, `POST /auth/sso/saml/start`, `POST /auth/sso/saml/acs` | SAML (public). |
| `GET /auth/mfa`, `POST /auth/mfa/verify`, `POST /auth/mfa/enroll`, `POST /auth/mfa/confirm` | TOTP status, challenge and enrollment. |
| `GET /auth/mfa/webauthn`, `DELETE /auth/mfa/webauthn/{key_id}` | Your security keys. |
| `POST /auth/mfa/webauthn/register/options`, `POST /auth/mfa/webauthn/register` | Register a security key. |
| `POST /auth/mfa/webauthn/options`, `POST /auth/mfa/webauthn/verify` | Answer a challenge with a security key. |
| `GET /auth/api-keys`, `POST /auth/api-keys`, `DELETE /auth/api-keys/{key_id}` | Your API keys (`?all=true` lists everyone's, administrators only). |
| `GET /auth/sessions`, `DELETE /auth/sessions/{session_id}` | Live sessions (administrators). |

### Administration and access

| Method and path | Purpose |
|---|---|
| `GET /users`, `POST /users`, `PATCH /users/{username}` | Users. |
| `PUT /users/{username}/roles` | Replace a user's roles. |
| `POST /users/{username}/password-reset`, `POST /users/{username}/mfa-reset` | Reset a password or a second factor. |
| `GET /roles`, `POST /roles` | Roles, including custom ones. |
| `GET /groups`, `POST /groups` | Groups. |
| `GET /namespaces`, `POST /namespaces`, `PATCH /namespaces/{name}` | Namespaces. |
| `GET /grants?kind=&ref=`, `POST /grants`, `DELETE /grants/{grant_id}` | Grants on one object. |
| `GET /access/recertification` | Grants on objects you own. |
| `GET /audit`, `GET /audit/verify` | The audit log and its chain (administrators and techops). |
| `GET /inbox`, `POST /inbox/read` | Your notifications. |
| `GET /search?q=&limit=` | Catalog search over what you may read. |
| `POST /search/reindex` | Rebuild the search index (administrators). |
| `GET /lineage?root=&direction=&depth=` | The lineage graph around an object. |

### Catalog: features and feature sets

| Method and path | Purpose |
|---|---|
| `GET /features`, `POST /features` | List and create. |
| `POST /features/infer`, `POST /features/quick` | Infer a definition from a file; a scratch feature in one call. |
| `GET /features/{ns}/{name}` | One feature with its versions. |
| `PUT /features/{ns}/{name}/draft`, `POST /features/{ns}/{name}/drafts` | Edit the draft; open a new draft. |
| `POST /features/{ns}/{name}/clone` | Clone or extend. |
| `POST /features/{ns}/{name}/ingest`, `POST /features/{ns}/{name}/pull` | Load data from an upload or a source. |
| `POST /features/{ns}/{name}/versions/{v}/transitions/{t}` | Workflow. |
| `GET /features/{ns}/{name}/compare?v1=&v2=` | Compare versions. |
| `POST /features/{ns}/{name}/draft-preview` | Resolve the draft without saving. |
| `POST /features/{ns}/{name}/pins` | Pin (202; `Idempotency-Key`). |
| `POST /pins/{pin_id}/approve`, `POST /pins/{pin_id}/retire` | Approve a requested pin; retire a pin. |
| `GET /feature-data/preview`, `GET /feature-data` | Preview; download. |
| `GET /sql-connections`, `POST /sql-connections`, `DELETE /sql-connections/{name}`, `POST /sql-connections/{name}/test` | Named SQL connections for sources. |
| `GET /featuresets`, `POST /featuresets`, `GET /featuresets/{ns}/{name}` | Feature sets. |
| `PUT /featuresets/{ns}/{name}/draft`, `POST /featuresets/{ns}/{name}/drafts` | Drafts. |
| `POST /featuresets/{ns}/{name}/versions/{v}/transitions/{t}` | Workflow. |
| `POST /featuresets/{ns}/{name}/draft-preview`, `POST /featuresets/{ns}/{name}/pins` | Preview a draft; pin (202). |
| `GET /featureset-data/preview`, `GET /featureset-data` | Preview; download. |
| `GET /licences?kind=&ref=` | The effective licence of a feature or feature set. |

### Models

| Method and path | Purpose |
|---|---|
| `GET /models`, `POST /models`, `GET /models/{ns}/{name}` | List, create, read. |
| `PUT /models/{ns}/{name}/draft`, `POST /models/{ns}/{name}/drafts` | Drafts. |
| `POST /models/{ns}/{name}/artifact` | Upload a Python artifact; validated as a job (202). |
| `POST /models/workbook/lift`, `POST /models/{ns}/{name}/workbook` | Lift an Excel workbook; import it into the draft. |
| `GET /models/{ns}/{name}/versions/{v}/workbook.xlsx` | The model as a workbook. |
| `POST /models/{ns}/{name}/versions/{v}/render`, `GET /models/{ns}/{name}/versions/{v}/spec.pdf` | Render and fetch the specification PDF. |
| `POST /models/{ns}/{name}/versions/{v}/transitions/{t}` | Workflow. |
| `GET /models/{ns}/{name}/diff?v1=&v2=` | What changed. |
| `GET /models/{ns}/{name}/versions/{v}/reference` | Generated reference code. |
| `POST /models/{ns}/{name}/versions/{v}/conformance` | Conformance test of the artifact against the formula. |

### Warrants and bundles

| Method and path | Purpose |
|---|---|
| `GET /warrants/training`, `POST /warrants/training`, `GET /warrants/training/{id}` | Training warrants. |
| `GET /warrants/training/{id}/data` | Training data (Parquet, with the manifest). |
| `POST /warrants/training/{id}/parameters` | Upload a parameter set. |
| `POST /warrants/training/{id}/transitions/{t}`, `POST /warrants/training/{id}/seal`, `POST /warrants/training/{id}/revoke`, `POST /warrants/training/{id}/clone` | Lifecycle. |
| `POST /warrants/training/{id}/score` | Blind holdout scoring. |
| `POST /warrants/training/{id}/bundle` | Export a reproducibility bundle (201). |
| `POST /parameters/{id}/transitions/{t}` | Parameter set workflow. |
| `POST /bundles/verify` | Verify an uploaded bundle. |
| `GET /warrants/execution`, `POST /warrants/execution`, `GET /warrants/execution/{id}` | Execution warrants. |
| `POST /warrants/execution/{id}/transitions/{t}`, `POST /warrants/execution/{id}/seal` | Lifecycle. |
| `POST /warrants/execution/{id}/token`, `GET /warrants/execution/{id}/bundle?environment=` | A signed run token; everything needed to run. |
| `POST /warrants/execution/{id}/report` | Report a run; covenants evaluated. |
| `POST /warrants/execution/{id}/reinstate`, `POST /warrants/execution/{id}/revoke` | Lift a suspension; revoke. |

### Workflow and workspaces

| Method and path | Purpose |
|---|---|
| `GET /workflow/queue`, `GET /workflow/aging`, `GET /workflow/break-glass` | Your queue, overdue items, forced transitions. |
| `GET /workflow/policies`, `GET /workflow/policies/{id}`, `GET /workflow/policies/{id}/yaml` | Policies. |
| `POST /workflow/policies`, `POST /workflow/policies/import`, `POST /workflow/policies/validate`, `POST /workflow/policies/{id}/activate` | Draft, import, validate, activate. |
| `GET /workflow/population/{object_type}` | Objects per state. |
| `GET /workflow/history?object_type=&object_id=` | An object's transitions. |
| `GET /workflow/comments`, `POST /workflow/comments`, `POST /workflow/comments/{id}/resolve` | Review comments. |
| `POST /workflow/transitions` | A transition on any object, by type and id. |
| `GET /workflow/delegations`, `POST /workflow/delegations`, `DELETE /workflow/delegations/{id}` | Delegations. |
| `GET /workflow/campaigns`, `POST /workflow/campaigns` | Campaigns. |
| `GET /workspaces`, `POST /workspaces`, `GET /workspaces/{id}` | Workspaces. |
| `PUT /workspaces/{id}/changes`, `DELETE /workspaces/{id}/changes/{change_id}` | Stage and unstage. |
| `GET /workspaces/{id}/preview`, `GET /workspaces/{id}/impact`, `POST /workspaces/{id}/replay` | Preview, impact, shadow replay (202). |
| `POST /workspaces/{id}/submit`, `POST /workspaces/{id}/abandon` | Submit or abandon. |
| `GET /assistant/memos`, `POST /assistant/memos`, `POST /assistant/memos/{id}/stance` | Challenge memos and your response. |

### Events, custody and operations

| Method and path | Purpose |
|---|---|
| `GET /events?after=&limit=&type=` | Events after a sequence number (administrators and techops). `type` is a prefix of the event type: `pin.` gives every pin event, `pin.sealed` just that one. |
| `GET /events/stream?after=` | Server-sent events: `id` is the sequence, `event` the type; reconnect with the last id. |
| `GET /webhooks`, `POST /webhooks`, `DELETE /webhooks/{id}`, `GET /webhooks/{id}/deliveries`, `POST /webhooks/{id}/ping` | Webhooks. |
| `GET /custody/anchors`, `POST /custody/anchor`, `GET /custody/verify` | Audit anchors (administrators and techops). |
| `GET /system/health`, `GET /system/config`, `GET /system/storage` | Health, effective configuration (administrators), storage report. |
| `POST /system/integrity`, `POST /system/lake/maintain` | Integrity verification; lake compaction (administrators and techops). |
| `GET /system/estate` | The estate export (administrators). |
| `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `POST /jobs/{id}/retry`, `GET /jobs/{id}/events` | Jobs. |
| `GET /blobs/{digest}` | A blob you uploaded or exported (administrators: any). |

!!! warning "Server-side bundle verification runs only MAYA's own bundles"
    `POST /bundles/verify` executes code only for a bundle signed by this instance's key whose every file still matches its signed hash, and then with MAYA's own verifier. Any other bundle is reported as not executed; verify it offline with its `verify.py`.
