---
title: "A GARCH volatility model, end to end"
slug: garch-end-to-end
section: Worked models
order: 49
icon: activity
summary: "A daily equity volatility model registered, fitted by maximum likelihood, reviewed and served — and the two things that make a time-series model different from a regression: an iterative fit that can fail to converge, and a score that needs state the caller has to supply. ARMA and ARIMA sit in exactly this slot."
audience: Quants, Model developers, Validators
---

# A GARCH volatility model, end to end

Same shape as [the regression](/tutorials/linear-regression-end-to-end), harder
arithmetic — and two consequences that a closed-form fit never exposes.

**What you are building.** A GARCH(1,1) conditional-variance model over daily
equity log returns, used to size a trading limit.

| | |
|---|---|
| `P` is | ω, α, β |
| Filled by | maximum likelihood, iteratively |
| `parameter_kind` | `estimated_coefficients` |
| `fit_procedure` | `estimate` |
| Derived class | **T2** — statistically estimated |
| Runtime | `estimator`, family `garch11` |
| The catch | it can fail to converge, and scoring needs **state** |

---

## 1 · The series is a feature, and it still has two clocks

A price series looks like it only needs one timestamp. It needs two, and the
reason is restatement: a closing price is corrected, a dividend adjustment is
applied retrospectively, a venue republishes a session. Each of those is a new
`ingest_ts` against an old `event_ts`.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' \
  -d '{"name":"log_return","entity":"instrument_id","dtype":"numeric",
       "description":"Daily close-to-close log return, adjusted",
       "owner":"person/j.okafor"}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' \
  -d '{"name":"eq_daily","entity":"instrument_id","owner":"person/j.okafor",
       "features":["log_return"]}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views/eq_daily/data \
  -H 'Content-Type: text/csv' --data-binary @returns.csv
```

```csv
entity_id,event_ts,ingest_ts,log_return
EQ.VOD.L,1711843200,1711929600,-0.0142
EQ.VOD.L,1711929600,1712016000,0.0087
```

A backfilled correction lands with today's `ingest_ts` and last month's
`event_ts`. A fit windowed to last month therefore **does not see it**, which is
the correct answer: nobody could have fitted on it then.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"eq_vol_series","entity":"instrument_id","owner":"person/j.okafor",
       "slots":{"log_return":"numeric"},"grain":"daily"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/eq_vol_series/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"log_return":"log_return"}}'
```

> **No label slot.** A GARCH is not supervised in the scorecard sense; the
> series is the target and the history is the evidence. The featureset therefore
> declares no `label_slot`, and the fit warrant does not carry an outcome
> window. That is a real difference in shape, not a field left blank.

---

## 2 · The version

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch","name":"Equity vol GARCH(1,1)",
       "model_class":"markets.volatility","domain":"markets",
       "owner":"person/j.okafor","legal_entity":"LE-UK-01",
       "purpose":"Daily conditional variance for limit sizing"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/markets.vol.garch/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"estimated_coefficients",
                 "fit_procedure":"estimate",
                 "runtime":"estimator",
                 "entry":{"family":"garch11","series":"log_return"},
                 "input_schema":[{"name":"log_return","dtype":"numeric"}],
                 "output_schema":[{"name":"conditional_variance",
                                   "dtype":"numeric"}]}}'
```

---

## 3 · The fit, and the refusal that matters

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch","environment":"prod",
       "principal":"svc/model-lab","featureset":"eq_vol_series",
       "featureset_version":1,
       "window":{"from":1609459200,"to":1735603200},"as_of":1736899200}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameter-fits \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch","snapshot_id":"01b7...",
       "environment":"prod","principal":"svc/model-lab",
       "window":{"from":1609459200,"to":1735603200},"name":"garch_2024"}'
```

```json
{"values": {"omega": 0.0213, "alpha": 0.0807, "beta": 0.8601},
 "diagnostics": {"persistence": 0.9408, "long_run_variance": 0.36,
                 "converged": true, "iterations": 61,
                 "log_likelihood": 8814.2},
 "status": "proposed"}
```

### Why this family is in the tutorials at all

Because it is the first one that can **fail while looking like it succeeded**.
Three numbers from a search that stopped early look exactly like three from one
that finished. So:

- **An unconverged fit is refused**, not recorded with a flag. A flag on a row
  is something a downstream reader has to remember to check.
- **The stationarity constraint α + β < 1 is enforced during the fit.** Without
  it there is no unconditional variance and the model forecasts an exploding
  one. Persistence at 0.9408 above is close to the boundary and worth a note in
  the review.

```json
{"error": "fit_did_not_converge",
 "detail": "the likelihood search stopped after 500 iterations without meeting
            the tolerance",
 "remediation": "lengthen the window, or fit in your own engine and deliver the
                 parameters back under this warrant"}
```

### ARMA, ARIMA, EGARCH and the rest

They sit in **exactly this slot**: `estimated_coefficients` / `estimate`, with
the order (p, d, q) in the kernel `entry` and the fitted φ/θ in `P`. MAYA's
captive engine implements `ols` and `garch11` only — fit the others in your own
engine and deliver the parameters back, as in §6 of
[the regression tutorial](/tutorials/linear-regression-end-to-end).

Nothing about the governance changes. That is the point of separating the
estimator from the register.

---

## 4 · Scoring, and the state problem

Here is what makes a time-series model genuinely different at run time.

A GARCH does not predict a level; it predicts a **variance**, and to do that it
needs the last shock and the last variance. Those are **state** — not input.

```bash
curl -u svc/limits:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch#champion","environment":"prod",
       "principal":"svc/limits","declared_use":"limit_sizing",
       "inputs":{"features":{"last_return":-0.0142},
                 "state":{"last_variance":0.00031}}}'
```

```json
{"outputs": {"conditional_variance": 0.00034},
 "state_used": {"last_variance": 0.00031},
 "state_out": {"last_variance": 0.00034}}
```

The answer says **which state it used** and **which state it returns**. A
forecast that invented the state or hid it would not be reproducible, and
reproducibility is the whole basis on which a validator can replay it.

### The consequence for testing

If a thing remembers, you cannot learn what it does by asking it questions one
at a time. Two systems can agree on every single call and differ on the second
call of every pair.

That is not a curiosity, it is a rule about what a "patch release" claim is
worth. For an artefact carrying state, **a test set of individual cases cannot
support the claim at any size**. MAYA's replay therefore records and replays
*sequences*, and the validation record says which.

---

## 5 · Approve, promote, monitor

Approval, quorum and alias promotion are identical to
[the regression](/tutorials/linear-regression-end-to-end#8-approve-promote-freeze).
The monitors are not:

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch","kind":"calibration",
       "test":"coverage","threshold":0.9,
       "reference":{"nominal":0.99,"horizon_days":1}}'
```

For a variance model the honest test is **coverage**: over the last 250 days,
how often did the realised return exceed the interval the model implied? A
99% one-day interval should be breached about 2.5 times a year. Six breaches is
a finding; zero is also a finding, and the second one is the one people forget
to raise.

This is a `calibration` monitor rather than `performance`, and the distinction
is not cosmetic — a `performance` monitor waits for a label delay it does not
have, and would never evaluate.

---

## What to carry into the next one

Two things this model taught that the regression could not:

1. **An iterative fit has an outcome beyond its numbers.** Convergence is part
   of the result, and a result that does not carry it is not reviewable.
2. **State is not input.** The moment an artefact remembers, single-call testing
   stops being evidence — which comes back with force in
   [the Monte Carlo engine](/tutorials/monte-carlo-end-to-end).
