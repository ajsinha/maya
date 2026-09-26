# Case study 7 — a card-fraud neural network

**Domain:** banking, card fraud detection · **Model type:** feed-forward neural network,
fitted, **declared black box** · **What it exercises:** what governance still means when
the mathematics is unreadable — an exact input contract with no formula behind it, weights
as an approved parameter set, determinism from a declared seed, the six-rung ladder on the
code, and MAYA refusing to score the model at all.

## The scripts, and what each one does

The study is seven steps, run in this order. They share the project's MAYA — the estate `config/application.yaml` configures, shared by every study, in which this study is the `card_fraud` namespace —, which the first script builds and the rest reopen, so
**each can be run on its own, in its own process** — and between any two of them you can
open the web UI and show what the last one actually created. That is the demonstration.

| Script | What it does | Shows |
| --- | --- | --- |
| `make_data.py` | Writes the three input feeds to `data/` (already committed; run it only to regenerate). Nothing to do with MAYA. | The recipe: a compromise process with two opposite fraud patterns, and the innocent days that look like half of each. |
| `setup_features.py` | Reads the three CSVs, declares a feature definition for each, ingests the rows, submits them as **dana** and approves them as **mick**. | Definitions as governed objects; the value ranges that are the only written statement of what the network may be given; **dana refused when she tries to approve her own feature**. |
| `setup_featureset.py` | Composes six drivers and the target into `fraud_panel` on `(date, card)` with as-of alignment, approves it, and pins it point-in-time. | A month-end profile carried as-of rather than resampled; an immutable, content-hashed pin — the only way to ask "which rows produced this score" when there is no coefficient to read. |
| `setup_model.py` | Registers the network as a **declared black box**, fills the nine specification sections, uploads two code artifacts and runs the ladder on both. | **Three refusals**: an IR with no mathematics at all, a black box that will not say what it estimates, and the artifact that loads its weights from a file. Then the ladder, the artifact hash, and **the differential test skipped by name**. |
| `get_training_warrant.py` | Draws a warrant with a target the panel lacks, then naively, then with the forward-looking target explained. | The input contract checked before anything is fitted; **the leakage certificate refusing all 13,500 rows**; the seed and the stopping rule written down before anybody fits. |
| `fit_parameters.py` | Fits the network three times, fits the challengers, carries 209 numbers through an `.npz`, uploads twice, and asks MAYA to score the holdout. | **Determinism**, exactly; both AUCs; **a pickle of the weights refused**; parameters that cannot prove their data refused; and **MAYA refusing to blind-score a declared black box**. |
| `get_execution_warrant.py` | Draws an execution warrant with three covenants, gets it approved by a *second* model manager, takes it live, then reports a batch whose amount ratios have all moved. | Covenants as the *primary* control rather than one of several; a PSI baseline fixed from the fitting data; **the warrant suspending itself on a PSI of 1.082**. |
| `show_estate.py` | Creates a reproducibility bundle, verifies it, and reads back the catalog, the audit chain, the custody and the lineage. | That everything above is discoverable afterwards — and that **the bundle marks re-execution "not run" and says why** instead of leaving a tick to be misread. |
| `network.py` | The desk's implementation: `fit` and `predict` to MAYA's model interface. Imported by the fit, and uploaded verbatim as the artifact. | One implementation, hashed once. The artifact MAYA validated is byte-for-byte the file the desk trained with. |
| `study.py` | No MAYA calls at all: the names, the definitions, the black-box node, the specification document, the challengers and the cast. | The declarations that would live under source control at a bank — including everything that stands in for a formula. |
| `run.py` | Runs all seven steps in order against a MAYA built from nothing. About ten seconds. | The unattended pass — for checking the study still works, or reading the whole story at once. |

```bash
# the whole story at once
.venv/bin/python case_studies/07-neural-network/run.py

# or one step at a time, which is how to demonstrate it
.venv/bin/python case_studies/07-neural-network/setup_features.py --reset
.venv/bin/python case_studies/07-neural-network/setup_featureset.py
...
```

`--reset` deletes this study's MAYA and starts again from nothing; `--quiet` prints the
results without the narration.

---

## 1. The business problem

A card issuer's fraud desk can review a few hundred cases a day. Every night it must rank
that day's card-days — one row per card per day — so that the cases worth reviewing are at
the top. The instrument almost every issuer uses for this is a neural network, because the
patterns are conjunctions rather than trends, and because nobody has to explain a queue
position to a customer.

