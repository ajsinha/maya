# Case study 19 — Vendor bureau score

**Domain:** banking, retail credit · **Model type:** a **bought black box**, delivered as
an MLflow model · **What it is really about:** holding to account a model you did not
build and cannot read — importing it with its declared contract, validating its code,
scoring it blind on your own outcomes, asking whether it treats regions alike and what it
leans on, and taking it out of service when its inputs stop resembling what it was built on.

```bash
.venv/bin/python case_studies/19-vendor-bureau-score/run.py      # about seven seconds
```

Four scripts, in this order, sharing the project's MAYA (this study is the `bureau`
namespace).

| Script | What it does | What it shows |
|---|---|---|
| `setup_data.py` | Loads the bureau attributes (known the evening they are pulled) and the outcomes (known a year later) as two features, and pins a year-end panel. | Two clocks kept apart, so the pin holds only applications whose outcome was **already known** when it was made. |
| `import_model.py` | Imports the vendor's MLflow model from its `MLmodel` file, uploads the scoring code through the six-rung validation ladder, and approves it with its document. | The input contract taken from the vendor's **signature**, MLflow provenance sealed into the version, and the code run twice in the **strong sandbox**. |
| `validate.py` | Draws a validation warrant on the bank's outcomes, scores the black box blind, computes performance by region and permutation importance, and seals. | **Blind scoring of a black box**: its code, in the sandbox, on rows nobody at the bank has seen — then fairness and drivers through the same path. |
| `monitor.py` | Licenses it with a population-stability covenant on utilisation and reports three months of live scoring. | The dashboard going **ok → watch → breach**, the warrant suspended on the third month, and the service refused. |

## The model

*BureauScore 4.1* estimates the probability an applicant defaults within twelve months from
four bureau attributes: revolving **utilisation**, recent **delinquencies**, **age of file**
and credit **inquiries** in the last six months. The vendor ships an MLflow model — an
`MLmodel` file whose signature names those four inputs and one output, `score`, and a
Python module with the scoring function. The bank never sees the vendor's development data
and treats the function as opaque, which is how such models are bought.

What MAYA can check about a model like this:

- **The contract.** The inputs are what the vendor's signature declares, not what somebody
  typed. The import refuses a model logged without a signature rather than guess.
- **The code.** The validation ladder parses it, checks its imports against an allowlist,
  searches it for file, network, process and dynamic-code use, and runs it twice in the
  sandbox (no network, no view of storage, capped resources) to see it is deterministic.
- **The performance, blind.** The holdout is escrowed on the warrant. MAYA runs the vendor's
  code in the sandbox on the holdout's four input columns — never the outcome — and computes
  the metrics itself. The validator sees numbers, not rows.
- **Fairness and drivers.** Error and bias by region, with small regions suppressed rather
  than disclosed; and permutation importance, which needs only predictions and so works on
  a black box exactly as on a formula.
- **Drift.** The population stability index of utilisation against the warrant's own data,
  on every reported run: under 0.10 stable, 0.10–0.25 worth watching, over 0.25 a covenant
  breach that suspends the warrant.

## What a run shows

From a run of `run.py` against an empty estate (seeded data, so the same every time):

| Step | Result |
|---|---|
| Features | 1,800 applications and 1,800 outcomes, approved |
| Pin `fy2025/2025-12-31` | **1,200 rows**: of 2025's applications, only those whose twelve-month outcome had arrived when the pin was made |
| Import | kind `black_box`; contract `utilisation, delinquencies, age_of_file, inquiries` from the signature; MLflow run `b3f1a2c4…` sealed as provenance |
| Validation ladder | all six rungs passed; smoke run under tier `strong`; deterministic |
| Leakage certificate | `certified_with_exceptions`: the target is known a year late by construction, and the warrant says so in writing |
| Blind score | 171 holdout applications; Brier score **0.0820**; `scored_in: sandbox`, tier `strong`, the artifact's hash recorded |
| By region | MAE 0.145 (west) to 0.196 (south): worst-to-best ratio **1.35**, no region flagged |
| Drivers | utilisation **43%**, delinquencies 27%, age of file 16%, inquiries 13% |
| January | mean utilisation 0.411, PSI **0.009**: live, dashboard **ok** |
| February | mean utilisation 0.451, PSI **0.109**: live, dashboard **watch** |
| March | mean utilisation 0.497, PSI **0.438**: covenant broken, warrant **suspended**, dashboard **breach**, the service refused |

The two halves of the story meet in March. Validation found that the score leans on
utilisation more than on anything else; monitoring watches exactly that input; and when a
cost-of-living squeeze pushes utilisation up by a fifth, the warrant stops the score being
used on a population it was not built for — before anyone has to notice a rising default
rate a year later.

## What to show in the UI

| After | Show |
|---|---|
| `import_model.py` | Models → `bureau_score`: *declared black box*, the contract, the artifact report with its six rungs, and (in the version's IR) the MLflow provenance |
| `validate.py` | Warrants → `bureau_validation`: the blind score marked *sandbox*, and the **Fairness & drivers** tab |
| `monitor.py` | Models → Monitoring: the warrant graded *breach*; open it for the PSI chart with the 0.10 and 0.25 lines and the breach marked on the time axis |

Everything is synthetic (`make_data.py`); no applicant is real, and *BureauScore* is not a
real product.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
