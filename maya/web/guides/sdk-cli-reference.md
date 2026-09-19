# Python SDK and CLI reference

The Python SDK, `maya.sdk`, is the one client of MAYA. The web UI calls it with your session, the command line wraps it, and notebooks and CI jobs use it directly — so anything the browser can do, a script can do, with the same permissions and the same audit trail. Every SDK method is one call to the REST API under `/api/v1`; this reference names the endpoint beside each method.

## Connecting

```python
# Connect with an API key
import maya.sdk as maya
my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
print(my.auth.me()["username"])
```

### Client

`maya.sdk.Client(base_url="http://127.0.0.1:8600", *, api_key=None, token=None, app=None, timeout=120.0, channel="sdk", verify=True)`

| Argument | Meaning |
|---|---|
| `base_url` | The server, without `/api/v1` (the client adds it). |
| `api_key` | An API key, `maya_<env>_<key id>_<secret>`. |
| `token` | A session token from `auth.login` (`maya_s_…`). Used instead of `api_key` when both are given. |
| `app` | An ASGI application: the client then runs in-process (`mode == "inproc"`) instead of over HTTP. MAYA's own tests and the web tier use this. |
| `timeout` | Seconds per request (connect timeout 10 s). |
| `channel` | Recorded on audit entries: `sdk`, `cli` or `web`. |
| `verify` | TLS verification: `True`, `False`, or a CA bundle path. |

The client is a context manager (`with maya.Client(...) as my:`) and has `close()`.

!!! warning "Credentials never travel over plain HTTP"
    A client given a key or token refuses a `http://` URL unless the host is `localhost`, `127.0.0.1` or `::1`. Use `https://`.

### AsyncClient

`maya.sdk.AsyncClient(base_url="http://127.0.0.1:8600", *, api_key=None, token=None, app=None, timeout=120.0, channel="sdk")` has the same namespaces and methods, each a coroutine. Close it with `await client.aclose()` or use `async with`. It does not retry, and it has no `wait` or `training_data`. `AsyncClient.record(path, …)` and `AsyncClient.replay(path)` work as they do for `Client`, and a cassette recorded by either client replays in the other.

```python
# The async client
import asyncio
import maya.sdk as maya

async def main():
    async with maya.AsyncClient("https://maya.example.com", api_key="maya_prod_…") as my:
        print(len(await my.features.list(namespace="eq")))

asyncio.run(main())
```

### connect()

`maya.sdk.connect(profile=None, *, base_url=None, api_key=None)` builds a `Client` from arguments, the environment or a profile file, so scripts carry no credentials.

| Resolved | In this order |
|---|---|
| The key | `api_key` argument → `MAYA_API_KEY` → the variable named by the profile's `api_key_env` |
| The URL | `base_url` argument → `MAYA_URL` → the profile's `base_url` → `http://127.0.0.1:8600` |
| The profile file | `MAYA_CONFIG`, else `~/.maya/config.toml`; a missing file is an error when a profile is named |

Set `MAYA_DEBUG_AUTH` to print where the credential came from.

```toml
# ~/.maya/config.toml
[profiles.prod]
base_url = "https://maya.example.com"
api_key_env = "MAYA_PROD_KEY"   # the key itself stays in the environment
```

## Conventions

- **References.** Methods that take `ref` accept a `maya://` reference (`maya://feature/eq/prices@v2`) or the short `namespace/name` form.
- **Lists and pages.** `list(...)` returns every row. `page(...)` returns one page: `{"items", "next_cursor", "page_size", "sort"}` plus `"total"` when `total=True`. `iter(...)` follows `next_cursor` for you and yields rows. The default page size is 100; the server allows 1 to 1000.
- **Jobs.** Slow work (pins, artifact validation, shadow replays) returns a job. `my.wait(job)` polls it.
- **Downloads.** Download methods return `{"data": bytes, "manifest": dict, "content_type": str}`.
- **Retries.** The synchronous client retries `GET`, `PUT` and `DELETE`, and any call carrying an `Idempotency-Key`, up to three times on network failures and on 429, 502, 503 and 504, with backoff. Other writes are not retried.

