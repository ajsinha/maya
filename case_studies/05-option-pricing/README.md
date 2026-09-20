# Case study 5 — a European option pricer, and the volatility nobody can observe

**Domain:** finance, equity derivatives · **Model type:** closed-form mathematics with a
**calibrated** parameter · **What it exercises:** a model registered from LaTeX with `ncdf`
and `where` in it, four feeds on three grains broadcast onto one chain, a feature set as set
algebra, parameter bounds MAYA enforces, two calibrations of one model version scored blind
against the same escrowed quotes, a differential test that catches a maturity bug a unit
test would not, and a covenant about the region the surface was calibrated in.

## Why this study exists

Case study 1 **fitted** a scorecard to outcomes and asked whether the fit was sound. Case
study 2 had **nothing to fit** and asked whether the code was the mathematics. This one sits
between them, and the gap is the point:

> Black–Scholes has one free parameter, and it is not observable, not fitted to outcomes, and
> not contractual. It is **calibrated** — chosen so the model reproduces prices the market has
> already published. So the "training data" is a set of answers, and the model's job
> afterwards is to interpolate between them.

Everything awkward about governing a pricing model follows from that sentence. The leakage
certificate has nothing to complain about and therefore proves nothing. The escrowed holdout
measures interpolation rather than prediction. The parameter is a restatement of today's
market in the model's own units, so "is it accurate?" is the wrong question and "where is it
allowed to be used?" is the right one. This study is MAYA's machinery pointed at that
problem, and it says out loud which of its own evidence is worth little.

## The scripts, and what each one does

Seven scripts, run in this order. They share one MAYA at
`case_studies/runs/equity_derivatives/`, which the first builds and the rest reopen, so
**each can be run on its own, in its own process** — and between any two you can open the web
UI and show what the last one created.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes the four feeds to `data/` (already committed; run it only to regenerate). No MAYA. | The recipe: a known volatility surface with a skew and a smile, priced through Black–Scholes–Merton and disturbed by quote noise. It prints the surface it generated, which is what calibration is trying to recover. |
| `setup_features.py` | Declares and ingests the option chain, the spot, the dividend forecast and the discount curve as **dana**, approved by **mick**. | Four feeds, three grains, four knowledge times — a closing quote at 21:10 the same evening, a forecast published at 07:00 that morning. |
| `setup_featureset.py` | Composes `acme_chain` on `(date, underlying, tenor, contract)`, pins it, then derives the 1Y pillar as **set algebra** over the same definition. | Three broadcast joins across three grains, stated in MAYA's own resolution plan; the model's notation meeting the vendors' column names; a derived set that cannot drift from its parent. |
| `setup_model.py` | Registers Black–Scholes–Merton from **LaTeX**, declares **bounds** on the nine volatilities, fills the specification, prints the reference Python MAYA lifts from the tree, and tries to draw a warrant on the draft. | That `ncdf`, `where` and comparisons make the whole pricer one formula model; that a bound is a property of the tree; **a warrant refused on an unapproved version**. |
| `check_conformance.py` | Uploads the desk's pricer; the ladder and the differential test run together. Then the same pricer with `sigma*T` for `sigma*sqrt(T)`, tested on the 1Y pillar, submitted, sent back by the reviewer, re-tested on the whole chain and **refused**. | **The heart of the study.** A maturity bug that is exactly right at one year, a test domain that hides it, and the refusal once the domain is honest. |
| `get_training_warrant.py` | Draws the warrant, calibrates one volatility and then nine, **is refused a negative one**, registers both against the same warrant, and has MAYA score each blind. | Calibration as distinct from fitting; the smile, measured; the bias a single volatility leaves bucket by bucket; two blind scores on the same escrowed quotes. |
| `get_execution_warrant.py` | Draws an execution warrant with an input-range and a PSI covenant, second-manager approval, takes it live, then reports a batch asking for two-year options. | A covenant about the *region* a calibration is valid in; **the warrant suspending itself**; reinstatement with a reason. |
| `show_estate.py` | Creates nothing. Reads back the catalog, the artifact report with the domain its conformance was gathered on, both calibrations and their holdout scores, the audit chain and the lineage. | That a reader who was not in the room can find out which volatility was live and how badly the alternative scored. |
| `study.py` | No MAYA calls: names, definitions, the LaTeX, both implementations, the specification, the calibration mathematics, the cast. | The declarations that would live under source control on a desk. |
| `run.py` | All seven steps in order against a MAYA built from nothing. About ten seconds. | The unattended pass. |

