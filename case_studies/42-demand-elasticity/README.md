# Case study 42 — Demand elasticity: champion and challenger

**Domain:** economics, retail pricing · **Model type:** two fitted regressions, one linear
and one log–log · **What it is really about:** replacing a model on evidence. Not two error
figures side by side, which could differ by luck, but a paired comparison on exactly the
same unseen rows, with an interval, a verdict that means something, and a decision taken by
somebody who did not build the challenger.

```bash
.venv/bin/python case_studies/42-demand-elasticity/run.py      # about six seconds
```

Three scripts, in this order, sharing the project's MAYA (this study is the `pricing`
namespace).

| Script | What it does | What it shows |
|---|---|---|
| `setup.py` | Loads two years of weekly sales for forty products, pins the panel, and approves the champion and the challenger as mathematics. | Two models over the same features, both approved on their documents before anything is measured. |
| `fit_both.py` | Draws a warrant for each on the same pin with the same seed; each developer fits theirs on the training rows, ties the fit to its data, has it approved and scored blind. | **Equal holdout hashes**: the two warrants' escrowed rows are the same rows. |
| `challenge.py` | Tries a comparison against a warrant drawn with another seed, and is refused; runs the challenge; the challenger's developer is refused the decision; a second manager promotes. | A **paired bootstrap interval**, a verdict that needs the whole interval on one side, and an **independent** decision that is recorded, not enacted. |

## The two models

Both explain relative demand — the week's units as a multiple of the product's normal
weekly units — from relative price, the week's price as a multiple of its reference price.

| | Model | Form |
|---|---|---|
| Champion | `weekly_demand_linear` | $\text{demand} = a + b \cdot \text{price}$ |
| Challenger | `weekly_demand_constant_elasticity` | $\text{demand} = e^{\alpha}\,\text{price}^{\beta}$ |

The challenger is the constant-elasticity form economists use: a 1% change in price moves
demand by $\beta$%, whatever the price. It is fitted by least squares on the logarithms,
$\ln \text{demand} = \alpha + \beta \ln \text{price}$, and used in natural space. The linear
champion is the model many pricing teams start with; it is a tangent to a curve, so it is
right near the reference price and wrong at deep discounts and steep rises, where pricing
decisions matter most.

## The comparison

Each model's blind score is an RMSE on the holdout. Two RMSEs differing by a few hundredths
could be noise: some rows favour one model by chance. So MAYA — which alone holds the
per-row errors — compares them *row by row*:

- the difference in RMSE, challenger minus champion (negative favours the challenger);
- a **paired bootstrap** 95% interval for it: the holdout rows are resampled with
  replacement, 2,000 times with a fixed seed, and the difference recomputed on each sample,
  keeping each row's two errors together;
- the share of rows on which the challenger's error is the smaller.

The verdict is *challenger better* only if the whole interval lies below zero. None of this
is possible unless both models were scored on the same rows, which is why MAYA refuses a
challenge between warrants whose holdout hashes differ.

## What a run shows

From a run of `run.py` against an empty estate (seeded data, so the same every time):

| Step | Result |
|---|---|
| Rows ingested | 4,160 (40 products × 104 weeks) |
| Champion fit | $a = 3.172$, $b = -2.063$; blind RMSE **0.2250** on 657 rows |
| Challenger fit | $\alpha = -0.003$, $\beta = -1.623$ (the data's true elasticity is −1.6); blind RMSE **0.1940** on the same 657 rows |
| Holdout hashes | equal: `554057c8176844e9…` on both warrants |
| A warrant drawn with another seed | refused: *not drawn on the same escrowed holdout* |
| Difference | **−0.0310**, 95% interval **[−0.0401, −0.0215]** |
| Rows the challenger wins | 60% of 657 |
| Verdict | **challenger better** |
| The challenger's developer deciding | refused |
| Decision | promoted by `lara`, with the reason recorded |

The last two rows of the comparison are worth reading together. The challenger wins only
60% of rows — a coin-flip-and-a-bit, which on its own would not justify replacing anything —
yet the interval is well clear of zero, because where it wins it wins by more. Across the
full two years, where a developer may look, the mean absolute error at the deepest discount
(0.65 of reference) is 0.276 for the straight line against 0.235 for the power law, and at
the steepest rise (1.3) it is 0.170 against 0.079 — while at 1.15 the two are level. The
straight line strays furthest from the curve exactly at the prices where pricing decisions
are made, and that is the information two headline RMSEs hide.

## What to show in the UI

| After | Show |
|---|---|
| `fit_both.py` | Warrants: the two training warrants, their holdout hashes (identical), their blind scores |
| `challenge.py` | Models → Champion & challenger: the challenge with its interval and verdict, and the recorded decision |

## The data

One feed, `data/weekly_sales.csv`, written by `make_data.py` from a seed: 104 weeks × 40 fictional
products = 4,160 rows.

| Column | Meaning |
|---|---|
| `date`, `product` | The week and the product: the feature's index |
| `price_index` | The week's price as a multiple of the product's reference price: 1.0 most weeks, promotions at 0.8 and 0.65, list rises at 1.15 and 1.3 |
| `demand_index` | The week's units as a multiple of the product's normal weekly units, drawn from a constant-elasticity law with elasticity −1.6 and 15% noise |
| `kt` | When the week's sales were finalised: two days after it closed |

## Who does what

| Person | Role | In this study |
|---|---|---|
| `dana`, `mick` | feature designer and manager | Load, approve and pin the sales feed |
| `mona` | model designer | Writes both models and their documents |
| `devi` | model developer | Fits the champion under its warrant |
| `dev2` | second model developer | Fits the challenger, and raises the challenge |
| `mgr` | model manager | Approves both models, both parameter sets and both warrants |
| `lara` | second model manager | Takes the decision, because `dev2` owns the challenger |

## Running it

Everything runs from the project folder with the project's own interpreter, against the
project's MAYA (the estate `config/application.yaml` configures, shared by every study).
Nothing needs to be prepared first: the first script creates the users and the study's
namespace.

```bash
.venv/bin/python case_studies/42-demand-elasticity/run.py            # the whole study
.venv/bin/python case_studies/42-demand-elasticity/run.py --quiet    # results only, no narration
```

To demonstrate it, run the scripts one at a time in the order of the table above, and open
the web UI between them (`.venv/bin/python run_maya_web.py`, then <http://127.0.0.1:8600>,
signing in as any of the people below with the password `Maya-testing-pass-1`). A full pass
refuses to run twice in the same estate; pass `--reset` to remove this study's namespace and
run it again (a failed pass cleans up after itself), or run a study into a
throwaway estate with `--storage.root=/tmp/demo --lake.root=/tmp/demo/lake`.

## What MAYA refused, on purpose

- **A comparison on different rows.** A warrant drawn on the same pin with seed 7 instead of 42
  holds a different holdout, and the challenge is refused rather than computed.
- **The challenger's author deciding.** `dev2` is refused; `lara` records the decision.

## What this study does not show

Both models are fitted to relative indices pooled across the range, which is what makes one
elasticity meaningful; a real pricing model would add product and seasonal effects, competitor
prices and stock-outs, and the documents say so. The decision is recorded and not enacted: the
study stops before drawing the challenger's execution warrant and retiring the champion's,
which is a change of its own.

The data is synthetic (`make_data.py`); the products are fictional.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
