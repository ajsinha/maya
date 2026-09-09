# Case study 1 — Black–Scholes: a model with no training data

> **The demo in one sentence.** A European equity call is a *closed form* with
> one number to calibrate, and MAYA governs it without ever pricing an option —
> holding the entire pricer, normal CDF included, as an expression in the
> register.

```bash
.venv/bin/python case_studies/01_black_scholes/build.py
```

Runs in about ten seconds against a local MAYA. See
[`../README.md`](../README.md) for starting the platform and creating users.

---

## 1. Why start here

Most model-governance demos show a scorecard: some data, a fit, a score. That
skips the question a markets audience asks first — *what about the models we
don't train?*

A Black–Scholes pricer has:

- **no training set**, and no amount of asking will produce one;
- **one parameter**, implied volatility, obtained by *matching a market quote*
  rather than by minimising a loss over a sample;
- **a closed form** that has not changed since 1973.

MAYA has a name for that shape. It is **T1**, and the platform derives it.

---

## 2. The taxonomy point (worth two minutes)

MAYA classifies a model by **how its parameter object is inhabited** — never by
what somebody typed in a field. This kernel says:

```python
"parameter_kind": "calibration_set",   # P is matched to observables
"fit_procedure":  "calibrate",         # ...by calibration
```

and MAYA answers **T1**. Nothing in `build.py` declares "T1"; the script prints
back what the platform decided.

| Class | Parameter object inhabited by | Example |
|---|---|---|
| **T0** | nothing — parameters come from theory | a physical constant, an accounting identity |
| **T1** | **calibration to observables** | **this model** |
| T2 | estimation from a sample | case studies 2 and 3 |
| T3 | iterative training | gradient boosting, neural nets |
| T6 | a vendor's parameters you cannot see | a black-box score |

Why it matters here: the warrant grammar admits a `fit` verb **only for classes
that can be fitted**. T0 and T6 cannot, and asking is a *type error* with a
named reason, not a permission problem. T1 can — so a calibration warrant is
admissible, and this case study gets one.

> **Try it.** Change `fit_procedure` to `"none"` and `parameter_kind` to
> `"none"` in `build.py`, register it as version `1.1.0`, and ask for a
> calibration warrant. MAYA refuses with *"its parameters come from theory, not
> from data — there is nothing to fit"*.

---

## 3. The whole model is in the register

This is the part people remember.

MAYA's expression language is arithmetic, comparison, a conditional, and
`exp`, `sqrt`, `log`, `abs`, `min`, `max`, `round`, `floor`, `ceil`. Nothing
else — no imports, no calls out, no state. That is deliberately not enough to
be a programming language, and it turns out to be exactly enough for
Black–Scholes:

```
d₁ = (log(S/K) + (r - q + σ²/2)·T) / (σ·√T)
d₂ = d₁ - σ·√T
C  = S·e^(-qT)·N(d₁) - K·e^(-rT)·N(d₂)
```

with `N(·)` — the standard normal CDF, which the language does not provide —
written out as the Abramowitz & Stegun 7.1.26 rational approximation, and the
symmetry `N(-x) = 1 - N(x)` expressed as a conditional:

```
(upper if x >= 0.0 else 1.0 - upper)
```

The assembled expression is about 3,700 characters. The register holds all of
it.

**What that buys.** There is no artifact to lose, no library version to
disagree with, no "which build of the pricer produced this number". The model
*is* the record. And because MAYA derives both the LaTeX and a runnable Python
module from that same syntax tree, the equation in the specification PDF, the
code a validator recomputes with, and whatever an engine prices with cannot
drift apart.

**The honesty check.** An approximation is an approximation. The script prices
the whole chain both ways — through MAYA's derived Python and through
`math.erf` — before asking anybody to govern it:

```
⚙ engine (not MAYA): the expression MAYA holds agrees with math.erf to 4.84e-06
```

---

## 4. X and P are different things

The kernel declares **two** schemas, and the distinction is load-bearing:

```python
"input_schema":     [spot, strike, tenor, rate, carry]   # X — the data
"parameter_schema": [sigma]                              # P — the parameter
```

A kernel is `f : P ⊗ X → D(Y)`. Putting `sigma` in the input schema would make
**L-W10** — *the featureset must supply everything the kernel reads* — demand
market data for a number that is not market data, and the calibration warrant
would be refused for a reason that is not true.

> This distinction is why `parameter_schema` exists. Building this case study
> is what surfaced its absence: before it, a parameterised model had to list its
> parameters in `input_schema` to have them typeset and generated into code,
> which then broke its own fit warrant.

---

## 5. The data

**Synthetic, and deliberately so.** There is no free, redistributable, quotable
option chain. The script generates one from a *stated* volatility smile:

```python
def true_vol(strike, tenor):
    m = log(strike / SPOT) / sqrt(tenor)
    return 0.200 - 0.045*m + 0.030*m² + 0.010*tenor
```

28 contracts, four tenors × seven strikes, spot 100, r = 4.25%, q = 1.50%. The
smile has the ordinary equity shape — downside puts bid up, upside calls bid
down.

Both clocks are on every row:

| Clock | Value | Meaning |
|---|---|---|
| `event_ts` | valuation date − 1 day | when the quote was true |
| `ingest_ts` | valuation date − 12 hours | when we learned it |

