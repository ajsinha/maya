# Case study 10 — CAPM, then Fama–French, as two versions of one model

**Domain:** asset management, equity research and performance attribution · **Model type:**
simple linear regression, then multiple linear regression, as **versions 1 and 2 of one
model** · **What it exercises:** `models.new_draft`, `models.diff` — MAYA's *semantic* diff
of two expression trees — an input contract that grows between versions, a parameter set
that belongs to one version and cannot be lent to the other, two warrants that escrow the
*same* holdout rows so the comparison is measured, and the §8.6 maturity ladder: deprecated
with a successor, every dependent warrant owner warned, and then retired.

The statistics are deliberately the two simplest regressions in finance. **The study is not
about the statistics. It is about MAYA's model versioning,** which no other study in the
library exercises.

## The scripts, and what each one does

Nine scripts, in this order. They share one MAYA at `case_studies/runs/factor_models/`,
which the first builds and the rest reopen, so **each runs on its own, in its own process** —
and between any two of them you can open the web UI and show what the last one created.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes two feeds to `data/` (already committed; run it only to regenerate). No MAYA. | The recipe: a five-factor structure with **no alpha in it at all**, over a universe tilted small and value, in a window where size and value both earned money. |
| `setup_features.py` | Declares and ingests two features: the equity tape on `(date, stock)`, the factor library on **`date` alone**. Measures each feed's knowledge-time lag from the file. | A close known that evening; a factor library known **4.5 to 34.5 days** later. **dana refused when she tries to approve her own feature.** |
| `setup_featureset.py` | Composes `factor_panel` from both and pins it; also builds the narrow `capm_panel`. | MAYA broadcasting the 504-row factor feed across the cross-section — *one distinct market factor value per date*. **Pinning an unapproved version refused.** |
| `setup_model.py` | Registers version 1 — two parameters, one feature — and cannot submit it without a document. | That MAYA's ceremony is not proportional to a model's complexity. **Submission refused while the specification is empty.** The maturity on creation: `experimental`. |
| `get_training_warrant.py` | Draws the warrant naively, then again with the publication lag explained. | A leakage certificate refusing **all 15,120 rows** — and refusing them on the **drivers**, which is a much harder exception than case study 1's. |
| `fit_parameters.py` | Fits by OLS on the training partition, reports **two standard errors per coefficient**, uploads twice (wrong checksum, then right), and has MAYA blind-score the holdout twice. | An alpha of **+14.83% annualised** on a universe whose true alpha is zero. **Parameters that cannot prove their data refused approval.** A holdout figure with a benchmark. |
| `get_execution_warrant.py` | Takes version 1 live in `dev` and `uat` — and nowhere else. | **mgr refused when he approves the warrant he submitted.** **The bundle refused in `prod`**, which is where the leakage exception's promise stops being prose. |
| `add_second_version.py` | **The heart of the study.** Mints version 2, prints the semantic diff, shows the contract growing, draws version 2's own warrant on the same escrowed rows, and fits it. | **Version 2 refused on version 1's document.** **Refused on the panel version 1 was happy with.** **Refused version 1's parameter set, twice over.** And alpha collapsing to nothing. |
| `deprecate_first_version.py` | Deprecates version 1 with version 2 as its successor, reads the notifications MAYA sent, then retires it while its execution warrant is still live. | **Deprecation without a successor refused.** **A new warrant on a deprecated version refused.** And one finding MAYA does *not* refuse — §9 below. |
| `show_estate.py` | Creates nothing. Reads both versions, the diff, the two fits side by side, the lineage and the audit chain. | That all of it is discoverable afterwards by somebody who was not in the room. |
| `study.py` | No MAYA calls: names, definitions, **both** formulas, **both** documents, the fitting mathematics, the cast. | The declarations that would live under source control. |
| `run.py` | All nine steps against a MAYA built from nothing. About eleven seconds. | The unattended pass. |

