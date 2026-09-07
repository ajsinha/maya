---
title: Featuresets — composing the X a model reads
slug: featuresets
section: Start here
order: 30
icon: grid-3x3
summary: Declare a schema of slots, compose one from others, fill every slot with a pinned view version, and meet the four refusals — leakage, an unfilled slot, an unpinnable binding, a schema no kernel can consume — through the screens, the SDK and curl.
audience: Model developers, Validators, Model risk managers
---

# Featuresets — composing the X a model reads

A feature is one signal. A **featureset** is the schema a model is defined over:
named slots, each with a type, one of which may be the label. Fill those slots
with exact, pinned data and you have a **featureset version** — the thing a fit
warrant names, a training set is assembled from, and a reviewer checks.

By the end of this page you will have composed a featureset from two others,
published a version whose every binding pins a Delta version, read the plan an
execution engine is handed, met the refusals, and filed a data dictionary
against the version it describes. About twenty-five minutes.

Everything below was run against a real instance. Every response is copied from
that run.

Three things worth knowing before you start.

- **Declaring and filling are separate acts.** `POST /featuresets` declares the
  schema; `POST /featuresets/{name}/versions` fills it. The schema is what a
  kernel is defined over, so changing it is a model change; filling it again is
  not.
- **Composition is a left-to-right fold and the rightmost wins.** A featureset
  composed from others inherits their slots and may declare none of its own.
  That is the ordinary case, not an exotic one.
- **Looking is free.** `POST /featuresets/preview` runs the same fold `define`
  runs and writes nothing. Use it before you name anything.

This page assumes the catalogue and views from
[features](/tutorials/features): the entity `customer`, the features `ebitda`,
`debt_service` and `utilisation`, and the view `sb_financials` carrying the
first two. `utilisation` is defined there and put into no view, because that
page is about defining it; a featureset can only pin a slot to a view that has
been **materialised**, so it needs one here.
Three more things are needed and are not on that page, so they are here rather
than described — a label feature, two derived features, and a view carrying all
three. Section 6 is why the derived pair is worth having:

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "defaulted_12m", "entity": "customer", "dtype": "numeric",
  "description": "1 if the borrower defaulted within twelve months",
  "owner": "person/d.raman"}'

curl -u d.raman:… -X POST http://localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
  "name": "loss_given_default", "expression": "defaulted_12m * 0.45",
  "dtype": "numeric", "description": "LGD, flat 45% of a defaulted exposure"}'

curl -u d.raman:… -X POST http://localhost:5006/api/v1/derived-features \
  -H 'Content-Type: application/json' -d '{
  "name": "expected_loss", "expression": "loss_given_default * debt_service",
  "dtype": "numeric", "description": "EL over the serviced balance"}'

curl -u d.raman:… -X POST http://localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_outcomes", "entity": "customer", "owner": "person/d.raman",
  "features": ["defaulted_12m", "loss_given_default", "expected_loss"],
  "description": "Outcomes for small-business borrowers"}'

curl -u d.raman:… -X POST http://localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_exposure", "entity": "customer", "owner": "person/d.raman",
  "features": ["utilisation"],
  "description": "Revolver utilisation for small-business borrowers"}'
```

And **materialise** both, because a slot is pinned to a view *version* and a
view with no data has none:

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/feature-views/sb_outcomes/materialise \
  -H 'Content-Type: application/json' -d '{"rows": [
    {"entity_id":"C1","event_ts":1717200000,"ingest_ts":1717286400,
     "defaulted_12m":0}]}'

curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/feature-views/sb_exposure/materialise \
  -H 'Content-Type: application/json' -d '{"rows": [
    {"entity_id":"C1","event_ts":1717200000,"ingest_ts":1717286400,
     "utilisation":0.62}]}'
```

If you have not registered a model, start at [defining a
model](/tutorials/defining-a-model).

## The SDK, once

Every SDK snippet on this page assumes this preamble.

```python
from maya_sdk import Maya, Refused, governance

maya = Maya("http://localhost:5006", "d.raman", "…")

sets = maya.featuresets          # declare, preview, fill, assemble, read bytes
algebra = governance.FeaturesetAlgebra(maya)   # plan, restatements, roll forward
```

`FeaturesetAlgebra` is built by hand because it is not attached to the client —
`maya.featuresets` carries the acts, and the plan and the restatement question
live in `governance`.

For curl, `-u d.raman:…` on every call, from a client holding no cookie. **A
session cookie is ambient authority**: once your client has one, Basic auth on
the same client is ignored and the CSRF guard applies. Sign in for the screens
in a browser, and drive the API from a clean client.

---

## 1. Look before you name it

A preview takes the composition half of a definition — slots, parents,
operations, defaults — and nothing that identifies it. No name, no owner, no
label slot. It refuses exactly what `define` refuses about those parts, so you
can find out what something resolves to without filling the register with
attempts.

### Through the interface

**Featuresets → Compose** (`/featuresets/author`). Everything you type goes to
`/featuresets/preview` on every keystroke, and the **Declare** button is enabled
by that call returning 200 and by nothing else. The *What it would resolve to*
panel is the preview's answer, not the page's opinion.

