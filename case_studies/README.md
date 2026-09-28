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


### If your IDE says `maya_demo` cannot be imported

It can. Each `run.py` and step script adds this folder to `sys.path` before importing, at
runtime, and PyCharm's inspector does not execute that — so it reports an unresolved import
for code that runs. In PyCharm, right-click `case_studies` and choose **Mark Directory as →
Sources Root**; the warning goes and you get completion on the helper. Nothing about the
scripts needs to change, and running them from the project root has always worked:

    .venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py

New to MAYA? The [quick start](../docs/QUICKSTART.md) installs it and runs study 01 with you,
step by step.

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

`--reset` removes that study's namespace and everything in it, then runs the study from
nothing. `--quiet` prints the results without the narration.

**Every study runs in one estate, configured by one file.** A study reads
`config/application.yaml` — the same file `run_maya_web.py` reads, with nothing overridden
— so one database, one lake, one set of users, and one web application that serves all of
them. Serving it needs no arguments at all:

    .venv/bin/python run_maya_web.py

Studies stay apart by **namespace**, which is what namespaces are for: `retail_credit`,
`rates`, `impairment` and so on sit side by side in the catalog. To put a study somewhere
else, pass the setting exactly as you would to the application — `--lake.root=/tmp/demo-lake`,
`--storage.root=/tmp/demo` — and the study passes it straight to the configuration loader.

**Resetting one study, and cleaning up after a failure.** MAYA does not delete governed
objects in a register people rely on. The demonstration estate is a development estate
(`app.environment: dev`), and there an administrator may **purge a namespace**: every row and
every lake file of it goes, and the purge itself is written to the audit log. The studies use
that in three ways:

| Flag | What happens |
|---|---|
| `--reset` | This study's namespace is purged, then the study runs from nothing. The other studies are untouched. |
| *(a failure)* | If a full pass (`run.py`) stops part way, it purges its own namespace, so the next pass starts clean. `--keep-on-failure` leaves the partial work in place for debugging. A single step script that fails is not purged — that would throw away the steps before it — and says how to clean up. |
| `--reset-all` | The **whole** demonstration estate is deleted and built again, every study in it. |

A full pass over a study already in the estate stops and names these options. The same purge
is on **Admin → Namespaces** in a development estate, and refused anywhere else.

**Every study writes into one lake**, at `data/maya-deltalake/`, which is the lake the web
application and the rest of MAYA use — configured once as `lake.root` and shared, because a
demonstration that invented its own storage arrangement would be demonstrating the wrong
thing. A lake table is `<kind>/<namespace>/<name>`, and each study owns a namespace, so
they sit side by side without colliding. The rest of the estate is shared too: one
database (`data/maya.db`), one blob store, one set of signing keys and one log, all under
`data/` as `config/application.yaml` says.

**Between any two steps you can open the web UI on exactly what has been built so far** —
`show_estate.py` prints the command — and walk through the catalog, the pin preview, the
warrant with its leakage certificate, the lineage canvas and the audit log on screen. That
is the demonstration; the console output is the script of it.

### Running a demonstration

Take the steps one at a time and show the UI between them. The console says what MAYA was
asked and what it answered; the screen shows what now exists because of it.

```bash
S=case_studies/01-retail-credit-pd-scorecard

.venv/bin/python $S/setup_features.py --reset   # three feeds become governed features
.venv/bin/python $S/show_estate.py              # prints how to serve this instance
```

`show_estate.py` ends by printing the exact command to run, and it is always the same one,
because every study lives in the estate the application serves by default:

```bash
.venv/bin/python run_maya_web.py
```

Leave that running in its own terminal and open <http://127.0.0.1:8600>. Sign in as any
user in the table above with `Maya-testing-pass-1`. Then carry on with the next step in the
first terminal and refresh the browser — the web tier reads the same database, so the
screen is never a rehearsal of the console.

What is worth showing, in the order the steps create it:

| After | Show in the UI |
|---|---|
| `setup_features.py` | Catalog → the three features, their definitions, their ingested data and the two clocks on it |
| `setup_featureset.py` | The feature set, then its pin: the rows it sealed, the hash that names it, and the members it pinned with it |
| `setup_model.py` | Models → the mathematics rendered from the tree MAYA parsed, the input contract, and the specification document with its required sections |
| `get_training_warrant.py` | Warrants → the leakage certificate. This is the one to dwell on: it refuses, and the refusal is arithmetic rather than opinion |
| `fit_parameters.py` | The parameter set, its bounds, the checksum tying it to the data it was fitted on, and the blind score on rows the developer never saw |
| `get_execution_warrant.py` | The covenant that suspends the warrant, and the custody trail of who did what |
| `show_estate.py` | Lineage → the whole chain as a graph, and Admin → the audit chain verified unbroken |

Sign in as different people to show the same screen refusing different things: `dana` cannot
approve her own feature, `mgr` cannot see the admin estate, `tess` can.

## Nothing to run first, and who you sign in as

**There is no preparation script.** Do not create users, namespaces or a database by hand:
the first script of a study does it, and doing it yourself would leave the study seeding a
namespace that already exists. A study needs no server, no API key and nothing configured.

The first script opens the project's MAYA, creating it under `data/` in about two seconds if
this is the first study ever run: a real database, a real Delta lake, real permissions, real
workflow and a real signer. Every later script opens the same one. The first study also
creates one user per built-in role, through the SDK, exactly as an administrator would, and
each study creates its own namespace:

| User | Role | What they may do in a study |
|---|---|---|
| `dana` | feature designer | Define features, ingest data, submit for approval — and be refused when she tries to approve her own |
| `mick` | feature manager | Approve features and feature sets, pin them point-in-time |
| `mona` | model designer | Register a model's mathematics and write its specification |
| `devi` | model developer | Draw a training warrant, upload parameters, iterate |
| `mgr` | model manager | Approve models, parameter sets and warrants |
| `owen` | model owner | Accountable for the model's use |
| `tess` | techops | Audit, custody, storage, extensions |
| `lara` | second model manager | Only where a policy needs two: an execution warrant submitted by one manager is approved by another |
| `admin` | administrator | The bootstrap user the platform creates itself |

**Every one of them signs in with `Maya-testing-pass-1`.** The one exception is `admin`,
whose password is the platform's dev default and which you should not need.

These are the passwords of a throwaway demonstration instance and are printed here on
purpose. Nothing in `case_studies/` should ever be pointed at an estate that matters.

This is `maya.testing`, a supported part of the platform, not a test fixture smuggled into
a demo.

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
| 11 | [Nelson–Siegel yield curve](11-nelson-siegel-curve/) | Fixed income, rates | Closed-form, non-linearly calibrated | A λ that is a convention rather than a measurement, and a planted bug a recalibration absorbs exactly — so only MAYA's blind score against the specification can see it. |
| 07 | [Card-fraud neural network](07-neural-network/) | Banking, card fraud | Feed-forward network, **declared black box** | What is left to hold to account when the mathematics is unreadable: a contract, weights as a parameter set, a sandboxed ladder on the code, and a blind score computed by running the validated artifact in the sandbox. |
| 08 | [AR(2) and GARCH(1,1)](08-arima-garch/) | Markets, market risk | Time series: formula mean, **black-box** variance | Models whose rows are not independent: lags as governed feature definitions, stationarity as **joint constraints**, a holdout that is **the last dates**, and a recursion MAYA cannot write scored blind in the sandbox |
| 09 | [Basel IRB regulatory capital](09-basel-irb-capital/) | Banking, regulatory capital | Closed-form, **prescribed**, no fit | A formula you may not change, proved by reconciliation. Version 1 misses the maturity floor and cap; a **finding**, a fix, **independent closure**, tier 1, a periodic review and the SR 11-7 inventory row |
| 19 | [Vendor bureau score](19-vendor-bureau-score/) | Banking, retail credit | **Bought black box**, from MLflow | Imported from its MLflow signature, its code validated and **scored blind in the sandbox**, fairness by region, and a drift covenant that takes it from *ok* to *watch* to *breach* |
| 42 | [Demand elasticity](42-demand-elasticity/) | Economics, retail pricing | Linear champion, log–log challenger | **Champion and challenger** on the same escrowed rows: a paired bootstrap interval, a refusal to compare different holdouts, and a decision the challenger's author may not take |
| 45 | [Gompertz–Makeham mortality](45-gompertz-makeham-mortality/) | Life sciences, actuarial | Mortality law, **non-linear** | Fairness when the law forbids the fair answer: a unisex table's bias by sex, invisible to the MAE ratio and marked *systematic*, and the risk **accepted in writing** |
| 49 | [LLM complaint triage](49-llm-complaint-triage/) | Operations, retail banking | **LLM application** | Prompts and guardrails sealed as a version, a fixed evaluation set, recorded runs from a provider MAYA never calls, and approval only on evidence gathered on exactly that definition |

