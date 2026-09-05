---
title: A linear regression, end to end
slug: linear-regression-end-to-end
section: Worked models
order: 48
icon: graph-up
summary: A small-business PD scorecard from an empty register to a champion serving in production — features with two clocks, a featureset that pins its bytes, a fit warrant, MAYA's own estimator, a four-eyes review of the coefficients, and a monitor that watches them age. The ordinary case, done completely.
audience: Data scientists, Model developers, Validators
---

# A linear regression, end to end

This is the plainest model in the book and the one worth doing first, because
every later tutorial is this one with a different way of filling `P`.

**What you are building.** A 12-month probability-of-default scorecard for a
small-business credit book. Two regressors, one label, a handful of
coefficients — and every control the platform has, applied to them.

| | |
|---|---|
| `P` is | an intercept and two slopes |
| Filled by | ordinary least squares, in MAYA's own estimator |
| `parameter_kind` | `estimated_coefficients` |
| `fit_procedure` | `estimate` |
| Derived class | **T3** — statistically estimated |
| Runtime | `estimator` |
| Where `P` lives | in the register, as a record |

The last row is the one that separates this tutorial from
[the neural network](/tutorials/neural-network-end-to-end): three numbers are a
*record*, twenty million are an *artifact*, and the register handles them
differently for that reason alone.

---

## 0 · The four people

Duties are separated. Doing this as one account gets you refused, which is the
platform working rather than failing.

```bash
curl -u admin:admin123 -X POST localhost:5006/api/v1/principals \
  -H 'Content-Type: application/json' \
  -d '{"username":"d.raman","display_name":"D Raman",
       "roles":["model_developer"],"password":"dev-pw"}'
```

Repeat for `j.okafor` (`model_owner`), `a.mehta` (`validator`) and `s.iqbal`
(`model_risk_manager`).

---

## 1 · The features

A feature is a governed object with an owner, a type and a lineage — not a
column somebody added to a table.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' \
  -d '{"name":"dscr","entity":"borrower_id","dtype":"numeric",
       "description":"Debt service coverage ratio, trailing 12m",
       "owner":"person/j.okafor"}'
```

Do the same for `turnover` (numeric) and `defaulted` (integer — the label).

> **Why the label is a feature too.** It has an owner, a definition and an
> ingest clock like anything else, and pretending otherwise is how a label gets
> restated without anybody noticing that a training set moved.

---

## 2 · The values, with both clocks

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_financials","entity":"borrower_id","owner":"person/j.okafor",
       "features":["dscr","turnover","defaulted"]}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/data \
  -H 'Content-Type: text/csv' --data-binary @financials.csv
```

```csv
entity_id,event_ts,ingest_ts,dscr,turnover,defaulted
B0001,1711843200,1716163200,1.42,2500000,0
B0002,1711843200,1716163200,0.88,410000,1
```

`event_ts` is when the fact was **true** (31 March, the quarter it describes).
`ingest_ts` is when it became **known** (20 May, when they filed). A file
carrying only one is refused: with one clock you cannot answer *what did we know
when the decision was made*, and a restatement then rewrites history silently.

The whole upload becomes **one view version**, because a version is what a
featureset pins.

---

## 3 · The featureset

A featureset declares a **schema**; a version **fills** it.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_core","entity":"borrower_id","owner":"person/j.okafor",
       "slots":{"dscr":"numeric","turnover":"numeric","defaulted":"integer"},
       "label_slot":"defaulted","outcome_window_days":365}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"dscr":"dscr","turnover":"turnover",
                   "defaulted":"defaulted"}}'
```

`sb_core@v1` now always resolves to the same bytes, because every binding names
a Delta version rather than a path.

---

## 4 · The model and its version

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","name":"SB PD",
       "model_class":"credit.pd.scorecard","domain":"credit",
       "owner":"person/j.okafor","legal_entity":"LE-US-01",
       "purpose":"12-month PD at origination"}'

curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":2000000000,"purpose_class":"regulatory_capital"}'
```

The assessment returns the **derivation** — which facts were used, which bands
they fell in, which ruleset version decided — not just a tier number.

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"estimated_coefficients",
                 "fit_procedure":"estimate",
                 "runtime":"estimator",
                 "entry":{"family":"ols","target":"defaulted",
                          "regressors":["dscr","turnover"]},
                 "input_schema":[{"name":"dscr","dtype":"numeric"},
                                 {"name":"turnover","dtype":"numeric"}],
                 "output_schema":[{"name":"pd_12m","dtype":"numeric"}]}}'
```

You never declare the trainability class. It is **derived** from
`parameter_kind` and `fit_procedure`, which is why asking this model for its
training set is a sensible question and asking
[a closed-form pricer](/tutorials/derivative-pricing-end-to-end) the same thing
is a type error.

---

## 5 · The fit warrant

Nothing reads training data without one.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","environment":"prod",
       "principal":"svc/model-lab","featureset":"sb_core",
       "featureset_version":1,
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200}'
```

Three laws are checked before it is signed:

- **L-W3** — training data must come from a source readable as-of.
- **L-W9** — the read must be bounded in **both** clocks.
- **L-W10** — the featureset must provide what the kernel declares it reads.
  Adding a regressor is a model change, and this is where that is enforced
  rather than remembered.

