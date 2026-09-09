# Case study 6 — HELOC eligibility: a model whose parameters are *authored*

> **The demo in one sentence.** A HELOC is underwritten against a policy
> rulebook, that rulebook decides who gets credit, and MAYA governs it as a
> model — versioned, digested, checked against the schema, trialled, and
> approved by somebody other than its author.

```bash
# Case study 2 first — this one reads its output.
.venv/bin/python case_studies/02_home_price_regression/build.py
.venv/bin/python case_studies/06_heloc_eligibility_rules/build.py
```

---

## 1. The theory

### What a HELOC is

A **home equity line of credit** is a revolving, second-lien facility secured on
a borrower's home. It differs from a mortgage in three ways that matter to risk:

1. **It is a line, not a loan.** The bank commits to an amount; the borrower
   draws what they want, when they want. Exposure is therefore *uncertain* —
   which is why HELOC capital rules turn on a **credit conversion factor**
   (CCF), the fraction of the undrawn line expected to be drawn by default.
   Empirically, distressed borrowers draw *more*, so exposure rises exactly
   when creditworthiness falls. This is adverse selection on the exposure
   dimension, and it is the reason HELOC EAD is not simply the current balance.
2. **It is subordinate.** In a default, the first-lien mortgage is repaid
   first. The HELOC absorbs loss only after that claim is satisfied, so
   recoveries are convex in house prices: a modest fall in value can take the
   second lien from fully secured to fully unsecured while the first lien is
   barely touched. Loss given default for a second lien is routinely 80–100%.
3. **It has two lives.** A **draw period** (typically 10 years, often
   interest-only) followed by a **repayment period** (10–20 years, amortising).
   The transition is the notorious **end-of-draw payment shock**: a borrower
   paying interest only on \$100,000 at 7% pays \$583 a month, and the day the
   draw period ends that becomes roughly \$1,160 on a 10-year amortisation. The
   2014–2017 US wave of end-of-draw defaults on 2004–2007 vintages is the
   reference event, and it is why supervisors ask specifically about
   end-of-draw exposure profiles.

### The quantity the policy is written in

**Combined loan-to-value**:

```
CLTV = (first-lien balance + HELOC line) / property value
```

Three modelling choices are buried in that formula, and each is a real decision:

- **The *line*, not the drawn balance.** Policy uses the committed amount
  because the borrower may draw it all. Using the drawn balance would understate
  risk at origination for precisely the accounts that later become problems.
- **Which property value?** An appraisal, an automated valuation model, or a
  tax assessment — and they disagree. This case study uses the output of the
  home-value model from case study 2, which makes the CLTV limit only as good
  as that model. That dependency is recorded rather than assumed (§5).
- **When?** CLTV at origination is not CLTV today. House prices move, and a
  policy expressed at origination says nothing about the book's current
  position.

### Why the policy is a rulebook and not a scorecard

A bank could model HELOC approval statistically: fit a PD, set a cutoff. Most
do that *too*. But origination policy is a rulebook for reasons that are not
about predictive power:

- **Some limits are not estimated, they are decided.** "CLTV above 85% is
  outside appetite" is a board decision about how much second-lien risk the
  institution wants. No amount of data makes it 87%.
- **Some limits are legal or regulatory**, and a model that optimised past them
  would be optimising past the law.
- **Adverse action.** Under the US Equal Credit Opportunity Act and Regulation
  B, a declined applicant must be given the **specific principal reasons**. A
  rule that fired, with the policy clause it implements, is such a reason. "The
  model scored you at 0.31" is not.

This is the substance of the T8 argument below: **a rulebook that decides who
gets credit is a model, and a register that governs the scorecard but not the
rulebook is governing the easier half.**

### First match wins, and totality

The rulebook is an *ordered* list evaluated top to bottom, first match wins.
Order is therefore semantics, not presentation: moving `dti_above_limit` above
`fico_below_floor` changes which reason a declined applicant is given, even
when the decision is unchanged — and the reason is the regulated artefact.

Formally, the rule set is a **total function** from the input space to the
decision set, and totality is guaranteed by construction rather than by
analysis: `otherwise` is required. A rulebook without one has an undefined
behaviour on the cases its author did not think of, and "undefined" in
production means "whatever the code happened to do".

---

## 2. The policy in this case study

