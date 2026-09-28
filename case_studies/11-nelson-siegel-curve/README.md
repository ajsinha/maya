# Case study 11 — the Nelson–Siegel yield curve, and whether a curve is a feature or a model

**Domain:** fixed income, rates · **Model type:** closed form with a **non-linearly calibrated**
parameter · **What it exercises:** a curve registered from LaTeX with its two factor loadings
named as intermediates, a grid search over λ with ordinary least squares inside it, an
objective reported as a whole profile rather than as a minimum, an implementation bug that a
recalibration hides *exactly* and only a differential test can see, four parameter sets scored
blind in basis points against the same escrowed pillars, a joint constraint bounds cannot
express and accepts the violation of, and the same mathematics built a second time as a
**feature** so the governance gap can be counted rather than asserted.

## Why this study exists

Case study 5 calibrated a parameter nobody can observe, and every one of its nine volatilities
entered the formula linearly enough to be solved bucket by bucket. This one is a step further
in two directions at once.

> Nelson–Siegel is linear in three of its four parameters and non-linear in the fourth. So the
> calibration is a **search with a solve inside it** — and what the search finds is that the
> parameter it was searching for is barely identified: over the range of λ from 1.06 to 3.37,
> a factor of three, the fit changes by less than half a basis point.

And the object itself is the wrong shape for the platform:

> A MAYA parameter set is one vector of numbers. A curve is a vector of numbers **per day**.
> Everything uncomfortable in this study follows from that sentence, and §9 is the argument it
> forces.

## The scripts, and what each one does

Eight scripts, run in this order. They share the project's MAYA — the estate `config/application.yaml` configures, shared by every study, in which this study is the `rates` namespace —, which the
first builds and the rest reopen, so **each can be run on its own, in its own process** — and
between any two you can open the web UI and show what the last one created.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes the three feeds to `data/` (already committed; run it only to regenerate). No MAYA. | The recipe: a known Nelson–Siegel curve whose factors move slowly, a λ that never moves at all, observation noise six times larger at the front than at the back, and a per-pillar bias three factors cannot reach. It prints all of it. |
| `setup_features.py` | Declares and ingests the par quotes, the published zero curve and the curve team's build report as **dana**, approved by **mick**. | Three feeds, two grains, two lags — a 16:15 fixing and an 18:40 publication. **A feature designer refused permission to approve her own feed.** |
| `setup_featureset.py` | Composes `gbp_zero_curve` on `(date, tenor)`, broadcasts the daily build report onto every pillar, and pins it point-in-time. | A broadcast join stated in MAYA's own resolution plan; the model's notation meeting the curve team's column names; 10,962 rows pinned as of 2026-06-30. |
| `setup_model.py` | Registers Nelson–Siegel from **LaTeX** with both loadings as named intermediates, declares per-parameter **bounds**, prints the reference Python MAYA lifts from the tree, and tries to draw a warrant on the draft. | That a four-line LaTeX block is the whole model; that `\beta_{0}` and `\tau` parse; **the constraint that cannot be written down**; **a warrant refused on an unapproved version**. |
| `check_conformance.py` | Uploads the desk's implementation; the ladder and the differential test run together. Then the same code with the loading divided by τ instead of by τ/λ, tested at the desk's own smoke parameters, submitted, sent back by the reviewer, re-tested at MAYA's values and **refused**. | **A comparison that agrees 2,000 of 2,000 on broken code because it was run at λ = 1**, the parameter values now on the record beside the count, and the refusal once the values are MAYA's own. |
| `get_training_warrant.py` | Draws the warrant, asks the model for the columns of its own linear problem, searches λ on a 45-point grid with least squares inside, fits one curve for the window and one per day, **is refused an impossible parameter set and accepted an incoherent one**, registers four calibrations and has MAYA score each blind. | The nested calibration; the λ profile; 522 curves against one parameter set; **the bug a recalibration absorbs to 8×10⁻¹³ bp**; four blind scores in basis points. |
| `get_execution_warrant.py` | Draws an execution warrant with an input-range and an output-range covenant, second-manager approval, takes it live, and then the actuarial system asks for a fifty-year point. | A covenant about the *region of the request*; **the warrant suspending itself**; a parameter set the reviewer sent back **refused a licence**; reinstatement with a reason. |
| `curve_as_feature.py` | Builds the *same* curve as a derived **feature** — the four calibrated numbers inlined as literals in an expression — checks the two agree row by row, and reads back what MAYA holds about each object. | **The centre of the study.** The same mathematics and the same numbers on both sides of the fence, and the governance difference as a list. |
| `show_estate.py` | Creates nothing. Reads back the catalog, the artifact report with the domain *and the parameter values* its conformance was gathered at, four calibrations with their blind scores, the audit chain and the lineage. | That a reader who was not in the room can find out which curve was live, and why one calibration was sent back. |
| `study.py` | No MAYA calls: names, the three feed definitions, the LaTeX, both implementations, the specification, the calibration mathematics, the cast. | The declarations that would sit under source control on a rates desk. |
| `run.py` | All eight steps in order against a MAYA built from nothing. About ten seconds. | The unattended pass. |

