---
title: Featuresets and fitted parameters
slug: featuresets-and-parameters
section: Features and data
order: 70
icon: diagram-3
summary: Named, versioned collections of features that a warrant can name; derived features computed from primitives; and the fitted parameters that come back from an execution engine and are stored, versioned and governed like everything else. With a worked New Jersey home-price regression, end to end.
audience: Model developers, Model owners, Model risk
---

# Featuresets and fitted parameters

A model in MAYA is a **parametric kernel**: `f : P × X → D(Y)`. Training does not
change `f`. Training *inhabits* `P` — it picks a point in the parameter object.

Two of those three letters were not first-class objects.

**`X`** — the input space — existed only as a list buried inside one model
version's feature contract. It could not be named, could not be reused, and two
models could not be said to read the same thing.

**`P`** — the parameter object — was not stored at all. MAYA held the digest of
an *artifact*, but nowhere to put the coefficients an engine computed. The
warrant grammar already demanded that a `fit` declare `sink: parameter_object`
(law **L-W4**); there was simply nothing on the register's side to receive it.

This page describes both, and the cycle that connects them. If you want the
concrete version first, skip to
[the worked example](#worked-example-new-jersey-home-prices).

## The shape of it

```
feature                     a declaration: name, entity, dtype, owner
   │
   ├── primitive            values arrive by materialisation
   └── derived              values computed from other features: Z = f(X, Y)
                            │
feature view version  ──────┘   where values actually live, in Delta,
   │                            in a namespace that never moves
   │
featureset                  a NAME and a declared SCHEMA
   └── featureset version   binds features to that schema — pinned exactly
          │
          │   fit warrant:  model version × featureset version × window
          ▼
   parameter set version    an inhabitant of P, returned by an engine
          │
          │   score warrant: model version × parameter set version
          ▼
       predictions
```

Read the last four lines together and the whole cycle is there.

## A featureset is a schema, and a version fills it

This is the load-bearing idea, and it is what makes *"different versions may
contain different features, but all adhere to the same structure"* true rather
than hopeful.

**The featureset declares a schema.** Named slots, each with a type. That schema
is the contract — it is what a kernel is defined over.

**A featureset version binds features to those slots.** Exactly: each slot names
a feature *and* the feature view version that supplies its values.

Most of the time the slot name simply *is* the feature name, and nobody has to
think about slots at all. They earn their keep when the constituents change:

```yaml
featureset: inflation
schema:
  gb_index:    numeric
  us_index:    numeric
  daily_index: numeric

version 1:                        version 2:
  gb_index    → UKRPI               gb_index    → UKRPI
  us_index    → USCPI               us_index    → USCPI
  daily_index → DAILY_INFLATION     daily_index → EUHICP
```

`inflation@v2` draws on a different feature entirely, and a model defined over
`inflation` does not change: it reads `daily_index`, and always did.

Now the important half. A version that **cannot fill the schema** is **refused**,
and the refusal says which half of the problem it is:

```
these slots are unfilled: {property_age}. a version that cannot fill the
schema is not a version of this featureset

these bindings name no declared slot: {school_rating}. adding a slot changes
the schema, which changes X — publish it as a different featureset

slot 'bedrooms' holds integer but 'bathrooms' is numeric; a version must
fill the schema it declares
```

It is not a new version of this featureset; it is a different featureset, or it
is a model change. MAYA decides which, so nobody has to remember.

That check is not new machinery. It is the schema lattice and the variance rule
(**L-12**) already used to gate alias promotion, applied one level out.

### Everything a featureset version pins

| | Why it is there |
|---|---|
| **Slot → (feature, view, view version)** | So *same version → same bytes*. A version that named views without pinning them would silently serve different data next month — adversarial finding **C-2**, one level up |
| **Entity and grain** | What one row *is* |
| **Column roles** | feature · label · identifier-not-to-be-fed. Without declared roles, leakage detection is guesswork |
| **Label spec and outcome window** | So *"is this cohort mature enough to train on"* is answerable rather than assumed |
| **The point-in-time rule** | Which clock bounds apply. Platform discipline belongs in the set, not re-declared in every warrant |

A version that names a view it did not pin, names a view that was never
materialised, or leaves the view ambiguous is refused for each of those reasons
by name.

### What it deliberately does *not* pin

**The spine.** Which entities, at which label timestamps, over what date range.

The set owns the **shape**; the warrant supplies the **window**. Otherwise "train
on 2019–2023, then on 2020–2024, same features" would be two featuresets, which
is wrong — it is one featureset and two warrants.

## Derived features

A derived feature is one whose values are **computed from other features** rather
than supplied: `Z = f(X, Y)`. Log transforms, ratios, interaction terms,
differences from a moving average — the ordinary furniture of a regression.

They are declared, not written down somewhere and applied by hand:

```json
POST /api/v1/derived-features
{
  "name": "lot_to_living_ratio",
  "expression": "lot_size_sqft / living_area_sqft",
  "dtype": "numeric",
  "description": "Plot generosity relative to the house on it",
  "on_error": "null"
}
```

Note what is **not** in that body: the input list. Inputs are parsed out of the
expression rather than declared beside it, because a declared input list is a
second statement of the same fact and the two will disagree. `on_error` is
`null` or `refuse`, and it is stated up front rather than discovered in
production when a denominator turns out to be zero.

Four rules govern derived features, and each exists because the alternative
fails quietly.

**Lineage is recorded and transitively closed.** `lot_to_living_ratio` depends on
two primitives, and `GET /api/v1/derived-features/{name}/lineage` will say so,
including dependants several hops out. A self-reference or a cycle is refused,
as is an input belonging to a different entity.

**The ingest clock is inherited as a maximum.**

> `ingest_ts(Z) = max(ingest_ts(X), ingest_ts(Y))`

You did not know `Z` before you knew both its inputs. Stamping the computation
time instead would make a derived feature appear knowable earlier than it was,
and every [point-in-time assembly](/help/features-and-two-clocks#point-in-time-assembly)
built on it would be subtly wrong. It is arithmetic, so MAYA computes it.

**A derived feature may not read a label.** Consider a `price_per_sqft` computed
from `sale_price`, where `sale_price` is what the model predicts. That is leakage
with a division sign in front of it, and a model using it will look extraordinary
in validation and fail on the first house it has not already seen. The check runs
when a featureset is published, over the full lineage rather than just the
immediate inputs, and the refusal is quoted in the worked example below.

**Certification is the meet of its inputs.** A derived feature is at most as
certified as its least-certified input. Deriving from an uncertified feature does
not launder it.

### Who actually computes it

MAYA evaluates a **deliberately small** expression language over feature values
it already holds, published at `GET /api/v1/expression-language`: arithmetic,
comparison, `and`/`or`/`not`, a conditional, and the functions `log`, `exp`,
`sqrt`, `abs`, `min`, `max`, `round`, `floor`, `ceil`. A row's own clocks are
readable as `event_ts` and `ingest_ts`, and its year as `event_year` or
`year(event_ts)`. Expressions are parsed to a syntax tree and evaluated against a
whitelist — no attribute access, no dunder names, no calls outside that table.

The language is total, deterministic, side-effect-free, and readable in one line.
It has **no window and no lag**: a derived feature sees the row it is computing,
not the rows around it. A moving average is not expressible here, and that is the
boundary rather than an omission to be filled in later.

The line being drawn: **MAYA transforms features it holds; it does not run
models.** Computing `x / y` over a stored column is the same class of act as
computing the null rate MAYA already reports. Running a kernel is not.

An expression outside that language — one needing a library, external data, or a
model — is declared with `evaluator: external`. MAYA stores the **definition** so
the lineage, the leakage check and the certification meet all still work, but it
refuses to evaluate it:

```
'nlp_sentiment' is declared external, so MAYA does not compute it;
materialise its values like any primitive — the definition is still kept, so
lineage and the leakage check still apply
```

## Worked example — New Jersey home prices

A multiple linear regression predicting residential sale price. Small enough to
hold in your head, and it exercises everything above. Both warrants below ship as
runnable documents — `examples/warrants/11-nj-linear-fit-from-featureset.json`
and `12-nj-linear-score-on-parameters.json` — and the same example is walked
through with real calls in
[Training a model, end to end](/tutorials/train-a-model).

### The model

```yaml
urn:   maya://model/re.price.nj_linear
name:  NJ Home Price — Multiple Linear Regression
class: real_estate.price.hedonic
kernel:
  parameter_kind: estimated_coefficients
  fit_procedure:  estimate
  output_kind:    point_estimate
  deterministic:  true
```

`fit_procedure: estimate` makes this **T2** — and T2 is derived from how `P` is
inhabited, never declared. It is not T0, so a `fit` warrant is admissible; had
this been a closed-form valuation with parameters from theory, law **L-W1**
would refuse one as a type error.

### The primitive features

| Feature | Type | Role | View |
|---|---|---|---|
| `living_area_sqft` | numeric | feature | `nj_property_characteristics` |
| `lot_size_sqft` | numeric | feature | `nj_property_characteristics` |
| `bedrooms` | integer | feature | `nj_property_characteristics` |
| `bathrooms` | numeric | feature | `nj_property_characteristics` |
| `year_built` | integer | feature | `nj_property_characteristics` |
| `municipality_code` | categorical | feature | `nj_property_characteristics` |
| `school_rating` | numeric | feature | `nj_location_context` |
| `distance_to_nyc_km` | numeric | feature | `nj_location_context` |
| `median_income_zip` | numeric | feature | `nj_location_context` |
| `property_id` | string | identifier | — |
| `sale_price` | numeric | **label** | `nj_transactions` |

Entity `property_id`; grain one row per property per observation date. Every row
carries both clocks — `event_ts` when the fact was true, `ingest_ts` when MAYA
learned it.

### The derived features

```yaml
- name: log_living_area
  expression: "log(living_area_sqft)"
  # Price responds to area multiplicatively. A linear model in log-area is
  # a better-specified model, not a cosmetic change.

- name: lot_to_living_ratio
  expression: "lot_size_sqft / living_area_sqft"
  on_error: "null"

- name: property_age
  expression: "year(event_ts) - year_built"
  # Reads the row's own event clock, so it is correct for a 1962 house
  # whether the row is a 2019 sale or a 2024 one.

- name: income_school_interaction
  expression: "median_income_zip * school_rating"
```

And the one that is **refused**:

```yaml
- name: price_per_sqft
  expression: "sale_price / living_area_sqft"
```

> **Refused.** `'price_per_sqft' is computed from 'sale_price', which this
> featureset declares as its label — a feature derived from the label leaks the
> answer into the training set. derive it from a value known before the outcome,
> or declare it an output rather than a feature.

The featureset's declared roles are what make this a check rather than a code
review. Over the API it comes back as `feature_refused`.

### The featureset

```yaml
featureset: nj_home_core
entity:     property_id
label:      sale_price
outcome_window_days: 0        # the price is known at the moment of sale
pit_rule:   event_ts <= label_ts AND ingest_ts <= as_of

schema:
  log_living_area:          numeric
  lot_to_living_ratio:      numeric
  bedrooms:                 integer
  bathrooms:                numeric
  property_age:             numeric
  municipality_code:        categorical
```

Version 1 binds it, and the pins are exact:

```yaml
featureset_version: nj_home_core@v1
bindings:
  log_living_area     → log_living_area      (derived, def@v1)
                          ← nj_property_characteristics@v7
  lot_to_living_ratio → lot_to_living_ratio  (derived, def@v1)
                          ← nj_property_characteristics@v7
  bedrooms            → bedrooms             ← nj_property_characteristics@v7
  bathrooms           → bathrooms            ← nj_property_characteristics@v7
  property_age        → property_age         (derived, def@v1)
                          ← nj_property_characteristics@v7
  municipality_code   → municipality_code    ← nj_property_characteristics@v7
label:
  sale_price          ← nj_transactions@v22
digest: sha256:4c1f…
```

Materialise `nj_property_characteristics@v8` with 2025 data and **nothing about
v1 changes**. Rolling forward — `POST /api/v1/featuresets/nj_home_core/roll-forward` —
mints `nj_home_core@v2`, re-resolved to `@v8`, with a diff showing exactly what
moved. Same schema, so the same model version can use it.

### Two featuresets, one model

```yaml
featureset: nj_home_enriched          # same entity, same label
schema:
  log_living_area:          numeric   # ... the six above, plus:
  school_rating:            numeric
  distance_to_nyc_km:       numeric
  income_school_interaction: numeric
```

This is a **different schema** — nine slots, not six. A linear model's coefficient
vector has one entry per column, so `re.price.nj_linear@1.0.0`, whose `X` names
six, is not defined over it. Adding a regressor is a model change, not a data
change: you create `re.price.nj_linear@2.0.0` over the nine, and then you have
two model versions and two featuresets that can be compared honestly, because
each run says exactly which data it saw.

That is checked, not left to a reviewer. `POST /api/v1/fit-warrants` refuses a
featureset that does not provide what the kernel declares it reads:

> **409 `schema_not_satisfied`** — `nj_home_core` does not provide
> `school_rating`, `distance_to_nyc_km`, which this version declares it reads.
> *Bind a featureset whose schema covers the kernel's inputs, or create a model
> version whose input schema matches this set — adding a regressor is a model
> change, not a data change.*

This is law **L-W10**, and it is the same variance rule (**L-12**) that gates
alias promotion, applied one level out. It is checked at warrant time rather than
at publish, because a featureset does not belong to a model: whether it provides
what a particular kernel reads is only answerable once both are named.

Be precise about its direction. The check is **contravariant in inputs**, so a
*wider* featureset passes — it provides everything the six-slot kernel asked for,
and the extra columns are simply not read. That is correct and deliberate: a set
carrying more than one model needs is the ordinary case, and refusing it would
make sets unshareable, which is what they exist for. What cannot happen is the
failure that matters: fitting a kernel over a set that is missing something it
declares.

## The fit warrant

```json
{
  "subject":   { "urn": "maya://model/re.price.nj_linear",
                 "semver": "1.0.0" },
  "operation": { "verb": "fit", "deterministic": true },
  "parameters":{ "kind": "estimated_coefficients",
                 "source": { "binding": "to_be_fitted" } },
  "realisation": { "runtime": "python.callable",
                   "entry": { "module": "nj.estimators", "attr": "ols_fit" } },
  "data": {
    "inputs": [{ "binding": "featureset",
                 "featureset": "nj_home_core",
                 "version": 1,
                 "window": { "from": "2019-01-01", "to": "2024-12-31" },
                 "as_of":  "2025-01-15T00:00:00Z" }],
    "outputs": [{ "sink": "parameter_object" }]
  },
  "constraints": { "resources": { "max_seconds": 600 } },
  "authority":   { "principal": "svc/model-lab", "expires_at": "…" },
  "signature":   { "key_id": "maya-dev-key", "value": "…" }
}
```

`featureset` is one of the grammar's twelve data bindings, and it takes exactly
these keys: the set, the version, and an `as_of`.

Four checks happen before it is signed:

1. **L-W1** — is `fit` meaningful for this class? T2, so yes.
2. **L-W10** — does `nj_home_core@v1` provide the six inputs the kernel declares,
   at compatible types? A set missing one is refused by name.
3. **L-W3 and L-W9** — `featureset` is one of the three bitemporal bindings, and
   for a fit both clocks must be bounded: a `window` with a start and an end, and
   an `as_of`. An unbounded read is **refused**, because a training set assembled
   from an unbounded source cannot be shown point-in-time correct.
4. **L-W4** — does it say where the parameters go? `sink: parameter_object`.

The engine assembles, fits, and posts the result back.

## What comes back

```json
POST /api/v1/models/re.price.nj_linear/parameters
{
  "name": "nj_home_core-fit-2025-01-15",
  "kind": "estimated_coefficients",
  "provenance": "fitted",
  "values": {
    "intercept":                    -142380.55,
    "log_living_area":               108422.31,
    "lot_to_living_ratio":             6218.04,
    "bedrooms":                       -4102.77,
    "bathrooms":                      21845.90,
    "property_age":                   -1187.62,
    "municipality_code[MONTCLAIR]":   88214.03,
    "municipality_code[NEWARK]":     -31776.48
  },
  "diagnostics": { "r_squared": 0.783, "n": 41208, "residual_se": 62114.20 },
  "fitted_from": {
    "model_version":     "re.price.nj_linear@1.0.0",
    "featureset_version":"nj_home_core@v1",
    "window":            "2019-01-01 … 2024-12-31",
    "as_of":             "2025-01-15T00:00:00Z",
    "snapshot":          "sha256:9a02…",
    "warrant":           "wrt_7f31"
  }
}
```

The negative `bedrooms` coefficient is not a bug and is worth a sentence: holding
floor area fixed, more bedrooms means *smaller* bedrooms. A register that stores
the coefficients makes that visible to a reviewer instead of leaving it in a
notebook.

**MAYA accepts a fitted parameter set only against a warrant it issued.** The
refusals are specific — `warrant_required` when none is named, `unknown_warrant`
when MAYA did not issue it, `warrant_names_another_version` when it did but for
something else. There is no back door. Without that, "which data produced these
numbers" becomes unanswerable, and the lineage this whole structure exists for
evaporates.

A parameter set is **immutable**, **versioned per model version**, and **does not
create a new model version** — the kernel did not change; only `P` was
re-inhabited. It is `proposed` until somebody reviews it, and **the person who
recorded it may not approve it** (`self_approval`); rejection requires a reason;
a set that has already been reviewed cannot be reviewed again. Values are held
inline up to a cap, beyond which the set is refused as `parameters_too_large`
rather than silently truncated.

One thing to be aware of: approval governs the parameter set record, and the
alias gate does **not** currently read it. An alias move checks that the *model
version* is approved. Pinning a parameter set into the serving path is done by
the warrant that names it, not by the alias.

### Three ways parameters arrive

`GET /api/v1/parameter-provenance` publishes the three, and the difference is
what evidence each one owes:

| Provenance | Typical classes | Evidence | Needs a warrant |
|---|---|---|---|
| **fitted** | T2 · T3 · T4 · T5 | A fit warrant and its result | **yes** |
| **calibrated** | T1 | Market data, often daily | no |
| **declared** | T0 · T7 · T8 | A person asserting them | no |

Only `fitted` requires a warrant, because it is the only one where MAYA can
check the claim: it issued the warrant, so it knows which featureset version and
which window produced the numbers. A calibration re-solved every morning and a
coefficient a committee agreed are recorded with their provenance and reviewed
individually.

Refusals here are keyed on the kernel rather than on the label: a `fitted` set
against a model whose `parameter_kind` is `none` is refused as `nothing_to_fit`,
and against an `opaque` one as `parameters_not_reachable`. That is the T0 and T6
case again, arriving from the other direction — a Black–Scholes closed form has
its parameters from the first day, no featureset and no fit warrant, and law
**L-W1** refuses a `fit` for it with the reason stated. Nobody has to remember
which models train.

## The run warrant

```json
{
  "subject":   { "urn": "maya://model/re.price.nj_linear", "semver": "1.0.0" },
  "operation": { "verb": "score", "deterministic": true },
  "parameters":{ "kind": "estimated_coefficients",
                 "source": "parameter_set",
                 "parameter_set": "nj_home_core-fit-2025-01-15" },
  "data": { "inputs":  [{ "binding": "request" }],
            "outputs": [{ "sink": "response" }] }
}
```

Model version **and** parameter set, both named. Law **L-W8** is the rule that
every run must say which point in `P` it runs at — a warrant that names a kernel
and leaves its parameters implicit describes an outcome nobody can reproduce.
With both pinned the run is determined: same kernel, same point in `P`, same
input, same answer.

And the appraiser querying a price sees a number whose provenance runs all the
way back — through the parameter set, to the featureset version, to the pinned
Delta namespaces, to the rows that were true and known on 15 January 2025.

## What this does not do

**It is not feature engineering.** The expression language is small on purpose,
and has no windows or lags. Anything needing a library, a join or a model is
declared `external`: MAYA keeps the definition, the lineage and the checks, and
says plainly that it did not compute the values.

**It does not fit anything.** MAYA issues the warrant and receives the result.
The estimation happens in an execution engine, which is the same boundary drawn
everywhere else.

**It does not choose your features.** No automatic selection, no importance
ranking, no suggestion engine. It records what you chose, pins it so it cannot
move underneath you, and refuses the combinations that are type errors.

**It does not yet guard feature retirement.** Lineage is recorded and reported,
so *"what breaks if this goes"* is answerable in one call — but the enforced
retirement guard is the one on feature view versions, and there is no endpoint
that retires a feature.