That last clause is doing a lot of work, and it is what this study is about. A scorecard can
be challenged line by line; this model cannot be challenged at all in that sense. So the
question a model risk function has to answer changes. In case study 1 it was *can the
platform check the mathematics?* Here it is:

> **What can be held to account when the mathematics is unreadable?**

The answer is not "nothing", and it is not "everything with a longer document". It is a
specific, shorter list, and the value of this study is that MAYA makes the list explicit —
by refusing, at the exact points where a platform that wanted to look good would not.

## 2. What changes, claim by claim

Everything in case studies 1 and 2 that does not depend on reading the model still works
here, unchanged. Everything that does depend on it either fails loudly or is marked
unverifiable. Nothing quietly degrades.

| Governance claim | Case study 1 (a logistic scorecard) | Here (a declared black box) |
| --- | --- | --- |
| Input contract checked against the data before training | Derived from the formula | **Unchanged** — declared, and checked identically (§7) |
| Data pinned point-in-time, content-hashed | Yes | **Unchanged** (§4) |
| Leakage certificate on every row | Yes | **Unchanged**, and it matters more (§7) |
| Parameters tied to their data by checksum | Yes | **Unchanged** (§9) |
| The mathematics reviewable | The formula *is* the model | **Gone.** Replaced by a declaration: architecture, loss, optimiser, learning rate, batch size, initialisation, epochs, stopping rule, seed (§5) |
| The code agrees with the mathematics (differential test) | Compared on 2,000 sampled inputs | **Skipped by name** — there is no closed form to compare against (§6) |
| The code runs, deterministically, in a sandbox | Optional extra | **The whole of what the platform can check about the code** (§6) |
| Blind scoring of an escrowed holdout | RMSE on 5,295 rows the developer never saw | **Refused.** MAYA evaluates formulas; this model has none (§10) |
| The reported metrics | Computed by MAYA | **Asserted by a named person** against a checksum (§10) |
| A reproducibility bundle that re-executes | Output hash re-derived by the verifier | **Marked "not run", with the reason** (§12) |
| Covenants on inputs and outputs | One control among several | **The primary control, because it is the only one left** (§11) |

## 3. The data, and why a network wins here

Three feeds, committed as CSV in `data/` and written by `make_data.py`. 300 cards over 45
days, 2025-03-01 to 2025-04-14, one row per card per day.

| File | Rows | Grain | Arrives | Why it matters |
| --- | --- | --- | --- | --- |
| `card_day_activity.csv` | 13,500 | card × day | day **+ 1 day** | Four ratios, each relative to the card's *own* recent behaviour. Known the next morning, which is soon enough to score on. |
| `card_profile.csv` | 600 | card × month end | month end **+ 10 days** | Tenure and dispute history. Monthly, late, and carried forward as-of — never resampled. |
| `fraud_confirmed.csv` | 13,500 | card × day | day **+ 45 days** | The target. Whether the disputes team confirmed fraud, which cannot be known until the chargeback window closes. |

The confirmed-fraud rate is **4.53%** of card-days. Underneath, a card-day is compromised
with a probability driven by tenure (new cards and long-dormant ones are the targeted ones)
and dispute history, and a compromised day is worked one of two ways:

| | `amount_ratio` | `velocity_ratio` | `foreign_share` | `night_share` |
| --- | --- | --- | --- | --- |
| **cash-out abroad** | ~4.7x the card's usual largest | low — one purchase | high | as usual |
| **card testing** | ~0.17x — micro-authorisations | ~4.7x — a burst | as usual | high |
| an innocent day | ~1x, sometimes a 4x big-ticket day | ~1x, sometimes a 4x busy day | high for the 30% who travel | high for the 25% who shop at night |

So the drivers are worthless on their own, and the study measures that rather than asserting
it. On the training partition, each driver's own AUC:

| `amount_ratio` | `foreign_share` | `night_share` | `velocity_ratio` | `tenure_months` | `prior_disputes` |
| --- | --- | --- | --- | --- | --- |
| **0.4929** | 0.6923 | 0.6528 | 0.5476 | 0.5168 | 0.5577 |

`amount_ratio` ranks card-days slightly *worse* than a coin, because fraud sits at both ends
of it. A logistic regression has one coefficient per driver and cannot say "either end".
Three models on the same 9,555 training rows, scored on the same 1,945 validation rows:

| Model | AUC train | AUC validation |
| --- | --- | --- |
| Logistic regression, six drivers | 0.8719 | **0.8612** |
| **The network**, 6 → 12 → 8 → 1 | 0.9526 | **0.9745** |
| Logistic regression, six drivers **plus the three true conjunctions** | — | **0.9624** |

The first two lines are the justification for accepting an unreadable model: **eleven points
of AUC**, on data where the readable model is not merely weaker but structurally unable to
express the pattern. The third line is the honest qualification, and the study computes it
on purpose: a logistic regression *told* the three conjunctions — amount × foreign, night ×
velocity, and velocity over amount — gets within 0.012 of the network. What the network
bought is **discovering** the conjunctions, not representing them. In a real book nobody
knows them, which is the argument for the network; it is also the whole of the argument, and
a reviewer is entitled to ask for the crafted challenger before accepting the opaque one.

Two smaller honesty notes. The validation AUC is *above* the training AUC (0.9745 against
0.9526); with 92 confirmed frauds in the validation partition that gap is noise, not
evidence of anything, and it is quoted here because a study that only quoted the flattering
direction would not be worth reading. And the label is a *decision*: 90% of compromised
days are confirmed and 0.3% of innocent ones are, so the network learns what the disputes
team confirms, which is written into the specification's *Assumptions*.

## 4. The panel

`fraud_panel` composes six drivers and the target on `(date, card)` with

```python
"alignment": {"mode": "asof", "tolerance_days": 45}
```

The profile file is monthly and lands ten days late, so as-of alignment carries the last
*known* file forward to each day. It does not resample or interpolate, because the issuer
did not have a daily tenure. `auth_count` exists in the activity feature and is deliberately
**not** a panel member: the model's contract does not name it, and a panel that carries what
nobody uses invites somebody to start using it.

The panel is pinned at `as_of = 2025-04-14`, `as_of_known = 2025-07-01` — the earliest
knowledge time at which the last day's 45-day dispute window has closed — cascading to the
three member features. Its reference is

```
maya://featureset/card_fraud/fraud_panel#fit2025q2/2025-04-14
```

For a scorecard, the pin is one piece of provenance among several. Here it is the only one:
a coefficient can be compared with last quarter's coefficient, but 209 weights cannot be
compared with anything, so "which rows produced this" is the only answerable version of
"why did the score change".

## 5. The model as a declaration, not a formula

MAYA holds the model as a **declared black-box node** — §8.1's "graceful degradation" —
with an exact input contract and named parameters:

```python
{
    "outputs": [{"name": "fraud_score", "type": "float64"}],
    # the six drivers with role "feature", then the eight weight arrays with role "parameter"
    "inputs": [...],
    "black_box": {"estimates": ..., "architecture": ..., "hyperparameters": {...}},
}
```

What MAYA prints back is worth reading carefully:

```
kind:                              black_box
opaque:                            True
input contract:                    amount_ratio, foreign_share, night_share,
                                   velocity_ratio, tenure_months, prior_disputes
parameters to be fitted:           W1, b1, W2, b2, W3, b3, x_mean, x_scale
fitted values:                     209
rendered mathematics:              ''  (there is none)
```

The contract is exact and the parameters are named, and neither fact requires MAYA to
understand the network. The rendered mathematics is an empty string, which is the honest
output rather than a plausible-looking one.

Two refusals establish that the opacity has to be *declared* rather than merely present:

```
ValidationFailed: The formula IR is not valid: body is required unless the model is
  a declared black box
ValidationFailed: The formula IR is not valid: black_box: a prose statement of what
  the model estimates is mandatory
```

An IR with no `body` and no `black_box` node is not an unreadable model — it is a model
nobody has said anything about, and MAYA will not hold one. And a declared black box must
say, in prose, what it estimates: here, that the output is a ranking instrument for a review
queue, not a calibrated probability, and that it explains nothing.

Then the specification document, whose nine sections are the gate:

```
NotApproved: Blocked by check(s): spec_document_complete — required sections empty:
  Purpose, Scope and Limitations, Assumptions, Calibration Methodology,
  Validation Evidence, Known Weaknesses, Change Log
```

