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

## Loading values from a file

The features page takes a file directly. **CSV, JSONL, Parquet or Arrow** — the
format comes from the extension, and the browser posts the bytes to the same
endpoint an execution engine uses, so the interface exercises the contract
rather than a convenience beside it.

| Format | When |
|---|---|
| `.csv` | What a person usually has. Types are inferred, because a CSV cannot carry any |
| `.jsonl` / `.ndjson` | One object per line; streams, and anything can produce it |
| `.parquet` | Columnar and typed; the right choice for anything large |
| `.arrow` | Streaming IPC, zero-copy; what an engine should send |

**CSV is read and never written.** A CSV cannot carry a type, so a feature
exported as one comes back as text and both clocks come back as strings. Reading
one is worth it because refusing would mean somebody converts by hand, and the
conversion is where the mistakes live. Writing one would hand back something
weaker than what went in.

Every row must carry `entity_id`, `event_ts` and `ingest_ts`. A file missing the
second clock is refused rather than stamped with the upload time — a value whose
arrival is guessed cannot be read point-in-time, and that is precisely how the
future gets into a training set.

**The whole upload becomes one feature view version.** A version is what a
featureset pins, and half a version is not something anybody can pin.

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


## Moving feature values in and out

Everything else in this platform moves small documents: a warrant, a contract, a
finding. Feature values are not small. A featureset over a few million entities
is the ordinary case, and an API that turns it into JSON objects — one dictionary
per row, keys repeated on every line — spends most of its time and nearly all of
its memory on punctuation.

So the rule here is different from everywhere else: **nothing is materialised
whole.** Reads iterate Arrow record batches straight off the Delta files and
write them out as they go; writes parse a batch at a time and append. Peak memory
is one batch, not one dataset.

A batch is sized by **cells rather than rows**, because sixteen thousand rows of
six columns is a few megabytes and sixteen thousand rows of two thousand columns
is not. A wide table is read in narrower slices, so the claim holds for both
shapes.

### Four formats, and the choice is not cosmetic

| Format | Media type | When |
|---|---|---|
| `arrow` | `application/vnd.apache.arrow.stream` | From an execution engine. Zero-copy, and the only one that is genuinely incremental in both directions |
| `parquet` | `application/vnd.apache.parquet` | When the data is going to disk. Columnar and compressed — typically less than half of NDJSON for the same rows |
| `ndjson` | `application/x-ndjson` | The lowest common denominator. Streams, and anything can read it |
| `json` | `application/json` | For a page, not a job. Hard-capped, because a browser asking for ten million rows is a mistake and answering it is not a kindness |

Parquet is assembled to a temporary file and streamed from it, because a Parquet
file's footer holds the row-group index and cannot be written until the last row
is known. The file still never holds more than one batch in memory on the way in.

### Copying a version out

```bash
curl -u you:… -o sb_credit.parquet \
  'http://localhost:5006/api/v1/feature-views/sb_credit/versions/1/data?format=parquet'
```

The read uses the **pinned** Delta version, not whatever the namespace currently
holds. What comes out is what that version *is*, not what the path has since
become.

A whole featureset version comes out joined on the entity key:

```
GET /api/v1/featuresets/{name}/versions/{n}/data?format=parquet
```

An engine that wants to pull a large set in parallel should read `/parts`
instead, which names each namespace and the Delta version it is pinned at, and
fetch them itself rather than waiting on a join.

### Loading values in

```bash
curl -u you:… -X POST \
  -H 'Content-Type: application/vnd.apache.parquet' \
  --data-binary @sb_credit.parquet \
  http://localhost:5006/api/v1/feature-views/sb_credit/data
```

**The whole upload becomes one version**, because a version is what a featureset
pins and half a version is not something anybody can pin.

Every row carries `entity_id`, `event_ts` and `ingest_ts`. An upload missing
either clock is refused *here*, at the upload, rather than accepted to be helpful
and failed two layers later during assembly — which is where it stops being
fixable. A body whose bytes and declared content type disagree is refused too,
rather than guessed at.

### Through the interface

