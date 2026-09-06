---
title: The API, refusals and configuration
slug: api-reference
section: Reference
order: 140
icon: code-slash
summary: The five request shapes the API actually uses, why a model name is a query parameter and not a path segment, every endpoint grouped by what it is for, what each HTTP status class tells you about who must act next, the refusals you are most likely to hit — and how the platform is configured.
audience: Engineers, Operators, Model owners
---

# The API, refusals and configuration

The interface is a client, not a privileged path: everything a page does is
available here. Interactive documentation is at **[`/docs`](/docs)** — the
generated Swagger UI, where every endpoint below can be called against this
instance — with [ReDoc](/redoc) as a reading view of the same specification, and
the OpenAPI document itself at `/api/v1/openapi.json`.

Three things are worth knowing before the endpoint tables, because they are
where a first client goes wrong.

**Not everything is under `/api/v1`.** The API is; the HTML pages, sign-in and
the health probes are not.

| Bare root | |
|---|---|
| `/`, `/about`, `/help`, `/help/{slug}`, `/tutorials`, `/tutorials/{slug}` | anonymous |
| `/health`, `/health/live`, `/health/ready` | anonymous |
| `/login` (`GET`, `POST`), `/logout`, `/auth/login`, `/auth/callback` | they establish a session |
| `/dashboard`, `/model/{name}`, `/dossier/{name}`, `/board-pack`, … | HTML pages; a signed-out request is redirected to `/login`, not refused with JSON |

Everything else in this document is literally prefixed `/api/v1`. There is no
configurable base path.

**A model name is a query parameter, not a path segment**, on every collection
endpoint. A URN carries dots and slashes, so the path converter that matches it
is greedy and would swallow any segment after it. So it is
`GET /api/v1/findings?urn=…`, never `/api/v1/models/{name}/findings`. Where a
name *is* in the path it is the last thing there, and the URN is assembled
server-side:

```bash
GET /api/v1/models/credit.pd.smallbiz            # → maya://model/credit.pd.smallbiz
GET /api/v1/dossiers/credit.pd.smallbiz
GET /api/v1/findings?urn=maya://model/credit.pd.smallbiz
```

The same reasoning explains two paths that look inside out. `/telemetry/{semver}/{name}`
and `/parameters/{semver}/{name}` put the version *before* the model, because a
greedy name segment placed first would eat the semver.

**Not every endpoint takes JSON.** Five request shapes are in use, and guessing
wrong produces a 422 from the framework rather than a MAYA refusal:

| Shape | Where |
|---|---|
| **JSON body** | most `POST`/`PUT`/`PATCH` |
| **Query parameters only, no body** | `POST /documents` (`urn`, `kind`), `POST /baseline/reconcile` (`urn`), `POST /overlays/{id}/approve` and `/renew`, `POST /monitors/{id}/status`, `POST /features/{name}/certify`, `POST /export-packs/{name}`, `POST /resolve` (`verb`, alongside its body), `DELETE /models/{name}` (`reason`) |
| **Raw bytes** | `POST /artifacts` (with `format` and `digest` as query parameters), `POST /feature-views/{name}/data` |
| **`multipart/form-data`** | `POST /attachments` |
| **Form-encoded** | `POST /login` |

Four endpoints take a free-form JSON object rather than a declared model, which
means a missing key is a fault rather than a validation error:
`/blast-radius`, `/shared-dependencies`, `/grammar/validate`, `/sso/preview`.

## The refusal shape

A refusal that does not tell you how to proceed is a support ticket. So a
governance refusal carries three fields at the top level: a machine-readable
`error` code, a human `detail` naming the specific thing that failed, and a
`remediation` saying what to do about it.

```json
{
  "error": "no_entitlement",
  "detail": "svc/pricing holds no warrant for maya://model/x in prod",
  "remediation": "request a warrant grant for this principal and approved use"
}
```

Two exceptions to know before you write a client:

- A plain **not-found** carries `error` and `detail` only. There is no useful
  remediation for a name that does not exist.
- **Request validation** — a malformed body, a missing required field, a wrong
  type — is rejected by the web framework before any MAYA code runs and comes
  back in the framework's own shape, with a `detail` list and **no `error`
  key**. If your client keys on `error`, handle 422 without one.

### The status class says who must act

There are over three hundred codes, all mapped in one table so no code
can mean two things. Branch on the class first; it tells you whose problem this
is.

| Class | Means | Who acts |
|---|---|---|
| **401 / 403** | you are not, or may not | you, or whoever grants |
| **404** | the name does not exist | you |
| **409** | a governance rule was not satisfied | somebody in the process |
| **410** | the credential is gone — `revoked`, `expired` | re-resolve |
| **413** | well-formed and too large | narrow the request |
| **422** | the request is coherent but the content is not admissible | you |
| **423** | the model is locked — `blocked`, `restricted` | close the finding, or approve for that environment |
| **50x** | the platform or a dependency, not you | an operator |

The codes a caller most often has to branch on:

| Code | HTTP | Meaning |
|---|---|---|
| `not_found` | 404 | No such model, version, warrant or validation |
| `unauthenticated` | 401 | No credentials, or they did not verify |
| `forbidden` | 403 | The principal's roles do not carry this permission |
| `out_of_scope` | 403 | The permission is held, but not over this model |
| `segregation_of_duties` | 403 | The evidence chain says this person already acted incompatibly |
| `no_entitlement` | 403 | This principal holds no warrant grant |
| `use_not_approved` | 403 | Declared use is not the approved use |
| `signature_invalid` | 403 | Warrant signature does not verify |
| `policy_refused` | 403 | A published policy gate said no |
| `registry_refused` | 409 | A registry rule was not satisfied |
| `feature_refused` | 409 | A feature or featureset rule was not satisfied |
| `validation_refused` | 409 | A validation rule was not satisfied |
| `illegal_transition` | 409 | The lifecycle does not allow that move |
| `record_frozen` | 409 | The record is not in a mutable state |
| `quorum_required` | 409 | This tier needs two signatures; open a version approval |
| `cohort_immature` | 409 | No outcomes have matured yet |
| `revoked` / `expired` | 410 | The warrant is no longer current |
| `restricted` | 423 | Version is not approved for this environment |
| `blocked` | 423 | An open blocking finding stands against this model |
| `validation_failed` | 422 | Malformed request — bad URN, misaligned series |
| `assembly_rejected` | 422 | A training set assembly was not point-in-time safe |
| `boundary_violation` | 422 | Inputs outside the contract's assumptions |
| `grammar_violation` | 422 | The warrant does not conform to the grammar |
| `no_fibre` | 422 | The trainability class has no fibre, so nothing says what evidence it needs or what may be monitored on it. Not a 404: the class is a real value and the caller named it correctly — what is missing is something the platform should have supplied |
| `kind_not_answerable` | 422 | The monitor asks a question this class cannot answer — a `performance` monitor on a T0 pricer, a `calibration` monitor on a T5 generative assembly. Both used to be accepted, and both then ran forever without meaning anything, which reads on the estate screen as coverage |
| `fibration_incomplete` | 503 | The one refusal here you should never see. The totality gate runs at start-up, so if this reaches you the instance is serving on a fibration it already knows is partial, and the honest answer is that it is not fit to answer |
| `test_not_admissible` | 422 | This test cannot answer this monitor's question |
| `unknown_subject` | 422 | A document was filed against something that is not a subject |
| `unknown_metric` | 422 | A limit named something the platform does not compute |
| `amber_beyond_limit` | 422 | A warning that could only fire after the thing it warns about |
| `rationale_required` | 422 | A limit or an overlay with no stated reason |
| `unknown_format` | 422 | Not an artifact format this platform stores |
| `artifact_digest_mismatch` | 409 | The bytes do not hash to the digest you declared |
| `artifact_not_stored` | 404 | Nothing is held under that address |
| `artifact_too_large` | 413 | Over the 8 GiB ceiling |
| `pack_too_large` | 413 | An export pack over 2 GiB; ask for fewer documents |
| `unknown_profile_fact` | 422 | A profile tried to select on something the platform does not derive |
| `not_defaultable` | 422 | A profile tried to fill in something a caller could not have typed |
| `authority_not_defaultable` | **403** | A profile reached for authority. 403 rather than 422 on purpose: it is not a malformed request, it is a profile trying to be a different kind of object |
| `no_runtime` | 501 | No execution runtime is configured for that warrant |

**Segregation refusals are a family**, and each names the act it is protecting:
`self_review` on a document, `self_approval` on a parameter set or an overlay,
`self_renewal` on an overlay, `self_attestation` on a machine generation,
`self_extension` on a finding's remediation date, `verifier_not_self` on a
finding closure, `principal_not_self` on resolving somebody else's warrant.
`segregation_of_duties` is the computed one, read from the evidence chain rather
than from a rule about the request.

## Authenticating, and the one case that needs a token

Two ways in, against the same principal register.

**HTTP Basic**, for services, scripts and engines. Nothing else is required — a
caller who can set an `Authorization` header already holds the credential, so
the authority is not *ambient* and there is nothing for a token to add.

```bash
curl -u svc/model-lab:svc-pw localhost:5006/api/v1/models
```

**A session cookie**, for the browser. This one *is* ambient — the browser sends
it whether or not the page that triggered the request came from us — so a
state-changing request under a cookie must also carry the session's CSRF token:

```
X-MAYA-CSRF: <the value of the page's csrf-token meta tag>
```

That matters because there are **a hundred and fourteen mutating endpoints**; the
argument for a token rests on the number being large. The pages do it for you
(`web/static/js/csrf.js` attaches it to every same-origin mutation), so this
concerns you only if you are scripting against a signed-in session. If you are,
use Basic instead.

| | Token required |
|---|---|
| `POST`/`PUT`/`PATCH`/`DELETE` under a session cookie | **yes** |
| Anything under HTTP Basic | no |
| `GET`/`HEAD`/`OPTIONS` | no |
| `/login`, `/auth/login`, `/auth/callback` | no — they establish the session |

```json
{"error": "csrf_token_invalid",
 "detail": "this request changes something and was authenticated by a session
            cookie, but carries no valid CSRF token",
 "remediation": "send the token from the page's 'x-maya-csrf' meta tag in that
                 header, or authenticate with HTTP Basic, which carries no
                 ambient authority and needs no token"}
```

**Single sign-on**, where an issuer is configured. `GET /api/v1/sso` is the one
endpoint that answers rather than refusing when SSO is switched off — it tells
you it is off and why. Group claims are **mapped, never obeyed**: `POST
/api/v1/sso/preview` shows which roles a given claim set would produce without
signing anybody in.

## Or use the SDK

Everything below is one call in `maya_sdk`, and the SDK is the shorter path on
purpose — if doing it properly took forty lines of HTTP plumbing and doing it
wrong took four, the register would fill with models nobody registered properly.

```bash
pip install -e sdk/python
```

```python
from maya_sdk import Maya, Blocked

maya = Maya("https://maya.internal", "d.raman", "…")
maya.models.register(urn="maya://model/credit.pd.smallbiz", name="SB PD", …)

try:
    maya.versions.promote("maya://model/credit.pd.smallbiz", semver="3.3.0")
except Blocked as refusal:
    print(refusal.detail, refusal.remediation, refusal.request_id)
```

Standard library only, no dependencies. It authenticates with HTTP Basic, so the
CSRF boundary does not apply to it. **It decides nothing** — no local tier
arithmetic, no client-side approval check, no copy of the vocabularies; ask
`maya.warrants.grammar()` and `maya.whoami()` instead, so a client cannot go
stale and be confidently wrong. See `sdk/README.md`.

## Paging, search and sorting

Every list endpoint takes `limit`, `offset` and — where it makes sense — `q`.
The response carries `total`, `returned`, `limit`, `offset` and `has_more`
alongside the rows, so a client always knows what it did not receive.

| Parameter | Default | Notes |
|---|---|---|
| `limit` | 50 | Capped at 500. Asking for more returns the cap and says so in `limit`, rather than truncating quietly — silently truncating is how a client concludes there are 200 models when there are 12,000 |
| `offset` | 0 | Ordinary offsets rather than cursors: a governance register is read by people who want page four |
| `q` | — | Case-insensitive substring across the fields a reader would search by |

**Scope filtering runs before the page is cut.** Page two of a filtered list is
never page two of the unfiltered one with holes in it — otherwise a model out of
scope becomes discoverable by a count that does not add up.

In the interface, every table is searchable and sortable, and pages once it is
long enough for a pager to be worth the space. That is served from
`/static/js/tables.js` — written rather than vendored, because this platform has
to run air-gapped and a table plugin is a hundred lines of arithmetic wearing
eighty kilobytes.

## The endpoints