```bash
.venv/bin/python case_studies/11-nelson-siegel-curve/run.py             # the whole story
.venv/bin/python case_studies/11-nelson-siegel-curve/setup_features.py --reset   # or step by step
```

---

## 1. The business problem

A sterling rates desk is quoted OIS swaps at twenty-one benchmark tenors. Everything it does
needs a rate at maturities nobody quotes: a cash flow on the 19th of November, a swap with
four years and one month to run, a pension liability at fifty years. So the curve between the
pillars comes from a model, and that model has to agree with the pillars that exist or the desk
is discounting itself off market.

Nelson and Siegel's (1987) three-factor form is the standard answer:

$$
y(\tau) = \beta_0 + \beta_1 \frac{1 - e^{-\tau/\lambda}}{\tau/\lambda}
       + \beta_2 \left( \frac{1 - e^{-\tau/\lambda}}{\tau/\lambda} - e^{-\tau/\lambda} \right)
$$

$\beta_0$ is the long rate — the limit as $\tau$ grows. $\beta_0 + \beta_1$ is the
instantaneous short rate — the limit as $\tau$ goes to zero. $\beta_2$ scales a hump that is
zero at both ends, and $\lambda$ decides where that hump sits: its maximum is at
$\tau \approx 1.79\lambda$. Level, slope, curvature, and where the curvature lives.

Three of those four are chosen by least squares. The fourth cannot be, and that is where the
study starts.

## 2. The data

| File | Rows | Size | Grain | Known | What it is |
| --- | --- | --- | --- | --- | --- |
| `data/ois_par_quotes.csv` | 10,962 | 0.71 MB | date × tenor | **16:15 that afternoon** | The closing par rate of the GBP OIS swap at each benchmark tenor, with bid and ask. |
| `data/zero_yields.csv` | 10,962 | 0.55 MB | date × tenor | 18:40 that evening | The continuously compounded zero rate the curve team publishes, bootstrapped from those quotes. **The calibration target.** |
| `data/zero_curve_build_report.csv` | 522 | 0.04 MB | date | 18:40 that evening | One row a day: how many instruments went into that build, the largest residual it left, and the method. |

522 business days, 2024-07-01 to 2026-06-30, 21 pillars from one month to thirty years, zero
yields from 1.3598% to 4.4612%. The curve is upward sloping throughout and steepens slowly:
on the last day it runs from 1.7510% at one month to 4.2245% at thirty years.

Underneath, `make_data.py` generates the pillars from a curve the model never sees:

```
beta0   an OU process around 4.30%, reverting at 0.03 a day, 4bp daily shock
beta1   drifting from -1.90% to -2.55%, plus OU noise
beta2   an OU process around -0.85%
lambda  1.30, on every one of the 522 days
noise   sd = 1.0bp + 6.0bp * exp(-tau / 0.8)      6.4bp at 1M, 2.7bp at 1Y, 1.0bp from 5Y
bias    a fixed per-pillar offset of a basis point or two, the same every day
```

Two of those five lines are the reason the study has anything to find. **The noise is larger
at the short end**, which is true of every real OIS curve — meeting dates, turn-of-year, thin
broking — and it means an unweighted least squares fit is pulled towards the noisiest pillars.
And **the bias is misspecification, not noise**: the two-year point sits 2.75 basis points
away from what a three-factor shape can produce, in the same direction every day, so a perfect
calibration still has a residual and the residual has a pattern.

**λ is constant.** That matters more than anything else in the recipe, because §6 estimates it
one day at a time and gets answers from 0.85 to 3.37.

### The third feed is the study's first exhibit

`zero_curve_build_report.csv` is the construction report of the bootstrap that produced the target: 21 to
24 instruments a day, a largest repricing residual of at most 0.46 basis points over the
window, one named method. That bootstrap has parameters, a method, an owner and an error. It
has no specification document, no conformance test, no parameter set and no approved version
anywhere in MAYA, because it arrived as a CSV. The only control the platform can put on it is
the quality check the feed definition declares:

```python
{"check": "range", "attr": "maxResidualBp", "min": 0.0, "max": 1.5}
```

A range check on a number the team reports about itself. Hold that thought until §9.

### One index, two grains

The feature set's index is the published curve's, `(date, tenor)`. The par quotes share it;
the build report is one row a day, so MAYA broadcasts it onto every pillar of that day and
says so:

```
join member           'maya://feature/rates/zero_yields@v1'    on ['date', 'tenor']
join member           'maya://feature/rates/ois_par_quotes@v1' on ['date', 'tenor']
broadcast join member 'maya://feature/rates/zero_curve_build_report@v1'    on ['date']
```

The pin is `maya://featureset/rates/gbp_zero_curve#ns2606/2026-06-30`, taken `as_of_known`
2026-07-01T07:00Z — seven the next morning, and it already contains everything, because a
curve is knowable the evening it is built.

## 3. The model, in the notation it was written in

```latex
z = \frac{\tau}{\lambda}
L_{slope} = \frac{1 - e^{-z}}{z}
L_{curve} = L_{slope} - e^{-z}
y = \beta_{0} + \beta_{1} L_{slope} + \beta_{2} L_{curve}
```

