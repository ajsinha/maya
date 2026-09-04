---
title: API reference
slug: api-reference
section: Reference
order: 150
icon: code-slash
summary: Every endpoint, what refuses and why, and the RFC 9457 shape every refusal comes back in.
audience: Engineers
---

# API reference

Base path `/api/v1`. Interactive documentation is at **`/docs`**; the OpenAPI
document is at `/api/v1/openapi.json`.

## The refusal shape

Every failure — from every route — comes back in the same shape:

```json
{
  "error": "no_entitlement",
  "detail": "svc/pricing holds no warrant for maya://model/x in prod",
  "remediation": "request a warrant grant for this principal and approved use"
}
```

Three fields, always: a machine-readable `error` code, a human `detail` that
names the specific thing that failed, and a `remediation` saying what to do about
it. A refusal that does not tell you how to proceed is a support ticket.

| Code | HTTP | Meaning |
|---|---|---|
| `not_found` | 404 | No such model, version, warrant or validation |
| `validation_failed` | 422 | Malformed request — bad URN, misaligned series |
| `assembly_rejected` | 422 | A training set assembly was not point-in-time safe |
| `boundary_violation` | 422 | Inputs outside the contract's assumptions |
| `no_entitlement` | 403 | This principal holds no warrant |
| `use_not_approved` | 403 | Declared use is not the approved use |
| `signature_invalid` | 403 | Warrant signature does not verify |
| `registry_refused` | 409 | A registry rule was not satisfied |
| `feature_refused` | 409 | A feature rule was not satisfied |
| `validation_refused` | 409 | A validation rule was not satisfied |
| `restricted` | 423 | Version is not approved for this environment |
| `blocked` | 423 | An open blocking finding stands against this model |
| `revoked` / `expired` | 410 | The warrant is no longer current |
| `no_runtime` | 501 | No execution runtime is configured |

## Models

| Method | Path | Notes |
|---|---|---|
| `GET` | `/models` | Inventory; filter by `domain`, `tier` |
| `POST` | `/models` | Register. Duplicate URN is refused |
| `GET` | `/models/{name}` | Model with versions, aliases, history |
| `POST` | `/models/{name}/versions` | Create an immutable version |
| `POST` | `/models/{name}/versions/{semver}/approve` | Draft → approved |
| `PUT` | `/models/{name}/aliases` | Move an alias. Gated on refinement, variance and findings |
| `POST` | `/models/{name}/assess` | Risk tier with its full derivation |

## Features

| Method | Path | Notes |
|---|---|---|
| `GET` `POST` | `/features` | List, define |
| `POST` | `/features/{name}/certify` | experimental → certified → deprecated |
| `GET` `POST` | `/feature-views` | List, create |
| `POST` | `/feature-views/{name}/materialise` | Write bitemporal rows; creates a new version namespace |
| `GET` | `/feature-views/{name}/versions` | Materialised versions |
| `GET` | `/feature-views/{name}/versions/{v}/retirable` | Who still pins it |
| `POST` | `/feature-contracts` | Pin a model version to exact view versions |
| `GET` | `/feature-contracts/{version_id}/namespaces` | What serving must read |
| `POST` | `/training-sets` | Point-in-time assembly. Refused if unbounded |

## Warrants

| Method | Path | Notes |
|---|---|---|
| `POST` | `/warrants` | Issue a standing entitlement |
| `POST` | `/resolve` | Mint a signed, expiring warrant. The hot path |
| `POST` | `/warrants/revoke` | Kill switch for every warrant on a model |
| `POST` | `/execute` | Captive engine — one consumer of the same contract |

## Validation and findings

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

## Health and evidence

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Liveness with uptime and version |
| `GET` | `/health/ready` | **Includes the evidence chain.** 503 if it is broken |
| `GET` | `/evidence/chain` | Chain verification result |