*Mathematical Formulation* is the section that changes character. It states that there is no
formula, and then declares everything that determines the model instead: layer widths, both
activations, the loss, the optimiser, the learning rate, the batch size, the initialisation,
the standardisation and where it is carried, a fixed **80 epochs with no early stopping**,
and the seed. Each of those is a decision a reviewer can challenge without reading a single
weight. The stopping rule matters more than it looks: because the epoch count is fixed in
advance, nothing in the fit depends on the validation partition, which is the only reason
the validation AUC in §3 is worth quoting.

## 6. The code, and what the ladder can and cannot tell you

The model carries a code artifact: `network.py`, uploaded verbatim, which is also the file
the fit imports. One implementation, hashed once —

```
artifact hash:                     50487efb1899028a…
sha256 of network.py on disk:      50487efb1899028a…
```

Before the real one, the study uploads the artifact everybody writes first — the one that
loads its weights from a file:

```
4. static ban: FAIL — use of 'open' on line 12
NotApproved: Blocked by check(s): code_artifact_validated — artifact failed
  validation: use of 'open' on line 12
```

That refusal is not incidental to this study; it is why the weights are a parameter set at
all. The ordinary way to carry a network's parameters is a file next to the code, and MAYA's
sandbox has no filesystem to read one from, so the 209 numbers have to arrive as values
somebody approved.

The real artifact passes all six rungs, under sandbox tier `strong` on this host:

```
1. parse:            ruff check ran: clean
2. entry point:      'Model' implements fit(X, y, ctx) and predict(X, params, ctx)
3. import allowlist: every import is on the allowlist
4. static ban:       no filesystem, process, network or dynamic-code use
5. smoke run:        succeeded in 0.09s under tier 'strong'
6. determinism:      two runs produced identical output
```

**And that is the whole of what the platform checks about this code.** In case study 2 the
ladder is the first half; the second half is the differential test against the documented
mathematics, which found a real bug. Here:

```
conformance in the ladder's report: absent
asking for it explicitly:          {'skipped': True,
                                    'statement': 'declared black box: nothing to compare'}
```

The skip is correct — there is nothing to compare against — but it is worth being precise
about what is lost. The ladder answers "does this run, and does it run the same way twice".
It cannot answer "does it compute the model", because nobody has written down a model for it
to compute. A network with the layers transposed, or the standardisation applied twice,
passes every rung.

What is left is a comparison the desk has to run for itself. MAYA ran the artifact in its
sandbox on the declared eight-row sample with the seed-7 initial weights; the study computes
the same forward pass locally and compares:

```
sandbox output, first three:       [0.556165, 0.557952, 0.559705]
desk's own forward pass:           [0.556165, 0.557952, 0.559705]
largest absolute difference:       0.00e+00
```

Bit-for-bit identical, which says the platform's sandboxed run of the artifact reproduces
the desk's own — a real claim, and the strongest available here. **Nothing in MAYA required
that check, and nobody would have noticed if it had failed.** That is a gap, and §13 says
what would close it.

## 7. The warrant: the contract, the certificate, and the seed

Drawing a warrant with a target the panel does not carry is refused before anything is
fitted, which is the point about the contract surviving opacity intact:

```
ContractMismatch: The feature set does not satisfy the model's input contract:
  target 'fraud' is not an attribute of the feature set
```

Drawn naively, the leakage certificate refuses **13,500 of 13,500 rows** — every row, as in
case study 1, because the panel's knowledge time per row is the latest of its members' and
the confirmed-fraud label is known 45 days late. The warrant cannot be submitted:

```
NotApproved: Blocked by check(s): leakage_certified —
  leakage certificate: refused; 13500 violating row(s)
```

The exception is written down, and the study's version of it ends with the sentence that
belongs to *this* model: *"any driver known late would be leakage, and for a model nobody
can read, a leaked driver would never be found by inspection."* In case study 1 a leaked
driver might show up as an implausible coefficient. Here there is no coefficient to look
implausible, so the certificate is not a formality — it is the only mechanical check that a
driver from the future did not get in.

The warrant then fixes the things the fit must not choose for itself:

```
split:         {'train': 0.7, 'validation': 0.15, 'test': 0.15}
seed:          7 — the number the 209 weights come from
stopping rule: a fixed 80 epochs; no early stopping
holdout:       escrowed, 2,000 rows, hash 56cc091e0b59b8f8…
```

## 8. Determinism, which is the practical claim

`warrant.data()` hands over **11,500 rows** — 9,555 training with 431 confirmed frauds, and
1,945 validation with 92 — and nothing else. The fit takes two or three tenths of a second.