```bash
.venv/bin/python case_studies/10-factor-models/run.py                          # the whole story
.venv/bin/python case_studies/10-factor-models/setup_features.py --reset       # or step by step
```

`--reset` deletes this study's MAYA and starts again from nothing; `--quiet` prints the
results without the narration.

---

## 1. The business problem

An equity research desk holds a universe of thirty stocks and has to explain, every month,
where last month's return came from. Not predict it — *explain* it. The performance
attribution that goes to the investment committee splits each stock's realised excess
return into the part its exposures account for and the part they do not, and the second
part is the number the meeting is actually about, because the second part is what gets
called skill.

The simplest instrument for that job is a regression of the stock's excess return on the
market's, and the coefficient on the market is the beta every finance course starts with:

$$R^e_{it} = \alpha + \beta M_t + \varepsilon_{it}$$

Two parameters. Nothing in this library is fitted with fewer, and that is why it is here: it
gets the same specification document, the same warrant, the same approved parameter set
and the same execution warrant as case study 5's nine-parameter volatility surface.
**MAYA's ceremony is not proportional to the model's complexity, because the consequences
are not either.** An alpha nobody challenged reaches the investment committee's report
exactly as fast whether it came from two coefficients or two hundred.

And then somebody asks the obvious question — *is that alpha really skill, or is it a size
tilt?* — and the answer is a second model. Not a new model: a second **version** of this
one, which is a different thing, and the difference is the whole study.

## 2. The data, and two very different lags

| File | Rows | Index | Known | What it is |
| --- | --- | --- | --- | --- |
| `data/equity_daily.csv` | 15,120 | `(date, stock)` | the same **evening**, 21:00 UTC | Thirty stocks' daily total and excess return, over 504 trading days from 2023-01-02. |
| `data/factor_daily.csv` | **504** | `(date)` | the **4th of the following month** | The market, size, value, profitability and investment factor returns, and the risk-free rate. One row a day. |

The study prints both lags, measured from the files rather than asserted:

```
equity_daily known after:          21 to 21 hours
factor_daily known after:          4.5 to 34.5 days
```

### Why the factor feed has no stock dimension

A factor return is a property of the market, not of any stock. Writing it into every row
would mean storing 15,120 copies of 504 numbers, and a copy can be wrong in one row and
right in the next. So the factor feature is indexed on `date` alone, MAYA broadcasts it
across the cross-section of each day, and `setup_featureset.py` prints the proof:

```
distinct market factor values within one date: 1
```

Case study 3 does the same thing with a mortgage rate. Here it matters twice as much,
because *five* of the panel's six attributes come from that one 504-row feed.

### What generated the returns

`make_data.py` states the recipe. Each stock has five true loadings and

$$R^e_{it} = b_i M_t + s_i \mathrm{SMB}_t + h_i \mathrm{HML}_t + r_i \mathrm{RMW}_t + c_i \mathrm{CMA}_t + \varepsilon_{it}$$

with **every stock's true alpha exactly zero**. Two things are set exactly rather than
drawn, for the same reason case study 3 draws its rate path down and then up instead of
sampling it — what the window has to contain is not random:

* each factor's realised mean over the 504 days is the stated premium, to the last decimal
  place: **market +7.56%, size +15.12%, value +10.08%, profitability +2.52%, investment
  +1.26%**, annualised at 252 days;
* the equal-weighted mean of the thirty loadings is the stated loading exactly — **beta
  1.00, size +0.60, value +0.40, profitability +0.05, investment 0.00.** A pooled
  regression over the universe estimates that mean, so stating it exactly is what makes
  §5's *fitted against generated* table a comparison rather than a guess.

The universe is therefore tilted small and value, in a window where small and value both
paid. A CAPM regression on it *must* report a positive alpha, and that alpha is arithmetic,
not skill. The average investment loading is zero on purpose, so that one of version 2's
five coefficients has nothing real behind it and the study has to say so.

## 3. The leakage exception, and why it is the hard kind

