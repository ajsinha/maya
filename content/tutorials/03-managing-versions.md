---
title: Running several versions at once
slug: managing-versions
section: The register
order: 30
icon: layers-half
summary: Champion and challenger, pinned versions, what an alias move must prove, and the amendment cycle for changing an attested model.
audience: Engineers, Model owners
---

# Running several versions at once

## Versions are immutable; aliases move

A model accumulates versions and never edits one. What changes is where the
**aliases** point.

```
maya://model/credit.pd.smallbiz
  ├── 3.2.0  approved   ← prod#previous
  ├── 3.2.1  approved   ← prod#champion, uat#champion
  └── 3.3.0  draft      ← uat#challenger
```

Consumers hold a URN with an alias, never a version:

```
maya://model/credit.pd.smallbiz#champion       whatever is champion here, now
maya://model/credit.pd.smallbiz@3.2.1          exactly 3.2.1, forever
```

That is the whole reason a version can be replaced without anyone redeploying —
and exactly why moving an alias is the most tightly controlled operation in the
platform.

## Champion and challenger

```bash
# the challenger runs in uat against the same traffic
curl -u s.iqbal:pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment": "uat", "alias": "challenger", "semver": "3.3.0"}'
```

Aliases are per environment, so `uat#champion` and `prod#champion` are different
bindings of the same name. Promotion is moving `prod#champion`, and it is refused
unless the replacement can be shown to be a safe substitute.

## What an alias move must prove

Two obligations, both discharged before the pointer moves:

**Refinement (L-7).** The replacement's contract must *assume no more and
guarantee no less*. A version demanding a narrower input range is not a drop-in,
however much better it scores:

```
alias move refused: guarantee 'gini' weakened from minimum 0.42 to 0.10 /
schemas are substitutable
```

**Variance (L-12).** Input schemas are contravariant, output schemas covariant —
a consumer written against the old version still type-checks against the new one.

Plus two gates from elsewhere: the target version must be `approved`, and no
**blocking finding** may be open against the model.

And segregation: the person who *created* the version cannot promote it,
whatever roles they hold. The evidence chain records who built it.

Every move is kept with its proofs:

```bash
curl -u a.mehta:pw localhost:5006/api/v1/models/credit.pd.smallbiz | jq .alias_history
```

## Changing an attested model

An attested record is immutable — including for new versions, because a new
version *is* a change to the model. The route out is an **amendment**:

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/amend \
  -H 'Content-Type: application/json' -d '{
  "reason": "Recalibrate for the 2026 cycle after the Q4 population shift",
  "scope": ["kernel", "thresholds"]}'
```

The record moves to `amending` and is changeable again. Now the cycle repeats:

```
amending → add version 3.3.0 → submit → approve → attest → attested
```

The amendment gets a reference (`AMD-001`) because it will be quoted in
committee minutes, and it closes automatically when the attestation completes.
One amendment at a time per model: two concurrent amendments to one record
produce a document nobody can reconstruct.

## Retiring a version's namespace

Old feature view versions and old model versions accumulate. Before retiring
anything, ask who still depends on it:

```bash
curl -u a.mehta:pw \
  localhost:5006/api/v1/feature-views/sb_financials/versions/1/retirable
# → {"retirable": false, "consumers": ["01a06a0a079c..."]}
```

And the model itself is **retired**, never deleted:

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/retire \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Superseded by credit.pd.smallbiz.v2 from 2026-07-01"}'
```

Retirement keeps everything: the record, the versions, the evidence, the
findings. Deletion is administrators only, needs a reason, and even then the
evidence chain survives it — ending with an entry saying who deleted it and why.