### Errors

Every refusal raises a typed exception, a subclass of `maya.sdk.MayaError`, carrying `.message`, `.status` and `.context`.

| Exception | Status | Meaning |
|---|---|---|
| `ValidationFailed` | 422 | The request or definition is invalid. |
| `NotAuthenticated` | 401 | No credential, or an ended, expired or unrecognised one. |
| `PermissionDenied` | 403 | Your roles, grants or key scope do not allow it. |
| `NotFound` | 404 | No such object. |
| `ConflictError` | 409 | The object changed, or already exists. |
| `NotApproved` | 409 | The object is not in a state that allows it. |
| `ContractMismatch` | 422 | Inputs do not satisfy a declared input contract. |
| `WarrantExpired` | 410 | A warrant is past its validity. |
| `WarrantSuspended` | 423 | An execution warrant is suspended by a covenant breach. |
| `QuotaExceeded` | 429 | An execution warrant's daily allowance is used. |
| `LicenceBreach` | 451 | A data licence forbids it; the context names the term and its source. |

`MayaError` is also raised for a network failure (code `transport_error`) and, from `wait`, for a job that ends other than `succeeded`. A client older than the server supports is refused with 426 (`client_too_old`) before its request runs.

```python
# Catch a licence refusal by name
try:
    blob = my.features.download("maya://feature/eq/prices@v1")
except maya.LicenceBreach as exc:
    print("refused:", exc.message, exc.context.get("source"))
```

## Client helpers

| Method | What it does |
|---|---|
| `wait(job, *, timeout=600.0, progress=None)` | Polls a job (a dict or an id) every 0.3 s until `succeeded`, `failed`, `cancelled` or `dead_letter`. Returns the job row on success; raises `MayaError` on any other terminal state or on timeout. `progress(row)` is called whenever progress or message changes. |
| `training_data(warrant_id)` | Downloads a training warrant's data, recomputes its content checksum and returns `(pyarrow.Table, manifest)`. Raises `ValidationFailed` when the checksum does not match the one MAYA issued. Needs `pyarrow`. |
| `Client.record(cassette, base_url="http://127.0.0.1:8600", **kw)` | A live client that also writes every request and response to a cassette file. |
| `Client.replay(cassette)` | A client served entirely from a cassette: no server, no network. |

```python
# Pin a feature set and wait for it
job = my.featuresets.pin("eq/panel", version_no=2, pin_name="eom", as_of="2026-03-31",
                         cascade=True, idempotency_key="panel-eom-2026-03-31")
done = my.wait(job["job"], progress=lambda j: print(j["progress"], j["message"]))
print(done["result"])
```

### Record and replay

A cassette is JSON in the format `maya-cassette/1`.

| Rule | Behaviour |
|---|---|
| Matching | Method, path, query parameters and a hash of the body and uploaded files. Identical requests replay their recordings in order; a `GET` polled more often than it was recorded repeats its last response. |
| Refusals | Replay as the same exception class with the same context. |
| Binary downloads | Kept, base64-encoded. |
| Credentials | Request headers are never recorded. Response fields named `token`, `access_token`, `refresh_token`, `id_token`, `secret`, `api_key`, `password`, `mfa_secret`, `client_secret`, `otpauth_uri`, or ending in `_secret` or `_token`, are written as `<redacted>`. |
| A miss | Raises `maya.sdk.replay.ReplayMiss`, naming the request. A replay never guesses. |

```python
# Record once, replay in tests
live = maya.Client.record("tests/fixtures/prices.json",
                          base_url="https://maya.example.com", api_key="maya_…")
panel = live.features.preview("maya://feature/eq/prices@v1")
tape = maya.Client.replay("tests/fixtures/prices.json")
assert tape.features.preview("maya://feature/eq/prices@v1") == panel
```

### Offline bundles