MAYA's rule is: *no row may use a value MAYA could not have known by its event date (plus a
declared lag)*. Drawn naively, version 1's warrant comes back

```
rule:             every row's knowledge time ≤ its event date + 1 day(s)
rows examined:    15,120
violating rows:   15,120
status:           refused
first example:    2023-01-02 SYN01, knowable 2023-02-04 12:00:00+00:00
```

and the warrant cannot be submitted:

```
NotApproved: Blocked by check(s): leakage_certified —
  leakage certificate: refused; 15120 violating row(s)
```

**This is a different refusal from case study 1's, and a much less comfortable one.** There,
the *target* was a forward-looking outcome and every driver was known at the observation
date, so the written exception could honestly say "the exception covers the target column
alone; any driver known late would be leakage". Here the **drivers themselves** are known a
month late. By case study 1's own standard, this is leakage.

There is exactly one honest defence, and MAYA makes the warrant carry it in writing:

> This is an attribution model, not a forecast, and both sides of the regression describe
> the same day. The factor library assembles a month's factor returns from the cross-section
> after that month has closed and publishes them on the fourth of the following month, so
> every row of this panel carries a knowledge time up to thirty-four days after its event
> date. The exception therefore covers the drivers as well as the target, which is only
> sound because the model's output is never used to take a position: it decomposes a return
> that has already happened. The execution warrant permits dev and uat only, the
> specification's Scope and Limitations section forbids forecasting use, and any use of this
> model to predict a return not yet realised would be leakage of exactly the kind this
> certificate exists to find.

That claim is then made a second time, in a field rather than in prose. The execution
warrant's environments are `["dev", "uat"]`, and

```
PermissionDenied: Warrant is not valid in 'prod'
```

Every other study in this library takes its model to production. This one is not allowed
to, and the reason it is not allowed to is a sentence somebody wrote on a certificate.

## 4. Version 1's fit, and an alpha that is not skill

Ordinary least squares by the normal equations, on the 10,654 training rows, in numpy.
Each coefficient is reported with **two** standard errors:

```
name     estimate         se   clustered se      t   clustered t    generated
alpha    +0.000589   0.000143       0.000235   +4.11         +2.51      +0.0000
beta     +1.055686   0.014059       0.023282  +75.09        +45.34      +1.0000
```

| | |
| --- | --- |
| R² train / validation | 0.3461 / 0.3472 |
| alpha, annualised at 252 days | **+14.83%** |
| beta against the generating value | **+1.0557 against 1.0000** |

Three things to read here.

**The alpha is arithmetic.** The process that generated these returns gave every stock an
alpha of exactly zero. This +14.83% is the size and value premium the model has no term
for, arriving in the only place it can. A model risk function that took it at face value
would be reporting a tilt as a talent.

**The beta is biased too**, by +0.0557 — five and a half per cent. Omitting a factor does
not only move the intercept: any sample correlation between the omitted factors and the
market is absorbed into the market slope. The *Known Weaknesses* section says so, and the
study measures it rather than mentioning it.

**The two standard errors differ, and the gap is the diagnostic.** Thirty stocks share one
day's factor realisation, so the residuals within a day are correlated and a classical
standard error assumes they are not. Clustering by date gives alpha a *t* of **+2.51**
against the classical **+4.11** — still significant, but a good deal less so. The gap is
large *because the model has omitted a common factor*, and it is worth watching what
happens to it in §6.

### The holdout figure, with something to compare it against

MAYA scores the escrowed 2,193 rows itself, evaluating the expression tree against rows the
developer has never seen. A root mean squared error on daily returns means nothing alone,
so the developer asks MAYA for a second score on the same rows with `alpha` and `beta` both
set to zero — a model that predicts no excess return for anybody. Both attempts are counted
on the warrant.

| | holdout RMSE |
| --- | --- |
| Version 1, on 2,193 escrowed rows | **0.014478** |
| Predicting zero for everybody | 0.018062 |

