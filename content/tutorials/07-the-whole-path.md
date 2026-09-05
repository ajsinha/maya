---
title: The whole path, step by step
slug: the-whole-path
section: The platform
order: 46
icon: diagram-3
summary: One walk through the register as a graph — three models, the typed edges between them, the featureset two of them share, the fit that inhabits P, and the dossier and export pack that carry the whole thing out to somebody who will never be given a login. Every refusal on the way is one you should expect.
audience: Everyone
---

# The whole path, step by step

The register is not a list of models. It is a **graph**, and almost every hard
question a supervisor asks is a question about the edges: what breaks if this
changes, what do these two both rest on, which data produced these numbers,
which document describes which version of what.

So this walkthrough builds a small graph rather than one model, and it finishes
by walking the graph out to somebody who cannot log in.

**What we build.** A small-business PD scorecard from features up. Then a
variant of it for the UK book, which is *lineage*. Then a credit VaR model that
reads the scorecard's output, which is a *dependency*. Two different edges, and
telling them apart is what makes both answers correct.

Every call is real. Where the platform refuses, the refusal is here too — being
refused is most of what learning this consists of, and a walkthrough that only
shows the happy path teaches the wrong shape.

---

## What is deliberately not one object

Read this table once now and once at the end. It is the whole design; the calls
are consequences.

| Object | Answers | Conflating it with its neighbour causes |
|---|---|---|
| **Feature** | what a signal is, where it comes from, when it became knowable | a restatement that rewrites history silently |
| **Featureset version** | what a model is defined over, pinned to exact bytes | a training set nobody can reproduce |
| **Model version** | what the kernel is — immutable | *did this model change in March* having two answers |
| **Parameter set** | which point of `P` a run is at | a committee pretending to meet every morning |
| **Warrant** | who may do what to which, until when | governance sitting in the serving path |
| **Edge** | how one model stands to another | a blast radius that includes every challenger |

---

## 0 · Four accounts

```bash
curl -u admin:admin123 -X POST localhost:5006/api/v1/principals \
  -H 'Content-Type: application/json' \
  -d '{"username":"d.raman","display_name":"D Raman",
       "roles":["model_developer"],"password":"dev-pw"}'
```

Repeat for `j.okafor` (`model_owner`), `a.mehta` (`validator`) and `s.iqbal`
(`model_risk_manager`).

| Account | Does here |
|---|---|
| `d.raman` | defines features, creates versions, records a fit |
| `j.okafor` | registers models, assesses the tier, issues warrants, attests |
| `a.mehta` | validates, approves parameters, seals the featureset |
| `s.iqbal` | signs the quorum, moves the alias, attests the second half |

---

## 1 · Features, including a derived one

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' \
  -d '{"name":"dscr","entity":"borrower_id","dtype":"numeric",
       "description":"Debt service coverage ratio","owner":"person/j.okafor"}'
```

Do the same for `turnover`, `region` and `defaulted`.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' \
  -d '{"name":"leverage","expression":"turnover / dscr","dtype":"numeric",
       "description":"turnover per unit of coverage"}'
```

Two things happen without asking. **Its ingest clock is the maximum over its
inputs** — if `turnover` was known in May and `dscr` in August, `leverage` was
not knowable until August. And **its lineage is walked whenever it is used**,
which matters in a moment.

### The refusal you should expect

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' \
  -d '{"name":"default_rate_proxy","expression":"defaulted * 1.0",
       "dtype":"numeric","description":"..."}'
```

That is *accepted*. It is a legitimate quantity and somebody may want it on a
dashboard. What is refused is **binding it into a featureset whose label is
`defaulted`** — step 3 — and the refusal names the derivation chain rather than
saying no. The check walks derivations of derivations, so hiding the label two
steps back does not help.

---

## 2 · The values

A view is where a feature's values live. The whole upload becomes **one view
version**, because a version is what a featureset pins.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_financials","entity":"borrower_id","owner":"person/j.okafor",
       "features":["dscr","turnover","region","defaulted"]}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/data \
  -H 'Content-Type: text/csv' --data-binary @financials.csv
```

