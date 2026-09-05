---
title: A derivative pricing model, end to end
slug: derivative-pricing-end-to-end
section: Worked models
order: 50
icon: calculator
summary: A closed-form bond and swaption pricer registered, warranted and served — the case where the parameter object is the terminal object, there is nothing to train, and the entire governance question moves onto the conventions, the curve and the valuation date. T0 is not a lesser model; it is a different shape, and its failures are day-count failures rather than statistical ones.
audience: Quants, Model developers, Validators
---

# A derivative pricing model, end to end

Ask most model-risk systems for a closed-form pricer's training set and you get
an empty field, an "N/A", and eventually a control everybody has learned to
ignore.

Here it is a **type error**, and what that frees you to govern instead is the
whole tutorial.

**What you are building.** A pricing service for vanilla instruments — a
discount factor, a fixed-rate bond, a European swaption under Black — served
through MAYA's QuantLib runtime.

| | |
|---|---|
| `P` is | **empty**. `P = 1`, the terminal object |
| Filled by | it isn't. There is nothing to fill |
| `parameter_kind` | `none` |
| `fit_procedure` | `none` |
| Derived class | **T0** — analytical, not trainable by construction |
| Runtime | `quantlib` |
| What is governed instead | the conventions, the curve, the fixings, the date |

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
                 "input_schema":[{"name":"maturity","dtype":"timestamp"},
                                 {"name":"coupon","dtype":"numeric"}],
                 "output_schema":[{"name":"clean_price","dtype":"numeric"},
                                  {"name":"dirty_price","dtype":"numeric"},
                                  {"name":"accrued","dtype":"numeric"}]},
       "contract":{"assumptions":[{"key":"coupon","minimum":0,"maximum":0.15},
                                  {"key":"face","minimum":0}],
                   "guarantees":[{"key":"benchmark_diff_bp","maximum":0.5}],
                   "on_boundary_violation":"reject"}}'

curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/markets.pricing.vanilla/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":8000000000,"purpose_class":"financial_reporting",
       "feature_count":0,"interpretable":true}'
```

```json
{"tier": 1, "materiality": "critical", "complexity": "simple",
 "rationale": "materiality=critical (exposure 8,000,000,000 in band critical,
               purpose financial_reporting); complexity=simple (class T0);
               tau(critical,simple)=Tier 1 under ruleset 2026.09.1"}
```

**Tier 1 on a model with no parameters, and that is correct.** Materiality
dominates: `tau` returns 1 for critical materiality however simple the model is,
because the size of what depends on the number is not reduced by the number
being easy to compute. Two operational consequences follow immediately — a
resolved warrant for this model lives **sixty seconds** with **zero grace**, and
its versions need a two-role quorum.

That is the entire model definition. No featureset, no fit warrant, no
parameters — and none of those are *missing*.

### The refusal that proves the point

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","environment":"prod",
       "principal":"svc/model-lab","featureset":"anything",
       "featureset_version":1,
       "window":{"from":0,"to":1735603200},"as_of":1735603200}'
```

```json
{"error": "grammar_violation",
 "detail": "the warrant does not conform to the grammar: 1 problem(s): a T0
            model cannot be fitted: its parameters come from theory, not from
            data — there is nothing to fit",
 "remediation": "this is a defect in the model's registration, not in the
                 request; the problems name the exact paths"}
```

The document is built, checked and **never signed** — validation runs before the
signature, always, because a signature over a non-conforming document would be
an assurance that it is authentic rather than that it is usable, and engines
would reasonably read it as both. The problem inside carries the path and the
law:

```json
{"law": "L-W1", "path": "operation.verb",
 "detail": "a T0 model cannot be fitted: its parameters come from theory, not
            from data — there is nothing to fit",
 "remediation": "ask for 'score', 'validate' or 'explain'; if this model really
                 is fitted, its parameter_kind and fit_procedure are wrong"}
```

The refusal does not say "no". It says **which fact about the kernel** made the
request incoherent, and where to correct it if the fact is wrong. And the fact
was never entered by anybody: `trainability_class` is computed from
`parameter_kind` and `fit_procedure` in `core/domain/algebra.py`, so this
refusal cannot be argued with by editing a category field. Every problem is
reported at once rather than one at a time —
`POST /api/v1/grammar/validate` will check a document you have written by hand
and return the whole list, because fixing one error to be told about the next is
the worst possible interface for a document with ten sections.

Try the other door — deliver parameters directly — and you get a different
refusal, with a different remedy:

```json
{"error": "nothing_to_fit",
 "detail": "this version's parameter object is terminal: its parameters come
            from theory, not from data, so there is nothing a fit could have
            produced",
 "remediation": "record them with provenance 'declared', which is what a closed
                 form actually has"}
```

**Read that remediation carefully, because it is the nuance the T0 story usually
loses.** A closed form *may* hold parameters — a recovery assumption, a
convexity adjustment somebody chose, a haircut. What is refused is the *route*,
not the object: `fitted` is evidence and `declared` is an assertion, and only the
second may arrive without a warrant behind it. A declared set is recorded,
digested and approved by a second person exactly like a fitted one; what it does
not claim is that data produced it.

---

## 2 · So what *is* governed?

Everything that was going to be governed anyway, and two things people usually
leave out.

| Governed | Where it lives |
|---|---|
| The **instrument and the pricing engine** | the kernel `entry`, immutable in the version |
| The **curve** the price is struck against | the `market_data` input binding, pinned |
| The **day count** the curve is built on | the same binding, from a closed list of four |
| The **past fixings** a floating leg needs | the same binding |
| The **volatility** for the swaption | the call, and refused if absent |
| The **valuation date** | the warrant, never defaulted to "today" |
| The **domain of applicability** | the version's contract assumptions |

The grammar makes the fourth column non-optional for two of these: the
`market_data` binding is defined in
`core/execution/grammar/vocabulary.py` as carrying `curve_set` **and** `as_of`,
so a warrant that reaches for market data without stating when is malformed
before it is signed rather than wrong when it runs.

---

## 3 · Serve it

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla#champion",
       "environment":"prod","principal":"svc/pricing",
       "declared_use":"end_of_day_valuation"}'

curl -u svc/pricing:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla#champion",
       "environment":"prod","principal":"svc/pricing",
       "declared_use":"end_of_day_valuation",
       "inputs":{"as_of":"2026-05-15",
                 "curve":[{"date":"2027-05-15","rate":0.0412},
                          {"date":"2031-05-15","rate":0.0388},
                          {"date":"2036-05-15","rate":0.0401}],
                 "face":1000000,"coupon":0.045,
                 "settlement":"2024-09-30","maturity":"2031-09-30",
                 "settlement_days":2}}'
```

```json
{"descriptor_id": "wd-3382",
 "model_urn": "maya://model/markets.pricing.vanilla", "version": "1.0.0",
 "prediction": {"clean_price": 102.31, "dirty_price": 102.8725,
                "accrued": 0.5625, "npv": 1028725.0},
 "boundary_ok": true, "boundary_violations": [], "latency_ms": 8.7}
