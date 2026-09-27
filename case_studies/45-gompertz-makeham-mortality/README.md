# Case study 45 — Gompertz–Makeham mortality

**Domain:** life sciences and actuarial work · **Model type:** a classical mortality law,
**non-linear** in two of its four parameters · **What it is really about:** fairness when
the law forbids the fair answer. A unisex table is required for pricing, so it is
necessarily wrong for men and for women in opposite directions. The job is not to remove
that error but to measure it, see that the usual summary hides it, and own it in writing.

```bash
.venv/bin/python case_studies/45-gompertz-makeham-mortality/run.py      # about six seconds
```

Three scripts, in this order, sharing the project's MAYA (this study is the `mortality`
namespace).

| Script | What it does | What it shows |
|---|---|---|
| `setup.py` | Loads ten years of deaths and exposures by age, sex and region, pins them, and approves the mortality law as mathematics. | Sex carried in the panel although the model may not read it: that is what lets a validator measure what leaving it out costs. |
| `calibrate.py` | Draws a calibration warrant, fits the law by a grid over its two non-linear parameters with least squares inside, ties the fit to its data, has it approved and scored blind. | Governance around a non-linear calibration, with parameters that each mean something. |
| `fairness.py` | Computes error and bias by sex and by region on the escrowed holdout, and what drives the table; raises a finding; the owner is refused when she tries to accept the risk; a manager accepts it with the legal reason in writing. | A **systematic** bias that the MAE ratio does not show; permutation importance; an **accepted risk** with its justification on record. |

## The law

Mortality rises roughly exponentially with age in adult life (Gompertz, 1825), on top of a
background risk that does not depend on age (Makeham, 1860). With mortality improving over
calendar time $t$:

$$
\mu(x, t) = \left(A + B\,e^{\gamma x}\right) e^{-\lambda t}
$$

$A$ is the age-independent hazard, $\gamma$ the Gompertz slope — mortality doubles every
$\ln 2 / \gamma$ years of age — and $\lambda$ the annual rate of improvement. For fixed
$\gamma$ and $\lambda$ the law is linear in $A$ and $B$, so the calibration is a grid over
$(\gamma, \lambda)$ with ordinary least squares for $(A, B)$ inside it.

**Why unisex.** Men die younger than women at every adult age, and a table by sex would fit
far better. But since the Court of Justice's *Test-Achats* ruling (C-236/09, 2011), insurers
in the EU may not charge men and women different premiums. The table must be unisex, and
each sex is priced from a rate that is wrong for it: men's understated, women's overstated,
a cross-subsidy by law.

## What a run shows

From a run of `run.py` against an empty estate (seeded data, so the same every time):

| Step | Result |
|---|---|
| Cells | 3,360 (10 years × 56 ages × 2 sexes × 3 regions); 2,339 in the training split |
| Calibration | $A = 0.000476$, $B = 2.54\times10^{-5}$, $\gamma = 0.1055$ (mortality doubles every 6.6 years of age), $\lambda = 0.0175$ (1.8% lower each year) |
| Blind score | RMSE of the death rate **0.04274** on 490 holdout cells |
| By sex | women: MAE 0.02590, bias **+0.02589**; men: MAE 0.02402, bias **−0.02399** |
| MAE ratio by sex | **1.08** — by error size, nothing stands out and nothing is flagged |
| Bias gap between the sexes | **0.0499**; both segments **systematic** |
| By region | MAE ratio 1.13, bias gap 0.012, nothing systematic |
| What drives it | age **99.7%**, calendar time 0.3% |
| Finding | raised by the validator; the owner refused when she tries to accept it; **accepted by `mgr`**, citing *Test-Achats* and stating that the cross-subsidy is reserved for |

The line to dwell on is the MAE ratio. Men's and women's errors are almost the same *size*,
so a fairness check that compares error sizes — the most common one — reports a model that
treats both sexes alike. It does not: for each sex the bias is nearly the whole of the error,
in opposite directions. That is why MAYA reports bias beside MAE and marks a segment
*systematic* when its bias is more than half its MAE. This study is what found the gap: the
first version of MAYA's fairness evidence flagged only on MAE, ran this study, and reported
nothing.

Calendar time's share of the importance is small because, over a decade of data, a
1.8%-a-year improvement moves rates far less than twenty years of age does; it matters for a
table projected forty years ahead, which is why it is in the law, not for scoring the
holdout.

## What to show in the UI

| After | Show |
|---|---|
| `calibrate.py` | Warrants → `mortality_calibration_2024`: the parameter set with its four values, and the blind score |
| `fairness.py` | The same warrant's **Fairness & drivers** tab: both sexes marked *systematic*. Models → Findings & reviews: the finding *accepted*, with the resolution in full |

## The data

One feed, `data/mortality_experience.csv`, written by `make_data.py` from a seed: 10 years × 56
ages × 2 sexes × 3 regions = 3,360 cells.

| Column | Meaning |
|---|---|
| `date`, `cell` | The year-end and the cell (`sex-region-age`): the feature's index |
| `age`, `t` | Age at last birthday, 40–95; years since 2015 |
| `sex`, `region` | Carried for the fairness evidence; the model reads neither |
| `exposure` | Central exposure in person-years |
| `deaths` | Deaths in the cell, drawn from a Poisson distribution at the Gompertz–Makeham rate × 1.30 for men or 0.78 for women × a few percent by region |
| `rate` | Deaths over exposure: the observed central death rate, the target |
| `kt` | When the year's experience was published: six months after it ended |

## Who does what

| Person | Role | In this study |
|---|---|---|
| `dana`, `mick` | feature designer and manager | Load, approve and pin the experience feed |
| `mona` | model designer | Writes the law and its document; owns the model |
| `devi` | model developer | Calibrates it under the warrant |
| `mgr` | model manager | Approves the model, the parameters and the warrant; accepts the risk |
| `lara` | second model manager | The validator: computes the fairness evidence and raises the finding |

## Running it

Everything runs from the project folder with the project's own interpreter, against the
project's MAYA (the estate `config/application.yaml` configures, shared by every study).
Nothing needs to be prepared first: the first script creates the users and the study's
namespace.

```bash
.venv/bin/python case_studies/45-gompertz-makeham-mortality/run.py            # the whole study
.venv/bin/python case_studies/45-gompertz-makeham-mortality/run.py --quiet    # results only, no narration
```

To demonstrate it, run the scripts one at a time in the order of the table above, and open
the web UI between them (`.venv/bin/python run_maya_web.py`, then <http://127.0.0.1:8600>,
signing in as any of the people below with the password `Maya-testing-pass-1`). A full pass
refuses to run twice in the same estate, because MAYA does not delete governed objects; pass
`--reset` to rebuild the whole demonstration estate from nothing, or run a study into a
throwaway estate with `--storage.root=/tmp/demo --lake.root=/tmp/demo/lake`.

## What MAYA refused, on purpose

- **The owner accepting the risk in her own model.** `mona` is refused; `mgr` accepts it, with
  the ruling cited in the resolution.

## What this study does not show

Mortality is fitted to death rates by unweighted least squares, which gives the oldest ages —
where rates are largest — the most weight; an actuary would fit by maximum likelihood on the
Poisson counts, weighting by exposure. The study makes the governance point either way, and
the document's *Calibration Methodology* states the choice. The improvement term is estimated
from ten years only.

Everything is synthetic (`make_data.py`); no person is real.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