```csv
entity_id,event_ts,ingest_ts,dscr,turnover,region,defaulted
B0001,1711843200,1716163200,1.42,2500000,NJ,0
B0002,1711843200,1716163200,0.88,410000,NY,1
```

`event_ts` is when the fact was **true** — 31 March, the quarter it describes.
`ingest_ts` is when it became **known** — 20 May, when they filed. A file with
one of them is refused, and not as pedantry: with one clock you cannot answer
*what did we know when the decision was made*, and a restatement then silently
rewrites history. [Features, end to end](/tutorials/features-end-to-end) is that
argument at length.

---

## 3 · The featureset, and one composed from it

A **featureset declares a schema**; a **version fills it**.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_core","entity":"borrower_id",
       "slots":{"dscr":"numeric","turnover":"numeric","defaulted":"integer"},
       "label_slot":"defaulted","outcome_window_days":365}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"dscr":"dscr","turnover":"turnover","defaulted":"defaulted"}}'
```

`sb_core@v1` always resolves to the same bytes, because every binding names a
Delta version rather than a path.

### A featureset composed from a featureset

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_core_plus_region","entity":"borrower_id",
       "composes":[{"name":"sb_core"}],
       "operations":[{"op":"add","name":"region",
                      "value":{"dtype":"categorical"}}]}'
```

The fold is **left to right, rightmost wins** — the leftmost parent is the least
prominent. Three operations, each **total**:

| Operation | Refused when |
|---|---|
| `add` | the slot already exists |
| `drop` | it was not there to remove |
| `override` | it changes nothing |

An operation that silently did nothing is one somebody believes happened.

Independent edits — ones naming different slots — **commute**, which is what lets
two people edit a shared featureset without the order of their edits carrying
meaning. Dependent edits deliberately do not: `override` then `drop` of the same
slot is not `drop` then `override`, and the second order is refused. Claiming
commutativity only for the independent case is the honest form of the law.

Before declaring, ask what it would resolve to:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets/preview \
  -H 'Content-Type: application/json' \
  -d '{"composes":[{"name":"sb_core"}],
       "operations":[{"op":"override","name":"dscr",
                      "value":{"dtype":"integer"}}]}'
```

It runs the same fold and refuses exactly what declaring would, so you can find
out without filling the register with attempts.

---

## 4 · The models, in the right order

A featureset does not belong to a model, and the same one can train several — so
it comes first here, but does not have to.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","name":"SB PD",
       "model_class":"credit.pd.scorecard","domain":"credit",
       "owner":"person/j.okafor","legal_entity":"LE-US-01",
       "purpose":"12-month PD at origination"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"estimated_coefficients",
                 "fit_procedure":"estimate",
                 "runtime":"estimator",
                 "entry":{"family":"ols","target":"defaulted",
                          "regressors":["dscr","turnover"]},
                 "input_schema":[{"name":"dscr","dtype":"numeric"},
                                 {"name":"turnover","dtype":"numeric"}],
                 "output_schema":[{"name":"pd_12m","dtype":"numeric"}]}}'
```

`parameter_kind` and `fit_procedure` are what the **trainability class** is
derived from — `estimated_coefficients` × `estimate` is **T2**. You never
declare it, which is why asking a closed-form pricer for its training set is a
type error rather than an empty field.

**Then** assess, and the order matters:

```bash
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":2000000000,"purpose_class":"regulatory_capital",
       "feature_count":3,"interpretable":true}'
```

Complexity is read off the **latest version's derived class**. Assess a model
with no version and it is assessed as though it were T0 — which for a network on
the same book is the difference between Tier 2 and Tier 1, and Tier 1 is the one
that needs two signatures.

You get back the derivation, not a number: the facts used, the bands they fell
in, the required control set and the ruleset version that decided.

---

## 5 · The edges

Now the second and third models, and the two edges that do different work.

