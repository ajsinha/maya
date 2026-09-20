# Case study 1 — a retail credit PD scorecard

**Domain:** banking, retail credit risk · **Model type:** fitted, parametric (logistic
regression) · **What it exercises:** bitemporal features, as-of alignment across
frequencies, point-in-time pinning, a leakage certificate that refuses, a fit tied to its
data by checksum, blind holdout scoring, and an execution warrant that suspends itself.

```
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py            # ~13 seconds
.venv/bin/python case_studies/01-retail-credit-pd-scorecard/run.py --keep      # and keep it to browse
```

---

## 1. The business problem

A bank holds a book of revolving unsecured retail accounts — credit cards and overdrafts.
For IFRS 9 it must decide, every month and for every account, the probability that the
account will default in the next twelve months. That number drives stage allocation, and
through it the expected credit loss provision, which is a line in the published accounts.
It is therefore a number a regulator will ask about, and the question will not be "is the
model good" but "what exactly produced this figure, on what data, approved by whom, and
can you show me it again".

That last question is the one this case study is really about. The statistics here are
deliberately ordinary: a four-driver logistic scorecard, the instrument most retail books
actually use, because it can be explained to a credit committee and challenged line by
line. What is not ordinary is that every artefact the answer depends on is a governed,
content-addressed object, and that the platform refuses to let the model go live until the
awkward questions have written answers.

## 2. The data, and why it is shaped the way it is

Three feeds, committed as CSV in `data/` and written by `make_data.py`. Each is deliberately
imperfect in a way that real feeds are, because every one of those imperfections is where
a model quietly goes wrong.

| File | Rows | Grain | Arrives | Why it matters |
| --- | --- | --- | --- | --- |
| `servicing_monthly.csv` | 36,000 | account × month end | month end **+ 5 days** | The values are *known* after the dates they are about. A backtest that assembles a portfolio on the last day of the month is using figures nobody had. |
| `bureau_file.csv` | 12,000 | account × quarter end | quarter end **+ 15 days** | A different frequency and a longer lag. At most observation months the best available bureau score is up to four months stale. |
| `default_outcome.csv` | 36,000 | account × month end | month end **+ 366 days** | The target. Whether the account defaulted over the *following* twelve months cannot be known until those twelve months have passed. |

1,200 accounts over thirty months, 2023-01 to 2025-06. The book's realised twelve-month
default rate is **26.6%** — high for a real card book, and chosen so that the holdout
partition has enough events for the metrics to mean something at this size.

Underneath, each borrower has a latent quality that the model never sees. Utilisation,
debt-to-income and the delinquency count are noisy functions of it, the bureau score is a
noisy measurement of it, and default is drawn from a logistic hazard in those quantities.
So a scorecard fitted on the four observable drivers can find something real, and cannot
find it perfectly — which is what makes the validation section of the model's
specification worth reading rather than worth skipping.

### Bitemporality, concretely

MAYA gives every row two dates: the **event time** it is about, and the **knowledge time**
at which MAYA could first have known it. The `kt` column in each CSV is the knowledge
time, declared in the feature definition as `source.knowledge_time_column`. Everything
downstream follows from that one declaration:

* A pin taken *as of* a knowledge time contains only rows knowable by then. Ask for the
  panel as it stood in June 2025 and you get June 2025's answer, not today's.
* A vendor restatement is a new knowledge-time row, not an overwrite, so the earlier
  answer stays reproducible.
* MAYA can *compute* whether a training set used a value from its own future, which is
  what §4 is about.

## 3. The features

Three feature definitions, written out in `run.py` rather than inferred, because the
definition is the governed object — the index, the types, where knowledge time comes from,
and what must be true of the values. The servicing feature carries three quality checks
(utilisation not null and within [0, 1], debt-to-income within [0, 1]); the bureau feature
checks its score is a real FICO-range number.

They are created and submitted by **dana**, a feature designer, and approved by **mick**, a
feature manager. The script tries to have dana approve her own work, and MAYA refuses:

```
PermissionDenied: You may not approve this object:
  role ceiling: no 'A' on feature in roles feature_designer
```

That is not a demo contrivance. It is the role ceiling from §11: a feature designer's
ceiling on features is create-read-write-submit, and no grant can raise it to approve.
Four-eyes is a property of the capability matrix, not a convention people follow.

## 4. The panel: aligning three frequencies without lying

The feature set `pd_panel` composes all three features on the index `(date, account)` with

```python
"alignment": {"mode": "asof", "tolerance_days": 100}
```

As-of alignment carries the last *known* bureau score forward to each observation month.
It does not resample, interpolate or average, because the bank did not have a monthly
bureau score and pretending otherwise would put information in the panel that never
existed. The hundred-day tolerance says how stale a score may be before MAYA declines to
carry it at all.

