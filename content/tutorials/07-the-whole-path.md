---
title: The whole path, step by step
slug: the-whole-path
section: The platform
order: 46
icon: diagram-3
summary: One worked example from an empty register to a model serving in production — defining features, composing a featureset, inheriting a model, issuing a warrant, fitting, approving the parameters, freezing, and running. Every call is real, and every refusal along the way is one you should expect.
audience: Everyone
---

# The whole path, step by step

This is the one tutorial that does not stop at a subsystem boundary. It starts
with an empty register and ends with a model serving in production, and it does
the whole thing twice — once for a model built from scratch, once for a model
built **from** that one.

Every call is a real call. Where the platform refuses something, the refusal is
in here too, because being refused is most of what learning this consists of and
a walkthrough that only shows the happy path teaches you the wrong shape.

**The example.** A small-business credit book. We build a PD scorecard, then a
second model for a different legal entity that derives from it, and a VaR model
that consumes both — so that by the end there is a shared dependency to find.

---

## What you are building, in one picture

```
  FEATURES                FEATURESET               MODEL              PARAMETERS
  ────────                ──────────               ─────              ──────────
  dscr        ─┐
  turnover    ─┼─→   sb_core @v1   ──────→   credit.pd.smallbiz  ──→  ols_v1
  region      ─┘      (slots +                  (the kernel)          (a point
                       bindings)                                       of P)
                          │                          │                    │
                          └────────── warrant ───────┴────────────────────┘
                                    (names all three)
```

Four objects, and each answers a different question:

| Object | Answers |
|---|---|
| **Feature** | *what a signal is*, where it comes from, and when it became knowable |
| **Featureset** | *what a model is defined over* — named slots with types |
| **Model version** | *what the kernel is* — immutable once created |
| **Parameter set** | *which point of `P` it runs at* — separate, because refitting is not a model change |

The last row is the one people get wrong, so it is worth saying plainly up
front: **recording new parameters does not create a new model version.** The
kernel did not change. That distinction is what lets you approve a daily
recalibration *procedure* once, rather than pretending a committee meets every
morning.

---

## 0 · Who you are

Duties are separated, so this walkthrough uses four accounts. If you try it as
one, you will be refused — and being refused is the platform working.

| Account | Role | Does |
|---|---|---|
| `d.raman` | model developer | defines features, creates versions, records a fit |
| `j.okafor` | model owner | registers the model, issues warrants, submits for approval |
| `a.mehta` | validator | validates, approves parameters, closes findings |
| `s.iqbal` | model risk manager | assesses tier, signs the quorum, moves the alias |

```bash
curl -u admin:admin123 -X POST localhost:5006/api/v1/principals \
  -H 'Content-Type: application/json' \
  -d '{"username":"d.raman","display_name":"D Raman",
       "roles":["model_developer"],"password":"dev-pw"}'
```

Repeat for the other three with their roles.

---

## 1 · Define the features

A feature is a governed object, not a column. It has an owner, a type and a
lineage.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' \
  -d '{"name":"dscr","entity":"borrower_id","dtype":"numeric",
       "description":"Debt service coverage ratio","owner":"person/j.okafor"}'
```

Do the same for `turnover` and `region`.

### A derived feature

`Z = f(X, Y)`, computed rather than supplied:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' \
  -d '{"name":"leverage","expression":"turnover / dscr","dtype":"numeric",
       "description":"turnover per unit of coverage","owner":"person/d.raman"}'
```

Two things happen without you asking:

- **Its ingest clock is the maximum over its inputs.** If `turnover` was known
  in May and `dscr` in August, `leverage` was not knowable until August. That is
  arithmetic, so it cannot be forgotten.
- **Its lineage is walked whenever it is used.** Which matters in a moment.

### The refusal you should expect

Try deriving a feature from what you are trying to predict:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' \
  -d '{"name":"default_rate_proxy","expression":"defaulted * 1.0",
       "dtype":"numeric","description":"...","owner":"person/d.raman"}'
```

This is fine *until* your label is `defaulted`, at which point using it is
refused — and the refusal names the derivation chain rather than saying "no".
The check walks derivations of derivations, so hiding the label two steps back
does not help.

---

## 2 · Load the values

A view is where a feature's values live. The whole upload becomes **one view
version**, because a version is what a featureset pins.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_financials","entity":"borrower_id","owner":"person/j.okafor",
       "features":["dscr","turnover","region"]}'
```

