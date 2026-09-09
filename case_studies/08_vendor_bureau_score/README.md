# Case study 8 — A vendor bureau score: governing what you cannot see

> **The demo in one sentence.** The bank buys a credit score, cannot inspect
> the model, could not reproduce it — and declines people with it. MAYA's answer
> is not to pretend otherwise: it refuses a fit, refuses reverse-engineered
> coefficients, and governs the three things that remain.

```bash
.venv/bin/python case_studies/08_vendor_bureau_score/build.py
```

---

## 1. The theory

### What a bureau score is

A consumer credit score is a model owned by a third party — Experian,
Equifax, TransUnion, FICO — fitted on data the bank does not hold, using
methods the bank is not told, and delivered as a single number in a documented
range. FICO's is 300–850; VantageScore's is the same range by design so the two
can be swapped.

The bank sends an identifier and a **permissible purpose** (under the US Fair
Credit Reporting Act, pulling a file requires one) and receives a number. That
is the entire interface.

### Why it is a model and not data

This is the argument worth having in a demo, because banks are inconsistent
about it. A bureau score is:

- **data** to the bank's decisioning platform, which reads it as a feature; and
- **a model output** to the bureau, which fitted it.

Both are true, and the governance consequence follows from the second. If a
bank treats it purely as data, then when the bureau reversions their model —
which they do, on their schedule, without asking — the bank's decisions change
and nothing in the bank's model inventory records that anything happened.
Regulators have been explicit that third-party models are in scope: SR 11-7 and
SR 26-2 both treat vendor models as the bank's responsibility to govern,
*including* the parts the bank cannot see.

### T6, and how it differs from T0

MAYA derives the class from how the parameter object is inhabited:

| | Parameter object | Fit is | Because |
|---|---|---|---|
| **T0** | does not exist — theory fixes the model | a **type error** | there is nothing a fit could produce |
| **T6** | **exists**, and is not ours | a **type error** | the parameters are somebody else's |

Both refuse. They refuse for *different reasons*, and the difference is not
pedantry:

- For T0, the honest alternative is `provenance="declared"` — a person asserting
  a number from theory.
- For T6, there is **no** alternative. The bank cannot record the parameters at
  all, because it does not have them, and anything it recorded would be a
  different model.

MAYA says both sentences correctly, which is what makes the taxonomy load-bearing
rather than decorative.

### The reverse-engineering temptation

A bank *can* fit a local model to reproduce a vendor score — regress the score
on the attributes it sent, get an R² of 0.9, and now you have coefficients.

The temptation is to file those as the model's parameters. It is the wrong move,
and MAYA refuses it:

```
[parameters_not_reachable] this version's parameters are inside a vendor black
box and cannot be reached, so MAYA cannot take delivery of them
→ record what the vendor states with provenance 'declared'
```

**Those coefficients are a different model that happens to correlate.** It will
track the vendor score until the day it does not — a segment the surrogate never
saw, or a reversion — and the divergence will be invisible precisely because the
register said the surrogate *was* the score. The right registration is a
*separate* model, related by `challenger_of` (which deliberately does **not**
propagate in the blast radius) or `benchmark_for`.

### What governance can still do

Everything requiring inspection is gone: no coefficient review, no independent
recode, no recomputation. What remains is the outside of the model, and it is
more than nothing:

**The contract.** What the vendor *asserts* — the 300–850 range, a gini floor,
a stability ceiling. Recorded as assertions with the source named, not as
findings. The distinction is the whole governance content of a T6 registration:
`gini ≥ 0.55` is true of the vendor's development sample and says nothing about
this bank's book, and the record says so rather than implying otherwise.

**Monitoring.** The score's *distribution over the bank's own population* is
observable without seeing inside. Population stability index, the share below
each policy cut, drift quarter on quarter, and — where outcomes exist —
discrimination measured on the bank's own defaults rather than the vendor's.

**The dependency.** When the bureau reversions, what breaks? Answerable from
the graph rather than from a supplier spreadsheet.

**The tier.** `interpretable=False` is declared honestly, and it **raises the
tier to 1**. Declaring otherwise to get a friendlier number is exactly the lie
this class exists to prevent.

### Adverse action, and the thing T6 makes hard

Under ECOA and Regulation B, a declined applicant must be given the specific
principal reasons. For a rulebook (case study 6) that is the rule that fired.
For a score nobody can see, the reason codes come **from the vendor** — and the
bank is accountable for them without being able to verify them.

MAYA does not solve that. It makes it visible: the reason codes are the vendor's
assertion, recorded as such, and the tier reflects it.

---

## 2. What the script does

