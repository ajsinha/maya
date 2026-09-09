# Case study 4 — Merton distance to default: a model with nothing to fit

> **The demo in one sentence.** Some models have no parameters at all, and the
> most interesting thing MAYA does with this one is **refuse** to train it —
> not because you lack permission, but because the request is a type error.

```bash
.venv/bin/python case_studies/04_merton_distance_to_default/build.py
```

Runs in about ten seconds. See [`../README.md`](../README.md) for starting the
platform and creating users.

---

## 1. The theory

### The structural idea

Merton (1974) observed that the equity of a leveraged firm **is** a call option
on its assets. If the firm owes `D` at time `T`, then at `T` the shareholders
either repay and keep the residual, or hand the firm to the creditors:

    equity payoff at T = max(V_T - D, 0)

That is precisely a European call on the asset value `V` with strike `D`. It
follows that the whole Black-Scholes apparatus applies to the capital structure
of a firm, and that default is not an event to be predicted statistically but a
**boundary crossing** to be priced.

This is the *structural* approach, as against the *reduced-form* approach
(Jarrow-Turnbull, Duffie-Singleton) where default is an exogenous jump process
calibrated to spreads. Structural models say *why* a firm defaults; reduced-form
models fit *when* the market thinks it will.

### Distance to default

Assume asset value follows a geometric Brownian motion,
`dV = mu*V*dt + sigma_V*V*dW`. Then `ln V_T` is normal, and the number of
standard deviations between today's log asset value and the default point is

    DD = [ln(V/D) + (r - sigma_V^2/2)*T] / (sigma_V*sqrt(T))

and, under the risk-neutral measure,

    PD = N(-DD) = 1 - N(DD)

`DD` is the quantity practitioners actually quote, because it is
scale-free and comparable across firms and sectors. It has a clean reading:
**how many standard deviations of asset value the firm is from insolvency at
the horizon.**

Notice what is in it. Leverage `V/D` enters through a logarithm, and volatility
enters twice — in the drift adjustment and in the denominator. This is why a
low-leverage, high-volatility firm can be riskier than a high-leverage, stable
one, which the output table in §7 shows directly. That insight is the model's
main contribution and it is unavailable to a leverage ratio.

### The `-sigma^2/2` term

Worth a sentence because it is asked about. Under GBM, `E[V_T] = V*exp(mu*T)`
but `E[ln V_T] = ln V + (mu - sigma^2/2)*T`. The asset value's *expected log*
grows more slowly than its *log expectation*, by half the variance. Since
default is a condition on `ln V_T`, the drift that matters carries the
correction — the same term that appears in `d1` and `d2` in Black-Scholes, for
the same reason.

### The unobservability problem

`V` and `sigma_V` are not observable. What trades is equity, not assets. The
KMV/Moody's approach solves a two-equation system simultaneously:

    E      = V*N(d1) - D*exp(-rT)*N(d2)          (equity is a call on assets)
    sigma_E = (V/E) * N(d1) * sigma_V             (Ito on that relation)

for the two unknowns `V` and `sigma_V`, given observable equity value `E` and
equity volatility `sigma_E`. **So a production Merton model has another model
inside it**, and this case study takes `V` and `sigma_V` as given precisely so
that the T0 point is not obscured — noting in the specification that a real
registration would carry the inference as its own model joined by an
`input_to` edge.

### Where the model is known to be wrong

- **The credit spread puzzle.** Merton PDs and spreads are far too low for
  short maturities and investment-grade firms. Diffusion cannot produce a
  default tomorrow for a firm comfortably solvent today, whereas markets price
  one. Jump-diffusion (Zhou) and first-passage models (Black-Cox, Longstaff-
  Schwartz) address this by letting default happen before `T`.
- **A single zero-coupon liability.** Real capital structures have seniority,
  covenants and rolling maturities. `D` is a fiction — usually short-term debt
  plus half of long-term, in the KMV convention.
- **Constant volatility and no jumps**, inherited from Black-Scholes.
- **The PD is risk-neutral**, not physical. `N(-DD)` prices default; it does not
  forecast it. Converting between the two requires a risk premium, and KMV's
  answer was to abandon the mapping altogether and calibrate `DD` to an
  empirical default frequency instead.

That last point is why this case study registers the model as a **challenger to
the internal rating** rather than as the rating itself.

### References

- Merton, R. C. (1974). *On the Pricing of Corporate Debt: The Risk Structure
  of Interest Rates.* Journal of Finance 29(2).
- Black, F. and Cox, J. (1976). *Valuing Corporate Securities.* Journal of
  Finance 31(2).
- Crosbie, P. and Bohn, J. (2003). *Modeling Default Risk.* Moody's KMV.

---

## 2. The model

The Merton (1974) structural model treats a firm's equity as a call option on
its assets. The firm defaults when asset value falls below the face value of
debt at the horizon, so:

```
DD = [ ln(V/D) + (r − ½σ_V²)·T ] / (σ_V·√T)
PD = N(−DD)
```

Five observables — asset value `V`, debt face `D`, asset volatility `σ_V`, the
risk-free rate `r`, the horizon `T`. Nothing else. **There is no sixth quantity
that had to be learned from a sample**, and that absence is the whole point.

---

## 3. T0, and why the class is load-bearing

```python
"parameter_kind": "none",     # P = I, the terminal object
"fit_procedure":  "none",
```

MAYA answers **T0**. The other case studies all have a parameter object
somebody had to produce and somebody else had to approve; this one does not.

