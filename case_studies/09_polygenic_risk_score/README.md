# Case study 9 — A polygenic risk score, and a limitation that is a *property*

> **The demo in one sentence.** A genomic risk score decides who gets screened
> earlier — and its most important fact is that it works far less well in some
> ancestries than others, which MAYA makes travel *with the numbers* instead of
> living in a paper nobody reads at the point of use.

```bash
.venv/bin/python case_studies/09_polygenic_risk_score/build.py
```

Independent of the other case studies. Runs in about ten seconds.

---

## 1. The theory

### What a polygenic risk score is

Most common diseases are **polygenic**: no single variant causes them, but
thousands of common variants each shift risk slightly. A genome-wide
association study (GWAS) genotypes a large cohort, tests each variant for
association with the trait, and publishes an **effect size** `β` per variant —
the change in log-odds of disease per copy of the effect allele.

A polygenic risk score adds them up:

```
PRS_i = Σ_j  β_j · g_ij
```

where `g_ij ∈ {0, 1, 2}` is how many copies of variant *j*'s effect allele
subject *i* carries. It is a **linear model with no intercept**, and the
weights were estimated somewhere else, years ago, by somebody else.

The 9p21.3 locus in this case study is the most replicated association in all of
complex-trait genetics — discovered in 2007, confirmed in essentially every
subsequent coronary artery disease GWAS, and still not fully explained
mechanistically. It is the strongest common-variant signal for CAD, which is why
its two variants carry the largest weights here.

### Why it is a governance problem and not just a statistics problem

A PRS is used to decide **who gets screened earlier**, who is offered statins,
and in some programmes who is offered risk-reducing surgery. So:

- it acts on people, individually;
- its inputs are the most protected data that exists;
- it is increasingly sold direct to consumers, outside any clinical governance;
- and it has a **known, measured, published failure mode** that most deployments
  do not record anywhere a clinician will see it.

### The transferability problem

**This is the heart of the case study.** A PRS developed in European-ancestry
cohorts loses much of its discriminative power in other ancestries. Published
transferability studies consistently find something like:

| Ancestry | Relative R² | Why |
|---|---|---|
| European | 1.00 | the development population |
| South Asian | ~0.7 | attenuated; different LD structure |
| East Asian | ~0.65 | attenuated; several loci not polymorphic |
| **African** | **~0.4** | **severely attenuated** |

Two mechanisms, and neither is a software defect:

1. **Effect sizes are estimated in one population.** The `β`s are averages over
   a specific cohort. Allele frequencies and gene–environment interactions
   differ elsewhere, so the same allele does not carry the same risk.
2. **Linkage disequilibrium structure differs.** GWAS rarely finds the *causal*
   variant; it finds a **tag** variant correlated with it. That correlation is a
   property of the population's LD structure. African populations have shorter
   LD blocks — a consequence of being the oldest and most genetically diverse —
   so a tag variant chosen in a European cohort tags the causal variant *less
   well*, and sometimes not at all.

**It is not fixable downstream.** No amount of recalibration in the clinic
repairs a weight that was estimated against the wrong linkage structure. The
fix is a GWAS in the target population, and the reason it has not happened is
that ~80% of GWAS participants have been of European ancestry. A model-risk
platform cannot fix that either — but it can refuse to let the fact go
unrecorded.

### Why this belongs on the parameter set

The limitation is not a caveat *about* the model. It is a **property of the
parameter set** — a different set of `β`s, from a different GWAS, would have a
different profile. So in MAYA it travels as a diagnostic on the recorded
coefficients:

```json
"transferability_r2_ratio": {"European": 1.0, "South Asian": 0.72,
                             "East Asian": 0.65, "African": 0.42},
"limitation": "Developed in European-ancestry cohorts. Discriminative
   performance attenuates in other ancestries — to roughly 42% of European in
   African ancestry — because effect sizes are estimated in one population and
   linkage disequilibrium structure differs in another. This is a property of
   the parameter set, not a defect to be fixed downstream."
```

Anybody reading the numbers reads the limitation **at the same moment**. That is
the entire governance contribution, and it is a small one that matters a great
deal at the point of use.

### A PRS has no meaningful absolute value

The score in this case study ranges from 0.25 to 2.13 and those numbers mean
nothing on their own. A PRS is interpreted as a **percentile within a reference
population** — "this person is in the top 5% of genetic risk" — and the
reference population is *the one the weights came from*.

So the transferability limitation reappears in the interpretation, wearing
different clothes: a percentile computed against a European reference is not a
percentile for somebody who is not of European ancestry. The script prints
percentiles and says so.

### References

- Martin, A. R. et al. (2019). *Clinical use of current polygenic risk scores
  may exacerbate health disparities.* Nature Genetics 51.
- Duncan, L. et al. (2019). *Analysis of polygenic risk score usage and
  performance in diverse human populations.* Nature Communications 10.
