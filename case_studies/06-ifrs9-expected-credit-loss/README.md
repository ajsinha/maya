# Case study 6 — the IFRS 9 expected credit loss allowance

**Domain:** banking, impairment and financial reporting · **Model type:** a **composite** of
three fitted members with **two parameters of its own** · **What it exercises:** a composite
whose combiner carries the judgements, parameter sets that are decisions rather than fits, a
seal that waits for all five numbers, and a portfolio test that finds something the
per-account error cannot see.

## The scripts, and what each one does

Nine scripts, in this order, sharing one MAYA at `case_studies/runs/impairment/`. Each runs
on its own, in its own process.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes the book and the outcomes to `data/` (committed; run it only to regenerate). No MAYA. | The recipe: a default hazard, a loss rate that falls with collateral, and a drawdown before default. |
| `setup_features.py` | Declares and ingests the two feeds, approved by someone other than their author. | The column most credit feeds lack: the probability of default **at origination**, without which IFRS 9 cannot be applied at all. |
| `setup_featureset.py` | Composes `ecl_panel` on `(date, account)` — eight attributes — and pins it. | One panel and one pin for three members and a combiner. |
| `setup_members.py` | Registers and approves PD, LGD and EAD, each with its own specification document. | Three quantities, three shapes: two logistics because a probability and a loss rate are shares, and a linear interpolation because an exposure has a known floor and ceiling. |
| `setup_composite.py` | Registers the composite, prints the contract MAYA computed, and shows what it made of the combiner's own parameters. | **The contract now carries the combiner's parameters**, which is this study's first finding. |
| `get_training_warrant.py` | One warrant over the whole allowance, with the forward-looking target explained. | A contract check that maps the features and leaves the parameters alone — somebody has to approve those instead. |
| `fit_parameters.py` | Fits the three members on the rows where each quantity exists, then registers the committee's two judgements. | **A seal that refuses while the committee's numbers are missing**, a half-registered decision refused, and a judgement that has no data checksum because it is not a fit. |
| `check_portfolio.py` | The portfolio arithmetic, a grid over the stage threshold, the committee's revision, and two blind figures. | **The heart of the study.** The per-account error cannot see the level of the allowance; the portfolio total can, and it finds a 2.67× over-provision the threshold only partly explains. |
| `get_execution_warrant.py` | Takes it live with a covenant on the stage population, then reports a quarter where arrears have moved. | An allowance is an accounting figure, so the control watches the largest lever nobody decided this quarter. |
| `show_estate.py` | Creates nothing. Reads every number behind the allowance, what was said about each, the custody chain and the audit log. | The question a reviewer of the accounts actually asks, answered. |
| `study.py` | No MAYA calls: names, definitions, three formulas, the combiner as an IR node, four specification documents, the fitting mathematics. | The declarations that would live under source control. |
| `run.py` | All nine steps against a MAYA built from nothing. About ten seconds. | The unattended pass. |

```bash
.venv/bin/python case_studies/06-ifrs9-expected-credit-loss/run.py                      # the whole story
.venv/bin/python case_studies/06-ifrs9-expected-credit-loss/setup_features.py --reset   # or step by step
```

---

## 1. The business problem

IFRS 9 requires a bank to carry an allowance for the credit losses it *expects*, not the ones
it has suffered. For accounts whose credit risk has not increased significantly since they
were written, that is the loss expected over the next twelve months; for those where it has,
it is the loss expected over the remaining life. The figure lands in the financial statements,
so an auditor will ask about it, and the question will not be "is the model good" but **"which
numbers produced this, who approved each of them, and what did they know when they did"**.

Structurally the allowance is a product of three estimates and one judgement:

$$
\mathrm{ECL} = h \cdot \mathrm{PD}_{12} \cdot \mathrm{LGD} \cdot \mathrm{EAD},
\qquad h = \begin{cases} \phi & \text{if } \mathrm{PD}_{12}/\mathrm{PD}_0 > \theta \\ 1 & \text{otherwise} \end{cases}
$$

