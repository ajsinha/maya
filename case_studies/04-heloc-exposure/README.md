# Case study 4 — HELOC exposure at default, as a composite of two models

**Domain:** banking, retail secured credit · **Model type:** a **composite router** over two
fitted members with *different functional forms* · **What it exercises:** §8.7's composite
model — one warrant, one feature set, a parameter set per member, a seal that waits for every
member, an input contract MAYA works out for itself, and maturity capped at the least mature
member.

## The scripts, and what each one does

Eight scripts, in this order, sharing the project's MAYA — the estate `config/application.yaml` configures, shared by every study, in which this study is the `heloc` namespace —. Each runs on
its own, in its own process.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes the tape and the realised exposure to `data/` (committed; run it only to regenerate). No MAYA. | The recipe: two behavioural regimes, one of which draws down and one of which amortises. |
| `setup_features.py` | Declares and ingests the two feeds, approved by someone other than their author. | The two amounts that matter and are easy to confuse: the **commitment** the bank promised and the **drawn** balance it actually lent. |
| `setup_featureset.py` | Composes `heloc_panel` on `(date, account)` — both regimes, the regime flag, and the target — and pins it. | Both regimes in one panel and one pin, because the router selects per row and two feature sets would make one warrant impossible. |
| `setup_members.py` | Registers and approves the two member models, each with its own specification document. | A member is a model in its own right: own version, own contract, own document, own approval — before anything composes it. |
| `setup_composite.py` | Registers the composite of kind `router`, prints the contract **MAYA computed**, gets it approved, then tries to compose a member that is still a draft. | The union contract nobody maintains; maturity capped at the members; **a composite over an unapproved member refused**. |
| `get_training_warrant.py` | Draws one warrant over the composite against the pinned panel, and shows how the two regimes divide the data. | §8.7's "trains under **one** warrant against **one** feature set", and the two regimes' realised means — one positive, one negative. |
| `fit_parameters.py` | Fits each member on its own rows, uploads a parameter set **per member alias**, tries to seal with one member fitted, then seals and scores blind. | **A seal that refuses while a member is unfitted.** Blind scoring in currency, with the benchmark scored by MAYA on the same escrowed rows. |
| `get_execution_warrant.py` | Takes it live with the output-range covenant the repayment member's own document asks for, then reports a batch with a negative exposure. | A weakness written into a document is a sentence; written into a covenant it is a control. |
| `show_estate.py` | Creates nothing. Reads the catalog, the members and their maturities, both parameter sets, both holdout attempts, the lineage and the audit chain. | The composite's structure visible in the lineage graph, above its members and below its warrant. |
| `study.py` | No MAYA calls: names, definitions, both formulas, the combiner as an IR node, three specification documents, the fitting mathematics, the cast. | The declarations that would live under source control. |
| `run.py` | All eight steps against a MAYA built from nothing. About five seconds. | The unattended pass. |

```bash
.venv/bin/python case_studies/04-heloc-exposure/run.py                        # the whole story
.venv/bin/python case_studies/04-heloc-exposure/setup_features.py --reset     # or step by step
```

---

## 1. The business problem

A home equity line of credit is a **commitment**, not a loan. The bank has promised money it
has not yet lent; the borrower decides when to take it. So the bank's exposure is not a
balance to read off a tape — it is a forecast.

The quantity is **exposure at default**: what would be owed if the borrower defaulted, which
is more than the balance drawn today because a committed line can still be drawn down. It
feeds credit risk capital, the exposure input to expected credit loss, and liquidity
planning on committed facilities.

Here is the data:

| | Draw period | Repayment |
| --- | --- | --- |
| Rows | 5,864 | 4,456 |
| Mean realised twelve-month draw fraction | **+0.190** | **−0.087** |

One regime draws down. The other pays down. **A single model with an interaction term would
average those together and be wrong about both** — and, worse, a logistic form could not
produce the negative number at all. That is the argument for a composite, and it is an
argument about the mathematics rather than about the coefficients.

## 2. The data

| File | Rows | Size | What it is |
| --- | --- | --- | --- |
| `data/heloc_month.csv` | 10,320 | 0.81 MB | The monthly tape: commitment, drawn, combined loan-to-value, rate, seasoning, and the regime flag. Cut three business days after month end. |
| `data/exposure_later.csv` | 10,320 | 0.50 MB | The drawn balance twelve months later. The target, unknowable until those twelve months have passed. |

