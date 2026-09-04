---
title: Features and the two clocks
slug: features-and-two-clocks
section: Features and data
order: 60
icon: clock-history
summary: Why every feature row carries both when a fact was true and when you learned it, how a training set is assembled so it cannot use the future, and how a model version is pinned to the exact feature data it was built on.
audience: Engineers, Data scientists
---

# Features and the two clocks

Three mechanisms, one purpose: a model should be served the same numbers it was
trained on, and should never have been trained on numbers nobody could have
known at the time. The two clocks make that expressible, point-in-time assembly
makes it checkable, and feature contracts make it stay true after everyone has
moved on.

## The failure this prevents

A model scores 0.47 AUC in development and 0.31 in production. The usual
conclusion is that it degraded. Usually it did not: **it was never trained on the
data it is now being served.**

The mechanism is almost always the same. A borrower files Q1 financials on 31
March. They land in the warehouse on 20 May. In August the figures are
**restated** downward after an audit. The warehouse now holds one row: the
restated one, stamped 31 March.

Train a model in September on "what was true as of 31 March" and it learns from
the restated figure — a number nobody could have known in March. The backtest is
measuring the model's ability to use information from the future. In production
that information does not exist, and the performance evaporates.

## Two clocks, always

Every feature row in MAYA carries both:

| Column | Meaning |
|---|---|
| `event_ts` | **Valid time** — when the fact was true in the world |
| `ingest_ts` | **Transaction time** — when the platform learned it |

The restatement above is *two rows*, not an update:

```json
{"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 1.20}
{"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0, "dscr": 0.40}
```

Same valid time. Different transaction times. Nothing was overwritten, so both
questions remain answerable:

- *What was true on 31 March?* → depends when you ask.
- *What did we know on 20 May?* → 1.20.
- *What do we know now?* → 0.40.

A store with one clock can answer only the third, and will answer it to a
question that asked the second.

### Materialisation refuses rows without both

```bash
POST /api/v1/feature-views/sb_financials/materialise
```

A row missing either clock — or the entity it is about — is refused:

```
row is missing 'ingest_ts'; feature rows carry two clocks —
event_ts (when it was true) and ingest_ts (when we learned it)
```

This is deliberately unhelpful to whoever is in a hurry. The alternative —
defaulting `ingest_ts` to now — produces a store that looks fine and is
silently wrong, and the wrongness surfaces months later as unexplained model
decay.

## Defining a feature

```json
{
  "name": "dscr",
  "entity": "customer",
  "dtype": "float",
  "description": "Debt service coverage ratio, trailing twelve months",
  "business_definition": "EBITDA divided by scheduled debt service",
  "owner": "person/d.raman",
  "source_system": "FIN-DW",
  "sensitivity": "internal",
  "pii": false,
  "protected_basis": false,
  "proxy_risk": "none"
}
```

**business_definition** is separate from `description` on purpose. One is for
the engineer reading the column; the other is the definition a validator or an
examiner will hold you to.

**protected_basis** and **proxy_risk** are how fair-lending exposure becomes
queryable. A feature like `zip3` is not a protected basis, but its proxy risk is
high, and being able to ask "which models in the estate read a high-proxy-risk
feature" is the difference between a fair-lending review that takes a day and
one that takes a quarter.

A feature is created `experimental` and can be moved to `certified` or
`deprecated`:

```bash
POST /api/v1/features/{name}/certify?level=certified
```

### Duplicate detection at creation time

Feature sprawl is what makes a large store unusable — the fourth
`customer_income_v2_final` is a discovery problem, not a storage problem. So
near-duplicates surface **when a feature is created**, while renaming is still
cheap: the response to `POST /api/v1/features` carries a `possible_duplicates`
list alongside the feature it just made.

The similarity is token overlap over the name and definitions — a Jaccard
score against a floor, deliberately not embeddings. It has to be fast enough to
run on every definition and explainable enough that a steward can see *why* two
features were called alike.

## Point-in-time assembly

### The rule

For a training row with label timestamp `label_ts`, assembled as of `as_of`, the
admissible feature value is:

> the **latest** fact that was **true by `label_ts`** and **known by `as_of`**

In code that is one predicate:

```python
eligible = [r for r in records
            if r[VALID_TIME] <= label_ts and r[INGEST_TIME] <= as_of]
return max(eligible, key=lambda r: (r[VALID_TIME], r[INGEST_TIME]))
```

Both bounds are required. Drop the valid-time bound and you use facts from after
the label — classic leakage. Drop the transaction-time bound and you use the
*restated* version of a fact that, at the time, said something else.

### Assemblies are refused, not warned

```bash
POST /api/v1/training-sets
{
  "name": "sb_pd_2025h2",
  "spine": [{"entity_id": "C1", "label_ts": 500.0, "label": 1}],
  "views": [{"view": "sb_financials", "version": 1}],
  "as_of": 999.0,
  "valid_time_bound": true,
  "transaction_time_bound": true
}
```

Set either bound to `false` and the request is **rejected** before any data is
read:

```
assembly lacks a bound on transaction_time; without both, leakage cannot
be excluded
```

A warning would be ignored. Everyone under deadline pressure ignores warnings,
and the resulting dataset is indistinguishable from a correct one until the
model reaches production.

### Three layers of verification

Being refused for the obvious mistake is not enough — the assembly could still
be wrong for a subtle reason. So a completed assembly is checked three ways.

**Layer 1 — static gate.** Are both bounds declared? Is `as_of` present? Is the
spine well-formed? Cheap, and catches the common error. This is the layer that
refuses outright: a failure here raises, and no snapshot is written.