```bash
.venv/bin/python case_studies/05-option-pricing/run.py            # the whole story
.venv/bin/python case_studies/05-option-pricing/setup_features.py --reset   # or step by step
```

---

## 1. The business problem

An equity derivatives desk quotes and books European calls. Every evening it must mark the
book: for each open contract, a price. Most of the book is not quoted — the strike or the
maturity the desk holds is between the listed ones — so the mark comes from a model, and the
model must agree with the quotes that *do* exist or the desk is marking itself off market.

Black–Scholes–Merton gives a closed form for that price:

$$
C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)
$$

Spot, strike, rate, dividend yield and time to expiry are observed. Volatility is not. It is
the one thing in the formula that has no market of its own, and the desk chooses it so that
the formula reproduces the prices that are quoted. That is calibration, and it is neither of
the two things the earlier studies did.

## 2. The data

| File | Rows | Size | Grain | Known | What it is |
| --- | --- | --- | --- | --- | --- |
| `data/option_quotes.csv` | 11,791 | 0.97 MB | date × underlying × tenor × contract | **21:10 that evening** | The closing mid of every listed call, on four tenors and a fixed strike ladder. |
| `data/underlying_spot.csv` | 261 | 0.01 MB | date × underlying | 20:45 that evening | The official close of each underlying. |
| `data/dividend_forecast.csv` | 261 | 0.01 MB | date × underlying | 07:00 **that morning** | The research desk's continuous dividend yield, revised monthly. |
| `data/discount_curve.csv` | 348 | 0.02 MB | date × tenor | 18:30 that evening | The continuously compounded risk-free rate per tenor. |

Three underlyings over 87 business days, 2025-06-02 to 2025-09-30. ACME is the flagship
name and the subject of the study: **5,859 quotes**, 17 strikes from 80 to 120, moneyness
from 0.653 to 1.250, mid prices from 1p to £45.12.

Underneath, `make_data.py` generates the quotes from a volatility surface the model never
sees:

```
k     = log(K / F),  F = S e^{(r - q) T}
atm   = atm0 (1 + 0.18 (T - 0.5))
sigma = atm (1 - 0.30 k / sqrt(T + 0.1) + 1.2 k^2 / (T + 0.1))
```

a skew plus a smile, strongest at the short end, flattening with maturity. On day one, at
one month, across ACME's ladder — the numbers `make_data.py` prints:

| K | 80 | 90 | 100 | 110 | 120 |
| --- | --- | --- | --- | --- | --- |
| σ | 0.3030 | 0.2341 | **0.2038** | 0.2018 | 0.2212 |

That is the thing a single volatility has to be. The mid is that surface priced through
Black–Scholes–Merton and then disturbed the way a quote is — about 35 basis points of
relative error with a floor of 1.5p, rounded to the penny, with calls worth less than 2p
dropped because nothing trades there. So calibration has something real to find, and cannot
find it exactly.

### Three grains, one chain

The chain arrives per contract, the spot and the dividend forecast per underlying, the curve
per tenor. Nobody writes a join: the feature set declares the index it wants and MAYA
broadcasts the coarser members onto it, saying so in its resolution plan:

```
broadcast join member '…/underlying_spot@v1'    on ['date', 'underlying']
join member           '…/option_quotes@v1'      on ['date', 'underlying', 'tenor', 'contract']
broadcast join member '…/discount_curve@v1'     on ['date', 'tenor']
broadcast join member '…/dividend_forecast@v1'  on ['date', 'underlying']
universe filter on underlying: 1 value(s)
```

The feature set is also where the model's notation meets the vendors' column names — `S` is
the spot feed's `spot`, `q` is the forecast's `divYield` — which is the feature set's job and
not the model's. And it is filtered to one underlying, because **a volatility surface belongs
to one underlying**: the other two names are in the features and would each get their own
chain, warrant and calibration.

The pin is `maya://featureset/equity_derivatives/acme_chain#surf2509/2025-09-30`, taken
`as_of_known` 2025-10-01T06:00Z — six the next morning, and it already contains everything,
because this data is knowable the evening it happens. Case study 1 had to wait a year.