`maya.sdk.offline(bundle)` opens a reproducibility bundle (a path or bytes) and returns an `Offline` object. Opening checks every file against the manifest's hash and the Ed25519 signature over the file list (when `cryptography` is installed; otherwise the report says the signature was not checked). A bundle that fails is refused, not partly served.

| Member | What it does |
|---|---|
| `verify()` | The verification report. |
| `training.get(warrant_id=None)` | The warrant document. |
| `training.data(warrant_id=None)` | The training data, as a live client returns it. |
| `training_data(warrant_id=None)` | `(pyarrow.Table, manifest)`, checksum-verified. |
| `models.get(ref=None)` | The model version document. |
| `parameters()` | The parameter values. |
| `certificate()` | The signed leakage certificate. |
| `predict(X, params=None)` | Evaluates the signed formula IR with MAYA's evaluator on a dict of arrays. |
| `json(name)`, `table()` | A named JSON file from the bundle; the data table. |
| `close()` | Also usable as a context manager. |

The bundle's `reference_model.py` is never imported: opening a bundle never runs code it carries. Anything a bundle does not hold — the catalog, workflow, other warrants — raises `maya.sdk.offline.NotInBundle`, as does `predict` on a black box or on a composite with a member that is not closed-form. A composite of closed-form members is evaluated from its signed member IRs.

## SDK namespaces

Each namespace is an attribute of the client: `my.features`, `my.training`, and so on.

### auth

| Method | Endpoint |
|---|---|
| `login(username, password)` | `POST /auth/login` |
| `logout()` | `POST /auth/logout` |
| `me()` | `GET /auth/me` |
| `change_password(old_password, new_password)` | `POST /auth/password` |
| `sso_config()` | `GET /auth/sso/config` |
| `sso_start()` | `POST /auth/sso/start` |
| `sso_callback(code, code_verifier, nonce)` | `POST /auth/sso/callback` |
| `oidc_backchannel_logout(logout_token)` | `POST /auth/sso/oidc/backchannel-logout` — what the IdP does server to server; here for tests and tooling |
| `saml_metadata()` | `GET /auth/sso/saml/metadata` |
| `saml_start(relay_state="")` | `POST /auth/sso/saml/start` |
| `saml_acs(saml_response)` | `POST /auth/sso/saml/acs` |
| `saml_sls(query_string)` | `POST /auth/sso/saml/sls` — the IdP's single-logout redirect query string, unaltered |
| `mfa_status()` | `GET /auth/mfa` |
| `mfa_verify(code)` | `POST /auth/mfa/verify` |
| `mfa_enroll()` | `POST /auth/mfa/enroll` |
| `mfa_confirm(code)` | `POST /auth/mfa/confirm` |
| `security_keys()` | `GET /auth/mfa/webauthn` |
| `remove_security_key(key_id)` | `DELETE /auth/mfa/webauthn/{key_id}` |
| `security_key_register_options()` | `POST /auth/mfa/webauthn/register/options` |
| `register_security_key(credential, name="security key")` | `POST /auth/mfa/webauthn/register` |
| `security_key_options()` | `POST /auth/mfa/webauthn/options` |
| `security_key_verify(credential)` | `POST /auth/mfa/webauthn/verify` |
| `api_keys(all=False)` | `GET /auth/api-keys` |
| `create_api_key(name, **kw)` | `POST /auth/api-keys` — `roles`, `namespaces`, `actions`, `cidrs`, `days` (default 90) |
| `revoke_api_key(key_id)` | `DELETE /auth/api-keys/{key_id}` |
| `sessions()` | `GET /auth/sessions` |
| `end_session(session_id)` | `DELETE /auth/sessions/{session_id}` |

### admin

