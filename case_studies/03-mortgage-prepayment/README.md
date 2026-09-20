# Case study 3 — a mortgage prepayment model, and a change proposed underneath it

**Domain:** banking, mortgage portfolio valuation and hedging · **Model type:** fitted
logistic hazard on a rare event · **What it exercises:** features on two different indexes
joined on the one they share, a fit compared against the process that generated the data, a
holdout figure quoted against something to beat, a population-shift covenant, and —
the reason this study exists — **a workspace, an impact analysis and a shadow replay**:
what MAYA does when somebody proposes changing a feature underneath a live model.

## The scripts, and what each one does

Eight scripts, in this order. They share one MAYA at `case_studies/runs/mortgage_prepay/`,
which the first builds and the rest reopen, so **each runs on its own, in its own process**.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes four feeds to `data/` (already committed; run it only to regenerate). No MAYA. | The recipe: a logistic hazard in rate incentive, seasoning, equity and the moving season, over a rate path that falls for a year and rises through the next. |
| `setup_features.py` | Declares and ingests four features: two on `(date, loan)`, two on **`date` alone**. | The market rate is one number a month and is stored as 30 rows, not copied into 37,873 of them. |
| `setup_featureset.py` | Composes `prepay_panel` from all four and pins it point-in-time. | MAYA broadcasting the date-indexed members across the loans of each month, and the proof: one distinct market rate per month in the pinned panel. |
| `setup_model.py` | Registers the hazard, refuses to submit it with an empty document, fills the nine sections, **declares what this model calls a material shift**, then gets it approved. | The two scalings declared *in the model*; the per-model materiality threshold that step 7 then uses. |
| `get_training_warrant.py` | Draws a warrant naively, then again with the forward-looking target explained. | The leakage certificate refusing all 37,873 rows, and the written exception. |
| `fit_parameters.py` | Fits by IRLS on the training partition, prints the coefficients **beside the ones that generated the book**, uploads twice (wrong checksum, then right), and has MAYA score the holdout blind. | What a fit on a 1.8%-a-month event can recover; a calibration number quoted against a base-rate model instead of alone. |
| `get_execution_warrant.py` | Takes it live with two PSI covenants and an output range, then reports a month whose rates sit outside the fitted distribution. | The covenant that matters for this model is about the *rate environment*, not the coefficients. PSI 12.5, suspended, reinstated with a reason. |
| `propose_change.py` | Opens a workspace, stages a smoothing change to the market-rate feature, lists what is downstream, and replays every affected warrant twice. | **The point of the study.** A defensible change, priced: 43.3% of rows move more than the model's own materiality threshold. |
| `show_estate.py` | Creates nothing. Reads the catalog, the approved coefficients against the generating ones, the lineage from the 30-row rate feature, the open proposal and the audit chain. | That one small feature reaches every forecast, and that the proposal is discoverable with its numbers attached. |
| `study.py` | No MAYA calls: names, definitions, the formula, the document, the proposed change, the fitting mathematics, the cast. | The declarations that would live under source control. |
| `run.py` | All eight steps against a MAYA built from nothing. About twenty seconds. | The unattended pass. |

```bash
.venv/bin/python case_studies/03-mortgage-prepayment/run.py            # the whole story
.venv/bin/python case_studies/03-mortgage-prepayment/setup_features.py --reset   # or step by step
```

---

## 1. The business problem

Case study 2 projected a mortgage pool's *scheduled* cash and said, in its scope section,
that prepayment was out of scope and needed a model of its own. This is that model.

A borrower paying 6.5% when the market offers 4.5% has two percentage points of reason to
refinance. Whether they act on it depends on how long they have held the loan, how much
equity they have to refinance into, and whether it is the season people move house. Get the
prepayment rate wrong and the pool's duration is wrong, the hedge is wrong, and the
valuation is wrong — which is why prepayment models are among the most heavily challenged
models a bank runs.

The quantity is the **single monthly mortality** (SMM), the probability a loan pays off in
full in a month, from which the annualised **constant prepayment rate** follows:

$$\mathrm{CPR} = 1 - (1 - \mathrm{SMM})^{12}$$

That conversion is a presentation of this model's output, computed by the caller, and the
specification says so — it is not a second model, and treating it as one is how a platform
ends up with two things to approve and one thing to trust.

## 2. The data, and two different indexes

| File | Rows | Index | Arrives | What it is |
| --- | --- | --- | --- | --- |
| `data/loan_month.csv` | 37,873 | `(date, loan)` | month end **+ 2 days** | Coupon, age, loan-to-value, balance. |
| `data/mortgage_rate.csv` | **30** | `(date)` | month end **+ 1 day** | The prevailing thirty-year survey rate. |
| `data/seasonality.csv` | **30** | `(date)` | a year ahead | Whether the month is in the moving season. |
| `data/prepaid.csv` | 37,873 | `(date, loan)` | month end **+ 31 days** | Whether the loan paid off in full. |