**Layer 2 — independent recomputation.** A stratified sample of assembled rows —
two hundred by default, drawn across label values so a rare class is not missed —
is recomputed by a *different code path*: a bitemporal `as_of` read against Delta
rather than the in-memory join the assembly used. The two must agree.
Verification that reuses the assembly path lets a bug hide behind itself.

**Layer 3 — leakage detection.** A sweep over the assembled frame for a column
that **determines** the label — every distinct value mapping to exactly one
outcome. That is what an accidental future-fact join looks like from the outside,
and it is a sharper signal than a correlation threshold, which fires on ordinary
strong predictors.

The `pit_report` on the resulting snapshot records all three, and `pit_verified`
is `false` if layer 2 or 3 failed. The snapshot is still written — you may need
to inspect it — but it is marked, and its status travels with it.

### A worked example

Given the restatement above:

```
C1 @ event_ts=100, ingest_ts=110  →  dscr 1.20
C1 @ event_ts=100, ingest_ts=900  →  dscr 0.40   (the restatement)
```

| Assembled with | Result | Why |
|---|---|---|
| `label_ts=500, as_of=500` | **1.20** | The restatement had not arrived yet |
| `label_ts=500, as_of=999` | **0.40** | Assembling today, we know the restated figure |
| `label_ts=50,  as_of=999` | *nothing* | No fact was true by t=50 |

The first row is what a September backtest of a March decision must use. The
second is what a fresh model trained today should use. A single-clock store
gives 0.40 for both, and the first is a lie.

### Snapshots

An assembly produces a **dataset snapshot**: a named, digested, immutable Delta
table with its PIT report attached. A validation episode can pin one, and a
replay can be run against it — which is what turns "the model was validated on
2025H2 data" into a checkable claim.

## Feature contracts

### The failure mode

A model is trained against a feature view. Six months later the view is
recomputed — a source system changed, a bug was fixed, a definition was
sharpened. The table is updated in place.

The model now scores against different numbers than it was trained on. Nothing
alerts. The contract digest still matches, because the contract named the *view*,
not a version of it. Every monitor is green, because the monitors compare today's
scores to yesterday's and the change was gradual.

This was found in adversarial review as **finding C-2**, and it is the reason for
the design below.

### A version is a serving namespace

Each materialisation writes to its **own Delta path**:

```
features/customer/sb_financials/v1
features/customer/sb_financials/v2
```

Publishing v2 does not touch a single byte that v1 serves. Writes go to a fresh
per-version path, the version number increments per materialisation, and asking
for the namespace of a version that was never materialised is refused. There is
no "latest" and no in-place update, because the mechanism that makes the failure
possible is simply absent.

### Contracts pin exact versions

```bash
POST /api/v1/feature-contracts
{
  "model_version_id": "01a06a...",
  "items": [{"view": "sb_financials", "version": 1}]
}
```

The contract records the resolved namespace for each item and a digest over the
whole binding. Ask what a model version must read:

```bash
GET /api/v1/feature-contracts/{model_version_id}/namespaces
→ {"sb_financials": "features/customer/sb_financials/v1"}
```

Serving reads that namespace. Law **L-17** — contract–serving agreement — is the
rule that what serving *must* read equals what it *did* read, which turns "the
model used the right features" from an assumption into a check. It is named as a
continuous production check rather than a design-time assertion, because C-2 was
invisible to every design-time check there was.

Binding to a version that does not exist is refused:

```
'sb_financials' has no version 3
```

### Retirement is guarded

You cannot retire a namespace something still depends on:

```bash
GET /api/v1/feature-views/sb_financials/versions/1/retirable
→ {"retirable": false, "pinned_by": ["01a06a..."]}
```

Storage costs money, so old versions will eventually be retired — but the
decision needs to know who breaks. This makes that answerable in one call
instead of a search across pipelines.

### The cost, stated honestly

This design trades storage for correctness. A view materialised weekly for two
years is 104 namespaces, and they are not deduplicated.

That is a real cost and it is the right trade for governed features: the
alternative saves disk and reintroduces exactly the silent failure the design
exists to prevent. Retirement is how the cost is managed, and the guard above is
what makes retirement safe rather than hopeful.

## Next

Naming a set of features so a warrant can ask for it by name, computing derived
features from primitives, and storing what a fit produced:
[Featuresets and fitted parameters](/help/featuresets-and-parameters).


## A read is pinned to a version, not to a path

A namespace is a path, and a path is mutable. Two writes to the same namespace
produce two Delta versions, and a read that names only the path gets whichever is
current.

For **serving** that is correct — the namespace *is* the contract, and a
correction to a stale row should be served. For **reproducing** it is not: the
whole point of a snapshot is that re-running it returns what it returned before.

So an assembly reads at the Delta version the view version was materialised at,
and a featureset binding carries that version alongside the path. That is what
makes *same featureset version → same bytes* true rather than
true-until-somebody-writes-again.

The neighbouring question — *has anything underneath this pin moved?* — is
answered separately, because it is the one a reviewer asks before comparing two
runs:

```
GET /api/v1/featuresets/{name}/versions/{n}/restatements
```

```json
{"restated": true,
 "slots": [{"slot": "dscr", "delta_version": 3, "current_delta_version": 5}],
 "detail": "1 of this version's namespaces have been written to since it was
            published; the version still reads the bytes it pinned"}
```

A restatement is not automatically wrong. Correcting a row that was stale is a
legitimate act. What matters is that a reader who dropped the pin would now see
something else, and that anybody comparing two runs knows which case they are in.