The page also says plainly which refusals it *cannot* show you before you press
Declare: the preview never sees the name, the label slot or the outcome window,
so a duplicate name or a label slot that is not one of the slots is found on
submit.

### Through the SDK

```python
sets.preview(slots={"ebitda": "numeric",
                    "debt_service": {"dtype": "numeric", "nullable": True}})
```

### Through curl

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets/preview \
  -H 'Content-Type: application/json' \
  -d '{"slots": {"ebitda": "numeric",
                 "debt_service": {"dtype": "numeric", "nullable": true}}}'
```

```json
{
  "slots": {"ebitda": {"dtype": "numeric", "nullable": false},
            "debt_service": {"dtype": "numeric", "nullable": true}},
  "declared_slots": ["debt_service", "ebitda"],
  "inherited_slots": [],
  "lineage": [],
  "provenance": {},
  "detail": "2 slot(s): 2 declared here. the order is the fold: leftmost parent first, rightmost wins, then this set's own slots, then its operations"
}
```

A bare string is a type; a mapping may also say `nullable`. Nothing else — a
slot is a type and a nullability, and that is the whole vocabulary.

---

## 2. Declare the two parents

Two small, honest featuresets. One is about affordability, one about behaviour.
Neither has a label; neither is a training set. They exist to be composed from.

### Through the interface

On **Compose**, panel *1 · What it is called* and panel *2 · Slots it declares
itself*. The type dropdown offers only the types the catalogue actually carries,
because a slot's type must equal its feature's exactly — a list of types nothing
in the register holds is a list of slots nothing can fill. There is no owner
field: the owner is whoever is acting.

### Through the SDK

```python
sets.define(name="sb_core", entity="customer",
            slots={"ebitda": "numeric", "debt_service": "numeric"},
            description="affordability")

sets.define(name="sb_behaviour", entity="customer",
            slots={"utilisation": "numeric",
                   "debt_service": {"dtype": "numeric", "nullable": True}},
            description="behavioural")
```

### Through curl

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_core", "entity": "customer",
  "slots": {"ebitda": "numeric", "debt_service": "numeric"},
  "description": "affordability"}'

curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_behaviour", "entity": "customer",
  "slots": {"utilisation": "numeric",
            "debt_service": {"dtype": "numeric", "nullable": true}},
  "description": "behavioural"}'
```

Both answer `201`. Note that the two disagree about `debt_service`: `sb_core`
says it is never null, `sb_behaviour` allows nulls. That disagreement is
deliberate, and section 3 is what the platform does with it.

---

## 3. Compose a child, and see who decided each slot

A combination of featuresets is a featureset. Name the parents, add the label
slot, and declare nothing else.

### Through the interface

Panel *3 · Featuresets it composes from* and panel *4 · What it changes about
what it inherited*. The operations are `add`, `drop` and `override`, and **every
one of them is total**: adding a slot a parent already has, dropping one no
parent has, overriding one no parent has — each is refused, because an operation
that silently did nothing is one somebody believes happened.

The preview panel updates as you add each parent, and the *The fold, once* card
shows which parent won each slot.

### Through the SDK

```python
sets.preview(composes=[{"name": "sb_core"}, {"name": "sb_behaviour"}],
             operations=[{"op": "add", "name": "defaulted_12m",
                          "value": {"dtype": "numeric"}}])
```

### Through curl

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets/preview \
  -H 'Content-Type: application/json' -d '{
  "composes": [{"name": "sb_core"}, {"name": "sb_behaviour"}],
  "operations": [{"op": "add", "name": "defaulted_12m", "value": {"dtype": "numeric"}}]}'
```

```json
{
  "declared_slots": ["defaulted_12m"],
  "inherited_slots": ["debt_service", "ebitda", "utilisation"],
  "lineage": [
    {"name": "sb_core", "depth": 0, "sealed": false,
     "contributes": ["debt_service", "ebitda"]},
    {"name": "sb_behaviour", "depth": 0, "sealed": false,
     "contributes": ["debt_service", "utilisation"]}
  ],
  "provenance": {
    "ebitda":        {"from": "sb_core",           "overrode": null},
    "debt_service":  {"from": "sb_behaviour",      "overrode": "sb_core"},
    "utilisation":   {"from": "sb_behaviour",      "overrode": null},
    "defaulted_12m": {"from": "(preview) (add)",   "overrode": null}
  },
  "detail": "4 slot(s): 1 declared here, 3 inherited. the order is the fold: leftmost parent first, rightmost wins, then this set's own slots, then its operations"
}
```

Read `provenance`. `debt_service` came from `sb_behaviour` and **overrode**
`sb_core` — so the slot is nullable, because the rightmost parent won.

### The order is not a detail

Swap the parents and the same two objects give a different schema:

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets/preview \
  -H 'Content-Type: application/json' \
  -d '{"composes": [{"name": "sb_behaviour"}, {"name": "sb_core"}]}'
```

