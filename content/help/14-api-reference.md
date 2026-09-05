---
title: The API, refusals and configuration
slug: api-reference
section: Reference
order: 140
icon: code-slash
summary: Every endpoint grouped by what it is for, the shape a refusal comes back in and what each code means, the refusals you are most likely to hit and what to do about them, and how the platform is configured.
audience: Engineers, Operators, Model owners
---

# The API, refusals and configuration

Base path `/api/v1`. Interactive documentation is at **`/docs`**; the OpenAPI
document is at `/api/v1/openapi.json`. Everything the interface does is available
here — the interface is a client, not a privileged path.

## The refusal shape

A refusal that does not tell you how to proceed is a support ticket. So a
governance refusal carries three fields: a machine-readable `error` code, a
human `detail` that names the specific thing that failed, and a `remediation`
saying what to do about it.

```json
{
  "error": "no_entitlement",
  "detail": "svc/pricing holds no warrant for maya://model/x in prod",
  "remediation": "request a warrant grant for this principal and approved use"
}
```

Two exceptions are worth knowing before you write a client against it:

- A plain **not-found** carries `error` and `detail` only. There is no useful
  remediation for a name that does not exist.
- **Request validation** — a malformed body, a missing required field, a wrong
  type — is rejected by the web framework before any MAYA code runs, and comes
  back in the framework's own shape with a `detail` list and no `error` key. If
  your client keys on `error`, handle 422 without one.

## Error codes

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
| `registry_refused` | 409 | A registry rule was not satisfied |
| `feature_refused` | 409 | A feature or featureset rule was not satisfied |
| `validation_refused` | 409 | A validation rule was not satisfied |
| `illegal_transition` | 409 | The lifecycle does not allow that move |
| `record_frozen` | 409 | The record is not in a mutable state |
| `cohort_immature` | 409 | No outcomes have matured yet |
| `revoked` / `expired` | 410 | The warrant is no longer current |
| `restricted` | 423 | Version is not approved for this environment |
| `blocked` | 423 | An open blocking finding stands against this model |
| `validation_failed` | 422 | Malformed request — bad URN, misaligned series |
| `assembly_rejected` | 422 | A training set assembly was not point-in-time safe |
| `boundary_violation` | 422 | Inputs outside the contract's assumptions |
| `grammar_violation` | 422 | The warrant does not conform to the grammar |
| `test_not_admissible` | 422 | This test cannot answer this monitor's question |
| `no_runtime` | 501 | No execution runtime is configured for that warrant |
| `unknown_format` | 422 | Not an artifact format this platform stores |
| `artifact_digest_mismatch` | 409 | The bytes do not hash to the digest you declared |
| `artifact_not_stored` | 404 | Nothing is held under that address |
| `artifact_too_large` | 413 | Over the 8 GiB ceiling |
| `unknown_profile_fact` | 422 | A profile tried to select on something the platform does not derive |
| `not_defaultable` | 422 | A profile tried to fill in something a caller could not have typed |
| `authority_not_defaultable` | 403 | A profile reached for authority; write it as a policy gate instead |
| `csrf_token_invalid` | 403 | A state-changing request rode a session cookie without a valid token |

Segregation refusals are a family, and each names the act it is protecting:
`self_review` on a document, `self_approval` on a parameter set or an overlay,
`self_renewal` on an overlay, `self_attestation` on a machine generation.

## Authenticating, and the one case that needs a token

Two ways in, against the same principal register:

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

The pages do this for you (`web/static/js/csrf.js` attaches it to every
same-origin mutation), so this matters only if you are scripting against a
signed-in session rather than using Basic. If you are, use Basic.

| | Token required |
|---|---|
| `POST`/`PUT`/`DELETE` under a session cookie | **yes** |
| `POST` under HTTP Basic | no |
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

## The endpoints

### Paging, search and sorting

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

### Models, versions and aliases

| Method | Path | Notes |
|---|---|---|
| `GET` | `/models` | Inventory; filter by `domain`, `tier`. Scope-filtered |
| `POST` | `/models` | Register. Duplicate URN is refused |
| `GET` | `/models/{name}` | Model with versions, aliases, history |
| `POST` | `/models/{name}/versions` | Create an immutable version |
| `POST` | `/models/{name}/versions/{semver}/approve` | Draft → approved |
| `PUT` | `/models/{name}/aliases` | Move an alias. Gated on approval, findings, L-7 and L-12 |
| `POST` | `/models/{name}/assess` | Risk tier with its full derivation |

### Serialised model artifacts