## 3. The model, in the notation it was written in

```latex
m = \frac{K}{S}
volShort = where(m < 0.95, sigma11, where(m > 1.05, sigma13, sigma12))
volMid = where(m < 0.95, sigma21, where(m > 1.05, sigma23, sigma22))
volLong = where(m < 0.95, sigma31, where(m > 1.05, sigma33, sigma32))
\sigma = where(T < 0.25, volShort, where(T < 0.75, volMid, volLong))
d_1 = \frac{\ln(S/K) + (r - q + \sigma^2/2) T}{\sigma \sqrt{T}}
d_2 = d_1 - \sigma \sqrt{T}
C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)
```

MAYA parses that, including `N` as the standard normal CDF and `where` as a conditional, so
**the whole pricer is one formula model**. Nothing is a black box, nothing needs an uploaded
weight file, and MAYA can evaluate the model itself — which is what makes blind scoring and
the differential test possible at all.

Two things in that text are worth pausing on.

**The volatility is nine numbers, not one.** $\sigma_{ij}$ is the volatility of maturity band
$i$ and strike band $j$: three maturity bands ($T < 0.25$, $0.25 \le T < 0.75$, $T \ge 0.75$)
crossed with three strike bands ($K/S < 0.95$, at the money, $K/S > 1.05$). A flat surface is
the special case where all nine are equal, which is how this study compares Black–Scholes
proper against a crude surface without changing the model.

**A multi-letter name is one symbol only if it is declared.** MAYA reads LaTeX the way LaTeX
means it: `rT` is $r \cdot T$. So `volShort` is one symbol because it is an intermediate the
formula defines, and every feature and parameter is declared in `roles` — `S, K, r, q, T` as
features, the nine $\sigma_{ij}$ as parameters. The input contract MAYA derives is

```
K, S, T, q, r
```

and note what is *not* in it: `mid`. The quoted price is a member of the chain and not an
input of the model, so the pricer cannot see the price it is calibrated against. That is a
property of the contract, not a convention the script follows.

### The band edges are part of the model

`0.95`, `1.05`, `0.25` and `0.75` are in the governed expression tree. A calibration script
cannot quietly use different ones, and the study goes one better: rather than reading the
numbers off the formula, the calibrator perturbs one $\sigma_{ij}$ at a time and sees which
prices move.

```
quotes claimed by exactly one bucket: 4,095 of 4,095
```

If a quote were claimed by none — a bucket boundary the calibrator had invented, or a
contract with no volatility sensitivity at all — it would show up as a gap rather than being
swept into a neighbour.

### The bound MAYA enforces

A volatility is positive and it is not 400%. The study declares `bounds: [0.01, 3.0]` on all
nine, on the tree MAYA parsed, and MAYA then checks every parameter upload against it for the
life of the version (`WarrantService.check_bounds`, called from `upload_parameters`). §6 shows
it refusing.

The version is left a draft, and nothing can be drawn on it. `setup_model.py` tries:

```
NotApproved: equity_derivatives/bsm_call@v1 is 'draft';
  warrants are drawn on approved model versions
```

which is the ordering the rest of the study depends on — the data a calibration sees is
licensed against a version somebody approved, not against a draft somebody was editing.

## 4. MAYA's own reference implementation

Because the model is an expression tree, MAYA lifts it back into runnable Python — the nine
`params[...]` lines elided:

```python
def predict(X, params):
    v_K = np.asarray(X["K"], dtype=float)
    v_S = np.asarray(X["S"], dtype=float)
    v_T = np.asarray(X["T"], dtype=float)
    v_q = np.asarray(X["q"], dtype=float)
    v_r = np.asarray(X["r"], dtype=float)
    v_m = v_K / v_S
    v_volLong = np.where((v_m < 0.95), v_sigma31, np.where((v_m > 1.05), v_sigma33, v_sigma32))
    v_volMid = np.where((v_m < 0.95), v_sigma21, np.where((v_m > 1.05), v_sigma23, v_sigma22))
    v_volShort = np.where((v_m < 0.95), v_sigma11, np.where((v_m > 1.05), v_sigma13, v_sigma12))
    v_sigma = np.where((v_T < 0.25), v_volShort, np.where((v_T < 0.75), v_volMid, v_volLong))
    v_d1 = (np.log(v_S / v_K) + ((v_r - v_q) + (v_sigma**2.0) / 2.0) * v_T) / (
        v_sigma * np.sqrt(v_T)
    )
    v_d2 = v_d1 - v_sigma * np.sqrt(v_T)
    return {
        "C": v_S * np.exp(-(v_q * v_T)) * _ncdf(v_d1) - v_K * np.exp(-(v_r * v_T)) * _ncdf(v_d2)
    }
```