```json
{"from": "sb_core", "version": null, "overrode": "sb_behaviour"}
```

Now `sb_core` wins and `debt_service` is not nullable. Composing `[a, b]` and
`[b, a]` are two different featuresets whenever the parents overlap. The
**Schema lattice** screen shows both folds side by side for any two sets, which
is the fastest way to settle an argument about which order somebody meant.

### Two refusals you will meet here

```bash
# an add of something a parent already has
curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets/preview \
  -H 'Content-Type: application/json' -d '{
  "composes": [{"name": "sb_core"}],
  "operations": [{"op": "add", "name": "ebitda", "value": {"dtype": "numeric"}}]}'
```

```json
{"error": "feature_refused",
 "detail": "operation 0: cannot add 'ebitda' — a parent already has it. say 'override' if replacing it is what is meant; the two read differently to a reviewer and should"}
```

```bash
# a parent that is not there
curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets/preview \
  -H 'Content-Type: application/json' -d '{"composes": [{"name": "sb_kore"}]}'
```

```json
{"error": "feature_refused",
 "detail": "cannot compose from 'sb_kore': no such featureset"}
```

Both answer `409`, and both would have been the same refusal from `define`.

### Now declare it

The label slot and the outcome window belong to the child, not to a parent.
`outcome_window_days` is how long after the decision the label is knowable at
all — it is why the model cannot be judged the week it ships.

```python
sets.define(name="sb_pd_2026", entity="customer", slots={},
            composes=[{"name": "sb_core"}, {"name": "sb_behaviour"}],
            operations=[{"op": "add", "name": "defaulted_12m",
                         "value": {"dtype": "numeric"}}],
            label_slot="defaulted_12m", outcome_window_days=365,
            description="the training presentation of X")
```

```bash
curl -u d.raman:… -X POST http://localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_pd_2026",
  "entity": "customer",
  "composes": [{"name": "sb_core"}, {"name": "sb_behaviour"}],
  "operations": [{"op": "add", "name": "defaulted_12m", "value": {"dtype": "numeric"}}],
  "label_slot": "defaulted_12m",
  "outcome_window_days": 365,
  "description": "the training presentation of X"}'
```

`201`. **This set declares no slots of its own** and has four. Read them back
with `GET /featuresets/sb_pd_2026/resolved` (`sets.resolved("sb_pd_2026")`),
which answers with the same `declared_slots`, `inherited_slots`, `lineage` and
`provenance` the preview gave, plus `drift` — see section 5.

Each parent is recorded with the **definition** it was composed against, so a
parent that changes afterwards is reported rather than silently changing this
one.

---

## 4. Fill the slots, and see what got pinned

A version fills every slot with a feature and the exact view version supplying
it. That pin is the whole point: the same featureset version resolves to the
same bytes, because a namespace without a Delta version is a path and a path is
mutable.

### Through the interface

**`/featureset/sb_pd_2026/bind`** — *Bind each slot*. The page lists, for each
feature, which materialised views carry it, because the platform refuses an
ambiguous binding rather than guessing at one and you cannot name the view you
meant without knowing there are two. It lists them; it does not choose.

There is no dry run for bindings — the platform previews the composition and
none of the filling — so **the publish is the check**, and the page says so
rather than claiming a verdict it cannot get. A refused publish writes nothing.

### Through the SDK

```python
sets.fill("sb_pd_2026",
          bindings={"ebitda": {"feature": "ebitda", "view": "sb_financials",
                               "view_version": 1},
                    "debt_service": "debt_service",
                    "utilisation": "utilisation",
                    "defaulted_12m": "defaulted_12m"},
          note="first fill")
```

### Through curl

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/featuresets/sb_pd_2026/versions \
  -H 'Content-Type: application/json' -d '{
  "bindings": {
    "ebitda": {"feature": "ebitda", "view": "sb_financials", "view_version": 1},
    "debt_service": "debt_service",
    "utilisation": "utilisation",
    "defaulted_12m": "defaulted_12m"},
  "note": "first fill"}'
```

A bare string names the feature and lets the platform locate the only view
carrying it. The long form names the view and version explicitly, which is what
you write once there is more than one.

What comes back, for one slot:

```json
{
  "feature": "ebitda",
  "slot": "ebitda",
  "dtype": "numeric",
  "view": "sb_financials",
  "view_version": 1,
  "namespace": "features/customer/sb_financials/v1",
  "delta_version": 0,
  "derived": false,
  "definition_version": null,
  "certification": "experimental"
}
```

`delta_version` is the field a reviewer has to check and cannot get anywhere
else. The `namespace` alone is a path; `delta_version: 0` is the commit. The
version's `digest` is taken over the whole resolved binding map, so two runs
quoting the same digest read the same bytes.

### Four things a binding cannot be

Each answers `409`, and each is worth meeting here rather than in an incident.

**A slot nothing supplies.** The feature is declared but no view carries it:

```json
{"error": "feature_refused",
 "detail": "no materialised feature view supplies 'sector_score'; materialise it before a featureset can pin it"}