The **Features** page defines primitives and derived features and lists what each
view holds. A view's own page uploads a file and offers each version in every
format. The **Featuresets** page declares a schema; a featureset's page fills it,
rolls it forward to newer view versions with a diff of what moved, and shows each
version's pins alongside whether anything underneath them has been restated.


## A feature is not always a number

A yield curve is a vector. A correlation structure is a matrix. A scenario grid
is a tensor. Storing all of them as "numeric" and hoping the consumer knows
better is how a model receives ten tenors where it expected eleven and produces
an answer rather than an error.

So a feature carries a **shape**, and along its first axis optional **component
names**:

```json
{"name": "usd_curve", "entity": "book_id", "dtype": "numeric",
 "shape": [10],
 "components": ["1m","3m","6m","1y","2y","3y","5y","7y","10y","30y"]}
```

| Shape | Kind |
|---|---|
| `[]` | scalar — one number per row |
| `[10]` | vector |
| `[10, 10]` | matrix |
| `[5, 10, 10]` | tensor |

**The component order is the axis order.** A curve whose tenors came back
alphabetically would be a different curve, and one nobody would notice was wrong.

The names are what make composition mean something. *Add a tenor*, *drop the
50-year point*, *override the 3-month with an OIS-based one* are operations on
named things; on an anonymous array they are operations on an index, and an index
is not a meaning.

A declared shape is **checked against the values** that arrive. A shape nobody
verifies is a comment.

## Composing features and featuresets

Inheriting from one parent and combining several are the same operation with a
different number of parents, so there is one mechanism:

> **A left-to-right fold in which the rightmost wins. An object's own operations
> are applied last, and are therefore the most prominent of all.**

Nothing else would be defensible. If a parent could override a child, naming a
parent would be an act of surrender.

That rule is not a convention. Merge-with-rightmost-wins is **associative** and
the empty map is its **identity**, so composition is a *monoid* — which is
exactly why "a combination of features is a feature" is a true statement rather
than an aspiration.

### Inheriting

```json
{"name": "usd_curve_extended",
 "composes": [{"name": "usd_curve"}],
 "operations": [
   {"op": "add",      "name": "50y", "value": {"dtype": "numeric"}},
   {"op": "drop",     "name": "1m"},
   {"op": "override", "name": "3m",  "value": {"dtype": "numeric",
                                               "source": "OIS"}}]}
```

`GET /api/v1/features/usd_curve_extended/resolved` returns what it *actually is*
— components, shape, lineage and, for each component, who decided it:

```json
{"components": ["3m","6m","1y","2y","5y","10y","30y","50y"],
 "shape": [8],
 "provenance": {"3m": {"from": "usd_curve_extended (override)",
                       "overrode": "usd_curve"}}}
```

Working that out is MAYA's job. The row holds what the object *declares*;
resolution happens on read.

### Combining

```json
{"name": "blended", "composes": [{"name": "usd_curve"},
                                 {"name": "gbp_curve"}]}
```

Left to right, so `gbp_curve` wins any component both define — and the
provenance says so.

### A worked example

`usd_curve` has five tenors and has been sealed. A child adds one, drops one and
replaces one:

```json
{"name": "usd_curve_plus",
 "composes":   [{"name": "usd_curve"}],
 "operations": [{"op": "add",      "name": "30y", "value": {"dtype": "numeric"}},
                {"op": "drop",     "name": "1m"},
                {"op": "override", "name": "3m",  "value": {"dtype": "numeric",
                                                            "source": "OIS"}}]}
```

| parent | operations | result |
|---|---|---|
| 1m, 3m, 1y, 5y, 10y | add 30y · drop 1m · override 3m | 3m, 1y, 5y, 10y, 30y |

`GET /api/v1/features/usd_curve_plus/resolved` returns the components **and
where each came from** — `3m` reports that it overrode `usd_curve`. The row
stores what this feature *declares*; resolving it is MAYA's job.

Two featuresets combine the same way, and the order is what settles a clash:

```json
{"name": "sme_retail", "composes": [{"name": "retail_core"},
                                    {"name": "sme_core"}]}
```