Every path below is relative to `/api/v1`. The permission column is what
`authorise` demands; *auth* means any authenticated principal.

### Models, versions and aliases

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/models` | `model:read` | Inventory; `domain`, `tier`, `q`, `limit`, `offset`. Scope-filtered first |
| `POST` | `/models` | `model:register` | `urn, name, model_class, domain, owner, legal_entity, purpose` + `description`, `origin` |
| `GET` | `/models/{name}` | `model:read` | Model with versions, aliases, lifecycle, evidence |
| `POST` | `/models/{name}/versions` | `version:create` | `semver` + `kernel`, `contract`, `artifact_digest`, `artifact_uri` |
| `POST` | `/models/{name}/versions/{semver}/approve` | `version:approve` | Draft → approved. Refuses `quorum_required` where the tier needs two |
| `PUT` | `/models/{name}/aliases` | `alias:move` | `semver` + `environment`, `alias`, `justification`. Gated on approval, findings, L-7 and L-12 |
| `POST` | `/models/{name}/assess` | `risk:assess` | Risk tier with its full derivation and ruleset version |

### The dependency graph

An `input_to` edge asserts that what one model produces arrives where another
reads it, and it is **type-checked** before it is recorded rather than drawn.

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/model-relations` | auth | The relation vocabulary: which kinds propagate, which are commentary |
| `POST` | `/model-relations` | `model:amend` | `from_urn, to_urn, kind` + `note`. Refused if the ends do not compose |
| `POST` | `/model-relations/remove` | `model:amend` | `from_urn, to_urn, kind, reason`. A `POST` because it carries a body |
| `GET` | `/models/{name}/relations` | `model:read` | Edges in both directions |
| `POST` | `/blast-radius` | `model:read` | `{"urn": …}` — what breaks downstream, following only propagating edges |
| `POST` | `/shared-dependencies` | `model:read` | `{"urns": [...]}` — what two or more of these rest on in common |

`feeds` is accepted on the way in and stored as `input_to`; it is deliberately
not published in the vocabulary, because two words for one relation invite
somebody to think they mean different things.

### Version approval by quorum

A Tier 1 or Tier 2 version is approved by two people in two named roles, so
`POST /models/{name}/versions/{semver}/approve` refuses with `quorum_required`
and these are what to use instead.

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/version-approval-quorum` | auth | Which roles each tier requires |
| `GET` | `/version-approvals?urn=&semver=` | `model:read` | Open approvals for a version |
| `POST` | `/version-approvals` | `version:approve` | `urn, semver` + `statement` |
| `GET` | `/version-approvals/{id}` | `model:read` | Signatures so far, and what is outstanding |
| `POST` | `/version-approvals/{id}/sign` | `version:sign` | `role` + `decision`, `statement`. One decline closes it; the same person may not sign under two hats |
| `POST` | `/version-approvals/{id}/withdraw` | `version:approve` | End it without approving |

### The record lifecycle

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/lifecycle` | auth | The states and the legal transitions |
| `PATCH` | `/models/{name}` | `model:register` | `fields`. Refused on a frozen record |
| `POST` | `/models/{name}/submit` | `model:submit` | `note` |
| `POST` | `/models/{name}/approve` | `model:approve` | `note`. Approves and **opens the attestation** |
| `POST` | `/models/{name}/return` | `model:approve` | `reason` |
| `POST` | `/models/{name}/attest` | `model:attest` | `role` + `decision`, `statement`. One role's half of the quorum |
| `POST` | `/models/{name}/amend` | `model:amend` | `reason` + `scope`. The only route out of immutability |
| `POST` | `/models/{name}/retire` | `model:retire` | `reason`. Withdraw from use, keep everything |
| `DELETE` | `/models/{name}?reason=` | `model:delete` | Administrators only. The evidence chain survives |

### Serialised model artifacts

The bytes of a model that is a file rather than a record — a network's weights, a
prompt bundle, a quantised checkpoint. Stored under their own SHA-256, so an
artifact cannot be edited in place and storing the same one twice stores it once.

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/artifact-formats` | auth | What may be stored, and which formats execute code when they load |
| `POST` | `/artifacts?format=&digest=` | `version:create` | The body is the raw file. `digest` is **checked**, not trusted |
| `GET` | `/artifacts/{digest}` | `model:read` | The bytes back, streamed |
| `GET` | `/artifacts/{digest}/verify` | `evidence:read` | Re-derive the hash from the bytes on disk. Separate, because re-hashing gigabytes on every read would be absurd |
| `GET` | `/artifact-usage` | `evidence:read` | How many artifacts, and how many bytes |

A version naming a digest the store holds gets its `artifact_uri` and
`artifact_size` **from the store** — the store is the authority on its own
contents. A digest it does not hold is recorded as naming an artifact somebody
else holds, which is a different state rather than an error, and the warrant
carries the difference as `held_by_maya`. Ceiling 8 GiB: a governance platform
is not a model store of last resort.

### Warrants, execution and the grammar

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/grammar`, `/grammar/schema` | auth | The four vocabularies; the generated JSON Schema |
| `POST` | `/grammar/validate` | auth | Check a document before you sign anything. Reports **every** problem, not the first |
| `GET` | `/fibres`, `/fibres/{trainability_class}` | auth | The fibration (`L-15`): for each of the nine trainability classes, the evidence it needs, the lifecycle it may occupy, the monitor kinds that can answer anything about it, and the documents that compile for it — plus, in prose, what conceptual soundness rests on, what outcomes analysis *is*, and what monitoring answers. A class with no fibre is refused `no_fibre` (422) rather than returned empty, because an empty fibre is what the law forbids |
| `POST` | `/warrants` | `warrant:issue` | Issue a standing entitlement: `urn, principal, declared_use` + `environment`, `flavour` |
| `POST` | `/resolve?verb=` | `warrant:resolve` | Mint a signed, expiring warrant. The hot path. Resolving for another principal needs `warrant:issue` |
| `POST` | `/fit-warrants` | `warrant:issue` | A warrant to *fit*: `urn, principal, featureset, featureset_version, window, as_of`. Enforces L-W10 |
| `POST` | `/warrants/revoke` | `warrant:revoke` | `urn, reason`. Kill switch for every grant on a model; returns the new epoch |
| `GET` | `/engine` | auth | Whether a captive engine exists here, and its isolation |
| `POST` | `/execute` | `warrant:execute` | Captive engine — one consumer of the same public contract. 404 with a remediation where no engine is configured |