```

**A slot whose type is not its feature's.** A set declaring `ebitda` as
`integer`, bound to the `numeric` feature:

```json
{"error": "feature_refused",
 "detail": "slot 'ebitda' holds integer but 'ebitda' is numeric; a version must fill the schema it declares"}
```

**A feature two views carry.** After a re-platforming, `sb_replatform` also
carries `ebitda`, and a bare `"ebitda": "ebitda"` becomes a guess:

```json
{"error": "feature_refused",
 "detail": "'ebitda' is supplied by more than one view (sb_financials, sb_replatform); name the view and version"}
```

Guessing here is how a set silently reads the wrong bytes, so the platform
refuses and asks. Name the view and the version and it publishes.

**A view named without a version.**

```json
{"error": "feature_refused",
 "detail": "'ebitda' names view 'sb_financials' without a version; a featureset version pins exactly, or the same version would resolve to different bytes next month"}
```

---

## 5. The plan, and whether the ground has moved

The plan is one document containing everything an execution engine needs. It
exists because reconstructing it from five endpoints is how two engines end up
disagreeing.

### Through the interface

**`/featureset/sb_pd_2026/plan/1`** — the point-in-time rule, the slots and what
fills each, the deduplicated pins an engine opens, what moved since the previous
version, and the documents filed against this one. One page per version, reached
from the *read* tab or from the version list on the bind screen.

### Through the SDK

```python
algebra.plan("sb_pd_2026", version=1)
algebra.restatements("sb_pd_2026", version=1)
```

### Through curl

```bash
curl -u d.raman:… http://localhost:5006/api/v1/featuresets/sb_pd_2026/versions/1
```

```json
{
  "featureset": "sb_pd_2026",
  "version": 1,
  "entity": "customer",
  "grain": "one row per customer",
  "digest": "sha256:6ff979d8b847617f9db6da5a67f153b930a1ea8263d2f02dd70c23fc4e897970",
  "pit_rule": "event_ts <= label_ts AND ingest_ts <= min(label_ts, as_of)",
  "outcome_window_days": 365,
  "namespaces": ["features/customer/sb_financials/v1",
                 "features/customer/sb_outcomes/v1"],
  "pins": [["features/customer/sb_financials/v1", 0],
           ["features/customer/sb_outcomes/v1", 0]]
}
```

The `pit_rule` is published as a string an engine implements, and it is the
platform's own — MAYA's assembler obeys the same one. The bound is
`min(label_ts, as_of)` because the two clocks refuse different things:
`label_ts` is what the model could have known when the decision was made,
`as_of` is what the platform could have known when the set was built.

### Has anything underneath moved?

The version reads the bytes it pinned — that is what the pin is for. The
neighbouring question, the one a reviewer asks before comparing two runs, is
whether the ground has moved:

```bash
curl -u d.raman:… \
  http://localhost:5006/api/v1/featuresets/sb_pd_2026/versions/1/restatements
```

```json
{"featureset": "sb_pd_2026", "version": 1, "restated": false, "slots": [],
 "detail": "nothing underneath this version has moved"}
```

### Taking up newer data on purpose

Publishing a new view version deliberately changes nothing about an existing
featureset version. Roll forward when you want the new data, and see exactly
what moved in doing so:

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/featuresets/sb_pd_2026/roll-forward
```

```json
{"version": 2, "moved": [
  {"slot": "ebitda", "was": "ebitda @ features/customer/sb_financials/v1",
                     "now": "ebitda @ features/customer/sb_financials/v2"},
  {"slot": "debt_service", "was": "debt_service @ features/customer/sb_financials/v1",
                           "now": "debt_service @ features/customer/sb_financials/v2"},
  {"slot": "utilisation", "was": "utilisation @ features/customer/sb_financials/v1",
                          "now": "utilisation @ features/customer/sb_financials/v2"}]}
```

`algebra.roll_forward("sb_pd_2026")` in the SDK; the **Roll forward** button on
the bind screen. Whoever trained against v1 still reads exactly the bytes v1
pinned.

### When a parent moves

Change a parent's retrieval policy — a definition change, because children
resolve their behaviour through it:

```bash
curl -u d.raman:… -X PUT http://localhost:5006/api/v1/featuresets/sb_core/policy \
  -H 'Content-Type: application/json' \
  -d '{"defaults": {"fill": {"debt_service": "median"}}}'
```

`algebra.set_policy("sb_core", defaults={"fill": {"debt_service": "median"}})`
in the SDK; panel *6 · Default retrieval policy* on the compose screen. A policy
says `fill`, `normalise` and `align` and nothing else.

The child now reports drift, and inherits the policy:

```json
{
  "drift": [{"parent": "sb_core", "composed_against": 1, "now_at": 2, "sealed": false}],
  "policy": {
    "policy": {"fill": {"debt_service": "median"}},
    "decided_by": {"fill": {"debt_service": "sb_core"}},
    "precedence": "parents left to right, then the object, then the request; the rightmost wins"
  }
}
```

