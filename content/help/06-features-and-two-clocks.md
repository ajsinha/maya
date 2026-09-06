---
title: Features and the two clocks
slug: features-and-two-clocks
section: Features and data
order: 60
icon: clock-history
summary: One question — what did we know then — answered by three mechanisms; two clocks on every row, a point-in-time read that saturates at the label, and feature view versions that never move.
audience: Engineers, Data scientists
---

# Features and the two clocks

Everything on this page serves one question: **what did we know, at the moment
the decision was made?**

A store with one clock cannot answer it. Two clocks make it *expressible*; the
point-in-time read makes the answer *reproducible*; pinned view versions keep it
*true* after everybody has moved on.

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

Every feature row carries both:

| Column | Meaning |
|---|---|
| `event_ts` | **Valid time** — when the fact was true in the world |
| `ingest_ts` | **Transaction time** — when the platform learned it |

The restatement is *two rows*, not an update:

```json
{"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 1.20}
{"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0, "dscr": 0.40}
```

Same valid time. Different transaction times. Nothing was overwritten, so all
three questions remain answerable:

- *What was true on 31 March?* → depends when you ask.
- *What did we know on 20 May?* → 1.20.
- *What do we know now?* → 0.40.

A store with one clock can answer only the third, and will answer it to a
question that asked the second.

### Rows without both clocks are refused

```bash
POST /api/v1/feature-views/sb_financials/materialise
```

```
row is missing 'ingest_ts'; feature rows carry two clocks —
event_ts (when it was true) and ingest_ts (when we learned it)
```

**409**, and deliberately unhelpful to whoever is in a hurry. The alternative —
defaulting `ingest_ts` to now — produces a store that looks fine and is silently
wrong, and the wrongness surfaces months later as unexplained model decay.

A bulk upload is checked the same way, once against the file's schema rather than
row by row:

```
the upload is missing ingest_ts. feature rows carry two clocks — event_ts
(when the fact was true) and ingest_ts (when the platform learned it) — and
an entity key; without them the rows cannot be assembled point-in-time, and
a set built from them could not be shown free of leakage
```

## The point-in-time read, and what makes it reproducible

For a training row with label timestamp `label_ts`, assembled as of `as_of`:

```
AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                { r ∈ R : r.event ≤ ℓ  ∧  r.ingest ≤ min(ℓ, a) }
```

In code:

```python
knowable_by = min(label_ts, as_of)
eligible = [r for r in records
            if r[VALID_TIME] <= label_ts and r[INGEST_TIME] <= knowable_by]
return max(eligible, key=lambda r: (r[VALID_TIME], r[INGEST_TIME]))
```

**The `min` is the whole reproducibility story**, and it is the part most
implementations get wrong. Four properties follow, each asserted over generated
data in `tests/test_laws.py::TestL10TheAsOfOperator` rather than argued in prose:

| | |
|---|---|
| **Idempotent** | reading the result again returns it |
| **Commutes with projection** | which row is admissible is decided on the clocks alone, so reading fewer columns cannot change the choice |
| **Monotone in `a`** | a later `as_of` can only *widen* what is admissible; nothing knowable stops being knowable |
| **Saturating at `ℓ`** | **every `as_of ≥ label_ts` gives the same answer** |

The fourth is the one to understand. A training row assembled the day its label
matured and the same row re-assembled a year later are **identical**, however
many restatements arrived in between. That is what makes *"reproduce this
training set"* a claim with content.

Without the `min`, a re-run would quietly *improve* on the original — the least
useful kind of reproducibility, because the numbers then agree with nothing,
including themselves.

### The worked example

Given the restatement above:

```
C1 @ event_ts=100, ingest_ts=110  →  dscr 1.20
C1 @ event_ts=100, ingest_ts=900  →  dscr 0.40   (the restatement)
```

| Assembled with | Result | Why |
|---|---|---|
| `label_ts=500, as_of=500` | **1.20** | The restatement had not arrived by t=500 |
| `label_ts=500, as_of=999` | **1.20** | Saturation. `min(500, 999) = 500`, so the restatement is still out of reach |
| `label_ts=950, as_of=999` | **0.40** | A *later label*. By t=950 the restatement was knowable |
| `label_ts=50, as_of=999` | *nothing* | No fact was true by t=50 |

Rows one and two are the point. A restatement that lands **after** the label
cannot change a row that was already settled — moving the `as_of` forward does
not move the answer, and only moving the *label* does. A single-clock store gives
0.40 for all three, and the first two are lies.