Three of those are models. Two — the significant-increase threshold $\theta$ and the lifetime
multiple $\phi$ — are not: they are decisions, and they are the ones an impairment committee
actually argues about.

## 2. The data

| File | Rows | Size | What it is |
| --- | --- | --- | --- |
| `data/exposures.csv` | 12,480 | 0.96 MB | Drawn balance, committed limit, collateral, arrears in months, and the probability of default **at origination**. Cut three business days after month end. |
| `data/outcomes.csv` | 12,480 | 0.62 MB | Whether the account defaulted over the next twelve months, the loss rate realised on it, and the money lost. Known a year and a day later. |

520 accounts over twenty-four months, 2023-07 to 2025-06. The realised twelve-month default
rate is **8.41%**, the mean loss rate given default **12.8%**, and total realised loss **£18.3m**.

**92.4% of rows have no loss at all.** That single figure shapes the whole study: it is why §7
argues about what a per-account error statistic can mean, and it is not an artefact of
synthetic data — it is what a credit book looks like.

## 3. Three members, three shapes

| Member | Form | Why that form |
| --- | --- | --- |
| `pd_12m` | Logistic in arrears, utilisation and loan-to-value | A probability is a share; it belongs in [0, 1] |
| `lgd_secured` | Logistic in collateral coverage | A loss rate is also a share. A linear form would predict a negative loss on a well-secured account and a loss above par on a badly secured one, and both are *impossible* rather than merely unlikely |
| `ead_ccf` | `drawn + ccf·(commitment − drawn)` | An exposure has a known floor and ceiling, so the model is an interpolation between them with one parameter — the credit conversion factor, and one of the most argued-over numbers in impairment |

Each is registered and approved with its own specification document before the composite
exists. One of those documents says something worth reading aloud: the LGD member measures
coverage on the balance drawn **today**, while the loss is realised on the exposure at
default, which the third member says is larger. So it overstates coverage and understates
loss, by most on exactly the accounts with the largest undrawn limits. Its *Known Weaknesses*
section names the honest fix — make the coverage read the EAD member's output, which would
make this a pipeline rather than a product — and says it is not done here. §7 comes back to
that.

## 4. The composite, and two parameters that belong to nobody's model

```
sicr = pd.pd12 / pdOrigination
ecl  = where(sicr > sicrThreshold, lifetimeFactor, 1) * pd.pd12 * lgd.lgd * ead.ead
```

MAYA computes the contract:

```
arrears         feature    needed by pd
collateral      feature    needed by lgd, pd
commitment      feature    needed by ead, pd
drawn           feature    needed by ead, lgd, pd
pdOrigination   feature    needed by combine
lifetimeFactor  parameter  needed by combine
sicrThreshold   parameter  needed by combine
```

Those last two rows are this study's **first finding**. A composite can be more than a product
of its members — the weight in a blend, the threshold in a router, the horizon multiple in an
impairment model — and MAYA's union contract took only the *members'* declarations. So the two
numbers an impairment committee argues hardest about were declared nowhere: the bounds check
had nothing to look for, and the warrant would seal without them. They are part of the
composite's contract now, and §5 shows the seal waiting for them.

## 5. One warrant, three fits, two judgements

The warrant covers the whole composite. Its target is the money actually lost over the
following twelve months, so its leakage certificate needs the same written exception as the
other studies — all 12,480 rows violate the rule by construction, and submitting without the
exception is refused.

The three members are fitted on the rows where each quantity exists: the PD member on all
8,761 training rows, the LGD member on the **747** that actually defaulted, and the conversion
factor on the realised exposure of those same accounts. Each gets its own parameter set,
tagged with its member alias.

### The seal waits for all five numbers

```
NotApproved: A trainable model's warrant seals only with an approved parameter set;
  still to fit: the combiner's own parameters
```

### And a judgement is not a fit

Two refusals worth watching. Registering half the committee's decision:

```
ValidationFailed: Parameters out of bounds: missing parameter 'lifetimeFactor'
```

And then the interesting one. The committee's numbers were **not** derived from the rows MAYA
handed over — they are a minuted decision — so the study deliberately uploads them with no
data checksum. MAYA flags the set `unverified_data` and refuses to approve it:

```
NotApproved: Blocked by check(s): data_verified_or_justified —
  unverified_data: the checksum does not match any download MAYA issued;
  approve only with an explicit justification
```

That is exactly right, and quoting the training data's checksum to make the flag go away would
have been a small lie: it would claim the judgement came from that data. The set is approved
with the justification instead — *"Not fitted: these are the impairment committee's judgements,
minuted on 2025-12-11, and there is no MAYA download they could be tied to"* — and the
justification is stored on the set, where `show_estate.py` reads it back.

## 6. Why the per-account error tells you almost nothing

MAYA scores the allowance blind on 1,860 escrowed rows and returns **RMSE £9,598, MAE £4,108**.
Before reading anything into that, consider what it is measuring. Realised loss is zero on more
than nine accounts in ten and tens of thousands of pounds on the rest. An expectation of £900
against an outcome of either £0 or £40,000 produces a large error **whether or not the
expectation is correct**.

So the study asks MAYA for a second blind figure, on the same escrowed rows, with parameters
that drive the probability of default to zero — the allowance you get by holding none at all:

| | RMSE on 1,860 escrowed rows |
| --- | --- |
| The model | £9,499 |
| No allowance at all | **£6,879** |

The model is *worse* by that measure, and it should be. Predicting zero for everybody is the
best per-account guess when nine in ten accounts lose nothing; an expected-loss model
deliberately does not do that. **A per-account error cannot distinguish a well-levelled
allowance from a badly levelled one, and quoting one as accuracy would be misleading.** Both
attempts are on the warrant, so the comparison is on the record rather than in a README.

## 7. The test that can actually fail

The question an expected-loss model has to answer is whether the **sum** of the allowance
matches the **sum** of the loss. On the 10,620 rows the developer can see:

| | |
| --- | --- |
| Allowance the model implies | £42,367,799 |
| Loss actually realised | £15,856,642 |
| **Coverage** | **2.67× the realised loss** |
| Accounts in stage 2 | 8,798 (82.8%) |
| Share of the allowance from stage 2 | 99.5% |

The committee's threshold of 3.0 puts **83% of the book in stage 2**, and almost the entire
allowance comes from the lifetime multiple applied to those accounts. So the study asks what
each threshold would have done:

| threshold | in stage 2 | coverage |
| --- | --- | --- |
| 1.5 | 98.2% | 2.69× |
| 2.0 | 95.2% | 2.69× |
| **3.0** | **82.8%** | **2.67×** |
| 5.0 | 57.3% | 2.55× |
| 8.0 | 37.4% | 2.29× |
| 12.0 | 23.3% | 2.00× |
| 20.0 | 12.1% | 1.63× |
| 40.0 | 4.9% | 1.31× |

Two conclusions, and the second is the one that matters.

**The study refuses to pick the threshold that flatters the total.** Choosing 40.0 because it
minimises the gap would be fitting a judgement to an outcome, and the threshold's whole purpose
is to express a view about credit risk rather than to calibrate a number. If a threshold can be
tuned until the allowance matches last year's losses, it has stopped being a threshold.

**And it would not work anyway.** Even at a fortieth-fold increase in default probability — a
threshold nobody would defend — the allowance is still **31% above** the loss realised on the
same accounts. The threshold explains part of the gap and not the rest of it, so the rest is in
the members.

So the committee settles on **12.0**: a twelve-fold increase in the probability of default
since origination is a defensible reading of "significant" for this book, it puts 23.3% of
accounts in stage 2 — a stage-2 population that can be explained — and coverage is still 2.00×.
That is registered as a **second approved parameter set**, superseding the first, with the
residual recorded as an open finding:

> OPEN FINDING: the residual over-provision of 100% is not explained by the threshold — the
> grid shows it persists at any threshold — and is to be investigated in the members. Two
> candidates are named in their own documents: the loss-given-default member measures collateral
> coverage on the balance drawn today rather than on the exposure at default, and the conversion
> factor is a single figure for the whole book. Neither is fixed in this version and the
> allowance is not to be taken as unbiased.

Both suspects are there in §3, written down before anybody looked at the outcome, and the
fitted conversion factor of **0.349** against the 0.55 that generated the book is consistent
with the second of them.

**Nothing here was fixed by the platform.** MAYA turned a disagreement about the level of the
allowance into a number, attached it to the warrant beside the decision it informed, and made
the next step somebody's job. That is what a model platform can do about a modelling problem,
and claiming more would be a lie.

## 8. Live, with the stage population as the control

```python
covenants = [
    {"kind": "output_range", "min": 0.0, "max": 400_000.0},  # attr filled in: ecl
    {"kind": "input_psi", "attr": "arrears", "max": 0.25},
    {"kind": "input_null_rate", "attr": "pdOrigination", "max": 0.0},
]
```

The null-rate covenant is set at **zero**, on purpose: the stage test divides by the
origination probability, so one missing value is not a degraded estimate but an account with no
stage at all.

The PSI covenant watches arrears, because arrears is what moves accounts across the threshold,
and a shift in the stage population moves the allowance by the lifetime multiple on every
account that crossed — the largest single lever in the calculation, and the one nobody decided
this quarter. Report a quarter where the distribution has moved and:

```
WarrantSuspended: Warrant suspended: population stability index of 'arrears' 10.979 > 0.25:
  the inputs this warrant sees are no longer the population it was fitted on.
  Contact impairment.committee@example.com.
```

Worth noting for anyone building one: the baseline has only **2 bins** here, because arrears is
a small integer and quantile bins collapse. The reported histogram has to be over the same
bins, which is precisely why MAYA fixes them at creation.

It is reinstated with what was decided — the shift confirmed against the servicing
reconciliation, the allowance accepted for the quarter with a management overlay recorded
separately, and a refit scheduled before the year-end accounts.

## 9. What an auditor can read afterwards

`show_estate.py` answers the question directly. Five approved parameter sets, each with its
values, its state, its notes and — for the two judgements — the justification under which it
was approved. Three holdout attempts with their metrics. Sixteen custody events on the warrant,
in order. 87 audit entries, hash-chained and verified unbroken. 17 lineage nodes. And a 20 kB
typeset manifest naming the parameter set that produced the figure in the accounts.

The superseded committee decision is still there. That is the point: a governance record that
deleted the judgement it replaced would be less useful than no record at all.

## 10. What to point at when demonstrating this

1. **§4's contract** — two parameters that belong to no member, now declared, and the finding
   that put them there.
2. **§5's three refusals** — a seal waiting for a judgement, half a decision refused, and a
   judgement that had to say where it came from before anybody could approve it.
3. **§6's two blind figures** — the model is *worse* on per-account error than holding no
   allowance, and that is the correct result. Governance that can say which of its own numbers
   is uninformative is worth more than governance that cannot.
4. **§7's grid, and the refusal to use it** — the platform produced the evidence; it did not
   choose the judgement; and the residual went on the record as an open finding.
5. **§9** — every number, who approved it, and what they said. In one screen.

## 11. What this study deliberately does not do

Stage 1 and stage 2 only — an account already in default is stage 3 and is measured
individually. No forward-looking macroeconomic scenarios, which IFRS 9 also requires and which
are a separate overlay with their own governance. Lifetime loss is a multiple of the
twelve-month figure rather than a term structure of default. And the three factors multiply as
if independent when they are positively correlated in stress, so the allowance understates loss
in exactly the conditions where it matters. All four are in the composite's *Scope* and *Known
Weaknesses* sections, where somebody reading the model will find them.