Nobody typed that twice. It is generated from the same tree the LaTeX produced, so it cannot
drift from the document, and the calibration in §6 prices with MAYA's evaluation of that same
tree rather than carrying a second Black–Scholes of its own.

## 5. The bug that is right at one year

The desk's pricer is its own: vectorised numpy, its own bucket selection, its own order of
operations, written to MAYA's model interface. Uploading it runs the six-rung ladder —

| Rung | Result |
| --- | --- |
| 1. parse | `ruff check` ran: clean |
| 2. entry point | `Model` implements `fit(X, y, ctx)` and `predict(X, params, ctx)` |
| 3. import allowlist | every import is on the allowlist |
| 4. static ban | no filesystem, process, network or dynamic-code use |
| 5. smoke run | succeeded in about a tenth of a second under sandbox tier `strong` |
| 6. determinism | two runs produced identical output |

— and, with the ladder rather than when somebody remembers to ask, the **differential test**:
2,000 sampled input rows, run in the sandbox, compared against MAYA's own evaluation of the
documented mathematics to a relative tolerance of $10^{-9}$. The correct pricer agrees on
**2,000 of 2,000**, both over the default domain and over quotes resampled from the pinned
chain.

Now the bug. One expression:

```
d2 = d1 - vol * tte        where the desk's own correct line reads
d2 = d1 - root             with  root = vol * np.sqrt(tte)
```

It is plausible — a square root dropped from an expression that already has one in it — and it
is **exactly correct at $T = 1$**. The desk quotes the 1Y pillar first, so that is where a test
gets written. The study does not assert what happens next; it runs it.

| Domain of the differential test | Agreement |
| --- | --- |
| The default domain, numbers near 1 | 19 of 2,000 |
| `acme_1y@v1` — the 1Y pillar, 1,479 quotes | **2,000 of 2,000** |
| `acme_chain#surf2509/2025-09-30` — the whole chain, 5,859 quotes | **501 of 2,000** |

Three things follow, and the middle one is uncomfortable.

**The pillar test passes.** Not approximately: identically, to the last bit, on broken code.
That is the unit test the desk would have written.

**On that evidence MAYA lets the version through.** The gate asks whether the last comparison
against *this* artifact agreed everywhere it looked — and it did look, at a quarter of the
chain. So the submission succeeds, and it is the reviewer who sends it back, with a reason
that is now part of the record: *"conformance was run on the 1Y pillar only; re-run it on the
whole chain."* A check is only as good as the domain it explored, which is exactly why MAYA
records the domain on the result and why reading it is somebody's job. (§9 says what I would
change about that.)

**With an honest domain it is refused.** 501 of 2,000 — and those 501 are the 1Y pillar
again: 1,479 of the chain's 5,859 quotes are at one year, 25.2% of them, and the test
resamples each column independently, so about a quarter of its 2,000 rows land at $T = 1$
exactly. Everywhere else:

```
NotApproved: Blocked by check(s): code_matches_specification —
  the code disagrees with the specification on 1499 of 2000 sampled inputs;
  e.g. K=80, S=122.104, T=0.0833333, q=0.02004, r=0.04273
     → specification 45.8522, code 39.3894
```

£6.46 a contract on a deep in-the-money one-month call, and the sign is always the same way.
For $T < 1$, $\sigma T < \sigma\sqrt{T}$, so the bug subtracts too little: $d_2$ comes out too
large, $N(d_2)$ too large, and the premium too low. A desk running it would have been
systematically cheap on everything short-dated and exactly right on the pillar it checked.

The counterexamples combine inputs that never co-occur — MAYA resamples each column
independently, so a spot from one day meets a strike from another — which is deliberate for a
differential test. Two implementations of the same stated mathematics must agree
*everywhere*, not only where the book happens to be.