Both parents declare `turnover`. `sme_core` is named second, so its three-year
average is what the set holds — and the resolved set says so, slot by slot.

### Every operation is total

| Refused | Because |
|---|---|
| `drop` of something absent | a drop that quietly does nothing leaves a child differing from what its author wrote |
| `add` of something present | say `override`; the two read differently to a reviewer and should |
| `override` of something absent | say `add` |
| a cycle | there is no fixed point to resolve to |
| composing an ephemeral parent | it resolves today and dangles tomorrow |
| composing something that does not exist | caught now, not on first read |

### Modifying something other things are built on

Four ways, and which one applies depends on whether the thing is sealed:

| | |
|---|---|
| **Amend it** | changes the definition and advances its version. Allowed while the feature is open |
| **Seal it** | no amendment, no further versions — and still composable |
| **Compose a child** | the way to change a sealed thing, where a reviewer sees it |
| **Roll forward** | for a featureset: re-resolve to the newest view versions, with a diff |

**And if a parent is amended anyway, the child says so.** A composition records
the parent's definition version at the moment it resolved, so a parent that has
since moved shows up as *drift* on every child that reads it:

```json
{"drift": [{"parent": "usd_curve", "composed_against": 1, "now_at": 3,
            "sealed": false}]}
```

Not a failed read — a child whose parent has moved is something to be told
about, not something that should stop working. But it is never silent, because a
stable name over moving contents is the failure this platform was built around.

Which is why sealing and composing are the same idea from two sides: **a sealed
parent cannot drift**, because the amendment that would move it is refused. That
turns a promise about stability into a property of the object.

## Sealing

A **sealed** feature or featureset is final. No amendment, no further versions, no
change of owner — and **it can still be composed from**.

That combination is the whole point. Sealing is what makes a parent safe to build
on, because a sealed parent is one that cannot move. Evolution does not stop; it
moves to a child, where it is visible.

> **409** — 'usd_curve' was sealed by person/s.iqbal and cannot be amended.
> *Compose a new feature from it instead — that is what sealing is for.*

`feature:seal` is its own permission, held by the second line. Whoever may define
a thing is not automatically who may end it. Breaking a seal is
administrators-only and needs a reason; both acts stay in the chain.

## Ephemeral features and featuresets

Created for one purpose, read, and destroyed — by TTL, or on request.

```json
{"name": "scratch_pull", "ephemeral": true, "ttl_days": 0.5}
```

Two rules follow, and both are refusals:

- **Nothing may depend on one.** Composing from something that will be destroyed
  leaves a child that resolves today and dangles tomorrow, and a dangling pin is
  worse than no pin because it looks like one.
- **It cannot be sealed.** Permanent and temporary are not two flags that happen
  to be set; one of them is wrong.

Longer than thirty days is refused: something needed for longer is not ephemeral,
and declaring it so is a way of avoiding the governance a durable object owes.

**Destruction is recorded.** The rows go and the evidence stays, with the version
digests. A throwaway featureset somebody pulled a million rows through is exactly
what an examiner asks about, and *"it was ephemeral"* is not an answer.

## Who made it, and who answers for it

Two facts, kept apart. **`created_by`** is history and never changes.
**`owner`** is a responsibility and can be transferred, to somebody named, by
somebody entitled, with the handover in the chain.

An owner field that quietly becomes a leaver's username is how a model ends up
accountable to nobody.


## What MAYA does to values on the way out

Filling gaps, normalising and aligning onto an axis are decisions somebody has to
make. Leaving them to every caller has two failure modes: either each consumer
decides differently and the same feature means different things in two models, or
the awkward columns get skipped and somebody downstream turns the nulls into
zeros without saying so.

So the decision can be attached to the feature or featureset as its **default
behaviour**, and a request may override it:

```json
{"defaults": {
   "align":     {"axis": "event_ts", "rule": "flat_forward"},
   "fill":      {"dscr": "median", "utilisation": "zero"},
   "normalise": {"dscr": "zscore"}}}
```

**The precedence is the composition rule again**, deliberately:

```
parents (left to right)  →  the object's own defaults  →  the request
```