The bytes of a model that is a file rather than a record — a network's weights, a
prompt bundle, a quantised checkpoint. Stored under their own SHA-256, so an
artifact cannot be edited in place and storing the same one twice stores it once.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/artifact-formats` | What may be stored, and which formats execute code when they load |
| `POST` | `/artifacts?format=&digest=` | The body is the file. `digest` is **checked**, not trusted |
| `GET` | `/artifacts/{digest}` | The bytes back, streamed |
| `GET` | `/artifacts/{digest}/verify` | Re-derive the hash from the bytes on disk |
| `GET` | `/artifact-usage` | How many artifacts, and how many bytes |

A version naming a digest the store holds gets its `artifact_uri` and
`artifact_size` **from the store** — the store is the authority on its own
contents. A digest it does not hold is recorded as naming an artifact somebody
else holds, which is a different state rather than an error, and the warrant
carries the difference as `held_by_maya`.

Ceiling 8 GiB. A governance platform is not a model store of last resort.

### Warrant profiles

Request defaults, selected by facts the platform derives. A profile fills holes
in a warrant request; it never overrides a caller and never widens authority.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/warrant-profile-vocabulary` | What a profile may select on, and what it may fill in |
| `GET` | `/warrant-profiles` | The live profiles, least specific first — the order they fold |
| `POST` | `/warrant-profiles` | Register a version. Immutable; a second `POST` under the same name is version 2 |
| `POST` | `/warrant-profiles/{name}/retire` | Stop it applying. Warrants it already shaped stand |
| `POST` | `/warrant-profiles/preview` | What would apply to this model, and which profile said so |

### Lifecycle

| Method | Path | Notes |
|---|---|---|
| `GET` | `/lifecycle` | The states and the legal transitions |
| `PATCH` | `/models/{name}` | Edit fields. Refused on a frozen record |
| `POST` | `/models/{name}/submit`, `/approve`, `/return` | Move the record |
| `POST` | `/models/{name}/attest` | Sign for one required role |
| `POST` | `/models/{name}/amend` | Open an amendment |
| `POST` | `/models/{name}/retire` | Withdraw from use, keep everything |
| `DELETE` | `/models/{name}` | Administrators only |

### Version approval by quorum

A whole subsystem that was documented nowhere. A Tier 1 or Tier 2 version is
approved by two people in two named roles, so `POST /versions/{semver}/approve`
refuses with `quorum_required` — and until now the refusal pointed at an endpoint
that did not exist and nothing named the ones that do.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/version-approval-quorum` | Which roles each tier requires |
| `GET` `POST` | `/version-approvals` | Open an approval for a version |
| `GET` | `/version-approvals/{id}` | Its signatures so far, and what is outstanding |
| `POST` | `/version-approvals/{id}/sign` | Sign for one role. The same person may not sign twice under two hats |
| `POST` | `/version-approvals/{id}/withdraw` | End it without approving |

### The findings workflow

Everything between raising a finding and closing it. Ageing, acceptance and
escalation are **derived from these acts**, so there is no status column that can
disagree with what happened.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/findings/{id}` | The finding with its acts, ageing and escalation |
| `GET` | `/finding-acts` | The act vocabulary and what each one means |
| `POST` | `/findings/{id}/assign` | Hand it over, with a reason. Authorship never moves |
| `POST` | `/findings/{id}/acknowledge` | The owner accepts it and names a date. Refused without a plan, and refused for a date past the due date |
| `POST` | `/findings/{id}/plan` | Write down what will be done. Re-planning appends |
| `POST` | `/findings/{id}/extend` | Move the date. Never by the owner, never by whoever acknowledged it, counted, and capped by severity |
| `GET` | `/findings/ageing` | The distribution a committee asks for, not a mean |
| `GET` | `/findings/escalated` | Overdue, unaccepted, or past the extension limit |

### Policy gates

| Method | Path | Notes |
|---|---|---|
| `GET` `POST` | `/policies` | The rule in force on each gate; draft a new one |
| `GET` | `/policies/{id}` | One draft with its cases and their verdicts |
| `POST` | `/policies/{id}/publish` | Put it in force. Reports every verdict that flipped |
| `POST` | `/policies/try` | Ask what the rule in force *would* decide, deciding nothing |
| `GET` | `/policies/facts/{gate}` | The closed vocabulary a rule for this gate may read |
| `GET` | `/policies/history/{gate}` | Every version, superseded ones included |

### Machine assistance

| Method | Path | Notes |
|---|---|---|
| `GET` | `/assist/tiers` | Tier A (an oracle checks it) and Tier B (citations ground it) |
| `GET` `POST` | `/assist/capabilities` | Register a capability. Tier C is refused by design |
| `GET` | `/assist/providers` | Which model this instance can ask, and why it cannot ask the rest |
| `POST` | `/assist/drafts` | Ask for a draft. What it may cite is fixed from the register **before** it is asked |
| `POST` | `/assist/generations` | Record a generation produced elsewhere, gated the same way |
| `GET` | `/assist/generations/{id}` | The draft, its grounded claims, and the ones rejected |
| `POST` | `/assist/generations/{id}/attest` | A person signs. Until then it is not evidence |
| `GET` | `/assist/reviewers/{reviewer}` | Automation-bias trend for one reviewer |