| Rule | Condition | Decision |
|---|---|---|
| `no_valuation` | `property_value` is null | refer |
| `cltv_outside_appetite` | CLTV > 0.85 | decline |
| `fico_below_floor` | FICO < 660 | decline |
| `investment_property` | occupancy = investment | refer |
| `dti_above_limit` | DTI > 0.43 | refer |
| `thin_file_high_cltv` | CLTV > 0.80 **and** FICO < 700 | refer |
| *otherwise* | — | **approve** |

Each carries a `because` citing the policy clause it implements, because
**MAYA requires one**:

> A rule with no stated reason cannot be defended to a supervisor, cannot be
> reviewed by whoever owns the policy, and cannot be retired by anybody later
> because nobody knows what it was for.

The last rule is the interesting one. It is not a threshold on either variable
alone; it is an *interaction* — the segment where high leverage meets a thin
file. Rulebooks express interactions crudely compared with a model, and that
crudeness is a real cost, which is why banks run both.

---

## 3. T8 — parameters that are authored

```python
"parameter_kind": "rule_set",   # P is a rulebook
"fit_procedure":  "author",     # ...inhabited by authoring
```

MAYA answers **T8**. Compare across the case studies:

| Class | P inhabited by | Case study |
|---|---|---|
| T0 | nothing; theory decides | 4 — Merton |
| T1 | calibration to observables | 1 — Black–Scholes |
| T2 | estimation from a sample | 2, 3, 5 |
| **T8** | **authoring** | **this one** |

What changes when parameters are authored:

- **The rule set *is* the parameter object.** It is versioned, digested and
  approved like a coefficient vector. The digest covers the **parsed canonical
  form**, so reformatting the document does not create a new parameter set —
  but *reordering the rules does*, because order is meaning.
- **Changing a threshold is a new parameter set, not a new model version.**
  That is why the rule set lives in the parameter object and only its *name*
  is in the kernel's `entry`. Move the rules into the version and every policy
  tweak becomes a model change with a full revalidation behind it, which is how
  policy ends up being managed outside the platform in a spreadsheet.
- **Self-approval is refused**, exactly as for a fitted set.

### An honest finding about where "authored, not fitted" is enforced

The script asks for a **training warrant** and MAYA **issues one**. That is not
a bug, and it is not quite right either.

The warrant grammar refuses a fit for **T0 and T6 only** — the classes with no
parameter object, or one nobody outside the vendor can see. A T8 rule set *has*
parameters and they *are* visible, so the grammar admits the verb. The refusal
lives one layer down, in the runtime that would have to perform the fit:

```
[wrong_verb] a rule set is authored rather than fitted, and the warrant's
verb is 'fit'
→ issue a warrant whose verb is 'score'; a change to the rules is a new
  parameter set somebody approves, not a fit
```

**The control holds** — the fit cannot execute. But MAYA issues authority for an
operation no runtime can carry out, and the two layers disagree about whether
the request was admissible. The grammar is the layer that should have said no.
The case study prints this rather than hiding it, and the warrant is saved to
`warrant-training.json` as *issued and unusable*.

---

## 4. The rule-set editor's arc

MAYA gives an author four verbs, and the script walks all of them.

### `check` — validate against the version's schemas

```
✓ refused as it should be: a rule reading 'applicant_postcode', which the
  version does not declare
```

A rule reading a field the version's `input_schema` does not declare is
**refused**, not warned about. So are a rule that can never fire and two rules
that contradict each other. The reasoning is worth quoting:

> a rule that never fires still appears in the model card and in every committee
> paper and nobody reading either can tell

### `trial` — run a draft over sample rows

No warrant, no entitlement, nothing recorded — an author reading their own draft
back. Deliberately *not* `/execute`, because nothing is being scored and giving
it an authority would have meant inventing one.

It reports **`never_fired`**:

```
✓ MAYA: 8 rows tried; rules that never fired: no_valuation
```

`no_valuation` never fires here because every application in the sample has a
valuation. That is fine and expected — but the general lesson is the one to
state: a set where most rules fire on nothing realistic is one somebody should
look at before approving, not after.

### `publish` — record it as a parameter set

Lands **proposed**. Self-approval refused.

### `explain` — the rule set in English

```
1. when property_value is not supplied, then decision = refer — no property
   valuation is available, so combined loan-to-value cannot be computed...
2. when cltv is greater than 0.85, then decision = decline — combined LTV above
   85% is outside the board-approved appetite for second-lien secured lending...
...
otherwise, decision = approve
```

**One rendering**, so the model card, the committee paper and the export pack
quote the same sentences. Three renderings would differ, and the difference is
exactly where a misreading survives.