```

Two details in that request are easy to get wrong and worth stating exactly.

**A curve is a list of dated rates**, `{"date": …, "rate": …}` — not tenors.
A tenor is relative to a date, and a curve carrying `"5Y"` would mean two
different curves on two different mornings while looking identical in the
record. Dates are absolute, and the engine anchors the short end at the
evaluation date by flat extrapolation from the first pillar only when the curve
does not already start there.

**The day count is named from a closed list** — `actual/360`, `actual/365`,
`30/360`, `actual/actual` — and lives on the `market_data` binding, defaulting
to `actual/365`. A name outside the list is refused rather than approximated,
because a day count silently swapped for another moves every cash flow.

### The refusals you will actually meet

These are the failures of a pricing model, and none of them is statistical.

```json
{"error": "no_evaluation_date",
 "detail": "this warrant does not say what date to value at",
 "remediation": "a price is a price on a date; supply as_of in the market data
                 binding or in the call, because valuing at 'now' would not be
                 reproducible tomorrow"}
```

Defaulting a valuation date to the wall clock is the wrong answer that looks
right, and a backtest of a model that reads the clock is a backtest of nothing.
The runtime sets QuantLib's evaluation date from the warrant and refuses
otherwise.

```json
{"error": "no_curve",
 "detail": "this warrant carries no curve to discount against",
 "remediation": "supply the curve in the market_data binding; reaching for a
                 market data service here would put an unversioned input into a
                 governed computation"}
```

That remediation is the design rule for this entire runtime: the curve comes
from what the warrant carries **and from nothing else**. A pricer that fetched
its own curve would be a governed computation with an ungoverned input, and the
record would say which model priced it without saying what it priced it against.

```json
{"error": "unknown_day_count",
 "detail": "'Actual365Fixed' is not a day count this engine knows; it knows
            30/360, actual/360, actual/365, actual/actual",
 "remediation": "a day count silently swapped for another moves every cash flow"}
```

```json
{"error": "instrument_unsupported",
 "detail": "this engine does not price 'bermudan_swaption'; it prices discount,
            zero_rate, forward_rate, fixed_bond, vanilla_swap, swaption",
 "remediation": "route the warrant to an engine that does, or price it as one of
                 these — guessing which is meant would be worse than refusing"}
```

```json
{"error": "pricing_engine_unsupported",
 "detail": "this engine does not build a 'jamshidian' pricing engine; it builds
            analytic, discounting, black",
 "remediation": "a warrant naming an engine that is silently swapped for another
                 produces a number nobody can reconcile"}
```

```json
{"error": "missing_fixing",
 "detail": "the instrument needs a past fixing the warrant does not carry",
 "remediation": "supply fixings alongside the curve; a valuation that invented
                 one would put an unversioned number into a governed computation"}
```

```json
{"error": "no_volatility",
 "detail": "a swaption under Black needs a volatility, and this warrant carries
            none",
 "remediation": "supply volatility; a price computed from an assumed one is a
                 price of a different instrument"}
```

Notice what none of these say. There is no refusal here about data quality,
sample size, drift or convergence, because none of those concepts applies. The
whole failure surface of a T0 model is **inputs, conventions and dates**, and
each of the seven above names one specific thing somebody forgot.

---

## 4 · The bug this runtime exists to have already fixed

This is the section that could only be about a pricing library, and it is worth
the whole page.

QuantLib keeps its index fixing history in a **process-global manager**. A swap
priced under one warrant deposits its past fixings there, and unless something
removes them they are still there for the next valuation — a different warrant,
a different counterparty, possibly a different legal entity, silently using a
fixing it never carried.

That is precisely the unversioned input this runtime exists to prevent, arriving
through the back door. So `core/execution/runtimes/quantlib.py` calls
`ql.IndexManager.instance().clearHistories()` before every valuation: **each
price starts from an empty fixing history and sees only what its own warrant
carries.**

Three things follow, and they generalise past QuantLib:

- **A shared library is shared state.** A pricing engine with process-global
  configuration — evaluation date, fixing history, calendars, a cached
  discounting curve — is an artefact that remembers, and everything the
  [GARCH tutorial](/tutorials/garch-end-to-end#4-scoring-and-the-state-problem)
  says about testing stateful things applies to it. Two valuations that are
  correct one at a time can be wrong in sequence.
- **A missing fixing is refused rather than skipped**, because a skipped fixing
  is an invented one — `malformed_fixing` if it does not read as a date and a
  rate, `missing_fixing` if the instrument needs one that is absent.
- **The library version is part of the model.** A closed-form pricer whose
  library was upgraded underneath it is a changed model, and the only way to
  notice is for the run record to say which library priced it. That is what the
  `realisation.environment` block on the warrant is for, and filling it is the
  registrar's job rather than something the platform can derive.

> **And one thing the platform does *not* do.** QuantLib is deliberately absent
> from `SANDBOXED_RUNTIMES`. It loads no artifact — the instrument and the curve
> arrive inside the warrant — so there is no untrusted file to isolate from, and
> paying a process spawn per valuation would buy nothing. The ONNX and PMML
> runtimes are isolated because they load bytes; this one is not because it does
> not.

---

## 5 · Validating a model with no parameters

The validation is not lighter. It is *different*, and the register records it as
a different shape.

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","semver":"1.0.0",
       "kind":"initial",
       "validators":["a.mehta","r.oyelaran"],
       "scope":["benchmark","boundary","conventions"],
       "plan":{"benchmark":"independent implementation across the strike and
                            tenor grid, tolerance 0.5bp of notional",
               "boundary":"zero rates, negative rates, expiry today, a
                           deliverable on a holiday",
               "conventions":"read against the term sheet, instrument by
                              instrument"}}'
```

`validators` is required and is checked for independence: a validator who built
the version is refused, because effective challenge by its author is not
challenge. `scope` is a list and `plan` is a document, not prose in a string —
so the replay in a moment has something structured to compare against.

Three things a T0 validation actually does:

1. **Benchmark**, instrument by instrument, against an independent
   implementation. This *replaces* backtesting, which has no meaning here:
   there is no realised outcome for the model to have been wrong about, only a
   different calculation of the same quantity. The unit is basis points of
   notional, and the tolerance belongs in the contract's guarantees where the
   alias move can check it.
2. **Boundary behaviour.** Zero rates, negative rates, expiry today, a
   deliverable on a holiday, a coupon date on 29 February. A closed form has
   closed-form edge cases, and they are enumerable — which makes this the one
   family where a validation can be genuinely exhaustive over its declared
   domain.
3. **Conventions, read against the term sheet.** Day count, calendar,
   settlement lag, roll convention, business-day adjustment. Most "pricing model
   errors" in practice are convention errors, and no amount of statistical
   testing finds one. The `unknown_day_count` refusal above catches the curve's;
   the instrument's are yours to check.

A replay is exact, because there is no fitted state to reconstruct:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/validations/<id>/replay-from-storage
```

Nothing is supplied by the caller there, which is the point: a mismatch is about
the test rather than about who handed over which file.

---

## 6 · Where this model sits in the graph

A pricer is rarely alone. Wire it to what reads it, and the wire is type-checked
rather than drawn:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"maya://model/markets.pricing.vanilla",
       "to_urn":"maya://model/markets.rates.curve","kind":"input_to"}'
```

```json
{"error": "registry_refused",
 "detail": "maya://model/markets.pricing.vanilla does not compose with
            maya://model/markets.rates.curve: what it produces is missing
            {curve}. An `input_to` edge asserts that the output arrives where
            the input is read, and an edge that does not type-check is a wire to
            nowhere — the blast radius would follow it and the composite would
            have no defined schema"}
```

The edge is the wrong way round, and the register says so instead of recording
it. Reverse it — the curve model's output is an input to the pricer — and it is
accepted, because the source's output schema now stands in for the target's
input schema under the same order (`core.domain.lattice.refines`) that `L-12`
uses at an alias move and `L-W10` uses at warrant issuance. `input_to` is the
relation that **propagates**, so recalibrating the curve fires a blast radius
that reaches this model and everything downstream of it.

`challenger_of` and `benchmark_for` are deliberately *not* type-checked: they
record how somebody thinks about a model, and there is no wire. Registering the
independent implementation from §5 as a `benchmark_for` edge is exactly right,
and it will not inflate anybody's blast radius.

---

## 7 · Monitoring a T0

There is no performance to decay, because there is nothing fitted to go stale.
What *can* go wrong is that the model is being used somewhere it was never
benchmarked — deep out of the money, a tenor beyond the grid, a negative rate on
a lognormal engine.

Two mechanisms cover that, and only one of them is a monitor.

**The contract does the real work, at every single call.** The assumptions
declared on the version in §1 are checked before the runtime is touched — a
`coupon` of 22% on a version benchmarked to 15% is outside the domain of
applicability, and the answer says so by name:

```json
{"descriptor_id": "wd-3391", "boundary_ok": false,
 "boundary_violations": ["coupon"]}
```

and with `on_boundary_violation: "reject"` the call is refused outright with
`boundary_violation`, naming the assumption. Outside the assumptions the
guarantee is void — that is what an assume–guarantee contract means — and the
domain of applicability is therefore enforced per call rather than reviewed
annually.

**The monitor watches the benchmark difference**, which is the only number this
model produces that can be wrong:

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.pricing.vanilla","name":"benchmark diff",
       "kind":"performance","test_key":"accuracy.rmse",
       "threshold":{"max":0.5},"owner":"person/j.okafor",
       "cadence_days":1,"label_delay_days":1,
       "breach_severity":"High","escalate_after":2}'
```

The "label" is the independent implementation's price and the "score" is this
model's, so RMSE in basis points is the statistic. MAYA insists you name a
`label_delay_days` even here, and the honest answer is 1: the independent run is
nightly, so today's prices are comparable tomorrow.

> **What is not built.** An `input_drift` monitor over the curve pillars would
> be the natural third control, and MAYA's telemetry carries `scores` and
> `outcomes` rather than feature vectors — so evaluating one means handing the
> pillar values in yourself at `POST /api/v1/monitors/<id>/evaluate`. The kind
> exists; the plumbing to feed it from stored telemetry does not.

That is the T0 lesson in one line: for a model with no parameters the risk moved
off the maths and onto **the inputs, the conventions and the domain of
applicability** — and the platform is where all three get written down and
checked.

---

## Next

[Hull–White](/tutorials/hull-white-end-to-end) is the same world with one
change: the model now has parameters, they are solved against market quotes
every morning, and the question stops being *what does it read* and becomes
*who approves two hundred and fifty acts a year*.