MAYA parses that into an expression tree with three intermediates and one output. The input
contract it derives is one column:

```
tau
```

and note what is not in it: `y`. The published zero yield is a member of the feature set and
the calibration target, not an input, so the curve cannot see the number it is fitted to. Nor
can it see `par` or `buildResidual`. That is a property of the contract, not a convention the
scripts follow.

Three things in that text are worth pausing on.

**The loadings are named.** `L_slope` and `L_curve` are intermediates rather than a single
inlined expression, and that is the difference between a specification a reviewer can read and
one he has to parse. It is also what makes §6 possible: the calibration asks the model for its
own loadings instead of writing them out again.

**`\tau` has to be declared.** MAYA reads LaTeX the way LaTeX means it, so an undeclared
`tau` is $t \cdot a \cdot u$ — three features nobody has. Declaring it in `roles` as a feature
is what makes it one symbol. Parameters are declared the same way and in the same notation:
`\beta_{0}`, `\beta_{1}`, `\beta_{2}`, `\lambda`.

**Four bounds, and the one that cannot be written.**

```python
BOUNDS = {
    "beta0": [0.0, 0.25],  # a long rate is not negative and it is not 25%
    "beta1": [-0.25, 0.25],  # a spread, either sign
    "beta2": [-0.5, 0.5],  # a curvature, which can be large
    "lambda": [0.25, 6.0],  # the hump between 0.45 and 10.7 years
}
```

MAYA enforces every one of those on every parameter upload for the life of the version. The
constraint beside them — that $\beta_0 + \beta_1$, the instantaneous short rate, is also not
negative — spans two parameters, so it is declared as a **joint constraint** rather than as a
bound. §7 uploads a set that satisfies all four rows of that table and implies a short rate of
minus 6.7%, and MAYA accepts it.

The version is left a draft, and nothing can be drawn on it:

```
NotApproved: rates/gbp_yield_curve_nelson_siegel@v1 is 'draft';
  warrants are drawn on approved model versions
```

## 4. MAYA's own reference implementation

Because the model is an expression tree, MAYA lifts it back into runnable Python:

```python
def predict(X, params):
    v_beta0 = params["beta0"]
    v_beta1 = params["beta1"]
    v_beta2 = params["beta2"]
    v_lambda = params["lambda"]
    v_tau = np.asarray(X["tau"], dtype=float)
    v_z = v_tau / v_lambda
    v_Lslope = (1.0 - np.exp((-v_z))) / v_z
    v_Lcurve = v_Lslope - np.exp((-v_z))
    return {"y": (v_beta0 + (v_beta1 * v_Lslope) + (v_beta2 * v_Lcurve))}
```

Nobody typed that twice. It is generated from the same tree the LaTeX produced, so it cannot
drift from the document, and the calibration in §6 fits with MAYA's evaluation of that same
tree rather than carrying a second Nelson–Siegel of its own.

## 5. A bug that no measure of fit can see

The desk's implementation is its own: vectorised numpy, its own variable names, written to
MAYA's model interface. Uploading it runs the six-rung ladder — parse and lint, entry point,
import allowlist, static ban, a smoke run in the sandbox at tier `strong` in 0.15 s, and a
determinism probe — and, with the ladder rather than when somebody remembers to ask, the
**differential test**: 2,000 sampled maturities compared against MAYA's own evaluation of the
documented mathematics to a relative tolerance of $10^{-9}$.

Now the bug. One expression:

```
slope_loading = (1.0 - decay) / maturity     where the desk's own correct line reads
slope_loading = (1.0 - decay) / scaled       with  scaled = maturity / decay_time
```

It is the commonest Nelson–Siegel error there is, and it has two properties that make it worth
a case study.

**It is exactly right at λ = 1.** The wrong loading is the right one divided by λ. So a smoke
test written at the round number — where the loading reads $(1 - e^{-\tau})/\tau$ and can be
checked against a hand calculation — passes on it. That is not a hypothetical: `upload_artifact`
takes the developer's own sample and parameters, and this study's desk ships
`lambda = 1.0` with its code.

| Differential test | Parameter values | Agreement |
| --- | --- | --- |
| Default domain, on upload | the desk's: λ = 1 | **2,000 of 2,000** |
| The pinned curve, 10,962 rows | the desk's: λ = 1 | **2,000 of 2,000** |
| The pinned curve, 10,962 rows | MAYA's, from the bounds: λ = 3.804 | **0 of 2,000** |

**On the passing evidence MAYA lets the version through**, and the submission succeeds. The
gate asks whether the last comparison against *this* artifact agreed everywhere it looked, and
it did — at one parameter value, chosen by the developer. It is the reviewer who sends it back,
and what she has to read is now on the record beside the count:

```
at the parameter values: beta0=0.043, beta1=-0.021, beta2=-0.009, lambda=1
```

That line is a fix this study made to the platform; §10 says what it replaced. Her reason goes
on the record too — *"the comparison was run at lambda=1, where a loading bug cancels; re-run
it at the values MAYA picks from the declared bounds"* — and the re-run refuses the submission:

```
NotApproved: Blocked by check(s): code_matches_specification —
  the code disagrees with the specification on 2000 of 2000 sampled inputs;
  e.g. tau=1 → specification 0.219425, code 0.104702
```

### And the second property, which is the interesting one

The wrong loading is the right one divided by λ, and the wrong curvature loading is
$L_{slope}/\lambda - e^{-z}$. Both are combinations of $\{1, L_{slope}, e^{-z}\}$ — **the same
three-dimensional space the correct model spans**. So least squares against the buggy code
lands on *exactly the same curve*:

| | Correct implementation | The desk's buggy one |
| --- | --- | --- |
| $\beta_0$ | +0.04303 | +0.04303 |
| $\beta_1$ | −0.02259 | **−0.03240** |
| $\beta_2$ | −0.00841 | −0.00841 |
| In-sample RMSE | 18.22 bp | 18.22 bp |
| Largest difference between the two fitted curves | | **8.3 × 10⁻¹³ bp** |

The algebra predicts it: $\beta_1' = \lambda(\beta_1 + \beta_2) - \beta_2 = -0.03240$, which is
the number least squares found. Every statistical check passes identically. The in-sample
residual, the out-of-sample residual, the backtest, the eyeball of the fitted curve against the
pillars — all identical to machine precision. **Nothing about the fit is worse.** What is wrong
is the number the desk then reports as the slope factor, which is λ times too large, and what
happens when somebody other than the desk's own code evaluates those coordinates. §7 measures
that: MAYA's blind score on the desk's coordinates is **53.96 bp** against **18.52 bp** for the
same fit reported in sample.

That is the strongest argument for spec–code conformance testing in this library. A bug that a
recalibration absorbs cannot be found by measuring how well the model fits. It can only be
found by comparing the code with the mathematics.

## 6. The calibration: a search with a solve inside it

A training warrant is drawn on the pin with `y` as the target. The certificate comes back
immediately:

```
leakage certificate:  certified
rows examined:        10,962
violations:           0
```

**It is clean about time, and time is not what is wrong here.** Every input and the target are
published the same evening, so the rule *"no row may use a value from its own future"* is
satisfied trivially. But the target is itself the output of a bootstrap, and a curve fitted to
it inherits every judgement in that build. Nothing bitemporal can see that, and §10 says what
I would add.

The warrant hands over **9,309 pillars** — 7,683 train, 1,626 validation — and escrows
**1,653**. The split hashes each `(date, tenor)` key, so the holdout is scattered through the
window rather than being its last few months; the thinnest day still keeps 7 training pillars,
which is more than enough to fit three factors to.

### The design matrix, asked of the model rather than written down

The curve is linear in the three factors, so evaluating the approved tree with one factor set
to 1 and the others to 0 *is* that factor's loading. The calibrator builds its design matrix
that way — three evaluations per λ — and checks the superposition rather than trusting it:

```
design matrix:          7,683 x 3 from MAYA's own evaluation
superposition holds to: 0
```

Exactly zero. So the curve the calibration fits is the curve MAYA's blind score will reprice
with, and the study contains no second implementation of Nelson–Siegel to be wrong in a
different way.

### The profile, which is the point

For each of 45 log-spaced λ across the declared bounds: evaluate the loadings, solve the three
factors **per day** by least squares — which is what the desk does every evening — and record
the residual.

| λ | 0.250 | 0.446 | 0.794 | 1.060 | **1.316** | 1.415 | 1.889 | 2.522 | 3.367 | 4.494 | 6.000 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RMSE (bp) | 18.015 | 10.511 | 4.416 | 2.771 | **2.519** | 2.555 | 2.722 | 2.668 | 2.974 | 4.260 | 6.184 |

The minimum is at **λ = 1.3165**, at 2.519 bp, which is within 1.3% of the 1.30 the data was
generated from. And then:

```
within 0.1 bp of the best:   lambda 1.139 to 1.521
within 0.5 bp of the best:   lambda 1.060 to 3.367
each day's own best lambda:  0.853 to 3.367, median 1.316
```

**The objective is sharp in the sense that matters to an optimiser and flat in the sense that
matters to a person.** Trebling λ from 1.06 to 3.37 costs less than half a basis point of fit
on 7,683 pillars. And the same grid, run one day at a time, puts the best λ anywhere between
0.853 and 3.367 — a factor of four — on data whose λ was 1.30 every single day. The wandering
is not the market moving. It is an unidentified parameter reading its own noise.

Three consequences, and they belong in the specification rather than in a footnote:

1. **λ is a convention, not a measurement.** Comparing this desk's λ with another desk's, or
   watching it move week to week, is reading noise as information. It is approved once and
   revisited annually.
2. **A λ only means something beside the factors it was fitted with.** §9 argues for a design
   in which the three factors arrive as a governed daily feed and λ lives in an approved
   parameter set. The moment those are two objects they have to agree, and nothing in MAYA
   relates a number in a parameter set to a number in a feed: if the curve team rebuilt its
   factors at λ = 1.30 while the model's approved λ stayed at 1.3165, the governed curve would
   quietly stop being the curve those factors describe and no check anywhere would fire.
