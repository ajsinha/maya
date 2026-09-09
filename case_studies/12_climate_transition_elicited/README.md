# Case study 12 — An elicited climate transition scorecard, and a dissent that is part of the number

> **The demo in one sentence.** Five experts, one mean, and one of them
> disagreed — and MAYA carries the disagreement on the parameter set, priced,
> instead of in a committee minute nobody reads.

```bash
.venv/bin/python case_studies/12_climate_transition_elicited/build.py
```

Independent of the other case studies. Runs in about fifteen seconds.

---

## 1. The theory

### Why these parameters cannot be estimated

A transition risk model asks how badly a sector is exposed to a decarbonising
economy. The obvious approach is to regress sector defaults on emissions
intensity and read off the coefficients.

It fails for a reason no quantity of data repairs: **the transition has not
happened yet.**

There is no history of a 2035 carbon price, because there has not been one. No
sector has yet defaulted *because* its assets were stranded by a phase-out date
that has not arrived. Estimating from 2015–2025 defaults produces a careful,
well-diagnosed, high-R² model of the world that is ending.

This is the honest home of **T7 — Expert judgment**. Not "we could not be
bothered to fit it", but *the quantity being estimated has no realisations
yet*, and a panel of people who understand the mechanism is the best available
instrument.

MAYA derives T7 from `elicited_weights` inhabited by `elicit`.

### The model

```
transition_score = Σ_k  w_k · factor_k          w elicited, not estimated
```

Five factors, each scored 0–100 where 100 is worst:

| Factor | What it measures |
|---|---|
| `emissions_intensity` | scope 1 and 2 emissions per unit of revenue, against the sector median |
| `capex_alignment` | share of planned capex consistent with a 1.5 °C pathway, **inverted** |
| `policy_exposure` | share of revenue in jurisdictions with a legislated carbon price or phase-out date |
| `technology_substitutability` | how readily a low-carbon substitute exists at scale today, **inverted** |
| `contract_duration` | weighted average remaining contract life — long contracts lock in exposure a repricing cannot reach |

The two "inverted" notes are not pedantry. **Half the disagreement in a badly
run elicitation is two experts scoring the same sector at opposite ends of the
same axis**, because nobody wrote down which direction was bad. The scale
direction is declared in the script before any expert is asked anything.

### What an elicitation actually owes

T7's fibre in MAYA asks for soundness evidence as:

> *"panel composition, the questions asked, and the dissent"*

Not a fit statistic — there is nothing fitted. Not a back-test — there are no
outcomes. Those three things, because without them **an elicitation is an
assertion with a decimal point on it.**

So this case study carries all three, on the parameter set:

1. **The panel**, by discipline.
2. **Every expert's individual return**, not just the mean.
3. **The dissent**, verbatim.

---

## 2. The panel

```
                                     E1     E2     E3     E4     E5    mean   range
emissions_intensity                  30     20     15     25     15    21.0      15
capex_alignment                      25     30     20     25     20    24.0      10
policy_exposure                      15     30     20     20     40    25.0      25
technology_substitutability          25     10     15     20     15    17.0      15
contract_duration                     5     10     30     10     10    13.0      25
```

| | Discipline | Coverage |
|---|---|---|
| E1 | climate scientist | physical and transition pathway modelling |
| E2 | energy economist | carbon pricing and stranded asset valuation |
| E3 | credit risk | wholesale obligor rating and loss estimation |
| E4 | sector analyst | utilities, materials and transport coverage |
| E5 | policy and regulatory affairs | EU and UK climate legislation |

**Composition is the first thing a reviewer should interrogate.** A panel of
five credit officers is one opinion held five times. This panel disagrees
because it contains people who look at the problem from incompatible angles —
which is the point of convening one, and the reason the spread is not a defect.

### Kendall's W

```
W = 12·S / (m²·(n³ − n))              W = 0.304
```

*m* raters rank *n* items; *S* is the sum of squared deviations of each item's
rank sum from the mean rank sum. **W = 1** is unanimity on the ordering; **W =
0** is chance.

**0.304 is weak agreement**, and the script says so in as many words: *"the mean
is a compromise, not a consensus."*

Two design notes worth defending in a demo:

- **Ranks, not weights.** Two experts who agree that policy matters most and
  duration least, but differ on magnitudes, have agreed about what the
  scorecard is *sensitive to*. That is the agreement that matters.
- **Ties are averaged.** E3 gave `capex` and `policy` both 20. Ranking them
  arbitrarily would manufacture an ordering the expert did not express, and
  would inflate W. Averaged ranks are one line of code and the difference
  between a statistic and a flattering one.

### The spread column, and why it is reported

A mean of 17 built from `{25, 10, 15, 20, 15}` and a mean of 17 built from
`{17, 17, 17, 17, 17}` are **the same number and not the same fact**. Only one
of them is a consensus.