```bash
# a variant for the UK book
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz.uk","name":"SB PD (UK)",
       "model_class":"credit.pd.scorecard","domain":"credit",
       "owner":"person/j.okafor","legal_entity":"LE-UK-01",
       "purpose":"12-month PD at origination, UK book"}'

curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"maya://model/credit.pd.smallbiz",
       "to_urn":"maya://model/credit.pd.smallbiz.uk",
       "kind":"derives_from","note":"same shape, UK portfolio"}'
```

Five kinds, published at `GET /api/v1/model-relations`:

| Kind | Means | Propagates | Type-checked |
|---|---|---|---|
| `derives_from` | built from it — a variant, a recalibration for another book | no | no |
| `input_to` | **its output is read as an input by that model** | **yes** | **yes** |
| `challenger_of` | built to argue with it | no | no |
| `benchmark_for` | a reference point to judge it against | no | no |
| `calibrated_by` | its parameters are solved by that | yes | no |

> **`input_to` is not a data feed.** The relation was once called `feeds`, and
> that was a bad name in a bank: a *feed* here means market data, a reference
> file, a nightly drop — so `A feeds B` read as though MAYA consumed or produced
> one. **It does neither.** MAYA moves no data and runs no model. The edge is a
> statement about two entries in the register — *this model's output is read as
> an input by that one* — and the wire it describes is carried by whatever engine
> runs the two ends. `feeds` is still accepted on the way in and stored as
> `input_to`, and it is deliberately not published in the vocabulary: two words
> for one relation invites somebody to think they mean different things.

Now a VaR model that reads the scorecard's output:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"maya://model/credit.pd.smallbiz",
       "to_urn":"maya://model/risk.credit_var","kind":"input_to"}'
```

### The edge is a claim about types, and it is checked

An `input_to` edge asserts that what one model produces arrives where another
reads it. Recorded and never checked, it is a **drawing**: the blast radius
follows edges nobody validated and a composite has no derived schema. So it is
refused unless the ends compose, through the same order that decides an alias
move:

```
409 — maya://model/credit.pd.smallbiz does not compose with
maya://model/risk.credit_var: what it produces is missing 'pd_12m'. An
`input_to` edge asserts that the output arrives where the input is read, and an
edge that does not type-check is a wire to nowhere — the blast radius would
follow it and the composite would have no defined schema.
```

| | |
|---|---|
| extra outputs | fine — simply unread |
| a missing output | refused: a wire to nowhere |
| a narrowed output | refused, the same regression `L-12` names at an alias move, one level out |
| either end has no version yet | **recorded without a type check**, and the log says so — refusing an edge for a schema nobody has decided would make the register harder to build than the estate is to describe |

`challenger_of` and `benchmark_for` are never type-checked: they record how
somebody *thinks* about a model, and there is no wire. `calibrated_by`
propagates but does not compose — a calibration solves parameters rather than
handing an output to an input.

`L-21`, and a composite's schema is **derived** rather than declared: the
source's inputs, the target's outputs. A composite whose schema somebody wrote
down is a composite that can disagree with its parts.

### The two questions this makes answerable

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/blast-radius \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz"}'
```

Only propagating edges are followed, so a challenger is not downstream of the
model it argues with. Each model comes back with its **distance**, so the
immediately affected are visible separately from the ones two hops away, and the
worst tier reached is reported — a change touching one Tier 1 model is not the
same as one touching five Tier 4s, and a count alone cannot tell you which
happened. Traversal is bounded at depth 20: a dependency graph deeper than that
is either wrong or is something nobody can reason about.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/shared-dependencies \
  -H 'Content-Type: application/json' \
  -d '{"urns":["maya://model/risk.credit_var",
               "maya://model/markets.swaption"]}'
```

This is the interesting one. Two models fed by the same curve are **not** two
independent risks, and a network that *copies* a dependency is not the same as
one that duplicates it. That difference is exactly why an aggregate risk figure
cannot simply add up, and why supervisors ask about "common dependencies and
shared assumptions" in prose. Here it has an answer.

A cycle is refused: a model whose output is its own input has no defined value.

Removing an edge takes a **reason**, and by POST rather than DELETE, because a
reason does not belong in a query string where it will be truncated and logged:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations/remove \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"…","to_urn":"…","kind":"input_to",
       "reason":"the VaR model now reads the LGD model instead"}'
```