The descriptor that comes back carries the slots, their types, which feature and
view version fills each, the entity, the grain, the label binding and the
outcome window. Names and types — never values. A signed credential is not a
wire format for a dataset.

---

## 6 · The fit

MAYA can run this one itself, because the kernel names the `estimator` runtime.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets/sb_core/training-sets \
  -H 'Content-Type: application/json' \
  -d '{"version":1,"as_of":1736899200,
       "spine":[{"entity_id":"B0001","label_ts":1730000000,"defaulted":0}]}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameter-fits \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","snapshot_id":"01a0...",
       "environment":"prod","principal":"svc/model-lab",
       "window":{"from":1546300800,"to":1735603200},"name":"ols_v1"}'
```

```json
{"values": {"intercept": -2.10, "dscr": -0.84, "turnover": 0.00003},
 "diagnostics": {"r_squared": 0.31, "condition_number": 34.9,
                 "standard_errors": {"dscr": 0.11}, "n": 8420},
 "status": "proposed"}
```

The order of what happened matters: **the warrant resolved first**, then the
snapshot was read at its pinned Delta version, then the estimator ran, then the
result landed `proposed`. Authority before data — a read performed under an
authority that turns out not to exist has already happened.

**Read the condition number before the R².** At 34.9 these coefficients are a
property of the world; in the thousands they are a solution to *this sample*.
MAYA does not judge the fit. It puts the number where somebody who can has to
look at it.

### Or fit it somewhere else

```bash
curl -u svc/model-lab:svc-pw \
  "localhost:5006/api/v1/featuresets/sb_core/versions/1/data?as_of=1736899200&format=parquet" \
  -o training.parquet

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0",
       "name":"ols_v1","kind":"coefficients","provenance":"fitted",
       "values":{"intercept":-2.1,"dscr":-0.84,"turnover":0.00003},
       "featureset":"sb_core","featureset_version":1,
       "warrant_id":"<the grant id>",
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200,
       "diagnostics":{"r_squared":0.31,"n":8420}}'
```

A fitted set is accepted **only** against a warrant MAYA issued. Without one,
"which data produced these numbers" has no answer.

---

## 7 · Four eyes on the numbers

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/<id>/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,"note":"condition number 34.9; signs as expected"}'
```

Not by whoever recorded it — a number one person can both produce and bless is a
preference, not an estimate.

**Recording new parameters does not create a new model version.** The kernel did
not change. That is what lets a recalibration *procedure* be approved once
rather than pretending a committee meets every morning.

---

## 8 · Approve, promote, freeze

```bash
APPROVAL=$(curl -su s.iqbal:mrm-pw -X POST localhost:5006/api/v1/version-approvals \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"model_risk_manager"}'
curl -u a.mehta:val-pw  -X POST localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"validator"}'

curl -u s.iqbal:mrm-pw -X PUT localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment":"prod","alias":"champion","semver":"1.0.0"}'

curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/featuresets/sb_core/seal \
  -H 'Content-Type: application/json' -d '{"note":"fitted against; frozen"}'
```

A Tier 1 or 2 version needs a quorum — two people in two named roles, and the
creator is not one of them. The alias move is a **proof obligation**: the
replacement's contract must refine the incumbent's (L-7) and its schemas must
satisfy variance (L-12).

---

## 9 · Serve it

```bash
curl -u svc/origination:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision",
       "inputs":{"features":{"dscr":1.4,"turnover":250000}}}'
```

The warrant names the approved parameter set by **id and digest**, and the
engine **re-derives** that digest from the values before running. It does not
compare the stored digest against the warrant's copy: those are two copies of
one claim and would agree happily over values somebody had edited underneath
them.

---

## 10 · Watch it age

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","kind":"input_drift",
       "test":"psi","feature":"dscr","threshold":0.25,
       "reference":{"featureset":"sb_core","version":1}}'

curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","kind":"performance",
       "test":"auc","threshold":0.62,"label_delay_days":365}'
```

The second monitor **will not evaluate** until a cohort is 365 days old. A PD
model's performance is not knowable sooner, and a performance number computed on
an immature cohort is a number about the fast defaulters only.

---

## What this tutorial buys the next six

Everything above stays the same in the six that follow. What changes is exactly
one thing: **how `P` is inhabited.**

| Next | `P` becomes | Read it for |
|---|---|---|
| [GARCH](/tutorials/garch-end-to-end) | three numbers from an iterative fit | convergence, and state at scoring time |
| [Derivative pricing](/tutorials/derivative-pricing-end-to-end) | *empty* | what governance means with nothing to fit |
| [Hull–White](/tutorials/hull-white-end-to-end) | a calibration set, refreshed daily | calibration is not training |
| [Monte Carlo](/tutorials/monte-carlo-end-to-end) | parameters **plus a seed** | reproducibility, and why one seed is a control |
| [Neural network](/tutorials/neural-network-end-to-end) | millions of weights, as an artifact | the store, and content addressing |
| [LLM application](/tutorials/llm-end-to-end) | a configuration you assembled | what "the model" even is |