a **19.8%** reduction. That is a statement about rows the developer never saw, and it is not
the same statement as the R² above, which was computed on rows the developer could see. The
specification's *Validation Evidence* section keeps the two apart, in writing, because a
review that conflates them will accept an overfitted model.

## 5. Version 2: a second version, and everything it costs

Four published factors are added. `models.new_draft` mints **version 2 of the same model**,
not a new model, and MAYA then makes every consequence of that explicit.

### 5.1 A document is bound to the mathematics it describes

Version 2 inherits version 1's 5,039-character document and its maturity. The moment the
formula moves under it:

```
document marked for re-review:  True
reason:                         the formula IR changed under the document
```

and submission is refused:

```
NotApproved: Blocked by check(s): spec_document_complete —
  required sections empty: (document marked for re-review after an IR change — save it)
```

Nothing was deleted and nothing was hidden. The document is still there, in full; MAYA's
objection is that the mathematics moved after it was written (§8.5). A platform that let
version 2 inherit version 1's *Mathematical Formulation* would be shipping a document that
describes a model nobody is running — which is the commonest documentation failure in model
risk, and the one nobody notices until an examiner reads both.

### 5.2 The semantic diff

`models.diff(ref, 1, 2)` returns statements about the mathematics, not about the text:

```
• parameter 'bCma' added
• parameter 'bHml' added
• parameter 'bRmw' added
• parameter 'bSmb' added
• feature 'cma' added
• feature 'hml' added
• feature 'rmw' added
• feature 'smb' added
• output equation changed: $\alpha + \beta\,\mathit{mktExcess}$ →
  $\alpha + \beta\,\mathit{mktExcess} + \mathit{bSmb}\,\mathit{smb} + \mathit{bHml}\,\mathit{hml}
   + \mathit{bRmw}\,\mathit{rmw} + \mathit{bCma}\,\mathit{cma}$
  (now uses bCma, bHml, bRmw, bSmb, cma, hml, rmw, smb)
code artifact changed:  False
document changed:       False
```

**What a semantic diff gives a reviewer that a text diff of two Python files does not** is
all four of these:

1. **Role, not position.** "parameter 'bSmb' added" and "feature 'smb' added" are different
   statements about different obligations: one is something somebody now has to fit and get
   approved, the other is something a feature set now has to supply. A text diff shows one
   longer line and leaves the reader to work out which of the eight new symbols are which.
2. **Structure, not characters.** The diff is computed over the expression tree, not over
   the formula text, so respacing the operators or otherwise reformatting the same
   expression produces **no statements at all** (`semantic_diff(ir, ir) == []` is asserted in
   `tests/test_formula.py`, and a respaced formula parses to the same tree). A text diff
   reports every one of those,
   and reports them as loudly as it reports a changed discount factor — which is how a
   reviewer learns to skim a diff.
3. **Refs used and dropped.** The equation statement ends with `now uses cma, hml, rmw,
   smb`. That is the sentence a reviewer acts on.
4. **Meaning it can express, which prose cannot be relied on to.** MAYA's diff rules
   recognise a class of change — `discount factor changed from continuous to simple
   compounding`, also proved in `tests/test_formula.py` — that a text diff shows as
   `exp(-r*T)` → `1/(1+r*T)` and a reviewer has to decompile in their head.

How far (2) reaches is worth being exact about, because a control whose reach is overstated
is worse than none. The comparison is on the *canonical* tree, not the *algebraic* one, so it
is blind to formatting and not to rearrangement. Writing the same model as
`exRet = beta*mktExcess + alpha + ...`, or `mktExcess*beta` instead of `beta*mktExcess`, or
pulling a term out into a named intermediate, each reports `output equation changed` with the
before and after rendered in LaTeX. That is the conservative failure — a reviewer is shown
two equations and can see they are the same — but it is a false positive, and a desk that
reorders terms for readability will produce them.