The network is then fitted **twice on the same rows with the seed the warrant declares**,
and all 209 values compared:

```
every one of the 209 values identical: True
largest difference:                    0.00e+00
```

Bitwise identical. Everything random in the fit — the He-normal initialisation and the
mini-batch order — comes from one `numpy` generator seeded with `ctx.seed`, and nothing else
in the loop consults a clock, a hash seed or a thread count.

Then the honest half, which a study that only reported the good news would omit. Fitted a
third time with seed 8, on the same rows:

```
identical:                         False
largest difference in a weight:    3.690
AUC validation:                    0.9733 against 0.9745
```

The same function, near enough, out of very different numbers. **The weights are not
identified; the procedure is.** Two consequences follow, and both are in the model document's
*Known Weaknesses*: comparing this quarter's weights with last quarter's tells you nothing
unless the seed was held, and "reproducible" here means the seed, the rows and the code
together — never the numbers on their own. That is also why the parameter set's own content
hash (`b9713fe19a5d1b67…`) is a statement about *these* weights and not about the model.

## 9. Carrying 209 numbers

A fit ends in whatever the trainer wrote. The study writes the natural thing, a 3,600-byte
`.npz`, and then tries the other natural thing first:

```
refused — the pickle every training script writes
  ValidationFailed: This pickle would run code, not just carry data: it uses
  STACK_GLOBAL. Save the fitted values as .npz or JSON instead.
```

A pickle of a dictionary of numpy arrays cannot be loaded without importing numpy, and
MAYA's parameter reader refuses any pickle that would import or construct anything, naming
the opcode. The `.npz` is read with `allow_pickle=False` into eight named arrays, **209
numbers**, identical to the fitted values.

One thing to know before designing around it: **the `.npz` itself never reaches MAYA.**
`maya.core.parameters` is a client-side codec — the same one `maya warrant upload-params`
runs — and the API takes named values. So the study decodes the file, uploads the values,
and records the file's own sha256 (`cb71a48db4d90c73…`) in the parameter set's notes. That
is faithful to how the CLI works and is the honest way to say "these values came from this
file", but it is worth knowing that §9.3's "an upload that accepts JSON, NPZ, Pickle
(scanned), or ONNX weights" describes the command line, not the API (§13).

Then the same closing of the loop as case study 1, and it is worth noting that it is
completely unaffected by opacity. Uploaded with the wrong data checksum:

```
flag: unverified_data
NotApproved: Blocked by check(s): data_verified_or_justified — unverified_data: the
  checksum does not match any download MAYA issued; approve only with an explicit
  justification
```

Uploaded with the right one, `verified_data=True`, and approved by mgr.

And the declaration is checked, which is what writing this study changed. The IR names eight
parameters, MAYA records that list on the parameter set, and a set with the second layer's
weight matrix simply missing is refused at upload:

```
parameter schema MAYA recorded:    W1, b1, W2, b2, W3, b3, x_mean, x_scale
refused — uploading weights with a whole layer missing
  ValidationFailed: Parameters out of bounds: missing parameter 'W2'
```

Seven of eight arrays is a network that runs and computes nonsense. When this study was first
written MAYA accepted it: both the recorded schema and the bounds check guarded on the
formula *body*, which every declared black box lacks, so neither ran. The mathematics is
unavailable; the declaration of what parameters it takes is not, and that declaration is the
only thing left to check the weights against. §8.4 says parameters are validated on upload,
and for a black box that is now true.

## 10. The refusal the study is built around

The holdout is escrowed and hashed exactly as in case study 1: 2,000 rows, hash
`56cc091e0b59b8f8…`. Then:

```
refused — blind-scoring a declared black box
  ValidationFailed: A declared black box cannot be scored by MAYA
holdout attempts on the warrant:   0
```

This is ADR-007 doing exactly what it says. MAYA concedes one piece of model runtime —
blind scoring — and implements it by evaluating the model's formula IR with its own
evaluator. This model has no formula IR to evaluate, so the concession does not reach it.

**The escrow is intact and useless.** MAYA will not score those 2,000 rows, and the desk
cannot either, because it was never given them. So the numbers on the parameter set are the
desk's own AUCs on the training and validation partitions, uploaded with
`computed_by: "the desk, outside MAYA, on the rows this checksum names"`.

How much weaker is that than case study 1? Precisely this much:

| | Case study 1 | Here |
| --- | --- | --- |
| Who computed the number | MAYA | devi |
| On which rows | 5,295 rows the developer never saw | 11,500 rows the developer had in full |
| What stops a flattering number | The rows were escrowed; every attempt is counted on the warrant | Nothing, except that the rows are named by checksum and the person is named |
| What a reviewer can re-derive | The metric, by asking MAYA to score again | Nothing inside MAYA. They can re-run the artifact themselves from the bundle |

The claim has moved from *demonstrated on unseen data* to *asserted by a named person
against a checksummed dataset*. That is a real control — it is falsifiable, because anyone
with the bundle and the weights can re-run it and get a different answer if the assertion
was wrong — but it is an attestation, not a measurement, and the model document's
*Validation Evidence* section records it as one.

What would make it stronger is narrow and already mostly built: MAYA's sandbox **already
runs this artifact**, twice, on every upload, and the bundle already carries the code, the
weights and the data. Letting blind scoring run an *approved* artifact against the escrowed
partition in that same sandbox — instead of only evaluating formula IR — would restore the
whole of case study 1's claim for a black box, at the cost of one narrowly-scoped execution
path. §13 states it as a recommendation, not as something this study did.

## 11. Going live, and coming back down

For a scorecard, covenants are one control among several. The specification says of a
*bought* black box (§29.10) that "the covenants of §29.5 become the primary control because
they are the only one available"; for an internally built black box the sentence is just as
true, for the same reason. So the covenants here are chosen with reasons rather than by
habit.

```python
covenants = [
    {"kind": "input_psi", "attr": "amount_ratio", "max": 0.25},
    {"kind": "input_null_rate", "attr": "tenure_months", "max": 0.02},
    {"kind": "output_range", "attr": "fraud_score", "min": 0.0, "max": 1.0},
]
```

* **PSI on `amount_ratio`** — the driver both fraud patterns live at the *ends* of. If that
  population moves, every conjunction the network learned is being asked about a different
  book. The covenant declares no baseline, so MAYA takes it from this warrant's own training
  data and fixes it at creation: ten bins with edges from 0.072 to 13.299. Drift means drift
  from what was fitted.
* **Null rate on `tenure_months`** — the fragile feed. The profile file is monthly and
  carried as-of; if it fails to arrive the column goes null, and a network handed nulls does
  not complain, it scores.
* **Output range on `fraud_score`** — a logistic output is a probability, so anything
  outside [0, 1] means the code in production is not the code that was approved. It is a
  weak check and it is the only end-to-end one available: there is no formula to
  re-evaluate and MAYA will not run the artifact.

The warrant is submitted by **mgr** and approved by **lara**, a second model manager, then
sealed. A batch of the book it was fitted on reports clean, with scores spanning 0.0005 to
0.9034. Then the same rows with every amount ratio inflated — an acquirer-mix change, the
commonest way that feed moves — and the histogram is computed from the real rows on the
covenant's own bin edges, so the number in the suspension is MAYA's arithmetic and not a
prop:

```
WarrantSuspended: Warrant suspended: population stability index of 'amount_ratio'
  1.082 > 0.25: the inputs this warrant sees are no longer the population it was
  fitted on. Contact card.fraud.analytics@example.com.
```

Nobody read a weight to find that. An administrator reinstates it with a reason —
*"acquirer mix confirmed changed by the payments team; the network is being refitted under a
new warrant and runs in shadow until then"* — and the reason is part of the record.

## 12. What the estate holds afterwards

| | |
| --- | --- |
| Features / feature sets / models | 3 / 1 / 1, all approved; the model flagged `opaque=True` |
| Audit chain | 77 entries, hash-chained, verified unbroken |
| Custody on the training warrant | created, downloaded, parameters_uploaded ×3, submit, approve, sealed, downloaded |
| Lineage around the pinned panel | 15 nodes, 18 edges |
| Reproducibility bundle | 253 kB, 17 files, verified |

The bundle is the last word on honesty here. It carries `model/artifact.py`,
`model/parameters.json`, `model/spec.tex`, the pinned training frame and the leakage
certificate, and it hashes and signs every one of them. Its verifier then reports:

```
ok       Ed25519 signature over the file list
ok       data content hash (canonical, value-based)
not run  re-execution — declared black box: MAYA holds no executable specification,
         so this bundle verifies inputs only and says so
```