1,600 loans over thirty months, 2023-07 to 2025-12. The market rate runs from **6.87% down
to 4.54% and back up**, which matters more than it looks: a prepayment model fitted on a
flat rate path has an unidentified coefficient on incentive, and a fit will report one
anyway. The realised prepayment rate is **1.782% a month — a 19.4% CPR**.

### Why two of the four features have no loan dimension

The mortgage rate is not a property of any loan. It is one number a month for the whole
market. A platform that made you write it into every row would be asking you to store
37,873 copies of 30 numbers, and a copy can be wrong in one row and right in the next.

So those two features are indexed on `date` alone, and MAYA joins them onto the loan panel
on the index the two share. The step prints the proof:

```
distinct market rates within one month: 1
```

"The incentive" is therefore a well-defined quantity rather than a per-row value that can
drift. This also sets up step 7: because the rate lives in one place, a change to it is one
change — with 37,873 rows of consequences.

## 3. The model

```
inc = 100 * (wac - mktRate)
s   = min(age, 36) / 12
eq  = 1 - ltv
z   = a0 + aInc*inc + aAge*s + aEq*eq + aSum*movingSeason
smm = 1 / (1 + exp(-z))
```

With coupon $c$, market rate $r$, age $a$ months and loan-to-value $\ell$:

$$
I = 100(c - r), \quad S = \frac{\min(a, 36)}{12}, \quad E = 1 - \ell, \quad
\mathrm{SMM} = \frac{1}{1 + e^{-(\alpha_0 + \alpha_I I + \alpha_S S + \alpha_E E + \alpha_M M)}}
$$

**The two scalings are part of the model, not of the fitting script.** Incentive in
percentage points and seasoning in years, stated in the governed object, so that:

* a coefficient reads as "per percentage point of incentive" and "per year on book" —
  a reviewer can argue with 0.61 in a way they cannot argue with 0.0061;
* the design matrix is not a mixture of 0.02 and 180, which is what makes an unpenalised
  IRLS fit fall over (case study 1 hit exactly this with a 300–850 bureau score);
* the fitting script reads the scaling off the model instead of choosing its own, so the
  fit and MAYA's own evaluation of the formula cannot disagree.

The seasoning ramp is capped at thirty-six months because the data cannot distinguish a
ramp from a level beyond that. That is a modelling judgement, it is in the *Mathematical
Formulation* section, and it is the kind of thing that is invisible in code and obvious in
a document.

### The materiality threshold, declared on the model

`setup_model.py` declares `shadow_materiality = 0.001`:

> 0.001 of monthly hazard, which is about 1.2 percentage points of annualised CPR: the
> granularity at which the hedge ratio changes.

This is the thing only the model knows. Its output is a probability, and one basis point of
monthly hazard is noise; for a pricing model one basis point is not. Left to the platform
default, step 7's replay reports **98.3%** of rows as material and teaches the reviewer to
ignore the report. With the model's own figure it reports **43.3%**, and the report says
which threshold it used and where the number came from.

## 4. The fit, and what it recovers

Because the book is synthetic, the generating coefficients are known, and the study prints
the fit beside them. This is the clearest available statement of what a fit on this much
data can do:

| | fitted | generated |
| --- | --- | --- |
| `a0` (intercept) | −5.891 | −6.100 |
| `aInc` (per point of incentive) | **+0.608** | +0.620 |
| `aAge` (per year on book) | +0.278 | +0.340 |
| `aEq` (per unit of equity) | +1.526 | +1.450 |
| `aSum` (moving season) | +0.404 | +0.380 |

AUC **0.710** on training, **0.733** on validation — validation slightly above training,
which is what you get on a rare event where the split happens to put a few more easy cases
on one side. The incentive coefficient is recovered to within two per cent; the seasoning
ramp is the worst of the five, which is honest, because thirty months of data and a
thirty-six-month cap leave the ramp only partly observed.

**488 prepayment events in 26,450 training rows.** That is what "rare event" means here,
and it is why the *Calibration Methodology* section says the intercept carries most of the
base rate and the standard errors on the slopes are what a reviewer should ask about.

### The holdout figure, with something to compare it against

MAYA's blind scoring returns RMSE, which on a zero–one target is the root Brier score. A
number like that alone is meaningless, so the study computes the obvious benchmark:

| | root Brier |
| --- | --- |
| This model, on 5,697 escrowed rows | **0.1214** |
| Predicting the base rate for everybody | 0.1346 |

which is an **18.7% reduction in Brier score**. That is a modest, believable improvement,
and it is the right shape of claim: a calibration statement about rows the developer never
saw, kept separate from the AUC figures above, which are discrimination and were computed
on data the developer could see.

## 5. The covenant that actually matters

```python
covenants = [
    {"kind": "input_psi", "attr": "mktRate", "max": 0.25},
    {"kind": "input_psi", "attr": "wac", "max": 0.25},
    {"kind": "output_range", "min": 0.0, "max": 0.5},
]
```

