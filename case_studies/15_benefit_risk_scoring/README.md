# Case study 15 — A benefit risk model that used nationality

**T2 — estimated.** The **second** case study in this suite that was not
designed to fit MAYA, and the first taken from outside financial services.

---

## Why this one exists

[Case study 14](../14_var_model_change/) walked a bank's model-change failure
into the register and found a refusal its author had not planned for. One
outside scenario is an anecdote. This is the second, chosen to fail in a
*different place*: 14 is about a change nobody was made to justify, and this is
about a **fact the register can see and cannot act on**.

It also leaves the industry the platform was built for. Every control in MAYA is
argued from banking supervision, and the question of whether any of it transfers
is one a bank's own case study cannot answer.

### Sources

The sequence is from the public record:

- Autoriteit Persoonsgegevens. **Belastingdienst/Toeslagen: de verwerking van de
  nationaliteit van aanvragers van kinderopvangtoeslag**, 17 July 2020.
- Autoriteit Persoonsgegevens. **Fining decision**, 7 December 2021 — €2.75m for
  unlawful, discriminatory and improper processing.
- Parlementaire ondervragingscommissie Kinderopvangtoeslag. **Ongekend onrecht**
  ("Unprecedented Injustice"), 17 December 2020.
- District Court of The Hague. **NJCM and others v. the State of the
  Netherlands** (the *SyRI* judgment), 5 February 2020,
  ECLI:NL:RBDHA:2020:865.

**The numbers are a reconstruction.** No applicant data is used or reproduced
and none of the coefficients is the administration's. They are sized so the
mechanism is visible and deterministic. MAYA is being shown a shape of failure,
not audited against a case file.

---

## What happened, in the order it happened

1. A **self-learning risk classification model** selected childcare benefit
   claims for manual review.
2. **Nationality was among the indicators.** Dual nationality raised the score.
3. Selected claims met a **recovery policy** that treated an administrative
   error as fraud, and demanded repayment in full.
4. Roughly **26,000 families** were wrongly treated as fraudulent. Children were
   removed from homes.
5. The data protection authority found the processing unlawful, discriminatory
   and improper, and fined the administration **€2.75m**.
6. A parliamentary inquiry reported in December 2020; the government **resigned**
   in January 2021.

---

## The model

A logistic scorer over claim attributes, feeding a **review queue of fixed
size** — the top-scoring share of claims goes to a person, because a review
function has a headcount:

$$p(\text{review}) \;=\; \sigma\Bigl(\beta_0 + \sum_j \beta_j\,(x_j - \bar{x}_j)\Bigr)$$

Modelling the queue as a *capacity* rather than as a probability threshold is
deliberate, and the first version of this script got it wrong: with a threshold
at $p \ge 0.5$ the reconstruction selected either everybody or almost nobody
depending on the intercept, which is a fact about the intercept and not about
the failure. It also puts the question where the harm was — not *what did the
model predict* but **who ended up in the queue**.

### The mechanism, and why deleting the column does not fix it

| model | single nationality | second nationality | ratio |
|---|---|---|---|
| as built | 6.2% | 23.8% | **3.80×** |
| nationality column deleted | 10.5% | 19.5% | **1.86×** |

Deleting the protected column removes **69% of the excess and leaves the rest**,
because postcode deprivation carries the same signal. Housing is segregated;
the proxy does not need anybody's intent.

> This is why MAYA records `binds_proxy_risk` as a fact **separate** from
> `binds_protected_basis`. A proxy is the harder case: it is not obviously a
> protected characteristic, and a model built on one is discriminating without
> any column saying so.

---

## Seven governance questions, and MAYA answers four and a half