### Warrant profiles

Request defaults, selected by facts the platform derives. A profile fills holes
in a warrant request; it never overrides a caller and never widens authority.

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/warrant-profile-vocabulary` | auth | What a profile may select on, what it may fill in, and what is never defaultable |
| `GET` | `/warrant-profiles` | auth | The live profiles, least specific first — the order they fold |
| `POST` | `/warrant-profiles` | `warrant:issue` | `name` + `when`, `defaults`, `note`. Immutable; a second `POST` under the same name is version 2 |
| `POST` | `/warrant-profiles/{name}/retire` | `warrant:issue` | Stop it applying. Warrants it already shaped stand |
| `POST` | `/warrant-profiles/preview` | auth | `urn` + `semver`, `environment`, `request`. Returns the fold **and the facts it read** |

### Features and feature views

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` `POST` | `/features` | `feature:read` / `feature:define` | List by `entity`; define. Creating returns `possible_duplicates` |
| `GET` | `/features/{name}/resolved` | `feature:read` | The row, its parents, its operations, shape, retrieval policy and remaining TTL |
| `POST` | `/features/{name}/certify?level=` | `feature:certify` | experimental → certified → deprecated |
| `POST` | `/features/{name}/amend` | `feature:define` | `fields` |
| `POST` | `/features/{name}/seal` | `feature:seal` | `note`. Still composable from — that is why it is a seal |
| `POST` | `/features/{name}/break-seal` | **`principal:manage`** | `reason`. Deliberately an administrator's act, not a feature owner's |
| `POST` | `/features/{name}/transfer` | `feature:define` | `to` + `reason`. The creator does not move |
| `DELETE` | `/features/{name}` | `feature:define` | Ephemeral features only |
| `GET` `POST` | `/feature-views` | `feature:read` / `feature:define` | List, create |
| `POST` | `/feature-views/{name}/materialise` | `feature:materialise` | `rows`. Writes bitemporal rows; creates a new version namespace |
| `GET` | `/feature-views/{name}/versions` | `feature:read` | Materialised versions |
| `GET` | `/feature-views/{name}/versions/{v}/retirable` | `feature:read` | Who still pins it |
| `POST` | `/feature-contracts` | `feature:contract` | `model_version_id, items`. Pin a model version to exact view versions |
| `GET` | `/feature-contracts/{version_id}/namespaces` | `feature:read` | What serving must read (L-17) |
| `POST` | `/training-sets` | `feature:assemble` | `name, spine, views, as_of`. Refused if either temporal bound is off |

### Derived features and the expression language

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/expression-language` | auth | What a derived feature may say. Deliberately small |
| `GET` | `/retrieval` | auth | Preparation, alignment, policy, composition |
| `GET` `POST` | `/derived-features` | `feature:read` / `feature:define` | List; define with `name, expression` + `dtype`, `on_error`, … |
| `GET` | `/derived-features/{name}/lineage` | `feature:read` | `rests_on` (the base features) and `depended_on_by` — two different questions |

### Featuresets

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` `POST` | `/featuresets` | `feature:read` / `featureset:define` | List; declare a schema of typed slots |
| `POST` | `/featuresets/preview` | `featureset:define` | Refuses exactly what `define` refuses, and declares nothing |
| `GET` | `/featuresets/{name}` | `feature:read` | The set and its versions |
| `GET` | `/featuresets/{name}/resolved` | `feature:read` | The schema after composition |
| `POST` | `/featuresets/{name}/versions` | `featureset:publish` | `bindings` + `label`, `note`. Bind every slot to a feature and a pinned view version |
| `GET` | `/featuresets/{name}/versions/{v}` | `feature:read` | The full assembly plan |
| `GET` | `/featuresets/{name}/versions/{v}/restatements` | `feature:read` | Whether anything underneath the pin has been written to since |
| `POST` | `/featuresets/{name}/roll-forward` | `featureset:publish` | Re-resolve to current view versions, on purpose, and see what moved |
| `POST` | `/featuresets/{name}/training-sets` | `feature:assemble` | `version, spine, as_of`. A PIT-correct set from a pinned version |
| `POST` | `/featuresets/{name}/seal` | `featureset:seal` | `note` |
| `POST` | `/featuresets/{name}/transfer` | `featureset:define` | `to` + `reason` |
| `PUT` | `/featuresets/{name}/policy` | `featureset:define` | `defaults` — default retrieval behaviour; a request may still override |
| `DELETE` | `/featuresets/{name}` | `featureset:define` | Ephemeral sets only |

### Moving feature data

Streamed, so peak memory is one Arrow batch rather than the whole export.

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/transfer` | auth | Which formats are offered |
| `GET` | `/feature-views/{name}/versions/{v}/data` | `feature:read` | `format`, `columns`, `limit`. Reads **at the pin**. Columns are checked before the response starts |
| `GET` | `/featuresets/{name}/versions/{v}/data` | `feature:read` | `as_of`, `format`, `limit`. JSON is capped and says so; ask for arrow or parquet to take the whole thing |
| `POST` | `/featuresets/{name}/versions/{v}/prepared` | `feature:read` | `as_of`, `fill`, `normalise`, `align`, `limit`. Policy is the set's default overridden per column |
| `GET` | `/featuresets/{name}/versions/{v}/parts` | `feature:read` | Namespaces and their pins, for a client pulling in parallel |
| `POST` | `/feature-views/{name}/data` | `feature:materialise` | Raw Arrow, Parquet or NDJSON. The whole upload becomes one version |

### Parameters — inhabiting `P`

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/parameter-provenance` | auth | fitted, calibrated, declared |
| `GET` `POST` | `/parameters?urn=&semver=` | `model:read` / `parameter:record` | Read and record parameter sets. Deliberately **not** nested under `/models/{name}` — that converter is greedy |
| `POST` | `/parameter-fits` | `parameter:record` | **Run** the fit. Resolves the warrant before reading anything, reads the snapshot at its pinned Delta version, lands `proposed`. 501 where no captive engine is configured |
| `GET` | `/parameter-sets/{id}` | `model:read` | One set with its lineage |
| `POST` | `/parameter-sets/{id}/review` | `parameter:approve` | `accept` + `note`. Not by whoever recorded it |

### Rule sets — the T8 parameter object

