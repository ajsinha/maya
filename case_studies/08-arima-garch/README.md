# Case study 8 — AR(2) and GARCH(1,1)

**Domain:** markets, market risk · **Model type:** time series, a **row-wise formula** for the
mean and a **declared black box** for the variance · **What it is really about:** governing
models whose rows are not independent. The lags become governed feature definitions, the
stationarity conditions become **joint constraints** MAYA enforces, the holdout becomes the
**last stretch of dates** rather than a random sample, and a recursion MAYA cannot write is
still run, blind, on data nobody has seen.

```bash
.venv/bin/python case_studies/08-arima-garch/run.py      # about fifteen seconds
```

Five scripts, in this order, sharing the project's MAYA (this study is the `market_risk`
namespace).

| Script | What it does | What it shows |
|---|---|---|
| `setup_data.py` | Defines the daily index feed with its two lags and the squared return as declared transforms, approves it, and pins a panel point-in-time. | The lag structure of an AR model in a governed definition, grouped per index, instead of in a line of a fitting script. |
| `setup_models.py` | Registers AR(2) as a formula with two joint stationarity constraints, and GARCH(1,1) as a declared black box whose code goes through the six-rung ladder. | What a formula can say and what it cannot: the recursion that makes GARCH a black box, and a constraint on it all the same. |
| `fit_mean.py` | Draws a **time-ordered** training warrant, fits AR(2) by least squares, is refused an explosive parameter set, and has the fit approved, scored blind on the last dates and sealed. | A holdout that is the future of the training data, and a joint constraint biting where no bound on a single parameter would. |
| `fit_vol.py` | Draws a time-ordered warrant on the squared return, fits GARCH by pooled maximum likelihood, is refused a persistence above one, and has MAYA score the fit in the sandbox. | A likelihood fit close to the generating process, and a model MAYA cannot read evaluated on rows the developer never saw. |
| `go_live.py` | Draws an execution warrant with a covenant on the forecast variance, reports a calm week, then a crash week that breaches it. | A model taken out of service by its own covenant the moment its forecast is too high to act on unreviewed. |

## The two halves of the model

Daily log returns $r_t$ on an equity index are close to unpredictable in their level and
strongly predictable in their size. The study models both, and they are the two halves of
what it is about.

**The conditional mean is an AR(2):**

$$
\hat r_t = c + \phi_1\, r_{t-1} + \phi_2\, r_{t-2}
$$

Once $r_{t-1}$ and $r_{t-2}$ are columns, this is a row-wise formula, and MAYA can read it,
typeset it and evaluate it. So the lags are made columns *in the feature*: `lag 1` and `lag 2`
of `ret` are transforms on the governed definition, grouped by index so that one index's
yesterday is never another's. A reviewer learns that the model is AR(2) from the definition,
without reading any Python.

An AR(2) is **stationary** only inside a triangle in $(\phi_1, \phi_2)$:

$$
\phi_1 + \phi_2 < 1, \qquad \phi_2 - \phi_1 < 1, \qquad |\phi_2| < 1
$$

The third is a bound on one parameter. The first two are **joint**: each coefficient can sit
anywhere inside $(-1, 1)$ while the pair describe a process that explodes. They are properties
of the model, so the model declares them, each with a sentence saying what breaking it means.

**The conditional variance is a GARCH(1,1):**

$$
\sigma_t^2 = \omega + \alpha\, \varepsilon_{t-1}^2 + \beta\, \sigma_{t-1}^2
$$

The right-hand side holds *yesterday's variance*, which is not an observable column. It is a
state carried from row to row, and it depends on the parameters, so no lag transform can
produce it. MAYA's formula language evaluates one row at a time, and writing GARCH in it would
be a lie. It is registered instead as a **declared black box**: an input contract, a written
account of what it estimates and how, a code artifact, and the stationarity constraint
$\alpha + \beta < 1$. The persistence $\alpha + \beta$ decides how long a shock lasts, a
half-life of $\ln 0.5 / \ln(\alpha + \beta)$ days, and at one or above the variance has no
long-run level at all.