3. **Reporting only the minimum would have been misleading**, which is why the study reports
   the profile, and why the *Calibration Methodology* section of the specification says
   "It is flat" in those words.

### One curve for the window, and 522 curves

| | Factors | In-sample RMSE |
| --- | --- | --- |
| One curve for the whole window | β0 +0.04303, β1 −0.02259, β2 −0.00841 | **18.22 bp** |
| Refitted each day, λ held | β0 from 3.85% to 4.62%, β1 from −2.70% to −1.75% | **2.52 bp** |

The window curve implies a long rate of 4.303% and an instantaneous rate of 2.044%, and it is
a real object: it is the average shape of the sterling curve over two years. It is also not
what anybody discounts with. The desk runs the second line, and the second line is **522
parameter sets**.

## 7. Four calibrations, one escrowed holdout

Before the holdout is touched, the alternatives are compared on the validation partition:

| On the 1,626 validation pillars | RMSE | Can it be a parameter set of this version? |
| --- | --- | --- |
| Nelson–Siegel, one window curve | 17.97 bp | **yes** |
| A flat curve at the mean yield | 75.91 bp | **yes** — the same model with β1 = β2 = 0 |
| Straight lines between that day's pillars | 6.72 bp | no: it needs the other rows of the same day |
| Nelson–Siegel refitted each day | 3.57 bp | no: it needs a parameter set per day |

The benchmark the study scores blind is the flat curve, and it is the right one *for the object
MAYA licenses*: both are date-blind, both are one vector of numbers, and the difference between
them is exactly what the curve's shape is worth to a single approved parameter set. Joining the
dots is a better benchmark for what a desk actually does, and MAYA cannot score it — a model
sees one row at a time, and interpolation is cross-sectional by nature.

### A calibration MAYA refuses, and one it should

```
ValidationFailed: Parameters out of bounds:
  'beta0'=-0.01 outside [0.0, 0.25]; 'lambda'=0.0 outside [0.25, 6.0]
```

Both named individually, before the set exists. Then the one that matters:

```
values:   beta0 = +0.031,  beta1 = -0.098,  beta2 = -0.0084,  lambda = 1.31648
its long rate:                     3.10%
its instantaneous short rate:      -6.70%
its yield at three weeks:          -6.63%

refused — registering a calibration whose short rate is negative
  ValidationFailed: Parameters out of bounds: constraint ≥ 0 is violated:
  beta0=0.031 + beta1=-0.098 gives -0.067 — beta0 + beta1 is the instantaneous short
  rate, which cannot be negative in a currency whose policy rate is not: a calibration
  that implies one has fitted the short end through noise, and every discount factor it
  produces at the front of the curve is wrong in the same direction
```

Every **bound** holds. $\beta_0 = 3.1\%$ is inside $[0, 0.25]$; $\beta_1 = -9.8\%$ is inside
$[-0.25, 0.25]$. Their sum is the instantaneous short rate and it is **−6.7%**, which is not a
curve, not a market and not a mistake anybody would defend.

When this study was first written MAYA accepted it, and said so: the condition spans two
parameters, a bound belongs to one, and the only things standing between that set and production
were a human approval and a blind score after the fact. **Writing the study is what put joint
constraints into the platform.** A model version may now declare conditions over several of its
own parameters — an expression, a comparison, and a reason that has to be written down, because
the reason is the only thing a modeller sees when it fires. The reason above is the model's own
words, quoted back at the person who would have shipped the curve.

### The blind scores

MAYA scores the escrowed 1,653 pillars itself, three times:

| Parameter set | What it is | RMSE | MAE |
| --- | --- | --- | --- |
| `ns-window-2606` | the calibrated curve | **18.52 bp** | 15.14 bp |
| `level-only-2606` | β1 = β2 = 0: a flat curve at the mean | **76.10 bp** | 67.90 bp |
| `desk-fit-2606` | the buggy implementation's coordinates | **53.96 bp** | 41.63 bp |

Three things follow. (A fourth set, `short-rate-negative`, is no longer among them: it is
refused at upload now, so there is nothing to score.)

**The shape is worth 4.11×.** The flat curve is four times worse on pillars neither calibration
was shown, which is what the *Validation Evidence* section claims and this is the number behind
it.

**The third row is the study's sharpest result.** The desk's own report said 18.22 bp in
sample, and it was telling the truth about its own code. MAYA's blind score on the same
coordinates is 53.96 bp, because MAYA evaluates the *specification*. The reviewer answers the
parameter set with that number, and the rationale is on the record:
*"blind holdout 54 bp against 19 bp for the same fit reported in sample: these coordinates
were produced by code that does not compute the specification."* The set moves to
`changes_requested`, and §8 shows it refused a licence.

**Every attempt is counted** — three parameter sets, three attempts, all on the warrant — so
scoring the holdout until it flatters you is visible.

### What that 18.52 bp is, and what it is not

It is the right number for the object MAYA licensed: one curve, scored on pillars drawn from
522 different days. It is not the accuracy of the model as the desk runs it, which is 3.57 bp,
and it is not comparable with a number from any firm that reports its per-day fit. A holdout
means "rows the fit did not see"; when the fitted object is a single curve and the rows span
two years, the number is dominated by the market having moved. The specification says so in
those words instead of quoting 18.52 bp as an accuracy.

