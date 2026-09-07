---
title: Features, from definition to loaded data
slug: features
section: Start here
order: 20
icon: database
summary: Define a feature, compute one from others, load values into a view, and ask what was knowable at the moment of a decision — each of them through the screens, the SDK and curl.
audience: Model developers, Data engineers, Validators
---

# Features, from definition to loaded data

By the end of this page you will have defined two features, computed a third
from them, loaded values twice, and asked the platform which of those values a
model trained on 1 July was allowed to see. About twenty minutes.

Everything below was run against a real instance. Every response is copied from
that run.

Three things worth knowing before you start.

- **A feature is an object with an owner**, not a column. It is declared before
  it has values, because a view that materialised an undeclared column would be
  a number nobody is accountable for.
- **Every row carries two clocks.** `event_ts` — when the fact was true.
  `ingest_ts` — when the platform learned it. Neither is optional, and section 3
  is why.
- **Looking is free.** `check`, `trial`, `alignment-trial` and the as-of probe
  record nothing, cost no permission beyond `feature:read`, and answer by
  calling the same function the real act calls. Use them constantly.

## The SDK, once

Every SDK snippet on this page assumes this preamble.

```python
from maya_sdk import Maya, governance

maya = Maya("http://localhost:5006", "d.raman", "…")

# `maya.features` defines features and loads values. The rest of the feature
# algebra lives in `governance` and is not attached to the client, so build it:
catalogue = governance.FeatureCatalogue(maya)
views = governance.FeatureViews(maya)
```

For curl, `-u d.raman:…` on every call. If you are driving the API from a
browser session instead, the session cookie is ambient authority and the CSRF
guard applies — use Basic auth from a clean client, or send the token.

---

## 1. Define a feature

### Through the interface

**Features → Define a feature** (`/features/new`), the *Primitive* panel. Name,
entity, type, owner, what it means. The form checks as you type against
`/features/check` and only enables **Define** once the check passes.

The entity is the one field people get wrong. It is what *one row is about* — a
customer, an account, a facility. Settling it later is how a per-account number
quietly becomes a per-customer one.

### Through the SDK

```python
maya.features.define(name="ebitda", entity="customer", dtype="numeric",
                     description="Trailing twelve month EBITDA",
                     owner="person/d.raman", source_system="finance.warehouse")

maya.features.define(name="debt_service", entity="customer", dtype="numeric",
                     description="Annual scheduled principal and interest",
                     owner="person/d.raman", source_system="loan.servicing")
```

### Ask before you write

`check` refuses exactly what `define` refuses, and writes nothing.

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features/check \
  -H 'Content-Type: application/json' \
  -d '{"kind": "primitive", "name": "ebitda", "entity": "customer",
       "description": "Trailing twelve month EBITDA"}'
```

```json
{"ok": 1, "kind": "primitive", "name": "ebitda", "entity": "customer",
 "dimensionality": {"shape": [], "rank": 0, "kind": "scalar", "cells": 1,
                    "detail": "a scalar: one number per row"},
 "certification": "experimental", "possible_duplicates": [],
 "detail": "'ebitda' would be a scalar on customer, landing experimental — certification is a later act, by somebody else"}
```

In the SDK that is `catalogue.check(name="ebitda", entity="customer",
description="Trailing twelve month EBITDA")`.

### Through curl

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "ebitda", "entity": "customer", "dtype": "numeric",
  "description": "Trailing twelve month EBITDA", "owner": "person/d.raman",
  "source_system": "finance.warehouse"}'
```

The SDK block above defines two features and this one defines one, which is the
sort of asymmetry that makes a walkthrough stop three sections later. Both, then
— and `monthly_revenue`, which §2 derives from:

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "debt_service", "entity": "customer", "dtype": "numeric",
  "description": "Annual scheduled principal and interest",
  "owner": "person/d.raman", "source_system": "loan.servicing"}'

curl -u d.raman:… -X POST http://localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "monthly_revenue", "entity": "customer", "dtype": "numeric",
  "description": "Revenue in the month", "owner": "person/d.raman",
  "source_system": "finance.warehouse"}'
```

```json
{"feature": {"id": "01a07372d56042fb3bea5edad925", "name": "ebitda",
  "entity": "customer", "dtype": "numeric", "owner": "person/d.raman",
  "shape": [], "components": [], "definition_version": 1,
  "certification": "experimental", "created_by": "admin"},
 "possible_duplicates": []}