---

## 6. What the script does, step by step

| Step | What happens | Who does it |
|---|---|---|
| 1 | Check the expression against `math.erf` | script |
| 2 | Create the four people | MAYA |
| 3 | Register six features and one **derived** feature (`moneyness`) | MAYA |
| 4 | Load 28 quotes as one view version | MAYA |
| 5 | Declare and fill the featureset | MAYA |
| 6 | Register the model; **T1 and tier 2 are derived** | MAYA |
| 7 | Approve the version — **a tier 2 quorum, two roles** | s.iqbal + v.chen |
| 8 | Put the model *record* in force — submit, approve, attest | MAYA |
| 9 | Grant standing entitlements | MAYA |
| 10 | **Show a refusal**: a warrant naming a featureset that does not exist | MAYA |
| 11 | **Training (calibration) warrant** | MAYA |
| 12 | **Calibrate** — Newton on vega, bracketed by bisection | **script** |
| 13 | Deliver the parameter set — lands **proposed** | MAYA |
| 14 | **Show a refusal**: the author approving their own numbers | MAYA |
| 15 | s.iqbal accepts it | MAYA |
| 16 | Ask for the mathematics; check it against `erf` | MAYA / script |
| 17 | **Execution warrant**, naming the set by id and digest | MAYA |
| 18 | **Price contracts locally** under that warrant | **script** |
| 19 | Write the LaTeX specification | script |

---

## 7. The calibration, and the limitation it exposes

Implied volatility is found by Newton's method on vega, bracketed by bisection
so a bad step cannot run away. It converges on the ATM one-year quote in three
iterations to a price residual of about `9e-13`.

Then the script does something a demo usually does not: it **reprices the whole
chain at that single volatility** and reports how badly it does.

```
⚙ repricing the whole chain at that single vol: RMSE 0.2769, worst 0.5888
```

That error is not a bug. It is the flat-volatility assumption, quantified — a
single σ cannot reproduce a smile, by construction. It goes onto the parameter
set as a diagnostic:

```json
"limitation": "a single flat volatility cannot reprice a smile;
               the RMSE above is that assumption, quantified"
```

**This is the demo's best governance moment.** The reviewer accepting these
parameters reads the limitation *before* approving, rather than discovering it
in a P&L attribution six months later. When the script prices locally at the
end, you can watch it: the at-the-money contract reprices exactly, and the
error grows monotonically toward the wings.

```
contract                strike     model    market    error
EQ-CALL-80-12M              80   22.8737   23.0761  -0.2024
EQ-CALL-100-12M            100    9.5316    9.5316  -0.0000   <- calibrated here
EQ-CALL-120-12M            120    2.9876    2.7578   0.2298
```

---

## 8. What has to be true before a warrant issues

Newcomers usually hit these in this order. The refusals are precise, so let
them happen in a demo rather than pre-empting them.

| Refusal | What it means |
|---|---|
| `restricted: version 1.0.0 is 'draft'` | The **version** has not been approved |
| `policy_refused: ...a record still in 'draft' has been asserted by nobody` | The **model record** has its own lifecycle: submit → approve → attest |
| `no_approved_parameters` | Nothing inhabits P yet, or nobody has accepted it |
| `no_entitlement` | No standing **grant** for this principal, use and environment |
| `schema_not_satisfied` | **L-W10** — the featureset does not cover the kernel's input schema |

**Two lifecycles must both complete.** Approving the *version* says the
mathematics was reviewed. Approving the *record* says this is a model the bank
runs, owned by somebody, at a tier. A warrant needs both.

---

## 9. Grants versus warrants

A **grant** says *this principal may ask*. A **warrant** is one signed, expiring
answer to one asking. Revoking the grant stops the *next* warrant rather than
reaching into the last one, which is why the revocation floor is measured in
seconds rather than in hope.

> **A wrinkle worth knowing.** `parameters.record(warrant_id=...)` is checked
> against the standing **grant**, because a minted warrant document carries a
> freshly generated id that MAYA does not persist and therefore cannot look up
> later. The script passes the grant id and puts the minted document's id in the
> parameter set's diagnostics, so *which authorisation produced these numbers*
> is answerable at both levels. If you are wiring your own engine, pass the
> grant id.

---

## 10. Questions this case study answers well

**"We don't train our pricing models. Does this apply to us?"**
Yes, and this is the case study for it. T1 is a first-class citizen: the
calibration gets a warrant, the calibrated numbers get a parameter set, and a
second person accepts them.

**"Where does the model actually live?"**
Here, in the register, as an expression. Ask
`GET /api/v1/mathematics` and you get the equation and runnable code, both
derived from it.

**"Who checks the quant?"**
The version needs two signatures in two roles. The parameter set needs somebody
other than its author. The script shows both refusing.

**"Does MAYA price our book?"**
No. Watch the `⚙` lines — the calibration and every price in this run happened
in the script's own process.

---

## 11. Files this produces

| File | What it is |
|---|---|
| `warrant-training.json` | The calibration warrant, exactly as MAYA issued it |
| `warrant-execution.json` | The execution warrant, naming the approved set by id and digest |
| `black-scholes-specification.tex` | The specification; equation derived by MAYA |

```bash
pdflatex black-scholes-specification.tex     # 2 pages
```
