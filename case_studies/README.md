# MAYA case studies

Each folder here is a worked case study: a real modelling problem from banking, finance,
economics or biology, carried through MAYA end to end — features defined and approved,
data pinned point-in-time, a model registered with its specification document, a warrant
drawn, parameters approved, an execution warrant sealed, and a covenant that takes the
model out of service when its inputs stop resembling what it was built on.

They exist to be **demonstrated**. Every study is a sequence of small scripts, and every
script prints what it did and what MAYA refused to let it do. Nothing is staged: the
refusals are the platform's real behaviour, and a study that could not make its point
honestly says so instead.

## How a study is laid out

```
NN-name/
  README.md        the theory, the mathematics, the analysis, and the numbers from a real run
  make_data.py     writes the study's input feeds to data/ — the recipe, in prose and code
  data/*.csv       those feeds, committed, so a reader can open exactly what MAYA was given
  study.py         the declarations: names, feature definitions, the model, its document
  setup_features.py … one script per step of the lifecycle (see each study's README)
  run.py           runs every step in order, against a MAYA built from nothing
```

Every study's README carries a table of **what each script does and what it shows**.

## Running one

```bash
# the whole story at once, about ten to fifteen seconds
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py

# or one step at a time, which is how to demonstrate it
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/setup_features.py --reset
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/setup_featureset.py
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/setup_model.py
#  … and so on
```

`--reset` deletes that study's MAYA and starts again from nothing. `--quiet` prints the
results without the narration.

**Between any two steps you can open the web UI on exactly what has been built so far** —
`show_estate.py` prints the command — and walk through the catalog, the pin preview, the
warrant with its leakage certificate, the lineage canvas and the audit log on screen. That
is the demonstration; the console output is the script of it.

## Nothing to install, nothing to configure

A study needs no server, no database, no API key and no namespace prepared by hand. The
first script builds a complete MAYA at `case_studies/runs/<namespace>/` in about two
seconds — real database, real Delta lake, real permissions, real workflow, real signer, one
user per built-in role — and every later script opens the same one. This is
`maya.testing`, a supported part of the platform, not a test fixture smuggled into a demo.

Everything the studies do then goes through **`maya.sdk.Client`, as a named user with that
user's roles**. That is deliberate and it is the point: a demonstration that reached past
the SDK would prove nothing about the SDK. The only exception is `maya.drain()`, which runs
the queued jobs a deployment's job workers would run.

Because the users are named, the refusals are real. When a study shows a feature designer
being refused permission to approve her own feature, that is MAYA's capability matrix
saying no to `dana`, not a script pretending.

## The studies

Finished studies first, then the catalogue they are being drawn from. Each study is chosen
for a **distinct thing it makes MAYA do** — a library of fifty models that all exercised the
same six calls would demonstrate nothing that one study could not.

### Finished

| | Study | Domain | Model type | What it is really about |
| --- | --- | --- | --- | --- |
| 01 | [Retail credit PD scorecard](01-retail-credit-pd-scorecard/) | Banking, retail credit risk | Fitted logistic regression | Bitemporality. A leakage certificate that refuses every row of a panel, and the written exception that lets the work proceed. A fit tied to its data by checksum. |
| 02 | [Scheduled mortgage cashflow](02-mortgage-cashflow/) | Banking, mortgage ALM | Closed-form, **nothing to fit** | Whether the code the desk runs is the same thing as the mathematics that was approved. A valid implementation with the commonest mortgage bug in it, caught. |
| 03 | [Mortgage prepayment](03-mortgage-prepayment/) | Banking, mortgage valuation | Fitted logistic hazard | What happens when somebody proposes changing a feature underneath a live model: a workspace, an impact analysis, and a shadow replay that prices a reasonable-sounding change at 60% of the book. |
| 04 | [HELOC exposure at default](04-heloc-exposure/) | Banking, retail secured credit | **Composite router** over two fitted members | One warrant over two models with different functional forms, a parameter set per member, and a seal that refuses while half the composite is unfitted. |
| 05 | [European option pricing](05-option-pricing/) | Finance, equity derivatives | Closed-form, **calibrated** | A parameter nobody can observe. Black–Scholes from LaTeX, a volatility surface as nine parameters, and a conformance test that passes on a narrow domain and fails on the whole chain. |
| 07 | [Card-fraud neural network](07-neural-network/) | Banking, card fraud | Feed-forward network, **declared black box** | What is left to hold to account when the mathematics is unreadable. MAYA refuses to score it, and says so rather than implying it did. |

### The catalogue

Fifty in total. The order is roughly the delivery order, and it is chosen so that each new
study adds a capability rather than another instance of one.

**Banking — retail and wholesale credit**