```

Two fields to notice. It lands **experimental** — certification is a later act
by somebody else (section 6). And `created_by` is recorded separately from
`owner`: who made it and who is accountable for it are different facts.

---

## 2. Compute one from others

`dscr = ebitda / debt_service`. MAYA will compute this one itself, because
dividing one stored column by another is the same class of act as counting
nulls. It will **not** run a model — see the end of this section.

### The language, in one paragraph

Arithmetic, comparison, `x if c else y`, and nine functions: `abs`, `ceil`,
`exp`, `floor`, `log`, `max`, `min`, `round`, `sqrt`. Plus `event_ts`,
`ingest_ts` and `year(event_ts)`. No attribute access, no subscripting, no
comprehensions, no other calls. `GET /api/v1/expression-language` prints it.

It is small on purpose: what cannot be expressed cannot be smuggled in.

### Read it over rows first

**Features → Define a feature**, the *Derived* panel, has a **Read these rows**
box. Paste rows, see the answer per row before anything is declared.

```python
catalogue.trial(expression="ebitda / debt_service", rows=[
    {"entity_id": "C1", "event_ts": 1717200000, "ingest_ts": 1717286400,
     "ebitda": 420000, "debt_service": 300000},
    {"entity_id": "C2", "event_ts": 1717200000, "ingest_ts": 1717286400,
     "ebitda": 180000, "debt_service": 0}])
```

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features/trial \
  -H 'Content-Type: application/json' -d '{
  "expression": "ebitda / debt_service",
  "rows": [{"entity_id":"C1","event_ts":1717200000,"ingest_ts":1717286400,"ebitda":420000,"debt_service":300000},
           {"entity_id":"C2","event_ts":1717200000,"ingest_ts":1717286400,"ebitda":180000,"debt_service":0}]}'
```

```json
{"expression": "ebitda / debt_service", "inputs": ["debt_service", "ebitda"],
 "rows": [
   {"row": 1, "entity_id": "C1", "value": 1.4, "refused": 0,
    "knowable_at": 1717286400, "clock_moved": 0},
   {"row": 2, "entity_id": "C2", "value": null, "refused": 0,
    "detail": "the arithmetic has no answer for this row; on_error says record a null",
    "knowable_at": 1717286400, "clock_moved": 0}],
 "nulls": 1, "refused": 0, "detail": "2 rows, 1 with no answer"}
```

C2 has no debt service. Division by zero is a **null, not a failure** — one bad
row must not fail a materialisation of a million. If you would rather it stopped,
say `"on_error": "refuse"` and the same row comes back `"refused": 1` with
*"a real materialisation would stop here"*.

`knowable_at` is the other thing this box is for. `ingest_ts(Z) = max(ingest_ts
of the inputs)` — you did not know the ratio before you knew both halves. Add
`"ebitda__ingest_ts": 1719878400` to a trial row and watch it move:

```json
{"row": 1, "value": 1.4, "knowable_at": 1719878400, "clock_moved": 1}
```

### Declare it

```python
maya.features.derive(name="dscr", expression="ebitda / debt_service",
                     dtype="numeric", description="Debt service coverage ratio",
                     owner="person/d.raman")
```

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
  "name": "dscr", "expression": "ebitda / debt_service",
  "dtype": "numeric", "description": "Debt service coverage ratio"}'
```

```json
{"name": "dscr", "expression": "ebitda / debt_service",
 "inputs": ["debt_service", "ebitda"], "evaluator": "internal",
 "on_error": "null", "definition_version": 1,
 "digest": "sha256:7af3c039fa33ee4c1ba77b1b4a88fe832c71d40d06120781042ac94578f96068"}
```

The inputs came from the parse, not from you. Corrections are new definition
versions, not edits.

### When MAYA cannot compute it

An expression needing a library, external data or a model is `external`. MAYA
keeps the definition — that is what lineage and the leakage check run on — and
the values arrive by materialisation instead. Because it cannot parse such an
expression, **you declare the inputs**:

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
  "name": "revenue_vol", "expression": "numpy.std(rolling(monthly_revenue, 12))",
  "dtype": "numeric", "description": "Twelve month revenue volatility",
  "evaluator": "external", "inputs": ["monthly_revenue"],
  "note": "computed in the feature pipeline; MAYA records the definition"}'
```

