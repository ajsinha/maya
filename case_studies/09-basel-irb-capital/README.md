# Case study 9 — Basel IRB regulatory capital

**Domain:** banking, regulatory capital · **Model type:** closed-form, prescribed by
regulation, **nothing to fit** · **What it is really about:** proving a formula you may not
change was implemented correctly, and what happens — findings, remediation, independent
closure, materiality, review, inventory — when it was not.

```bash
.venv/bin/python case_studies/09-basel-irb-capital/run.py      # about five seconds
```

Five scripts, run in this order. They share the project's MAYA — the estate
`config/application.yaml` configures, shared by every study — in which this study is the
`regulatory_capital` namespace, so each can be run on its own and the web UI shown between
them.

| Script | What it does | What it shows |
|---|---|---|
| `setup_data.py` | Defines the corporate exposures feed (PD, LGD, EAD, maturity, and the regulator's reference capital), loads four quarter-ends, approves it, and pins a year-end panel. | A benchmark carried beside the inputs as the target — never an input — and a pin named by its content hash. |
| `setup_model.py` | Registers the IRB formula as typed from the regulation, with its document, and approves version 1. | `N^{-1}(pd)` read as the normal quantile, not a reciprocal; a model with **no parameters**, because every constant is prescribed. |
| `reconcile_v1.py` | Draws a warrant whose target is the reference capital, has MAYA reconcile blind on the escrowed holdout, and looks at where the misses are on the rows the desk can see. The validator raises a **finding**. | Reconciliation as the evidence for a model with nothing to fit; a written leakage exception for a reporting calculation; a finding with an owner and a due date. |
| `remediate.py` | Version 2 floors and caps the maturity; MAYA's semantic diff shows that is the only change; a new warrant reconciles to the last digit; the owner is refused when she tries to close her own fix, and the validator closes it. | Remediation as a new version, and **independent closure**. |
| `govern.py` | Declares use and exposure and answers the firm's questionnaire; the validator records the first periodic review; the model is licensed to run and a run is reported; the inventory is exported in the SR 11-7 layout. | Tier 1, a yearly review, a live warrant, and the row a supervisor sees. |

## The mathematics

The foundation-IRB capital requirement for a corporate exposure, per unit of exposure at
default (Basel CRE31; CRR Article 153):

$$
R = 0.12\,\frac{1 - e^{-50\,PD}}{1 - e^{-50}} + 0.24\left(1 - \frac{1 - e^{-50\,PD}}{1 - e^{-50}}\right),
\qquad b = \left(0.11852 - 0.05478 \ln PD\right)^2
$$

$$
K = \left[ LGD \cdot N\!\left(\frac{N^{-1}(PD) + \sqrt{R}\,N^{-1}(0.999)}{\sqrt{1 - R}}\right) - PD \cdot LGD \right]
\cdot \frac{1 + (M - 2.5)\,b}{1 - 1.5\,b}
$$

It is the Vasicek single-factor model evaluated at the 99.9th percentile of the systematic
factor, less expected loss, scaled by a maturity adjustment. Two details matter for this
study. First, $N^{-1}$ is the inverse of the standard normal distribution — MAYA's formula
language has it as an operator (`ncdfinv`), and `N^{-1}(pd)` is parsed as that rather than
as $1/N(pd)$. Second, the regulation requires the effective maturity $M$ to be **floored at
one year and capped at five** (CRE31.46) before it enters the adjustment. Version 1 omits
that; version 2 has it:

```text
mat = (1 + (\max(1, \min(M, 5)) - 2.5) b) / (1 - 1.5 b)
```

There is nothing to calibrate. The evidence for a model like this is **reconciliation**:
the same inputs through an independent implementation — here, the regulator's reference
calculation, carried in the feed as `reference_k` — and the differences explained.

## What a run shows

From a run of `run.py` against an empty estate (the data is seeded, so these numbers are
the same every time):

| Step | Result |
|---|---|
| Rows ingested | 1,200 (300 obligors × 4 quarter-ends) |
| Pin `ye2025/2025-12-31` | 1,200 rows, sealed, hash `a63e29bc4f10a5a0…` |
| Leakage certificate | `certified_with_exceptions` — every value is known 25 days after its date, which is the point of a reporting calculation, and the warrant carries that justification in writing |
| Version 1, blind reconciliation | 173 holdout obligors; RMSE of K **0.00982**, MAE 0.00565 |
| Version 1, on the training rows | largest miss with maturity inside 1–5 years: **1.2e-16**; outside: **0.0449** of EAD |
| The finding | high severity, owner `mona`, due 90 days out |
| Version 2, semantic diff | one statement changed: `mat`, the floor and cap added |
| Version 2, blind reconciliation | RMSE of K **5.7e-17** |
| Closing the finding | `mona` refused (*whoever remediated a finding does not close it*); closed by `lara` |
| Materiality | 2.15 bn of exposure, regulatory use, questionnaire answered: **tier 1**, review every 365 days |
| Inventory, SR 11-7 layout | risk rating 1, approved, reviewed, no open findings, one live warrant, monitoring `ok` |

The size of the version 1 error is worth reading. Obligor by obligor it reaches 4.5% of
exposure at default; over the year-end book it overstates the capital requirement by
**6.5 million** (179.6m against the reference 173.1m), from 9.9m of gross obligor-level
error — long maturities overstated, short ones understated, netting partly away. That is a
bracket that is easy to leave out and invisible to anyone checking a handful of obligors
whose maturities happen to lie between one and five years. Reconciliation on every obligor, against an implementation the
modeller did not write, is what finds it.

## What to show in the UI

| After | Show |
|---|---|
| `setup_model.py` | Models → `basel_irb_corporate_capital`: the formula rendered from the parsed tree, $N^{-1}$ included |
| `reconcile_v1.py` | Warrants → `irb_reconcile_v1`: the leakage certificate with its written exception, and the blind score. Models → Findings & reviews: the open finding |
| `remediate.py` | The model's versions and the diff between them; the finding's history, with who remediated and who closed |
| `govern.py` | Models → Findings & reviews → `basel_irb_corporate_capital`: tier 1, its drivers and the questionnaire answers, the review. Export the inventory as Excel from the same page |

## The data

One feed, `data/corporate_exposures.csv`, written by `make_data.py` from a seed:

| Column | Meaning |
|---|---|
| `date`, `obligor` | The quarter-end and the obligor: the feature's index. Four quarter-ends of 2025 × 300 obligors = 1,200 rows |
| `pd` | One-year probability of default, log-uniform from the 3 bp regulatory floor to 20%, drifting a little each quarter |
| `lgd` | Loss given default, uniform 25%–60% |
| `ead` | Exposure at default, log-normal around 5 million |
| `maturity` | Effective maturity in years, 0.1 to 9 — a fifth under one year and a fifth over five, which is what makes the floor and cap matter |
| `reference_k` | The regulator's reference capital per unit of EAD, computed from exactly the values in the file |
| `kt` | When the quarter's figures were known: twenty-five days after the quarter-end |

## Who does what

| Person | Role | In this study |
|---|---|---|
| `dana` | feature designer | Defines and loads the exposures feed |
| `mick` | feature manager | Approves it and pins the year-end panel |
| `mona` | model designer | Writes both versions of the formula and its document; owns the model |
| `devi` | model developer | Draws the reconciliation warrants |
| `mgr` | model manager | Approves the model versions, the warrant and the execution licence |
| `lara` | second model manager | The independent validator: raises the finding, closes it, records the review, approves the licence |

## Running it

Everything runs from the project folder with the project's own interpreter, against the
project's MAYA (the estate `config/application.yaml` configures, shared by every study).
Nothing needs to be prepared first: the first script creates the users and the study's
namespace.

```bash
.venv/bin/python case_studies/09-basel-irb-capital/run.py            # the whole study
.venv/bin/python case_studies/09-basel-irb-capital/run.py --quiet    # results only, no narration
```

To demonstrate it, run the scripts one at a time in the order of the table above, and open
the web UI between them (`.venv/bin/python run_maya_web.py`, then <http://127.0.0.1:8600>,
signing in as any of the people below with the password `Maya-testing-pass-1`). A full pass
refuses to run twice in the same estate; pass `--reset` to remove this study's namespace and
run it again (a failed pass cleans up after itself), or run a study into a
throwaway estate with `--storage.root=/tmp/demo --lake.root=/tmp/demo/lake`.

## What MAYA refused, on purpose

- **The owner closing her own fix.** `mona` remediated the finding; closing it is refused —
  *whoever remediated a finding does not close it*. `lara` closes it.
- **Sealing on unexplained late data** would be refused by the leakage certificate: every row is
  known 25 days after its date. The warrant proceeds only because it carries a written exception
  saying why that is right for a reporting calculation.

## What this study does not show

The reference calculation is generated by the same arithmetic as version 2, so the
reconciliation proves that MAYA's evaluation of the formula matches an implementation of the
regulation, not that the regulation's inputs (PD, LGD, maturity) are right — those come from
other models and feeds, each with its own governance. The SME firm-size adjustment and the
other asset classes of CRE31 are out of scope, and the model document says so.

The data is synthetic (`make_data.py`); no obligor is real.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
