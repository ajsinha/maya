# Case study 2 — Home price regression, on real public data

> **The demo in one sentence.** Five regressors, 2,928 real house sales from
> their authoritative source, ordinary least squares fitted *outside* MAYA — and
> the interesting part is not the regression, it is the clock the source did not
> have.

```bash
.venv/bin/python case_studies/02_home_price_regression/build.py
```

First run downloads ~1 MB and caches it in `data/`. Afterwards, or with
`--offline`, it uses the cache. See [`../README.md`](../README.md) for starting
the platform and creating users.

---

## 1. Why this one exists

Case study 1 is a model with no training data. This is the ordinary case, and
it is deliberately unglamorous: a linear regression any analyst could fit in a
spreadsheet. The demo value is not the model. It is that **real data brings a
real provenance problem**, and MAYA makes somebody answer it.

---

## 2. The data, and its provenance

**Source, verbatim:**

```
http://jse.amstat.org/v19n3/decock/AmesHousing.txt
http://jse.amstat.org/v19n3/decock/DataDocumentation.txt
```

That is Dean De Cock's own file, from the *Journal of Statistics Education*
paper that published it — 2,930 residential sales in Ames, Iowa, 2006–2010, 82
columns. **Not** a mirror, not a repackaged copy on somebody's profile, not a
Kaggle re-upload. A governance demo that cites a convenient copy is teaching the
habit it should be correcting.

> De Cock, D. (2011). *Ames, Iowa: Alternative to the Boston Housing Data as an
> End of Semester Regression Project.* Journal of Statistics Education 19(3).

**There is no synthetic fallback.** If the download fails, the script stops and
tells you to fetch the file. Silently substituting invented numbers for a named
public source is precisely the failure this case study teaches against.

### What is read

| Feature | Source column | Meaning |
|---|---|---|
| `gr_liv_area` | `Gr Liv Area` | above-grade living area, ft² |
| `overall_qual` | `Overall Qual` | overall material and finish, 1–10 |
| `year_built` | `Year Built` | year of original construction |
| `total_bsmt_sf` | `Total Bsmt SF` | total basement area, ft² |
| `garage_cars` | `Garage Cars` | garage capacity, in cars |
| `sale_price` | `SalePrice` | **the label**, USD |

Rows with a missing or non-numeric value in any of those are **dropped, and the
count is reported** — 2,928 of 2,930 survive. Dropped rather than imputed on
purpose: quietly filling missing basements with zero would be making the
modelling decision that matters most and saying nothing about it.

---

## 3. The clock that was not in the data

**This is the demo.** Spend the time here.

MAYA requires **two timestamps on every feature row**:

- `event_ts` — when the fact was *true* in the world
- `ingest_ts` — when the recording system *learned* it

A row missing either is refused at upload, not two layers later during
assembly, where it stops being fixable.

The Ames data gives `Mo Sold` and `Yr Sold`. That is `event_ts`. It says
**nothing** about when the assessor's office recorded the sale — so `ingest_ts`
had to come from somewhere, and somebody had to decide.

```python
RECORDING_LAG_DAYS = 45.0
"ingest_ts": sold + RECORDING_LAG_DAYS * DAY
```

**Forty-five days is an assumption, not a fact from the source.** The script
says so on the console, the feature view's own description carries it, the
parameter set's diagnostics carry it, and the LaTeX specification has a
paragraph headed *The assumption*.

### Why this matters more than the regression

Ask the room: *for your models, who decided the ingest clock, and where is it
written down?*

The usual answer is that nobody decided, because nobody was asked. And its
absence is invisible until the day somebody re-fits a model on data that had
not been recorded when the original decision was taken — at which point the
backtest looks wonderful and the model performs badly, and the discrepancy is
attributed to drift rather than to leakage.

MAYA cannot supply the second clock. What it can do is **refuse to accept data
without one**, which forces the question to a person with a name.

---

## 4. What the script does

| Step | What happens | Who does it |
|---|---|---|
| 1 | Fetch and parse the Ames file; report drops | script |
| 2 | Create the four people | MAYA |
| 3 | Register five features and the label | MAYA |
| 4 | Load 2,928 sales as one view version, both clocks | MAYA |
| 5 | Declare the featureset, with `sale_price` as the **label slot** | MAYA |
| 6 | Register the model; **T2 and the tier are derived** | MAYA |
| 7 | Approve the version — tier quorum | s.iqbal + v.chen |
| 8 | Put the model record in force | MAYA |
| 9 | Grant standing entitlements | MAYA |
| 10 | **Show a refusal**: a read bounded in only one clock (**L-W9**) | MAYA |
| 11 | **Training warrant** | MAYA |
| 12 | **Fit by QR least squares** | **script** |
| 13 | Deliver coefficients — land **proposed** | MAYA |
| 14 | s.iqbal accepts them | MAYA |
| 15 | Ask for the mathematics | MAYA |
| 16 | **Execution warrant** | MAYA |
| 17 | **Value eight properties locally** | **script** |
| 18 | Write the LaTeX specification | script |