| Method | Endpoint |
|---|---|
| `users()` | `GET /users` |
| `create_user(username, **kw)` | `POST /users` — `password`, `email`, `display_name`, `roles`, `is_service`, `desk` |
| `update_user(username, **changes)` | `PATCH /users/{username}` — `email`, `display_name`, `status`, `desk` |
| `set_roles(username, roles)` | `PUT /users/{username}/roles` |
| `reset_password(username, new_password)` | `POST /users/{username}/password-reset` |
| `reset_mfa(username)` | `POST /users/{username}/mfa-reset` |
| `roles()` | `GET /roles` |
| `create_role(name, capabilities, description="")` | `POST /roles` |
| `groups()` | `GET /groups` |
| `create_group(name, **kw)` | `POST /groups` — `description`, `roles`, `members` |
| `audit(q=None, action=None, limit=1000)` | `GET /audit` |
| `audit_page(...)`, `iter_audit(...)` | `GET /audit` with paging |
| `verify_audit()` | `GET /audit/verify` |
| `health()` | `GET /system/health` |
| `config()` | `GET /system/config` |
| `lake_maintain()` | `POST /system/lake/maintain` |
| `storage()` | `GET /system/storage` |
| `verify_integrity()` | `POST /system/integrity` |
| `export_estate()` | `GET /system/estate` |
| `blob(digest)` | `GET /blobs/{digest}` |

### sources

| Method | Endpoint |
|---|---|
| `connections()` | `GET /sql-connections` |
| `create_connection(name, url, password_env=None, description="")` | `POST /sql-connections` |
| `delete_connection(name)` | `DELETE /sql-connections/{name}` |
| `test_connection(name)` | `POST /sql-connections/{name}/test` |

### namespaces

| Method | Endpoint |
|---|---|
| `list()` | `GET /namespaces` |
| `create(name, **kw)` | `POST /namespaces` — `description`, `parent`, `preset`, `default_visibility`, `production`, `classification`, `quota_bytes` |
| `update(name, **changes)` | `PATCH /namespaces/{name}` |

### access

| Method | Endpoint |
|---|---|
| `grants(kind, ref)` | `GET /grants` |
| `grants_page(...)`, `iter_grants(...)` | `GET /grants` with paging |
| `grant(kind, object_ref, principal_type, principal_id, level, **kw)` | `POST /grants` — `days` (default 90), `deny`, `conditions` |
| `revoke(grant_id)` | `DELETE /grants/{grant_id}` |
| `recertification()` | `GET /access/recertification` |
| `inbox()` | `GET /inbox` |
| `inbox_page(...)`, `iter_inbox(...)` | `GET /inbox` with paging |
| `mark_read(ids=None)` | `POST /inbox/read` |
| `search(q, limit=50)` | `GET /search` |
| `reindex_search()` | `POST /search/reindex` |
| `lineage(root, direction="both", depth=3)` | `GET /lineage` — objects you may not read are left out and counted in `hidden` |

### features

| Method | Endpoint |
|---|---|
| `list(namespace=None, q=None, status=None, state=None)` | `GET /features` — `state` keeps features whose latest version is in one of the named states, e.g. `"draft,changes_requested"` |
| `page(...)`, `iter(...)` | `GET /features` with paging |
| `create(namespace, name, definition, **kw)` | `POST /features` — `description`, `tags` |
| `infer(data, fmt="csv", filename="upload")` | `POST /features/infer` |
| `quick(data, name, fmt="csv")` | `POST /features/quick` |
| `get(ref)` | `GET /features/{ns}/{name}` |
| `update_draft(ref, definition, **kw)` | `PUT /features/{ns}/{name}/draft` — `expected_version`, `description`, `tags` |
| `new_draft(ref)` | `POST /features/{ns}/{name}/drafts` |
| `clone(ref, name, namespace=None, extend=False)` | `POST /features/{ns}/{name}/clone` |
| `ingest(ref, data, fmt="csv", filename="upload", knowledge_time=None, note="")` | `POST /features/{ns}/{name}/ingest` |
| `pull(ref, knowledge_time=None)` | `POST /features/{ns}/{name}/pull` |
| `transition(ref, version_no, transition, **kw)` | `POST /features/{ns}/{name}/versions/{v}/transitions/{t}` — `rationale`, `force` |
| `compare(ref, v1, v2)` | `GET /features/{ns}/{name}/compare` |
| `draft_preview(ref, as_of_known=None)` | `POST /features/{ns}/{name}/draft-preview` |
| `pin(ref, version_no, pin_name, as_of, as_of_known=None, idempotency_key=None)` | `POST /features/{ns}/{name}/pins` |
| `pins(ref, page_size=100, cursor=None, sort=None, total=False)` | `GET /features/{ns}/{name}/pins` — a feature's pins a page at a time (`get` shows the latest 100 and `pins_total`) |
| `approve_pin(pin_id)` | `POST /pins/{pin_id}/approve` |
| `retire_pin(pin_id, reason)` | `POST /pins/{pin_id}/retire` |
| `preview(ref, as_of_known=None, start=None, end=None)` | `GET /feature-data/preview` |
| `download(ref, format="parquet", csv_encoding=None, as_of_known=None)` | `GET /feature-data` |