The widest disagreements here are on `policy_exposure` (25 points) and
`contract_duration` (25 points) — the policy specialist weights policy at 40
while the climate scientist weights it at 15, and the credit officer weights
duration at 30 while everyone else is near 10. Those are not errors. They are
what each discipline can see.

---

## 3. The dissent

E1 signed the elicitation **and** recorded a reservation:

> *"I weighted technology substitutability at 25 against a panel mean of 17.
> The panel is anchoring on the cost of low-carbon substitutes TODAY. Every
> previous panel that did this — on solar, on batteries, on onshore wind — was
> wrong in the same direction, because learning curves are exponential and
> expert forecasts of them are linear. A sector I would call substitutable in
> eight years is being scored as locked in. I expect this weight to be revised
> upward at the first re-elicitation and I would rather the record showed I
> said so."*

**A panel output that reports a mean and not this has been rounded into
agreement.**

### The dissent is priced

The script scores every sector twice — once under the panel mean, once with
E1's weight upheld and the rest renormalised:

```
sector                             score  if E1 upheld   move
Oil and gas extraction              78.9          79.4   +0.5
Coal-fired power generation         86.3          85.1   -1.2
Cement manufacturing                70.2          71.6   +1.5
Primary steel                       69.4          70.6   +1.2
Passenger aviation                  60.9          62.9   +2.0
Deep-sea shipping                   59.1          60.7   +1.5
Automotive manufacturing            46.4          45.2   -1.2
Renewable power generation          22.1          21.6   -0.5
Enterprise software                  8.9           8.6   -0.3
```

This is only possible because the record kept the **individual returns**, not
just the mean. A dissent recorded as prose is a sentence somebody can argue
with; a dissent recorded alongside the numbers that produced it is a
counterfactual anybody can compute.

### The acceptance acts on it

```python
people["s.iqbal"].parameters.review(
    parameter_set_id, accept=True,
    note="Accepted for concentration limits and pricing guidance, NOT for
          individual obligor ratings. E1's dissent on technology
          substitutability is noted and is the reason the re-elicitation date
          is twelve months rather than the usual three years.")
```

**A dissent nobody acts on is a dissent that was recorded in order to be
ignored.** Here it shortens the re-elicitation cycle from three years to
twelve months — a consequence, in the same record as the disagreement.

---

## 4. The refusal: a judgment cannot claim to have been fitted

```python
maya.parameters.record(kind="elicited_weights", values=weights,
                       provenance="fitted", ...)     # refused
```

```
[not_obtained_from_data] this version's parameter object is 'elicited_weights',
which is not a quantity data produces, so it cannot have been fitted
→ record it with provenance 'declared' — the honest word for parameters a
  person asserted — and put the panel, the procedure or the configuration in
  the diagnostics
```

The same refusal covers `calibrated`, which is the lesser lie and still one.
For these three kinds, `declared` is the only admissible provenance.

**This is the tempting one.** The numbers look exactly like coefficients. They
are floats that sum to one. The column accepts them. The row reads identically
on every screen downstream.

And that is precisely the harm: `fitted` is the strongest claim the register
offers — *estimated from data, under a warrant MAYA issued* — so claiming it
for a judgment **launders an opinion into a measurement**. After which nobody
goes looking for the panel, the questions or the dissent, because the record
already told them the numbers came from data.

> **A note on demonstrating this honestly.** The script supplies the featureset,
> its version, the window and the as-of on the *refused* call as well. Without
> them the request is refused first with `featureset_required` — a correct
> refusal for a different reason, which would have demonstrated the wrong
> control. This bit us while writing the case study, and it is worth watching
> for in your own.

Three parameter kinds are covered by this rule, and none of them is a quantity
data produces:

| Kind | Filled by | Case study |
|---|---|---|
| `rule_set` | an author | 6 (HELOC eligibility) |
| `llm_configuration` | somebody assembling a system | 11 (RAG assistant) |
| `elicited_weights` | a panel | **12 (this one)** |

`none` and `opaque` were already refused, each with its own sentence — see
case studies 4 and 8.

### And no warrant

The declared set is recorded with `warrant_id="none"`. A warrant answers *which
data produced these numbers*, and for a panel's judgment the honest answer is
that **no data did**. Borrowing the lab grant to fill the field would have been
a small lie in a field built to prevent one.

---

## 5. What can and cannot be monitored

There is no back-test. Transition outcomes are not observable yet — the same
fact that made the weights elicited in the first place. So what *is* the
empirical handle?

T7's fibre answers it: **the override rate**, and specifically *"whether the
judgment is being overridden in one direction."*

- A scorecard overridden 5% of the time is being used.
- A scorecard overridden 60% of the time is being worked around.
- A scorecard overridden 60% of the time **and always downward** is a scorecard
  whose weights the front line has quietly replaced with their own.

That last one is measurable **years before any transition outcome arrives**,
and it is the single most useful number about a judgment-based model. Nothing
about it requires the future to have happened.

---

## 6. Two clocks, nine months apart

| Clock | Value |
|---|---|
| `event_ts` | the period the figure describes |
| `ingest_ts` | roughly **nine months** later, when it was disclosed |

