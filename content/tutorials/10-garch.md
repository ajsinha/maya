---
title: "A GARCH volatility model, end to end"
slug: garch-end-to-end
section: Worked models
order: 49
icon: activity
summary: "A daily equity volatility model registered, fitted by maximum likelihood, reviewed and served — and the three things that separate a time-series model from a regression: a search that can stop in the wrong place, a stationarity constraint enforced inside the objective, and a score that needs state the caller has to supply. ARMA and ARIMA sit in exactly this slot."
audience: Quants, Model developers, Validators
---

# A GARCH volatility model, end to end

Same shape as [the regression](/tutorials/linear-regression-end-to-end), harder
arithmetic — and three consequences a closed-form fit never exposes.

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
| The catch | the search can stop early, and scoring needs **state** |

Everything in §0–§2 of the regression tutorial applies unchanged: the same four
people, the same two clocks, the same featureset discipline. What follows is
only what is different.

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
the correct answer: nobody could have fitted on it then. That is not a
convention here, it is the saturation property of the point-in-time operator —
the ingest bound is `min(label_ts, as_of)`, so every read at or after the label
returns the same rows however many restatements arrive later.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"eq_vol_series","entity":"instrument_id",
       "slots":{"log_return":"numeric"},"grain":"daily"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/eq_vol_series/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"log_return":"log_return"}}'
```

> **No label slot.** A GARCH is not supervised in the scorecard sense; the
> series is the target and its own history is the evidence. The featureset
> therefore declares no `label_slot` and no `outcome_window_days`, and the fit
> warrant carries no label binding. That is a real difference in shape, not a
> field left blank — and it comes back in §5, where it decides which kind of
> monitor is even definable.

---

## 2 · The version, and a lower tier

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

curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/markets.vol.garch/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":250000000,"purpose_class":"risk_management",
       "feature_count":1,"interpretable":true}'
```

```json
{"tier": 3, "materiality": "moderate", "complexity": "simple",
 "required_controls": ["peer_review","triennial_review",
                       "semiannual_monitoring","owner_approval"],
 "rationale": "materiality=moderate (exposure 250,000,000 in band moderate,
               purpose risk_management); complexity=simple (class T2);
               tau(moderate,simple)=Tier 3 under ruleset 2026.09.1"}
```

**Tier 3, and everything downstream changes.** No quorum: a Tier 3 version is
approved by one authorised person, and opening a quorum for it is refused —

```json
{"error": "no_quorum_required",
 "detail": "a tier 3 version is approved by one authorised person, so there is
            no quorum to open",
 "remediation": "approve it directly"}
```

— which is the mirror image of the `quorum_required` refusal the Tier 2
scorecard meets when somebody approves directly. One vocabulary, two refusals,
and which one you get is derived rather than chosen. Warrant lifetimes move too:
Tier 3 descriptors live an hour with fifteen minutes of grace, against sixty
seconds and no grace at Tier 1.

> **A gap worth naming.** The kernel declares **one** `input_schema`, and for a
> stateful model the fit's `X` and the score's `X` are not the same object: the
> fit reads a series of `log_return`, the score reads `last_shock` and
> `last_variance`. The schema above is the fit's, because `L-W10` is the law
> that consumes it — a featureset has to provide what the kernel declares it
> reads, and no featureset provides a variance the previous call produced. So
> the score's inputs are enforced by the runtime's own refusals in §4 rather
> than by the grammar. That is a real asymmetry in the design, not a
> simplification for the tutorial, and it is why §4's two refusals had to be
> written by hand.

---

## 3 · The fit, and what the optimiser is actually doing

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch","environment":"prod",
       "principal":"svc/model-lab","declared_use":"model_development",
       "featureset":"eq_vol_series","featureset_version":1,
       "window":{"from":1609459200,"to":1735603200},"as_of":1736899200}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameter-fits \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch","snapshot_id":"01b7...",
       "environment":"prod","principal":"svc/model-lab",
       "declared_use":"model_development",
       "window":{"from":1609459200,"to":1735603200},
       "name":"garch_2024","kind":"coefficients"}'
```

```json
{"id": "ps-9042", "name": "garch_2024", "state": "proposed",
 "provenance": "fitted", "kind": "coefficients",
 "values_inline": {"omega": 0.0000100, "alpha": 0.0807, "beta": 0.8601},
 "diagnostics": {"n": 1008, "series": "log_return",
                 "log_likelihood": 3122.4, "iterations": 61, "converged": true,
                 "persistence": 0.9408,
                 "long_run_variance": 0.000169,
                 "sample_variance": 0.000169,
                 "mean_removed": 0.00021,
                 "family": "garch11", "rows": 1008, "fitted_in_ms": 812.7},
 "digest": "sha256:7b3e…"}
