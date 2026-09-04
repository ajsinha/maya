---
title: Training a model, end to end
slug: train-a-model
section: The platform
order: 45
icon: calculator
summary: A multiple linear regression on New Jersey home prices — primitive features, derived ones, a named featureset, a fit warrant, and the coefficients that come back and are approved before anything runs on them.
audience: Data scientists, Model developers
---

# Training a model, end to end

A model in MAYA is a parametric kernel, `f : P × X → D(Y)`. Training does not
change `f` — it **inhabits `P`**. This walkthrough goes round that loop once, on
a model small enough that you can check every number by hand: an ordinary least
squares regression predicting residential sale prices in New Jersey.

Everything below is a real request against a running instance. Substitute your
own credentials for `d.raman` (a model developer) and `a.mehta` (a validator);
the separation between them is the point of several steps.

---

## 1. Define the primitives

A feature in MAYA is a *meaning*, not a column: it has an entity, a type, an
owner and a definition.

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

`sale_price` is here with the rest. It becomes the **label** when a featureset
says so — the role is a property of the set, not of the feature, because the
same quantity can be an outcome in one model and an input in another.

---

## 2. Derive what the model actually reads

A hedonic price model is not linear in floor area; it is linear in *log* floor
area. So the regressor is a derived feature, declared rather than computed in a
notebook and pasted in:

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "log_living_area",
    "expression": "log(living_area_sqft)",
    "dtype": "numeric",
    "description": "Price responds to area multiplicatively"}'
```

Three more, each doing a job:

```json
{"name": "lot_to_living_ratio",
 "expression": "lot_size_sqft / living_area_sqft"}

{"name": "property_age",
 "expression": "year(event_ts) - year_built"}

{"name": "income_school_interaction",
 "expression": "median_income_zip * school_rating"}
```

`property_age` reads the row's **own event clock**, so a 1962 house is 57 in a
2019 sale and 62 in a 2024 one. Reading today's date instead would make the
feature depend on when you happened to assemble the training set, which is the
kind of error that never shows up in a metric.

Ask what the language admits before you write one:

```bash
curl -s localhost:5006/api/v1/expression-language | jq '.functions[].name'
```

Arithmetic, comparison, and nine total functions. Nothing else — no attribute
access, no imports, no calls that are not on the list. An expression needing more
is declared `"evaluator": "external"`: MAYA keeps the definition so lineage and
the leakage check still apply, and says plainly that it did not compute the
values.

### The one that gets refused

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
    "name": "price_per_sqft",
    "expression": "sale_price / living_area_sqft", "dtype": "numeric",
    "description": "price per square foot"}'
```

That one is accepted — `price_per_sqft` is a perfectly good quantity, and
somebody may want it on a dashboard. What is refused is *putting it in a
featureset whose label is `sale_price`*, which is step 4. Hold that thought.

---

## 3. Materialise, and look at the lineage

Feature values arrive by materialisation, with both clocks on every row:

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

Note the derived columns carry the **maximum** `ingest_ts` of their inputs. You
did not know `lot_to_living_ratio` before you knew both the lot size and the
floor area, and stamping it any earlier would make a point-in-time assembly quietly
include a value nobody could have used.

Lineage runs both ways:

```bash
curl -s localhost:5006/api/v1/derived-features/living_area_sqft/lineage
```

```json
{"feature": "living_area_sqft",
 "rests_on": [],
 "depended_on_by": ["log_living_area", "lot_to_living_ratio", "price_per_sqft"]}
```

Which is why you cannot retire it.

---

## 4. Declare the featureset

