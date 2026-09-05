---
title: A calibrated term-structure model, end to end
slug: hull-white-end-to-end
section: Worked models
order: 51
icon: sliders
summary: Hull–White registered, calibrated against the swaption grid every morning, and served — the case where P is refreshed daily by a solver rather than trained once on history. Calibration is not training, and the difference decides who has to approve what, how often.
audience: Quants, Model developers, Model risk managers
---

# A calibrated term-structure model, end to end

The question this model answers is organisational as much as mathematical: **if
the numbers change every morning, who approves them?**

Answering "a committee" is how banks end up with a control nobody performs.
Answering "nobody" is how a model drifts without a record. The platform's answer
is neither: the *procedure* is approved once, the *outputs* are recorded every
day, and the exceptions are what a human sees.

**What you are building.** A one-factor Hull–White short-rate model, calibrated
each morning to the co-terminal swaption grid, feeding an XVA engine.

| | |
|---|---|
| `P` is | mean reversion `a`, volatility `σ` (or a term structure of σ) |
| Filled by | a solver, against market quotes |
| `parameter_kind` | `calibration_set` |
| `fit_procedure` | `calibrate` |
| Derived class | **T1** — calibrated, not trained |
| Runtime | `quantlib` |
| Cadence | daily |

---

## 1 · Why T1 is its own class

A trained model learns a relationship from history and is expected to hold for a
while. A calibrated model **reproduces today's market** and is expected to be
wrong tomorrow — that is not degradation, it is the design.

Three consequences follow immediately, and they are why the class exists:

| | Trained (T3/T4) | Calibrated (T1) |
|---|---|---|
| Refit cadence | occasional, an event | daily, a process |
| A refit is | reviewable individually | reviewable **by exception** |
| Drift means | the world moved away from the fit | the calibration stopped fitting |
| The control | approve each parameter set | approve the **procedure**, monitor the residuals |

Recording new parameters is never a new model version — but for a T1 that
statement carries the operational load of the whole design. Two hundred and
fifty parameter sets a year, one approved kernel.

---

## 2 · The calibration instruments are the input

The market quotes are governed exactly like features, because they are the data
the parameters come from.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' \
  -d '{"name":"swaption_vol","entity":"grid_point","dtype":"numeric",
       "description":"Normal implied vol, co-terminal swaption grid",
       "owner":"person/j.okafor"}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' \
  -d '{"name":"swaption_grid","entity":"grid_point","owner":"person/j.okafor",
       "features":["swaption_vol"]}'
```

```csv
entity_id,event_ts,ingest_ts,swaption_vol
1Yx5Y,1743379200,1743382800,0.00612
2Yx5Y,1743379200,1743382800,0.00658
```

The two clocks are doing real work here even though the lag is minutes: a
morning calibration run at 07:00 must **not** see a quote that arrived at 09:30,
and a re-run of yesterday's calibration must see yesterday's snap. Without
`ingest_ts` a re-run silently improves on the original, which is the least
useful kind of reproducibility.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"hw_calibration_grid","entity":"grid_point",
       "owner":"person/j.okafor",
       "slots":{"swaption_vol":"numeric"},"grain":"daily"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/hw_calibration_grid/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"swaption_vol":"swaption_vol"}}'
```

---

## 3 · The version

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","name":"Hull-White 1F",
       "model_class":"markets.term_structure","domain":"markets",
       "owner":"person/j.okafor","legal_entity":"LE-UK-01",
       "purpose":"Short-rate dynamics for XVA and Bermudan exercise"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/markets.rates.hullwhite/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"calibration_set",
                 "fit_procedure":"calibrate",
                 "runtime":"quantlib",
                 "entry":{"instrument":"swaption","pricing_engine":"jamshidian"},
                 "input_schema":[{"name":"curve","dtype":"structured"},
                                 {"name":"as_of","dtype":"timestamp"}],
                 "output_schema":[{"name":"npv","dtype":"numeric"}]}}'
```

---

## 4 · Calibrate, and deliver the set

MAYA's captive engine does not solve Hull–White. That is deliberate: a
calibration engine is a serious piece of quant software and the register is not
the place for it. So the bank's own engine calibrates **under a warrant** and
delivers the result back.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","environment":"prod",
       "principal":"svc/rates-calib","featureset":"hw_calibration_grid",
       "featureset_version":1,"verb":"calibrate",
       "window":{"from":1743379200,"to":1743379200},"as_of":1743382800}'
```

The engine reads the pinned grid, solves, and posts back:

```bash
curl -u svc/rates-calib:svc-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","semver":"1.0.0",
       "name":"hw_2026-03-31","kind":"calibration_set",
       "provenance":"calibrated",
       "values":{"mean_reversion":0.031,
                 "sigma":[{"tenor":"1Y","value":0.0062},
                          {"tenor":"5Y","value":0.0071},
                          {"tenor":"10Y","value":0.0069}]},
       "featureset":"hw_calibration_grid","featureset_version":1,
       "warrant_id":"<the grant id>","as_of":1743382800,
       "diagnostics":{"rmse_bp":0.42,"max_abs_error_bp":1.7,
                      "worst_point":"10Yx10Y","instruments":36,
                      "converged":true,"iterations":18}}'
```

### The as_of is not optional

`as_of` on that parameter set is what **L-W11** requires, and the law is worth
understanding rather than satisfying.

A calibrated model reproduces a market rather than summarising a history, so the
moment it was solved for is part of what the numbers *mean*. Two warrants naming
this same set on different mornings are not the same run. Without the stamp,
staleness is silent: the engine runs yesterday's fit against today's book,
produces an entirely ordinary-looking number, and nothing in the record says
which market it came from.

```json
{"law": "L-W11", "path": "parameters.source.as_of",
 "detail": "this model's parameters are a calibration, and the warrant does not
            say what they were calibrated as of, so nothing downstream can tell
            a current calibration from a stale one"}
```

The law requires the age to be **statable**, not small — how old is too old
depends on your cadence, and that is the policy gate's question. So the resolved
warrant carries both:

```json
"parameters": {"source": {"binding": "parameter_set",
                          "parameter_set": "ps-8817",
                          "digest": "sha256:1c9a…",
                          "as_of": 1743382800,
                          "age_seconds": 3600}}
```

A fit warrant is exempt, because the calibration being solved for cannot state
when it was solved.

`provenance: "calibrated"` is not decoration. It says the numbers reproduce a
market rather than summarise a history, and every downstream reader —
monitoring, reporting, the validator's checklist — branches on it.

---

## 5 · Approval by exception

This is the part that makes a daily model workable.

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/policies \
  -H 'Content-Type: application/json' \
  -d '{"gate":"parameter_acceptance",
       "urn":"maya://model/markets.rates.hullwhite",
       "rule":"rmse_bp < 1.0 and max_abs_error_bp < 3.0 and converged == 1
               and abs(mean_reversion - prior.mean_reversion) < 0.02",
       "cases":[{"facts":{"rmse_bp":0.4,"max_abs_error_bp":1.7,"converged":1,
                          "mean_reversion":0.031,"prior":{"mean_reversion":0.030}},
                 "verdict":"pass"},
                {"facts":{"rmse_bp":2.4,"max_abs_error_bp":9.0,"converged":1,
                          "mean_reversion":0.031,"prior":{"mean_reversion":0.030}},
                 "verdict":"refuse"}]}'
```

Read what that policy is and is not:

- It is **versioned and published**, so "which rule was in force on 31 March"
  has an answer.
- It ships with **cases**, and a policy whose own cases do not pass is refused
  at publication. A rule nobody tested is a rule nobody can rely on.
- It requires **at least one refusing case**. A gate that has never refused
  anything is indistinguishable from no gate, and this is the check that stops
  one being written.

A calibration inside the envelope is accepted and recorded. One outside is
**held** and lands on the quant's worklist with the reason attached:

```json
{"status": "held",
 "gate": "parameter_acceptance",
 "failed": "max_abs_error_bp < 3.0",
 "actual": {"max_abs_error_bp": 9.0, "worst_point": "10Yx10Y"},
 "detail": "the grid did not fit today; the long end is the problem"}
```

Nobody approves 250 calibrations a year. Somebody approves the envelope once,
and looks at the eleven days it was breached.

---

## 6 · What feeds what

An XVA engine consumes this model, and that relationship is a **`feeds`** edge —
which propagates.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"maya://model/markets.rates.hullwhite",
       "to_urn":"maya://model/xva.cva","kind":"feeds"}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/blast-radius \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite"}'
```

Recalibrating does not fire that edge — the kernel did not change. **Changing
the calibration instrument set does**, and so does moving to two factors.

Use `calibrated_by` when the direction is the other way: a Bermudan model whose
parameters are solved by this one holds a `calibrated_by` edge to it, and that
edge propagates too.

---

## 7 · Monitoring: residuals, not accuracy

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","kind":"calibration",
       "test":"residual","threshold":1.0,
       "reference":{"metric":"rmse_bp","window_days":60}}'
```

There is no label to wait for and no accuracy to compute. The signal is the
**residual trend**: an RMSE that has been climbing for six weeks means the
one-factor form is running out of grid, and that is a model finding rather than
a bad day.

A second monitor worth having watches **parameter stability**: mean reversion
that jumps 40% overnight usually means the solver found a different local
minimum, not that the world changed.

---

## Next

[The Monte Carlo engine](/tutorials/monte-carlo-end-to-end) consumes exactly
these parameters — and adds the one thing calibration does not have: a random
seed, which turns out to be a governed input rather than a detail.