Then send a file. CSV, JSONL, Parquet or Arrow — or use the upload box on the
**Features** page, which posts to this same endpoint.

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/data \
  -H 'Content-Type: text/csv' --data-binary @financials.csv
```

Your file **must** carry `entity_id`, `event_ts` and `ingest_ts`.

```csv
entity_id,event_ts,ingest_ts,dscr,turnover,region
B0001,1711843200,1716163200,1.42,2500000,NJ
B0002,1711843200,1716163200,0.88,410000,NY
```

### Why the second clock is not optional

`event_ts` is when the fact was **true** — 31 March, the quarter it describes.
`ingest_ts` is when it became **known** — 20 May, when they filed.

A file with only one of them is refused. Not as pedantry: with one clock you
cannot answer *what did we know when the decision was made*, and a restatement
then silently rewrites history. If that borrower revises the March figure in
August, both rows belong in the store, and a training row labelled in May must
see the original.

---

## 3 · Compose the featureset

A **featureset declares a schema**; a **version fills it**.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_core","entity":"borrower_id","owner":"person/j.okafor",
       "slots":{"dscr":"numeric","turnover":"numeric","defaulted":"integer"},
       "label_slot":"defaulted","outcome_window_days":365}'
```

Then bind each slot to a feature *and to the exact view version supplying it*:

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"dscr":"dscr","turnover":"turnover","defaulted":"defaulted"}}'
```

That pin is the point. `sb_core@v1` always resolves to the same bytes, because
every binding names a Delta version rather than a path.

### Composing from another featureset

A combination of featuresets is a featureset. Order is **left to right, the
rightmost winning** — the leftmost parent is the least prominent.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_core_plus_region","entity":"borrower_id",
       "owner":"person/j.okafor",
       "composes":[{"name":"sb_core"}],
       "operations":[{"op":"add","name":"region",
                      "value":{"dtype":"categorical"}}]}'
```

Three operations, and each is **total**:

| Operation | Does | Refused when |
|---|---|---|
| `add` | introduces a slot the parents do not have | the slot already exists |
| `drop` | removes one they do | it was not there to remove |
| `override` | replaces one with a different type | it changes nothing |

An operation that silently did nothing would be one somebody believes happened.

**Before you declare it, ask what it would resolve to.** The interface has a
*Preview* button; the API is:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets/preview \
  -H 'Content-Type: application/json' \
  -d '{"composes":[{"name":"sb_core"}],
       "operations":[{"op":"override","name":"dscr","value":{"dtype":"integer"}}]}'
```

It runs the same fold and refuses exactly what declaring would, so you can find
out without filling the register with attempts.

---

## 4 · Register the model

The model comes **after** the featureset in this walkthrough, but it does not
have to — a featureset does not belong to a model, and the same one can train
several.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","name":"SB PD",
       "model_class":"credit.pd.scorecard","domain":"credit",
       "owner":"person/j.okafor","legal_entity":"LE-US-01",
       "purpose":"12-month PD at origination"}'
```

Assess it, because the tier decides how many signatures its versions need:

```bash
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":2000000000,"purpose_class":"regulatory_capital"}'
```

You get back the **derivation**, not just a number: which facts were used, which
bands they fell in, the required control set, and which ruleset version decided.

### Create a version

A version is the kernel, and it is immutable.

```bash
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
derived from. You never declare the class — asking a closed-form pricer for its
training set is then a type error rather than an empty field.

---

## 5 · Compose the model

Here is the second model, built **from** the first — and a third that consumes
both.

```bash
# a variant for the UK book
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz.uk","name":"SB PD (UK)", ... }'

curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"maya://model/credit.pd.smallbiz",
       "to_urn":"maya://model/credit.pd.smallbiz.uk",
       "kind":"derives_from","note":"same shape, UK portfolio"}'
