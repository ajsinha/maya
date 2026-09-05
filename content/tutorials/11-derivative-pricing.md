---
title: A derivative pricing model, end to end
slug: derivative-pricing-end-to-end
section: Worked models
order: 50
icon: calculator
summary: A closed-form option and bond pricer registered, warranted and served — the case where the parameter object is empty, there is nothing to train, and the governance question moves entirely onto the market data the warrant names. T0 is not a lesser model; it is a different shape.
audience: Quants, Model developers, Validators
---

# A derivative pricing model, end to end

Ask most model-risk systems for a closed-form pricer's training set and you get
an empty field, a "N/A", and eventually a control that everybody has learned to
ignore.

Here it is a **type error**, and that is the whole tutorial.

**What you are building.** A pricing service for vanilla instruments — a
discount factor, a fixed-rate bond, a European swaption under Black — served
through MAYA's QuantLib runtime.

| | |
|---|---|
| `P` is | **empty**. `P = I`, the terminal object |
| Filled by | it isn't. There is nothing to fill |
| `parameter_kind` | `none` |
| `fit_procedure` | `none` |
| Derived class | **T0** — not trainable, by construction |
| Runtime | `quantlib` |
| What is governed instead | the **inputs**: the curve, the vol, the conventions |

---

## 1 · Register it

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","name":"Vanilla pricer",
       "model_class":"markets.pricing","domain":"markets",
       "owner":"person/j.okafor","legal_entity":"LE-UK-01",
       "purpose":"Discounting, fixed-rate bonds and European swaptions"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/markets.pricing.vanilla/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"none","fit_procedure":"none",
                 "runtime":"quantlib",
                 "entry":{"instrument":"fixed_bond",
                          "pricing_engine":"discounting"},
                 "input_schema":[{"name":"curve","dtype":"structured"},
                                 {"name":"as_of","dtype":"timestamp"}],
                 "output_schema":[{"name":"clean_price","dtype":"numeric"},
                                  {"name":"dirty_price","dtype":"numeric"},
                                  {"name":"accrued","dtype":"numeric"}]}}'
```

That is the entire model definition. No featureset, no fit warrant, no
parameters — and none of those are *missing*.

### The refusal that proves the point

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","environment":"prod",
       "principal":"svc/model-lab","featureset":"anything",
       "featureset_version":1,"window":{"from":0,"to":1735603200}}'
```

```json
{"error": "nothing_to_fit",
 "detail": "markets.pricing.vanilla 1.0.0 is T0: its parameter object is the
            terminal object, so there is no point of P to move to",
 "remediation": "if this model does have parameters, the kernel declares the
                 wrong parameter_kind; fix the version rather than the warrant"}
```

The refusal does not say "no". It says **which fact about the kernel** made the
request incoherent, and where to correct it if the fact is wrong.

---

## 2 · So what *is* governed?

Everything that was going to be governed anyway, and one thing people usually
leave out.

| Governed | Where it lives |
|---|---|
| The **conventions** — day count, calendar, settlement days | the kernel `entry`, immutable in the version |
| The **curve** the price is struck against | a warrant input binding, pinned |
| The **volatility** for the swaption | likewise, and refused if absent |
| The **valuation date** | in the warrant, never defaulted to "today" |
| The **library version** | the engine's descriptor, recorded in the evidence |

The last one is the one that gets left out. A closed-form pricer whose library
was upgraded under it is a changed model, and the only way to notice is for the
run record to say which library priced it.

---

## 3 · Serve it

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","environment":"prod",
       "principal":"svc/pricing","declared_use":"end_of_day_valuation"}'

curl -u svc/pricing:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla#champion",
       "environment":"prod","principal":"svc/pricing",
       "declared_use":"end_of_day_valuation",
       "inputs":{"as_of":"2026-03-31",
                 "curve":{"kind":"zero","day_count":"Actual365Fixed",
                          "nodes":[{"tenor":"1Y","rate":0.0412},
                                   {"tenor":"5Y","rate":0.0388}]},
                 "instrument":{"face":1000000,"coupon":0.045,
                               "maturity":"2031-03-31","frequency":"semiannual",
                               "settlement_days":2}}}'
```

```json
{"outputs": {"clean_price": 102.84, "dirty_price": 103.96,
             "accrued": 1.12, "npv": 1039600.0}}
```

### The three refusals you will actually meet

```json
{"error": "no_evaluation_date",
 "detail": "this warrant does not carry as_of and the instrument does not imply one"}
```

Defaulting a valuation date to the wall clock is how a price gets reproduced
differently tomorrow. It is refused rather than guessed.

```json
{"error": "malformed_curve",
 "detail": "the zero curve has a 5Y node before its 1Y node"}
```

```json
{"error": "runtime_unavailable",
 "detail": "QuantLib is not installed on this engine",
 "remediation": "install it, or route this warrant to an engine that has it"}
```

The third is worth pausing on. MAYA refuses **by name**, saying which runtime is
missing and where to send the work instead — as opposed to producing a number
from a fallback nobody authorised.

---

## 4 · Validating a model with no parameters

The validation is not lighter. It is *different*, and the platform records it as
such.

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","semver":"1.0.0",
       "scope":"full","plan":"benchmark against an independent implementation
                              across the strike and tenor grid"}'
```

Three things a T0 validation actually does:

1. **Benchmark**, instrument by instrument, against an independent
   implementation — this replaces backtesting, which has no meaning here.
2. **Boundary behaviour**: zero rates, negative rates, expiry today, a
   deliverable on a holiday. A closed form has closed-form edge cases.
3. **Conventions**, read against the term sheet. Most "pricing model errors" in
   practice are day-count and calendar errors, and no amount of statistical
   testing finds one.

A replay is exact, because there is no fitted state:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/validations/<id>/replay
```

---

## 5 · Monitoring a T0

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","kind":"input_drift",
       "test":"range_breach","feature":"curve.5Y",
       "threshold":0.02,"reference":{"window_days":250}}'
```

There is no performance to decay, because there is nothing fitted to go stale.
What *can* go wrong is that the model is being used somewhere it was never
benchmarked — deep out-of-the-money, a tenor beyond the grid, a negative rate on
a lognormal engine. So the monitor watches **the inputs against the validated
envelope**, and a breach is a finding against the *use*, not against the maths.

That is the T0 lesson in one line: for a model with no parameters, the risk
moved from the model to its **domain of applicability**, and the platform is
where that domain gets written down.

---

## Next

[Hull–White](/tutorials/hull-white-end-to-end) is the same world with one
change: the model now has parameters, and they are solved against market quotes
every morning rather than trained on history once.