```json
{"name": "revenue_vol", "expression": "numpy.std(rolling(monthly_revenue, 12))",
 "inputs": ["monthly_revenue"], "evaluator": "external", "definition_version": 1}
```

Leave the inputs out and you get the reason rather than a bare no:

```json
{"error": "feature_refused",
 "detail": "'revenue_vol' is external and MAYA cannot parse its expression, so it must declare the features it reads — without them there is no lineage and no leakage check, which is the whole reason the definition is kept"}
```

`maya.features.derive` does not carry `evaluator` or `inputs` yet; for an
external definition call `maya.call("POST", "/derived-features", json={…})`.

Two more refusals worth meeting once, both from `check`, both free:

```
'that' is not one of the functions this language provides: abs, ceil, exp, floor, log, max, min, round, sqrt
undefined inputs: turnover; a derived feature can only read features the catalogue knows about
```

---

## 3. Load values

A **view** is where values live. **One upload is one version**, and a version is
a namespace: loading again does not touch what an earlier version serves. That is
what makes a training set reproducible.

### Through the interface

**Features → Create a view, and load values into it** (`/features/load`).
Top form creates the view. Below it, two ways in: **Choose one → Load the file**
for CSV, NDJSON, Parquet or Arrow, and **Or paste rows → Load these rows** for
JSON lines or CSV typed straight in. Every version of every view is listed
underneath with links to pull it back out as Parquet or Arrow.

### Create the view

```python
maya.features.create_view(name="sb_financials", entity="customer",
                          owner="person/d.raman",
                          features=["ebitda", "debt_service"],
                          description="Quarterly financials for small-business borrowers")
```

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_financials", "entity": "customer", "owner": "person/d.raman",
  "features": ["ebitda", "debt_service"],
  "description": "Quarterly financials for small-business borrowers"}'
```

### Paste rows

C1's Q2 figure, and the restatement that arrived on 15 September. Same
`event_ts`; different `ingest_ts`.

```python
views.materialise("sb_financials", rows=[
    {"entity_id": "C1", "event_ts": 1717200000, "ingest_ts": 1717286400,
     "ebitda": 420000, "debt_service": 300000},
    {"entity_id": "C1", "event_ts": 1717200000, "ingest_ts": 1726358400,
     "ebitda": 310000, "debt_service": 300000}])
```

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/feature-views/sb_financials/materialise \
  -H 'Content-Type: application/json' -d '{
  "rows": [
    {"entity_id":"C1","event_ts":1717200000,"ingest_ts":1717286400,"ebitda":420000,"debt_service":300000},
    {"entity_id":"C1","event_ts":1717200000,"ingest_ts":1726358400,"ebitda":310000,"debt_service":300000}]}'
```

```json
{"version": 1, "features": ["debt_service", "ebitda"], "delta_version": 0,
 "valid_time_column": "event_ts", "ingest_time_column": "ingest_ts",
 "row_count": 2,
 "quality_report": {"debt_service": {"null_rate": 0.0, "distinct": 1},
                    "ebitda": {"null_rate": 0.0, "distinct": 2}}}
```

The null rate per column comes back with the load. It is the number nobody looks
at until it is 40%.

### Upload a file

Same endpoint for every format; the content type says which. CSV is accepted on
the way **in** only — it cannot carry a type, so MAYA will never write one.

```
entity_id,event_ts,ingest_ts,ebitda,debt_service
C3,1717200000,1717286400,96000,60000
```

```python
maya.features.load("sb_financials", "q2.csv")   # media type from the extension
```

```bash
printf 'entity_id,event_ts,ingest_ts,ebitda,debt_service\nC3,1717200000,1717286400,96000,60000\n' \
  > q2.csv

curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/feature-views/sb_financials/data \
  --data-binary @q2.csv -H 'Content-Type: text/csv'
```

```json
{"version": 2, "row_count": 1, "uploaded_rows": 1,
 "columns": ["ebitda", "debt_service"],
 "detail": "1 rows materialised as sb_financials v2"}
```

Version 2. Version 1 still serves exactly the bytes it served before.

### The refusal you will meet

Pasting a row without both clocks:

```json
{"error": "feature_refused",
 "detail": "row is missing 'ingest_ts'; feature rows carry two clocks — event_ts (when it was true) and ingest_ts (when we learned it)"}
```