```

**Two relations, and they do different work.**

| Kind | Means | Propagates |
|---|---|---|
| `derives_from` | built from it — a variant, a recalibration for another book | **no** |
| `input_to` | this model's **output** is read as an input by that one | **yes** |
| `challenger_of` | built to argue with it | no |
| `benchmark_for` | a reference point to judge it against | no |
| `calibrated_by` | its parameters are solved by that | yes |

> **`input_to` is not a data feed.** It was once called `feeds`, and in a bank
> that reads as market data or a nightly file. MAYA neither consumes nor produces
> any such thing: it never moves data and never runs a model. The edge is a
> statement about two entries in the register — *this model's output is read as
> an input by that one* — and the wire it describes is carried by whatever engine
> runs them. `feeds` is still accepted and stored as `input_to`.

`derives_from` does not propagate, and that is deliberate. The UK model has its
own versions and its own approvals; the edge records where it came from. A
challenger counted as a dependency would inflate every blast radius it appeared
in.

Now a VaR model that consumes both:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"maya://model/credit.pd.smallbiz",
       "to_urn":"maya://model/risk.credit_var","kind":"input_to"}'
```

### The two questions this makes answerable

**What breaks if I change this?**

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/blast-radius \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz"}'
```

Only propagating edges are followed, and each model comes back with its
*distance*, so the immediately affected ones are visible separately from the
ones two hops away. The worst tier reached is reported too — a change touching
one Tier 1 model is not the same as one touching five Tier 4s, and a count alone
cannot tell you which happened.

**What do these two models both rest on?**

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/shared-dependencies \
  -H 'Content-Type: application/json' \
  -d '{"urns":["maya://model/risk.credit_var","maya://model/markets.swaption"]}'
```

This is the interesting one. Two models fed by the same curve are **not** two
independent risks, and a network that *copies* a dependency is not the same as
one that duplicates it. That difference is precisely why an aggregate risk
figure cannot simply add up, and why supervisors ask about "common dependencies
and shared assumptions". Here it has an answer instead of a paragraph.

A cycle is refused: a model whose output is its own input has no defined value.

---

## 6 · Issue the warrant

Nothing runs without one. A warrant is a signed, expiring, entitlement-bound
authorisation naming exactly one operation.

First the standing entitlement:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","environment":"prod",
       "principal":"svc/model-lab","declared_use":"model_development"}'
```

Then the fit warrant, which names the model **and** the featureset:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","environment":"prod",
       "principal":"svc/model-lab","featureset":"sb_core",
       "featureset_version":1,
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200}'
```

### What comes back, and why it is enough

The descriptor is **self-describing**. It carries the featureset's schema — which
slots, what each holds, which feature and which view version fills it, the
entity, the grain, the label binding and the outcome window — so an engine does
not need a second call to know what it is being asked to train on.

It carries names and types, never values. A signed credential is not a wire
format for a dataset; the rows come from the transfer API.

Three laws are checked before it is signed:

- **L-W3** — training data must come from a source that can be read as-of.
- **L-W9** — the read must be bounded in both clocks.
- **L-W10** — the featureset must provide what the kernel declares it reads.
  Adding a regressor is a model change, not a data change, and this is where
  that is enforced rather than remembered.

---

## 7 · Get the data and fit

Assemble a point-in-time-correct training set:

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

…or **let MAYA fit it**, if the version's kernel names the `estimator` runtime:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameter-fits \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","snapshot_id":"01a0...",
       "environment":"prod","principal":"svc/model-lab",
       "window":{"from":1546300800,"to":1735603200},"name":"ols_v1"}'
```

Four things happen in this order, and the order is the point:

1. **The warrant is resolved first.** Authority before data — a read performed
   under an authority that turns out not to exist has already happened.
2. **The snapshot is read at its pinned Delta version**, not at the head. Run
   the same fit twice and it sees the same bytes.
3. **The estimator runs** through the ordinary runtime dispatch.
4. **The result lands `proposed`.**

### Fitting elsewhere

If you fit in your own engine, deliver the result back:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0",
       "name":"ols_v1","kind":"coefficients","provenance":"fitted",
       "values":{"intercept":-2.1,"dscr":-0.84,"turnover":0.00003},
       "featureset":"sb_core","featureset_version":1,
       "warrant_id":"<the grant id>",
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200,
       "diagnostics":{"r_squared":0.31,"n":8420}}'
```

A fitted set is accepted **only** against a warrant MAYA issued. Without one,
"which data produced these numbers" has no answer.

---

## 8 · Approve the parameters