A featureset is a **schema** — named slots with types. It is what the kernel is
defined over.

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' -d '{
    "name": "nj_home_core",
    "entity": "property_id",
    "label_slot": "sale_price",
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

Now try the leaky one:

```json
{"bindings": {"log_living_area": "price_per_sqft", ...}}
```

> **409 —** `price_per_sqft` is computed from `sale_price`, which this featureset
> declares as its label — a feature derived from the label leaks the answer into
> the training set. *Derive it from a value known before the outcome, or declare
> it an output rather than a feature.*

The check walks the whole lineage, so a derivation of a derivation of the label
is caught too. And it runs **before** the view lookup, so you get that message
rather than "no view supplies that".

The plan is what an engine reads:

```bash
curl -s localhost:5006/api/v1/featuresets/nj_home_core/versions/1
```

```json
{"featureset": "nj_home_core", "version": 1,
 "pit_rule": "event_ts <= label_ts AND ingest_ts <= as_of",
 "label": {"feature": "sale_price",
           "namespace": "features/property_id/nj_transactions/v1"},
 "namespaces": ["features/property_id/nj_characteristics/v1",
                "features/property_id/nj_transactions/v1"]}
```

---

## 5. Issue the fit warrant

```json
{"subject":   {"urn": "maya://model/re.price.nj_linear", "semver": "1.0.0"},
 "operation": {"verb": "fit"},
 "parameters":{"kind": "estimated_coefficients",
               "source": {"binding": "to_be_fitted"}},
 "data": {
   "inputs": [{"binding": "featureset", "featureset": "nj_home_core",
               "version": 1,
               "window": {"from": "2019-01-01", "to": "2024-12-31"},
               "as_of":  "2025-01-15T00:00:00Z"}],
   "outputs": [{"sink": "parameter_object"}]}}
```

Four things are checked before it is signed:

| | Law | What it asks |
|---|---|---|
| 1 | **L-W1** | Is `fit` meaningful for this class? T2, so yes. A Black–Scholes closed form would be refused here — *"its parameters come from theory, not from data"*. |
| 2 | Schema | Does `nj_home_core` provide what the kernel declares it reads? |
| 3 | **L-W9** | Is the read bounded in both clocks? Drop the `as_of` and it is refused. |
| 4 | **L-W4** | Does it say where the parameters go? |

**The featureset fixes the columns; the warrant fixes the period.** That is why
`window` and `as_of` are here and not in the set — the same set trains 2019–2023
and 2020–2024 without becoming two sets.

MAYA does not fit anything. It signs this and waits.

---

## 6. Take delivery of the coefficients

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/re.price.nj_linear", "semver": "1.0.0",
    "name": "nj-core-2025q1", "kind": "estimated_coefficients",
    "provenance": "fitted",
    "warrant_id": "<the grant id>",
    "featureset": "nj_home_core", "featureset_version": 1,
    "as_of": 1736899200,
    "values": {"intercept": -142380.55, "log_living_area": 108422.31,
               "lot_to_living_ratio": 6218.04, "bedrooms": -4102.77,
               "bathrooms": 21845.90, "property_age": -1187.62,
               "municipality_code[MONTCLAIR]": 88214.03},
    "diagnostics": {"r_squared": 0.783, "n": 41208}}'
```

Drop `warrant_id` and it is refused:

> **422 —** a fitted parameter set must name the warrant it was produced under;
> without it, which data produced these numbers has no answer.

Drop `featureset` and it is refused too — the coefficients mean nothing without
the columns they belong to.

The negative `bedrooms` coefficient is worth a moment. Holding floor area fixed,
more bedrooms means *smaller* bedrooms. Storing the coefficients puts that in
front of a reviewer instead of leaving it in a notebook.

---

## 7. Somebody else approves them

```bash
curl -su a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/$ID/review \
  -H 'Content-Type: application/json' \
  -d '{"accept": true, "note": "residuals and influence reviewed"}'
```

`d.raman` cannot do this, twice over: a model developer holds no
`parameter:approve` permission at all, and the register refuses `self_approval`
even for a principal whose role would let them through. A role grant is a policy
that can change; segregation of duty is not.

Until then:

```bash
curl -s "localhost:5006/api/v1/parameters?urn=maya://model/re.price.nj_linear&semver=1.0.0"
```

```json
{"ready": false,
 "detail": "parameters recorded but none approved, so nothing may run yet"}
```

---

## 8. Run it

A scoring warrant names the model version **and** the parameter set:

```json
{"operation": {"verb": "score"},
 "parameters": {"kind": "estimated_coefficients",
                "source": {"binding": "parameter_set",
                           "parameter_set": "01a06d51f9c3",
                           "digest": "sha256:c4e7…"}},
 "data": {"inputs": [{"binding": "request"}],
          "outputs": [{"sink": "response"}]}}
```

Both pinned, so the run is determined: same kernel, same point in `P`, same
input, same answer. Law **L-W8** refuses each of `to_be_fitted` and
`parameter_set` in the other's position — a fit that claims to read parameters
has the direction backwards, and a score that will not name its inhabitant
produces a number attributable to nothing.

---

## 9. What happens when the data refreshes

Materialise `nj_characteristics@v2` with 2025 sales. **`nj_home_core@v1` does not
move.** Whoever trained on it can still reproduce it exactly.

Taking up the new data is a deliberate act:

```bash
curl -su d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/nj_home_core/roll-forward
```

which mints `@v2` and tells you what moved:

```json
{"version": 2, "moved": [
  {"slot": "bedrooms",
   "was": "bedrooms @ features/property_id/nj_characteristics/v1",
   "now": "bedrooms @ features/property_id/nj_characteristics/v2"}]}
```

Same schema, so the same model version can fit against it, and MAYA confirms that
rather than you assuming it.

---

## 10. What happens when you want another regressor

Add `school_rating` and `distance_to_nyc_km`, and the schema is different — nine
slots, not six. A linear model's coefficient vector has one entry per column, so
`re.price.nj_linear@1.0.0` cannot consume it:

> **`school_rating`, `distance_to_nyc_km` are not in this version's input schema.
> Adding a regressor is a model change, not a data change.**

So you create `re.price.nj_linear@2.0.0` over the nine. Now you have two model
versions and two featuresets, and they can be compared honestly — because each
run says exactly which data it saw.

That refusal is the whole structure earning its keep. Widening a featureset under
a model that was never defined over it is the failure all of this exists to make
visible.