Uploading a file without the column:

```json
{"error": "feature_refused",
 "detail": "the upload is missing ingest_ts. feature rows carry two clocks — event_ts (when the fact was true) and ingest_ts (when the platform learned it) — and an entity key; without them the rows cannot be assembled point-in-time, and a set built from them could not be shown free of leakage"}
```

It is refused here, at the upload, where it is still fixable — rather than two
layers later during assembly, where it is not.

---

## 4. The two clocks

This is the idea the whole feature platform is built on. A training row may read
only what was **true** by the moment of the decision, and **known** by then too.

    AsOf(R, ℓ, a) = the latest row with event_ts ≤ ℓ and ingest_ts ≤ min(ℓ, a)

`ℓ` (`label_ts`) is the decision moment. `a` (`as_of`) is when the set was
assembled. The `min` is the reproducibility law: every `a ≥ ℓ` gives the same
answer, so a row built the day its label matured and the same row rebuilt a year
later are identical, however many restatements landed in between.

### Through the interface

**Features → Ask a point-in-time question** (`/features/point-in-time`). Pick the
view and version, type the decision moment and the assembly moment, optionally
one entity, and press **Ask**. Every candidate row comes back with a verdict and
which clock refused it.

### Ask it

C1's figure was restated on 15 September. A model trained on decisions made on
**1 July** must not see it.

```python
views.as_of("sb_financials", version=1,
            label_ts=1719792000,     # 2024-07-01, the decision
            as_of=1735689600,        # 2025-01-01, when we are assembling
            entity_id="C1")
```

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/feature-views/sb_financials/versions/1/as-of \
  -H 'Content-Type: application/json' \
  -d '{"label_ts": 1719792000, "as_of": 1735689600, "entity_id": "C1"}'
```

```json
{"knowable_by": 1719792000,
 "entities": [{"entity_id": "C1",
   "candidates": [
     {"event_ts": 1717200000, "ingest_ts": 1717286400, "admissible": 1,
      "detail": "true by the decision moment and known by it — the latest such row is the one that is read"},
     {"event_ts": 1717200000, "ingest_ts": 1726358400, "admissible": 0,
      "refused_by_event_clock": 0, "refused_by_ingest_clock": 1,
      "detail": "refused: it was not yet known at min(label_ts, as_of) — the platform learned it later than the decision"}],
   "read": {"entity_id": "C1", "event_ts": 1717200000, "ingest_ts": 1717286400,
            "ebitda": 420000, "debt_service": 300000}}],
 "operator": "AsOf(R, l, a) = argmax over (event_ts, ingest_ts) of { r in R : r.event_ts <= l and r.ingest_ts <= min(l, a) }"}
```

It read **420000**, the figure that existed on 1 July, not the 310000 that
replaced it in September. Nobody had to remember a flag.

Move `label_ts` to 2025-01-01 and it reads 310000 instead — correct, because by
then the restatement was known. Move it back to 2024-03-01 and both rows are
refused, with `"read": null`:

> nothing this entity holds was both true and known by then, so the feature is
> null for this row — which is an answer, not a gap to be filled

The probe is a **read**: no snapshot, no evidence, no warrant. Building a
training set out of the answer is a different act, and it lives in
[warrants and training](/tutorials/warrants-and-training).

---

## 5. Nulls and gaps

Features arrive on their own clocks — a balance monthly, a rating annually, a
price daily and never at weekends. Aligning them onto one axis and filling the
holes by a stated rule gives an engine a rectangle instead of a ragged frame.

Five rules, and **they are not equivalent**:

| rule | what it does | safe for training |
|---|---|---|
| `none` | leaves the gap | yes |
| `flat_forward` | carries the last observation forward | yes |
| `flat_backward` | carries the next observation **back** | no |
| `linear` | interpolates between the neighbours on each side | no |
| `nearest` | whichever neighbour is closer, ahead or behind | no |

### Through the interface

The point-in-time page has an **Align** panel: paste rows, pick the axis, the
fill rule, the grid and a carry limit, press **Align**. Nothing stored is
touched.

### See the stamp move

Two observations — March, known 2 March; June, known 15 September — onto a grid
of March, April, June.

```python
views.alignment_trial(
    rows=[{"entity_id": "C1", "event_ts": 1709251200, "ingest_ts": 1709337600, "ebitda": 300000},
          {"entity_id": "C1", "event_ts": 1717200000, "ingest_ts": 1726358400, "ebitda": 420000}],
    columns=["ebitda"], rule="flat_backward", grid="explicit",
    points=[1709251200, 1711929600, 1717200000])