---

## 5. Reuse: the valuation is another model's output

`property_value` is not observed. It is the output of
`retail.collateral.home_value` (case study 2), written back as a feature and
read here — so the `input_to` edge carries something and the blast radius
answers what a change to the valuation model reaches.

This is a real dependency with a real consequence: **the CLTV limit is only as
good as the valuation model.** If that model is biased upward by 5%, every
CLTV in the book is understated and the 85% policy limit is not the limit
anybody approved. MAYA cannot detect that, but it can make the dependency
impossible to lose.

`cltv` itself is a **derived feature** with one definition in the catalogue:

```python
maya.features.derive(name="cltv",
    expression="(first_lien_balance + line_requested) / property_value")
```

A CLTV computed differently in two systems — one using the drawn balance, one
the committed line — is the ordinary way a policy limit turns out not to have
been applied.

---

## 6. The decisions

```
application    CLTV  FICO   DTI  decision matched rule
HEL-001        0.64   762  0.31  approve  (otherwise)
HEL-002        0.97   715  0.38  decline  cltv_outside_appetite
HEL-003        0.72   641  0.29  decline  fico_below_floor
HEL-004        0.78   688  0.47  refer    dti_above_limit
HEL-005        0.73   704  0.33  refer    investment_property
HEL-006        0.81   673  0.35  refer    thin_file_high_cltv
HEL-007        0.58   801  0.22  approve  (otherwise)
HEL-008        0.90   745  0.40  decline  cltv_outside_appetite
```

Two things to point at:

**HEL-008 has a 745 FICO and is declined.** Strong borrower, unacceptable
leverage. A scorecard would probably have approved it; the policy does not,
because the limit is about the institution's appetite for second-lien exposure
rather than about this borrower's propensity to pay.

**HEL-006 is the interaction rule.** CLTV 0.81 passes the 0.85 limit and FICO
673 passes the 660 floor — it fails neither test alone and is referred by the
rule that considers them together.

Every decision carries `matched_rule` and `because`, and those travel even when
the output schema does not declare them, because under most consumer-credit
regimes **the explanation is the obligation, not the decision**.

---

## 7. What this case study does not model

Named, because a HELOC demo that stopped at eligibility would be leaving out
most of the risk:

- **No line assignment.** How *much* to offer is a separate model.
- **No CCF / utilisation.** The exposure question from §1 — how much of an
  undrawn line is drawn by default — is the hard part of HELOC EAD and is not
  here.
- **No end-of-draw payment shock.** The largest single driver of HELOC loss in
  the last cycle.
- **No behavioural scoring** over the life of the line.
- **No lifetime CLTV.** The policy is applied at origination only.

Each of those is a separate model that would sit in the register beside this
one, sharing the `heloc_application` entity and reusing its features — which is
the pattern case study 5 demonstrates.

---

## 8. Things to try live

**Change a threshold.** Set `MAX_CLTV = 0.80` and re-run. You get a **new
parameter set**, proposed, needing a second person — and the model version is
untouched, because the policy is the parameter object.

**Reorder two rules** and watch the digest change while reformatting does not.
Order is meaning.

**Delete an `otherwise`** and watch `check` refuse the document.

**Delete a `because`** and watch the same thing happen.

**Ask what a change to the valuation model reaches:**

```bash
curl -s -u admin:maya-admin-dev -X POST \
  http://127.0.0.1:5006/api/v1/blast-radius \
  -H 'content-type: application/json' \
  -d '{"urn":"maya://model/retail.collateral.home_value"}'
```

---

## 9. Questions this case study answers well

**"Our credit policy isn't a model."**
It decides who gets credit and has to be explained to whoever is refused. This
is the case study for that conversation.

**"How do we change a threshold without a full revalidation?"**
It is a new parameter set, approved by a second person. The version and its
schemas are unchanged.

**"Can we show a supervisor the policy as it stood in March?"**
Yes — the parameter set is versioned and digested, and `explain` renders any of
them in English.

**"Where do adverse-action reasons come from?"**
The `because` on the rule that fired, which MAYA requires and which travels
with every decision.

---

## 10. Files this produces

| File | What it is |
|---|---|
| `warrant-training.json` | The fit warrant — **issued and unusable**; see §3 |
| `warrant-execution.json` | The execution warrant, naming the approved rule set |
| `heloc-eligibility-specification.tex` | Specification, with the policy table |

```bash
pdflatex heloc-eligibility-specification.tex
```