An edge that disappears without one is a dependency somebody stopped believing
in and nobody can ask about.

---

## 6 · The warrant

Nothing reads training data without one. First the standing entitlement, then
the fit warrant:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","environment":"lab",
       "principal":"svc/model-lab","declared_use":"model_development"}'

curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","environment":"lab",
       "principal":"svc/model-lab","declared_use":"model_development",
       "featureset":"sb_core","featureset_version":1,
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200}'
```

The descriptor is **self-describing**: the slots, their types, which feature and
which view version fills each, the entity, the grain, the label binding and the
outcome window — so an engine needs no second call to know what it is being
asked to train on. It carries names and types, never values. A signed credential
is not a wire format for a dataset; the rows come from the transfer API.

Three laws are discharged before the signature:

- **L-W3** — training data must come from a source readable as-of.
- **L-W9** — the read must be bounded in **both** clocks.
- **L-W10** — the featureset must provide what the kernel declares it reads. That
  is the same comparison `L-12` makes at an alias move, one level out.

---

## 7 · Assemble, and fit

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/training-sets \
  -H 'Content-Type: application/json' \
  -d '{"version":1,"as_of":1736899200,
       "spine":[{"entity_id":"B0001","label_ts":1730000000,"defaulted":0}]}'
```

Then either **take the data away** and fit in your own engine:

```bash
curl -u svc/model-lab:svc-pw \
  "localhost:5006/api/v1/featuresets/sb_core/versions/1/data?as_of=1736899200&format=parquet" \
  -o training.parquet
```

```python
maya.featuresets.data("sb_core", version=1, into="training.parquet",
                      as_of=1736899200)
```

`as_of` is **required** on that read. An export is a claim about what was known
at a moment, and defaulting it would make that moment whatever the clock said
when somebody happened to call. The SDK writes to a file rather than returning
rows, for the same reason: an SDK that materialised a dataset to be convenient
would be convenient until the first real one.

…or **let MAYA fit it**, where the version's kernel names the `estimator`
runtime:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameter-fits \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","snapshot_id":"01a0…",
       "environment":"lab","principal":"svc/model-lab",
       "window":{"from":1546300800,"to":1735603200},"name":"ols_v1"}'
```

An instance with no captive engine answers `501 no_captive_engine` and says so
plainly — *it can record a fit performed elsewhere but cannot perform one.*

Four things happen in this order, and the order is the argument:

1. **The warrant is resolved first.** Authority before data — a read performed
   under an authority that turns out not to exist has already happened.
2. **The snapshot is read at its pinned Delta version**, not at the head. Run
   the same fit twice and it sees the same bytes.
3. **The estimator runs** through the ordinary runtime dispatch. Nothing about
   the captive engine is privileged; it is one consumer of the same contract.
4. **The result lands `proposed`.**

If a snapshot did not pass its own point-in-time verification, the fit is
refused before the estimator sees a row — `snapshot_not_pit_verified`, naming
the columns the leakage check suspected.

Fitting elsewhere? Deliver the result back with the warrant that produced it:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0",
       "name":"ols_v1","kind":"estimated_coefficients","provenance":"fitted",
       "values":{"intercept":-2.1,"dscr":-0.84,"turnover":0.00003},
       "featureset":"sb_core","featureset_version":1,
       "warrant_id":"wrt_01a06d3f8b21",
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200,
       "diagnostics":{"r_squared":0.31,"condition_number":34.9,"n":8420}}'
```

---

## 8 · Approve the parameters