And then the thing the diff **cannot** say, which is the reason to read it carefully. The
symbol `beta` is in both versions with the same name, the same type, the same role and the
same bounds, so no diff of any kind reports it as changed. What it *means* has changed
completely: in version 1 it is the market exposure of the universe, in version 2 it is the
market exposure *holding four other exposures fixed*. Those are different quantities that
happen to share a name, and version 1's estimate of one is not an estimate of the other.
MAYA cannot draw that conclusion. What it can do, and does, is print the fact from which a
reviewer draws it — the equation beta sits in now uses four more things — which is exactly
the division of labour a governance platform should be aiming for. Version 2's
*Mathematical Formulation* section then says it in words, because that is what the document
is for.

### 5.3 The input contract grew, and things that satisfied version 1 no longer qualify

```
input contract, v1:  mktExcess
input contract, v2:  cma, hml, mktExcess, rmw, smb
```

`capm_panel` carries exactly `stockExcess` and `mktExcess` — what version 1 declared it
needed. MAYA confirms it satisfies version 1:

```
capm_panel against v1's contract:  True
mapping:                           {'mktExcess': 'mktExcess'}
```

and refuses it for version 2, naming every missing attribute:

```
ContractMismatch: The feature set does not satisfy the model's input contract:
  input 'cma' needs attribute 'cma', which the feature set does not expose;
  input 'hml' needs attribute 'hml', ...;
  input 'rmw' needs attribute 'rmw', ...;
  input 'smb' needs attribute 'smb', which the feature set does not expose
```

This is what an input contract changing between versions means in practice, and it is why
§8.6 mints a new version when the contract moves rather than editing the old one in place.
Every feature set, every pin and every downstream consumer that satisfied version 1 has to
be re-checked against version 2 — and MAYA does the checking **at warrant time, by name,
before anything is fitted**, rather than at three in the morning in a training script.

### 5.4 A parameter set belongs to a model version, through its warrant

Version 1's approved set is `{'alpha': 0.00058851, 'beta': 1.05568635}`. Offered to version
2's warrant:

```
ValidationFailed: Parameters out of bounds: missing parameter 'bCma';
  missing parameter 'bHml'; missing parameter 'bRmw'; missing parameter 'bSmb'
```

MAYA validates an uploaded set against the declared parameters of the model version the
*warrant* names. Two numbers where six are declared is not a partially-fitted model; it is
not a parameter set for this model at all.

And the same claim is enforced a second time, at the other end. Version 2's execution
warrant, drawn on version 2's training warrant but naming version 1's parameter set:

```
ValidationFailed: The parameter set was not fitted under this training warrant
```

Which is the answer to "can we just reuse the beta we already have". The chain is
`parameter set → training warrant → model version`, and there is no step in it where a
number can be lifted across.

### 5.5 The same escrowed holdout, provably

Both warrants are drawn on the same pin with the same split and the same seed. MAYA assigns
splits by hashing `(seed, index key)`, so:

```
holdout rows, v1:        2,193
holdout rows, v2:        2,193
holdout hash, v1:        ec10f28d3a0d31c02feb7e7b…
holdout hash, v2:        ec10f28d3a0d31c02feb7e7b…
the same escrowed rows:  True
```

The comparison in §6 is therefore comparable **by construction**, and the construction is
checkable by a reader who was not there. "We evaluated both on the same holdout" is a claim
somebody has to be believed about; two equal content hashes are not.

## 6. What version 2 recovers, and what it is worth

```
name     estimate         se   clustered se      t   clustered t    generated
alpha    +0.000065   0.000138       0.000130   +0.47         +0.50      +0.0000
beta     +1.019021   0.013495       0.013084  +75.51        +77.88      +1.0000
bSmb     +0.602723   0.023425       0.023098  +25.73        +26.09      +0.6000
bHml     +0.419368   0.021468       0.019803  +19.53        +21.18      +0.4000
bRmw     +0.035600   0.029173       0.028596   +1.22         +1.24      +0.0500
bCma     -0.065056   0.028376       0.027533   -2.29         -2.36      +0.0000
```