### Features, featuresets and parameters

| Method | Path | Notes |
|---|---|---|
| `GET` `POST` | `/features` | List, define. Creating returns `possible_duplicates` |
| `POST` | `/features/{name}/certify` | experimental → certified → deprecated |
| `GET` `POST` | `/feature-views` | List, create |
| `POST` | `/feature-views/{name}/materialise` | Write bitemporal rows; creates a new version namespace |
| `GET` | `/feature-views/{name}/versions` | Materialised versions |
| `GET` | `/feature-views/{name}/versions/{v}/retirable` | Who still pins it |
| `POST` | `/feature-contracts` | Pin a model version to exact view versions |
| `GET` | `/feature-contracts/{version_id}/namespaces` | What serving must read |
| `POST` | `/training-sets` | Point-in-time assembly. Refused if unbounded |
| `GET` | `/expression-language` | What a derived feature may say |
| `GET` `POST` | `/derived-features` | List, define |
| `GET` | `/derived-features/{name}/lineage` | Inputs and dependants, transitively |
| `GET` `POST` | `/featuresets` | List, declare a schema |
| `GET` | `/featuresets/{name}` | The set and its versions |
| `GET` `POST` | `/featuresets/{name}/versions` | Bind features to the schema |
| `POST` | `/featuresets/{name}/roll-forward` | Re-resolve to current view versions |
| `GET` | `/parameter-provenance` | fitted, calibrated, declared |
| `GET` `POST` | `/parameters?urn=&semver=` | Read and record parameter sets. Deliberately **not** nested under `/models/{name}` — that path converter is greedy and would swallow the trailing segment |
| `POST` | `/featuresets/{name}/training-sets` | Assemble a PIT-correct training set from a pinned version |
| `POST` | `/parameter-fits` | **Run** the fit and record what came out. Resolves the warrant before reading anything, reads the snapshot at its pinned Delta version, lands `proposed` |
| `GET` | `/parameter-sets/{id}` | One set with its lineage |
| `POST` | `/parameter-sets/{id}/review` | Approve or reject. Not by whoever recorded it |

### Warrants, execution and the grammar

| Method | Path | Notes |
|---|---|---|
| `POST` | `/warrants` | Issue a standing entitlement |
| `POST` | `/resolve` | Mint a signed, expiring warrant. The hot path |
| `POST` | `/warrants/revoke` | Kill switch for every grant on a model |
| `POST` | `/execute` | Captive engine — one consumer of the same contract |
| `GET` | `/grammar`, `/grammar/schema` | The vocabularies; the generated JSON Schema |
| `POST` | `/grammar/validate` | Check a document before you sign anything |

### Validation, findings, monitoring and overlays

| Method | Path | Notes |
|---|---|---|
| `GET` | `/tests` | The registered test catalogue |
| `POST` | `/validations` | Open an episode. Refused if a validator built the version |
| `GET` | `/validations/{id}` | Episode with results and summary |
| `POST` | `/validations/{id}/results` | Run and record one catalogue test |
| `POST` | `/validations/{id}/conclude` | Refused if a test failed or a finding blocks |
| `POST` | `/validations/{id}/replay` | Recompute and compare on digest |
| `GET` `POST` | `/findings` | List by `urn`, raise |
| `POST` | `/findings/{id}/close` | Needs an independent verifier and evidence |
| `GET` | `/monitor-kinds` | Kinds and the tests each admits |
| `GET` `POST` | `/monitors` | List by `urn`, define |
| `POST` | `/monitors/{id}/evaluate` | Pass in scored rows |
| `GET` | `/monitors/{id}/observations` | What it has measured |
| `GET` | `/overlay-kinds` | The four kinds |
| `GET` `POST` | `/overlays` | Register with aggregate, persistence and trend |
| `POST` | `/overlays/{id}/approve`, `/measure`, `/renew`, `/close` | Each segregated |

### Documents, attachments and regimes

