# Case study 10 — An SEIR epidemic model, and a reporting delay that closes schools

> **The demo in one sentence.** The same outbreak data, on the same day, yields
> R₀ = 2.04 or R₀ = 2.34 depending on one modelling choice nobody writes down —
> and MAYA's two clocks are what make that choice a recorded decision rather
> than an accident.

```bash
.venv/bin/python case_studies/10_seir_epidemic/build.py
```

Independent of the other case studies. Runs in about ten seconds.

---

## 1. The theory

### The compartmental idea

Kermack and McKendrick's 1927 insight was that an epidemic can be described
without tracking individuals at all: partition the population into
**compartments** and write down the flows between them. SEIR is the four-box
version, and it is still the workhorse a century later.

```
     β·S·I/N        α·E          γ·I
S ───────────► E ────────► I ────────► R
```

| | Compartment | Leaves at rate |
|---|---|---|
| **S** | susceptible | `β·S·I/N` — proportional to contact between S and I |
| **E** | exposed: infected, **not yet infectious** | `α·E`, so the latent period averages `1/α` |
| **I** | infectious | `γ·I`, so the infectious period averages `1/γ` |
| **R** | removed — recovered or dead | — |

```
dS/dt = -β·S·I/N
dE/dt =  β·S·I/N - α·E
dI/dt =  α·E - γ·I
dR/dt =  γ·I
```

The **E** compartment is what separates SEIR from the simpler SIR, and it is not
a detail. A disease where you are infectious immediately behaves very
differently from one with a three-day head start — the latent period sets how
much of the epidemic is already committed and invisible on any given day.

### R₀, and why the second decimal place is a policy difference

```
R₀ = β / γ                    R_eff = R₀ · s        (s = susceptible fraction)
```

R₀ is the expected number of secondary cases produced by one case in a fully
susceptible population. It is a **threshold** parameter:

- `R_eff > 1` — each case more than replaces itself; the epidemic grows.
- `R_eff < 1` — it shrinks.

There is no smooth interpolation between those two futures. Which is why a
disagreement in the second decimal place is not a technical quibble: it is the
difference between a policy that works and one that does not, argued in a
meeting where nobody has time to interrogate the calibration.

The **herd immunity threshold** falls straight out: `R_eff = 1` when
`s = 1/R₀`, so the immune fraction needed is `1 − 1/R₀`. At R₀ = 2.34 that is
**57.2% of the population** — a number that has been used to justify enormous
policy decisions and is only as good as the R₀ underneath it.

### Estimating R₀ from a growth rate

You cannot observe β and γ directly. What you can observe is the **exponential
growth rate** `r` of the early curve, and for an SEIR system with exponentially
distributed latent and infectious periods the Euler–Lotka relation gives R₀
exactly:

```
R₀ = (1 + r/α) · (1 + r/γ)
```

So the recipe is: take logs of daily incidence, fit a straight line, read off
the slope `r`, apply the relation. That is what the script does, and it is what
real outbreak analytics does in the first weeks of an epidemic.

Note the shape of it: **α and γ are assumed, not fitted.** They come from
clinical studies of the disease. Only `r` — and through it β — is estimated
from the outbreak. A wrong assumption about the latent period propagates
straight into R₀ and no amount of data quality fixes it.

---

## 2. The reporting delay, which is the whole case study

### What actually happens

A case that occurs on day *t* is not in the database on day *t*. Somebody feels
ill, waits, tests, the laboratory runs the sample, the result is notified, the
notification is keyed. In this case study the pipeline is five days long and,
crucially, **partial**:

| Age of case | Fraction reported |
|---|---|
| 0 days (today) | 10% |
| 1 day | 35% |
| 2 days | 62% |
| 3 days | 83% |
| 4 days | 95% |
| 5+ days | 100% |

Which produces exactly this on the screen of anybody looking at the dashboard:

```
  day   occurred   reported   as seen today
   25       88.9       88.9     100% reported
   26      101.9       96.8      95% reported
   27      116.7       96.9      83% reported
   28      133.8       82.9      62% reported
   29      153.3       53.6      35% reported
   30      175.6       17.6      10% reported
```

**The right-hand end of the curve is bending downward.** Cases are still
accelerating — 175 on day 30 against 133 on day 28 — and the surveillance
system shows a fall from 83 to 18. This is not a data quality problem to be
fixed. It is what a correctly functioning notification system looks like.