### One thing that is not yet consistent

Two places still describe the older rule, and it is worth knowing which.

The **layer 2 verifier** (below) recomputes through a different code path and
bounds ingest by `as_of` rather than by `min(label_ts, as_of)`. Where a
restatement lands between the label and the `as_of`, the verifier and the
assembler disagree by construction, and the assembly — which is the correct one —
is marked `pit_verified: false`. The plan a fit warrant carries also still
advertises `ingest_ts <= as_of` as its `pit_rule`.

Neither affects the data an assembly produces. Both are stated here rather than
left for somebody to discover from a snapshot flagged for a reason that turns out
to be the checker.

## Assembling a training set

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
read — **422**, and nothing is written:

```
assembly lacks a bound on transaction_time; without both, leakage cannot
be excluded
```

Drop the valid-time bound and you use facts from after the label — classic
leakage. Drop the transaction-time bound and you use the *restated* version of a
fact that, at the time, said something else. A warning would be ignored:
everybody under deadline pressure ignores warnings, and the resulting dataset is
indistinguishable from a correct one until the model reaches production.

### Three layers of verification

Being refused for the obvious mistake is not enough — an assembly can be wrong
for a subtler reason. So a completed one is checked three ways.

**Layer 1 — static gate.** Are both bounds declared? Is `as_of` present? Is the
spine well-formed? Cheap, and catches the common error. This is the layer that
refuses outright: a failure raises and **no snapshot is written**, which is why
layer 1 never appears in a `pit_report`.

**Layer 2 — independent recomputation.** A sample of assembled rows — **200 by
default**, stratified across label values so a rare class is not missed — is
recomputed by a *different code path*. Different in two ways, and both matter:
it is a bitemporal read against Delta rather than the in-memory join, **and** it
resolves each column on its own from that column's own binding, where the
assembler groups columns by view and reads each view once.

Verification that reuses the assembly path lets a bug hide behind itself, and
this is not hypothetical: the recomputation once walked the same view list the
same way, so a featureset binding the assembler ignored was one the verifier
could not see, and `pit_verified: true` could not be false about it.

**Layer 3 — leakage screen.** It screens every column *against the label*, so
the first thing it needs is to know which column that is. On a featureset
assembly the label sits under the slot the author named it — `defaulted_12m`,
`charged_off`, `sale_price` — and the screen takes that slot from the published
featureset version. A views-only assembly declares no label, and then there is
nothing to screen against.

Two screens, chosen per column, and it needs at least eight rows and two
distinct labels to run at all:

- A column with more than half its values distinct is treated as **continuous**
  and screened for **perfect separation** — one threshold along the sorted column
  splitting the labels cleanly.
- Anything else is screened for **purity** — every distinct value mapping to
  exactly one outcome.

Two screens rather than one, because a single purity test fires on almost every
real continuous column and a check that cries wolf is a check somebody turns off.
Both are sharper than a correlation threshold, which fires on ordinary strong
predictors.

**An empty `leakage` list is not the same as a clean one**, and the report says
which it is. `leakage_screened` is false, with the reason in `detail`, whenever
the screen could not conclude: fewer than eight rows, no label column in the
frame, one distinct label value, or — the subtle one — a **continuous** label,
where the only available test is a threshold split and a threshold split means
nothing unless the label is binary. A regression training set is therefore
reported as *unscreened*, not as clean. `label_column` names the column it ran
against.