### The catalogue

Fifty in all. Fifteen are built; the rest are listed with their final numbers, so a folder
name never has to be renumbered. The order within each group is roughly the delivery order, and
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
| 09 | Basel IRB regulatory capital ✅ | Closed-form, no fit | Regulatory constants that are approved and never fitted; the Vasicek single-factor formula |
| 12 | LGD and recovery, two-stage | Fitted, conditional | A target conditional on another model's event: cure rate, then loss given no cure |
| 13 | Credit card behavioural scoring | Fitted | A model whose own output changes the population it next sees |
| 14 | Collections roll-rate | Estimated matrix | A Markov transition matrix as a parameter set: a matrix, not a vector |
| 15 | Low-default portfolio rating | Fitted, almost no events | What a warrant can honestly claim when there are twelve defaults |
| 16 | Auto residual value | Fitted curve | A depreciation curve, and a feature that is a published index |
| 07 | Card-fraud neural network ✅ | **Declared black box** | What is left to hold to account when the mathematics is unreadable |
| 17 | AML transaction monitoring | Tree ensemble | An opaque ensemble, and weights carried as a parameter file |
| 18 | AML segmentation | Unsupervised | **No target at all** — a warrant for a model with nothing to predict |
| 19 | Vendor bureau score ✅ | Bought black box | What MAYA cannot verify, *marked* unverifiable rather than omitted |

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
| 11 | Nelson–Siegel yield curve ✅ | **Non-linear** calibration | Non-linear in one parameter: a search with least squares inside it, and a bug no measure of fit can see |
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
| 42 | Demand elasticity ✅ | **Log–log** | A logarithmic fit used in natural space |
| 43 | Okun's law | Simple linear regression | The simplest possible model, governed properly, as the floor case |

**Life sciences**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 44 | Cox proportional hazards | Survival | Censoring: rows whose outcome has not happened *yet* |
| 45 | Gompertz–Makeham mortality ✅ | **Exponential law** | A century of published parameters to argue with |
| 46 | Gene-expression classifier | Regularised, wide | More features than rows, and what a contract means then |
| 47 | Pharmacokinetics, two compartments | ODE solution | A sum of exponentials |
| 48 | SIR epidemic | Recursive | A model used for decisions before it can be validated |

**Operations**

| | Study | Model type | What it adds |
| --- | --- | --- | --- |
| 49 | LLM complaint triage ✅ | LLM | A prompt as a versioned parameter set, and a model MAYA never executes |
| 50 | Spreadsheet-lifted provision overlay | Lifted from Excel | MAYA judging the lift against the workbook's own results |

## What a case study is not

It is not a benchmark — `docs/BENCHMARKS.md` holds the measured throughput and capacity
figures. It is not a tutorial — the four in `maya/web/guides/tutorial-0*.md`, read in the
product under *Help → Guides*, walk a newcomer through the platform step by step. And it is not a test — the suite under `tests/` is what holds MAYA's
behaviour in place. A case study is the argument, made on a concrete problem, that the
governance is worth having.

---

The input data in every study is **synthetic**, generated by the `make_data.py` beside it
from a seeded recipe stated in that file's docstring. No real borrower, loan, patient or
counterparty appears anywhere in this folder.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
