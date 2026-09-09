# Case study 3 — A non-linear model: exponential ramp, polynomial response

> **The demo in one sentence.** Mortgage prepayment is a curve in both of its
> drivers, and this shows the shape a bank actually reaches for — non-linear in
> the inputs, linear in the parameters — registered whole, fitted outside MAYA,
> and recovering coefficients we can check against the truth.

```bash
.venv/bin/python case_studies/03_prepayment_nonlinear/build.py
```

Runs in about fifteen seconds. See [`../README.md`](../README.md) for starting
the platform and creating users.

---

## 1. The theory

### What prepayment is, and how it is measured

A mortgage borrower may repay early — by moving, refinancing, or paying down.
For the holder of the loan this is an embedded short call on interest rates:
when rates fall, the borrower refinances and the holder loses exactly the asset
they wanted to keep. Prepayment risk is therefore the dominant risk in a
mortgage book after credit, and it drives everything from MSR valuation to
IRRBB to the hedging of a pass-through.

The conventional measure is the **conditional prepayment rate** (CPR), the
annualised fraction of the outstanding pool that prepays. It relates to the
**single monthly mortality** (SMM) by

    SMM = 1 - (1 - CPR)^(1/12)
    CPR = 1 - (1 - SMM)^12

CPR is a *hazard rate* conditional on survival, not a share of the original
balance — which is why a constant CPR still produces a declining absolute
runoff as the pool amortises.

### The two drivers, and their shapes

**Seasoning.** A newly originated pool barely prepays: nobody has moved yet,
and refinancing immediately after closing rarely pays for its own costs. As the
pool ages, prepayment rises and then flattens as the population reaches its
steady turnover rate. The market convention, the **PSA benchmark**, models this
as a linear ramp from 0.2% CPR to 6% over 30 months and constant thereafter.
A ramp with a kink is awkward to differentiate and awkward to fit, so a smooth
exponential approach to an asymptote is the usual practitioner substitute:

    seasoning(a) = 1 - exp(-a / tau)

with `tau` a time constant — 24 months here — reaching about 63% of full speed
at `a = tau` and 95% at `a = 3*tau`.

**Refinancing incentive.** The driver is how much lower the market rate is than
the rate the borrower pays, `i = WAC - market rate`, in percentage points. The
response is famously **S-shaped**:

- Near zero, little happens: refinancing has fixed costs, so a small saving
  does not repay them.
- Through 50-150 basis points the response steepens sharply as the saving
  clears those costs for most of the pool.
- Far in the money it **saturates**: everyone who can refinance already has.
  What is left is the population who cannot — impaired credit, insufficient
  equity, or simple inertia. This is **burnout**, and it is why a pool that has
  already been through a refinancing wave prepays more slowly than a fresh pool
  at the same incentive.

A cubic in `i` captures the first two regions and the beginning of the third.
It is a local approximation to a sigmoid, and it is not one: extrapolated far
enough the cubic turns over and predicts *falling* prepayment at very high
incentive, which is wrong. Within the fitted range it is a good and very
tractable description; outside it, it is not, which is the standard caveat on
any polynomial basis.

### Non-linear in the inputs, linear in the parameters

The model is

    CPR = b0 + b_s*(1 - exp(-a/tau)) + b1*i + b2*i^2 + b3*i^3

This is **non-linear in `a` and `i`** and **linear in `b`**. That distinction is
the point of the case study and it has real consequences:

- The design matrix `X = [1, 1-exp(-a/tau), i, i^2, i^3]` is a fixed **basis
  expansion** of the inputs, and once formed the problem is ordinary least
  squares. There is no optimiser, no starting values, no convergence criterion
  and no random seed.
- The estimator is therefore **deterministic and reproducible**, which is what
  makes independent recomputation by a validator possible at all.
- Every coefficient keeps a standard error and an interpretation.

The price is that `tau` is **not estimated** — it is fixed at 24 months and put
in the registered expression. Estimating it too would make the model genuinely
non-linear in the parameters and require iterative optimisation. That is a
defensible design choice, and it is a choice: `tau` is a modelling assumption
sitting inside the model definition, where a reviewer can see it and change it
deliberately.

### What a fuller model would carry

Named because the case study does not: burnout as an explicit state variable
(cumulative incentive experienced), seasonality (spring moving season), loan
size and credit as heterogeneity, the media effect, and a term structure of
rates rather than a scalar incentive. Industry models are dozens of parameters
and often a Monte Carlo over rate paths.

### References

- Richard, S. and Roll, R. (1989). *Prepayments on Fixed-Rate
  Mortgage-Backed Securities.* Journal of Portfolio Management 15(3).
- Schwartz, E. and Torous, W. (1989). *Prepayment and the Valuation of
  Mortgage-Backed Securities.* Journal of Finance 44(2).
- PSA/SIFMA standard prepayment model.

---

## 2. The model