The artifact recurses each index on its own, starts from the unconditional variance
$\omega / (1 - \alpha - \beta)$, and measures each day's shock against the mean of the returns
*before* it, so nothing after day $t-1$ enters the forecast for day $t$.

## Why the holdout is the last dates

A training warrant normally splits rows at random, by hashing each row's key with the seed.
For a time series that is wrong twice over. It trains on the future and tests on the past,
which is the look-ahead a leakage certificate exists to stop, arriving by a different door.
And it scatters the test rows, so a model that carries state from one day to the next cannot
even be run on them: a GARCH recursion over every fifth day is not the model.

So the warrants here are drawn with **`shape: time_series`**. The earliest 70% of the dates
train, the next 10% validate, and the last 20% are the escrowed test. Every row of one date
lands in the same partition, so the three indices split at the same moment, and the rows stay
in date order, which is the only order a recursion can run in. The seed does not move a
time-ordered split, because there is nothing random in it.

## What a run shows

From a run of `run.py` against an empty estate (the data is generated with a fixed seed, so
these numbers repeat):

| Step | Result |
|---|---|
| The feed | 4,200 rows: 3 indices × 1,400 business days, 2 January 2020 to 14 May 2025 |
| The pin | `ret`, `retLag1`, `retLag2`, `retSq`, 4,200 rows as of 30 June 2025, known by 15 July |
| The GARCH ladder | all six rungs passed at sandbox tier *strong*, including two identical runs |
| Leakage certificates | both warrants *certified* |
| Escrowed holdout | 840 rows each: the last 280 days of each index |
| What the developer can download | 2 January 2020 to 17 April 2024 (train and validation) |
| AR(2) fit | $c$ = +0.00041 (process +0.00028), $\phi_1$ = +0.0554 (+0.0620), $\phi_2$ = −0.0523 (−0.0410); $R^2$ = 0.0055 |
| Refused | $\phi_1$ = 0.75, $\phi_2$ = 0.35: "phi1 + phi2 < 1 is half of AR(2) stationarity…" |
| AR(2) blind score | RMSE 0.01002 on 840 rows, against a return volatility of 0.01139 |
| GARCH fit | $\omega$ = 3.18e−6 (process 3.39e−6), $\alpha$ = 0.0919 (0.092), $\beta$ = 0.8835 (0.880) |
| Persistence | $\alpha + \beta$ = 0.9754: a shock halves in 28 days |
| Against a constant variance | likelihood-ratio statistic 334 on 2 degrees of freedom |
| Refused | $\alpha$ = 0.15, $\beta$ = 0.90: "alpha + beta < 1 is stationarity…" |
| GARCH blind score | RMSE of the variance 1.46e−4 on 840 rows, **scored in the sandbox** |
| A calm week | largest forecast variance 1.53e−4; warrant *live* |
| A crash week | largest forecast variance 8.72e−4, above the covenant's 6e−4; warrant **suspended**, and the next call refused naming the contact |

The AR(2) result is the honest one for daily returns: the fit recovers the sign and rough size
of the coefficients, explains half a percent of the variance, and its forecast error is almost
the whole volatility. That is what an efficient market looks like, and a mean model that
claimed more would be the one to worry about. The GARCH fit is the opposite: volatility is
predictable, the likelihood rises by 167 over a constant variance, and the parameters land
within a few percent of the process that generated the data.

The GARCH blind score is measured against the squared return, a one-observation estimate of a
day's variance, so it is large by nature. What matters is that it was measured at all: MAYA
cannot read the model, and it still ran the validated code on 840 rows nobody had seen.

## What to show in the UI

- **Catalog → Features → `daily_index_returns`**, *Definition* tab: the transform pipeline, `lag 1`,
  `lag 2` and `retSq`, as part of the approved version.
- **Catalog → Models → `daily_return_variance_garch`**: the black-box declaration, the constraint and its
  sentence, and the *Code* tab's ladder report, all six rungs.
- **Warrants → Training → `garch_fit_2025`**: the spec with `shape: time_series`, the
  certificate, the escrowed holdout, the blind score and `scored_in: sandbox`.
- **Warrants → Execution → `garch_vol_live`**: *suspended*, the breach that did it, and the
  custody chain.