- The **GWAS Catalog** (EBI/NHGRI) and the **PGS Catalog** — where real summary
  statistics live.

---

## 2. The data

**The rsIDs and loci are real.** `rs1333049` and `rs4977574` at 9p21.3,
`rs11206510` near PCSK9, and the others are genuine, published CAD associations.

**The effect sizes are illustrative**, and the script says so in a comment where
they are defined. Real summary statistics are published in the GWAS Catalog and
the PGS Catalog under terms this repository should not redistribute — and using
a convenient copy of somebody's data is the habit case study 2 argues against.

**The dosages are synthetic**: twelve subjects, 0/1/2 copies per variant.

---

## 3. Two clocks, with a laboratory in between

| Clock | Value | Meaning |
|---|---|---|
| `event_ts` | sample taken | when the genotype was **true** — at conception, in fact, but the sample fixes it |
| `ingest_ts` | + 20 days | when the laboratory **returned the calls** |

The gap is weeks, not hours, and it is the same bitemporal rule a bank needs
with a longer lag: **a score computed "as of" a clinic date must not use variant
calls that had not come back yet.** A retrospective study that ignores this
will look better than the clinic ever could have been.

---

## 4. Protected data, declared rather than assumed

Every variant feature is registered with:

```python
pii=True, protected_basis=True, sensitivity="restricted"
```

`protected_basis` is the one worth pausing on. Genotype is special-category
data under GDPR Article 9 — but the sharper point is that **ancestry is
inferable from genotype**. A handful of variants is enough to predict continental
ancestry with high accuracy. So every one of these features is a potential proxy
for a protected characteristic *whether or not anybody intended it to be*, and
declaring it makes the fairness question answerable by query instead of by
interview.

---

## 5. What the script does

| Step | What happens |
|---|---|
| 1–2 | Register a feature per variant, flagged PII and protected-basis |
| 3 | Load genotypes with both clocks |
| 4–5 | Featureset; register the model; class derived |
| 6–8 | Approve the version, put the record in force, grant |
| 9 | **Training warrant** |
| 10 | Deliver the GWAS weights **with the limitation quantified on them** |
| 11 | A second person accepts — **naming the population it is accepted for** |
| 12–13 | Execution warrant; score the cohort locally, as percentiles |
| 14 | Write the LaTeX specification |

---

## 6. The acceptance names a population

```python
people["s.iqbal"].parameters.review(
    parameter_set_id, accept=True,
    note="Accepted for the European-ancestry screening pathway ONLY. The
          attenuation figures are on the set; use outside that pathway is a
          different decision that nobody has taken.")
```

**A parameter set approved without a population is one that will be used on
everybody.** The approval is the natural place to bound it, because it is the
moment somebody with authority is already reading the diagnostics.

---

## 7. The output, and a detail worth pointing at

```
subject          PRS  percentile   alleles carried
SUB-0007       2.130         96%   11 of 12
SUB-0004       1.720         88%   9 of 12
SUB-0001       1.590         79%   7 of 12
SUB-0003       1.470         62%   8 of 12
```

**`SUB-0001` carries seven risk alleles and outranks `SUB-0003`, who carries
eight.** Because the two 9p21.3 variants carry the largest weights, and
`SUB-0001` is homozygous for both.

That is the model working correctly, and it is also exactly the kind of result a
patient will find counter-intuitive: "I have fewer risk variants and a higher
score." A PRS is a *weighted* sum, and the weights are the model.

---

## 8. Where this case study's approach stops scaling

Stated because it is a real boundary:

- **Six variants fit in an expression; a production PRS does not.** Real scores
  use 10⁴–10⁶ variants. At that size the parameter set is an artifact rather
  than a row, MAYA locates it by digest instead of holding it, and the
  `formula` runtime is the wrong choice — the honest registration becomes closer
  to case study 8's shape.
- **No calibration in this clinic's population**, which the diagnostics record
  as `not_measured` rather than leaving to be assumed.
- **No competing-risk or age-of-onset modelling**, both of which a clinical
  deployment needs.

---

## 9. Questions this case study answers well

**"Does any of this apply outside finance?"**
This is the case study for that conversation. Change the vocabulary and every
control is the same: two clocks, a pinned training set, parameters somebody
delivered and somebody else approved, and a limitation that has to be readable
at the point of use.

**"Where do you record that a model does not work for everyone?"**
On the parameter set, quantified, so it is read at the same moment as the
numbers — and in the approval, which names the population the set is approved
for.

**"How do you handle protected characteristics you never collected?"**
By declaring the features that are proxies for them. Ancestry is inferable from
genotype whether or not anybody asked for it.

---

## 10. Files this produces

| File | What it is |
|---|---|
| `warrant-training.json` | The training warrant |
| `warrant-execution.json` | The execution warrant |
| `prs-specification.tex` | Specification, with the transferability table |

```bash
pdflatex prs-specification.tex     # 2 pages
```