The **conditional prepayment rate** of a mortgage pool: the annualised rate at
which borrowers pay off early. Two drivers, each with a shape:

**Seasoning.** A freshly originated pool barely prepays. As loans age, prepayment
climbs and then flattens — people move, refinance, trade up. That is an
exponential approach to a ceiling, not a straight line.

**Refinancing incentive.** How much lower the market rate is than what the pool
is paying. Near zero, little happens. As it goes positive, prepayment
accelerates. Far in the money, it saturates — everyone who *can* refinance
already has. That S-shape is captured here by a cubic.

```
CPR = b₀
    + b_season · (1 − e^(−a/24))              ← exponential seasoning ramp
    + b₁·i + b₂·i² + b₃·i³                     ← cubic in refinancing incentive
```

where `a` is age in months and `i` is incentive in percentage points.

---

## 3. The idea worth the whole demo

**Non-linear in the inputs. Linear in the parameters.**

The model's *response* to age and to incentive is a curve. The thing being
*estimated* is still a coefficient vector. So:

- ordinary least squares fits it — no optimiser, no convergence to worry about,
  no random seed;
- every coefficient keeps an interpretation and a standard error;
- the fit is **deterministic**, which means it is reproducible, which means a
  validator can recompute it.

This is the honest middle ground, and banks live in it: seasoning ramps,
S-curves, recovery decay, deposit runoff, loss emergence. A straight line cannot
describe prepayment. A gradient-boosted machine describes it and cannot be
explained to a supervisor. This shape does both.

| | Straight line | **This** | Boosted trees |
|---|---|---|---|
| Describes the behaviour | ✗ | ✓ | ✓ |
| Coefficients interpretable | ✓ | ✓ | ✗ |
| Deterministic fit | ✓ | ✓ | ✗ (seed, ordering) |
| Explainable to a supervisor | ✓ | ✓ | with effort, and by proxy |
| MAYA class | T2 | **T2** | T3 |

---

## 4. Where the curve lives, and why it matters

The non-linearity is **inside the registered expression**, not in a feature
pipeline beside it.

That is a deliberate choice with a governance consequence. The common
alternative is to compute `seasoning` and `incentive_squared` in a data pipeline
and register a model whose kernel reads `b0 + b1*x1 + b2*x2`. It is a linear
model on paper, a non-linear one in reality, and **the curve — the part a
supervisor asks about — lives somewhere nobody governs**.

Here, `GET /api/v1/mathematics` returns the exponential and the cubic, because
the register holds them:

```bash
curl -s -u admin:maya-admin-dev \
  "http://127.0.0.1:5006/api/v1/mathematics?urn=maya://model/alm.prepayment.cpr&semver=1.0.0"
```

The script *also* registers `seasoning` and `incentive_sq` as **derived
features**, so the two shapes have names and lineage in the catalogue:

```python
maya.features.derive(name="seasoning",
                     expression="1.0 - exp(-age_months / 24.0)")
```

Ask MAYA where `seasoning` comes from and you get an expression, not a
paragraph:

```bash
curl -s -u admin:maya-admin-dev \
  http://127.0.0.1:5006/api/v1/derived-features/seasoning/lineage
```

---

## 5. The data

**Synthetic, from a data-generating process stated in the script.** There is no
freely redistributable loan-level prepayment panel — servicer tapes are
licensed. Rather than pretend otherwise, `build.py` writes down the truth:

```python
TRUE = {"b0": 5.5, "b_season": 21.0,
        "b_inc1": 7.5, "b_inc2": 2.4, "b_inc3": -1.1}
NOISE_CPR = 1.6
```

60 pools × 24 monthly observations = **1,440 pool-months**. Noise is
deterministic — a SHA-256 digest of the row's own identity, not a seeded RNG —
so the numbers are identical on every machine and every Python version. A case
study whose output moves between laptops is one nobody can check against its
README.

**This buys something a real panel cannot give you:** the fit can be compared
against the answer. See §7.

### Both clocks, and this time neither is invented

Unlike case study 2, the second clock here is a real fact about the process:

| Clock | Value | Meaning |
|---|---|---|
| `event_ts` | month end | the prepayment was true for that month |
| `ingest_ts` | + 21 days | the servicer reported it partway through the next |

That reporting lag is exactly why a model fitted "as of" a date must not see
the month that had not been reported yet.

---

## 6. What the script does

| Step | What happens | Who does it |
|---|---|---|
| 1 | Build the 1,440-row panel | script |
| 2 | Create the four people | MAYA |
| 3 | Register three features + **two derived features** | MAYA |
| 4 | Load the panel, both clocks | MAYA |
| 5 | Declare the featureset (`cpr` as label, 30-day outcome window) | MAYA |
| 6 | Register the model; class and tier derived | MAYA |
| 7 | Approve the version — quorum | s.iqbal + v.chen |
| 8 | Put the record in force | MAYA |
| 9 | Grant standing entitlements | MAYA |
| 10 | **Show a refusal**: wrong featureset for this kernel (**L-W10**) | MAYA |
| 11 | **Training warrant** | MAYA |
| 12 | **Fit by QR on the non-linear basis** | **script** |
| 13 | Deliver coefficients with standard errors — **proposed** | MAYA |
| 14 | s.iqbal accepts them | MAYA |
| 15 | Ask for the mathematics | MAYA |
| 16 | **Execution warrant** | MAYA |
| 17 | **Project the curve locally** across ages and incentives | **script** |
| 18 | Write the LaTeX specification | script |