This has a visible consequence that the study prints rather than hides: the earliest
observation months of the panel have **no** bureau score, because no file had been
delivered yet. MAYA leaves the gap as a gap. The fit therefore uses complete cases and
says what that cost — **2,055 of 30,705 rows**. A platform that had forward-filled from
nothing, or imputed the mean, would have produced a fit with no warning attached and a
coefficient contaminated by an invention. The model's *Known Weaknesses* section now says
so in writing, where a reviewer will read it.

The panel is then **pinned**: `as_of = 2025-06-30`, `as_of_known = 2026-09-01`, cascading
so the member features are pinned too. A pin is immutable, content-hashed and stored in
MAYA's Delta lake. Its reference is

```
maya://featureset/retail_credit/pd_panel#fit2025h1/2025-06-30
```

That string, and not "the panel", is what everything downstream is drawn on.

## 5. The model as mathematics, not code

The scorecard is registered as a formula, which MAYA parses into an expression tree:

```
b = (bureau - 680) / 60
z = intercept + wUtil*utilisation + wDti*dti + wDelinq*delinquencies + wBureau*b
pd12m = 1 / (1 + exp(-z))
```

Written properly, that is

$$
b = \frac{\text{score} - 680}{60}, \qquad
z = \beta_0 + \beta_u u + \beta_d d + \beta_n n + \beta_b b, \qquad
\mathrm{PD}_{12} = \frac{1}{1 + e^{-z}}
$$

Three things follow from holding it as an expression rather than as a pickled object:

1. **MAYA knows the model's input contract** — `bureau, delinquencies, dti, utilisation` —
   and can check a feature set against it *before* anyone trains anything. The study prints
   the contract and the mapping MAYA resolved.
2. **MAYA can evaluate it** for blind holdout scoring without executing anyone's Python,
   which is why scoring can happen on data the developer never sees (ADR-007).
3. **The centring of the bureau score is part of the model.** `(score − 680)/60` is stated
   in the governed object, so the coefficient's units are unambiguous and a second
   implementation cannot quietly choose a different centre. The fitting script reads that
   same statement — `design_matrix()` exists precisely so the fit and the scoring cannot
   disagree.

The **specification document** is a real one: the nine sections §8.3 requires, with the
scope limits, the linearity assumption and its failure in the tails, the calibration
method, and the weaknesses actually written out. The script first tries to submit the model
*without* it, and MAYA refuses by naming every missing section:

```
NotApproved: Blocked by check(s): spec_document_complete — required sections empty:
  Purpose, Scope and Limitations, Assumptions, Calibration Methodology,
  Validation Evidence, Known Weaknesses, Change Log
```

## 6. The training warrant, and the refusal that matters most

A **training warrant** is MAYA's record of one attempt to fit one model version to one
pinned data set: what data, what target, what split, what seed, who drew it. Drawing one
produces two pieces of evidence immediately.

The **contract report** confirms the panel exposes every input the model declares, and
records the mapping.

The **leakage certificate** applies one rule: *every row's knowledge time must be no later
than its event date (plus a declared lag)*. Drawn naively, the certificate comes back:

```
status:          refused
violating rows:  36,000
```

All of them. This is correct, and it is the most instructive moment in the study. The
panel's knowledge time per row is the latest of its members', and one member — the
twelve-month default flag — is by construction known a year after the month it describes.
So *every* row of this panel is, by MAYA's rule, a row that could not have been assembled
at its event date. Submitting the warrant is refused outright:

```
NotApproved: Blocked by check(s): leakage_certified —
  leakage certificate: refused; 36000 violating row(s)
```

The wrong response is to widen the rule. The right response — and the one MAYA forces — is
to say why this particular exception is sound, in a field that becomes part of the warrant:

> The target `default_12m` is a forward-looking outcome: whether the account defaulted in
> the twelve months after the observation month. Its knowledge time is necessarily later
> than its event date, and it is never an input at scoring time — the scorecard takes the
> four drivers only, all of which are known at the observation month. The exception covers
> the target column alone; any driver known late would be leakage.

With the justification recorded, the certificate reads `certified_with_exceptions`, the
warrant proceeds, and a reviewer six months later can read the exception and the reason for
it side by side. Note what has *not* happened: nobody turned the check off, and the
distinction between "the target is forward-looking" and "a driver leaked" is now a written
claim somebody signed.

## 7. Fitting, and tying the fit to its data

`warrant.data()` hands over the training and validation partitions — **30,705 rows** — and
nothing else. The test partition is escrowed by MAYA; `ds.X` excludes the target, and the
study asserts as much (`target among the inputs: False`).

The fit is iteratively reweighted least squares on the Bernoulli log-likelihood, in numpy,
in twelve lines. It is deliberately unremarkable: this study is about the governance around
the fit, not the optimiser. On the run recorded here:

| | intercept | wUtil | wDti | wDelinq | wBureau |
| --- | --- | --- | --- | --- | --- |
| fitted | −3.917 | +3.704 | +2.602 | +0.547 | −0.095 |

Every sign is the right way round: higher utilisation, higher debt-to-income and more
delinquencies raise the probability of default; a better bureau score lowers it. AUC is
**0.758** on training and **0.760** on validation — close together, which is what an
unpenalised four-driver linear scorecard on 30,000 rows should look like, and a useful
sanity check that nothing has leaked into the fit.

Uploading the parameters is where MAYA closes the loop. The script uploads the same
coefficients twice:

* quoting the **wrong** data checksum → MAYA flags the set `unverified_data`, and approval
  is refused: *"the checksum does not match any download MAYA issued; approve only with an
  explicit justification"*;
* quoting the **right** one → `verified_data=True`, and it can be approved.

This is the answer to "which data produced these numbers". Not a convention, not a
changelog entry: the parameter set carries the checksum of the exact bytes MAYA handed
over, and a set that cannot prove its provenance is marked as such forever.

## 8. Blind scoring, and what the holdout can and cannot tell you

The escrowed test partition — **5,295 rows** — is scored by MAYA, not by the developer.
MAYA evaluates the expression tree against rows the developer has never seen and returns
metrics only, never rows. Every attempt is counted on the warrant, so scoring the holdout
repeatedly until it flatters you is visible.

The figure here is **RMSE 0.3989**. Read it correctly: on a zero-one target the mean
squared error *is* the Brier score, so 0.3989 is the root Brier score — a statement about
**calibration** on unseen rows, not about discrimination. The AUC figures above are
discrimination, and they were computed on data the developer could see. Keeping those two
claims apart is the sort of thing a model risk function exists to insist on, and the
specification's *Validation Evidence* section says exactly this.

The warrant is then submitted, approved and **sealed**. A sealed warrant is immutable: the
data reference, the certificate, the exception, the parameter set and its checksum are
fixed together.

## 9. Going live, and coming back down

An **execution warrant** says where the model may run, who is accountable, and what would
make it stop:

```python
environments = ["dev", "prod"]
contact = "retail.credit.risk@example.com"
covenants = [
    {"kind": "input_null_rate", "attr": "bureau", "max": 0.05},
    {"kind": "input_psi", "attr": "utilisation", "max": 0.25},
]
```

It is submitted by **mgr**, a model manager, and approved by **lara**, a second model
manager — not by mgr, because the person who submits is not the person who approves. That
is why the study seeds a second holder of the role at all.

The PSI covenant is declared with no baseline, so MAYA takes the baseline from *this
warrant's own training data* and fixes it at creation. "Drift" therefore means drift away
from the distribution the model was actually fitted on, rather than away from whatever
last month happened to look like.

The script then reports a production batch whose bureau score is 31% null. The covenant
breaks, the warrant **suspends itself**, and the next attempt to obtain the model refuses
with the number and the person to call:

```
WarrantSuspended: Warrant suspended: null rate of 'bureau' 0.310 > 0.05.
  Contact retail.credit.risk@example.com.
```

An administrator reinstates it with a reason — *"bureau file arrived late; the feed is
confirmed restored"* — and it is live again. The reason is part of the record.

## 10. What the estate holds afterwards

| | |
| --- | --- |
| Features / feature sets / models | 3 / 1 / 1, all approved |
| Audit chain | 68 entries, hash-chained, verified unbroken |
| Custody events on the training warrant | 8 |
| Lineage around the pinned panel | 14 nodes, 17 edges |

The audit chain is append-only and each entry carries the hash of the previous one, so
tampering is detectable rather than merely discouraged. The lineage graph is what an
auditor actually wants: from the panel version, edges to the three member features, to the
pins, to the warrant, to the parameter set, to the execution warrant.

## 11. What to point at when demonstrating this

1. **The refusal in §3** — four-eyes is in the capability matrix, not in a process document.
2. **The 2,055 excluded rows in §4** — MAYA showed the gap instead of filling it, and the
   decision is in the open with a number attached.
3. **The leakage certificate in §6** — the platform found the awkward question and would
   not proceed until it had a written answer. Then read the answer.
4. **The two parameter uploads in §7** — "which data produced these numbers" has a
   cryptographic answer.
5. **The suspension in §9** — the model took itself out of service and named the problem
   and the owner.

Run it with `--keep` and the script prints how to start the web UI on exactly the estate it
just built, so the same story can be walked through on screen: the catalog, the pin preview,
the warrant with its certificate and exception, the lineage canvas, and the audit log.

## Files

| | |
| --- | --- |
| `run.py` | The study. Every MAYA interaction goes through `maya.sdk.Client` as a named user. |
| `make_data.py` | Writes the three CSVs in `data/`, with the recipe in its docstring. |
| `data/*.csv` | The three feeds, committed, ~4 MB in total. |