### featuresets

| Method | Endpoint |
|---|---|
| `list(namespace=None, q=None, state=None)` | `GET /featuresets` — `state` as for features |
| `page(...)`, `iter(...)` | `GET /featuresets` with paging |
| `create(namespace, name, definition, **kw)` | `POST /featuresets` |
| `get(ref)` | `GET /featuresets/{ns}/{name}` |
| `update_draft(ref, definition, **kw)` | `PUT /featuresets/{ns}/{name}/draft` |
| `new_draft(ref)` | `POST /featuresets/{ns}/{name}/drafts` |
| `transition(ref, version_no, transition, **kw)` | `POST /featuresets/{ns}/{name}/versions/{v}/transitions/{t}` |
| `draft_preview(ref)` | `POST /featuresets/{ns}/{name}/draft-preview` |
| `pin(ref, version_no, pin_name, as_of, cascade=False, as_of_known=None, idempotency_key=None)` | `POST /featuresets/{ns}/{name}/pins` |
| `preview(ref, as_of_known=None)` | `GET /featureset-data/preview` |
| `download(ref, format="parquet", shape="tabular", csv_encoding=None)` | `GET /featureset-data` |

### models

| Method | Endpoint |
|---|---|
| `list(namespace=None, q=None)` | `GET /models` |
| `page(...)`, `iter(...)` | `GET /models` with paging |
| `create(namespace, name, **kw)` | `POST /models` — `kind`, `description`, `formula`, `roles`, `ir`, `python_source`, `vendor` |
| `get(ref)` | `GET /models/{ns}/{name}` |
| `update_draft(ref, **kw)` | `PUT /models/{ns}/{name}/draft` — `formula`, `roles`, `ir`, `python_source`, `spec_latex`, `maturity`, `expected_version` |
| `new_draft(ref)` | `POST /models/{ns}/{name}/drafts` |
| `upload_artifact(ref, source, sample=None, params=None)` | `POST /models/{ns}/{name}/artifact` |
| `lift_workbook(data, output=None, roles=None, filename="workbook.xlsx")` | `POST /models/workbook/lift` |
| `import_workbook(ref, data, output=None, roles=None, filename="workbook.xlsx")` | `POST /models/{ns}/{name}/workbook` |
| `workbook(ref, version_no)` | `GET /models/{ns}/{name}/versions/{v}/workbook.xlsx` |
| `render_spec(ref, version_no)` | `POST /models/{ns}/{name}/versions/{v}/render` |
| `spec_pdf(ref, version_no)` | `GET /models/{ns}/{name}/versions/{v}/spec.pdf` |
| `transition(ref, version_no, transition, **kw)` | `POST /models/{ns}/{name}/versions/{v}/transitions/{t}` — `rationale`, `force`, `successor` |
| `diff(ref, v1, v2)` | `GET /models/{ns}/{name}/diff` |
| `reference_code(ref, version_no)` | `GET /models/{ns}/{name}/versions/{v}/reference` |
| `conformance(ref, version_no, n=500)` | `POST /models/{ns}/{name}/versions/{v}/conformance` |