---

## 7. The fit recovers the truth

The design matrix is where the non-linearity sits — column 1 is the exponential
ramp, columns 2–4 are powers of the incentive — and the solve is plain least
squares:

```
X = [1, 1−exp(−a/24), i, i², i³]
```

```
n=1,440   R²=0.9872   residual SE 0.931 CPR

parameter      estimate   std err       t    truth
b0               5.4390    0.0925    58.8     5.50
b_season        21.0499    0.1497   140.6    21.00
b_inc1           7.4716    0.0426   175.5     7.50
b_inc2           2.4394    0.0444    54.9     2.40
b_inc3          -1.1072    0.0208   -53.4    -1.10
```

**All five coefficients are recovered within one standard error of the value
that generated the data.** (Not within one per cent — two of them miss that, and
the standard error is the right yardstick anyway: it is the estimator's own
statement of how precisely it could have known.)

The residual standard error is worth a moment, because the obvious reading of
it is wrong. `NOISE_CPR = 1.6` is a *scale*, not a standard deviation: the
jitter is uniform on `[-1, 1]`, so the noise actually has standard deviation
`1.6/√3 ≈ 0.924`. The fit reports **0.931**. The estimator is recovering the
noise it was given, and the arithmetic is the check —
which is the kind of thing worth doing out loud, because "the residual matches
the noise" is a sentence people nod at without verifying.

**Standard errors are delivered with the parameters**, not left out. They are
what tells a reviewer that the cubic term is real here (t = −53) rather than
curve-fitting — and on a real panel that is exactly the term that often is not,
which is why it must be visible at the moment of approval rather than
discoverable afterwards.

Then the script projects the curve locally under the execution warrant:

```
  age  incentive    CPR %    truth
    3      -0.50    4.925    4.955     <- new pool, out of the money: barely prepays
   24       0.50   22.952   22.987
  120       1.50   39.306   39.296     <- fully seasoned, in the money
```

Worst deviation from the generating curve across 15 points: **0.060 CPR**.

---

## 8. The refusal this one shows: L-W10

The script asks for a training warrant against case study 1's featureset:

```
[schema_not_satisfied] 'bs_calibration_set' does not provide age_months,
rate_incentive, which this version declares it reads
→ bind a featureset whose schema covers the kernel's inputs, or create a model
  version whose input schema matches this set — adding a regressor is a model
  change, not a data change
```

**L-W10** is the law that a featureset must supply everything the kernel reads.
The remediation is the sentence to read aloud: *adding a regressor is a model
change, not a data change*. It is the difference between a platform that tracks
models and one that can tell you when a model became a different model.

---

## 9. Things to try live

**Drop the cubic.** Remove `b_inc3` from the expression and the parameter
schema, register `1.1.0`. The fit still works; the residual grows; the model is
now a different model with its own approval. Nothing is silently swapped.

**Change the time constant.** `SEASONING_MONTHS = 24.0` is *in the registered
expression*. Change it to 36 and you have changed the model — which is correct,
and is the point of putting it there rather than in a pipeline.

**Ask what depends on this model:**

```bash
curl -s -u admin:maya-admin-dev \
  http://127.0.0.1:5006/api/v1/models/alm.prepayment.cpr/blast-radius
```

**Look at it in the browser.** `http://127.0.0.1:5006/models` → the prepayment
model → its version, kernel, parameter sets and warrants.

---

## 10. Questions this case study answers well

**"Our models aren't linear."**
Neither is this one. Non-linear in the inputs is the normal case, and it does
not require giving up interpretability or determinism.

**"Where does feature engineering live?"**
If the transformation is part of the model, put it in the model — then the
register holds it and a supervisor can be shown it. MAYA supports both, and
this case study takes a position on which is better.

**"How do we know the estimator is right?"**
Here you can check: the panel is synthetic and the truth is printed beside every
estimate. On a real panel you cannot, which is why the standard errors and the
condition number travel with the parameters.

**"Does MAYA fit this?"**
No. `numpy.linalg.lstsq`, in `build.py`, in your process. MAYA issued the
warrant and recorded the result.

---

## 11. Files this produces

| File | What it is |
|---|---|
| `warrant-training.json` | The training warrant |
| `warrant-execution.json` | The execution warrant, naming the approved set |
| `prepayment-specification.tex` | Specification; equation derived by MAYA |

```bash
pdflatex prepayment-specification.tex        # 2 pages
```