Four verbs and one vocabulary, and the split between them is the whole design.
`check` and `trial` are **free**: they carry no authority, record nothing, and can
be called on every keystroke. `publish` is the ordinary `parameter:record` act
with the ordinary consequences — so an author iterates without touching the
register, and the moment their draft becomes a governed object is one act they
had to choose.

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/rulesets/vocabulary` | auth | The eleven operators, what each means, which need an ordered field, the combinators, and which dtypes have an order. Taken from the code, so a screen cannot hold a second copy that drifts |
| `POST` | `/rulesets/check` | `model:read` | `urn, semver, document`. Validates against the version's input and output schemas. Returns the rule count, the fields read, the shadowing and contradiction reports, the English rendering and the canonical document. **Records nothing** — and it is `model:read` rather than `parameter:record` deliberately, because requiring the recording permission to *look* at whether a document is valid pushes authors to skip the step |
| `POST` | `/rulesets/trial` | `model:read` | `urn, semver, document, rows`. Runs a draft against sample rows. Reports every outcome, per-rule fire counts, which rules fired on nothing, and how many rows fell through to `otherwise`. A row that cannot be decided is reported against that row rather than raised, so one bad sample does not hide what the other nineteen would have shown. Deliberately **not** `/execute`: there is no warrant and no entitlement, because nothing is being scored |
| `POST` | `/rulesets` | `parameter:record` | `urn, semver, name, document, note`. **201.** `POST /parameters` reached through a door that checks the document: the set lands `proposed`, carries the shadowing and contradiction reports as diagnostics, and needs somebody other than its author |
| `GET` | `/rulesets/{parameter_set_id}` | `model:read` | An approved rule set in English. One rendering, so the model card, the committee paper and the export pack quote the same sentences |

Executing one is the ordinary `POST /execute` against a warrant whose runtime is
`rules` and whose verb is `score`. See [Rule sets](/help/rule-sets).

### Validation

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/tests` | `validation:read` | The registered test catalogue |
| `POST` | `/validations` | `validation:open` | `urn, semver, validators` + `kind`, `scope`, `plan`, `snapshot_id`, `due_at`. Refused if a validator built the version |
| `GET` | `/validations/{id}` | `validation:read` | Episode with results and summary |
| `POST` | `/validations/{id}/results` | `validation:record` | `test_key, left, right` + `threshold`, `parameters`, `slice` |
| `POST` | `/validations/{id}/conclude` | `validation:conclude` | `outcome` + `conditions`. Refused if a test failed or a finding blocks. Segregation is checked against the **version** |
| `POST` | `/validations/{id}/replay` | `validation:read` | `data` you supply. Compared on digest, so a moved threshold is caught |
| `POST` | `/validations/{id}/replay-from-storage` | `validation:read` | No body. Re-reads the pinned snapshot; nothing comes from the caller |
| `GET` | `/validations/{id}/replayable` | `validation:read` | Whether it can be replayed at all, before you spend anything on it |

### Findings

Ageing, acceptance and escalation are **derived from the acts**, so there is no
status column that can disagree with what happened.

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` `POST` | `/findings?urn=` | `finding:read` / `finding:raise` | List by model; raise with `urn, severity, title, owner` + `description`, `category`, `source`, `blocking` |
| `GET` | `/finding-acts` | auth | The four acts and what each one means |
| `GET` | `/findings/ageing?urn=` | `finding:read` | The distribution a committee asks for, not a mean. Estate-wide without `urn` |
| `GET` | `/findings/escalated?urn=` | `finding:read` | Overdue, unaccepted, or past the extension limit |
| `GET` | `/findings/{id}` | `finding:read` | The finding with its acts, ageing and escalation |
| `POST` | `/findings/{id}/assign` | `finding:assign` | `to, reason`. Authorship never moves; a handover withdraws the previous acceptance |
| `POST` | `/findings/{id}/acknowledge` | `finding:acknowledge` | `plan` + `days` or `committed_at`. Only the owner. Refused past the due date |
| `POST` | `/findings/{id}/plan` | `finding:plan` | `plan`. Re-planning appends |
| `POST` | `/findings/{id}/extend` | `finding:extend` | `reason` + `days` or `due_at`. Never by the owner, never by whoever acknowledged it, counted, capped by severity |
| `GET` | `/findings/{id}/escalation` | `finding:read` | Why this is no longer only its owner's problem |
| `POST` | `/findings/{id}/close` | `finding:close` | `evidence` required. Needs a verifier who is not the owner — and `verified_by` is never trusted from the body |

### Monitoring and telemetry

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/monitor-kinds` | auth | The kinds, the tests each admits, and which need labels |
| `GET` `POST` | `/monitors?urn=` | `monitor:read` / `monitor:define` | List; define with `urn, name, kind, test_key, threshold, owner` + `cadence_days`, `label_delay_days`, `breach_severity`, `escalate_after` |
| `POST` | `/monitors/{id}/evaluate` | `monitor:evaluate` | `rows` + `reference`, `now` |
| `POST` | `/monitors/{id}/evaluate-from-telemetry` | `monitor:evaluate` | `since, until, reference_from, reference_to`. Reads what the platform already holds |
| `GET` | `/monitors/{id}/observations` | `monitor:read` | What it has measured, and its breaches |
| `POST` | `/monitors/{id}/status?status=` | `monitor:define` | active / paused / retired |
| `GET` | `/telemetry-streams` | auth | `scores` and `outcomes`, and what each means |
| `POST` | `/telemetry` | **`monitor:observe`** | `urn, semver, rows` + `stream`, `sample_rate`, `source`. Idempotent on the batch digest |
| `GET` | `/telemetry?urn=&semver=` | `monitor:read` | What a version has sent, and how long it has been silent |
| `GET` | `/telemetry/cohort?urn=&semver=&since=&until=&known_by=` | `monitor:read` | Scores left-joined to outcomes. Unlabelled rows come back unlabelled, never dropped |

`monitor:observe` and `monitor:evaluate` are separate on purpose: the principal
that runs the model holds the rows and should be able to hand them over without
also being able to rule that a monitor has breached.

