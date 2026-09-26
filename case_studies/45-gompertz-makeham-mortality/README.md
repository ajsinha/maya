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

Everything is synthetic (`make_data.py`); no person is real.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