A parameter set changes what the model does, so it is approved the way a version
is — and **not by whoever recorded it**.

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/<id>/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,"note":"diagnostics reviewed; condition number 34"}'
```

Read the diagnostics before you sign. The **condition number** is the one to
look at first: in the thousands, the coefficients are a solution to this sample
rather than a property of the world. MAYA does not decide whether a fit is any
good — it puts the numbers in front of somebody who can.

---

## 9 · Approve the version and promote it

A Tier 1 or Tier 2 version needs a **quorum** — two people in two named roles.
A single call is refused, correctly.

```bash
APPROVAL=$(curl -su s.iqbal:mrm-pw -X POST localhost:5006/api/v1/version-approvals \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -u s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"model_risk_manager"}'

curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"validator"}'
```

The same person cannot sign twice under two hats, and whoever created the version
cannot approve it.

Then point the alias:

```bash
curl -u s.iqbal:mrm-pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment":"prod","alias":"champion","semver":"1.0.0"}'
```

An alias move is the most dangerous operation here, so it is a **proof
obligation**: the replacement's contract must refine the incumbent's (L-7) and
its schemas must satisfy variance (L-12), or the move is refused naming the
clause.

---

## 10 · Freeze what should not move

**Seal the featureset**, so its schema cannot change under models fitted on it:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/seal \
  -H 'Content-Type: application/json' -d '{"note":"fitted against; frozen"}'
```

A sealed featureset can still be **composed from** — that is what sealing is
for. A parent that cannot move is a parent worth building on.

**Attest the model record**, which puts it in force:

```bash
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/attest \
  -H 'Content-Type: application/json' -d '{"role":"model_owner"}'
```

Attestation is a quorum, not a signature: every required role signs, and one
decline ends it.

---

## 11 · Run it

Now a consumer resolves a warrant and gets everything needed to execute:

```bash
curl -u svc/origination:svc-pw -X POST localhost:5006/api/v1/resolve \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision"}'
```

This descriptor names the **approved parameter set** by id and digest, because
for a model whose parameters live in the register an artifact binding would be a
false statement — there is no artifact, and the numbers deciding what it does
would be somewhere the warrant did not name.

The engine **re-derives** that digest from the values before running at them. It
does not compare the stored digest against the warrant's: those are two copies
of the same claim, and they would agree happily over values somebody had edited
underneath them.

```bash
curl -u svc/origination:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision",
       "inputs":{"features":{"dscr":1.4,"turnover":250000}}}'
```

You may only resolve a warrant **for yourself**, unless you hold
`warrant:issue`. Otherwise anybody could obtain a credential in a service
account's name.

---

## What refuses what, and why

The refusals are the product. Here are the ones you will meet, in the order you
will meet them.

| Refusal | Cause | The reason it exists |
|---|---|---|
| `ingest_ts` missing | a file with one clock | a value whose arrival is guessed cannot be read point-in-time |
| leakage refused | a feature derived from the label | it is the answer wearing a disguise |
| `schema_not_satisfied` | featureset does not cover the kernel's inputs | adding a regressor is a model change |
| `snapshot_not_pit_verified` | the assembly failed its own leakage check | a model fitted on leaked data scores well and then does not |
| `self_approval` | you approved your own parameters | a number one person can both produce and bless is a preference |
| `quorum_required` | one signature on a Tier 1/2 version | the version is what actually runs |
| `refines` / variance | an alias move that narrows the contract | consumers built against the old guarantee |
| `principal_not_self` | resolving a warrant in another's name | a credential names who is acting |
| would close a cycle | A is `input_to` B is `input_to` A | a model whose output is its own input has no value |

---

## The shape of it, once more

The thing worth carrying away is not the sequence of calls. It is which objects
are separate, and why:

- **A featureset is not part of a model.** The warrant names both, which is what
  lets one featureset train several models and one model be fitted from
  different featuresets under different warrants.
- **A parameter set is not a model version.** Refitting produces a new *point*
  of `P`, not a new kernel — so "did this model change in March?" has one answer
  instead of two.
- **`derives_from` is not `input_to`.** Where a model came from and what breaks when
  it changes are different questions, and answering them with one edge makes
  both answers wrong.
- **Every value carries two clocks.** Everything else in this walkthrough rests
  on being able to say what was known when.