---

## 5. The fit, and the diagnostic that matters

Fitted with `numpy.linalg.lstsq` — QR, **not** the normal equations. Inverting
XᵀX squares the condition number, and two correlated regressors is exactly
where that stops being a textbook remark.

```
n=2,928   R²=0.7868   adj R²=0.7864
condition number 229,832, residual SE $36,920

intercept               -699,736.57
b_gr_liv_area                 51.55     <- $/ft² of living area
b_overall_qual            20,805.86     <- $/quality point
b_year_built                 313.71     <- $/year of construction
b_total_bsmt_sf               33.25     <- $/ft² of basement
b_garage_cars             13,030.77     <- $/garage space
```

The coefficients are all the right sign and a plausible magnitude, which makes
this a good model to *talk* about — and then to be careful about.

**Look at the condition number: 229,832.** That is the number a validator
should react to, and it is why the script reports it beside R². `year_built`
runs from 1872 to 2010 and never goes near zero, so the design matrix is badly
scaled and the intercept (−$700k) is an extrapolation to year zero rather than
a price. A well-fitting regression on badly conditioned regressors has a
respectable R² and coefficients nobody should interpret individually.

MAYA does not judge this. It **records it**, on the parameter set, where the
person accepting the numbers has to read it.

---

## 6. The refusal this one shows: L-W9

```python
maya.warrants.for_fitting(..., window={"from": WINDOW_FROM})   # no "to"
```

```
[grammar_violation] a featureset read for fitting must bound the period it covers
```

A training read must be bounded in **both** directions. An unbounded window is
one that will quietly include tomorrow's data the next time somebody opens it —
and the fit will look fine.

> **A trap worth knowing.** `{"from": 0.0}` does *not* work as "from the
> beginning of time": zero is falsy, and a falsy bound reads as no bound at all.
> The script uses a real date (2000-01-01) with a comment saying why. If you
> adapt this for your own model, do the same.

---

## 7. Scoring locally under the execution warrant

The last step is the one that makes the boundary concrete. The script:

1. reads the execution warrant,
2. pulls the **approved** coefficient set the warrant names by id and digest,
3. runs the Python **MAYA derived from its own stored expression**,
4. and values eight properties — in its own process.

```
property                 modelled       actual        error
AMES-0526301100           187,304      215,000      -27,696
AMES-0526350040           108,018      105,000        3,018
...
```

MAYA is not in that loop. It issued a credential; the arithmetic happened here.

---

## 8. Things to try live

**Change a regressor and watch the model change.** Add `Lot Area` to
`REGRESSORS`, bump `SEMVER` to `1.1.0`, re-run. You get a new version, a new
approval, a new warrant — because *adding a regressor is a model change, not a
data change*, and MAYA is built around that sentence.

**Try to reuse the old featureset with the new kernel.** MAYA refuses with
`schema_not_satisfied`, naming the missing field.

**Approve your own parameters.** Sign in as whoever recorded them and call
`parameters.review(..., accept=True)`. Refused.

**Ask what the platform thinks it has:**

```bash
curl -s -u admin:maya-admin-dev \
  "http://127.0.0.1:5006/api/v1/mathematics?urn=maya://model/retail.collateral.home_value&semver=1.0.0"
```

---

## 9. Questions this case study answers well

**"Can it take our real data?"**
This *is* real data, from its authoritative source, downloaded at run time.

**"What does MAYA make us do that we don't do today?"**
Name the second clock, and own it. Everything else here you already do.

**"Is the model locked away in the platform?"**
No. The fit ran in numpy in a script you can read; MAYA never saw the design
matrix.

---

## 10. Files this produces

| File | What it is |
|---|---|
| `data/AmesHousing.txt` | The cached source file, ~1 MB, downloaded once |
| `warrant-training.json` | The training warrant |
| `warrant-execution.json` | The execution warrant |
| `home-price-specification.tex` | Specification; equation derived by MAYA |

```bash
pdflatex home-price-specification.tex        # 2 pages
```