## The data

`make_data.py` generates three equity indices (AZX, BQI and CVM) from one AR(2)-GARCH(1,1)
process with a fixed seed, 1,400 business days each, after a 400-day burn-in. The process is
$c$ = 0.00028, $\phi_1$ = 0.062, $\phi_2$ = −0.041, $\omega$ = 3.39e−6, $\alpha$ = 0.092,
$\beta$ = 0.880: a long-run daily volatility near 1.1% (about 17.5% a year) and a persistence
of 0.972, where real equity volatility sits. Every close is known at 21:30 UTC the same day,
which is the knowledge time on each row. Because the three indices share one process, one
pooled parameter set is correct for all three, and the fit uses their summed likelihood with
each series recursed on its own.

## Who does what

| Person | Role | In this study |
|---|---|---|
| dana | feature designer | defines the daily feed and its transforms |
| mick | feature manager | approves the feature and the panel, and pins it |
| devi | model developer | builds the panel, draws both training warrants, fits both models |
| mona | model designer | registers both models, their documents and the GARCH code |
| mgr | model manager | approves the models and the parameter sets, seals the warrants, draws the execution warrant |
| lara | model manager | approves the execution warrant, so the person who drew it is not the one who approves it |

## Running it

```bash
.venv/bin/python case_studies/08-arima-garch/run.py               # the whole study
.venv/bin/python case_studies/08-arima-garch/setup_data.py        # or one step at a time
.venv/bin/python case_studies/08-arima-garch/setup_models.py
.venv/bin/python case_studies/08-arima-garch/fit_mean.py
.venv/bin/python case_studies/08-arima-garch/fit_vol.py
.venv/bin/python case_studies/08-arima-garch/go_live.py
```

On Windows use `.venv\Scripts\python`. The steps share the project's MAYA, so between any two
you can start the web server and look at what the last one created. `--reset` removes this study's
namespace and runs it again from nothing; `--reset-all` rebuilds the whole estate.

## What MAYA refused, on purpose

- **An explosive AR(2).** $\phi_1$ = 0.75 and $\phi_2$ = 0.35 are each inside $(-1, 1)$; their
  sum is 1.1. Refused at upload, with the constraint's own sentence.
- **A persistence above one.** $\alpha$ = 0.15 and $\beta$ = 0.90 are each inside $[0, 1]$;
  their sum is 1.05. Refused at upload.
- **A forecast too high to act on unreviewed.** The crash week's largest variance breached the
  output covenant, the warrant suspended itself, and the next call was refused with the name
  of the person to contact.

## What MAYA had to learn

Building this study found three places where MAYA assumed rows were independent, and each is
now fixed and tested:

- **A feature offered only its uploaded columns.** A lag or a derived column exists only after
  the transforms run, and a feature set could not map `retLag1` although every row of the pin
  held it. A feature now reports its schema as the transforms leave it.
- **A model could not read an index column.** The GARCH artifact keeps the three series apart by
  the `index` column, and the input contract only accepted a feature set's attributes. An index
  column is on every row, so a model may now bind to one, and a text input is no longer forced
  to be numeric.
- **Every split was random.** The time-ordered split above is new: `shape: time_series` on a
  training warrant, in the SDK, the API and the warrant form.

## What this study does not show

- **ARIMA with differencing, or moving-average terms.** An MA term is a recursion on past
  errors, like GARCH, and would be a black box for the same reason. Differencing is a transform
  and would work exactly as the lags do.
- **Asymmetric volatility.** Equity volatility rises more after falls than after rises; GJR or
  EGARCH are the usual answers, and the model document says so under its limitations.
- **Multi-day forecasts.** The term structure of volatility follows from the same parameters
  and is only as good as the stationarity it assumes.
- **Re-fitting on a rolling window.** Each warrant is one fit on one pin. A production process
  that refits monthly would draw a warrant per refit, each with its own holdout.
- **A formal forecast evaluation.** A variance forecast is better judged by a loss such as
  QLIKE, or a value-at-risk backtest, than by the RMSE MAYA computes. The study reports the RMSE
  because it is what MAYA scores; a validator would add the others as evidence.