| Step | What happens |
|---|---|
| 1–2 | Register what the bank **sends** and what it **receives** |
| 3 | Load the pulls — `event_ts` the pull, `ingest_ts` the response |
| 4–5 | The featureset, and the model at the **vendor's** version number |
| 6–8 | Tier it (`interpretable=False`), approve the version, put the record in force |
| 9 | **Show a refusal**: a training warrant, refused for three reasons at once |
| 10 | **Show a refusal**: reverse-engineered coefficients |
| 11 | Execution warrant — runtime `descriptor_only` |
| 12 | **Monitor the outside**: the distribution over this book |

---

## 3. The refusal, in full

Once the version is approved and in force, the fit warrant is refused with
**three** independent reasons:

```
[grammar_violation] the warrant does not conform to the grammar: 3 problem(s):
  this model is registered descriptor-only — MAYA holds its governance but not
    a locatable artifact — so it cannot be warranted for fitting;
  a T6 model cannot be fitted: its parameters are inside a vendor black box and
    cannot be reached;
  a 'fit' produces the parameter object, so it cannot also run from
    'vendor_internal'
```

Three separate properties of the registration each independently make the
request incoherent. That is defence in depth doing what it is supposed to.

> **A sequencing note worth knowing for your own demos.** Ask for this warrant
> *before* the version is approved and you get `restricted: version 3.2.0 is
> 'draft'` instead. Ask before granting the entitlement and you get
> `no_entitlement`. Both are correct and neither demonstrates T6 — a control
> that refuses for the wrong reason is a demonstration of the wrong control.
> The script grants and approves first, deliberately.

---

## 4. Two details that matter more than they look

### The version number is the vendor's

```python
SEMVER = "3.2.0"     # the VENDOR's version, not ours
```

A bank that renumbers a vendor's model has thrown away the only identifier both
parties share. When the vendor's release notes say "v3.3 changes the thin-file
treatment", the bank needs to be able to find v3.2 in its own register without a
translation table.

### `bureau_score` is a feature whose source system is a vendor

```python
maya.features.define(name="bureau_score", entity="applicant", dtype="numeric",
                     description="the score as received, 300-850. NOT computed here",
                     source_system="credit bureau (vendor)")
```

That is the honest description of the dual nature in §1: it is data here, and a
model output there, and the `source_system` field is where that fact lives.

---

## 5. The monitoring output

```
⚙ n=12  mean=698.0  sd=75.96  min=588.0  median=705.0  max=812.0
⚙ 4 of 12 below the 660 policy floor
✓ MAYA: the contract's stated range 300-850 holds on this book: True
```

**This is not a validation.** A validation of a model you cannot see is not a
thing, and the script says so out loud. It is a description of what the model is
doing to *this* population — the handle the bank actually has, and a real one.
The vendor's asserted gini is measured on the vendor's development sample, and
the monitoring record states that rather than letting it be read as a
verification.

---

## 6. The data

**Synthetic.** A real bureau file is licensed and cannot be redistributed —
which is itself part of the point of this case study. The scores are chosen to
span the range and straddle the 660 policy floor.

---

## 7. Things to try live

**Change `interpretable` to `True`** and re-tier. Watch the tier fall. Then ask
whether anybody would notice, and what in the platform would have caught it —
the answer is nothing, because tiering reads what it is told. It is an input to
governance, not a control over it, and that boundary is worth being explicit
about.

**Register the surrogate properly.** Fit a local model to the score, register it
as its own model, and relate it with `challenger_of`. Then check the blast
radius — it does not move, because a challenger is deliberately not a dependency.

**Ask for a `fit` before approving.** Watch the refusal change to `restricted`,
and note that it proves something different.

---

## 8. Questions this case study answers well

**"How do we govern a model we did not build?"**
By its contract, its monitoring, its dependencies and its refusals — and by
being honest that inspection is not among them.

**"Can we just treat it as data?"**
You can, until the vendor reversions. Then your decisions changed and your model
inventory records nothing.

**"Our validators want to review the coefficients."**
They cannot, and the platform will not let anybody pretend they did. What they
can review is the contract and the monitoring, and the record distinguishes the
vendor's assertions from the bank's measurements.

---

## 9. Files this produces

| File | What it is |
|---|---|
| `refusal-training.json` | The three-reason refusal, kept as evidence |
| `warrant-execution.json` | The execution warrant, `descriptor_only` |
| `monitoring.json` | The observed distribution, and what it does *not* establish |
| `bureau-score-specification.tex` | Specification |

```bash
pdflatex bureau-score-specification.tex     # 2 pages
```