Every hash checks, the signature checks, and the claim a reader would most like — *these
weights on these rows give these scores* — is marked **not run**, with the reason, rather
than left as a tick to be misread. `output_hash` is `None` rather than absent.

## 13. Findings

Three things this study found in MAYA, recorded here because a case study that only
demonstrated the good parts would not be evidence of anything.

**1. A black box's declared parameters were neither recorded nor checked — now fixed.** The
IR declares eight parameter inputs, but `parameter_sets.param_schema` was stored as `[]` and
no completeness or bounds check ran, so a parameter set missing an entire layer was accepted.
Both followed from guarding on the formula *body* instead of on the declared parameter
inputs, which made the workflow gate that reads them vacuous for every black box. The
asymmetry is what gave it away: the execution warrant reads the *same* declaration correctly
and refuses to run without an approved set, so the declaration was trusted in one place and
ignored in the other. Both now test the declaration, the check happens at upload as §8.4
says, and §9 above shows the refusal. `tests/test_vendor_models.py` holds it.

**2. The skipped differential test is invisible on the model version.** The specification
says (§29.7, line 2074) "where the model is a declared black box the test is skipped and the
model version *says so*, which is itself useful information". As built,
`run_validation_job` simply omits the comparison for an opaque IR
(`maya/services/models.py:574`), so the artifact report contains no `conformance` key at all;
the "skipped" statement exists only in the return value of `models.conformance()`, which
somebody has to think to call. The model version says nothing.

**3. `.npz` and the other parameter file formats never reach the API.** `maya.core.parameters`
is a client-side codec; `POST /warrants/training/{id}/parameters` accepts JSON values only,
and the CLI decodes the file before it calls the SDK (`maya/cli/__main__.py:206–216`). This
is a reasonable design — the server never parses a pickle — but §9.3's "an upload that
accepts JSON, NPZ, Pickle (scanned), or ONNX weights with a declared schema" reads as an API
capability, and there is no "declared schema" for a black box at all (finding 1).

**A recommendation, not a finding.** ADR-007 concedes exactly one piece of model runtime and
implements it by evaluating formula IR, which is why §10 happens. The sandbox that the
ladder uses already runs *this* artifact, twice, on every upload, in a separate interpreter
under tier `strong`; the escrowed partition is already hashed on the warrant; the approved
parameter set is already named. Letting `score_holdout` run an **approved** artifact against
the escrowed rows in that same sandbox — no new execution surface, only an existing one
pointed at rows the developer may not see — would give a declared black box the same blind
metric a formula gets, and turn §10's attestation back into a measurement. The same
extension would let the bundle's `reexecutable` be true for a black box with an artifact and
a parameter set, since the bundle's verifier already runs code on the verifier's own machine.

## 14. What to point at when demonstrating this

1. **The two IR refusals in §5** — MAYA will not hold a model with no mathematics; opacity
   has to be declared, with a prose statement of what the thing estimates.
2. **The `open()` refusal in §6** — the reason a network's weights are a governed parameter
   set and not a file beside the code.
3. **`conformance` → `{'skipped': True}` in §6** — the one check case study 2 is built on,
   gone, and said out loud.
4. **The determinism block in §8** — identical to the last bit with the seed held, 3.690
   apart without it, and the same AUC either way.
5. **"A declared black box cannot be scored by MAYA" in §10** — then the table that says
   exactly how much weaker the resulting claim is.
6. **`not run  re-execution` in §12** — the platform declining to imply a check it did not
   perform.

This study's MAYA outlives the scripts, and `show_estate.py` prints how to start the web UI
on exactly the estate it just built, so the same story can be walked through on screen: the
catalog with
the model flagged opaque, the pin preview, the warrant with its certificate and exception,
the parameter set, the lineage canvas and the audit log.

## The input data

| File | Rows | Size | What it is |
| --- | --- | --- | --- |
| `data/card_day_activity.csv` | 13,500 | 923 kB | The daily authorisation summary, cut the next morning. |
| `data/card_profile.csv` | 600 | 27 kB | The month-end customer profile, delivered ten days later. |
| `data/fraud_confirmed.csv` | 13,500 | 554 kB | The confirmed-fraud flag, knowable 45 days later. |

All three are committed, so the study runs with no generation step and a reader can open
them and see exactly what MAYA was given. `make_data.py` holds the recipe, including the
compromise process and both fraud patterns.