```

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/features/alignment-trial \
  -H 'Content-Type: application/json' -d '{
  "rows": [{"entity_id":"C1","event_ts":1709251200,"ingest_ts":1709337600,"ebitda":300000},
           {"entity_id":"C1","event_ts":1717200000,"ingest_ts":1726358400,"ebitda":420000}],
  "columns": ["ebitda"], "axis": "event_ts", "rule": "flat_backward",
  "grid": "explicit", "points": [1709251200, 1711929600, 1717200000]}'
```

```json
{"rows": [
   {"entity_id": "C1", "event_ts": 1709251200, "ingest_ts": 1709337600, "ebitda": 300000},
   {"entity_id": "C1", "event_ts": 1711929600, "ingest_ts": 1726358400, "ebitda": 420000},
   {"entity_id": "C1", "event_ts": 1717200000, "ingest_ts": 1726358400, "ebitda": 420000}],
 "filled": 1, "point_in_time_safe": false, "looks_ahead": 1,
 "means": "carry the next observation back — reaches into the future",
 "detail": "1 entities on a grid of 3 points; 1 values filled by flat_backward. this rule fills from observations later than the gap, so the filled values carry the ingest time at which they actually became knowable — a point-in-time read at the grid point excludes them, which is correct and is the point"}
```

**That middle row is the whole design.** The April grid point got June's value —
and with it June's ingest stamp, `1726358400`. Run the same rows through
`flat_forward` and the April row comes back with `ebitda: 300000` and
`ingest_ts: 1711929600`, the grid point itself: nothing later was used, so
nothing later is stamped.

So the three look-ahead rules are **not refused anywhere**, and there is no flag
to forget. They are stamped honestly, and section 4's operator then throws the
back-filled April value out of any training row whose `min(label_ts, as_of)`
falls before 15 September. The leakage is not caught by a check; it is made
arithmetically impossible to hide. Use them freely for drawing a curve or for an
explicitly retrospective backtest — that is what they are right for.

### Carry limits

A balance from eighteen months ago is not this month's balance. Add
`"carry_limit": 2592000` (thirty days) to the same call with `flat_forward`:

```json
{"rows": [{"entity_id": "C1", "event_ts": 1711929600, "ingest_ts": 1711929600,
           "ebitda": null}],
 "filled": 0, "carried_beyond_limit": 1,
 "detail": "1 entities on a grid of 3 points; 0 values filled by flat_forward; 1 left empty because carrying them further would have turned a stale observation into a fabricated one"}
```

(One row of three shown.)

### Filling nulls, as opposed to gaps

A gap is a missing *row*; a null is a missing *value* in one. Nulls are filled by
a **retrieval policy**, which is attached to the feature so that two models do
not each decide differently. Six strategies: `keep`, `constant`, `zero`, `mean`,
`median`, `most_frequent`.

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "utilisation", "entity": "customer", "dtype": "numeric",
  "description": "Revolver utilisation", "owner": "person/d.raman",
  "defaults": {"fill": {"utilisation": {"strategy": "median"}},
               "align": {"axis": "event_ts", "rule": "flat_forward"}}}'
```

Get it wrong and the check says so, free, before anything is written — this is
a *different* call from the one above, with `backfill` where a strategy belongs:

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features/check \
  -H 'Content-Type: application/json' -d '{
  "kind": "primitive", "name": "utilisation_bad", "entity": "customer",
  "description": "Revolver utilisation",
  "defaults": {"fill": {"utilisation_bad": {"strategy": "backfill"}}}}'
```

```json
{"error": "feature_refused",
 "detail": "fill of 'utilisation_bad': 'backfill' is not a strategy; expected one of keep, constant, zero, mean, median, most_frequent"}
```

The statistics are fitted on what was **observed** and at a stated moment — a
median over the whole column is the median it turned out to be, and using it on a
row from three years ago puts the future into the past. The order is fit, then
fill, then normalise. Where the policy is actually applied to data is a
featureset read: [featuresets](/tutorials/featuresets).

---

## 6. Lineage and certification

Lineage is the transitive closure, both ways, and it is the reason a primitive
cannot be retired while something derives from it.

