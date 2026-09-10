# Case study 14 — A VaR model swapped mid-crisis

**T2 — estimated.** The one case study in this suite that was **not designed to
fit MAYA.**

---

## Why this one exists

Every other case study here was written by the person who wrote the platform.
That is the weakness the accompanying research paper names as its principal
missing evidence: a demonstration built by its own author shows sufficiency and
very little else. You cannot fix that by building a fourteenth demonstration
the same way.

So this one is taken from the public record instead. It reconstructs the model
governance failure at the centre of the 2012 JPMorgan Chief Investment Office
losses — the "London Whale" — and walks it into whatever MAYA happens to do.
**The sequence is theirs. The controls are the platform's. Nothing about the
shape of the failure was chosen to make the platform look good**, and the last
section of the script is a list of the parts it does not reach.

### Sources

The qualitative sequence below is from the public record:

- JPMorgan Chase & Co. **Report of JPMorgan Chase & Co. Management Task Force
  Regarding 2012 CIO Losses**, 16 January 2013.
- United States Senate Permanent Subcommittee on Investigations. **JPMorgan
  Chase Whale Trades: A Case History of Derivatives Risks and Abuses**,
  15 March 2013.
- Subsequent OCC and Federal Reserve consent orders, 2013.

**The numbers in the script are a reconstruction**, sized to be realistic and
deterministic. They are not the firm's data. The reconstruction produces a 52%
fall in reported VaR on the same book on the same day, which is about the
halving the reports describe. MAYA is being shown a *shape of failure*, not
audited against a balance sheet.

---

## The theory

A historical-simulation Value at Risk model asks one question:

> Over the observed past, how bad was the 1-in-100 day?

$$\mathrm{VaR}_{99,1d} \;=\; \Bigl| Q_{0.01}\Bigl(\textstyle\sum_i w_i\, r_{i,t}\Bigr) \Bigr| \times N$$

There is no distributional assumption — that is the appeal. The portfolio's
weighted return is computed for each day in a lookback window, the series is
sorted, and the loss quantile is read off. Two choices decide everything:

1. **The lookback window.** 260 days, 120 days, exponentially weighted. Longer
   windows carry old stress; shorter windows forget it.
2. **The weighting.** Equal, or decaying toward the present.

**Both choices are legitimate. Neither is more correct in general.** And that
is the whole difficulty: two defensible models can report numbers that differ
by a factor of two on the same book on the same day, and the difference is a
modelling choice rather than an error anybody can point at.

### Where it is known to be wrong

- **It cannot see a risk the window did not contain.** A position that has never
  moved has no measured risk, right up until it does.
- **The quantile is estimated from a handful of observations.** At 99% over 260
  days, the number is the second or third worst day — an order statistic with
  enormous sampling error.
- **It is not sub-additive.** Historical-simulation VaR can report that a
  diversified portfolio is riskier than its parts, which is a known defect and
  the reason expected shortfall exists.

---

## What happened, in the order it happened

1. A synthetic credit portfolio **breached its VaR limit** in January 2012.
2. A new VaR model was already in development. It was **put into production
   days later**. Reported VaR fell by roughly half. The breach disappeared.
3. The model had been **approved subject to further work that was not
   completed**.
4. It was implemented as a **chain of spreadsheets with manual copy-and-paste**
   between them.
5. One of those spreadsheets **divided by the sum of two rates where it should
   have divided by their average**, understating volatility.
6. The portfolio lost about **$6.2bn**.
7. Regulators required remediation under **consent orders with dates the firm
   committed to**.

---

## Six governance questions, and MAYA answers five