430 accounts over twenty-four months, 2023-01 to 2024-12; £58m committed, £31m drawn, mean
utilisation 49%. Every account's path is simulated for a further twelve months so that each
observation month has a realised outcome.

## 3. Two members, two shapes

**The draw-period member** is a logistic:

$$
E = 1 - \ell, \quad R = \frac{C - D}{C}, \quad \rho = 100r - 8, \quad
f = \frac{1}{1 + e^{-(\delta_0 + \delta_E E + \delta_R R + \delta_\rho \rho)}}
$$

for combined loan-to-value $\ell$, commitment $C$, drawn balance $D$ and rate $r$. The
logistic is chosen because the quantity is a fraction of a known amount: it cannot be
negative and cannot exceed one, and **those bounds are a property of the problem rather than
a convenience.**

**The repayment member** is linear:

$$f = \rho_0 + \rho_E E$$

and its document says why, in as many words: the quantity is negative, a logistic cannot
produce a negative number, and forcing both regimes through one form would be wrong about at
least one of them. It also says what being linear costs — the form is unbounded, so far
outside the fitted range of equity it returns a fraction below minus one, which is
arithmetically impossible — and names the control that stops that reaching a balance sheet.
Section 7 trips that control.

Each member is registered and approved **before** the composite exists, with its own
specification document. A member is not a fragment.

## 4. The composite, and the contract nobody maintains

```
ead = drawn + where(inDraw, draw.leq, repay.leq) * (commitment - drawn)
```

Exposure at default is what is already drawn plus the part of the remaining line the
borrower is expected to take, and which fraction applies depends on the regime. The combiner
is written as an IR node rather than a formula string, because it refers to a member's output
by alias (`draw.leq`) and the formula syntax does not spell that.

Registered as `kind="composite"` with `composite.kind = "router"` and
`train: {mode: parallel}` — parallel because neither member consumes the other's output.

MAYA then computes the input contract:

```
cltv, commitment, drawn, inDraw, rate
```

**Nobody wrote that list down.** It is the union of the two members' contracts (`cltv`,
`commitment`, `drawn`, `rate`) plus what the combiner itself reads (`commitment`, `drawn`,
`inDraw`). `show_estate.py` prints which member needs each one:

```
cltv         needed by draw, repay
commitment   needed by draw, combine
drawn        needed by draw, combine
inDraw       needed by combine
rate         needed by draw
```

That `inDraw` row is there because of this study. MAYA's union contract previously took only
the *members'* contracts, so the composite declared a contract that omitted an input it
genuinely required — and then failed during evaluation for something the contract check had
already passed. Both halves are fixed: the contract includes the combiner's own references,
and the evaluator builds its inputs from the composite's contract rather than re-deriving a
narrower one.

### And a refusal

The step then builds a second composite over a member that is still a draft:

```
NotApproved: Blocked by check(s): composite_members_mature —
  members still experimental: draw
```

A composite is capped at the maturity of its least mature member, so a member nobody has
approved is not something to build production on.

## 5. One warrant, two fits, and a seal that waits

The warrant is drawn over the composite against the pinned panel — §8.7's promise that a
composite "trains and executes under **one** warrant against **one** feature set". Its
contract report resolves all five inputs; its leakage certificate carries the same
forward-looking-target exception as the other studies (the target is a balance twelve months
later); 1,491 rows are escrowed.

It hands over 8,829 rows, and the two regimes divide them 4,999 / 3,830.

Each member is fitted on its own regime's rows and uploaded as **its own parameter set**,
tagged with the member alias it belongs to. On this run:

| | | |
| --- | --- | --- |
| `draw.d0` | −2.8663 | |
| `draw.dEq` | +1.1514 | more equity, more drawing |
| `draw.dRoom` | +2.2972 | more room on the line, more drawing |
| `draw.dRate` | −0.0892 | dearer money, less drawing |
| `repay.r0` | −0.1047 | |
| `repay.rEq` | +0.0541 | |

Note what the study **does not** do with those numbers: it does not compare them against the
coefficients in `make_data.py`. The book is generated month by month and these members are
twelve-month reduced forms, so the two sets of numbers are in different units and comparing
them would be a category error. Studies 1 and 3 can make that comparison; this one cannot,
and says so rather than printing a table that invites a false conclusion. What *is* checked
is that every sign matches what the specification commits to, and that each member
reproduces its own regime's mean.

### The refusal that makes composite governance worth having

With only the draw member fitted, sealing the warrant is refused:

```
NotApproved: A trainable model's warrant seals only with an approved parameter set;
  still to fit: repay
```