### training

Training warrants and their parameter sets. The warrants reference covers each field.

| Method | Endpoint |
|---|---|
| `list()` | `GET /warrants/training` |
| `page(q=None, ...)`, `iter(...)` | `GET /warrants/training` with paging |
| `create(namespace, name, model, featureset, spec=None)` | `POST /warrants/training` |
| `get(warrant_id)` | `GET /warrants/training/{id}` |
| `data(warrant_id)` | `GET /warrants/training/{id}/data` |
| `upload_parameters(warrant_id, values, **kw)` | `POST /warrants/training/{id}/parameters` — `metrics`, `data_checksum`, `name`, `notes`, `member_alias` |
| `transition(warrant_id, transition, **kw)` | `POST /warrants/training/{id}/transitions/{t}` |
| `seal(warrant_id)` | `POST /warrants/training/{id}/seal` |
| `revoke(warrant_id, reason)` | `POST /warrants/training/{id}/revoke` |
| `clone(warrant_id, **changes)` | `POST /warrants/training/{id}/clone` |
| `score_holdout(warrant_id, parameter_set_id=None, values=None)` | `POST /warrants/training/{id}/score` |
| `export_bundle(warrant_id)` | `POST /warrants/training/{id}/bundle` |
| `parameter_transition(parameter_set_id, transition, **kw)` | `POST /parameters/{id}/transitions/{t}` — `rationale`, `force`, `justification` |
| `verify_bundle(data)` | `POST /bundles/verify` |

### execution

| Method | Endpoint |
|---|---|
| `list()` | `GET /warrants/execution` |
| `page(q=None, ...)`, `iter(...)` | `GET /warrants/execution` with paging |
| `create(namespace, name, **kw)` | `POST /warrants/execution` — `training_warrant_id`, `model`, `parameter_set_id`, `spec` |
| `get(ew_id)` | `GET /warrants/execution/{id}` |
| `transition(ew_id, transition, **kw)` | `POST /warrants/execution/{id}/transitions/{t}` |
| `seal(ew_id)` | `POST /warrants/execution/{id}/seal` |
| `token(ew_id, environment)` | `POST /warrants/execution/{id}/token` |
| `bundle(ew_id, environment)` | `GET /warrants/execution/{id}/bundle` |
| `report(ew_id, environment, rows, input_stats=None, output_stats=None)` | `POST /warrants/execution/{id}/report` |
| `reinstate(ew_id, reason)` | `POST /warrants/execution/{id}/reinstate` |
| `revoke(ew_id, reason)` | `POST /warrants/execution/{id}/revoke` |

### workflow

| Method | Endpoint |
|---|---|
| `queue()` | `GET /workflow/queue` |
| `aging()` | `GET /workflow/aging` |
| `break_glass(days=31)` | `GET /workflow/break-glass` |
| `policies()` | `GET /workflow/policies` |
| `policy(policy_id)` | `GET /workflow/policies/{id}` |
| `policy_yaml(policy_id)` | `GET /workflow/policies/{id}/yaml` |
| `draft_policy(object_type, policy, scope="*", note="")` | `POST /workflow/policies` |
| `import_policy(object_type, yaml, scope="*")` | `POST /workflow/policies/import` |
| `validate_policy(object_type, policy)` | `POST /workflow/policies/validate` |
| `activate_policy(policy_id)` | `POST /workflow/policies/{id}/activate` |
| `population(object_type)` | `GET /workflow/population/{object_type}` |
| `history(object_type, object_id)` | `GET /workflow/history` |
| `comments(object_type, object_id)` | `GET /workflow/comments` |
| `comment(object_type, object_id, body, blocking=False, anchor=None)` | `POST /workflow/comments` |
| `resolve_comment(comment_id)` | `POST /workflow/comments/{id}/resolve` |
| `transition(object_type, object_id, transition, rationale=None, force=False)` | `POST /workflow/transitions` |
| `delegations()` | `GET /workflow/delegations` |
| `delegate(to, starts_on, ends_on, object_types=None, reason="")` | `POST /workflow/delegations` |
| `revoke_delegation(delegation_id)` | `DELETE /workflow/delegations/{id}` |
| `campaigns()` | `GET /workflow/campaigns` |
| `run_campaign(name, transition, items, rationale="")` | `POST /workflow/campaigns` |