Finally, the result belongs to the code. It is recorded against the artifact hash, so
attaching different code invalidates it: *"the code has not been tested against the
specification since it changed"*.

## 6. Calibration, and what it does and does not justify

A training warrant is drawn on the pin with `mid` as the target. Two pieces of evidence come
back immediately, and the first is the interesting one:

```
leakage certificate:  certified
rows examined:        5,859
violations:           0
```

**That is the least informative certificate in the case study library, and the study says
so.** Nothing in this panel is a forecast: every input and the target are published the
evening of the trade date, so the rule *"no row may use a value from its own future"* is
satisfied trivially. Compare case study 1, where the same rule refused all 36,000 rows and
had to be answered in writing. A clean certificate here means the data is causal. It does not
mean the model predicts anything, and it cannot, because the target is a price the market had
already quoted.

The warrant hands over **4,957 quotes** — 4,095 train, 862 validation — and escrows **902**.
The developer never sees the escrowed ones.

### What the calibration actually does

For each bucket, choose the volatility that minimises the sum of squared differences between
the model's premium and the quoted mid, over that bucket's training quotes. Least squares in
price, which is what a desk minimises when it marks a surface. The calibrator does not
contain a second Black–Scholes: it prices with MAYA's evaluation of the tree the SDK returned,
so the volatility it finds is the volatility MAYA's blind score will reprice with.

The single best volatility for the whole chain is **0.2377**, with an in-sample RMSE of
**£0.4033** per contract. And per bucket (volatility, quotes calibrated on):

| | K/S < 0.95 | at the money | K/S > 1.05 |
| --- | --- | --- | --- |
| **T < 0.25** (1M) | 0.2224 (588) | 0.2048 (232) | 0.1999 (163) |
| **0.25 ≤ T < 0.75** (3M, 6M) | 0.2378 (1,208) | 0.2180 (478) | 0.2143 (398) |
| **T ≥ 0.75** (1Y) | 0.2609 (592) | 0.2422 (230) | 0.2365 (206) |

Read it both ways: left to right the market charges more volatility for low strikes than for
high ones; top to bottom it charges more for longer maturities. No single number is both.

The surface's own in-sample residual runs from **£0.3877** in $\sigma_{31}$ — one year,
$K/S < 0.95$, the widest band and the most expensive contracts in it — down to **£0.0159** in
$\sigma_{13}$, one month and out of the money, where the options cost pennies and so does
being wrong about them. A single residual for the whole chain would have hidden both.

Compare it with the surface the data was generated from — `make_data.py` prints this, averaged
over the window:

| | K/S < 0.95 | at the money | K/S > 1.05 |
| --- | --- | --- | --- |
| 1M | 0.2882 | 0.2051 | 0.2024 |
| 3M, 6M | 0.2604 | 0.2166 | 0.2122 |
| 1Y | 0.2686 | 0.2423 | 0.2364 |

The at-the-money and high-strike buckets are recovered to within a quarter of a volatility
point. The low-strike buckets come out *flatter* than the truth, and that is not a defect in the
optimiser: the true average over `K/S < 0.95` includes strikes down to 0.65, where a call is
almost all intrinsic and its price barely depends on volatility at all. Least squares in price
weights each quote by its sensitivity, so the bucket's number is set by the quotes that
actually carry volatility. A bucket wide enough to contain both is a bucket whose single
number cannot describe either — which is in *Known Weaknesses*, with this measurement behind
it.

### The misfit, bucket by bucket

Mean error in pence per contract on the validation quotes, flat / nine buckets, positive
meaning the model pays more than the market:

| | K/S < 0.95 | at the money | K/S > 1.05 |
| --- | --- | --- | --- |
| **T < 0.25** (1M) | +1.8 / −1.1 | +37.5 / +0.5 | +19.7 / −0.6 |
| **0.25 ≤ T < 0.75** | −5.4 / −5.3 | +48.2 / −1.2 | +46.8 / +3.7 |
| **T ≥ 0.75** (1Y) | **−70.1** / −6.9 | −15.0 / +3.5 | +4.4 / −0.0 |

