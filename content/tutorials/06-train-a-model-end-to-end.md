---
title: Training a model, end to end
slug: train-a-model
section: The platform
order: 45
icon: calculator
summary: An ordinary least squares regression on New Jersey house prices, told as the seven refusals a real fit meets — a regressor derived from the label, an unbounded read, coefficients with no warrant behind them, an approval by their author, a widened featureset — and the record that gets compiled at the end because it went right.
audience: Data scientists, Model developers
---

# Training a model, end to end

Training does not change the model. `f : P ⊗ X → D(Y)` is fixed the moment the
version exists; a fit **inhabits `P`**, and produces a point rather than a new
kernel.

Which means the interesting question about a fit is not *did it converge*. It is
**which data produced these numbers, and can anybody check.** Almost everything
that goes wrong in a fit goes wrong in the data, quietly, and shows up months
later as a model that scored well and then did not.

So this walkthrough is organised around the seven places the platform refuses,
on a model small enough to check by hand: an OLS regression predicting
residential sale prices in New Jersey. Substitute your own credentials for
`d.raman` (model developer), `j.okafor` (model owner) and `a.mehta` (validator);
the separation between them is the point of several steps.

---

## 1 · The primitives

A feature is a *meaning*, not a column: an entity, a type, an owner and a
definition.

```bash
for f in 'living_area_sqft numeric' 'lot_size_sqft numeric' \
         'bedrooms integer' 'bathrooms numeric' 'year_built integer' \
         'municipality_code categorical' 'sale_price numeric'; do
  set -- $f
  curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/features \
    -H 'Content-Type: application/json' -d @- <<JSON
{"name": "$1", "entity": "property_id", "dtype": "$2",
 "description": "NJ residential $1", "owner": "person/j.okafor"}
JSON
done
```

`sale_price` is defined alongside the rest. It becomes the **label** when a
featureset says so — the role belongs to the set, not to the feature, because
the same quantity is an outcome in one model and an input in another.

---

## 2 · What the model actually reads

A hedonic price model is not linear in floor area; it is linear in *log* floor
area. So the regressor is a **derived feature** — declared, not computed in a
notebook and pasted in.

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "log_living_area",
    "expression": "log(living_area_sqft)",
    "dtype": "numeric",
    "description": "Price responds to area multiplicatively"}'
```

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "lot_to_living_ratio",
    "expression": "lot_size_sqft / living_area_sqft",
    "dtype": "numeric", "description": "Plot generosity, scale-free"}'
```

Two things happen without you asking. The lineage is recorded, and the ingest
clock of the derived value is the **maximum** over its inputs: you did not know
`lot_to_living_ratio` before you knew both the lot size and the floor area, and
stamping it earlier would make a point-in-time assembly quietly include a value
nobody could have used. That is not a convention to remember — it is a
homomorphism out of the derivation, and a homomorphism has no exceptions to
forget.

### The row's own clock

A third one, and the reason it is worth its own paragraph:

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "property_age", "expression": "year(event_ts) - year_built",
    "dtype": "numeric", "description": "Age of the house at the sale date"}'
```

`year(event_ts)` reads **the row's own event clock**, so a 1962 house is 57 in a
2019 sale and 62 in a 2024 one. Reading today's date instead would make the
feature depend on when you happened to assemble the training set, which is the
kind of error that never shows up in a metric.

There is no `year()` function. The spelling is rewritten to a plain name before
the expression is parsed, deliberately: a function taking a timestamp would be
the first step towards a date library living inside the expression language.

### **Refusal 1** — the language is small, and says so

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "median_sale_price",
    "expression": "median(sale_price)", "dtype": "numeric",
    "description": "Median sale price across the book"}'
```

```
409 — 'median' is not one of the functions this language provides:
abs, ceil, exp, floor, log, max, min, round, sqrt
```

Nine functions, arithmetic, comparison and a conditional, and nothing else — no
attribute access, no subscripting, no comprehensions, no lambdas, no imports.
Ask before you write one:

```bash
curl -s localhost:5006/api/v1/expression-language | jq '.functions[].name'
```

The line this draws is the one the platform draws everywhere else. **MAYA
transforms features it already holds; it does not run models.** Computing `x / y`
over a stored column is the same class of act as computing the null rate MAYA
already reports for every materialisation. Running a kernel is not.

### What `external` does, and what it does not

An expression MAYA should not *evaluate* — because it is expensive, or because
your pipeline already computes it — is declared `external`:

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "baths_per_bed",
    "expression": "bathrooms / bedrooms", "dtype": "numeric",
    "evaluator": "external",
    "description": "Already computed in the loading pipeline"}'
```

The definition is still kept, so **lineage and the leakage check still apply**,
and the values arrive by materialisation like any primitive. Ask MAYA to compute
one and it refuses rather than quietly returning nulls:

```
409 — 'baths_per_bed' is declared external, so MAYA does not compute it;
materialise its values like any primitive — the definition is still kept, so
lineage and the leakage check still apply
```

**Be clear about what this is not.** `external` is *not* an escape from the
language: the expression is parsed before the evaluator is looked at, so
`median(sale_price)` is refused whether you declare it internal or external.
For a quantity the language genuinely cannot express, the only route is to
define it as a **primitive** feature and materialise the values — and the cost is
real and worth stating: a primitive has no lineage, so the leakage check cannot
see through it. If that quantity is derived from your label, nothing here will
catch it.

---

## 3 · Materialise, and look both ways along the lineage

```bash
curl -su d.raman:dev-pw -X POST \
  localhost:5006/api/v1/feature-views/nj_characteristics/materialise \
  -H 'Content-Type: application/json' -d '{"rows": [
    {"entity_id": "P1", "event_ts": 1717200000, "ingest_ts": 1717200000,
     "living_area_sqft": 1840, "lot_size_sqft": 7250, "bedrooms": 3,
     "bathrooms": 2.5, "year_built": 1962, "municipality_code": "MONTCLAIR",
     "log_living_area": 7.5175, "lot_to_living_ratio": 3.9402,
     "property_age": 62}]}'
```

```bash
curl -s localhost:5006/api/v1/derived-features/living_area_sqft/lineage
```

```json
{"feature": "living_area_sqft",
 "rests_on": [],
 "depended_on_by": ["log_living_area", "lot_to_living_ratio"]}
```

Two directions, two different questions. `depended_on_by` answers *what breaks
if this changes* — which is why you cannot retire it. `rests_on` answers *what
data does this ultimately read*: the free variables, base features and nothing
else.

---

## 4 · Declare the featureset

A featureset is a **schema** — named slots with types. It is what the kernel is
defined over.

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' -d '{
    "name": "nj_home_core",
    "entity": "property_id",
    "label_slot": "sale_price",
    "outcome_window_days": 0,
    "slots": {
      "log_living_area":     "numeric",
      "lot_to_living_ratio": "numeric",
      "bedrooms":            "integer",
      "bathrooms":           "numeric",
      "property_age":        "numeric",
      "municipality_code":   "categorical",
      "sale_price":          "numeric"}}'
```

Then a **version fills it**, pinning each slot to a feature and to the exact
feature view version supplying its values:

```bash
curl -su d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/nj_home_core/versions \
  -H 'Content-Type: application/json' -d '{"bindings": {
    "log_living_area": "log_living_area",
    "lot_to_living_ratio": "lot_to_living_ratio",
    "bedrooms": "bedrooms", "bathrooms": "bathrooms",
    "property_age": "property_age",
    "municipality_code": "municipality_code",
    "sale_price": "sale_price"}}'
```

### **Refusal 2** — a regressor derived from the label

Define one more derived feature first:

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "price_per_sqft",
    "expression": "sale_price / living_area_sqft", "dtype": "numeric",
    "description": "Price per square foot"}'