### A parameter that multiplies nothing

`level-only-2606` sets β1 and β2 to zero, and then λ has nothing to scale:

```
flat curve at lambda 0.3 and 5.9:  identical: 0
```

Two parameter sets differing only in λ would be byte-different objects with different hashes,
different approvals and identical behaviour, and nothing in MAYA can tell. That is not a defect
to fix — identifiability is a property of the model and the data, not of the platform — but it
is the same fact §6 measured, in its purest form.

## 8. Live, with covenants about the region of the request

```python
covenants = [
    {"kind": "input_range", "attr": "tau", "min": 0.02, "max": 30.0},
    {"kind": "output_range", "min": -0.005, "max": 0.25},
]
```

The first is the one that suits a curve. Nelson–Siegel answers for any maturity at all — it
flattens smoothly towards β0 — so a fifty-year point comes back looking exactly as
authoritative as a ten-year point and is supported by nothing. The second is the backstop for
§7's joint constraint: a set whose $\beta_0 + \beta_1$ is negative produces negative yields at
the front, and while per-parameter bounds cannot refuse it, an output covenant notices the
consequence — **after** the parameters are live, which is the difference between a bound and a
covenant.

The output covenant names no attribute, and MAYA fills it in rather than accepting a control
that watches nothing: this version has one output, so it can only mean `y`.

The warrant is submitted by **mgr** and approved by **lara** — a second model manager, because
the person who submits is not the person who approves — sealed, with a 20 kB typeset PDF
manifest. Then the calibration the reviewer sent back is refused a licence of its own:

```
NotApproved: Blocked by check(s): parameters_approved — parameter set is changes_requested
```

And then the actuarial system asks for a fifty-year discount factor:

```
warrant: suspended
  'tau' max 50.0 above 30.0
what it would have answered: 30Y 4.167%, 50Y 4.222%

WarrantSuspended: Warrant suspended: 'tau' max 50.0 above 30.0.
  Contact rates.curve.quant@example.com.
```

4.222% is plausible, inside the output covenant, and evidence-free: the last pillar is thirty
years and everything beyond it is the functional form talking. An administrator reinstates with
a reason — *"the fifty-year request came from a pension valuation run in error; the curve team
will publish a 40Y and 50Y pillar before it is repeated"* — and the custody chain reads
`created, submit, approve, sealed, suspended, reinstated`.

What the estate holds when the eight steps finish:

| | |
| --- | --- |
| Features / feature sets / models | 4 / 1 / 1 |
| Parameter sets | 4: two approved, one sent back, one left in draft on purpose |
| Blind holdout attempts | 4, every one on the warrant |
| Audit chain | 94 entries on the unattended pass, hash-chained, verified unbroken |
| Custody on the training warrant | 13 events, from `created` to `sealed` |
| Lineage around the pinned curve | 20 nodes, 22 edges |

## 9. Is a curve a feature or a model?

This is the question the study exists for, and it is not rhetorical: MAYA lets you answer it
either way, and `curve_as_feature.py` answers it both ways on the same numbers.

MAYA's restricted expression language has arithmetic and `exp`, which is everything
Nelson–Siegel needs. So the curve that §3 to §8 governed as a model can also be a **derived
feature** over the published pillars, with the four calibrated numbers inlined as literals:

```
nsYield = 0.0430327493
        - 0.0225884866 * ((1 - exp(-(tau / 1.3164794))) / (tau / 1.3164794))
        - 0.00840561141 * (((1 - exp(-(tau / 1.3164794))) / (tau / 1.3164794))
                           - exp(-(tau / 1.3164794)))
```

dana defines it, mick approves it, and it resolves over all 10,962 rows. Compared with MAYA's
evaluation of the approved model at the approved parameter set:

```
rows compared:          10,962
largest disagreement:   4.64e-07 bp
feature at 10Y:         3.895871%
model at 10Y:           3.895871%
```

The same mathematics, the same four numbers, the same answers. (The disagreement is not quite
zero, and the reason is the whole argument in miniature: the feature carries the factors as
*text*, rounded to nine figures, while a parameter set holds them as numbers. Text has a
precision nobody declared.)

And here is what MAYA holds about each of the two objects — read back from the platform, not
composed for the README:

| | as a model | as a feature |
| --- | --- | --- |
| a specification document | 9 required sections, none empty | — |
| mathematics MAYA can read | an expression tree, IR `2bb046a4e508…` | an expression string |
| code tested against it | 2,000 of 2,000, on a named domain, at stated values | — |
| bounds on the numbers | 4 parameters bounded, enforced on every upload | — |
| the numbers as an object | 4 parameter sets, each separately approvable | 4 literals |
| a licence to compute | 1 training + 1 execution warrant | — |
| a blind score | 4 escrowed attempts | — |
| covenants | input_range, output_range | — |
| a version and an approval | v1 approved | v1 approved |
| a definition hash | `2bb046a4e508…` | `5b31ee680d18…` |
| a quality contract | — | 1 range check |
| a knowledge time | — | inherited from `zero_yields` |
| a place in lineage | yes | yes |