```

### The three deliberate choices inside that number

`core/execution/runtimes/estimator.py` makes three decisions a GARCH
implementation has to make, and each is stated rather than left to the library:

**The mean is removed first, and the recursion is seeded with the sample
variance.** Seeding `h₀` with the first squared residual instead would make the
fit depend on which row happened to be first in the extract — a parameter set
that changes when the data is re-sorted is not a parameter set anybody can
replay. `mean_removed` is reported so a reviewer can see what was subtracted.

**Stationarity is enforced inside the objective, not checked after it.** The
negative log-likelihood returns `+inf` whenever `ω ≤ 0`, `α < 0`, `β < 0` or
`α + β ≥ 0.9999`, so the simplex cannot walk out of the stationary region and
come back with a plausible-looking answer. Without the constraint there is no
unconditional variance and the model forecasts an exploding one — and the
diagnostic that would have told you, `long_run_variance`, would be negative.

**There is no randomness anywhere.** Nelder–Mead on a fixed initial simplex,
fixed reflection and contraction coefficients, a fixed tolerance of `1e-10`, a
ceiling of 2,000 iterations. Run it twice on the same rows and it returns the
same digits. That is a governance requirement rather than a nicety: a fit
nobody can reproduce is a number in a register with no provenance, and the
[Monte Carlo tutorial](/tutorials/monte-carlo-end-to-end) is about what happens
when it is not true.

### Reading these three numbers

**Persistence, α + β = 0.9408, first.** It is the decay rate of a variance
shock, so the half-life is `ln(0.5) / ln(0.9408)` ≈ **11.4 trading days**. That
is the single most reviewable fact about the fit: a shock today is half
forgotten in a fortnight. Persistence at 0.99 gives a half-life of 69 days,
which for a limit-sizing model means the limit stays wide for a quarter after a
single bad session — a modelling decision somebody should make on purpose.

**Then `long_run_variance` against `sample_variance`.** They are reported side
by side because that comparison is the check. `ω / (1 − α − β)` is what the model
says the unconditional variance is; the sample variance is what it was. Here both
are `0.000169` — a daily volatility of 1.3%, about 20.6% annualised — and the
agreement is evidence the fit found the right basin. A long-run variance an order
of magnitude away from the sample variance is a fit that has found a corner of
the parameter space, usually with `α + β` pinned against the stationarity ceiling
and `ω` doing all the work.

**`converged` and `iterations` last, and only to confirm.** Sixty-one iterations
against a ceiling of 2,000 is a search that settled comfortably. Fifty of the
2,000 would be suspicious in the other direction.

### The refusal this family exists to demonstrate

This is the first model in the series that can **fail while looking like it
succeeded**. Three numbers from a search that stopped early look exactly like
three from one that finished.

```json
{"error": "fit_did_not_converge",
 "detail": "the likelihood had not settled after 2000 iterations, so these three
            numbers are where the search happened to stop rather than where they
            belong",
 "remediation": "a longer or cleaner series usually settles; recording an
                 unconverged fit as a parameter set would put a number in the
                 register that nobody could reproduce or defend"}
```

**Refused, not recorded with a flag.** A flag on a row is something a downstream
reader has to remember to check, and the register's whole claim is that nobody
has to remember anything. The other refusals this family produces are
`series_is_constant` (a series with no variation has no volatility to model),
`unknown_family` (the captive engine implements `ols` and `garch11` and refuses
the rest by name), and `too_few_rows` below thirty.

### ARMA, ARIMA, EGARCH and the rest

They sit in **exactly this slot**: `estimated_coefficients` / `estimate`, with
the order `(p, d, q)` in the kernel `entry` and the fitted φ/θ in `P`. MAYA's
captive engine implements two families and says so — a warrant naming a third
is refused by name, listing what it does have, rather than failing three layers
down. Fit the others in your own engine and deliver the parameters back under
the warrant, as in §6 of
[the regression tutorial](/tutorials/linear-regression-end-to-end).

Nothing about the governance changes. That is the point of separating the
estimator from the register.

---

## 4 · Scoring, and the state problem

Here is what makes a time-series model genuinely different at run time.

A GARCH does not predict a level; it predicts a **variance**, and to do that it
needs the last shock and the last variance. Those arrive as inputs the caller
supplies — because a forecast that invented them would not be reproducible, and
reproducibility is the entire basis on which a validator can replay it.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch#champion","environment":"prod",
       "principal":"svc/limits","declared_use":"limit_sizing"}'

curl -u svc/limits:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch#champion","environment":"prod",
       "principal":"svc/limits","declared_use":"limit_sizing",
       "inputs":{"features":{"last_shock":-0.0142,"last_variance":0.000169}}}'
```

```json
{"descriptor_id": "wd-7710",
 "model_urn": "maya://model/markets.vol.garch", "version": "1.0.0",
 "prediction": {"family": "garch11",
                "prediction": 0.0001716,
                "conditional_variance": 0.0001716,
                "conditional_volatility": 0.013100,
                "from_state": {"last_shock": -0.0142,
                               "last_variance": 0.000169}},
 "boundary_ok": true, "boundary_violations": [], "latency_ms": 1.4}
```

**`from_state` is the whole reason this section exists.** The answer says which
state it ran on, so replaying it is a matter of reading the record rather than
reconstructing what the caller must have had. Two refusals guard it:

```json
{"error": "state_required",
 "detail": "a one-step GARCH forecast needs 'last_variance', which is state
            carried from the previous step rather than an input",
 "remediation": "supply last_shock and last_variance from the previous
                 observation; a forecast that invented them would not be
                 reproducible"}
```

```json
{"error": "state_not_a_variance",
 "detail": "last_variance was -0.0004, and a variance is positive",
 "remediation": "supply the previous step's conditional variance"}
```

The second looks pedantic and is not. A negative variance reaching the recursion
produces a finite, plausible, entirely wrong number, and the next step compounds
it — the failure is silent and self-propagating, which is the worst combination
there is.

### The consequence for testing

If a thing remembers, you cannot learn what it does by asking it questions one
at a time. Two systems can agree on every single call and differ on the second
call of every pair.

That is a rule about what a "patch release" claim is worth. For an artefact
carrying state, **a test set of individual cases cannot support the claim at any
size** — not because the suite is too small, but because every element of it has
length one. Your probe set has to be *sequences*: seed the state once, run the
series, compare the trajectory. The
[Monte Carlo tutorial](/tutorials/monte-carlo-end-to-end) has the incident that
makes this concrete.

---

## 5 · Monitoring a model with no labels

The regression waited a year for its labels. This model's outcome is known
tomorrow — and that turns out to constrain which monitor is definable.

A `calibration` monitor is **label-dependent** in MAYA, exactly like
`performance`, so it must declare a delay:

```json
{"error": "label_delay_required",
 "detail": "a 'calibration' monitor compares predictions to outcomes, so it must
            declare how long those outcomes take to arrive",
 "remediation": "set label_delay_days; for a 12-month PD model that is 365"}
```

For a one-day-ahead variance forecast the honest answer is `1`, and saying so is
not a formality: it is what makes the cohort split correct, so today's forecasts
sit out of the window until tomorrow's close.

The test then has to come from the catalogue, and this is where a variance model
meets a real limitation. The catalogue holds eight tests, and **none of them is
an exceedance-count test.** The nearest honest construction is to score the
model's own implied breach probability and let `calibration.expected_vs_actual`
compare it against what happened:

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.vol.garch","name":"1d 99% coverage",
       "kind":"calibration","test_key":"calibration.expected_vs_actual",
       "threshold":{"target":1.0,"tolerance":0.5},
       "owner":"person/j.okafor","cadence_days":1,"label_delay_days":1,
       "breach_severity":"High","escalate_after":3,
       "reference":{"nominal":0.01,"horizon_days":1}}'