### What it does to the answer

The script calibrates twice on the same data, on the same day:

| Treatment | R₀ | Error vs truth (2.40) |
|---|---|---|
| Fit on **all** available days | **2.037** | −15.1% |
| Drop the five incomplete days | **2.338** | −2.6% |

A 15% error, in the direction that says *the epidemic is slowing down*, from a
choice most people would not describe as a modelling assumption at all.

And note which way the bias runs. The mistake is not random — it is
**systematically reassuring**. The naive fit always says things are better than
they are, on exactly the days when someone is deciding whether to act.

### Why this is a MAYA problem

Because it is the *same problem* as case study 3's servicer reporting lag, with
a public-health decision on the other end instead of a prepayment forecast. Two
clocks:

| Clock | Here |
|---|---|
| `event_ts` | when the case **occurred** |
| `ingest_ts` | five days later, when it was **reported** |

With both recorded, "what did we know on the day we gave the advice?" is a
query. Without them it is an argument in a public inquiry two years later, in
which nobody can reconstruct the dataset and everybody is sure they remember.

### The counterfactual on the record

The script records the **rejected** number as a diagnostic on the parameter set:

```json
"r0": 2.338,
"r0_if_recent_days_not_dropped": 2.037,
"days_dropped": 5,
"limitation": "The most recent days are incompletely reported and are
   excluded. Including them biases R0 DOWNWARD — here to 2.04 against 2.34 —
   because a partially reported week looks like a slowing epidemic. This is a
   property of the surveillance system, not of the disease."
```

**That single field is the governance contribution.** It converts an invisible
modelling choice into a reviewable one. A validator reading the parameter set
sees not just what was chosen but the size of the effect of choosing otherwise
— and can form a view in thirty seconds instead of re-deriving the analysis.

The second-line reviewer's acceptance note says so explicitly:

> *"Accepted. The excluded-days treatment is documented and the counterfactual
> R₀ is on the record, which is what makes the choice reviewable rather than
> invisible."*

---

## 3. T1, and what "calibration" actually means

MAYA derives **T1** — `calibration_set` inhabited by `calibrate`.

The distinction from T2 (estimation) and T3 (training) is worth drawing out,
because SEIR sits cleanly in a class people often mislabel:

| | What is estimated | What is assumed |
|---|---|---|
| **T3** trained | the function itself | an architecture and a loss |
| **T2** estimated | coefficients on chosen inputs | the functional form |
| **T1 — SEIR** | **two rates** | **the entire structure** |

The compartments and the flows between them are not learned from the data.
They are **asserted by the model's form**, and they come from theory about how
an infection progresses. If the theory is wrong — if there is a substantial
asymptomatic reservoir the four boxes do not represent — no amount of data
makes the model right, and the calibration will happily fit rates to a
structure that does not hold.

That is why T1 models get more scrutiny of their *assumptions* than their
*fit statistics*. The R² on log incidence in this case study is above 0.99, and
that number tells you almost nothing about whether the model is right.

---

## 4. What is deliberately not modelled

Named in the record, because a compartmental model's omissions are precisely
where its projections and reality diverge:

- **Homogeneous mixing.** Every susceptible is equally likely to meet every
  infectious person. Real contact networks are nothing like this, and real
  transmission is heavily **overdispersed** — a minority of cases cause the
  majority of onward infections. Superspreading makes outbreaks both more likely
  to die out by chance *and* more explosive when they do not, neither of which
  the deterministic model can express.
- **Exponentially distributed latent and infectious periods.** Analytically
  convenient — it is what makes the Euler–Lotka relation exact — and
  biologically wrong. Real periods are closer to gamma-distributed with much
  less variance.
- **Age structure and spatial heterogeneity.** Contact rates differ by an order
  of magnitude across age bands.
- **Any intervention effect.** The projection assumes nobody changes their
  behaviour, which they demonstrably do — often before any policy tells them to.

The last one is the sharpest for a demo: **a projection from this model is a
statement about what happens if nothing changes**, and it will be reported as a
forecast. That gap has already caused one round of public argument about
epidemic models, and no register can close it. What MAYA can do is put
`not_modelled` in the same place as the numbers.

---

## 5. Setting up the people

The script creates them if they do not exist (`_common/casekit.py`):