| Method | Path | Notes |
|---|---|---|
| `GET` | `/document-kinds`, `/attachment-kinds` | What may be compiled; what may be filed |
| `GET` `POST` | `/documents` | List by `urn`; compile one |
| `GET` | `/documents/{id}`, `/documents/{id}/markdown` | With citations and staleness; exportable |
| `GET` `POST` | `/attachments` | Current set or `history=true`; file one as multipart |
| `GET` | `/attachments/{id}`, `/attachments/{id}/content` | Re-hashed on the way out |
| `POST` | `/attachments/{id}/review` | Accept or reject. Not by whoever filed it |
| `GET` | `/regimes`, `/regimes/determinations` | Activated regimes; verdicts with their derivations |
| `GET` `POST` | `/regimes/{key}/satisfaction`, `/activate` | The invariance check; activation |

### Baseline, scheduler, assistance and authorisation

| Method | Path | Notes |
|---|---|---|
| `GET` | `/baseline`, `/baseline/gaps`, `/baseline/debt` | Burn-down; the gap catalogue; open debt |
| `POST` | `/baseline/imports`, `/baseline/reconcile` | Import an estate; close what is now evidenced |
| `POST` | `/baseline/debt/{id}/plan` | Give a debt item a date |
| `GET` | `/scheduler`, `/scheduler/history` | State; what has run |
| `POST` | `/scheduler/run` | All jobs, or the ones you name |
| `GET` | `/assist/tiers`, `/assist/capabilities` | The tiers; what is registered |
| `POST` | `/assist/capabilities`, `/assist/generations` | Register; draft |
| `POST` | `/assist/generations/{id}/attest` | Not by whoever asked for it |
| `GET` | `/assist/reviewers/{reviewer}` | Whether a reviewer has stopped reading |
| `GET` | `/me`, `/roles` | Your permissions; the catalogue and the SoD rules |
| `GET` `POST` | `/principals` | Administer principals |
| `PUT` | `/principals/{username}/roles` | Refused on an incompatible pair unless declared |
| `POST` | `/principals/{username}/suspend` | Takes effect on the next request |

### Health and evidence

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health`, `/health/live` | Liveness with uptime and version |
| `GET` | `/health/ready` | **Includes the evidence chain.** 503 if it is broken |
| `GET` | `/api/v1/evidence/chain` | Chain verification result |

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
evidence), or if it should not have been blocking, that is a decision someone
must make explicitly rather than route around.

### "holds no warrant" — HTTP 403

The principal has no standing entitlement in that environment. Issue one with
`POST /api/v1/warrants`. Note that entitlement is per **principal, environment
and declared use** — a grant for `svc/pricing` in `uat` does nothing in `prod`.

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
| *this model is attested and therefore immutable* | You are changing a record that is in force — including by adding a version, which counts as a change | Open an amendment |
| *the UI shows no features* | The model version has no [feature contract](/help/features-and-two-clocks#feature-contracts) bound, so it reads no governed features | `POST /api/v1/feature-contracts` |
| *a configuration change had no effect* | A key in the tracked file is overridden by the same key in the git-ignored overlay — what the overlay is for, and what makes it confusing at 2am | Check precedence, below |

### /health/ready returns 503

The evidence chain failed verification. This is serious: it means a historical
record does not reconcile with its hashes. Do not restart and hope. Capture the
chain state (`GET /api/v1/evidence/chain`), and treat it as an integrity
incident. Nothing else takes readiness down — a stopped scheduler is reported
there but is informational.

## Configuration

Everything is in `config/application.yaml`. There is one file, it is tracked,
and secrets do not go in it.

### Precedence

```
command line  >  environment  >  config/application.local.yaml  >  config/application.yaml
```

The `.local.yaml` overlay is **git-ignored** and sets only the keys it names. That
is where a password, a signing key or a production database URL belongs. A
committed secret is a public secret.

```bash
python run_maya_web.py --server.port=8080 --database.url=postgresql+psycopg://...
```

One trap worth knowing: `MAYA_CONFIG_FILE` in the environment overrides the
config file path entirely, including one passed as an argument.

### Substitution

`${VAR}` and `${VAR:default}` resolve against other keys in the file, environment
variables, and command-line overrides:

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
exactly two substitutions — `REAL`/`DOUBLE PRECISION` and `INTEGER`/`BOOLEAN` —
and timestamps are epoch seconds throughout, because SQLite has no date type and
the two dialects disagree about time zones.

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
`risk.*` sets the tier bands and review cadence, `lifecycle.attestation.*` the
quorum, `overlays.*` the window and renewal limit, `regimes.active` which
supervisors are switched on, `scheduler.loop.*` the optional in-process timer,
and `execution.captive.enabled` whether the bundled engine exists at all.

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
```

One logger hierarchy, one format, installed at startup. Every module logs
through `core.log.get_logger(__name__)`, and **no exception anywhere is ignored
or swallowed** — a handler may recover, but it may not do so silently. A test
walks the abstract syntax tree of every source file to enforce it: every
`except` must log, none may be bare, and none may have a body that is only
`pass`.