```

That is **accepted**. `price_per_sqft` is a perfectly good quantity and somebody
may want it on a dashboard. What is refused is *binding it into a featureset
whose label is `sale_price`*:

```json
{"bindings": {"log_living_area": "price_per_sqft", …}}
```

```
409 — 'price_per_sqft' is computed from 'sale_price', which this featureset
declares as its label — a feature derived from the label leaks the answer into
the training set. Derive it from a value known before the outcome, or declare it
an output rather than a feature.
```

The check walks the whole lineage, so a derivation of a derivation of the label
is caught too. And it runs **before** the view lookup, so you get that message
rather than *no view supplies that*.

The plan is what an engine reads:

```bash
curl -s localhost:5006/api/v1/featuresets/nj_home_core/versions/1
```

```json
{"featureset": "nj_home_core", "version": 1, "entity": "property_id",
 "digest": "sha256:…",
 "pit_rule": "event_ts <= label_ts AND ingest_ts <= as_of",
 "label": {"feature": "sale_price",
           "namespace": "features/property_id/nj_transactions/v1"},
 "slots": [{"slot": "bedrooms", "feature": "bedrooms",
            "namespace": "features/property_id/nj_characteristics/v1",
            "view_version": 1, "delta_version": 0}, …],
 "namespaces": ["features/property_id/nj_characteristics/v1",
                "features/property_id/nj_transactions/v1"],
 "pins": [["features/property_id/nj_characteristics/v1", 0], …]}
```

---

## 5 · The fit warrant

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/re.price.nj_linear", "environment": "lab",
    "principal": "svc/model-lab", "declared_use": "model_development",
    "featureset": "nj_home_core", "featureset_version": 1,
    "window": {"from": 1546300800, "to": 1735603200},
    "as_of": 1736899200}'
```

`warrant:issue` sits with the model owner, so `d.raman` cannot mint this. What
comes back is the ten-section document, with the resolved plan inside it:

```json
{"operation": {"verb": "fit"},
 "parameters": {"kind": "estimated_coefficients",
                "source": {"binding": "to_be_fitted"}},
 "data": {"inputs": [{"binding": "featureset", "featureset": "nj_home_core",
                      "version": 1, "digest": "sha256:4c1f9d7e…",
                      "window": {"from": 1546300800, "to": 1735603200},
                      "as_of": 1736899200}],
          "outputs": [{"sink": "parameter_object"}]}}
```

Five things were established before it was signed:

| | Law | What it asks |
|---|---|---|
| 1 | **L-W1** | is `fit` meaningful for this class? T2, so yes. A closed-form pricer would be refused here — *its parameters come from theory, not from data* |
| 2 | **L-W3** | can the source be read as-of? A `featureset` binding can |
| 3 | **L-W9** | is the read bounded in both clocks? |
| 4 | **L-W10** | does `nj_home_core` provide what the kernel declares it reads? |
| 5 | **L-W4** | does it say where the parameters go? |

### **Refusal 3** — an unbounded read

Drop the `as_of`:

```json
{"law": "L-W9", "path": "data.inputs[0].as_of",
 "detail": "a featureset read for fitting must say as of when it is read;
            without it the assembly reads whatever has since arrived",
 "remediation": "pin as_of to the moment the training set is assembled at"}
```

Drop the window and you get the second half of the same law. **The featureset
fixes the columns; the warrant fixes the period.** That is why `window` and
`as_of` are here and not in the set — the same set trains 2019–23 and 2020–24
without becoming two sets.

L-W9 applies to a bare `feature_namespace` too, and not only to featuresets. A
fit from a raw namespace with no bounds is *everything we know now*, which is
precisely what the law exists to refuse.

MAYA does not fit anything at this point. It signs this and waits.

---