The one volatility is not merely less accurate. It is wrong *in a pattern*: seventy pence a
contract too cheap on the long-dated low-strike wing — the most expensive contracts on the
sheet — while overpaying the at-the-money and high-strike buckets out to six months by twenty
to fifty pence. A desk marking its book on it would carry the wing too cheap and believe it
was flat. Where it looks harmless, at 1M low strikes, that is only because those calls have
almost no volatility sensitivity to be wrong about.

Nine buckets are inside seven pence everywhere, and the worst of those seven is the same wing
— which is what the *Known Weaknesses* section of the specification says, in those words,
with these numbers behind it.

### A volatility MAYA will not accept

An optimiser that has not converged produces numbers, and the numbers get uploaded. So:

```
ValidationFailed: Parameters out of bounds:
  'sigma13'=-0.15 outside [0.01, 3.0]; 'sigma33'=8.0 outside [0.01, 3.0]
```

Both ends at once, named individually, before the set exists. The bound was declared on the
model in §3 and it is checked here, not by review.

### Two calibrations of one model version, one escrowed holdout

§8.4 allows several parameter sets per model version — "per region, per desk, per vintage" —
and a flat surface is a legitimate vintage of this one. Both are registered against the same
warrant, quoting the download's checksum, so both come back `verified_data=True`; both are
submitted and approved by a model manager. The choice between them is made on the validation
partition — flat £0.3855, surface £0.1886 — *before* the holdout is touched.

Then MAYA scores the escrowed 902 quotes itself, twice:

| Parameter set | σ | RMSE | MAE |
| --- | --- | --- | --- |
| `flat-vol-2509` | 0.2377 everywhere | **£0.4049** | £0.3154 |
| `surface-2509` | 0.1999 … 0.2609 | **£0.2059** | £0.1422 |

The flat surface is **1.97× worse** on quotes neither calibration was shown. Every attempt is
counted on the warrant — two parameter sets, two attempts — so scoring the holdout until it
flatters you is visible.

### What that holdout is, and what it is not

It is 15% of the same days' chain, drawn by hashing each row's index key. So a withheld
quote for the 105 strike at three months sits between quotes for 102.5 and 107.5 that the
calibration *did* see, on the same evening, on the same underlying. Repricing it is
**interpolation**, and a good score means the surface is locally consistent with the market —
which is a real and useful property, and is what a desk needs from a marking model.

It is not evidence of predictive power, and MAYA cannot make it so. Nothing here says the
premium will be right tomorrow, that the realised volatility will turn out to be anything in
particular, or that the wing is mispriced. A holdout means "rows the fit did not see"; when the fit's target is a published
price, that is a much weaker claim than it sounds, and the specification's *Validation
Evidence* section says exactly this rather than quoting £0.2059 as an accuracy.

## 7. Live, and a covenant about where the surface may be used

```python
covenants = [
    {"kind": "input_range", "attr": "T", "min": 0.02, "max": 1.05},
    {"kind": "input_psi", "attr": "moneyness", "max": 0.25},
]
```

A calibrated model is trustworthy exactly where it was calibrated. Outside the quoted
maturities this surface extrapolates a step function off the edge of the data — confidently,
because Black–Scholes will return a number for any $T$ you give it. So the covenant that
matters is not about the model's output at all: it is about the *region of the request*.

The PSI covenant declares no baseline, so MAYA takes it from this warrant's own quotes and
fixes it at creation — ten quantile bins of the moneyness the surface was actually marked on.
"Drift" therefore means away from the strikes the calibration covered, rather than away from
whatever last week happened to look like.

The warrant names the surface parameter set, is submitted by **mgr** and approved by **lara**
— a second model manager, because the person who submits is not the person who approves — and
sealed, with a 20 kB typeset PDF manifest of what went live. Then a desk system reports a
batch that includes two-year options:

```
WarrantSuspended: Warrant suspended: 'T' max 2.5 above 1.05.
  Contact equity.derivatives.quant@example.com.
```

An administrator reinstates it with a reason — *"the two-year request came from a test
harness; the feed is unchanged"* — and the custody chain reads
`created, submit, approve, sealed, suspended, reinstated`.

One execution warrant runs **one** parameter set. The flat calibration is approved and never
live, which is right; but it also means a desk running a surface per underlying runs one
execution warrant per underlying, and a surface that spans strikes must fit inside a single
parameter set to be governed as one object. That is why the nine volatilities are nine
parameters of one model rather than nine parameter sets.