```python
maya.features.lineage("dscr")
```

```bash
curl -u d.raman:… http://localhost:5006/api/v1/derived-features/dscr/lineage
```

```json
{"feature": "dscr", "rests_on": ["debt_service", "ebitda"], "depended_on_by": []}
```

Ask the same of an input and the answer is the other direction:

```json
{"feature": "ebitda", "rests_on": [], "depended_on_by": ["dscr"]}
```

Both directions are on the feature's own page, `/feature/dscr`, along with the
view versions carrying its values and each one's null rate.

**Certification is a meet.** A derived feature is as certified as its *weakest*
input and no more — deriving from an uncertified feature does not launder it. The
chain is `experimental ≤ reviewed ≤ certified ≤ gold`. Certifying is a separate
act by a separate person; a model developer cannot certify their own feature.

```bash
curl -u s.iqbal:… -X POST \
  'http://localhost:5006/api/v1/features/ebitda/certify?level=certified'
```

`check` shows you the meet before you declare anything, with each input beside
it so the weak one is visible:

```json
{"name": "dscr2", "inputs": ["debt_service", "ebitda"],
 "certification": "certified",
 "certification_of_inputs": [{"name": "debt_service", "certification": "certified"},
                             {"name": "ebitda", "certification": "certified"}],
 "certification_order": ["experimental", "reviewed", "certified", "gold"]}
```

Two things to plan around.

The meet is taken **when the derived feature is defined**, not recomputed
afterwards. Certify the inputs first, or define the derivation again once they
have been.

And the levels you may *set* are a shorter list than the ones the meet ranks
over:

```json
{"error": "feature_refused",
 "detail": "unknown certification level 'gold'; expected one of experimental, certified, deprecated"}
```

---

## 7. Composition and inheritance

Combining several features into one, and inheriting from a single parent and
adding to it, are the same act with a different number of parents. So there is
one mechanism, and inheritance is the one-parent case.

**The rule is a left-to-right fold in which the rightmost wins**, and the
object's own operations are applied last of all — a thing's own declarations beat
anything it inherited, because otherwise naming a parent would be an act of
surrender.

### Components

A feature is not always a number. `shape: [3]` with `components: ["1y", "3y",
"5y"]` is a curve, and the component names let a child talk about a tenor rather
than about an index.

**Features → Define a feature**, the *Composed* panel, takes the parents in fold
order and the operations, and previews the result before you commit.

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "sector_spread_curve", "entity": "customer", "dtype": "numeric",
  "description": "Sector credit spread by tenor", "owner": "person/d.raman",
  "shape": [3], "components": ["1y", "3y", "5y"]}'

curl -u d.raman:… -X POST http://localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "sector_spread_curve_long", "entity": "customer", "dtype": "numeric",
  "description": "Sector spread curve with a ten-year point", "owner": "person/d.raman",
  "composes": [{"name": "sector_spread_curve"}],
  "operations": [{"op": "add", "name": "10y", "value": {"dtype": "numeric"}}]}'
```

Ask what it actually is — not what its row says, what its row plus its parents
plus its own operations say:

```bash
curl -u d.raman:… \
  http://localhost:5006/api/v1/features/sector_spread_curve_long/resolved
```

```json
{"components": ["1y", "3y", "5y", "10y"],
 "dimensionality": {"shape": [4], "rank": 1, "kind": "vector", "cells": 4,
   "detail": "a vector of 4 — 4 numbers per row, the first axis named 1y, 3y, 5y, 10y"},
 "provenance": {
   "1y": {"from": "sector_spread_curve", "overrode": null},
   "3y": {"from": "sector_spread_curve", "overrode": null},
   "5y": {"from": "sector_spread_curve", "overrode": null},
   "10y": {"from": "sector_spread_curve_long (add)", "overrode": null}}}
```

The shape followed the components. `provenance` answers the question a reviewer
actually asks about an inherited thing — not *what does it have* but *which of
these did somebody here decide*. The SDK reads it with
`catalogue.resolved("sector_spread_curve_long")`.

### Every operation is total

`add`, `drop`, `override` — and each is refused when it would do nothing, because
an operation that silently did nothing leaves a child differing from what its
author believed they wrote.

```
operation 0: cannot drop '30y' — none of the parents has it. a drop that quietly
does nothing leaves a child differing from what its author believed they wrote