Drift is **reported, not refused**. A child whose parent has moved is a thing to
be told about; refusing the read would take the schema away from whoever most
needs to look at it. The bind screen shows it as a banner at the top.

---

## 6. The refusals, which are the point

Every refusal below comes from the code that enforces it. There is a screen that
answers all of them live for one featureset, and it is the fastest way to learn
them.

### Through the interface

**`/featureset/sb_pd_2026/refusals`** — five cards, each answered for this set
now: what leaks, what is unfilled, which model versions can and cannot be fitted
from it, what sealing and ephemerality forbid, and which bindings cannot be
pinned exactly. Nothing on the page is a second opinion.

### Leakage — however many hops away

`expected_loss` is derived from `loss_given_default`, which is derived from
`defaulted_12m`, which is this set's label. Its expression never mentions the
label.

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/featuresets/sb_pd_2026/versions \
  -H 'Content-Type: application/json' -d '{"bindings": {
  "ebitda": "ebitda", "debt_service": "expected_loss",
  "utilisation": "utilisation", "defaulted_12m": "defaulted_12m"}}'
```

```json
{"error": "feature_refused",
 "detail": "'expected_loss' is computed from 'defaulted_12m', which this featureset declares as its label — a feature derived from the label leaks the answer into the training set. derive it from a value known before the outcome, or declare it an output rather than a feature"}
```

The check is the transitive closure, and it runs on **what was asked for**,
before anything is resolved — so a leaking slot is refused whether or not a view
happens to supply it. "You cannot train on the answer" is a better message than
"no view supplies that". The refusals screen lists every feature in the
catalogue that can no longer fill any slot, with how many hops away each one is.

### An unfilled slot

```json
{"error": "feature_refused",
 "detail": "these slots are unfilled: utilisation. a version that cannot fill the schema is not a version of this featureset"}
```

Including the slots you inherited: a composed set owes the slots it inherited as
much as the ones it declared.

### A binding naming no slot

```json
{"error": "feature_refused",
 "detail": "these bindings name no declared slot: expected_loss. adding a slot changes the schema, which changes X — publish it as a different featureset, and expect the model to need a new version"}
```

This is the mirror of the one above, and it is where the model/data distinction
is enforced rather than remembered.

### A schema a kernel cannot consume

A fit warrant naming a set that does not provide what the kernel declares it
reads is refused. `sb_core` has `ebitda` and `debt_service`; the version reads
those and `utilisation`:

```json
{"error": "schema_not_satisfied",
 "detail": "'sb_core' does not provide utilisation, which this version declares it reads",
 "remediation": "bind a featureset whose schema covers the kernel's inputs, or create a model version whose input schema matches this set — adding a regressor is a model change, not a data change"}
```

**There is no read-only endpoint for this question.** The platform answers *does
this set provide what that kernel reads* only as a side effect of issuing a fit
warrant, which writes. Card 3 of the refusals screen asks the same comparison
directly and answers it without writing anything, and that is currently the only
way to get the answer in advance. Issuing the warrant itself belongs to
[warrants and training](/tutorials/warrants-and-training).

### Sealed

Sealing is a second-line act — `sets.seal("sb_pd_2026", note="final for 2026")`,
or `POST /featuresets/sb_pd_2026/seal` with `{"note": "final for 2026"}`. The
button is on the bind screen and is only offered to somebody who may press it,
because an inert control teaches people the platform is broken. A model
developer is refused:

```json
{"error": "forbidden",
 "detail": "'featureset:seal' is not granted by your roles (model_developer)"}
```

A validator seals it, and afterwards:

```json
{"error": "feature_refused",
 "detail": "'sb_pd_2026' was sealed by a.mehta and cannot take another version. compose a new featureset from it instead — that is what sealing is for: a parent that cannot move is a parent worth building on, and the change stays visible in the child"}
```

A sealed set can still be composed from, assembled from and named by a warrant.
It is final, not inert.

---

## 7. The lattice — one order under all of it

`refines(A, B)` reads **"A can stand in for B"**: A has every field B has, each
accepting at least what B's did. A may have extra fields — they are simply not
read — and a shared field that accepts less is a regression.

Four questions in this platform are that one relation, written once in
`core.domain.lattice`: can this version replace that one (`L-12`); can this
featureset be fitted from by that kernel (`L-W10`); can one featureset serve two
models; and what do two schemas agree on.

### Through the interface

**`/featuresets/lattice`** — pick any two schemas in the register (a featureset,
a model version's declared inputs, or ⊤ the empty schema) and press Compare. A
featureset contributes its **resolved** schema with the label left out, because
a kernel does not read the answer.

Comparing `sb_core` with what `SB PD 1.0.0` reads:

```
A ⊑ B — sb_core can stand in for SB PD 1.0.0 reads     no    missing: utilisation
B ⊑ A — SB PD 1.0.0 reads can stand in for sb_core     yes
```

That `no` is the `schema_not_satisfied` above, asked before issuing anything.

The **meet** (⊓) is the union of the fields, each widened enough to accept
both — the schema that could serve *both* models. The **join** (⊔) is the
intersection, each narrowed to what both accepted — what a consumer of either
may rely on.

**Meet is partial, and its failure is the informative case.** Declare
`sb_pd_legacy` — the 2019 presentation, in which `ebitda` was an `integer` —
and compare it with `sb_pd_2026`:

```
A ⊓ B — the meet
Field    In A       In B
ebitda   numeric    integer