A parameter set changes what the model does, so it is approved the way a version
is — and **not by whoever recorded it**.

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/$ID/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,"note":"diagnostics reviewed; condition number 34.9"}'
```

Read the diagnostics before you sign, and read the **condition number** before
the R². In the thousands, the coefficients are a solution to this sample rather
than a property of the world. MAYA does not decide whether a fit is any good; it
puts the numbers in front of somebody who can.

---

## 9 · Approve the version, promote it

Tier 2, so a **quorum** — two people in two named roles. One signature is
refused, correctly, and the refusal names the endpoint to use instead.

```bash
APPROVAL=$(curl -su s.iqbal:mrm-pw -X POST localhost:5006/api/v1/version-approvals \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0"}' | jq -r .id)

curl -u s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"model_risk_manager"}'

curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"validator"}'

curl -u s.iqbal:mrm-pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment":"prod","alias":"champion","semver":"1.0.0",
       "justification":"initial promotion"}'
```

The same person cannot sign twice under two hats, and whoever created the
version cannot approve or promote it. The alias move is a **proof obligation** —
see [running several versions at once](/tutorials/managing-versions).

---

## 10 · Freeze what should not move

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/seal \
  -H 'Content-Type: application/json' -d '{"note":"fitted against; frozen"}'
```

A sealed featureset can still be **composed from** — that is what sealing is
for. A parent that cannot move is a parent worth building on.

```bash
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/submit \
  -H 'Content-Type: application/json' -d '{"note":"ready for review"}'
curl -u s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/approve \
  -H 'Content-Type: application/json' -d '{"note":"challenge complete"}'
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/attest \
  -H 'Content-Type: application/json' -d '{"role":"model_owner"}'
curl -u s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/attest \
  -H 'Content-Type: application/json' -d '{"role":"model_risk_manager"}'
```

Attestation is a quorum, not a signature: every required role signs, and one
decline ends it.

---

## 11 · Run it

```bash
curl -u svc/origination:svc-pw -X POST localhost:5006/api/v1/resolve \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision"}'
```

The descriptor names the **approved parameter set** by id and digest, because
for a model whose parameters live in the register an artifact binding would be a
false statement — there is no artifact, and the numbers deciding what it does
would be somewhere the warrant did not name.

The engine **re-derives** that digest from the values before running at them. It
does not compare the stored digest against the warrant's copy: those are two
copies of one claim, and they would agree happily over values somebody had
edited underneath them.

```bash
curl -u svc/origination:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision",
       "inputs":{"features":{"dscr":1.4,"turnover":250000}}}'
```

A missing regressor is refused rather than treated as zero — `column_missing` —
because treating it as zero would return a number, and a number is what the
caller will use.

You may only resolve a warrant **for yourself**, unless you hold
`warrant:issue`. Otherwise anybody could obtain a credential in a service
account's name.

---

## 12 · Walk it out

Everything so far has been building the graph. This is reading it.

**The training record**, compiled per parameter set from what the register
already holds — the warrant, the featureset version, the window, the `as_of`,
the diagnostics, who recorded it and who accepted it:

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/training-records/$ID
```

**The dossier**, which walks the whole graph from the model:

```bash
curl -u a.mehta:val-pw localhost:5006/api/v1/dossiers/credit.pd.smallbiz
```

```
model  credit.pd.smallbiz
 ├── attached:  methodology paper, literature
 ├── compiled:  model development document, model card, Annex IV
 └── version 1.0.0
      ├── attached:  kernel specification
      ├── compiled:  validation report
      ├── parameter set ols_v1        (fitted, as_of 2026-01-15)
      │    ├── compiled: training record
      │    └── fitted from  sb_core @ v1
      │         ├── attached: data dictionary, source agreement
      │         └── feature dscr → business definition
      └── validation  discrimination, calibration
```

Note where the featureset hangs. Under the **parameter set that read it**, at
the **version** it read — not under the model, and not under the set, which has
since moved on. That pin is the difference between *what was this trained on*
and *what does that featureset look like today*.

It is **computed, never stored.** Its inputs are all versioned or immutable, so
there is nothing to keep in step — and a stored dossier would be a second
account of the model's documentation, able to disagree with the first.

Every node with nothing filed is a **named gap**, with what was expected:

```json
{"urn": "maya://model/credit.pd.smallbiz", "model": "SB PD",
 "counts": {"nodes": 6, "documents": 4},
 "gaps": [{"what": "model_version version 1.0.0",
           "why": "nothing is filed here; expected the specification of this kernel"}],
 "detail": "4 document(s) across 6 node(s); 1 gap(s)"}