| | version 1 | version 2 | generated |
| --- | --- | --- | --- |
| alpha, annualised | **+14.83%** (*t* 2.51 clustered) | **+1.64%** (*t* 0.50 clustered) | 0.00% |
| beta | +1.0557 | **+1.0190** | 1.0000 |
| size loading | — | +0.6027 | +0.6000 |
| value loading | — | +0.4194 | +0.4000 |
| R² train / validation | 0.3461 / 0.3472 | **0.4025 / 0.4066** | |

**The substantive finding is the intercept.** Version 1 reported a *t* of 2.51 on an alpha
that does not exist; version 2, on the same rows, reports one indistinguishable from zero.
The size and value loadings come back at +0.603 and +0.419 against generated +0.600 and
+0.400 — this is what a pooled fit on 10,654 rows can recover when the model is right.

**The classical and clustered standard errors have converged.** On alpha they were 0.000143
and 0.000235, a ratio of 1.6; now they are 0.000138 and 0.000130, a ratio of 0.95. That is
not cosmetic: the gap in version 1 existed *because* a common factor was sitting in the
residual, and it has closed because the factor is now in the model. The pair of numbers was
a diagnostic all along, and it is the sort of thing worth quoting for every pooled panel
regression a desk runs.

**Two coefficients are reported honestly rather than tidily.** The profitability loading is
+0.036 with a *t* of 1.2 — not distinguishable from zero, against a generated +0.05, which
is genuinely too small to find in this much data. And the investment loading comes back at
**−0.065 with a *t* of −2.3**, significant at five per cent and *wrong*: the universe's
generated average investment tilt is exactly zero. With five coefficients and a five per
cent test, about one such false positive is what should be expected. The study reports it,
and version 2's *Known Weaknesses* section says in writing that a reviewer who reads it as
a real exposure has been misled by arithmetic rather than by the model.

### The holdout, blind, on the same rows

| | holdout RMSE |
| --- | --- |
| Predicting zero for everybody | 0.018062 |
| Version 1 | 0.014478 |
| **Version 2** | **0.013956** |

Version 2 is **3.61%** lower than version 1 and **22.74%** lower than saying nothing.

So: **the extra factors are worth having, and they are worth having by a good deal less
than the collapse in alpha suggests.** Both of those numbers are the finding. A study that
reported the alpha collapse and left the 3.61% out would be advocacy; one that reported
3.61% and left the alpha out would have missed the point entirely. The reason the two
differ so much is that most of a daily stock return is idiosyncratic — adding four factors
moves R² from 0.35 to 0.40, and the remaining 0.60 is noise no factor model reaches. What
version 2 buys is not forecasting power. It is an *attribution that does not lie about
skill*, which is the only thing this model was ever for.

## 7. The maturity ladder

§8.6 gives a model version a maturity — `experimental`, `candidate`, `approved`,
`restricted`, `deprecated`, `retired` — and says two things about deprecation: it requires
a successor reference or an explicit statement that none exists, and MAYA warns every owner
of a warrant that depends on it. Both are built, and the study exercises both.

Without a successor and without a word about why:

```
ValidationFailed: Deprecation names a successor or states that none exists (§8.6)
```

With version 2 named, and a rationale:

```
version 1 state:                    deprecated
version 1 maturity:                 deprecated
successor recorded on the version:  maya://model/factor_models/equity_factor_model@v2
```

and MAYA tells the people who have something to stop doing, without being asked to:

```
devi's inbox:  1 deprecation notice(s)
  maya://model/factor_models/equity_factor_model@v1 was deprecated; a warrant you own depends on it
mgr's inbox:   1 deprecation notice(s)
  maya://model/factor_models/equity_factor_model@v1 was deprecated; a warrant you own depends on it
mona's inbox:  0 deprecation notice(s)
```

devi owns the two training warrants; mgr owns the execution warrant serving version 1.
mona wrote the model and hears nothing, because she does not hold a warrant — §8.6 warns
warrant *owners*, which is the right set: they are the people with a decision to make.