There is no meet. No schema can accept both a numeric and an integer in one
slot, so the honest answer to "can one featureset serve both these models" is
no, with the slot named.
```

The join still exists — fields that disagree on their type are simply not
shared, which is why the join is total and the meet is not.

The same page also runs the composition fold both ways round on two real
featuresets, so you can see for yourself that the order is not commutative.

### Through the SDK and curl

**Neither is reachable.** `refines`, `meet` and `join` have no HTTP endpoint and
therefore no SDK call; the lattice screen calls `core.domain.lattice` directly,
and it says so. Over the API the order reaches you in exactly two ways: as the
`schema_not_satisfied` refusal from `POST /fit-warrants`, and as the version
variance check when a new model version replaces an old one. If you need the
answer in a script today, issue the fit warrant in a lab environment and read
the refusal.

### One thing this section verifies

A featureset composed from parents, declaring nothing of its own, **satisfies
the kernel it covers**:

This is `L-W10`, and it is checked against the **version's declared inputs** —
so it needs a version that reads what this set provides. The model from
[defining a model](/tutorials/defining-a-model) reads `dscr`, which
`sb_pd_2026` does not carry, and asking anyway is refused with
`schema_not_satisfied: 'sb_pd_2026' does not provide dscr, which this version
declares it reads`. That refusal is the section's point arriving early; here is
the version that satisfies it:

```bash
curl -u j.okafor:… -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.sbset", "name": "SB PD over sb_pd_2026",
  "model_class": "credit.pd.scorecard", "domain": "credit",
  "owner": "person/j.okafor", "legal_entity": "LE-US-01",
  "purpose": "PD defined over the composed featureset"}'

curl -u d.raman:… -X POST \
  localhost:5006/api/v1/models/credit.pd.sbset/versions \
  -H 'Content-Type: application/json' -d '{
  "semver": "1.0.0",
  "kernel": {"parameter_kind": "estimated_coefficients",
             "fit_procedure": "estimate", "output_kind": "point_estimate",
             "runtime": "estimator",
             "entry": {"family": "ols", "target": "pd_12m",
                       "regressors": ["ebitda", "debt_service",
                                      "utilisation"]},
             "input_schema": [{"name": "ebitda", "dtype": "numeric"},
                              {"name": "debt_service", "dtype": "numeric"},
                              {"name": "utilisation", "dtype": "numeric"}],
             "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]},
  "contract": {"assumptions": [{"key": "ebitda", "minimum": 0}],
               "guarantees": [{"key": "pd_12m", "minimum": 0,
                               "maximum": 1}]}}'
```

A warrant resolves against an **alias**, not a semver, so the version has to be
approved and the alias pointed at it — the same two acts as
[defining a model §6](/tutorials/defining-a-model):

```bash
curl -u j.okafor:… -X POST localhost:5006/api/v1/models/credit.pd.sbset/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure": 40000000, "purpose_class": "risk_management",
       "feature_count": 3, "uses_alternative_data": false,
       "interpretable": true}'

curl -u s.iqbal:… -X POST \
  localhost:5006/api/v1/models/credit.pd.sbset/versions/1.0.0/approve \
  -H 'Content-Type: application/json' -d '{"note": "reviewed"}'

curl -u s.iqbal:… -X PUT localhost:5006/api/v1/models/credit.pd.sbset/aliases \
  -H 'Content-Type: application/json' \
  -d '{"semver": "1.0.0", "environment": "prod", "alias": "champion",
       "justification": "first version over the composed set"}'

curl -u j.okafor:… -X POST localhost:5006/api/v1/models/credit.pd.sbset/submit \
  -H 'Content-Type: application/json' -d '{"note": "ready"}'
curl -u s.iqbal:… -X POST localhost:5006/api/v1/models/credit.pd.sbset/approve \
  -H 'Content-Type: application/json' -d '{"note": "tier 3 controls in place"}'
```

A fit warrant is then minted against a **grant** — *this principal may ask* — so
the lab account needs one, or the answer is
`no_entitlement: svc/model-lab holds no warrant for … in prod`:

```bash
curl -u j.okafor:… -X POST http://localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.sbset", "environment": "prod",
  "principal": "svc/model-lab", "declared_use": "model_development"}'
```

```bash
curl -u j.okafor:… -X POST http://localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.sbset", "environment": "prod",
  "principal": "svc/model-lab",
  "featureset": "sb_pd_2026", "featureset_version": 2,
  "window": {"from": 1546300800.0, "to": 1735603200.0}, "as_of": 1753920000.0}'