| Class | P is inhabited by | Can it be fitted? |
|---|---|---|
| **T0** | **nothing — theory determines it** | **No. Type error** |
| T1 | calibration to observables | Yes |
| T2 | estimation from a sample | Yes |
| T3 | iterative training | Yes |
| T6 | a vendor's parameters you cannot see | No. Type error |

**T0 and T6 are the two classes for which fitting is meaningless**, and MAYA
refuses them for *different reasons*, each named.

---

## 4. The demonstration: two doors into the same mistake, both shut

### Door one — ask for a training warrant

```
[grammar_violation] a T0 model cannot be fitted: its parameters come from
theory, not from data — there is nothing to fit
```

Read that aloud in a demo. It is not "you are not authorised". It is not "no
training data is configured". It is the platform saying the request does not
typecheck.

The script saves this refusal to `refusal-training.json`, because **a refusal
is evidence**. "We tried to train the structural model and the platform would
not let us" is a sentence with a document behind it.

### Door two — record a parameter set anyway

Somebody who cannot get a warrant will often try to write the numbers in
directly. That door is shut too, with a *different* message:

```
[nothing_to_fit] this version's parameter object is terminal: its parameters
come from theory, not from data, so there is nothing a fit could have produced
→ record them with provenance 'declared', which is what a closed form actually has
```

Note the remediation. MAYA is not saying *never record anything*; it is saying
that if a person is asserting a number, the provenance is **declared**, not
**fitted** — and those two words mean different things to whoever reads the
register later.

**Why this matters.** A platform that issued the warrant, ran a "fit", and
stored a fitted parameter set for a model with no parameter object would be
recording a fiction — and would do it silently, because every individual step
would have returned success.

---

## 5. What *does* happen: it is governed anyway

The absence of parameters does not mean the absence of governance. This model
still goes through:

| Step | Still required? |
|---|---|
| Risk tiering | Yes — tier 2, derived from exposure and purpose |
| Version approval | Yes — two signatures, two roles |
| Model record lifecycle | Yes — submit, approve, attest |
| Standing grant | Yes |
| Execution warrant | Yes |
| **Approved parameter set** | **No — there is nothing to approve** |

The execution warrant issues immediately once the version and record are
approved, and its parameter binding is `none`. Compare with case study 1, where
the same request is refused with `no_approved_parameters` until somebody
accepts the calibrated volatility.

---

## 6. The equation is in the register

As in case study 1, the whole model — including the Abramowitz–Stegun normal
CDF — is one expression MAYA holds. It is checked against `math.erf` on the way
through:

```
⚙ engine (not MAYA): the expression MAYA holds agrees with math.erf to 6.46e-08
```

`GET /api/v1/mathematics` returns the equation and a runnable `predict()`,
both derived from that same syntax tree.

---

## 7. The output

```
obligor                 V/D    σ_V      DD     PD %
ACME-INDUSTRIALS       2.29   0.22    3.84     0.01
BOREAL-MINING          1.19   0.41    0.32    37.41
CALDER-RETAIL          1.10   0.35    0.22    41.21
DELTA-UTILITIES        1.81   0.14    4.46     0.00
EASTPORT-SHIPPING      1.07   0.48   -0.01    50.50
FENWICK-PHARMA         3.44   0.29    4.27     0.00
GRANITE-REIT           1.33   0.19    1.64     5.02
HARROW-AIRLINES        0.91   0.52   -0.35    63.76
```

Two things to point at:

**Volatility matters more than leverage.** `DELTA-UTILITIES` has less asset
cover than `ACME-INDUSTRIALS` (1.81 vs 2.29) and a *lower* PD, because its
asset volatility is 0.14 against 0.22. That is the model's central insight and
it falls out of the formula rather than being fitted.

**`HARROW-AIRLINES` already has assets below debt** (V/D = 0.91), so its
distance to default is negative and its PD is above 50%. The script says how
many such obligors are in the book before it starts, so you know what to look
for.

---

## 8. The stated limitation

Asset value and asset volatility **are not observable**. In practice both are
inferred from equity value and equity volatility by solving the Merton system
simultaneously — which makes this model's inputs another model's *output*.

This case study takes them as given so the T0 point is not obscured, and says
so in the specification. A production registration would carry that inference
as its own model, joined by an `input_to` edge — which is exactly what **case
study 5** does with this model's output.

---

## 9. Things to try live

**Make it T1 and watch the refusal disappear.** Change the kernel to
`parameter_kind: "calibration_set"`, `fit_procedure: "calibrate"`, register it
as `1.1.0`, and ask for a training warrant. It issues — because a calibrated
asset volatility *is* something a fit could produce.

**Record the parameters as declared.** Follow the remediation:
`provenance="declared"` with a `warrant_id` of `None`. That path is open, and
it is the right one for a number a person is asserting.

**Look at the two refusals side by side.** `grammar_violation` comes from the
warrant grammar; `nothing_to_fit` comes from the parameter register. Two
independent layers reached the same conclusion, which is what defence in depth
looks like when it is real.

---

## 10. Questions this case study answers well

**"What about our closed-form models?"**
They are first-class. T0 is a class, not an unsupported case.

**"Won't people just write the numbers in anyway?"**
They will try. The second refusal is for that, and it points at the honest
alternative rather than just saying no.

**"Is the taxonomy just labelling?"**
No — it decides what operations are admissible. This case study is the proof:
change one field in the kernel and the same request goes from a type error to a
warrant.

---

## 11. Files this produces

| File | What it is |
|---|---|
| `refusal-training.json` | The refusal, kept as evidence |
| `warrant-execution.json` | The execution warrant, with a `none` parameter binding |
| `merton-specification.tex` | Specification; equation derived by MAYA |

```bash
pdflatex merton-specification.tex        # 2 pages
```