| Login | Name | Role | Does here |
|---|---|---|---|
| `a.mehta` | Anika Mehta | `model_developer` | calibrates, delivers β and γ |
| `j.okafor` | Jide Okafor | `model_owner` | owns the model |
| `s.iqbal` | Sana Iqbal | `model_risk_manager` | **accepts** the parameter set |
| `v.chen` | Wei Chen | `validator` | second quorum signature |

Manually, if you prefer:

```bash
curl -s -XPOST localhost:5099/api/v1/principals -H 'Content-Type: application/json' \
  -d '{"login":"a.mehta","display_name":"Anika Mehta","roles":["model_developer"],
       "password":"quant-password-long"}'
```

The separation that matters: **a.mehta delivers the parameters, s.iqbal accepts
them.** One person cannot do both, and the choice about which days to drop is
therefore seen by somebody who did not make it.

---

## 6. What the script does

| Step | Who | What |
|---|---|---|
| 1 | ⚙ engine | Simulate a known outbreak (R₀ = 2.40) and degrade it through the reporting pipeline |
| 2 | ⚙ engine | Calibrate **twice** — with and without the incomplete days |
| 3–4 | ✓ MAYA | Register the features; load the curve with **both clocks** |
| 5–6 | ✓ MAYA | Featureset; register the model; **T1 derived** |
| 7–8 | ✓ MAYA | Quorum approval; put the record in force |
| 9 | ✓ MAYA | Grants — calibrate in the lab, advise in production |
| 10 | ✓ MAYA | **Calibration warrant**, bounding both clocks |
| 11 | ✓ MAYA | Record β and γ **with the counterfactual R₀ as a diagnostic** |
| 12 | ✓ MAYA | A second person accepts |
| 13 | ✓ MAYA | **Execution warrant** |
| 14 | ⚙ engine | Project R_eff **locally**, as immunity accumulates |
| 15 | — | Write the LaTeX specification |

MAYA never integrates an ODE and never fits a growth rate. It registers what
the model is, warrants who may calibrate it and when, takes delivery of the
rates, and warrants who may run it.

---

## 7. The output

```
 susceptible    R_eff   interpretation
       1.000    2.338   epidemic grows
       0.800    1.870   epidemic grows
       0.600    1.403   epidemic grows
       0.428    1.000   HERD IMMUNITY THRESHOLD
       0.300    0.701   epidemic shrinks
```

`0.428 = 1/R₀`. The immune fraction at that point is **57.2%**, and the arrival
of `R_eff = 1.000` exactly on that row is the model's arithmetic checking
itself.

---

## 8. Things to try live

**Change `REPORT_DELAY_DAYS` to 10** and re-run. The naive R₀ collapses further
while the corrected one holds. This is the single most convincing thing to do
in front of an audience: the size of the error is a property of the *pipeline*,
not of the disease, and it is invisible on the face of the data.

**Set `drop_recent=0` in the delivered parameters** and watch the herd immunity
threshold fall from 57% to 51%. Six points of a national population is a
policy, and it came from a default argument.

**Move `AS_OF` back ten days** and re-run the fit warrant. The window bounds
both clocks, so you get the epidemic as it was *understood* then — not as it is
understood now. That is the reproducibility a public inquiry asks for.

**Ask for the fit warrant before approving the version.** You get `restricted:
version 1.0.0 is 'draft'` — a different control, correctly refusing.

---

## 9. Questions this case study answers well

**"What does model risk management have to do with public health?"**
Everything in this file is the same control a bank applies to a PD model. The
governance question — *did the numbers you acted on reflect what you knew at
the time* — is domain-independent.

**"Where does a modelling judgement get recorded?"**
As a diagnostic on the parameter set, alongside what the alternative would have
produced. Judgements that are not written down are not reviewable, and this one
moves R₀ by 15%.

**"Why do you insist on two timestamps?"**
This case study is the answer. One clock cannot express "the last five days are
still filling in", and every consequence in §2 follows from that.

---

## 10. Files this produces

| File | What it is |
|---|---|
| `warrant-training.json` | The calibration warrant, both clocks bounded |
| `warrant-execution.json` | The execution warrant |
| `seir-specification.tex` | Specification, with the two-R₀ comparison |

```bash
pdflatex seir-specification.tex     # 2 pages
```