A composite that reached production with one member fitted and the other left at whatever it
happened to have would be the easiest possible way to ship a wrong number, and it would be
invisible — the composite has one version, one document and one approval, and nothing on its
face would say that half of it was stale.

## 6. Blind scoring, with a benchmark scored the same way

MAYA scores the **composite** against the realised exposure, in currency, on 1,491 escrowed
rows:

| | RMSE | MAE |
| --- | --- | --- |
| The model | **£5,362** | £3,431 |
| "Exposure does not change" | £13,982 | £10,045 |

an **85.3% reduction in mean squared error**.

The benchmark is worth a sentence, because getting it honestly took some care. Rather than
compute it on rows the developer can see, the study scores the *same warrant* a second time
with parameters that make both members return a zero draw fraction — so the prediction is
exactly today's drawn balance, produced through the same code path, against the same
escrowed rows. It costs a holdout attempt, and MAYA counts it: `show_estate.py` reports both
attempts, so the benchmark run is on the record rather than a number in a README.

## 7. Live, and an exposure that cannot be right

```python
covenants = [
    {"kind": "output_range", "min": 0.0, "max": 2_000_000.0},  # no attr: MAYA names it
    {"kind": "input_psi", "attr": "cltv", "max": 0.25},
    {"kind": "input_null_rate", "attr": "commitment", "max": 0.001},
]
```

The first is the guard the repayment member's own document asked for by name. It is declared
with no `attr`, and MAYA fills in `ead` — the composite declares one output, so there is one
candidate. This study is why: a covenant naming nothing was compared against nothing and
could never breach, which is worse than no covenant, because it appears on the warrant and
in the manifest and controls nothing. An `output_range` covenant on a multi-output model is
now refused until it says which output, and `input_range` and `input_null_rate` are refused
without an attribute too.

Then a batch whose minimum output is −£41,250, which is not a small exposure but a number
that cannot be an exposure at all:

```
WarrantSuspended: Warrant suspended: 'ead' min -41250.0 below 0.0.
  Contact retail.secured.risk@example.com.
```

Reinstated with what was actually done about it — *"traced to 41 accounts whose combined
loan-to-value exceeds the repayment member's fitted range; the calling system now floors the
fraction at zero and the member is scheduled for a bounded reformulation in the next
version"*. The reason is the governance; the model coming back is the easy part.

## 8. What the estate holds

```
maya://model/heloc/usage_draw_period@v1  --composite_member (draw)-->   maya://model/heloc/ead_heloc@v1
maya://model/heloc/usage_repayment@v1    --composite_member (repay)-->  maya://model/heloc/ead_heloc@v1
maya://model/heloc/ead_heloc@v1          --trained_on (model)-->        maya://warrant/train/heloc/ead_fit_2025h1@v1
…                                        --parameterized_by-->          two parameter sets
maya://warrant/train/heloc/ead_fit_2025h1@v1 --executed_under-->        maya://warrant/exec/heloc/ead_heloc_live@v1
```

12 nodes, and the composite's structure is *in* the graph: two `composite_member` edges
coming in, labelled with their aliases, and a warrant going out. 74 audit entries, chain
verified unbroken.

## 9. What to point at when demonstrating this

1. **§1's table** — one regime draws down and one pays down. The composite is not an
   architectural flourish; a single form would be wrong about one of them.
2. **§4's contract** — five inputs, computed, with each one's `needed_by` recorded. Nobody
   maintains that list, and this study is why it is now correct.
3. **§5's seal refusal** — half a composite cannot go to production, and nothing on the
   composite's face would otherwise have said so.
4. **§6's benchmark** — the comparison was scored by MAYA on the same escrowed rows, and both
   attempts are on the record.
5. **§7** — a weakness the model's own document predicted, caught by a covenant that MAYA had
   to be taught to name.

## 10. What this study deliberately does not do

It is a **usage** model, not a regulatory loan-equivalent model. A Basel-compliant LEQ is
estimated on accounts that actually defaulted; this one is estimated on all accounts, which
makes it right for stress and liquidity work and wrong for regulatory exposure at default
without a separate conditional adjustment. That is the single most important sentence in the
composite's specification, and it is in *Scope and Limitations* where somebody will find it.

It also inherits both members' weaknesses — a stale valuation, no measure of borrower
distress, an unbounded repayment member, and a twelve-month reduced form over monthly
behaviour — and in a liquidity event the independence assumption fails in the direction that
matters, understating exposure exactly when the number is needed.
