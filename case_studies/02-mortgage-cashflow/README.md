# Case study 2 — a scheduled mortgage cashflow model

**Domain:** banking, mortgage asset-liability management · **Model type:** closed-form,
**nothing to fit** · **What it exercises:** a model registered from LaTeX, MAYA's own
reference implementation lifted from the mathematics, the six-rung artifact ladder, a
differential test that catches the commonest mortgage bug, a parameter set that is a
contractual constant rather than a fit, blind reconciliation against a third party's
report, and a covenant about the data rather than the model.

## The scripts, and what each one does

Seven scripts, run in this order. They share one MAYA at
`case_studies/runs/mortgage_alm/`, which the first builds and the rest reopen, so **each
can be run on its own, in its own process** — and between any two you can open the web UI
and show what the last one created.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes the loan tape and the servicer's report to `data/` (already committed; run it only to regenerate). No MAYA. | The recipe: exact level-payment amortisation, disturbed by partial prepayments and late payments the way a real book is. |
| `setup_features.py` | Declares and ingests the two feeds as features, submits them as **dana**, approves them as **mick**. | Two feeds on two different lags — two business days and a fortnight — each declaring its own knowledge time. |
| `setup_featureset.py` | Composes `loan_month` on `(date, loan)` from the four tape columns *and* the servicer's remittance, approves it, pins it. | Keeping the benchmark inside the pinned set is what makes the later reconciliation reproducible. |
| `setup_model.py` | Registers the model from the **LaTeX** the analyst wrote, fills the specification, and prints the **reference Python MAYA lifts from the expression tree**. | That MAYA reads LaTeX and Python into the same tree; that `remitted` is not an input; a runnable statement of the specification nobody typed twice. |
| `check_conformance.py` | Uploads the desk's implementation; the six-rung ladder **and** the differential test run together. Re-runs the test on the pinned tape's own values, then does the same for a buggy implementation, then puts the correct one back. | **The heart of the study.** A valid-but-wrong implementation passes every rung, agrees with the specification *nowhere*, and cannot be submitted. The domain the test used is stated, because agreement over an invented domain is worth less than it looks. |
| `get_training_warrant.py` | Draws a warrant that fits nothing, registers the servicing fee as an approved parameter set, and has MAYA score the model blind against what the servicer actually remitted. | A model with no fit still owes a signed constant; an accuracy statement measured against an independent record. |
| `get_execution_warrant.py` | Draws an execution warrant with a staleness covenant and an output range, gets a second model manager's approval, takes it live, then reports a batch on a 75-day-old tape. | A cashflow model is exactly as right as its tape, so the covenant that matters is about whether the tape arrived. |
| `show_estate.py` | Creates nothing. Reads back the catalog, the artifact report *including the conformance result and the artifact hash it was run against*, the reconciliation attempts, the audit chain and the lineage. | That the evidence is discoverable afterwards, and tied to the exact code it was gathered about. |
| `study.py` | No MAYA calls: names, definitions, the LaTeX, both implementations, the specification document, the cast. Imported by every step. | The declarations that would live under source control at a bank. |
| `run.py` | All seven steps in order against a MAYA built from nothing. About twelve seconds. | The unattended pass. |

```bash
.venv/bin/python case_studies/02-mortgage-cashflow/run.py          # the whole story
.venv/bin/python case_studies/02-mortgage-cashflow/setup_features.py --reset   # or step by step
```

---

## 1. The business problem, and why it is a different problem from case study 1

A bank holds a pool of fixed-rate, level-payment mortgages. Every month it needs to know
what cash those loans will remit: for liquidity planning, for asset-liability management,
and to reconcile against what the servicer says it collected.

There is nothing to estimate. A level-payment mortgage's monthly payment is contractual
arithmetic — the annuity that amortises the balance over the payments remaining. Case
study 1 fitted a model to data and the interesting question was *"is the fit sound?"*.
Here there is no fit, and the interesting question becomes:

> **Is the code the desk runs the same thing as the mathematics the committee approved?**

That question is not answered by testing the code, because the commonest implementation
bugs are perfectly valid Python that passes every test written from the same
misunderstanding. It is answered by having two independent implementations of the same
stated mathematics and comparing them — which is what MAYA does here.

## 2. The data

| File | Rows | Size | Grain | Arrives | What it is |
| --- | --- | --- | --- | --- | --- |
| `data/loan_tape.csv` | 8,820 | 0.7 MB | loan × month end | month end **+ 2 days** | Balance, coupon, original term, age, original balance. What the model reads. |
| `data/servicer_report.csv` | 8,820 | 0.4 MB | loan × month end | month end **+ 15 days** | What the servicer actually collected and remitted, net of its fee. What the model is *measured against*. |

420 loans of 15 to 30 years at coupons between roughly 2% and 9.5%, over 21 months
(2024-01 to 2025-09), £104m outstanding at the end of the window.