### workspaces

| Method | Endpoint |
|---|---|
| `list()` | `GET /workspaces` |
| `create(name, description="")` | `POST /workspaces` |
| `get(ws_id)` | `GET /workspaces/{id}` |
| `stage(ws_id, kind, ref, definition, note="")` | `PUT /workspaces/{id}/changes` |
| `unstage(ws_id, change_id)` | `DELETE /workspaces/{id}/changes/{change_id}` |
| `preview(ws_id, ref)` | `GET /workspaces/{id}/preview` |
| `impact(ws_id)` | `GET /workspaces/{id}/impact` |
| `shadow_replay(ws_id)` | `POST /workspaces/{id}/replay` |
| `submit(ws_id)` | `POST /workspaces/{id}/submit` |
| `abandon(ws_id)` | `POST /workspaces/{id}/abandon` |

### events

| Method | Endpoint |
|---|---|
| `list(after=0, limit=500, type=None)` | `GET /events` — `type` is a prefix: `"pin."` gives every pin event |
| `page(type=None, ...)`, `iter(...)` | `GET /events` with paging |
| `stream(after=0)` | `GET /events/stream` |
| `webhooks()` | `GET /webhooks` |
| `create_webhook(name, url, event_types=None, description="")` | `POST /webhooks` |
| `delete_webhook(webhook_id)` | `DELETE /webhooks/{id}` |
| `deliveries(webhook_id)` | `GET /webhooks/{id}/deliveries` |
| `ping(webhook_id)` | `POST /webhooks/{id}/ping` |

### assistant, custody and jobs

| Method | Endpoint |
|---|---|
| `assistant.memos(object_type, object_id)` | `GET /assistant/memos` |
| `assistant.request(object_type, object_id)` | `POST /assistant/memos` |
| `assistant.respond(memo_id, stance, note="")` | `POST /assistant/memos/{id}/stance` |
| `custody.anchors()` | `GET /custody/anchors` |
| `custody.anchor()` | `POST /custody/anchor` |
| `custody.verify()` | `GET /custody/verify` |
| `custody.licence(kind, ref)` | `GET /licences` |
| `jobs.list(all=False)` | `GET /jobs` |
| `jobs.page(all=False, q=None, ...)`, `jobs.iter(...)` | `GET /jobs` with paging |
| `jobs.get(job_id)` | `GET /jobs/{id}` |
| `jobs.cancel(job_id)` | `POST /jobs/{id}/cancel` |
| `jobs.retry(job_id)` | `POST /jobs/{id}/retry` |
| `jobs.events(job_id)` | `GET /jobs/{id}/events` |

## The command line

The CLI wraps the SDK for scripting and CI. Run it as `python -m maya.cli`; an installed package also provides the `maya` command. Global options go **before** the command group.

```bash
# The shape of every command
python -m maya.cli [--json] [--profile NAME] [--local] [--config PATH] <group> <command> [args]
```

| Option | Meaning |
|---|---|
| `--json` | Machine-readable output instead of the human summary. |
| `--profile NAME` | Connect with a profile from `~/.maya/config.toml`. Without it the CLI calls `connect()`: `MAYA_URL` and `MAYA_API_KEY`. |
| `--local` | Start an in-process platform from the configuration file instead of calling a server. Signs in as `MAYA_USER` (default `admin`) with `MAYA_PASSWORD`, which is required. |
| `--config PATH` | The configuration file for `--local` and for the `admin` database commands (default `config/application.yaml`). |
| `--section.key=value` | Overrides one setting for `--local` and the `admin` database commands, exactly as it does for `run_maya_web.py`; for example `--db.dialect=postgresql`. It may go anywhere on the line. Any other unrecognised flag is a usage error. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Refused by MAYA (any `MayaError`), or a check that failed: integrity drift, a failed bundle verification, a workbook whose check disagreed. |
| `2` | Usage error (argument parsing). |
| `3` | Network failure. |