| | Question | MAYA | Where |
|---|---|---|---|
| **0** | May the replacement even be *registered*? | **Refused** — an attested record is immutable. Open an amendment | not planned; see below |
| **1** | Is replacing a VaR model a material change? | **Computed**, not asked. `material`, and the reasons name the loosened guarantee | `core/lifecycle/changes.py` |
| **2** | May the alias move without revalidation? | **Refused** — an alias may only point at an approved version | `core/registry/aliases.py` |
| **3** | Does swapping the model close the breach? | **No.** The finding survives the swap and keeps blocking | `core/monitoring/breaches.py` |
| **4** | Does "approved subject to further work" bind? | **Yes**, and it expires. `validated_by` is *enforced* | `core/lifecycle/conditions.py` |
| **5** | Does the spreadsheet agree with the model? | **Answerable** — and the *shape* of the disagreement, not a pass rate | `core/validation/recode.py` |
| **6** | Is the arithmetic inside the spreadsheet right? | **No. It cannot see this.** | — |

### Question 0 was not in the plan

The script was written expecting to demonstrate questions 1 through 6. It got a
refusal it did not expect:

```
cannot add a version to maya://model/market.var.synthetic_credit:
this model is attested and therefore immutable; open an amendment to change it
```

An attested model record cannot simply acquire a new version. Somebody has to
open an **amendment**, with a name on it and a stated scope, and that act goes
on the evidence chain. In the failure this reconstructs, the new model went into
production days after the breach and *the question of what was being amended was
never put*.

That refusal is a stronger control than the one this case study set out to show,
and it is here because the scenario was somebody else's. A case study designed
to fit the platform would not have found it.

### Question 3 is the sharpest one

A VaR breach is a fact about the **portfolio**. A model that reports a smaller
number has not made the portfolio safer.

MAYA closes a *breach* when the monitor recovers and deliberately leaves the
*finding* open — the model having recovered is not the same as somebody having
looked at why it degraded. Here the model did not even recover. It was replaced,
and the finding is still open and still blocking.

### Question 5 is conditional, and the condition matters

The recode harness reports:

```
0 of 24 agreed, 24 did not
shape: systematic
100% of outputs disagree, by a typical 50.00% of their own magnitude.
That is not a numerical artefact: the two implementations are computing
different things, and the specification is where to look first.
```

A pass rate would have said 0% and stopped. The **shape** is what separates *a
branch nobody tested* from *a floating-point tail* from *two implementations of
two different specifications*.

But note the conditional: **somebody has to run it.** The register cannot make
them.

---

## What MAYA would not have caught

This is the section a demonstration usually omits, and it is the reason to run
somebody else's failure rather than your own.

- **The divide-by-sum error inside the cell.** MAYA does not run models and does
  not read spreadsheets.
- **The manual copy-and-paste between spreadsheets.** There is no artifact
  digest for a process that lives in a person's hands. A model whose
  implementation is a sequence of human steps is outside what any register can
  bind.
- **The trader marks.** The losses were also a valuation dispute. MAYA holds a
  model's declared boundaries, not the marks a desk puts on a position.
- **Whether anybody read the finding.** It stayed open, it blocked promotion, it
  went on a worklist. Escalation past that point is a management act, and this
  platform's own documentation says a control nobody reads is not a control.

Four of the seven links in this failure chain are outside the platform. That is
the honest answer, and a firm adopting a register needs it before it adopts one.

---

## Running it

```bash
python case_studies/14_var_model_change/build.py
```

It is re-runnable. Every step asks before it acts, and the refusals it
demonstrates are refusals whether or not the state is already there.

It writes `var-model-change.tex` (and a PDF if you run `pdflatex`) and
`case-14-summary.json` with the reconstruction's numbers.

---

## What this case study changed in the platform

Running it found two things, which is the suite working as intended:

1. **A wording defect in the supervisory register.** With an internal plan
   landing five months after the committed date, `core/validation/supervisory.py`
   reported `-163 day(s) apart, inside the 14 days closure verification needs` —
   arithmetically true, and it reads as a near miss. A plan that misses a
   regulatory commitment by five months is not a near miss. There is now a
   separate branch that says so.
2. **The MRM cannot issue warrants.** The script tried, was refused, and was
   right to be: `warrant:issue` sits with the first line. The second line
   revokes and never grants.