```

A page that silently omits what it could not find reads as complete, and a
reader cannot tell a thin model from a thin page unless the page says which it
is.

**The export pack**, which carries the same graph to somebody who will never be
given a login:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/export-packs/credit.pd.smallbiz -o pack.zip

curl -u a.mehta:val-pw \
  localhost:5006/api/v1/export-packs/credit.pd.smallbiz/manifest
```

The audience cannot query the platform, so the pack is **self-contained**. They
cannot take the platform's word for it, so every member is **digested** and the
manifest is digested over the members. They will read it months later, so it
records the **evidence chain head** it was cut against — which makes *has
anything changed since* a question with an answer rather than an assurance. And
`gaps.md` is the first file to read, because an absence is recorded rather than
omitted.

The manifest endpoint exists separately for a reason worth copying: comparing
the content digest against the last pack answers *has anything changed* without
moving a hundred megabytes to find out that nothing has.

Cutting a pack is itself recorded in the evidence chain, because handing a
complete record of a model to somebody outside is a governance act, and the
thing an auditor asks later is who took a copy and when.

**And the board pack**, which will not give you one number:

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/board-packs/preview \
  -H 'Content-Type: application/json' -d '{"period":"2026Q1"}'
```

> This pack reports indicators and refuses to average them. A single model-risk
> figure requires the parts to compose, and they do not: two models fed by the
> same curve are not two independent risks, so any one number either
> double-counts the shared dependency or ignores it — and a committee cannot
> decompose it to find out which.

That refusal is `shared-dependencies` from step 5, promoted to a governance
position. Preview computes without recording; `POST /board-packs` records the
one a minute refers to. See [portfolio
reporting](/help/portfolio-reporting).

---

## What refuses what, and why

In roughly the order you will meet them.

| Refusal | Cause | The reason it exists |
|---|---|---|
| `feature_refused` — missing `ingest_ts` | a file with one clock | a value whose arrival is guessed cannot be read point-in-time |
| `feature_refused` — leakage | a slot derived from the label | it is the answer wearing a disguise |
| `registry_refused` — does not compose | an `input_to` edge whose ends do not type-check | a wire to nowhere that the blast radius would follow |
| `schema_not_satisfied` | the featureset does not cover the kernel's inputs | adding a regressor is a model change |
| `snapshot_not_pit_verified` | the assembly failed its own leakage check | a model fitted on leaked data scores well and then does not |
| `warrant_required` | fitted parameters with no warrant | *which data produced these numbers* has no answer |
| `self_approval` | you approved your own parameters | a number one person can produce and bless is a preference |
| `quorum_required` | one signature on a Tier 1 or 2 version | the version is what actually runs |
| `registry_refused` — alias move | a promotion that narrows the contract | consumers were built against the old guarantee |
| `principal_not_self` | resolving a warrant in another's name | a credential names who is acting |
| `blocked` | an open blocking finding | a validation finding should stop the model, not generate an email |

---

## The shape of it, once more

The thing worth carrying away is not the sequence of calls. It is which objects
are separate, and why:

- **A featureset is not part of a model.** The warrant names both, which is what
  lets one featureset train several models and one model be fitted from
  different featuresets under different warrants.
- **A parameter set is not a model version.** Refitting produces a new *point*
  of `P`, not a new kernel — so *did this model change in March* has one answer.
- **`derives_from` is not `input_to`.** Where a model came from and what breaks
  when it changes are different questions; answering both with one edge makes
  both answers wrong.
- **`input_to` is not a drawing.** It type-checks, so the graph the blast radius
  walks is one somebody could not have drawn wrong.
- **Every value carries two clocks.** Everything above rests on being able to say
  what was known when.
- **The documentation is compiled from all of it**, so it cannot drift from what
  it describes — and where it cannot be filled, it says so.