### Overlays

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/overlay-kinds` | auth | The four kinds |
| `GET` `POST` | `/overlays?urn=` | `overlay:read` / `overlay:propose` | Register with aggregate, persistence and trend; propose with `urn, name, kind, rationale, owner` + `direction`, `basis`, `days` |
| `GET` | `/overlays/{id}` | `overlay:read` | One overlay with its assessment |
| `POST` | `/overlays/{id}/approve?days=` | `overlay:approve` | Never by the proposer |
| `POST` | `/overlays/{id}/measure` | `overlay:measure` | `period, base_value, adjusted_value` |
| `POST` | `/overlays/{id}/renew?days=&period=` | `overlay:approve` | Never by the owner, and never without a measurement for that period |
| `POST` | `/overlays/{id}/close` | `overlay:approve` | `reason` + `status`: `withdrawn`, `absorbed` or `expired` |

### Documents, the graph and export packs

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/document-kinds` | auth | The four that may be compiled |
| `GET` | `/document-subjects` | auth | The six things a document may be *about*, and which are pinned |
| `GET` | `/documents?urn=` | `document:read` | With staleness on each |
| `POST` | `/documents?urn=&kind=` | `document:compile` | **Query parameters, no body** |
| `GET` | `/documents/{id}` | `document:read` | With citations verified and staleness |
| `GET` | `/documents/{id}/markdown` | `document:read` | Plain text — the exportable form |
| `GET` | `/dossiers/{name}` | `document:read` | The whole documentation graph, with its gaps named |
| `POST` | `/training-records/{parameter_set_id}` | `document:compile` | Compile the record of one fit |
| `GET` | `/training-records/{parameter_set_id}/preview` | `document:read` | What it would say, without authoring it |
| `GET` | `/attachment-kinds` | auth | The nine kinds that may be filed |
| `GET` | `/attachments?urn=&history=` | `document:read` | Current set, or everything including superseded and rejected |
| `POST` | `/attachments` | `document:attach` | **multipart**: `urn, kind, title, file` + `semver`, `note`, `supersedes`, `model_level`, `subject_type`, `subject_id` |
| `GET` | `/attachments/{id}`, `/attachments/{id}/content` | `document:read` | The row; the bytes, re-hashed on the way out |
| `POST` | `/attachments/{id}/review` | `document:review` | `accept` + `note`. Not by whoever filed it |
| `GET` | `/export-packs` | auth | What a pack contains, and what each part answers |
| `POST` | `/export-packs/{name}?documents=&attachments=` | `document:read` | Cut one. Returns a zip with `X-Pack-Digest` and `X-Pack-Content-Digest` |
| `GET` | `/export-packs/{name}/manifest` | `document:read` | The manifest without the bytes — compare `content_digest` against the last pack |

### Risk appetite and the board pack

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/risk-appetite/metrics` | auth | The twelve things that may be held to a limit, and why each matters |
| `GET` | `/risk-appetite` | auth | Every live limit, least specific scope first |
| `POST` | `/risk-appetite` | `policy:publish` | `metric, limit, rationale` + `amber`, `scope`, `owner`, `review_at`. Declaring over an existing limit versions it |
| `POST` | `/risk-appetite/retire` | `policy:publish` | Stop holding the estate to it; the versions stay |
| `GET` | `/risk-appetite/history/{metric}` | auth | Every version, so a relaxation is findable |
| `POST` | `/board-packs/preview` | `report:read` | What the pack would say, without recording one |
| `POST` | `/board-packs` | `report:cut` | Record it. This is the one a minute refers to |
| `GET` | `/board-packs`, `/board-packs/{id}` | `report:read` | Packs on record; one as it was read, not as it would be recomputed |

There is no composite score endpoint. Aggregating requires the parts to compose,
and two models fed by the same curve are not two independent risks — see
[risk appetite and the board pack](/help/portfolio-reporting).

### Policy gates

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/policies` | auth | The gates, the rule language, and what a policy may and may not do |
| `POST` | `/policies` | `policy:author` | `gate, rule, reason, cases`. The cases are checked at draft time |
| `GET` | `/policies/{id}` | `policy:read` | One draft with its cases and their verdicts |
| `POST` | `/policies/{id}/publish` | `policy:publish` | Put it in force. Reports every verdict that flipped |
| `POST` | `/policies/try` | `policy:read` | `gate` + `facts`. Ask what the rule in force *would* decide, deciding nothing |
| `GET` | `/policies/facts/{gate}` | auth | The closed vocabulary a rule for this gate may read |
| `GET` | `/policies/history/{gate}` | `policy:read` | Every version, superseded ones included |

A policy adds a condition and can never remove one: it applies *in addition to*
the checks written into the registry, never instead of them.

### Supervisory regimes

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/regimes` | `regime:read` | Each regime's vocabulary, obligations, citations, and whether it is active |
| `GET` | `/regimes/{key}/satisfaction` | `regime:read` | Does truth survive translation into this regime's terms |
| `POST` | `/regimes/{key}/activate` | `regime:activate` | Refused if the encoding is inconsistent or self-contradictory (L-16) |
| `GET` | `/regimes/determinations?urn=` | `regime:read` | Every activated regime's verdict, **kept apart**, each with the terms it read |

### Machine assistance

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/assist/tiers` | auth | Tier A (an oracle checks it), Tier B (citations ground it), and the oracles |
| `GET` `POST` | `/assist/capabilities` | `assist:read` / `assist:register` | Register a capability. Tier A must name an oracle; Tier C is refused by design |
| `GET` | `/assist/providers` | auth | Which model this instance can ask, and why it cannot ask the rest |
| `POST` | `/assist/drafts` | `assist:generate` | Ask for a draft. What it may cite is fixed from the register **before** it is asked. 501 where no provider is configured |
| `POST` | `/assist/generations` | `assist:generate` | Record a generation produced elsewhere, gated the same way |
| `GET` | `/assist/generations/{id}` | `assist:read` | The draft, its grounded claims, and the ones rejected |
| `POST` | `/assist/generations/{id}/attest` | `assist:attest` | A person signs. Not whoever asked for it. Until then it is not evidence |
| `GET` | `/assist/reviewers/{reviewer}` | `assist:read` | Automation-bias trend for one reviewer |

There is deliberately no endpoint that turns a generation into a governance
decision, and a test reads the OpenAPI document to keep it that way.