Then the last step moves the curve, as a curve moves every morning: β0 up 15 basis points.
MAYA mints v2, classifies the change as `behavioral`, and shows the approver the diff — the
whole source binding, before and after. Which is the right diff for a source and a poor one
for a number: the fifteen basis points that moved are one digit inside a two-hundred-character
string. The same move as a parameter set is four numbers, bounds-checked, tied to the
warrant's data checksum, blind-scored, and approved by a model manager.

### The position

**A fitted curve is a feature. Its shape is a model. MAYA supports both halves and cannot yet
join them, and that — not the choice — is the thing to fix.**

The argument for "feature" is not that a curve is unimportant. It is that a curve fails every
practical test of being a governable model object:

- **Its parameters change daily and a MAYA parameter set is one vector.** Two years is 522
  parameter sets, each formally needing a submit and an approve by a model manager. Nobody
  will do that, and what you get if you refuse to is the object this study licensed: a curve
  that scores 18.52 bp where the real one scores 3.57.
- **Everything downstream consumes it as a column.** Every pricing model in the bank needs
  today's discount factor. MAYA models cannot consume other models except as composite
  members (§8.7), so governing the curve as a model means every consumer embeds it as a
  pipeline member and carries a copy of its factors inside its own parameter set, namespaced
  by alias. One curve, forty composites, forty copies of the same four numbers to recalibrate.
  As a feature it is one column that forty feature sets read, with lineage that answers "who
  uses this curve" in one query.
- **Its knowledge time is the thing that most often goes wrong in production**, and knowledge
  time is a feature concept. A curve used at 09:00 that was built at 18:40 *yesterday* is the
  commonest real incident on a rates desk, and the feature subsystem was built for exactly
  that.

The argument for "model" is the one the table above makes, and it is not weak: a curve has a
specification, an owner, an error, a method with judgement in it, and consumers who will be
wrong if it is wrong. Everything in the right-hand column that reads "—" is a control a bank
would want on it. §2's third feed is the honest illustration: the bootstrap that produced this
study's target is, today, a CSV with a range check on its self-reported residual.

The resolution is not to pick a side; it is that the platform makes a false choice. What is
missing is a way for a model version's **parameters to be bound to a feature set attribute the
way its inputs already are**. §9.2 already says an execution warrant carries "feature or
feature set bindings for each input"; the same sentence for parameters would mean:

- one approved model version, with the LaTeX, the specification, the conformance test and the
  bounds — the shape, governed once;
- one approved parameter set holding λ, the number that genuinely does not move;
- β0, β1 and β2 bound to a governed daily factor feed, with a knowledge time, a quality
  contract, lineage, and per-row bounds checked at execution;
- and then MAYA's blind holdout score would measure the object the desk actually runs. On this
  study's validation pillars that object fits to **3.57 bp** against the licensed object's
  17.97, and a blind score of it is the number a model risk function should be asking for.

That is the specification change this study would make. §10 has the exact wording.

Two smaller things would help even without it. A feature should be able to declare that it is
**model-derived** and name the model version that produced it, so `zero_yields` is visibly the
output of something rather than an observation. And the leakage certificate should be able to
say *"this feature was fitted to this warrant's target"*, which is a circularity the bitemporal
rule cannot see and which is the real leakage in every factor-feed design.

## 10. What this study found that is not about curves

Four observations. Two are fixed in this branch, under one test; two are described and left
alone, with reasons.

**The differential test was run at parameter values that switched off the mathematics it was
testing — fixed.** `ModelService._default_params` placed every parameter at the *midpoint* of
its declared bounds. For a signed parameter that midpoint is exactly zero, and
zero times a loading is zero: for this model the platform's own comparison evaluated
$\beta_0 = 0.125$, $\beta_1 = 0$, $\beta_2 = 0$, λ = 3.125, which is the constant function
$y = \beta_0$. An implementation that computes both loadings wrongly agrees with the
specification on 2,000 of 2,000 rows, because nothing multiplies either loading. The fix is one
line — the default point is now 0.618 of the way through each bound rather than the middle,
which is inside every declared bound, is never zero unless the bounds force it, and is not a
round number a plausible bug could be exactly right at. The test that would fail without it is
`test_the_comparison_is_not_run_where_a_signed_parameter_is_zero`, in
`tests/test_conformance_gate.py`, and it asserts both halves: that the midpoints see nothing
wrong, and that the off-centre point sees it on every row.

**A conformance result did not record the parameter values it was run at — fixed.** §29.7 was
revised once already to put the *domain* on the result, because "an agreement over an invented
or narrow domain is worth less than it looks". Parameter values are the other axis of the same
problem, and this study is the case that shows it: 2,000 of 2,000 at λ = 1 and 0 of 2,000 at
λ = 3.804, on the same code and the same domain. The values are now in the result and in the
stored record, where the reviewer reads them. §5's request-for-changes is written from that
line.

