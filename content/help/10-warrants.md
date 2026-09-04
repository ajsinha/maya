---
title: Warrants
slug: warrants
section: Execution
order: 100
icon: key
summary: The signed, expiring, entitlement-bound document that an execution engine acts on — and the boundary that keeps MAYA out of the trading day.
audience: Engineers, Model risk
---

# Warrants

A **warrant** is a signed instrument authorising a named principal to perform a
stated operation on a stated model version, within limits, until a stated
moment, revocable at will.

It used to be called a hook. That name suggested a callback, which is the wrong
mental model: nothing calls back, and the document is not a piece of plumbing. It
is an authorisation, and calling it one makes the semantics obvious.

## Why the boundary exists

**MAYA does not execute models.** It issues warrants; an execution engine acts on
them.

That separation is not squeamishness. A governance platform that is also the
runtime becomes a single point of failure for the trading day, and every one of
its outages becomes a governance outage — which is precisely the pressure that
gets governance bypassed. Keeping issuance and execution apart means the control
plane can be unavailable for a minute without the bank stopping, and it means an
execution engine can be replaced without renegotiating governance.

## Grants and warrants are different things

A **grant** is the standing entitlement: this principal, in this environment, for
this declared use.

```bash
POST /api/v1/warrants
{
  "urn": "maya://model/credit.pd.smallbiz#champion",
  "environment": "prod",
  "principal": "svc/origination",
  "declared_use": "origination_decision"
}
```

A **warrant** is the short-lived credential minted against a grant, at the moment
of use:

```bash
POST /api/v1/resolve
{ ...the same four fields... }
```

Separating them is what makes revocation meaningful. Withdrawing the grant stops
future warrants; bumping the revocation epoch invalidates the ones already out.

## What resolution checks, in order

1. **Is the model registered?** → `404 not_found`
2. **Is anything blocking?** → `423 blocked` — see [Findings](/help/findings)
3. **Does this principal hold a grant here?** → `403 no_entitlement`
4. **Has the grant been withdrawn?** → `410 revoked`
5. **Is the declared use the approved use?** → `403 use_not_approved`
6. **Is anything bound for this URN in this environment?** → `404 not_found`
7. **Is that version approved?** → `423 restricted`

The order matters. Revocation is checked before the use comparison, because a
withdrawn warrant is withdrawn whatever the caller claims to be doing with it.

Every refusal carries a reason and a remediation. Resolution **fails closed**:
there is no path that degrades quietly into something that looks like it worked.

## What a warrant carries

Enough for an engine to act correctly and to ask no second question:

- **Subject** — the resolved model, version, manifest digest, and how the
  binding was made (pinned version or alias).
- **Authority** — principal, declared use, environment, when it was granted,
  when it expires, how much grace, and the revocation epoch it was minted under.
- **Realisation** — how to obtain and invoke the artifact, and its digest.
- **I/O contract** — the input and output schemas.
- **Constraints** — the operating boundary from the version's contract, so the
  engine can refuse *before* touching the artifact.
- **Governance snapshot** — tier, model status, version status at the moment of
  resolution, so what an engine acted on can be reconstructed later even if the
  model has moved on since.
- **Signature** — HMAC over the canonical form.

## The URN is all a consumer holds

```
maya://model/credit.pd.smallbiz              the environment's champion
maya://model/credit.pd.smallbiz@3.2.1        a pinned version
maya://model/credit.pd.smallbiz#challenger   a named alias
```

Artifact location, schemas, boundaries and policy are resolved at runtime from
the URN. That is exactly what lets a governed version move happen without a
consumer redeploying — and what makes the alias move the most tightly controlled
operation in the platform.

## Expiry, grace and the revocation floor

TTL and grace are keyed by risk tier:

```yaml
warrants:
  ttl_seconds:   {1: 60, 2: 300, 3: 3600, 4: 3600}
  grace_seconds: {1: 0,  2: 0,   3: 900,  4: 900}
  jitter_pct: 20
```

A Tier 1 model gets sixty seconds and **zero grace**: it must never run on stale
authorisation. Tier 3 and 4 get grace so a transient control-plane outage does
not stop the business.

**Jitter** spreads expiry across a band. Without it, a fleet issued warrants at
deploy time expires in lockstep and stampedes the resolver at the worst possible
moment — found in adversarial review as **H-1**.

**The revocation floor** is the rule that grace never overrides: a warrant on the
local revocation list is refused regardless of grace state. Grace extends how
long an *authorisation* stays current when the platform is unreachable; it never
extends how long a consumer may stay ignorant of a withdrawal it has already been
told about. This was **finding C-1**.

## Revocation

```bash
POST /api/v1/warrants/revoke
{"urn": "maya://model/credit.pd.smallbiz", "reason": "Suspected leakage"}
```

The kill switch: every warrant on the model, at once. The epoch is bumped, so
warrants already in flight can be recognised as stale by any engine that checks.

## Next

- [Execution engines](/help/execution-engines) — what acting on a warrant looks like.