### Baseline, scheduler and notifications

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/baseline/gaps` | auth | The thirteen computed gaps and their materiality |
| `GET` | `/baseline` | `baseline:read` | The burn-down, and the import batches |
| `POST` | `/baseline/imports` | `baseline:import` | `source` + `models`, `note`. One bad row does not stop the batch |
| `GET` | `/baseline/debt?urn=` | `baseline:read` | Open debt for one model |
| `POST` | `/baseline/debt/{id}/plan` | `baseline:plan` | `plan`. An empty one is refused |
| `POST` | `/baseline/reconcile?urn=` | `baseline:plan` | No body. Closes what is now evidenced, expires what is overdue. Idempotent |
| `GET` | `/scheduler`, `/scheduler/history` | `scheduler:read` | The jobs and their health; what has run |
| `POST` | `/scheduler/run` | `scheduler:run` | `jobs` — empty runs all of them. Idempotent |
| `GET` | `/notifications` | auth | Which channels actually work, and whether anything is reaching anybody |
| `GET` | `/notifications/history` | `principal:read` | Deliveries, failures kept |
| `GET` | `/notifications/preview` | auth | The digest **you** would receive |
| `POST` | `/notifications/run` | `scheduler:run` | `channel`, `dry_run`. One of the scheduler's jobs |

### Identity and authorisation

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/me` | auth | Your permissions, scope and roles, explained |
| `GET` | `/roles` | auth | The catalogue, the incompatible pairs, and the segregation rules |
| `GET` `POST` | `/principals` | `principal:read` / `principal:manage` | Administer principals |
| `PUT` | `/principals/{username}/roles` | `principal:manage` | Refused on an incompatible pair unless `allow_conflicts` |
| `POST` | `/principals/{username}/suspend` | `principal:manage` | Takes effect on the next request |
| `GET` | `/sso` | none | Whether SSO is on, and why not if it is off |
| `POST` | `/sso/preview` | `principal:manage` | Which roles a claim set would produce, signing nobody in |

### Health and evidence

| Method | Path | Permission | Notes |
|---|---|---|---|
| `GET` | `/health`, `/health/live` | none | Liveness with uptime and version. **Not** under `/api/v1` |
| `GET` | `/health/ready` | none | **Includes the evidence chain**, incrementally from the last checkpoint. 503 if it is broken |
| `GET` | `/api/v1/evidence/chain` | `evidence:read` | The full walk from genesis |

## The refusals you are most likely to hit

### "versions are immutable"

```
version 3.2.1 already exists for maya://model/x; versions are immutable
```

Working as designed. Create `3.2.2`. If you are re-running a pipeline that
should be idempotent, have it check for the version first rather than relying on
create-or-update — there is deliberately no update.

### "alias move refused"

Four different causes, distinguished by the message, checked in this order.

**Not approved:** *version 3.2.2 is 'draft', not approved.* Approve it first.

**Blocking finding:** see below.

**Refinement or variance failed:** the message names the clause. The replacement
assumes more than the incumbent (a narrower input range) or guarantees less, or
its schemas are not substitutable. This is not a bug — the replacement would
break existing consumers. Either widen the new contract, or move consumers to a
new alias.

**Segregation:** you created the version, so you may not promote it.

### "blocking finding(s) open" — HTTP 423

A Critical finding (or one explicitly marked blocking) stands against this
model. The model is still registered, approved and aliased — and unservable.

Either close the finding (needs a verifier who is not the owner, plus closure
evidence), or if it should not have been blocking, that is a decision somebody
must make explicitly rather than route around.

### "quorum required" — HTTP 409

A Tier 1 or Tier 2 version cannot be approved by one person. `GET
/api/v1/version-approval-quorum` says which roles this tier needs; open the
approval with `POST /api/v1/version-approvals` and have each role sign.

### "holds no warrant" — HTTP 403

The principal has no standing entitlement in that environment. Issue one with
`POST /api/v1/warrants`. Entitlement is per **principal, environment and
declared use** — a grant for `svc/pricing` in `uat` does nothing in `prod`.

### "declared use … is not the approved use" — HTTP 403

The warrant was granted for one use and a different one was presented. This is
the control that catches a model approved for origination decisioning quietly
being used for pricing. Either declare the approved use, or seek approval for
the new one — do not edit the grant to make the error go away without that
conversation.

### "assembly lacks a bound on …"

```
assembly lacks a bound on transaction_time; without both, leakage cannot
be excluded
```

You disabled one of the temporal bounds. Both are required. If you genuinely
want the latest restated view of history — a legitimate thing to want for
*analysis*, never for training — read the Delta table directly rather than going
through assembly.

### The shorter ones