A new warrant on the deprecated version is refused:

```
NotApproved: factor_models/equity_factor_model@v1 is 'deprecated';
  warrants are drawn on approved model versions
```

**But what was already licensed keeps running**, and that is the right answer. Deprecation
says what may be *started*, not what must stop. The attribution that shipped last month was
computed under a warrant that is still sealed and still verifiable, and tearing it up
retroactively would destroy the reproducibility the seal exists to guarantee. Stopping a
model *now* is what revocation is for (§9.4), and it is a separate, louder act with a reason
attached.

The ladder version 1 walked, printed by the step:
`experimental → candidate (on approval) → deprecated → retired`.

That last transition is §8 below.

## 8. The bug this study found, and the fix

**`maya/services/models.py`, `ModelService._after_move` (line 699).** MAYA set a version's
maturity in exactly one place — `experimental` → `candidate`, on approval — and `maturity`
is otherwise only settable through `update_draft`, which requires an *editable draft*. An
approved version therefore could not be moved down §8.6's ladder at all: the `deprecate` and
`retire` transitions moved the workflow **state** and left the maturity at `candidate`
forever. Before the fix, the step above printed

```
version 1 state:     deprecated
version 1 maturity:  candidate
```

which is not a cosmetic disagreement. §8.7 caps a composite's maturity at its lowest
member's, and `_member_maturities` reads the member's **maturity**, not its state — so a
composite containing a *deprecated* member computed a cap of `candidate` and went on
treating that member as usable. The specification says "deprecating a member warns every
composite that contains it"; the implementation was doing the opposite of that for the one
mechanism that enforces it.

The fix is two lines of code in `_after_move` (plus the comment that explains them): when a
version moves to `deprecated` or `retired`,
its maturity moves with it. `tests/test_composite_governance.py::
test_deprecating_a_version_moves_its_maturity_down_the_ladder` fails without it, at the
assertion that the maturity is `deprecated`, and also proves the consequence — that a
composite over a deprecated member is now capped at `deprecated` and refuses to claim
`candidate`.

## 9. The finding that was left as a finding, and what was decided

Then an administrator retires version 1 **while its execution warrant is still live and still
serving**. On this study's first run MAYA allowed it:

```
version 1 state:                        retired
MAYA allowed the retirement:            True
bundle:                                 live
still serving a retired model version:  True
```

The warrant went on issuing bundles for a version that had been retired. Nothing refused,
nothing revoked, nothing warned — not even the deprecation notice, which fired on `deprecate`
and not on `retire`.

That was not an oversight in one function so much as a seam between two lifecycles that did not
know about each other. MAYA guards the *drawing* of a warrant against a version that is not
approved (`warrants.create` checks `APPROVED_STATES`), and it guards a warrant's own lifecycle
thoroughly — expiry, suspension by covenant, revocation with a reason that propagates. But
`ExecutionService.check`, which every bundle and every token goes through, looks only at the
warrant's own status. The model version underneath it was never consulted.

The study left it unfixed, because closing it meant choosing between designs and that choice
belongs to the owner rather than to a case study. Four were on the table: retirement *refuses*
while a live warrant depends on the version; retirement *cascades* a revocation; *serving*
refuses, which silently turns every retirement into an outage; or retirement *warns* and leaves
revocation to a person.

**The decision was the first, with the fourth added.** Retirement is an administrative end of
life, not an outage, and left unguarded it was neither. So:

```
NotApproved: Blocked by check(s): no_live_execution_warrant —
  an execution warrant is still serving this version: factor_models/capm_attribution.
  Retirement is not an outage — revoke the warrant first (§9.4)
```

Revoke, then retire, and the order is the point: taking a model out of service *now* is
revocation, and it is a deliberate act with a reason attached. A **training** warrant does not
block, because it is a record rather than a service and its seal exists to keep the fit
reproducible — withdrawing that would destroy the thing the seal is for. Its owner is warned
instead, which is the fourth option folded in: retirement now notifies every dependent
warrant's owner exactly as deprecation does.