The snapshot's `pit_report` carries `{passed, layer, checked, violations,
leakage, leakage_screened, label_column, detail}`, and `pit_verified` is false
if layer 2 or 3 failed. **The snapshot is still written** — you may need to inspect it — but it is marked, its
status travels with it, and a fit warrant will refuse a snapshot that is not
verified.

### Snapshots

An assembly produces a **dataset snapshot**: a named, digested Delta table with
its PIT report attached, recording the Delta versions it actually read. A
validation episode can pin one and a replay can run against it, which is what
turns *"the model was validated on 2025H2 data"* into a checkable claim.

One caveat: a snapshot is written at `snapshots/{name}` in overwrite mode, so
re-assembling under the same name replaces it. Names are how you tell two
snapshots apart.

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

`name`, `entity`, `dtype`, `description` and `owner` are required; the rest have
defaults.

**business_definition** is separate from `description` on purpose. One is for the
engineer reading the column; the other is the definition a validator or an
examiner will hold you to.

**protected_basis** and **proxy_risk** are how fair-lending exposure becomes
queryable. `zip3` is not a protected basis, but its proxy risk is high, and being
able to ask *"which models read a high-proxy-risk feature"* is the difference
between a fair-lending review that takes a day and one that takes a quarter.

A feature is created `experimental` and moves to `certified` or `deprecated`:

```bash
POST /api/v1/features/{name}/certify?level=certified
```

### Duplicate detection at creation time

Feature sprawl is what makes a large store unusable — the fourth
`customer_income_v2_final` is a discovery problem, not a storage problem. So
near-duplicates surface **when a feature is created**, while renaming is still
cheap: the response to `POST /api/v1/features` carries a `possible_duplicates`
list of names alongside the feature it just made.

Similarity is Jaccard overlap of the tokens in the name and the description,
against a floor, capped at three suggestions — deliberately not embeddings. It
has to be fast enough to run on every definition and explainable enough that a
steward can see *why* two features were called alike.

## A version is a serving namespace

### The failure mode

A model is trained against a feature view. Six months later the view is
recomputed — a source changed, a bug was fixed, a definition was sharpened — and
the table is updated in place.

The model now scores against different numbers than it was trained on. Nothing
alerts. The contract digest still matches, because the contract named the *view*
rather than a version of it. Every monitor is green, because monitors compare
today's scores to yesterday's and the change was gradual.

That is adversarial finding **C-2**, and it is the reason for the design below.

### Each materialisation writes its own path

```
features/customer/sb_financials/v1
features/customer/sb_financials/v2
```

Publishing v2 does not touch a single byte v1 serves. Writes go to a fresh
per-version path, the version number increments per materialisation, and asking
for the namespace of a version that was never materialised is refused. There is
no "latest" and no in-place update, because the mechanism that makes the failure
possible is simply absent.

### Feature contracts

```bash
POST /api/v1/feature-contracts
{"model_version_id": "01a06a…", "items": [{"view": "sb_financials", "version": 1}]}