| | Study | What it adds |
| --- | --- | --- |
| 05 | LGD and recovery, two-stage | A target conditional on another model's event: cure rate, then loss given no cure |
| 06 | IFRS 9 / CECL expected credit loss | A **composite pipeline** over PD, LGD and EAD — reusing studies 01, 05 and 04 as members, under one warrant |
| 07 | Basel IRB regulatory capital | Regulatory constants that are approved, never fitted; the Vasicek single-factor formula |
| 08 | Credit card behavioural scoring and limits | A model whose own output changes the population it next sees |
| 09 | Collections roll-rate | A Markov transition matrix as a parameter set: a matrix, not a vector |
| 10 | SME / low-default-portfolio rating | A model with almost no events, and what a warrant can honestly claim about one |
| 11 | Auto residual value | A depreciation curve, and a feature that is a published index |
| 13 | AML transaction monitoring | A gradient-boosted ensemble, and weights carried as a parameter file |
| 14 | AML segmentation | **No target at all** — a warrant for an unsupervised model |
| 15 | Vendor bureau score | A bought black box, with what MAYA cannot verify *marked* unverifiable |

**Banking — ALM and treasury**

| | Study | What it adds |
| --- | --- | --- |
| 16 | Deposit beta | Market rate as a date-indexed feature driving a behavioural response |
| 17 | Deposit decay and runoff | An **exponential** fitted in log space and stated in natural space |
| 18 | LCR outflow rates | A model that is entirely regulatory constants, and the argument for governing it anyway |
| 19 | Funds transfer pricing curve | A model whose consumers are other desks, and the licence question that raises |
| 20 | Interest-rate risk in the banking book | Scenario-conditional output: the scenario as a pinned feature set |

**Markets — pricing**

| | Study | What it adds |
| --- | --- | --- |
| 22 | Implied volatility surface | Calibration per bucket, and a misfit the model cannot hide |
| 23 | Hull–White / Vasicek short rate | Calibration to a grid of instruments, not to outcomes |
| 24 | Nelson–Siegel yield curve | **Non-linear in a parameter**: a grid search with least squares inside it |
| 25 | Curve bootstrapping (Svensson) | The sharpest governance question in the set: is a yield curve a feature or a model? |
| 26 | CDS hazard-rate bootstrapping | A term structure of hazards, each solved from the last |
| 27 | Bond pricing, duration and convexity | Analytic derivatives of a governed formula |
| 28 | American option, binomial lattice | **Recursion**: the boundary of MAYA's row-wise formula language |
| 29 | Asian and barrier options, Monte Carlo | A model whose output is not deterministic, and what reproducibility means then |
| 30 | Convertible bond | A composite over an equity model and a credit model |

**Markets — risk**

| | Study | What it adds |
| --- | --- | --- |
| 31 | Historical-simulation VaR | A covenant on **model performance** — the regulatory backtest exception count — rather than on inputs |
| 32 | Expected shortfall / FRTB sensitivities | Many outputs from one governed calculation |
| 33 | GARCH(1,1) volatility | State carried between rows, and a **joint** parameter constraint (α + β < 1) |
| 34 | ARIMA forecasting | Lags as **governed feature definitions** rather than hidden in code |
| 35 | EWMA covariance | A parameter that is a decay, and a matrix output |
| 36 | Stress testing and scenario expansion | One model, many scenarios, one warrant each |
| 37 | CVA / counterparty exposure | Monte Carlo behind a black box, plus market-data **licence algebra** |
| 38 | Mean-variance portfolio optimisation | An output that is a **vector of weights**, not a scalar |
| 39 | Black–Litterman | Prior and view as separately approved parameter sets |
| 40 | CAPM beta → Fama–French factors | Simple then multiple linear regression as **two versions of one model**, with MAYA's semantic diff and the deprecation path |

**Economics**

| | Study | What it adds |
| --- | --- | --- |
| 41 | Inflation nowcast | Mixed frequency, and **data vintages**: what was knowable at the time |
| 42 | GDP nowcast, dynamic factor | A latent state nobody observes |
| 43 | Demand elasticity | A **log–log** fit used in natural space |
| 44 | Okun's law | The simplest possible regression, governed properly, as a floor case |

**Life sciences**

| | Study | What it adds |
| --- | --- | --- |
| 45 | Cox proportional hazards survival | Censoring: rows whose outcome has not happened *yet* |
| 46 | Gompertz–Makeham mortality | An exponential law with a century of published parameters to argue with |
| 47 | Gene-expression classifier | Many more features than rows, and what a contract means then |
| 48 | Pharmacokinetics, two-compartment | An ODE solution as a sum of exponentials |
| 49 | SIR epidemic model | Recursion again, and a model used to make decisions before it can be validated |

**Operations**

| | Study | What it adds |
| --- | --- | --- |
| 50 | LLM complaint triage | A prompt as a versioned parameter set, and a model MAYA never executes |
| 51 | Spreadsheet-lifted provision overlay | Lifting a model out of Excel, and MAYA judging the lift against the workbook's own results |

Fifty-one are listed; the last one to be built gets dropped if the count matters.

## What a case study is not

It is not a benchmark — `docs/BENCHMARKS.md` holds the measured throughput and capacity
figures. It is not a tutorial — `content/tutorials` walks a newcomer through the platform
step by step. And it is not a test — the suite under `tests/` is what holds MAYA's
behaviour in place. A case study is the argument, made on a concrete problem, that the
governance is worth having.

---

The input data in every study is **synthetic**, generated by the `make_data.py` beside it
from a seeded recipe stated in that file's docstring. No real borrower, loan, patient or
counterparty appears anywhere in this folder.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