```

`201`, and a signed descriptor. Its `data.inputs[0]` — the featureset half —
reads:

```json
{
  "name": "training_set",
  "binding": "featureset",
  "featureset": "sb_pd_2026",
  "version": 2,
  "digest": "sha256:d7539f097c449e24e25477b015cf31dc9c87088e38541b26b0345626ceada32e",
  "as_of": 1753920000.0,
  "window": {"from": 1546300800.0, "to": 1735603200.0},
  "entity": "customer",
  "grain": "one row per customer",
  "outcome_window_days": 365,
  "namespaces": ["features/customer/sb_financials/v2",
                 "features/customer/sb_outcomes/v1"],
  "pit_rule": "event_ts <= label_ts AND ingest_ts <= min(label_ts, as_of)"
}
```

The plan travelled into the warrant intact — same digest, same pins, same rule.
The rest of the descriptor is [warrants and
training](/tutorials/warrants-and-training)'s business.

That is worth checking on your own instance if you are on an older build: the
comparison used to read the set's *own* row while `publish` filled the
**resolved** schema, so a composed set reported an empty schema and satisfied no
kernel at all — refused for slots it demonstrably had and had just been
published with.

---

## 8. Assemble a training set

The set supplies the columns and the pins. **You** supply the spine — which
entities, as at which label times — and the `as_of`. That division is the whole
design: the platform cannot know which population you are training on, and you
should not be inventing the point-in-time rule.

### Through the interface

**`/featureset/sb_pd_2026/assemble`**. The page shows the rows already sitting
in each pinned namespace, read at the pinned Delta version, so you can build a
spine against entities that exist rather than assembling a table of nulls.

### Through the SDK

```python
sets.training_set("sb_pd_2026", version=2, as_of=1753920000.0, spine=[
    {"entity_id": "C1", "label_ts": 1751328000.0, "label": 0.0},
    {"entity_id": "C2", "label_ts": 1751328000.0, "label": 1.0},
    {"entity_id": "C3", "label_ts": 1751328000.0, "label": 0.0}])
```

### Through curl

```bash
curl -u d.raman:… -X POST \
  http://localhost:5006/api/v1/featuresets/sb_pd_2026/training-sets \
  -H 'Content-Type: application/json' -d '{
  "version": 2,
  "spine": [{"entity_id": "C1", "label_ts": 1751328000.0, "label": 0.0},
            {"entity_id": "C2", "label_ts": 1751328000.0, "label": 1.0},
            {"entity_id": "C3", "label_ts": 1751328000.0, "label": 0.0}],
  "as_of": 1753920000.0,
  "name": "sb_pd_2026_train"}'
```

```json
{
  "name": "sb_pd_2026_train",
  "kind": "training",
  "row_count": 3,
  "as_of": 1753920000.0,
  "pit_verified": true,
  "pit_report": {"passed": true, "layer": "sampled", "checked": 3,
                 "violations": [], "leakage": [],
                 "detail": "3 of 3 rows independently recomputed"},
  "featureset": "sb_pd_2026",
  "featureset_version": 2,
  "digest": "sha256:7b1c7b4fd58ec7af8cc403bfb1c3790c514afd7b4661a4109c8242b3c09cc847",
  "id": "01a0737bc08271e8f34b7a87e0a8"
}
```

Two layers ran, and they prove different things.

- **Layer 1, static.** Both temporal bounds must be present or the assembly is
  *rejected*, not warned about. That is a proof for the dominant leakage class:
  without both bounds, `min(label_ts, as_of)` was never computed.
- **Layer 2, sampling.** An independent recomputation over a stratified sample —
  `"3 of 3 rows independently recomputed"`. It detects systematic violations. It
  does not prove absence, and the report says `layer: "sampled"` rather than
  claiming more than it did.

The snapshot names the featureset version, so a fit warrant can pin the snapshot
and recompute nothing. That is where [warrants and
training](/tutorials/warrants-and-training) picks up.

To read the rows rather than snapshot them, `sets.data("sb_pd_2026", version=2,
into="x.parquet", as_of=…)` streams to a file, or
`GET /featuresets/sb_pd_2026/versions/2/data?as_of=…&format=json&limit=3` for a
capped look. `as_of` is required: an export is a claim about what was known at a
moment, and defaulting it would make that moment whatever the clock happened to
say.

---

## 9. Documents against a featureset version

**Yes — a featureset version is one of the six things a document can be about.**
A data dictionary or a source-system agreement describes *one filled schema*,
and it is pinned to the version rather than to the set, because a document filed
against the set would describe something that has since moved.

Three things to know before you file one.

- **The subject is the version, never the set.** `subject_type` must be
  `featureset_version`.
- **A document still hangs under a model URN.** There is no way to file one
  against a featureset version alone.
- **The version's id comes from the plan.** `GET
  /featuresets/{name}/versions/{n}` carries it as `id`. It did not until this
  page was run against a live instance: `GET /featuresets/{name}` lists versions
  by number, digest and note, the plan carried everything about the version
  except what identifies it, and the only way to file a document was to read the
  id off a screen and retype it. This page said so in prose and then printed a
  curl example nobody could complete.

### Through the interface

**`/featureset/sb_pd_2026/plan/2`**, the *Documents filed against this version*
card. It lists what is filed, links each to its bytes, and — when nothing is
filed — prints this version's id and the call to make. There is no upload form
on this screen; the filing itself is the API call below.

### Through the SDK

```python
maya.attachments.subjects()          # the six, with their meanings and whether pinned