operation 0: cannot add '3y' — a parent already has it. say 'override' if
replacing it is what is meant; the two read differently to a reviewer and should
```

### Policy inherits by the same fold

Define `utilisation_capped` composing `utilisation` (section 5) and overriding
only the fill:

```json
{"policy": {"fill": {"utilisation": {"strategy": "keep"}},
            "align": {"axis": "event_ts", "rule": "flat_forward"}},
 "decided_by": {"fill": {"utilisation": "utilisation_capped"},
                "align": {"axis": "utilisation", "rule": "utilisation"}},
 "precedence": "parents left to right, then the object, then the request; the rightmost wins"}
```

The child changed the fill and kept the parent's alignment, and `decided_by`
names which layer decided each. The same fold governs featureset slots —
[featuresets](/tutorials/featuresets).

---

## 8. Can documents be attached to a feature?

Yes, with one honest caveat.

`feature` is one of the six things a document can be *about* — "one governed
signal — its business definition, the argument for how it is computed". File one
by naming the subject:

A document about a feature still hangs off a **model**, because that is what a
reviewer opens; `subject_type` says what it is really about. Pass `model_level`
so the register knows you meant the model rather than a version it would
otherwise have to pick — without it the answer is
`no_version_to_attach_to: … a document filed at model level has to say so`,
which is the register declining to guess.

```python
maya.attachments.attach("maya://model/credit.pd.smallbiz", "ebitda.md",
                        kind="other", title="EBITDA: source and definition",
                        model_level=True,
                        subject_type="feature", subject_id="ebitda")
```

```bash
printf '# EBITDA\n\nTrailing twelve months, from the finance warehouse.\n' > ebitda.md

curl -u d.raman:… -X POST http://localhost:5006/api/v1/attachments \
  -F 'urn=maya://model/credit.pd.smallbiz' -F 'kind=other' \
  -F 'title=EBITDA: source and definition' -F 'model_level=1' \
  -F 'subject_type=feature' -F 'subject_id=ebitda' \
  -F 'file=@ebitda.md;type=text/markdown'
```

```json
{"id": "01a0737432080746d77bcbbcd645", "subject_type": "feature",
 "subject_id": "ebitda", "kind": "other",
 "title": "EBITDA: source and definition", "media_type": "text/markdown",
 "digest": "sha256:250947316dde1605aad442d9367ca71fcf6c2de9f7941f8f76e3ed4b4c7e80e6",
 "text_indexed": true, "state": "attached", "reviewed_by": null}
```

The caveats, plainly:

- **An attachment still hangs off a model URN.** There is no way to file a
  document about a feature that no model uses.
- **You cannot list documents by subject over HTTP.** `GET /api/v1/attachments`
  is addressed by model URN, so you find a feature's document by listing the
  model's and filtering on `subject_type`. There is no card for it on
  `/feature/{name}` either. This is a known gap, not something to work around
  with an endpoint that does not exist.
- **There is no `data_dictionary` kind.** The nine kinds are fixed; `other` is
  the honest answer for a feature note, and `GET /api/v1/attachment-kinds`
  prints them with their meanings.

Filing is not accepting: the document lands `attached` and somebody else has to
`review` it. See [documentation](/help/documentation).

---

## What you can now do on Monday

- Declare features before they have values, and check the declaration for free.
- Compute a ratio in MAYA, and record — rather than hide — the one you compute
  outside it.
- Load a file or paste rows, knowing one upload is one immutable version.
- Answer *what did we actually know when that decision was made* from real rows,
  in one call.
- Fill gaps with any rule you like, because the ingest stamp keeps you honest.

Next: [featuresets](/tutorials/featuresets), which names a set of these features
as the schema a model is defined over; then [warrants and
training](/tutorials/warrants-and-training), where an assembly turns a point-in-
time read into a snapshot a fit can pin. If you have not registered a model yet,
start at [defining a model](/tutorials/defining-a-model). The whole chain in one
sitting is [end to end](/tutorials/end-to-end), and the packaged result is the
[model package](/tutorials/model-package).

Reference: [features and the two clocks](/help/features-and-two-clocks),
[featuresets and parameters](/help/featuresets-and-parameters),
[API reference](/help/api-reference), [glossary](/help/glossary).

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE.
*Not legal, regulatory or financial advice — see NOTICE §4.*