```
capm_fit_2324:                      approved, sealed_at 2026-09-20T14:03:51
devi's notices about version 1:     ['retirement', 'deprecation']
```

Both notices, and the retirement one exists because of this study. §11 has the specification
wording that followed, which §8.6 had been silent on.

## 10. What to point at when demonstrating this

1. **§5.2, the diff** — and then the paragraph about `beta`. This is the clearest example in
   the library of a control that does exactly as much as it honestly can and hands the rest
   to a person with the right fact in front of them.
2. **§5.3 and §5.4 together** — a second version is not a longer file. It is a new contract
   that old feature sets may fail, and a new set of parameters that the old numbers cannot
   be poured into.
3. **§5.5, the two equal holdout hashes** — the comparison is verifiable by somebody who
   was not in the room.
4. **§4 and §6, the pair of standard errors** — the classical/clustered gap is a
   measurement of what the model left in its residual, and watching it close between the
   two versions is the study's best single piece of statistics.
5. **§3, the environments list** — a leakage exception written in prose, enforced in a field.
6. **§9** — the study found something MAYA does not do, and says so instead of not looking.

## 11. What I would change in the specification

Two sentences, both in §8.6, which currently reads:

> A model version carries a **maturity**: `experimental`, `candidate`, `approved`,
> `restricted`, `deprecated`, `retired`. Deprecation requires a successor reference or an
> explicit statement that none exists, and MAYA warns every owner of a warrant that depends
> on it.

It never says **who moves a version along that ladder, or when**. The implementation
answered "only its author, and only while it is a draft", which makes `approved` and
`restricted` unreachable for any version that has actually been approved — you cannot mark
a live version `restricted` without minting a new draft, which mints a new version, which
is not what restriction means. I would add:

> A version's maturity is set by whoever may approve it, at any point in its life, and does
> not require a new draft: a version already in service can be marked `restricted` without
> becoming a different version. The `deprecate` and `retire` transitions move the maturity
> with the state; the two never disagree.

And §8.6 says nothing at all about retirement, which is the hole §9 fell into. I would add:

> Retirement is the end of the ladder and it is not retroactive: warrants already sealed on
> a retired version remain valid and remain reproducible, because withdrawing them would
> destroy the reproducibility the seal exists to guarantee. MAYA warns every owner of a
> warrant that depends on a version being retired, exactly as it does on deprecation, and
> names the warrants. Taking a model out of service *now* is revocation (§9.4), not
> retirement, and the two are deliberately different acts.

## 12. What this study deliberately does not do

It is a **pooled** regression: one intercept and one slope per factor for the whole
universe, so what it estimates is the equal-weighted universe's exposure and not any single
stock's. A per-stock beta would be thirty parameter sets or a thirty-row parameter matrix,
which is case study 35's problem, not this one's.

The split is a **random row split**, not a forward time split. For a contemporaneous
attribution that is correct — there is no forecast whose horizon a time split would need to
respect — and for anything predictive it would be wrong. The specification's *Calibration
Methodology* section says which of the two this is.

Exposures are constant over the window, which is why the window is two years and not ten.
There is no momentum factor, no industry control, no currency dimension and no
multicollinearity diagnostic among the published factors. Public holidays are not modelled
in the calendar. All of it is in *Known Weaknesses*, where somebody reading the model will
find it.

## The input data

| File | Rows | Size | What it is |
| --- | --- | --- | --- |
| `data/equity_daily.csv` | 15,120 | 0.86 MB | Thirty stocks × 504 trading days: total return, excess return, known that evening. |
| `data/factor_daily.csv` | 504 | 0.04 MB | Five factor returns and the risk-free rate, one row a day, known on the 4th of the following month. |

Both are committed (0.90 MB in total), so the study runs with no generation step and a
reader can open them and see exactly what MAYA was given. `make_data.py` holds the recipe,
and prints the realised premia and the universe's mean loadings when it runs.