maya.attachments.attach("maya://model/credit.pd.smallbiz",
                        "sb_pd_2026_v2_dictionary.md",
                        kind="other",
                        title="sb_pd_2026 v2 - data dictionary",
                        subject_type="featureset_version",
                        subject_id="01a0737bc02a940f5461180a85bc")
```

```json
{"id": "01a0737f87e410047f435f807bb5",
 "subject_type": "featureset_version",
 "subject_id": "01a0737bc02a940f5461180a85bc",
 "kind": "other", "state": "attached",
 "digest": "sha256:820f225bf149cd5f16a11b04f5aebb2bdbc2f5adcf27e73a865b6a1eefd6f36a"}
```

Call `subjects()` rather than trusting a list in your own code: the vocabulary
is published so a subject added to the platform is reachable from an SDK nobody
rebuilt.

### Through curl

The version id above is from the run that produced this page. Take yours from
the register rather than pasting one, and make the file the upload needs:

```bash
printf '# sb_pd_2026 v2\n\n| slot | source |\n|---|---|\n| ebitda | finance.warehouse |\n' \
  > sb_pd_2026_v2_dictionary.md

FSV=$(curl -s -u d.raman:… localhost:5006/api/v1/featuresets/sb_pd_2026/versions/2 \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -u d.raman:… -X POST http://localhost:5006/api/v1/attachments \
  -F "urn=maya://model/credit.pd.smallbiz" \
  -F "kind=other" -F "model_level=1" \
  -F "title=sb_pd_2026 v2 - data dictionary" \
  -F "subject_type=featureset_version" \
  -F "subject_id=$FSV" \
  -F "file=@sb_pd_2026_v2_dictionary.md;type=text/markdown"
```

```json
{
  "id": "01a0737bc28952113a77f82b903d",
  "subject_type": "featureset_version",
  "subject_id": "01a0737bc02a940f5461180a85bc",
  "kind": "other",
  "title": "sb_pd_2026 v2 - data dictionary",
  "digest": "sha256:eff1623a75ebbed7add248f66e9faa0b3360a124d9c8fe8f22242c510d48afa0",
  "state": "attached"
}
```

Filing it against the set instead is refused:

```json
{"error": "unknown_subject",
 "detail": "'featureset' is not something a document can be about",
 "remediation": "use one of model, model_version, parameter_set, featureset_version, feature, validation; a subject the platform cannot resolve is a document nobody will find from the thing it describes"}
```

Two rough edges to expect. **There is no `data_dictionary` kind** — the kinds
are the nine in `GET /attachment-kinds`, so a data dictionary is filed as
`other` with a title that says what it is. And **there is no endpoint that lists
what is filed against a subject**: `GET /attachments?urn=…`
(`maya.attachments.list(urn)`) is addressed by model, and returns each document
with its `subject_type` and `subject_id` for you to filter on. The model's
dossier reaches a featureset version only through a parameter set whose fit read
it, so it will not show this document until something has been fitted. The plan
screen reads the register directly for its card.

The document is content-addressed, so it cannot be edited in place — a revision
has a different digest, which is a different document, which is a supersession
somebody declares. It lands `attached` and is accepted or rejected by somebody
other than whoever filed it. See [documentation](/help/documentation).

---

## What you can rely on

- **A featureset version resolves to the same bytes, always.** Every binding
  pins a Delta version, not a path.
- **A composed set owes every slot it inherited**, and satisfies a kernel on the
  strength of its resolved schema, not its own row.
- **The rightmost parent wins**, and `provenance` names which one did for every
  slot.
- **Nothing computed from the label can fill another slot**, however many
  derivations away and whatever the expressions say.
- **A new view version changes nothing** until somebody rolls forward on
  purpose, and the roll forward comes with a diff.
- **`refines` is one relation with one implementation**, so version
  substitutability and featureset satisfaction cannot disagree.

## Next

[Warrants and training](/tutorials/warrants-and-training) takes one of these
snapshots, issues the warrant that authorises a fit, and records what came out.
If a slot here had no feature behind it, go back to
[features](/tutorials/features). The whole chain in one sitting is [end to
end](/tutorials/end-to-end); what ships at the other end is the [model
package](/tutorials/model-package); and the model itself starts at [defining a
model](/tutorials/defining-a-model).

Reference: [featuresets and parameters](/help/featuresets-and-parameters),
[features and the two clocks](/help/features-and-two-clocks),
[warrants](/help/warrants), [documentation](/help/documentation),
[API reference](/help/api-reference), [glossary](/help/glossary).

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE.
*Not legal, regulatory or financial advice — see NOTICE §4.*