A prepayment model does not usually fail because a coefficient was wrong. It fails because
the rate environment stopped resembling the one the coefficient was estimated in. `aInc` was
identified by one down-and-up cycle between 4.54% and 6.87%; a book sitting at 3.1% is
being extrapolated, not predicted, and the model has no way of saying so itself.

The PSI covenants are declared with no baseline, so MAYA takes the baseline from this
warrant's own training data and fixes it at creation. "Shifted" then means shifted away from
what the coefficients were fitted on, rather than away from last month.

Report a month whose rates sit entirely in the lowest baseline bin and:

```
WarrantSuspended: Warrant suspended: population stability index of 'mktRate' 12.526 > 0.25:
  the inputs this warrant sees are no longer the population it was fitted on.
  Contact mortgage.analytics@example.com.
```

It is reinstated with a reason that becomes part of the record — *"refinancing wave
confirmed; forecast accepted as a lower bound pending a refit on the 2026 window, and the
ALM committee has been told"*. That sentence is the governance. The model going back into
service is the easy part.

## 6. The step the other studies do not have

A model gets approved once. Its **features** get changed for years afterwards, usually by
somebody who has never met the model, and each change quietly moves every forecast
downstream of it. This is where model risk actually leaks.

Here the desk proposes something entirely reasonable: the published survey rate jumps a few
basis points a month on nothing, so smooth it with a three-month trailing mean.

```python
"transform": [
    {"op": "window", "attr": "mkt_rate", "fn": "mean", "size": 3, "name": "mkt_rate"}
]
```

The argument is sound in the abstract. Almost nobody, asked in a meeting, would object.

### Staged on a workspace

The change goes onto a **workspace** — a copy-on-write branch of the catalog. The definition
can be edited and resolved against without touching anything in production, and the step
ends by confirming that the approved feature is still `v1 approved`. Nothing has moved.

### What is downstream

MAYA walks the lineage and lists it: the pinned rate, the panel and its pin, both training
warrants, the parameter sets, and the execution warrant serving production.

### Replayed twice, and measured

Every affected warrant is resolved live twice — once against the current definitions, once
against the workspace's — and scored with its own model and parameters:

| | |
| --- | --- |
| Warrants replayed | 3 (one more could not be: *no parameter set to score with yet*) |
| Warrants whose output moved | 2 of 2 replayable |
| Median absolute shift in monthly hazard | **0.00087** |
| 95th percentile | 0.00314 |
| Worst row | **0.01116** — 2023-08-31, loan P01127 |
| Rows over the model's threshold | **2,163 of 5,000 (43.3%)**, against 0.001, *the model threshold* |
| Coverage | 10,000 of 75,746 matched rows (**13.2%**) |
| Compute budget | 2,000,000 row comparisons a day; this replay spent 10,000 |

Read the worst row: **1.1 points of monthly hazard**, which is over ten points of
annualised CPR on that loan. Smoothing the rate is defensible. Moving 43% of the book by
more than the desk's own materiality threshold, and one loan by ten points of CPR, is a
*decision* — and it is now a decision somebody makes with the number in front of them
rather than a sentence about noise reduction.

Three things about that report are worth pointing at:

* **It says what threshold it used and where the figure came from.** `(0.001, model)` — the
  model's own declaration, not the platform default. A report measured against the wrong one
  of the three reads as "nothing moved".
* **It states its coverage.** 13.2% of the matched rows, and the basis says the sample is
  the most recent rows of each index — *a recency bias, not a random draw*. It ends
  "sampled agreement is not proof". A platform that printed a percentage without that
  sentence would be inviting a conclusion the sample cannot support.
* **It charges compute to a budget.** Replaying is not free, and a replay that would blow
  the namespace's daily allowance is reported as unreplayed rather than silently skipped.

## 7. What to point at when demonstrating this

1. **§2** — the market rate is 30 rows, joined on the index it shares. One number, one place.
2. **§4, the fitted-against-generated table** — you can see exactly what the fit recovered
   and what it did not, and the specification already said which would be weak.
3. **§4, the two Brier scores** — a calibration number with a benchmark, and discrimination
   kept separate from it.
4. **§5** — the model takes itself out of service because its *inputs* moved, and the
   reinstatement reason is part of the record.
5. **§6** — the whole step. A reasonable change to one feature, priced in the units of the
   model it affects, before anybody approves it.

## 8. What this study deliberately does not do

It models **voluntary** prepayment. A loan leaving the pool through default and liquidation
is a different event and is out of scope. There is no burnout term, so a pool that has
already refinanced once will be over-predicted; no term structure and no servicer capacity
constraint, so it cannot represent the queue that is the real limit in a refinancing wave;
and the hazard is conditionally independent across loans, which makes a pool-level forecast
in a wave too confident. All four are in *Known Weaknesses*, where somebody reading the
model will find them.