GET /api/v1/feature-contracts/{model_version_id}/namespaces
→ {"namespaces": {"sb_financials": "features/customer/sb_financials/v1"}}
```

Binding to a version that does not exist is refused: `'sb_financials' has no
version 3`.

Law **L-17** — contract–serving agreement — is the rule that what serving *must*
read equals what it *did* read. **It does not run.** It is one of the six
foundational laws named as not executable, because checking it needs an online
store to compare against. Half of it exists: `serving_namespaces` computes what
serving must read, and nothing yet observes what it did.

### A read is pinned to a version, not to a path

A namespace is a path, and a path is mutable. Two writes to the same namespace
produce two Delta versions, and a read naming only the path gets whichever is
current.

For **serving** that is correct — the namespace *is* the contract, and a
correction to a stale row should be served. For **reproducing** it is not: the
point of a snapshot is that re-running it returns what it returned before.

So an assembly reads at the Delta version the view version was materialised at,
and a featureset binding carries that version alongside the path. That is what
makes *same featureset version → same bytes* true rather than
true-until-somebody-writes-again.

The neighbouring question — *has anything underneath this pin moved?* — is asked
separately, because it is the one a reviewer asks before comparing two runs:

```bash
GET /api/v1/featuresets/{name}/versions/{n}/restatements
```

```json
{"featureset": "sb_core", "version": 1, "restated": true,
 "slots": [{"slot": "dscr",
            "namespace": "features/customer/sb_financials/v1",
            "delta_version": 3, "current_delta_version": 5,
            "row_count": 41208, "materialised_at": 1767139200.0, "restated": true,
            "detail": "…has been written to since it was pinned: v3 then, v5 now"}],
 "detail": "1 of this version's namespaces have been written to since it was
            published; the version still reads the bytes it pinned"}
```

A restatement is not automatically wrong — correcting a stale row is a legitimate
act. What matters is that a reader who dropped the pin would now see something
else, and that anybody comparing two runs knows which case they are in.

### Retirement: reported, not yet enforced

```bash
GET /api/v1/feature-views/sb_financials/versions/1/retirable
→ {"retirable": false, "pinned_by": ["01a06a…"]}
```

Storage costs money, so old versions will eventually be retired — and the
decision needs to know who breaks.

Two honest limits. **There is no retirement endpoint**: this reports, and nothing
enforces. And it consults *model version contracts* only — the check that catches
a view version pinned by a **featureset version** is implemented and wired to no
route, so a namespace pinned only that way reports `retirable: true`. Read the
featureset's own pins before acting on this.

### The cost, stated honestly

This design trades storage for correctness. A view materialised weekly for two
years is 104 namespaces, and they are not deduplicated. That is a real cost and
the right trade for governed features: the alternative saves disk and
reintroduces exactly the silent failure the design exists to prevent.

## Moving feature values in and out

Everything else in this platform moves small documents: a warrant, a contract, a
finding. Feature values are not small. A featureset over a few million entities
is the ordinary case, and an API that turns it into JSON objects — one dictionary
per row, keys repeated on every line — spends most of its time and nearly all of
its memory on punctuation.

So the rule here is different: **nothing is materialised whole.** Reads iterate
Arrow record batches straight off the Delta files and write them out as they go;
writes parse a batch at a time and append. Peak memory is one batch, not one
dataset.

A batch is sized by **cells rather than rows**, because sixteen thousand rows of
six columns is a few megabytes and sixteen thousand rows of two thousand columns
is not. A wide table is read in narrower slices, so the claim holds for both
shapes.

| Format | Media type | When | Out | In |
|---|---|---|---|---|
| `arrow` | `application/vnd.apache.arrow.stream` | From an execution engine. Zero-copy, genuinely incremental in both directions | yes | yes |
| `parquet` | `application/vnd.apache.parquet` | When the data is going to disk. Typically under half of NDJSON for the same rows | yes | yes |
| `ndjson` | `application/x-ndjson` | The lowest common denominator; anything can read it | yes | yes |
| `json` | `application/json` | For a page, not a job. Hard-capped at ten thousand rows | yes | no |
| `csv` | `text/csv` | What a person usually has, over the API only | **no** | yes |

**CSV is read and never written.** A CSV cannot carry a type, so a feature
exported as one would come back as text and both clocks would come back as
strings. Reading one is worth it because refusing would mean somebody converts by
hand, and the conversion is where the mistakes live. Writing one would hand back
something weaker than what went in. Note that the browser upload control is
narrower still — it offers Parquet, Arrow and NDJSON; CSV goes through the API.

Parquet is assembled to a temporary file and streamed from it, because a Parquet
file's footer holds the row-group index and cannot be written until the last row
is known. The file still never holds more than one batch in memory on the way in.

```bash
# out — at the PINNED Delta version, not whatever the namespace now holds
curl -u you:… -o sb_credit.parquet \
  'localhost:5006/api/v1/feature-views/sb_credit/versions/1/data?format=parquet'

# a whole featureset version, joined on the entity key — as_of is required
curl -u you:… -o core.parquet \
  'localhost:5006/api/v1/featuresets/sb_core/versions/1/data?format=parquet&as_of=1767139200'

# in — the whole upload becomes ONE version
curl -u you:… -X POST \
  -H 'Content-Type: application/vnd.apache.parquet' \
  --data-binary @sb_credit.parquet \
  localhost:5006/api/v1/feature-views/sb_credit/data
```

A featureset export **must** say what moment it speaks for. Joining the parts
without an `as_of` pairs each feature's history against every other feature's,
and that is refused rather than guessed.

**The whole upload becomes one version**, because a version is what a featureset
pins and half a version is not something anybody can pin. A body whose bytes and
declared content type disagree is refused too, rather than guessed at.

An engine pulling a large set in parallel should read `/parts` instead, which
names each namespace and the Delta version it is pinned at, and fetch them itself
rather than waiting on a join.

## A feature is not always a number

A yield curve is a vector. A correlation structure is a matrix. A scenario grid
is a tensor. Storing all of them as "numeric" and hoping the consumer knows
better is how a model receives ten tenors where it expected eleven and produces
an answer rather than an error.

So a feature carries a **shape**, and along its first axis optional **component
names**:

```json
{"name": "usd_curve", "entity": "book_id", "dtype": "numeric",
 "description": "USD OIS discount curve", "owner": "person/d.raman",
 "shape": [10],
 "components": ["1m","3m","6m","1y","2y","3y","5y","7y","10y","30y"]}
```

| Shape | Kind |
|---|---|
| `[]` | scalar — one number per row |
| `[10]` | vector |
| `[10, 10]` | matrix |
| `[5, 10, 10]` | tensor |

Rank is capped at 4 and an axis at 100,000 — beyond that it is a dataset with a
name rather than a feature. A zero-length axis, a component list that does not
match the first axis, duplicate component names, and components on a scalar are
each refused separately, by name.

**The component order is the axis order.** A curve whose tenors came back
alphabetically would be a different curve, and one nobody would notice was wrong.
Resolution preserves insertion order and never sorts.

The names are what make composition mean something. *Add a tenor*, *drop the
50-year point*, *override the 3-month with an OIS-based one* are operations on
named things; on an anonymous array they are operations on an index, and an index
is not a meaning.

**What is not checked:** the declared shape is validated when the feature is
*defined*, not against the values that arrive. The row-level check exists and is
exercised only in the test suite. A shape here is a contract with the reader, not
yet an assertion against the data.

## Composing features and featuresets

Inheriting from one parent and combining several are the same operation with a
different number of parents, so there is one mechanism:

> **A left-to-right fold in which the rightmost wins. An object's own operations
> are applied last, and are therefore the most prominent of all.**

Nothing else would be defensible. If a parent could override a child, naming a
parent would be an act of surrender.

That is not a convention. Merge-with-rightmost-wins is **associative** and the
empty map is its **identity**, so composition is a *monoid* — which is why "a
combination of features is a feature" is a true statement rather than an
aspiration.

```json
{"name": "usd_curve_extended", "entity": "book_id", "dtype": "numeric",
 "description": "USD curve with a 50y point", "owner": "person/d.raman",
 "composes": [{"name": "usd_curve"}],
 "operations": [
   {"op": "add",      "name": "50y", "value": {"dtype": "numeric"}},
   {"op": "drop",     "name": "1m"},
   {"op": "override", "name": "3m",  "value": {"dtype": "numeric", "source": "OIS"}}]}
```

`GET /api/v1/features/usd_curve_extended/resolved` returns what it *actually is*
— components, shape, ownership, drift and, for each component, who decided it:

```json
{"components": ["3m","6m","1y","2y","5y","10y","30y","50y"],
 "shape": [8],
 "provenance": {"3m": {"from": "usd_curve_extended (override)",
                       "version": 1, "overrode": "usd_curve"}}}
```

The row holds what the object *declares*; resolution happens on read. Two
featuresets combine the same way — name `sme_core` second and its `turnover`
definition is what the set holds, slot by slot, and the resolved set says so.

### Every operation is total

| Refused | Because |
|---|---|
| `drop` of something absent | a drop that quietly does nothing leaves a child differing from what its author wrote |
| `add` of something present | say `override`; the two read differently to a reviewer and should |
| `override` of something absent | say `add` |
| an operation naming no member, or carrying no definition | an operation nobody can execute is not one |
| a cycle | there is no fixed point to resolve to |
| a chain deeper than twelve | beyond that it is a modelling problem rather than a composition |
| composing an ephemeral parent | it resolves today and dangles tomorrow |
| composing something that does not exist | caught now, not on first read |

### When a parent moves

A composition records the parent's definition version at the moment it resolved,
so a parent that has since been amended shows up as **drift** on every child that
reads it:

```json
{"drift": [{"parent": "usd_curve", "composed_against": 1, "now_at": 3,
            "sealed": false}]}
```

Not a failed read — a child whose parent moved is something to be told about, not
something that should stop working. But it is never silent, because a stable name
over moving contents is the failure this platform was built around.

### Sealing

A **sealed** feature or featureset is final: no amendment, no further versions,
no change of owner — and **it can still be composed from**.

That combination is the whole point. **A sealed parent cannot drift**, because
the amendment that would move it is refused. Evolution does not stop; it moves to
a child, where a reviewer sees it.

> **409** — 'usd_curve' was sealed by person/s.iqbal and cannot be amended.
> *Compose a new feature from it instead — that is what sealing is for: a parent
> that cannot move is a parent worth building on, and the change stays visible in
> the child.*

`feature:seal` and `featureset:seal` are their own permissions, held by the
second line. Whoever may define a thing is not automatically who may end it.
Breaking a seal is administrators-only and needs a reason; both acts stay in the
chain.

### Ephemeral features and featuresets

Created for one purpose, read, and destroyed — by TTL, or on request.

```json
{"name": "scratch_pull", "entity": "customer", "dtype": "float",
 "description": "one-off pull", "owner": "person/d.raman",
 "ephemeral": true, "ttl_days": 0.5}
```

One day by default, **thirty days maximum**: something needed for longer is not
ephemeral, and declaring it so is a way of avoiding the governance a durable
object owes. Two rules follow, and both are refusals:

- **Nothing may depend on one.** Composing from something that will be destroyed
  leaves a child that resolves today and dangles tomorrow, and a dangling pin is
  worse than no pin because it looks like one.
- **It cannot be sealed.** Permanent and temporary are not two flags that happen
  to be set; one of them is wrong.

**Destruction is recorded.** The rows go and the evidence stays, with the version
digests. A throwaway featureset somebody pulled a million rows through is exactly
what an examiner asks about, and *"it was ephemeral"* is not an answer.

### Who made it, and who answers for it

Two facts, kept apart. **`created_by`** is history and never changes. **`owner`**
is a responsibility, transferable to somebody named, by somebody entitled, with
the handover in the chain. An owner field that quietly becomes a leaver's
username is how a model ends up accountable to nobody.

## What MAYA does to values on the way out

Filling gaps, normalising and aligning onto an axis are decisions somebody has to
make. Leaving them to every caller has two failure modes: each consumer decides
differently and the same feature means different things in two models, or the
awkward columns get skipped and somebody downstream turns the nulls into zeros
without saying so.

So the decision attaches to the feature or featureset as its **default
behaviour**, and a request may override it:

```json
{"defaults": {
   "align":     {"axis": "event_ts", "rule": "flat_forward"},
   "fill":      {"dscr": "median", "utilisation": "zero"},
   "normalise": {"dscr": "zscore"}}}
```

A policy says `fill`, `normalise`, `align` and nothing else. **The precedence is
the composition rule again**, deliberately:

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

> **A request that normalises with no `as_of` is refused.** The leaky answer is
> the one somebody would get by accident, so it is the one that must not be the
> default.

`none` · `zscore` · `minmax` · `robust` (median/IQR) · `rank`. Only `none`
escapes the `as_of` requirement. Vectors and tensors normalise elementwise. Fewer
than **thirty** observations is refused — a statistic on fewer is a guess with a
decimal point. A constant column returns zeros and says so rather than dividing
by zero quietly.

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
the variance down. So the statistics are fitted on what was observed, then
applied to everything including what was filled.

### Aligning onto an axis

Features arrive on their own clocks — a balance monthly, a rating annually, a
price daily and not at weekends. Aligning them onto one axis and filling the gaps
hands an engine a rectangle instead of a ragged frame:

```json
{"align": {"axis": "event_ts", "rule": "flat_forward", "carry_limit": 7776000}}
```

| Rule | Fills from | Safe for training |
|---|---|---|
| `none` | nothing — the observed grid stands | **yes** |
| `flat_forward` | the last observation | **yes** |
| `flat_backward` | the next observation | no |
| `linear` | both neighbours | no |
| `nearest` | whichever is closer | no |

The last three reach into the future. They are right for drawing a curve, for an
explicitly retrospective backtest, for showing a history to a person — and wrong
for training a model.

**They are not refused. They are stamped honestly.** A value derived from a later
observation inherits that observation's `ingest_ts`, because that is genuinely
when it became knowable:

```
grid point  t=1   value 400.0   ingest_ts 3.0   ← filled from the observation at t=3
```

An ordinary point-in-time read at `as_of = 1` then excludes it, by the same rule
that governs everything else here, with nobody having to remember a flag. The
leakage is not caught by a check; it is made arithmetically impossible to hide.

A **carry limit** bounds how far an observation may travel. Past it the value is
**dropped and counted** rather than carried: a balance from eighteen months ago
is not this month's balance, and carrying it forever turns a stale observation
into a fabricated one. And interpolation will not *extrapolate* from one side
under the name of interpolating — that is a different act with a different error,
and doing it silently would hide which was done.

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

The response carries the rows, the policy actually applied, what each step did,
and the statistics it fitted. `GET /api/v1/retrieval` publishes the whole
vocabulary — preparation, alignment, policy and composition — and the rules each
obeys.

## Through the interface

The **Features** page defines primitives and derived features and lists what each
view holds. A view's own page uploads a file and offers each version in every
format. The **Featuresets** page declares a schema; a featureset's page fills it,
rolls it forward to newer view versions with a diff of what moved, and shows each
version's pins alongside whether anything underneath them has been restated.

## Next

Naming a set of features so a warrant can ask for it by name, computing derived
features from primitives, and storing what a fit produced: [Featuresets and
fitted parameters](/help/featuresets-and-parameters).
