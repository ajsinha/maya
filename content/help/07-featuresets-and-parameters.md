---
title: Featuresets and fitted parameters
slug: featuresets-and-parameters
section: Features and data
order: 70
icon: diagram-3
summary: The two letters that are not the kernel — a featureset that names X as a schema, and a parameter set that inhabits P — the fit warrant that connects them, and the training record compiled for every fit. With a worked New Jersey home-price regression.
audience: Model developers, Model owners, Model risk
---

# Featuresets and fitted parameters

A model is a **parametric kernel**: `f : P ⊗ X → D(Y)`. Training does not change
`f`. Training *inhabits* `P` — it picks a point in the parameter object.

Two of those three letters used to have nowhere to live.

**`X`** existed only as a list buried inside one model version's feature
contract. It could not be named, could not be reused, and two models could not be
said to read the same thing.

**`P`** was not stored at all. MAYA held the digest of an *artifact* and had
nowhere to put the coefficients an engine computed — while the warrant grammar
already demanded that a `fit` declare `sink: parameter_object` (law **L-W4**).

This page is both, and the cycle between them. If you want the concrete version
first, skip to [the worked
example](#worked-example-new-jersey-home-prices).

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
   parameter set version    an inhabitant of P, proposed then approved
          │                 └── training record, compiled from the register
          │   run warrant:  model version × parameter set version
          ▼
       predictions
```

Read the last five lines together and the whole cycle is there.

## A featureset is a schema, and a version fills it

This is the load-bearing idea, and it is what makes *"different versions may
contain different features, but all adhere to the same structure"* true rather
than hopeful.

**The featureset declares a schema** — named slots, each with a dtype and a
nullability. That schema is the contract, and it is what a kernel is defined
over.

**A featureset version binds features to those slots**, exactly: each slot names
a feature *and* the view version that supplies its values.

Most of the time the slot name simply *is* the feature name and nobody thinks
about slots at all. They earn their keep when the constituents change:

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

Now the important half. A version that **cannot fill the schema** is **refused**
(409), and the refusal says which half of the problem it is:

```
these slots are unfilled: property_age. a version that cannot fill the
schema is not a version of this featureset

these bindings name no declared slot: school_rating. adding a slot changes
the schema, which changes X — publish it as a different featureset, and
expect the model to need a new version

slot 'bedrooms' holds integer but 'bathrooms' is numeric; a version must
fill the schema it declares
```

It is not a new version of this featureset; it is a different featureset, or it
is a model change. MAYA decides which, so nobody has to remember.

That check is not new machinery. It is the schema lattice and the variance rule
(**L-12**) already used to gate alias promotion, applied one level out.

Four more refusals guard the pinning itself, each by name:

```
'dscr' names view 'sb_financials' without a version; a featureset version
pins exactly, or the same version would resolve to different bytes next month

no materialised feature view supplies 'dscr'; materialise it before a
featureset can pin it

'dscr' is supplied by more than one view (sb_financials, sb_core); name the
view and version

'sb_core' declares label slot 'default_12m' but this version does not bind
it; a supervised set without a label is not one
```

### What lives where

Two objects, and it matters which is which — the set is what a model is defined
over, the version is what a fit actually read.

| On the **set** | On the **version** |
|---|---|
| `entity` and `grain` — what one row *is* | one **binding per slot** |
| `slots` — the schema: dtype and nullability | `label_binding` |
| `label_slot` and `outcome_window_days` — so *"is this cohort mature enough to train on"* is answerable | `digest` over the whole binding |
| `defaults` — the retrieval policy | `note`, `created_by`, `created_at` |
| `composes` and `operations` | |

Each binding pins eleven things, and the reason is one sentence: **same version →
same bytes.**

```
feature · slot · dtype · view · view_version · feature_view_id ·
namespace · delta_version · derived · definition_version · certification
```

`delta_version` is the one people forget. A version that named views without
pinning the Delta version underneath them would silently serve different data
next month — adversarial finding **C-2**, one level up.

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
  "evaluator": "internal",
  "on_error": "null"
}
```

Note what is **not** in that body: the input list. Inputs are parsed out of the
expression rather than declared beside it, because a declared input list is a
second statement of the same fact and the two will disagree. `on_error` is `null`
or `refuse`, stated up front rather than discovered in production when a
denominator turns out to be zero.

Four rules govern derived features, and each exists because the alternative fails
quietly.

**Lineage is recorded and transitively closed.** `GET
/api/v1/derived-features/{name}/lineage` names every ancestor including dependants
several hops out, to a depth of twelve. A self-reference, a cycle, an undefined
input, an expression that reads no features at all (that is a constant), and
inputs spanning more than one entity are each refused by name.

Two lineages answer different questions, and the distinction is worth having:
*what would break if this changed* follows every ancestor, derived ones included;
*what data does this ultimately read* is the base features and nothing else —
computed as the free variables of a polynomial rather than by walking the graph
twice.

**The ingest clock is inherited as a maximum.**

> `ingest_ts(Z) = max(ingest_ts(X), ingest_ts(Y))`

You did not know `Z` before you knew both its inputs. Stamping the computation
time instead would make a derived feature appear knowable earlier than it was,
and every [point-in-time
assembly](/help/features-and-two-clocks#the-point-in-time-read-and-what-makes-it-reproducible)
built on it would be subtly wrong. It is a homomorphism, not a convention, which
is why it has no exceptions to forget.

**A derived feature may not read a label.** Consider `price_per_sqft` computed
from `sale_price`, where `sale_price` is what the model predicts. That is leakage
with a division sign in front of it, and a model using it will look extraordinary
in validation and fail on the first house it has not already seen. The check runs
when a featureset is **published**, over the full lineage rather than the
immediate inputs, and refuses with `feature_refused` at 409.

**Certification is the meet of its inputs**, over
`experimental < reviewed < certified < gold`. A derived feature is at most as
certified as its least-certified input. Deriving from an uncertified feature does
not launder it.

### Who actually computes it

MAYA evaluates a **deliberately small** expression language over feature values
it already holds, published at `GET /api/v1/expression-language`:

| | |
|---|---|
| Functions | `log` `exp` `sqrt` `abs` `min` `max` `round` `floor` `ceil` — nine, and no more |
| Operators | `+ - * / // % **`, `< <= > >= == !=`, `and` `or` `not`, and `x if cond else y` |
| Names | the row's own clocks as `event_ts` and `ingest_ts`, and its year as `event_year` or `year(event_ts)` |
| Excluded | attribute access, subscripting, comprehensions, lambdas, imports, and any function not in that table |

Expressions are parsed to a syntax tree and evaluated against a node whitelist,
so the exclusions are structural rather than a blocklist. `log` of a
non-positive number and `sqrt` of a negative one return null rather than raising.

The language is total, deterministic, side-effect-free, and readable in one line.
It has **no window and no lag**: a derived feature sees the row it is computing,
not the rows around it. A moving average is not expressible here, and that is the
boundary rather than an omission to be filled in later.

The line being drawn: **MAYA transforms features it holds; it does not run
models.** Computing `x / y` over a stored column is the same class of act as
computing the null rate MAYA already reports. Running a kernel is not.

An expression outside that language — one needing a library, external data, or a
model — is declared with `evaluator: external`. MAYA stores the **definition** so
the lineage, the leakage check and the certification meet all still work, and
refuses to evaluate it:

```
'nlp_sentiment' is declared external, so MAYA does not compute it;
materialise its values like any primitive — the definition is still kept, so
lineage and the leakage check still apply
```

Such an expression usually cannot be *parsed* either, and then it must declare
what it reads:

```json
{"name": "nlp_sentiment",
 "expression": "hf.sentiment(complaint_text)",
 "evaluator": "external",
 "inputs": ["complaint_text"]}
```

Without the `inputs` the definition is refused, because a feature resting on
nothing is a feature the leakage check cannot see through — and seeing through it
is why the definition is kept at all. The list is accepted **only** for an
expression MAYA cannot parse: where the expression parses, the parse is the
single source of truth and a second list is refused as something that can
disagree with it.

## Worked example — New Jersey home prices

A multiple linear regression predicting residential sale price. Small enough to
hold in your head, and it exercises everything above. Both warrants ship as
runnable documents — `examples/warrants/11-nj-linear-fit-from-featureset.json`
and `12-nj-linear-score-on-parameters.json` — and the same example is walked with
real calls in [Training a model, end to end](/tutorials/warrants-and-training).

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
  runtime:        estimator
  entry:
    family:     ols
    target:     sale_price
    regressors: [log_living_area, lot_to_living_ratio, bedrooms,
                 bathrooms, property_age, municipality_code]
```

`fit_procedure: estimate` makes this **T2**, derived from how `P` is inhabited
and never declared. It is not T0, so a `fit` warrant is admissible; had this been
a closed-form valuation with parameters from theory, law **L-W1** would refuse
one as a type error.

The `estimator` runtime is what lets MAYA run the fit itself. Without it the
version is fitted somewhere else and the result delivered back — the same
boundary drawn everywhere else in the platform.

### The derived features

```yaml
- name: log_living_area
  expression: "log(living_area_sqft)"
  # Price responds to area multiplicatively. A linear model in log-area is a
  # better-specified model, not a cosmetic change.

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

> **409 `feature_refused`** — `'price_per_sqft' is computed from 'sale_price',
> which this featureset declares as its label — a feature derived from the label
> leaks the answer into the training set. derive it from a value known before the
> outcome, or declare it an output rather than a feature.*

The featureset's declared label slot is what makes this a check rather than a
code review, and the check runs at publish over the whole lineage — so a feature
three hops away from the label is caught too.

### The featureset, and its version

```yaml
featureset: nj_home_core
entity:     property_id
grain:      one row per property per observation date
label_slot: sale_price
outcome_window_days: 0        # the price is known at the moment of sale

slots:
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
  log_living_area     → log_living_area   (derived, def@v1)
                          ← nj_property_characteristics@v7, delta 12
  lot_to_living_ratio → lot_to_living_ratio (derived, def@v1)
                          ← nj_property_characteristics@v7, delta 12
  bedrooms            → bedrooms          ← nj_property_characteristics@v7, delta 12
  bathrooms           → bathrooms         ← nj_property_characteristics@v7, delta 12
  property_age        → property_age      (derived, def@v1)
                          ← nj_property_characteristics@v7, delta 12
  municipality_code   → municipality_code ← nj_property_characteristics@v7, delta 12
label_binding:
  sale_price          ← nj_transactions@v22, delta 4
digest: sha256:4c1f…
```

Materialise `nj_property_characteristics@v8` with 2025 data and **nothing about
v1 changes**. Rolling forward — `POST
/api/v1/featuresets/nj_home_core/roll-forward` — mints `nj_home_core@v2`,
re-resolved to `@v8`, with a diff showing exactly what moved. Same schema, so the
same model version can use it.

### Two featuresets, one model

```yaml
featureset: nj_home_enriched          # same entity, same label
slots:
  log_living_area:           numeric  # ... the six above, plus:
  school_rating:             numeric
  distance_to_nyc_km:        numeric
  income_school_interaction: numeric
```

This is a **different schema** — nine slots, not six. A linear model's
coefficient vector has one entry per column, so `re.price.nj_linear@1.0.0`, whose
`X` names six, is not defined over it. Adding a regressor is a model change, not
a data change: you create `re.price.nj_linear@2.0.0` over the nine, and then you
have two model versions and two featuresets that can be compared honestly,
because each run says exactly which data it saw.

That is checked, not left to a reviewer:

> **409 `schema_not_satisfied`** — `'nj_home_core' does not provide
> school_rating, distance_to_nyc_km, which this version declares it reads.*
> *Bind a featureset whose schema covers the kernel's inputs, or create a model
> version whose input schema matches this set — adding a regressor is a model
> change, not a data change.*

This is law **L-W10**, and it is *literally* the same comparison **L-12** makes
when one version replaces another — `refines`, on the schema lattice, written
once. They were one relation implemented twice, and two implementations of one
order eventually disagree in the direction of permitting more.

It is checked at warrant time rather than at publish, because a featureset does
not belong to a model: whether it provides what a particular kernel reads is only
answerable once both are named.

Be precise about the direction. The check is **contravariant in inputs**, so a
*wider* featureset passes — it provides everything the six-slot kernel asked for,
and the extra columns are simply not read. That is correct and deliberate: a set
carrying more than one model needs is the ordinary case, and refusing it would
make sets unshareable, which is what they exist for. What cannot happen is the
failure that matters: fitting a kernel over a set missing something it declares.
(The label slot is excluded from the comparison — a kernel does not read its own
answer.)

## The fit warrant

```bash
POST /api/v1/fit-warrants
{"urn": "maya://model/re.price.nj_linear",
 "environment": "lab",
 "principal": "svc/model-lab",
 "declared_use": "model_development",
 "featureset": "nj_home_core",
 "featureset_version": 1,
 "window": {"from": "2019-01-01", "to": "2024-12-31"},
 "as_of": "2025-01-15T00:00:00Z"}
```

What comes back is a signed warrant whose `data.inputs[0]` carries far more than
you sent: the set, the version, the digest, the entity and grain, every slot, the
label, the outcome window, the pinned namespaces and the point-in-time rule. The
schema travels *with* the warrant, so an engine needs no access to the register
to know what it is reading.

`featureset` is one of the grammar's twelve data bindings, and it requires the
set and the version. An `as_of` is **not** required in general — scoring may
legitimately read a featureset at whatever is current — and **is** required for a
fit, by L-W9.

Checks, in the order they fire:

1. **Is the model blocked?** An open blocking finding stops a fit warrant exactly
   as it stops a score — `blocked`, 423.
2. **Is the principal entitled, is the grant live, is the use approved?**
3. **L-W10** — does `nj_home_core@v1` provide the six inputs the kernel declares,
   at compatible types? Missing slots are named.
4. **L-W1** — is `fit` meaningful for this class? T2, so yes.
5. **L-W3** — is every input read from a source that can be read as-of?
   `featureset`, `feature_namespace` and `dataset_snapshot` qualify; nothing else
   does.
6. **L-W9** — for a fit, both clocks bounded: an `as_of`, and a window with a
   start *and* an end. An unbounded read is refused, because a training set
   assembled from an unbounded source cannot be shown point-in-time correct.
7. **L-W4** — does it say where the parameters go? `sink: parameter_object`.
8. **L-W8** — a fit's parameter source must be `to_be_fitted`, and nothing else's
   may be.

Only then is it signed. MAYA validates every warrant **before** signing, never
after.

## Running the fit

If the version's kernel declares the `estimator` runtime, MAYA can run the fit
itself. Assemble the training set from the featureset version, then:

```http
POST /api/v1/parameter-fits
{
  "urn": "maya://model/re.price.nj_linear",
  "snapshot_id": "01a06d…",
  "environment": "lab",
  "principal": "svc/model-lab",
  "declared_use": "model_development",
  "window": {"from": 1546300800.0, "to": 1735603200.0},
  "name": "ols_v1"
}
```

Six things happen, in this order, and the order is the point:

1. **The window is checked first.** `window_required` (422) if absent,
   `window_inverted` if it runs backwards. Cheapest, and it is a statement about
   the fit rather than about the data.
2. **The snapshot is loaded and must name a featureset version.** A snapshot
   assembled from loose views has no answer to *which schema did these columns
   come from* — `snapshot_not_from_a_featureset`, 409.
3. **The warrant is resolved.** Authority before data: a read performed under an
   authority that turns out not to exist has already happened.
4. **The snapshot must be point-in-time verified.** `snapshot_not_pit_verified`,
   409. A snapshot MAYA itself flagged cannot quietly become the basis of an
   approved parameter set.
5. **The rows are read at the Delta version the snapshot pinned**, not at the
   head. Run the same fit twice and it sees the same bytes even if the table has
   been written to since. Without that, *"reproduce this fit"* has no meaning and
   neither does replaying the validation that used it.
6. **The estimator runs, and the result is recorded through the ordinary
   register** — which means it arrives `proposed`. The person who ran the fit
   still cannot approve it.

You must state the **window**. MAYA will not derive it from the rows: the period
a fit is *for* is a governance statement — *"estimated over 2019 to 2024"* —
which happens to be reported by the data but is not defined by it. Reading it off
whatever rows arrived would turn the claim into a description of the extract.

### What it refuses, and why

| Refusal | Status | Why it is not a warning |
|---|---|---|
| `collinear_regressors` | 422 | The solver would return one of infinitely many answers, and the coefficient a validator reads would be an artefact of the solver |
| `value_not_numeric` | 422 | Dropping or zeroing a missing value changes the population the fit speaks for without saying so. Put a fill policy on the featureset, where the decision is on the record |
| `too_few_rows` | 422 | Under thirty rows, the diagnostics look like results |
| `fit_did_not_converge` | 422 | Three numbers from a search that stopped early look exactly like three from one that finished |
| `target_is_a_regressor` | 422 | The fit would predict the answer from the answer |
| `series_is_constant` · `not_identified` | 422 | There is nothing to estimate, and a number would imply there was |
| `window_required` · `window_inverted` | 422 | See above |
| `snapshot_not_pit_verified` | 409 | The snapshot is marked, and a fit that ignores the mark launders it |
| `no_captive_engine` | 501 | This instance issues warrants and runs nothing; record a fit performed elsewhere instead |

Diagnostics travel with the parameter set. For OLS: `n`, `k`,
`degrees_of_freedom`, `r_squared`, `adjusted_r_squared`, `residual_std_error`,
per-name `standard_errors` and `t_statistics`, and the **condition number**,
which is the one to read first — in the thousands, the coefficients are a
solution to this sample rather than a property of the world. MAYA adds the
family, the row count, the snapshot, the Delta version and the elapsed time.

MAYA does not decide whether a fit is any good. It puts the numbers in front of
somebody who can.

## Recording what came back

```json
POST /api/v1/parameters
{
  "urn": "maya://model/re.price.nj_linear",
  "semver": "1.0.0",
  "name": "nj_home_core-fit-2025-01-15",
  "kind": "estimated_coefficients",
  "provenance": "fitted",
  "warrant_id": "wrt_7f31",
  "featureset": "nj_home_core",
  "featureset_version": 1,
  "snapshot_id": "01a06d…",
  "window": {"from": 1546300800.0, "to": 1735603200.0},
  "as_of": 1736899200.0,
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
  "diagnostics": {"r_squared": 0.783, "n": 41208,
                  "residual_std_error": 62114.20, "condition_number": 47.2}
}
```

The negative `bedrooms` coefficient is not a bug and is worth a sentence: holding
floor area fixed, more bedrooms means *smaller* bedrooms. A register that stores
the coefficients makes that visible to a reviewer instead of leaving it in a
notebook.

**MAYA accepts a fitted parameter set only against a warrant it issued.** The
refusals are specific, and there is no back door:

| Refusal | Status | |
|---|---|---|
| `warrant_required` | 422 | a fitted set must name the warrant it was produced under; without it, *which data produced these numbers* has no answer |
| `unknown_warrant` | 404 | MAYA did not issue it |
| `warrant_revoked` | 410 | nothing produced under a revoked warrant may be taken into the register |
| `warrant_names_another_model` | 409 | issued, for something else |
| `warrant_names_another_version` | 409 | issued for this model, pinned to a different version |
| `featureset_required` | 422 | a fitted set must name the featureset version that produced it |

Refusals are keyed on the **kernel** rather than on the label a caller supplied:
a `fitted` set against a model whose `parameter_kind` is `none` is refused as
`nothing_to_fit`, and against an `opaque` one as `parameters_not_reachable` —
both 422, both pointing at `declared` as the honest provenance. That is the T0 and
T6 case arriving from the other direction, and nobody has to remember which
models train.

Three more kinds are covered the same way, as `not_obtained_from_data`:

| `parameter_kind` | Filled by | Class |
|---|---|---|
| `rule_set` | an author | T8 |
| `llm_configuration` | somebody assembling a system | T5 |
| `elicited_weights` | an expert panel | T7 |

None of the three is a quantity a procedure over data produces, so for them
`declared` is the only admissible provenance — `calibrated` is refused as well
as `fitted`, because `calibrated` means solved against market data under an
approved procedure and a panel is not that either.

This matters more than it looks. `fitted` is the strongest claim the register
offers, and claiming it for a judgment **launders an opinion into a
measurement**: once the row says the numbers came from data, nobody goes
looking for the panel, the elicitation protocol or the dissent — which are the
only evidence a judgment has.

A parameter set is **immutable**, **versioned per model version**, and **does not
create a new model version** — the kernel did not change; only `P` was
re-inhabited.

### Review

A set lands `proposed` and moves to `approved` or `rejected`:

```bash
POST /api/v1/parameter-sets/{parameter_set_id}/review
{"accept": true, "note": "Diagnostics reviewed; condition number acceptable."}
```

**The person who recorded them may not approve them** — `self_approval`, 403,
comparing `person/d.raman` and `d.raman` as the same human. Rejection requires a
reason (`reason_required`, 422). A set already reviewed cannot be reviewed again
(`already_reviewed`, 409).

Values are held inline up to **4,096** of them. Past that the set is refused as
`parameters_too_large` (413) — *"an artifact rather than a record"* — **unless**
you supply a `values_uri` naming them in the artifact store, in which case the
set is accepted with the values held out of line and the cardinality recorded.
Silent truncation is the one thing that does not happen.

### Three ways parameters arrive

`GET /api/v1/parameter-provenance` publishes the three, and the difference is
what evidence each one owes:

| Provenance | Typical classes | Means | Needs a warrant |
|---|---|---|---|
| **fitted** | T2 · T3 · T4 · T5 | estimated or trained from data, under a fit warrant MAYA issued | **yes** |
| **calibrated** | T1 | solved against market data under an approved procedure, often daily — *the procedure* is approved, not each morning's result | no |
| **declared** | T0 · T7 · T8 | asserted by a person, and attested rather than fitted | no |

Only `fitted` requires a warrant, because it is the only one where MAYA can check
the claim: it issued the warrant, so it knows which featureset version and which
window produced the numbers.

### One of the three has a shape

`declared` covers T0's constants, T7's elicited weights and **T8's rule sets**,
and until recently all three were held the same way: a JSON document in `values`,
versioned, digested, approved by a second person, and completely opaque. MAYA
could tell you a rule set had changed and not one thing about what it said.

A rule set now has a structure the platform can read — ordered rules, first match
wins, a required `otherwise`, a required `because` per rule — and four checks run
before it can be recorded: nothing falls through, no rule is shadowed by any
the earlier rules singly or together, no two rules with the same condition disagree, and every
field a rule reads is one the version's input schema declares. Publishing one is
this same `POST /parameters` act with the same consequences: the set lands
`proposed`, and whoever wrote it may not approve it.

Everything on this page about review, immutability, digests and the alias gate
applies to a rule set unchanged. What is different is that you can read it.
See [Rule sets](/help/rule-sets).

### What the alias gate does and does not read

Approval governs the parameter set record, and **the alias gate does not read
it.** An alias move checks that the *model version* is approved and nothing else.

What actually keeps an unapproved point of `P` out of the serving path is two
other things: resolving a parameter set for a run returns only `approved` sets
(`no_approved_parameters`, 409, when there is none), and the engine re-derives
the digest of the values it loaded before running them. Worth knowing which
control is doing the work.

## The run warrant

```json
{
  "subject":   {"urn": "maya://model/re.price.nj_linear", "semver": "1.0.0"},
  "operation": {"verb": "score", "deterministic": true},
  "parameters":{"kind": "estimated_coefficients",
                "source": {"binding": "parameter_set",
                           "parameter_set": "nj_home_core-fit-2025-01-15",
                           "digest": "sha256:b71e…"}},
  "data": {"inputs":  [{"binding": "request"}],
           "outputs": [{"sink": "response"}]}
}
```

`parameters.source` is an **object**, not a string, and for a `parameter_set`
binding it carries both the set and its digest — that is what **L-W8** requires.
Model version *and* point of `P`, both named: a warrant that names a kernel and
leaves its parameters implicit describes an outcome nobody can reproduce. With
both pinned the run is determined — same kernel, same point in `P`, same input,
same answer.

Before anything runs, the engine reads the values and **re-derives** their
digest. It does not compare the stored digest against the warrant's: those are
two copies of the same claim, and they would agree happily over values somebody
had edited underneath them. And a runtime never fetches its own parameters — one
that did would be choosing which numbers it ran on, and that is the decision the
approval exists to make.

And the appraiser querying a price sees a number whose provenance runs all the
way back: through the parameter set, to the featureset version, to the pinned
Delta namespaces, to the rows that were true and known on 15 January 2025.

## The training record

Until recently that whole path existed and nobody could read it. A model
recalibrated every morning produces **two hundred and fifty governed acts a
year**, each with a warrant behind it and a signature on it, and none of them had
a record anybody could open.

So a **training record is compiled per parameter set**, from what the register
already holds:

```bash
GET  /api/v1/training-records/{parameter_set_id}/preview   # render it, author nothing
POST /api/v1/training-records/{parameter_set_id}           # file it
```

Six sections, and each one is a question somebody actually asks:

| Section | Answers |
|---|---|
| **What this is** | which model version, which point of `P`, who recorded it |
| **Under what authority** | the fit warrant, its principal, its declared use |
| **What it read** | the featureset version, the window, the `as_of`, the snapshot |
| **What it produced** | the values, or where they are held |
| **What the fit reported** | the diagnostics the estimator returned |
| **Who accepted it** | the reviewer, the decision, the note |

Compiled rather than written, and that is the point: all of them exist whether or
not somebody had time to write one, and the one that needs a human note has a
place to put it — an attachment against the same subject.

**A section that cannot be filled is a named gap, not a blank.** A fitted set
with no warrant has no answer to *which data produced these numbers*, and that is
worth saying out loud rather than leaving a heading with nothing under it.

## The dossier

A parameter set's record is one node. The **dossier** walks the whole graph from
a model and shows the rest:

```bash
GET /api/v1/dossiers/{name}     #  and the page at /dossier/{name}
```

```
model
 ├── attached: methodology paper, literature, vendor note
 ├── compiled: model development document, model card, Annex IV
 └── version 1.0.0
      ├── attached: kernel specification
      ├── compiled: validation report
      ├── parameter set ps-8817        (fitted 2026-03-31)
      │    ├── compiled: training record
      │    └── attached: convergence study
      └── fitted from  featureset nj_home_core @ v1
           └── feature property_age
                └── attached: business definition
```

Documentation is filed against **six kinds of subject** — `model`,
`model_version`, `parameter_set`, `featureset_version`, `feature`, `validation` —
and three of them are **pinned by construction**: `model_version`,
`parameter_set` and `featureset_version`. `featureset` is deliberately absent
from the vocabulary rather than discouraged in a comment, because a document
filed against the *set* would describe something that has since moved.

The dossier is **computed, never stored.** Its inputs are all versioned or
immutable, so there is nothing to keep in step — and a stored dossier would be a
second account of the model's documentation, able to disagree with the first.

**Every node with nothing filed is a named gap**, with what was expected. A page
that silently omits what it could not find reads as complete, and a reader cannot
tell a thin model from a thin page unless the page says which it is.

It travels whole into an **export pack**, which carries the same graph — digested
member by member, byte-identical for the same state — to somebody who will never
be given a login. See [Documentation](/help/documentation).

## What this does not do

**It is not feature engineering.** The expression language is small on purpose
and has no windows or lags. Anything needing a library, a join or a model is
declared `external`: MAYA keeps the definition, the lineage and the checks, and
says plainly that it did not compute the values.

**It fits two families and no more.** The captive engine estimates `ols` and
`garch11` — enough that the whole path from a featureset version to an approved
point of `P` can be walked without leaving the platform, and every control on
that path exercised against a real fit rather than a hand-written dictionary.
Anything else is estimated in an execution engine and delivered back, which is
the same boundary drawn everywhere else. It is not a modelling library and does
not want to become one.

**It does not choose your features.** No automatic selection, no importance
ranking, no suggestion engine. It records what you chose, pins it so it cannot
move underneath you, and refuses the combinations that are type errors.

**It authors exactly one kind of parameter object, and no artifacts.** A T8 rule
set can be typed into MAYA, because a rule set's provenance *is* its authorship —
that is what `declared` means. There is deliberately no ONNX or PMML editor:
those formats serialize a *fitted* map, and hand-authoring one would put an
artifact in the register that had never been trained or validated and was
indistinguishable from one that had. See [Rule sets](/help/rule-sets).

**It does not yet guard feature retirement.** Lineage is recorded and reported,
so *"what breaks if this goes"* is answerable in one call. But the only wired
retirement check is the one on feature view versions, and it consults model
version contracts rather than featureset pins — the featureset-side check exists
and reaches no route. Read the pins before you delete anything.
