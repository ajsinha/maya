---
title: Troubleshooting
slug: troubleshooting
section: Reference
order: 180
icon: life-preserver
summary: The refusals you are most likely to hit, what each one actually means, and what to do about it.
audience: Engineers, Model owners
---

# Troubleshooting

Every refusal in MAYA carries a `remediation` field. This page explains the ones
behind the common surprises.

## "versions are immutable"

```
version 3.2.1 already exists for maya://model/x; versions are immutable
```

Working as designed. Create `3.2.2`. If you are re-running a pipeline that
should be idempotent, have it check for the version first rather than relying on
create-or-update — there is deliberately no update.

## "alias move refused"

Three different causes, distinguished by the message.

**Not approved:** *version 3.2.2 is 'draft', not approved.* Approve it first.

**Refinement or variance failed:** the message names the clause. The replacement
assumes more than the incumbent (a narrower input range) or guarantees less, or
its schemas are not substitutable. This is not a bug — the replacement would
break existing consumers. Either widen the new contract, or move consumers to a
new alias.

**Blocking finding:** see below.

## "blocking finding(s) open" — HTTP 423

```json
{"error": "blocked", "detail": "1 blocking finding(s) open against ..."}
```

A Critical finding (or one explicitly marked blocking) stands against this
model. The model is still registered, approved and aliased — and unservable.

Either close the finding (needs a verifier who is not the owner, plus closure
evidence), or if it should not have been blocking, that is a decision someone
must make explicitly rather than route around.

## "holds no warrant" — HTTP 403

The principal has no standing entitlement in that environment. Issue one with
`POST /api/v1/warrants`. Note that entitlement is per **principal, environment
and declared use** — a warrant for `svc/pricing` in `uat` does nothing in `prod`.

## "declared use ... is not the approved use" — HTTP 403

The warrant was granted for one use and a different one was presented. This is
the control that catches a model approved for origination decisioning quietly
being used for pricing. Either declare the approved use, or seek approval for
the new one — do not edit the grant to make the error go away without that
conversation.

## "assembly rejected"

```
transaction_time_bound is false, so the assembly would use facts restated after as_of
```

You disabled one of the temporal bounds. Both are required. If you genuinely
want the latest restated view of history — a legitimate thing to want for
*analysis*, never for training — read the Delta table directly rather than going
through assembly.

## "not computable on this sample"

A test returned no value: a class was absent, the base rate was zero, or there
were fewer reference points than requested PSI bins. The result is recorded and
**does not pass**. Fix the sample; do not lower the threshold.

## "cannot approve: N test(s) failed"

Working as designed, and the message offers the two legitimate routes:
`approved_with_conditions` with the conditions written down, or `rejected`.

## "cannot verify its own closure"

The verifier is the finding's owner. Segregation is required here because a
blocking finding is the only thing standing between a failed model and
production.

## /health/ready returns 503

The evidence chain failed verification. This is serious: it means a historical
record does not reconcile with its hashes. Do not restart and hope. Capture the
chain state (`GET /api/v1/evidence/chain`), and treat it as an integrity
incident.

## The UI shows no features for a model

The model version has no feature contract bound. Bind one with
`POST /api/v1/feature-contracts` so serving is pinned to exact view versions
rather than "latest". A version with no contract reads no governed features —
see [Feature contracts](/help/feature-contracts).

## Configuration change had no effect

Check precedence: command line beats environment beats `application.local.yaml`
beats `application.yaml`. A key set in the tracked file is silently overridden by
the same key in the git-ignored overlay, which is exactly what the overlay is
for and exactly what makes it confusing at 2am.
