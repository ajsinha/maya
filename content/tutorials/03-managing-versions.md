---
title: Running several versions at once
slug: managing-versions
section: The register
order: 30
icon: layers-half
summary: Everything in the register accumulates except one thing. Champion and challenger, what a promotion has to prove before the name moves, the one order that decides it, and the amendment cycle for changing a record that is already in force.
audience: Engineers, Model owners
---

# Running several versions at once

Almost everything you do here **adds**. A version is created and never edited. A
parameter set joins the ones before it. A finding is closed rather than removed.
Evidence is appended. Nothing is deleted; a model is retired.

There is exactly one operation that **replaces**, and this page is about it.

---

## The indirection, and what it costs

A model accumulates versions. What moves is where the **aliases** point.

```
maya://model/credit.pd.smallbiz
  ├── 3.2.0  approved   ← prod#previous
  ├── 3.2.1  approved   ← prod#champion, uat#champion
  └── 3.3.0  draft      ← uat#challenger
```

A consumer holds a URN, never a version:

```
maya://model/credit.pd.smallbiz#champion    whatever is champion here, now
maya://model/credit.pd.smallbiz@3.2.1       exactly 3.2.1, forever
```

That indirection is what lets a version be replaced with nobody redeploying, and
what lets a decision made months ago be reproduced by pinning. Both are worth
having. Both are bought by the same fact: **the meaning of `#champion` can
change under a caller who is not watching.**

So the alias move is the most tightly controlled operation in the platform, and
it is a **proof obligation** rather than a write. Aliases are per environment,
so `uat#champion` and `prod#champion` are different bindings of the same name.

```bash
# the challenger runs in uat against the same traffic
curl -u s.iqbal:pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment": "uat", "alias": "challenger", "semver": "3.3.0",
       "justification": "monotone recalibration on the 2026 population"}'
```

---

## The five things a promotion must establish

They are checked in this order, and the order is chosen so the cheapest and most
useful refusal comes first.

**1 · The target is approved.**

```
version 3.3.0 is 'draft', not approved; an alias may only point at an
approved version
```

**2 · No blocking finding stands open.** Checked before the contract proofs,
because *this model has an unresolved Critical finding* is a more useful refusal
than a clause number, and cheaper to establish:

```
alias move refused: 1 blocking finding(s) open against
maya://model/credit.pd.smallbiz (Label leakage in the training set);
close them or downgrade them before promoting a version
```

**3 · Refinement — L-7.** The replacement's operating contract must *assume no
more and guarantee no less*. A version that scores better and demands a narrower
input range is not a drop-in:

```
alias move refused: guarantee 'gini' weakened from minimum 0.42 to 0.10 /
schemas are substitutable
```

Both halves of the proof are reported, passing and failing alike, so you can see
which clause failed rather than which call did.

**4 · Variance — L-12.** Input schemas are **contravariant** and output schemas
**covariant**: the new version must accept everything the old one accepted, and
provide everything the old one provided. A consumer written against 3.2.1 still
type-checks against 3.3.0, or the move does not happen.

**5 · Segregation.** Whoever *created* the version cannot promote it, whatever
roles they hold. That is not a role check — `s.iqbal` holds `alias:move` and
would still be refused had they created 3.3.0. The evidence chain records who
built it, and the segregation policy reads the chain.

A gate on `alias:move` can add more. Gates are versioned predicates with their
cases recorded, so *what did the rule say in March* has an answer.

---

## One order, four questions

The interesting thing about clause 4 is that it is no longer its own
implementation. `core/domain/lattice.py` holds a single partial order on
schemas:

> **`A ⊑ B`** iff `A` has every field `B` has, each accepting **at least** what
> `B`'s accepted.

Read it as *A can stand in for B*. Extra fields are fine — they are simply not
read — and each shared field must accept at least what its counterpart did,
because a replacement that rejects an input its predecessor took is a
replacement that breaks a caller.

Four questions used to have four implementations of that relation:

| Question | Now |
|---|---|
| is the replacement substitutable? (**L-12**) | `refines(new_in, old_in)` |
| does the featureset provide what the kernel reads? (**L-W10**) | the same `refines`, one level out |
| is this child featureset a refinement of its parent? | `A ⊑ B` |
| does one model's output arrive where another reads it? (**L-21**) | the same `refines`, across a dependency edge |

`L-W10` and `L-12` are now **literally the same comparison**. That matters
because four implementations of one relation disagree eventually, and the
direction is predictable: towards permitting more, because that is the direction
in which nobody files a bug.

The order is a lattice — meet is what a featureset must provide to serve two
models at once, join is what two versions agree on — and `L-20` asserts the
lattice laws over generated schemas in the test suite.

---

## The move is kept with its proofs

```bash
curl -u a.mehta:pw localhost:5006/api/v1/models/credit.pd.smallbiz | jq .alias_history
```

Each entry carries the version it moved from, the version it moved to, the
refinement result, the variance result, who moved it, when, and the
justification they gave. A promotion whose proof is not stored is a promotion
somebody has to reconstruct from memory the first time it is questioned.

---

## Changing a record that is in force

An attested record is immutable — **including for new versions**, because a new
version *is* a change to the model, and pretending otherwise is how an attested
record quietly stops describing what runs.

```
409 — cannot add a version to maya://model/credit.pd.smallbiz:
the record is attested
```

The route out is an amendment:

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/amend \
  -H 'Content-Type: application/json' -d '{
  "reason": "Recalibrate for the 2026 cycle after the Q4 population shift",
  "scope": ["kernel", "thresholds"]}'
```

The record moves to `amending` and is changeable again:

```
amending → add version 3.3.0 → submit → approve → attest → attested
```

The amendment gets a reference because it will be quoted in committee minutes,
and it closes when the attestation completes. **One amendment at a time per
model**: two concurrent amendments to one record produce a history nobody can
reconstruct.

Seven states in all, and two of them are places a record can *start*: `draft`
for something somebody registered, `baselined` for something imported from a
legacy inventory and carrying explicit debt for the evidence it does not have.
An import must never enter through `draft`, because the register would then
imply that historical evidence was asserted when it was not.

---

## Recalibration is not a new version

Worth stating here because it is the distinction people lose first. Recording
new parameters does **not** create a version. The kernel did not change; a
different point of `P` is being run at.

That is what lets a daily recalibration *procedure* be approved once instead of
pretending a committee meets every morning, and it is why *did this model change
in March* has one answer rather than two. The parameter set is approved on its
own, by somebody other than whoever recorded it — see [training a model, end to
end](/tutorials/train-a-model).

---

## Retiring what nobody needs

Before retiring anything, ask who still depends on it:

```bash
curl -u a.mehta:pw \
  localhost:5006/api/v1/feature-views/sb_financials/versions/1/retirable
```

```json
{"retirable": false, "pinned_by": ["01a06a0a079c…"]}
```

A featureset version pinned that view version, and a model was fitted from it.
Retiring it would make a training set unreproducible, which is a decision rather
than a tidy-up.

And a model is **retired**, never deleted:

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/retire \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Superseded by credit.pd.smallbiz.v2 from 2026-07-01"}'
```

Retirement keeps everything: the record, the versions, the evidence, the
findings, the alias history and its proofs. Deletion is administrators only,
needs a reason, and even then the evidence chain survives it — ending with an
entry saying who deleted it and why.

---

Next: [features, end to end](/tutorials/features-end-to-end), where the same
question — *can this stand in for that* — is asked of data rather than of
kernels, and answered by a clock.