Emissions data reaches a bank long after the year it describes, because it
arrives through annual reporting. Policy data arrives the day it is legislated.
**The lag is not one number**, and a scorecard computed "as of" a date must not
use a disclosure that had not been made.

Same rule as case study 3's servicer lag and case study 10's notifiable-disease
reporting delay, at a different timescale.

---

## 7. Setting up the people

The script creates them if they do not exist (`_common/casekit.py`):

| Login | Name | Role | Does here |
|---|---|---|---|
| `a.mehta` | Anika Mehta | `model_developer` | runs the elicitation, delivers the weights |
| `j.okafor` | Jide Okafor | `model_owner` | owns the model |
| `s.iqbal` | Sana Iqbal | `model_risk_manager` | **accepts**, and acts on the dissent |
| `v.chen` | Wei Chen | `validator` | second quorum signature |

Manually, if you prefer:

```bash
curl -s -XPOST localhost:5099/api/v1/principals -H 'Content-Type: application/json' \
  -d '{"login":"a.mehta","display_name":"Anika Mehta","roles":["model_developer"],
       "password":"quant-password-long"}'
```

Note that **none of the four is a panel member.** The panel is recorded as data
on the parameter set, not as principals — they were consulted, they did not act
in the platform, and inventing logins for them would put five people in the
access model who never needed one.

---

## 8. What the script does

| Step | Who | What |
|---|---|---|
| 1 | ⚙ engine | Show every expert's return, the mean, the spread, and Kendall's W |
| 2–5 | ✓ MAYA | People; five factors as features; load with both clocks; featureset |
| 6 | ✓ MAYA | Register the model — **T7 derived** — and tier it |
| 7–8 | ✓ MAYA | Quorum approval; put the record in force |
| 9 | ✓ MAYA | Grants — elicit in the lab, score in production |
| 10 | ✓ MAYA | **The refusal** — the same weights, claimed as `fitted` |
| 11 | ✓ MAYA | Record them as `declared`, with panel, protocol, spread, W and dissent |
| 12 | ✓ MAYA | A second person accepts, names the use, and shortens the cycle |
| 13 | ✓ MAYA | Execution warrant |
| 14 | ⚙ engine | Score nine sectors **locally**, twice — mean and dissent |
| 15 | — | Write the LaTeX specification |

MAYA never runs an elicitation and never scores a sector. It registers what the
model is, what the panel said, who disagreed, who accepted it and for what.

---

## 9. The data

**The factor values are illustrative** and the script says so where they are
defined. The sectors are real and their relative ordering is uncontroversial —
coal-fired power above cement above aviation above software — but the numbers
are not drawn from a disclosure database.

**The panel is fictional.** Five named disciplines, invented returns. The
disciplines are chosen to be the ones a real transition-risk elicitation
convenes, and the *pattern* of disagreement is the realistic part: the policy
specialist weights policy highest, the credit officer weights contract duration
highest, and the climate scientist is the one worried about technology curves.

---

## 10. Things to try live

**Make the panel agree.** Set every expert's return equal and re-run. W jumps
to 1.0, the spread collapses to zero, and the reading changes — and the
scorecard is *no better*, it is just no longer telling you that its inputs were
contested. That is the whole argument for reporting the spread.

**Uphold the dissent.** Change E1's weight in `ELICITED` and re-run. Both
columns of the final table move, because both are computed from the same
recorded returns rather than hard-coded.

**Try to record it as `calibrated`.** Also refused, and worth showing after
the `fitted` one, because it is the *lesser* lie: `calibrated` means solved
against market data under an approved procedure, and a panel is not that
either. For these three kinds `declared` is the only admissible answer.

(Guarding `fitted` alone left the middle claim open — which is what writing
this case study found.)

**Drop a discipline.** Remove E5 (policy) and re-run. The policy weight falls
from 25 to about 21, and the coal and oil scores move. A panel's composition
*is* a parameter, and this is what it looks like when it changes.

---

## 11. Questions this case study answers well

**"Where do you put expert judgment?"**
In the same place as a coefficient, with different evidence attached. The
platform does not treat a judgment as second-class — it treats it as a
different *kind* of claim, and refuses to let it be described as the other one.

**"Our climate model has no back-test. Is that a finding?"**
It is a property. The transition has not happened. What is a finding is a
judgment-based model with no override tracking, because that is the one piece
of empirical evidence available and it costs nothing to collect.

**"What happens to the person who disagreed?"**
Their position is on the parameter set, in their words, and the acceptance
cites it. In most institutions it is in a minute in a shared drive, and the
number that reached production carries no trace of it.

---

## 12. Files this produces

| File | What it is |
|---|---|
| `refusal-provenance.json` | A judgment refused the claim of having been fitted |
| `warrant-execution.json` | The execution warrant |
| `transition-scorecard-specification.tex` | Specification, with the panel, W and the dissent |

```bash
pdflatex transition-scorecard-specification.tex     # 3 pages
```