| | Question | MAYA | Where |
|---|---|---|---|
| **1** | Does the register know the model reads a protected characteristic? | **Yes** — computed by walking the contract to the *pinned* view version | `core/features/screening.py` |
| **2** | Does anything **refuse** on it? | **Only if the firm wrote the rule** — and the estate view says whether it did | `core/policy/` |
| **3** | Does deleting the column fix it? | **No**, and the proxy is a fact of its own | `binds_proxy_risk` |
| **4** | What control depth does this model owe? | Tier **2** — and that is a **limitation**, see below | `core/risk/` |
| **5** | Is the version that runs the version approved? | **Yes**, and an alias to a version that does not exist is refused | `core/registry/aliases.py` |
| **6** | May a fit on this data happen here, for this purpose? | The **authority** is refused; the execution is not observed | `docs/14 §9.4` |
| **7** | Was the household treated fairly? | **MAYA cannot see this.** | — |

### Question 2 is the uncomfortable one

MAYA answers it about itself, in its own words:

```
1 model(s) bind a protected characteristic, 1 bind a known proxy, and 1 bind
an uncertified feature. **No rule in force refuses on `binds_protected_basis`**,
so the tag is recorded and nothing acts on it — which is a control that exists
in a screenshot, and worse than an absent column because a tagged estate looks
governed.
```

That is the [eleventh edge](../../docs/18-the-registers-edges.md) pointed at the
exact failure it was written about. The platform publishes five facts at the
approval and alias-move gates and **does not write the rule**, because
*prohibit direct use in in-scope decisions while permitting controlled use for
fairness testing* is not a sentence a platform can evaluate on a government's
behalf — and one refusing on the tag alone would refuse the fairness testing the
same regulation requires.

**So the honest headline is: MAYA would have made the nationality binding
visible, and would not by itself have stopped it.** What it adds is that the
absence of a rule is *also* reported, so a firm that never wrote one cannot
mistake a tagged estate for a governed one.

### Question 4 found a limitation the script did not expect

`policy_decision` is the **highest purpose class MAYA has**, and the model still
tiers at **2**.

The tier is a lattice over purpose *and* **exposure**, and exposure is
denominated in money. This model's exposure is twenty-six thousand households.
MAYA's tiering was built for an estate where consequence is measured in
currency, and a model that ruins people without moving a balance sheet sits
below a mid-sized pricing model.

> That is a real limitation of the platform, found by running somebody else's
> failure. It is recorded here rather than quietly absent, and it is exactly
> the kind of thing a self-designed case study does not surface.

---

## What this case study changed in the platform

Two things, which is the suite working as intended:

1. **The SDK could not set `proxy_risk`.** The API has always accepted it and
   `ContractScreening` screens on it, but `maya.features.define` had no such
   argument — so a client using the shorter path could tag a protected
   characteristic and silently fail to tag the proxy for one, which is the
   harder of the two. Fixed.
2. **Re-binding a feature contract returned a 500.** `bind` inserted straight
   into a table with a unique index on `model_version_id`, so a second call
   raised an `IntegrityError`. The fix is not only the status code: an
   **identical** re-bind is now a no-op, and a **different** contract on the
   same version is **refused**. A contract is what `L-17` compares serving
   against and what the approval was given on, so letting it be rewritten in
   place would change what a version reads without changing the version.

---

## What MAYA would not have caught

The section a demonstration usually omits. In this failure it is most of the
harm.

- **The recovery policy.** The damage was not mainly that claims were selected —
  it was that selection met an all-or-nothing repayment rule that treated an
  administrative error as fraud. That rule was *policy*, not a model.
- **The blacklist.** A separate fraud signalling facility held names. A list is
  not a model, and nothing in a model register makes anybody register one.
- **Whether anybody read the finding.** MAYA can put a fact on a screen, a
  worklist and an evidence chain. It cannot make an institution look at it.
- **The absence of an impact assessment.** MAYA records that one is required and
  holds the document if somebody compiles it. It is not a DPIA and does not
  write one.
- **The harm.** Twenty-six thousand families, children removed from homes and
  years of recovery proceedings are not governance artefacts. Nothing here
  should be read as suggesting a register would have prevented them.

---

## Running it

```bash
python case_studies/15_benefit_risk_scoring/build.py --url http://127.0.0.1:5006
```

Re-runnable. It writes `benefit-risk-scoring.tex` and `case-15-summary.json`.