**The conformance gate can be reopened by a comparison at chosen values, and I did not change
that.** In §5 the buggy version is refused, then passes a comparison at the developer's λ = 1,
and the submission is then allowed — because the gate reads the *last* recorded comparison. The
tempting fix is to make the gate insist on a run at MAYA's own values, or to keep the worst
result rather than the last. Both are policy changes to a check that other studies depend on,
and the platform's stated design is that the domain and now the values are reported *to a
person* because MAYA cannot judge representativeness (§29.7). So it is left as it is, and the
study shows a reviewer doing the job the design assigns her. If you do want a change here, the
smallest honest one is to record *every* comparison rather than only the latest, so a reviewer
can see that an earlier run on the same artifact disagreed.

**`check_bounds` silently skipped a parameter whose value was not a number** — now fixed.
`WarrantService.check_bounds` bound-checked a value only when it was an `int` or a `float`, so
`{"beta0": [9.0, -9.0]}` and `{"beta0": "9.0"}` both passed every bound on a model declaring
`beta0 ∈ [0, 0.25]`. The resolution was not to make bounds element-wise but to refuse the
mismatch: a declared scalar bound on a value that is not a scalar means one of the two is wrong,
and it is now reported as *"declares bounds [0.0, 0.25] but its value is list, so no bound could
be applied"*. A model whose parameter genuinely is an array — a black box's weight matrix, as in
case study 7 — declares no bound on it, and then nothing here applies.

### What I would change in the specification

Three wordings. I own none of these files; this is the text I would propose.

**§8.4, on parameters.** After *"Parameters are validated against the model's declared bounds
on upload"*, add:

> Bounds are per parameter. A constraint that spans two of them — that a level and a spread sum
> to something non-negative, that two mixture weights sum to one — cannot be expressed as a
> bound and is not checked. A model whose validity depends on such a constraint states it in
> the specification's *Assumptions* and relies on an output covenant to detect the consequence
> at run time, which is after the fact. Where a parameter's value is not a number — a weight
> matrix, a lookup table — no bound is applied, and the parameter set records that its bounds
> were not evaluated rather than implying they passed.

**§9.2, on execution warrants.** The contents list says *"feature or feature set bindings for
each input"*. I would extend it:

> A parameter may also be **bound to an attribute** of the bound feature set rather than held in
> the parameter set, in which case the parameter set holds only the parameters that are
> genuinely constant and the warrant records, per bound parameter, the attribute it reads and
> the bounds MAYA checks per row. This is what a curve is: a functional form and a decay
> constant that are approved once, and three factors that are re-derived every evening by
> machine. Without it, the only two available shapes for a daily-recalibrated model are a
> parameter set per day — which no approval process can absorb — or a single parameter set
> describing an average nobody trades on.

**§29.1, on the leakage certificate.** After the description of the bitemporal rule:

> The certificate is about time and about nothing else. It cannot see a feature that was
> *fitted* to the warrant's own target: a bootstrapped curve, a factor file, a smoothed index,
> any column produced by an estimation whose inputs included the thing the model is now being
> scored against. That is leakage in every sense a modeller cares about and in no sense the
> knowledge-time rule can detect, so a feature should be able to declare that it is
> model-derived and name the version that produced it, and a warrant whose feature set contains
> a model-derived attribute should say so on its certificate as an exception requiring a
> justification, exactly as a non-causal fill does.

## 11. What to point at when demonstrating this

1. **§6's λ profile** — an objective reported as a whole curve, flat over a factor of three,
   and a per-day estimate that wanders from 0.85 to 3.37 when the truth never moved. Then the
   sentence in the specification that says so.
2. **§5's table of three comparisons** — the same code, three answers, and the passing one is
   the test the desk actually wrote. Then the parameter values on the record, and the refusal.
3. **§5's second table** — a bug that a recalibration absorbs to 8×10⁻¹³ of a basis point, and
   the 54 bp blind score that is the only number in the file that noticed.
4. **§7's bounds refusal beside §7's acceptance** — a negative long rate named and refused; a
   −6.7% short rate, refused by a joint constraint the model declares for itself.
5. **§8's suspension** — a curve taken out of service for being asked about a maturity nobody
   quoted, with the answer it would have given printed beside it.
6. **§9's table** — the same mathematics and the same numbers, then thirteen rows: six controls
   the model carries and the feature cannot, two the feature carries and the model does not. It
   is the most useful five minutes in the library for anybody who thinks governance is
   paperwork.

## 12. What this study deliberately does not do

It fits one currency's zero curve. No Svensson fourth factor and second decay (that is a
separate version, and its second decay is even less identified than this one's first), no
weighted objective, no arbitrage-free constraint on the implied forwards, no bootstrap — the
published pillars are taken as given and the study says what that costs. It does not forecast
anything: every number here is an interpolation of a curve the market has already printed. And
it does not build the joint parameter constraint whose absence §7 demonstrates, on purpose:
demonstrating that a platform cannot express something is a different job from teaching it to.

Those limits are in the specification's *Scope and Limitations* and *Known Weaknesses*
sections, which is where a reviewer will look for them rather than in a README.

---

The input data is **synthetic**, generated by `make_data.py` from the seeded recipe in that
file's docstring. No real quote, curve, desk or counterparty appears anywhere in this folder.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