## 6 · Take delivery of the coefficients

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/re.price.nj_linear", "semver": "1.0.0",
    "name": "nj-core-2025q1", "kind": "estimated_coefficients",
    "provenance": "fitted",
    "warrant_id": "wrt_01a06d3f8b21",
    "featureset": "nj_home_core", "featureset_version": 1,
    "window": {"from": 1546300800, "to": 1735603200},
    "as_of": 1736899200,
    "values": {"intercept": -142380.55, "log_living_area": 108422.31,
               "lot_to_living_ratio": 6218.04, "bedrooms": -4102.77,
               "bathrooms": 21845.90, "property_age": -1187.62,
               "municipality_code[MONTCLAIR]": 88214.03},
    "diagnostics": {"r_squared": 0.783, "n": 41208,
                    "condition_number": 41.2}}'
```

```python
maya.parameters.record(
    urn="maya://model/re.price.nj_linear", semver="1.0.0",
    name="nj-core-2025q1", kind="estimated_coefficients",
    warrant_id=grant["warrant_id"], featureset="nj_home_core",
    featureset_version=1, values={…}, diagnostics={…})
```

`warrant_id` is a keyword in the SDK rather than a dictionary entry, so omitting
it is a visible mistake.

### **Refusal 4** — numbers with no data behind them

Drop it:

```json
{"error": "warrant_required",
 "detail": "a fitted parameter set must name the warrant it was produced under;
            without it, which data produced these numbers has no answer",
 "remediation": "issue a fit warrant and quote its id, or record this with
                 provenance 'declared' if nobody fitted it"}
```

### **Refusal 5** — coefficients with no columns

Drop `featureset`:

```json
{"error": "featureset_required",
 "detail": "a fitted parameter set must name the featureset version it was
            fitted from; the coefficients mean nothing without the columns they
            belong to",
 "remediation": "quote the featureset and version the fit warrant named"}
```

Three provenances exist and they are genuinely different governance, not three
words for one thing: `fitted` needs a warrant, `calibrated` is solved under an
approved procedure, `declared` is asserted by a person and attested rather than
fitted. Record `declared` values against a `parameter_kind: none` kernel and you
get `nothing_to_fit` — *its parameters come from theory, so there is nothing a
fit could have produced.*

The negative `bedrooms` coefficient is worth a moment. Holding floor area fixed,
more bedrooms means *smaller* bedrooms. Storing the coefficients puts that in
front of a reviewer instead of leaving it in a notebook — and the diagnostics
are the point of the exercise. Read the **condition number before the R²**: at
41 these coefficients are a property of the world; in the thousands they are a
solution to this sample. MAYA does not judge the fit. It puts the number where
somebody who can has to look at it.

Above `MAX_INLINE_VALUES` — 4,096 — the values stop being a record and belong in
the artifact store with their digest here. A coefficient vector is a record;
twenty million weights are a file. See [the neural
network](/tutorials/neural-network-end-to-end).

---

## 7 · **Refusal 6** — approving your own numbers

```bash
curl -su a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/$ID/review \
  -H 'Content-Type: application/json' \
  -d '{"accept": true, "note": "residuals and influence reviewed; condition 41"}'
```

`d.raman` is refused twice over: a model developer holds no `parameter:approve`
permission at all, and even a principal whose role would let them through is
refused:

```json
{"error": "self_approval",
 "detail": "d.raman recorded these parameters and cannot also approve them",
 "remediation": "a parameter set changes what the model does; approval is by
                 somebody other than whoever produced it"}
```

A role grant is a policy that can change. Segregation of duty is read from the
evidence chain, so it cannot be granted around.

Until somebody accepts them:

```bash
curl -s "localhost:5006/api/v1/parameters?urn=maya://model/re.price.nj_linear&semver=1.0.0"
```

```json
{"ready": false,
 "detail": "parameters recorded but none approved, so nothing may run yet",
 "parameter_sets": [{"name": "nj-core-2025q1", "state": "proposed", …}]}
```

---

## 8 · The document nobody had to write

This is what the discipline was for. Every field of the record already exists in
the register, so it is **compiled** rather than authored:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/training-records/$ID
```

Six sections — *what this is*, *under what authority*, *what it read*, *what it
produced*, *what the fit reported*, *who accepted it* — with coverage reported
alongside:

```json
{"kind": "training_record", "title": "Training Record — nj-core-2025q1",
 "subject_type": "parameter_set", "subject_id": "01a06d51f9c3",
 "coverage": {"sections": 6, "filled": 6, "missing_required": [],
              "complete": true}}
```

`GET …/training-records/$ID/preview` shows what it would say without authoring
it.

Compiling rather than writing is the whole point. A model recalibrated every
morning produces **two hundred and fifty governed acts a year**, each with a
warrant behind it and a signature on it, and until this existed none of them had
a record anybody could read. Compiling means all of them exist whether or not
somebody had time — and the one that needs a human note has a place to put it,
as an attachment against the same subject:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/attachments \
  -F urn="maya://model/re.price.nj_linear" -F kind=other \
  -F title="nj-core-2025q1 — influence diagnostics" \
  -F subject_type=parameter_set -F subject_id=$ID \
  -F file=@influence.md
```

A fit with **no warrant behind it** is a **named gap** in the authority section
rather than a blank one. A page that silently omits what it could not find reads
as complete, and a reader cannot tell a thin fit from a thin page unless the
page says which it is.

---

## 9 · Run it, at a named point of `P`

```json
{"operation": {"verb": "score"},
 "parameters": {"kind": "estimated_coefficients",
                "source": {"binding": "parameter_set",
                           "parameter_set": "01a06d51f9c3",
                           "digest": "sha256:c4e7…"}},
 "data": {"inputs": [{"binding": "request"}],
          "outputs": [{"sink": "response"}]}}
```

Both pinned, so the run is determined: same kernel, same point of `P`, same
input, same answer. **L-W8** refuses each of `to_be_fitted` and `parameter_set`
in the other's position — a fit that claims to *read* parameters has the
direction backwards, and a score that will not name its inhabitant produces a
number attributable to nothing.

The engine **re-derives** the digest from the values before running. Values
edited underneath the register produce `parameter_mismatch`, which is a security
event, not a bad request.

---

## 10 · New data does not move an old set

Materialise `nj_characteristics@v2` with 2025 sales. **`nj_home_core@v1` does
not move.** Whoever fitted against it can still reproduce it exactly, byte for
byte, because every binding pins a Delta version.

Taking up the new data is a deliberate act:

```bash
curl -su d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/nj_home_core/roll-forward
```

```json
{"version": 2, "moved": [
  {"slot": "bedrooms",
   "was": "bedrooms @ features/property_id/nj_characteristics/v1",
   "now": "bedrooms @ features/property_id/nj_characteristics/v2"}]}
```

Same schema, so the same model version can be fitted against it — and MAYA
confirms that rather than you assuming it.

---

## 11 · **Refusal 7** — the one that earns the whole structure

Add `school_rating` and `distance_to_nyc_km`. The schema is now nine slots, not
seven, and a linear model's coefficient vector has one entry per column:

```
409 — 'nj_home_core' does not provide school_rating, distance_to_nyc_km,
which this version declares it reads. Bind a featureset whose schema covers the
kernel's inputs, or create a model version whose input schema matches this set —
adding a regressor is a model change, not a data change.
```

That is **L-W10**, discharged at warrant issuance against the register, and it
is the same comparison **L-12** makes when one version replaces another — one
partial order in `core/domain/lattice.py`, written once rather than four times.

So you create `re.price.nj_linear@2.0.0` over the nine slots. Now there are two
model versions and two featuresets, and they can be compared honestly, because
each run says exactly which data it saw.

Widening a featureset under a model that was never defined over it is the
failure all of this exists to make visible.

---

## What to read next

| | |
|---|---|
| [A linear regression, end to end](/tutorials/linear-regression-end-to-end) | the same shape with MAYA's own estimator running the fit, through to a champion serving in production |
| [The whole path](/tutorials/the-whole-path) | featuresets composed from featuresets, models composed from models, and the documentation graph at the end |
| [Every kind of model, worked](/tutorials/every-kind-of-model) | the other six ways `P` gets inhabited |