| You saw | It means | Do this |
|---|---|---|
| *not computable on this sample* | A class was absent, the base rate was zero, or there were fewer reference points than requested PSI bins. It is recorded and **does not pass** | Fix the sample; do not lower the threshold |
| *cannot approve: N test(s) failed* | Working as designed | `approved_with_conditions` with the conditions written down, or `rejected` |
| *cannot verify its own closure* | The verifier is the finding's owner, and a blocking finding is the only thing standing between a failed model and production | Route the verification to somebody else |
| *this model is attested and therefore immutable* | You are changing a record in force — including by adding a version, which counts as a change | Open an amendment |
| *'featureset' is not something a document can be about* | A subject must be pinned, so it is `featureset_version` | Name the version the document describes |
| *the UI shows no features* | The model version has no [feature contract](/help/features-and-two-clocks#feature-contracts) bound, so it reads no governed features | `POST /api/v1/feature-contracts` |
| *a configuration change had no effect* | A key in the tracked file is overridden by the same key in the git-ignored overlay — what the overlay is for, and what makes it confusing at 2am | Check precedence, below |
| *compares '…' with 'high', but the field is declared 'numeric'* (`value_wrong_type`, 422) | The comparison can never be true, so the rule can never fire. Refused only where the platform is certain — a `date` may be an epoch or an ISO string, and an unrecognised dtype is somebody's extension, so neither is judged | Give a value of the right kind, or fix the field's declared type |
| *rule '…' can never fire* (`rule_unreachable`, 422) | An earlier rule matches everything this one matches. A rule that never fires still appears in the model card and in every committee paper, and nobody reading either can tell | Reorder them, narrow the earlier rule, or delete this one |
| *rules '…' and '…' have the same condition and different outcomes* (`rules_contradict`, 409) | First match wins, so the second can never fire — but the ordering is not the problem | Decide which outcome the policy actually means |
| *reads '…', which this model's input schema does not declare* (`unknown_field`, 422) | A rule reading a field that does not exist is a rule that will silently never fire | Declare it on the version, or read a field it has |
| *does not say why it exists* (`reason_required`, 422) | `because` is required per rule. A rule nobody can justify is one nobody can retire either | Name the policy, the limit or the regulation |

### /health/ready returns 503

The evidence chain failed verification. This is serious: a historical record
does not reconcile with its hashes. Do not restart and hope. Capture the chain
state (`GET /api/v1/evidence/chain`, which walks the whole thing rather than the
incremental slice readiness checks), and treat it as an integrity incident.
Nothing else takes readiness down — a stopped scheduler is reported there but is
informational.

## Configuration

Everything is in `config/application.yaml`. There is one file, it is tracked,
and secrets do not go in it.

### Precedence

```
command line  >  environment  >  config/application.local.yaml  >  config/application.yaml
```

The `.local.yaml` overlay is **git-ignored** and sets only the keys it names.
That is where a password, a signing key or a production database URL belongs. A
committed secret is a public secret.

```bash
python run_maya_web.py --server.port=8080 --database.url=postgresql+psycopg://...
```

One trap worth knowing: `MAYA_CONFIG_FILE` in the environment overrides the
config file path entirely, including one passed as an argument.

### Substitution

`${VAR}` and `${VAR:default}` resolve against other keys in the file,
environment variables, and command-line overrides:

```yaml
server:
  port: "${PORT:5006}"
database:
  url: "sqlite:///${data.sqlite.dir}/maya.db"
```

Values are read as strings and coerced on access, so `port: 5006` and
`port: "${PORT:5006}"` behave identically. A reference that resolves to nothing
is left verbatim rather than silently emptied.

> **Careful with YAML booleans.** Bare `yes`, `no`, `on`, `off` are coerced to
> booleans by YAML itself. If you mean the string, quote it.

### Switching to PostgreSQL

```yaml
database:
  url: "postgresql+psycopg://maya:...@db.internal:5432/maya"
```

That is the entire change; the dialect is chosen from the URL and nothing else
in the application differs. There are **no migrations**: the schema is two
hand-written files, `db/schema/sqlite.sql` and `db/schema/postgres.sql`, applied
idempotently at start-up with `CREATE TABLE IF NOT EXISTS`. The two differ by
exactly **one** type substitution — `REAL` where PostgreSQL needs `DOUBLE
PRECISION` — and timestamps are epoch seconds throughout, because SQLite has no
date type and the two dialects disagree about time zones. JSON documents are
`TEXT` rather than `JSONB` deliberately, so no query depends on a
dialect-specific operator.

There is no `BOOLEAN` column anywhere, in either dialect: integer `0`/`1`, and
the service layer converts to a real `bool` at its boundary. That is not
fastidiousness. The PostgreSQL file once declared fourteen columns `BOOLEAN`
while the repository layer coerced every boolean to `int` on the way in;
PostgreSQL does not implicitly cast integer to boolean, so every insert touching
one of those tables failed and the whole dialect was unusable — and nothing
tested it. A discipline test now walks both schemas column for column.

### Storage layout

```yaml
data:
  dir: ./data
  attachments: "${data.dir}/attachments"
  artifacts:   "${data.dir}/artifacts"
  sqlite: {dir: "${data.dir}/sqlite"}
  delta:
    dir: "${data.dir}/delta"
    features:   "${data.delta.dir}/features"
    snapshots:  "${data.delta.dir}/snapshots"
    telemetry:  "${data.delta.dir}/telemetry"
    monitoring: "${data.delta.dir}/monitoring"
    retention_days: 400
```

Nothing under `data/` is committed. It holds the development database, the Delta
lake, filed documents and any artifacts. `data.artifacts` is also the directory
the captive engine reads artifacts from, and a path resolving outside it is
refused.

### Other keys worth knowing

`warrants.*` sets TTL, grace and jitter by tier — see
[Warrants and execution](/help/warrants#expiry-grace-and-the-revocation-floor).
`risk.*` sets the exposure bands, purpose ranks and review cadence,
`lifecycle.attestation.*` the quorum, `overlays.*` the window and renewal limit,
`notifications.*` the channels and quiet period, `regimes.active` which
supervisors are switched on, `scheduler.loop.*` the optional in-process timer,
`assist.provider` which model may be asked, and `execution.captive.enabled`
whether the bundled engine exists at all.

```yaml
content:
  dir: ./content
```

Help, tutorials and about pages are markdown files under this directory,
rendered at request time and cached on modification time. Edit a topic and the
next request shows it — no restart.

### Logging

```yaml
logging:
  level: INFO
  format: "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s %(principal)s] | %(message)s"
  json: false
```

One logger hierarchy, one format, installed at startup. Every module logs
through `core.log.get_logger(__name__)`, and **no exception anywhere is ignored
or swallowed** — a handler may recover, but it may not do so silently. A test
walks the abstract syntax tree of every source file to enforce it: every
`except` must log, none may be bare, and none may have a body that is only
`pass`.

#### Every line says which request, and whose

```
2026-09-05 09:14:02 WARNING core.execution.warrants [8f2c1a7e4b3d0865 a.mehta] | refused (blocked): an open finding stands against credit.pd.smallbiz
```

Two fields between the brackets: the **request id** and the **principal**. A
refusal you cannot trace back to a request is a refusal you diagnose twice, and
there is a second reason particular to this platform — the evidence chain
records what was *decided*, the log records what happened around it, and a
`warrant_resolved` node and the six lines before it join on the request id or
they do not join at all.

Every response carries the id back in `X-Request-ID`, so a bug report can quote
it:

```bash
curl -si -u a.mehta:pw localhost:5006/api/v1/models | grep -i x-request-id
```

**An inbound `X-Request-ID` is honoured when it is safe to log.** That is what
lets one trace span a gateway, a queue and this process. Honouring it
*unchecked* would be log injection — the value lands in a log file, and a
newline in it writes a line of somebody else's choosing — so anything that is
not plainly alphanumeric (up to 64 characters of `A-Za-z0-9._:-`) is
**replaced** rather than escaped, and the response header tells the caller which
id was actually used.

One line per request records the method, path, status and duration, at a level
that follows the outcome: `INFO` for success, `WARNING` for a refusal — a
governance decision is worth seeing — and `ERROR` for a fault.

#### JSON, when something ships the logs

`json: true` emits one object per line, with the same fields plus `method`,
`path`, `status` and `duration_ms` on access lines:

```json
{"ts": "2026-09-05T09:14:02.317Z", "level": "WARNING",
 "logger": "core.execution.warrants", "request_id": "8f2c1a7e4b3d0865",
 "principal": "a.mehta", "message": "refused (blocked): an open finding stands"}
```

Offered rather than imposed: a person reading a terminal is served worse by
JSON, and an instance nobody ships logs from should not pay for a format only a
machine reads.