### admin

These commands open the database directly, beside the server rather than through it.

| Command | What it does |
|---|---|
| `admin init-db [--force]` | Creates the schema for the configured dialect from its schema file. Refuses (exit 1) when a MAYA schema exists, unless `--force`, which drops and recreates it. |
| `admin export-estate --out FILE` | Writes every table to an estate file. Opens the database with the running code, so its schema must match. |
| `admin import-estate --in FILE [--allow-drop]` | Loads an estate into an empty database (creating the schema when there is none). Every table's hash, the audit chain and every column are checked before anything is written; `--allow-drop` accepts columns this version no longer has, and names them. |
| `admin verify-integrity` | Through the API: re-hashes every sealed pin and walks the audit chain. Exits 1 on any drift or a broken chain. |

### feature

| Command | What it does |
|---|---|
| `feature list [--namespace NS] [-q TEXT]` | Lists features. |
| `feature show REF` | Prints a feature as JSON. |
| `feature quick FILE [--name NAME]` | An ungoverned scratch feature from a CSV, Parquet or JSON file; the name defaults to the file's stem. |
| `feature upload REF FILE [--knowledge-time ISO]` | Ingests a file into a feature; the format comes from the extension. |
| `feature pin REF --version N --name PIN --as-of DATE [--as-of-known ISO]` | Pins a version, waiting for the pin job and printing progress; when your role can only request a pin, says it awaits approval. |
| `feature download REF --out FILE [--format parquet] [--csv-encoding ENC]` | Downloads data. |
| `feature diff REF V1 V2` | Compares two versions. |

### featureset

| Command | What it does |
|---|---|
| `featureset pin REF --version N --name PIN --as-of DATE [--cascade]` | Pins a feature set version and waits for the job. |
| `featureset download REF --out FILE [--format parquet] [--shape tabular] [--csv-encoding ENC]` | Downloads data. |

### model

| Command | What it does |
|---|---|
| `model push REF FILE` | Uploads a Python artifact to the model's draft. |
| `model import-workbook REF FILE [--output CELL] [--role NAME=ROLE]... [--preview]` | Lifts an Excel workbook into the draft; `--preview` only shows the lift. A `--role` with no role means `feature`. Exits 1 when the workbook check disagreed. |
| `model diff REF V1 V2` | The statements that changed between two versions. |

### warrant, job and export

| Command | What it does |
|---|---|
| `warrant fetch ID --out FILE` | Downloads a training warrant's data, verifies the checksum and writes Parquet. |
| `warrant upload-params ID FILE` | Uploads parameters from a JSON file with `values` and optional `metrics`, `data_checksum`, `notes`. |
| `warrant seal ID` | Seals a training warrant. |
| `job watch ID` | Follows a job to its end, printing progress. |
| `job cancel ID` | Cancels a job. |
| `export bundle ID --out FILE` | Exports a training warrant's reproducibility bundle and saves it. |
| `export verify FILE` | Verifies a bundle offline by running the bundle's own `verify.py` in a clean interpreter on this machine. Exits 1 unless verified. |

!!! warning "export verify runs the bundle's code"
    `export verify` executes the `verify.py` inside the file, exactly as `python verify.py` would. Run it only on bundles you chose to trust. To inspect a bundle without running anything it carries, open it with `maya.sdk.offline()`.

```bash
# A nightly pin in CI
export MAYA_URL=https://maya.example.com MAYA_API_KEY=maya_prod_…
python -m maya.cli --json feature pin eq/prices --version 3 --name eod --as-of 2026-09-18
python -m maya.cli admin verify-integrity || exit 1
```