Merged **section by section and column by column**, so a parent that fills three
columns and a child that normalises one end up doing both. Replacing the section
wholesale would silently drop the parent's decision and the child's author would
never see it go. The resolved policy comes back saying which layer decided each
column.

### Point-in-time normalisation

Statistics are fitted from rows where `event_ts <= as_of AND ingest_ts <= as_of`,
and from nothing else.

A z-score fitted over the whole column encodes what the mean *turned out* to be,
including the part of the history that had not happened when the row was scored.
That is leakage, and it is invisible afterwards because the column looks
unremarkable. So:

> **A request with no `as_of` is refused.** The leaky answer is the one somebody
> would get by accident, so it is the one that must not be the default.

`zscore` · `minmax` · `robust` (median/IQR) · `rank`. Vectors and tensors
normalise elementwise. Fewer than thirty observations is refused — a statistic on
fewer is a guess with a decimal point. A constant column returns zeros and says so
rather than dividing by zero quietly.

**The fitted statistics come back with the data.** Whoever scores one row
tomorrow has to apply the same transform, and a reviewer asking what was done to
a column deserves a number rather than a method name.

### Missing values

Null, NaN and infinity arrive by different routes — no observation, a division
with no answer, an overflow — and are equally unusable, so all three count as
missing. A NaN is never folded into a statistic: doing so makes the statistic a
NaN, which then propagates through everything it touches.

`keep` · `constant` · `zero` · `mean` · `median` · `most_frequent`. The last three
fit a statistic and so need an `as_of`, for the same reason.

**The fill rate is part of the answer**, and loud past a fifth of the column:

> 40 of 100 values (40.0%) filled with zero — past a fifth of the column, what
> comes back is mostly invention, and a model will train on it without complaint.

### The order, and why it is the order

> **Fit on observed → fill → normalise.**

Fitting the normalisation *after* filling would shrink the spread by exactly the
amount that was invented, because every filled cell sits at the centre and pulls
the variance down. So the statistics are fitted on what was observed and then
applied to everything, including what was filled.

### Aligning onto an axis

Features arrive on their own clocks — a balance monthly, a rating annually, a
price daily and not at weekends. Aligning them onto one axis and filling the gaps
hands an execution engine a rectangle instead of a ragged frame:

```json
{"align": {"axis": "event_ts", "rule": "flat_forward",
           "carry_limit": 7776000}}
```

| Rule | Fills from | Safe for training |
|---|---|---|
| `flat_forward` | the last observation | **yes** |
| `flat_backward` | the next observation | no |
| `linear` | both neighbours | no |
| `nearest` | whichever is closer | no |

The last three reach into the future. They are the right answer for drawing a
curve, for an explicitly retrospective backtest, for showing a history to a
person — and wrong for training a model.

**They are not refused. They are stamped honestly.** A value derived from a later
observation inherits that observation's `ingest_ts`, because that is genuinely
when it became knowable:

```
grid point  t=1   value 400.0   ingest_ts 3.0   ← filled from the observation at t=3
```

An ordinary point-in-time read at `as_of = 1` then excludes it, by the same rule
that governs everything else here, with nobody having to remember a flag. The
leakage is not caught by a check; it is made arithmetically impossible to hide.

A **carry limit** bounds how far an observation may travel. A balance from
eighteen months ago is not this month's balance, and carrying it forever turns a
stale observation into a fabricated one. And interpolation will not
*extrapolate* from one side under the name of interpolating: that is a different
act with a different error, and doing it silently would hide which was done.

### Asking for it

```bash
curl -u you:… -X POST \
  localhost:5006/api/v1/featuresets/rates_core/versions/1/prepared \
  -H 'Content-Type: application/json' -d '{
    "as_of": 1767139200,
    "align": {"axis": "event_ts", "rule": "flat_forward"},
    "fill": {"dscr": "median"},
    "normalise": {"dscr": "zscore"}}'
```

The response carries the rows, the policy that was actually applied, what each
step did, and the statistics it fitted. `GET /api/v1/retrieval` publishes the
whole vocabulary and the rules it obeys.
