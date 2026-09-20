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
| 06 | [IFRS 9 expected credit loss](06-ifrs9-expected-credit-loss/) | Banking, impairment | Composite with its own parameters | Judgements as approved parameter sets, and a portfolio test that finds a 2.67× over-provision the per-account error cannot see. |
| 10 | [Factor models, CAPM to Fama–French](10-factor-models/) | Asset management | Simple then multiple regression | Two versions of one model: a semantic diff, a contract that grew, and the maturity ladder from candidate to retired. |
| 07 | [Card-fraud neural network](07-neural-network/) | Banking, card fraud | Feed-forward network, **declared black box** | What is left to hold to account when the mathematics is unreadable. MAYA refuses to score it, and says so rather than implying it did. |

### The catalogue

Fifty in all. Six are built; the rest are listed with their final numbers, so a folder name
never has to be renumbered. The order within each group is roughly the delivery order, and
every entry is there for a **distinct thing it makes MAYA do** — fifty models that all
exercised the same six calls would demonstrate nothing one study could not.

**Banking — retail and wholesale credit**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 01 | Retail credit PD scorecard ✅ | Fitted logistic | Bitemporality; a leakage certificate that refuses every row; a fit tied to its data by checksum |
| 02 | Scheduled mortgage cashflow ✅ | Closed-form, no fit | Whether the code the desk runs *is* the mathematics that was approved |
| 03 | Mortgage prepayment ✅ | Fitted hazard | A workspace, an impact analysis and a shadow replay of a change proposed under a live model |
| 04 | HELOC exposure at default ✅ | **Composite router** | Two members with different functional forms; a parameter set each; a seal that waits for both |
| 06 | IFRS 9 expected credit loss ✅ | **Composite** with its own parameters | PD × LGD × EAD under one warrant, plus two judgements that belong to the combination rather than to any member |
| 09 | Basel IRB regulatory capital | Closed-form, no fit | Regulatory constants that are approved and never fitted; the Vasicek single-factor formula |
| 12 | LGD and recovery, two-stage | Fitted, conditional | A target conditional on another model's event: cure rate, then loss given no cure |
| 13 | Credit card behavioural scoring | Fitted | A model whose own output changes the population it next sees |
| 14 | Collections roll-rate | Estimated matrix | A Markov transition matrix as a parameter set: a matrix, not a vector |
| 15 | Low-default portfolio rating | Fitted, almost no events | What a warrant can honestly claim when there are twelve defaults |
| 16 | Auto residual value | Fitted curve | A depreciation curve, and a feature that is a published index |
| 07 | Card-fraud neural network ✅ | **Declared black box** | What is left to hold to account when the mathematics is unreadable |
| 17 | AML transaction monitoring | Tree ensemble | An opaque ensemble, and weights carried as a parameter file |
| 18 | AML segmentation | Unsupervised | **No target at all** — a warrant for a model with nothing to predict |
| 19 | Vendor bureau score | Bought black box | What MAYA cannot verify, *marked* unverifiable rather than omitted |

**Banking — asset-liability management and treasury**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 20 | Deposit beta | Fitted regression | A market rate as a date-indexed feature driving a behavioural response |
| 21 | Deposit decay and runoff | **Exponential** | Fitted in log space, stated and used in natural space |
| 22 | LCR outflow rates | Regulatory constants | A model that is nothing but constants, and the argument for governing it anyway |
| 23 | Funds transfer pricing curve | Constructed | A model whose consumers are other desks, and the licence question that raises |
| 24 | Interest-rate risk in the banking book | Scenario-conditional | The scenario as a pinned feature set |

**Markets — pricing**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 05 | European option pricing ✅ | Closed-form, **calibrated** | A parameter nobody can observe; a conformance test that passes on a narrow domain |
| 11 | Nelson–Siegel yield curve | **Non-linear** calibration | Non-linear in one parameter: a search with least squares inside it |
| 25 | Implied volatility surface (SABR) | Calibrated | A misfit the model cannot hide |
| 26 | Hull–White short rate | Calibrated | Calibration to a grid of instruments rather than to outcomes |
| 27 | Curve bootstrapping (Svensson) | Constructed | The sharpest governance question in the set: is a yield curve a feature or a model? |
| 28 | CDS hazard-rate bootstrapping | Constructed | A term structure of hazards, each solved from the last |
| 29 | Bond duration and convexity | Closed-form | Analytic derivatives of a governed formula |
| 30 | American option, binomial lattice | Recursive | **Recursion**: the boundary of MAYA's row-wise formula language |
| 31 | Asian and barrier options | Monte Carlo | Output that is not deterministic, and what reproducibility means then |
| 32 | Convertible bond | Composite | A composite over an equity model and a credit model |

**Markets — risk**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 08 | ARIMA and GARCH | Time series | Lags as **governed feature definitions**; state between rows; a **joint** parameter constraint |
| 33 | Historical-simulation VaR | No fit | A covenant on **model performance** — the regulatory backtest exception count |
| 34 | Expected shortfall / FRTB | Closed-form | Many outputs from one governed calculation |
| 35 | EWMA covariance | Estimated matrix | A parameter that is a decay, and a matrix output |
| 36 | Stress testing and scenarios | Scenario-conditional | One model, many scenarios, one warrant each |
| 37 | CVA / counterparty exposure | Monte Carlo | A black box plus market-data **licence algebra** |
| 38 | Mean-variance optimisation | Optimisation | An output that is a **vector of weights**, not a scalar |
| 39 | Black–Litterman | Bayesian | Prior and views as separately approved parameter sets |
| 10 | CAPM beta → Fama–French ✅ | Simple then multiple regression | **Two versions of one model**, MAYA's semantic diff, and the whole maturity ladder to retirement |

**Economics**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 40 | Inflation nowcast | Mixed-frequency regression | **Data vintages**: what was knowable at the time |
| 41 | GDP nowcast, dynamic factor | Latent state | A state nobody observes |
| 42 | Demand elasticity | **Log–log** | A logarithmic fit used in natural space |
| 43 | Okun's law | Simple linear regression | The simplest possible model, governed properly, as the floor case |

**Life sciences**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 44 | Cox proportional hazards | Survival | Censoring: rows whose outcome has not happened *yet* |
| 45 | Gompertz–Makeham mortality | **Exponential law** | A century of published parameters to argue with |
| 46 | Gene-expression classifier | Regularised, wide | More features than rows, and what a contract means then |
| 47 | Pharmacokinetics, two compartments | ODE solution | A sum of exponentials |
| 48 | SIR epidemic | Recursive | A model used for decisions before it can be validated |

**Operations**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 49 | LLM complaint triage | LLM | A prompt as a versioned parameter set, and a model MAYA never executes |
| 50 | Spreadsheet-lifted provision overlay | Lifted from Excel | MAYA judging the lift against the workbook's own results |

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