```

Each row is one session: `score` is the nominal breach probability the model
implied (0.01), `label` is whether the realised return actually breached the
interval. The test returns predicted rate over observed rate — 1.0 is
calibrated, above 1 over-predicts breaches, below 1 under-predicts them, which
for a limit model is the dangerous direction.

Over 250 sessions a 99% one-day interval should be breached about **2.5 times**.
Six breaches gives a ratio of 0.42 and is a finding. Zero breaches is also a
finding, and it is the one people forget to raise — a model that never breaches
is sizing limits from a variance it is systematically overstating.

> **How zero breaches is caught, honestly.** With no breaches in the window the
> ratio has no denominator, so `expected_vs_actual` returns *not computable*,
> which does not pass, which opens a breach and raises a finding. The right
> outcome, reached by an accident of arithmetic rather than by design. Worth
> knowing which, because a test that fires for the wrong reason is one that will
> stop firing when somebody fixes the arithmetic.

Everything from `stability.psi` on the score distribution is available too, and
needs no labels at all — but on its own it tells you the forecasts have moved,
not that they were wrong.

---

## 6 · Approve, promote

Tier 3, so a single authorised approval rather than a quorum:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/ps-9042/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,
       "note":"persistence 0.9408, half-life 11 days; long-run variance agrees
               with the sample to three figures; converged in 61 iterations"}'

curl -u s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/models/markets.vol.garch/versions/1.0.0/approve

curl -u s.iqbal:mrm-pw -X PUT \
  localhost:5006/api/v1/models/markets.vol.garch/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment":"prod","alias":"champion","semver":"1.0.0"}'
```

That review note is what the training record will carry into its acceptance
section, beside who wrote it and who could not have. Compile it —
`POST /api/v1/training-records/ps-9042` — and the convergence argument stops
living in a reviewer's memory.

---

## What to carry into the next one

Three things this model taught that the regression could not:

1. **An iterative fit has an outcome beyond its numbers.** Convergence is part
   of the result, and a result that does not carry it is not reviewable.
2. **A constraint enforced inside the objective is not the same as one checked
   afterwards.** The first makes an inadmissible answer unreachable; the second
   makes it reportable, which is a different and weaker thing.
3. **State is not input.** The moment an artefact remembers, single-call testing
   stops being evidence — which comes back with force in
   [the Monte Carlo engine](/tutorials/monte-carlo-end-to-end).

Next: [a derivative pricer](/tutorials/derivative-pricing-end-to-end), where
there is nothing to fit at all, and the entire risk moves onto the conventions.