The tape is exact level-payment amortisation, disturbed the way a real book is: about one
loan in fifty makes a partial prepayment in a month, so the balance falls faster than the
schedule; and about one remittance in eighty is short, because a borrower paid late.
Rounding to the penny does the rest.

That matters. A model that matched its benchmark to the penny would mean the benchmark was
somehow being read as an input. Here the two agree closely and never exactly, and §6
measures the difference.

## 3. The model, in the notation it was written in

```
i       = rate / 12
n       = term - age
annuity = (1 - (1 + i)^(-n)) / i
payment = balance / annuity
netCash = payment - balance · fee / 12
```

registered from the LaTeX itself:

```latex
i = \frac{rate}{12}
n = term - age
annuity = \frac{1 - (1 + i)^{-n}}{i}
payment = \frac{balance}{annuity}
netCash = payment - balance \cdot \frac{fee}{12}
```

Written properly: with balance $B$, annual coupon $r$, original term $m$ months and age
$a$ months, let $i = r/12$ and $n = m - a$. Then

$$
\alpha = \frac{1 - (1+i)^{-n}}{i}, \qquad P = \frac{B}{\alpha}, \qquad
\text{netCash} = P - \frac{Bf}{12}
$$

where $f$ is the annual servicing fee. The interest and principal components, $Bi$ and
$P - Bi$, follow from the same quantities.

MAYA parses LaTeX and Python into the *same* expression tree, so the notation is a
presentation choice, not a semantic one. For a formula this shape the LaTeX is the
documentation, which is why the study registers it that way.

The input contract MAYA derives is `age, balance, rate, term`. Note what is **not** in it:
`remitted`. The benchmark is a member of the feature set and not an input of the model, so
the model cannot see what it is graded against. That is a property of the contract, not a
convention the script follows.

### `n = term - age`, and why it is the whole point

The single most common error in mortgage systems is amortising over the **original** term
instead of the term **remaining**. It is one expression. It is invisible on a new loan and
wrong on every seasoned one. And it will pass a unit test written by the same person who
made the mistake, because the expected values in that test were computed the same wrong
way.

## 4. MAYA's own reference implementation

Because the model is an expression tree, MAYA can lift it back into runnable Python:

```python
def predict(X, params):
    v_age = np.asarray(X["age"], dtype=float)
    v_balance = np.asarray(X["balance"], dtype=float)
    v_fee = params["fee"]
    v_rate = np.asarray(X["rate"], dtype=float)
    v_term = np.asarray(X["term"], dtype=float)
    v_i = v_rate / 12.0
    v_n = v_term - v_age
    v_annuity = (1.0 - (1.0 + v_i) ** (-v_n)) / v_i
    v_payment = v_balance / v_annuity
    return {"netCash": v_payment - v_balance * (v_fee / 12.0)}
```

Nobody typed that twice. It is generated from the same tree the LaTeX produced, which
means it cannot drift from the document — and it is the thing the desk's code is compared
against.

## 5. The two checks on the desk's code

The desk's implementation is its own: vectorised numpy, its own variable names, its own
order of operations, written to MAYA's model interface (a class `Model` with
`fit(X, y, ctx)` and `predict(X, params, ctx)`). Its `fit` returns nothing and says so in a
docstring, because a contractual cashflow has nothing to estimate.

### The ladder (automatic, on upload)

| Rung | Result on this artifact |
| --- | --- |
| 1. parse | `ruff check` ran: clean |
| 2. entry point | `Model` implements `fit(X, y, ctx)` and `predict(X, params, ctx)` |
| 3. import allowlist | every import is on the allowlist |
| 4. static ban | no filesystem, process, network or dynamic-code use |
| 5. smoke run | succeeded in 0.14s under sandbox tier `strong` |
| 6. determinism | two runs produced identical output |

Every rung is reported, and rungs after a failure are recorded as *not run* rather than
silently omitted — a report never implies a check it did not perform.

The ladder asks whether the artifact parses, imports nothing forbidden and runs. **That is
a different question from whether it computes the model.**

### The differential test (with the ladder, and a gate)

The differential test runs **as part of the upload**, not when somebody remembers to ask
for it. MAYA draws 2,000 input rows, runs the artifact in the sandbox over them, and
compares the result against its own evaluation of the documented mathematics to a relative
tolerance of $10^{-9}$.

The domain matters as much as the count, and the report says which domain was used. By
default the inputs are drawn from the unit interval — fine for catching a gross
disagreement, useless for a mortgage, because a 1.2-month term at a 100% coupon is not a
loan and a bug that only shows on a seasoned one hides there. So the study re-runs the test
naming the pinned tape, and the inputs are resampled from its own values:

```
domain: resampled from maya://featureset/mortgage_alm/loan_month#recon2509/2025-09-30
        (8,820 rows)
```

| Code | Agreement |
| --- | --- |
| The desk's correct implementation | **2,000 of 2,000** |
| The same, amortising over the original term | **0 of 2,000** |

with counterexamples in the units of the problem:

```
at age=209, balance=427,614, rate=0.05119, term=240:
    specification -3,061.73, code -14,967.00
```

and the version cannot be submitted:

```
NotApproved: Blocked by check(s): code_matches_specification —
  the code disagrees with the specification on 2000 of 2000 sampled inputs;
  e.g. age=209, balance=427614, rate=0.05119, term=240 →
  specification -3061.73, code -14967
```

Two details worth pointing at:

* **The counterexamples show negative cash.** MAYA resamples each input independently, so
  it tests combinations that never co-occur in the book — here an age drawn from one loan
  against a term from another, which can make the payments remaining negative. That is
  deliberate for a differential test: two implementations of the same stated mathematics
  must agree *everywhere*, including where the inputs are absurd. It is not a claim about
  the portfolio.
* **A result belongs to the code it tested.** The outcome is recorded against the artifact
  hash, so a clean run is never inherited by whatever is uploaded next: attach different
  code and the check refuses with *"the code has not been tested against the specification
  since it changed"* until a comparison has been made against the artifact that is actually
  there. Uploading runs one, which is why the study's last upload can be submitted
  straight away.

## 6. A warrant that fits nothing, and a constant that still needs a signature

There is nothing to learn, so `fit` is never called. MAYA still requires a training warrant
and an approved parameter set, and that is the right requirement: the servicing fee in
production should be a figure somebody signed for. It is registered at 25 basis points a
year with its provenance in the metrics — *"servicing agreement clause 7.2"* — quoting the
data checksum, because "which rows was this registered against" is still worth being able
to answer. It is then submitted and approved by a model manager.

The leakage certificate comes back `certified_with_exceptions`: the servicer's report
arrives a fortnight after the month it covers, so its knowledge time is later than its
event date by construction. The exception is written down, and it names what makes it
sound — the benchmark is never an input, and the model's contract proves it.

Then the reconciliation. MAYA scores the escrowed partition itself, against the servicer's
remittance:

| | |
| --- | --- |
| Loan-months scored | 1,312 |
| RMSE per loan-month | £66.43 |
| MAE per loan-month | £5.92 |

Read the gap between those two figures, because it is the interesting result. The median
loan reconciles to pennies — the mean absolute error is about six pounds on payments
averaging two thousand. The RMSE is eleven times larger, because it is dominated by the
small share of loan-months with a partial prepayment or a late payment. Neither is
something this model claims to predict; the *Scope and Limitations* section says so, and
the *Known Weaknesses* section says that for a book with meaningful arrears the residual
will be dominated by collection rather than arithmetic. The reconciliation is that
statement, measured.

## 7. Live, and a covenant about the tape

```python
covenants = [
    {"kind": "staleness_days", "attr": "balance", "max": 40},
    {"kind": "output_range", "min": 0.0, "max": 20_000.0},
]
```

A scheduled cashflow model is exactly as right as the tape's age column. A stale tape, a
capitalised arrears balance or a loan that has silently converted to interest-only all
produce a confident and wrong number, and the model cannot tell. So the covenant that
matters here is not about the model's behaviour at all — it is about whether the tape
arrived. Report a batch computed on a 75-day-old tape and:

```
WarrantSuspended: Warrant suspended: 'balance' is 75 days stale.
  Contact alm.analytics@example.com.
```

The execution warrant is submitted by one model manager and approved by another, and a
19 kB typeset PDF manifest states what went live.

## 8. What to point at when demonstrating this

1. **§3 and §4** — the model was registered in LaTeX and MAYA generated the reference
   implementation from it. There is no second transcription to go stale.
2. **§5, the buggy implementation** — valid Python, passes every rung of the ladder,
   disagrees with its own specification on every row, and cannot be submitted. This is the
   thing a model risk function actually worries about, and it is checked automatically.
3. **§5, the domain and the hash** — the test says which values it explored, and its
   result is tied to the artifact it was gathered about. Both are the difference between
   evidence and a green tick.
4. **§6, the RMSE against the MAE** — a model that is right about what it claims and
   visibly silent about what it does not.
5. **§7** — the covenant guards the input, because that is where this model fails.

## 9. What this study deliberately does not do

It is a *scheduled* cashflow model. It does not forecast prepayment, default, delinquency
or recovery, and it is not a valuation model: a price needs a prepayment model and a
discount curve, each a separate model with its own warrant. Interest-only periods, rate
resets, payment holidays and capitalised arrears are out of scope and are not detected by
the model itself.

Those are the next case studies, and the scope section says so rather than leaving a
reader to find out.