What the estate holds when the seven steps finish:

| | |
| --- | --- |
| Features / feature sets / models | 4 / 2 / 1, all approved |
| Audit chain | 93 entries on the unattended pass, hash-chained, verified unbroken (running the steps one at a time adds each process's sign-in: 163) |
| Custody events on the training warrant | 9, from `created` to `sealed` |
| Lineage around the pinned chain | 15 nodes, 18 edges |

## 8. Greeks, and why they are not here

MAYA's formula language has `npdf`, so delta and vega are one line each:

$$
\Delta = e^{-qT} N(d_1), \qquad \mathcal{V} = S e^{-qT} \phi(d_1) \sqrt{T}
$$

They are deliberately **out of scope for this model version**, and the reason is structural
rather than mathematical. A MAYA formula model has one output: `evaluate`, the generated
reference code and the differential test all use `outputs[0]`. So delta would be a separate
model version — with its own specification, its own artifact, its own conformance run, and,
because a parameter set is bound to a model version through a training warrant, **its own
copy of the same nine calibrated volatilities**. Two objects would then hold the same numbers
with nothing in MAYA tying the copy to the original, and a recalibration would have to be
remembered twice. That is worse governance than not registering them.

The honest ways to do it are either a multi-output IR — one version, one calibration, several
named outputs, all conformance-tested together — or a composite whose members share a
parameter set, which §8.7 already namespaces by alias. Until one of those exists, the desk's
risk numbers stay outside MAYA and the specification's *Change Log* says so instead of leaving
a reader to wonder.

## 9. What this study found that is not about options

Three observations: two from the runs above, one from the code they made me read.

**The conformance gate does not care how wide the domain was.** MAYA records the domain
string and the artifact hash, which is more than most platforms do, but the gate
(`code_matches_specification`) only asks whether the last comparison agreed. §5 shows a
version with a maturity bug being accepted because the last comparison was run on a
one-maturity feature set. The domain is evidence a human has to read. A policy that could
require the comparison to have been run against a named feature set — or better, against the
feature set the warrant will be drawn on — would close it without any new concept.

**`conformance()` returns a result without the artifact hash it tested.** The stored report
carries `artifact_hash`; the SDK response does not, so a caller who wants to tie the result it
was just handed to a specific artifact has to re-read the model version. `show_estate.py` does
exactly that.

**The differential test's domain ignores the warrant's bindings.** `_conformance_domain`
requires the feature set to expose columns named exactly as the input contract, so a feature
set that supplies `spot` for `S` — legitimate, and what `spec.bindings` exists for — cannot
serve as a test domain. This study named its chain's attributes `S, K, r, q, T` to avoid it,
which is a fair design choice, but it was a choice made to suit the tool.

## 10. What to point at when demonstrating this

1. **§2's resolution plan** — four feeds on three grains, joined by declaration.
2. **§5's table of three domains** — the same code, three answers, one of them a passing unit
   test on a real bug. Then the refusal, and the reviewer's reason on the record.
3. **§6's certificate** — a clean leakage certificate, and a study that tells you it means
   almost nothing here. Governance that can say which of its own evidence is weak is worth
   more than governance that cannot.
4. **§6's bias table and the two holdout scores** — the misfit of a single volatility, in
   pence, on quotes nobody calibrated to, both computed by MAYA against the same escrowed
   rows.
5. **§6's bounds refusal** — a negative volatility named before it can be signed for.
6. **§7's suspension** — a pricing model taken out of service for being asked about a maturity
   it never saw.

## 11. What this study deliberately does not do

It prices European calls on one underlying. No puts (the same tree with the terms
exchanged, and a separate version), no American exercise, no discrete dividends, no barriers,
no term structure or skew *within* a bucket, and no forecast of anything. The surface is a
step function where the market is smooth, so the residual is worst at the band edges and in
the widest bucket, and a quote that crosses an edge as spot moves changes volatility
discontinuously. Recalibration is daily in production, and each day is a new parameter set
against a new warrant rather than an edit.

Those limits are in the specification's *Scope and Limitations* and *Known Weaknesses*
sections, which is where a reviewer will look for them rather than in a README.

---

The input data is **synthetic**, generated by `make_data.py` from the seeded recipe in that
file's docstring. No real quote, counterparty or desk appears anywhere in this folder.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
