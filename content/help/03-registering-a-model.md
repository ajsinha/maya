---
title: Registering a model
slug: registering-a-model
section: The register
order: 30
icon: box-seam
summary: The two acts that bring a model into the register, the T0–T8 class derived from what the version declares, the schema and contract obligations that gate a promotion, and how a model's artifact and its dependencies are recorded.
audience: Model owners, Engineers
---

# Registering a model

Two acts bring a model into the register, and the split is the whole design.

**Registering the model** creates the record: who owns it, what it is for, which
entity carries it. It is deliberately cheap.

**Creating a version** declares the kernel: how the parameter object is
inhabited, what it reads, what it returns, and what it promises. Everything
consequential hangs here — the trainability class, the schemas, the operating
contract, the artifact digest — and everything downstream is derived from it.

## What counts as a model

Supervisory guidance is broad on purpose. SR 26-2 and its predecessors define a
model as a quantitative method that applies statistical, economic, financial or
mathematical theories to process input data into quantitative estimates.

Read literally — and it is meant literally — that covers a great deal no
inventory captures:

| It looks like | It is still a model |
|---|---|
| A pricing library call (Black–Scholes, SABR, Hull–White) | Yes — theory-derived parameters, quantitative estimate |
| A spreadsheet an analyst maintains | Yes — the classic end-user-computed model |
| A vendor black box you cannot open | Yes — opacity is a control problem, not an exemption |
| A prompt bundle with a foundation model behind it | Yes — configured, not trained, but a model |
| A rules engine encoding credit policy | Yes — authored parameters |
| A regulatory capital calculator (SA-CCR, RWA) | Yes — and usually Tier 1 |

All of them sit in one population. They differ in what evidence is appropriate,
not in whether they are governed, and the [trainability
classes](#trainability-classes-t0-to-t8) below are how one definition stretches
that far without going vacuous.

## The URN

```
maya://model/credit.pd.smallbiz
```

The permanent handle. Chosen once and never changed, because consumers bind to it
and everything downstream — warrants, evidence, findings, documents — hangs off
it.

Conventions that hold up:

- **Domain first**, then subject, then variant: `credit.pd.smallbiz`,
  `market.var.equities`, `ops.kyc.summariser`.
- **No version in the URN.** Versions are separate objects; a URN that says `_v2`
  is a URN you will have to abandon.
- **No environment in the URN.** The same model runs in dev and prod; the
  environment is a coordinate on the alias, not on the identity.

A qualifier is *appended* at resolution, never stored in the identity:

```
maya://model/credit.pd.smallbiz              the environment's champion
maya://model/credit.pd.smallbiz@3.2.1        a pinned version
maya://model/credit.pd.smallbiz#challenger   a named alias
```

## Registering: the fields, and why

```json
{
  "urn": "maya://model/credit.pd.smallbiz",
  "name": "Small Business PD",
  "model_class": "credit.pd.scorecard",
  "domain": "credit",
  "owner": "person/j.okafor",
  "legal_entity": "LE-US-01",
  "purpose": "12-month PD at origination",
  "description": "Logistic scorecard over financial and behavioural features.",
  "origin": "internal"
}
```

**owner** — a person, not a team. A model owned by "Credit Analytics" is a model
nobody will be asked about, and a finding needs an owner who can be paged.

**legal_entity** — because model risk aggregates by entity, not by org chart. The
same model used by two entities is two exposures to two supervisors, and it is
also the dimension a principal's scope is cut on.

**purpose** — the *declared* use, and it is load-bearing. A warrant carries a
`declared_use`, and resolution refuses with `use_not_approved` if the use
presented is not the use approved. A model approved for origination decisioning
that starts being used for pricing has changed its risk profile without changing
a line of code, and this is the field that catches it.

**domain** and **model_class** — how the estate is sliced for reporting, and two
of the nine facts a warrant profile may select on.

**origin** — conventionally `internal`, `vendor`, `open_source` or `hybrid`. Free
text rather than an enum, and descriptive: it records what evidence is obtainable
at all. You cannot ask a vendor black box for its coefficients; you can ask for
its validation report and its version notes.

Registration produces a **draft** model with no tier and no versions. That is
deliberate. The alternative — a heavyweight intake form — is what drives people
to route around the platform, and an estate governed by a platform people avoid
is worse than one governed by a spreadsheet they use.

## Versions are immutable

A version is created once and never edited. Creating `3.2.1` twice is refused:

```
version 3.2.1 already exists for maya://model/credit.pd.smallbiz;
versions are immutable
```

This is not fastidiousness. Three things depend on it:

1. **The manifest digest means something.** If a version could be edited, a
   digest recorded last March would prove nothing about what runs today.
2. **A warrant can name a version.** An engine that resolved `3.2.1` in January
   and again in June got the same model, and can prove it.
3. **Evidence stays attached.** A validation result is about a specific artifact.
   Let the artifact change underneath and the result becomes a statement about
   nothing.

Need a change? Create `3.2.2`. Versions are cheap; ambiguity is not.

A version can also be refused for a reason that is about the *model*: an attested
record is immutable, and a new version is a change to the model. That refusal is
`registry_refused` at **409**, and it points at opening an amendment. See
[Approval, attestation and segregation of
duties](/help/approval-and-attestation).

## The kernel specification

Every model in MAYA is one shape:

> a parameter object **P**, an input **X**, an output **Y**, and a kernel
> **f : P ⊗ X → D(Y)**

The version declares how that shape is filled in.

```json
{
  "semver": "3.2.1",
  "kernel": {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "output_kind": "point_estimate",
    "deterministic": true,
    "adaptive": false,
    "runtime": "pmml",
    "input_schema":  [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
    "output_schema": [{"name": "pd_12m", "dtype": "float"}]
  },
  "contract": { "…" },
  "artifact_digest": "sha256:9f2c1a…",
  "artifact_uri": "maya://artifact/sha256:9f2c1a…"
}
```

`parameter_kind` — how `P` is inhabited. One of eight: `none`,
`calibration_set`, `estimated_coefficients`, `learned_weights`,
`llm_configuration`, `rule_set`, `elicited_weights`, `opaque`.

`fit_procedure` — how it got that way. One of seven: `none`, `calibrate`,
`estimate`, `train`, `elicit`, `configure`, `author`.

The model page renders exactly this back as **the model, as its type** — `P`,
`X`, `D(Y)` side by side, with the class printed beside the two facts it comes
from.

## Trainability classes T0 to T8

Most model inventories were designed around one implicit assumption: a model is
something that was **trained on data**. Ask that inventory to hold a
Black–Scholes pricer, a credit policy rulebook or a prompt bundle and it either
rejects them or forces them into fields that make no sense — a "training dataset"
for an analytic formula, a "model performance" metric for a rulebook.

MAYA asks a different question. The class is about **how the parameter object is
inhabited**, and training is one of the ways.

| Class | `P` is inhabited by | Bank examples |
|---|---|---|
| **T0** | Nothing — `P` is the terminal object. Parameters come from theory | Black–Scholes closed form, SA-CCR, standardised RWA, accrual mechanics |
| **T1** | Calibration to market observables, re-solved each period | Hull–White to swaption vols, SABR surfaces, bootstrapped curves |
| **T2** | Statistical estimation from a sample | Logistic PD scorecards, OLS/GLM, ARIMA, Cox survival models |
| **T3** | A training run over a loss | Gradient boosting, random forests, neural networks |
| **T4** | Training that continues after deployment | Online learners, bandits, adaptive fraud models |
| **T5** | Configuration of a pre-trained foundation model | Prompt bundles, RAG pipelines, fine-tune-free LLM applications |
| **T6** | Opaque — `P` exists, you cannot see it | Vendor black boxes, licensed scoring services |
| **T7** | Expert elicitation | Judgemental overlays, expert-weighted scorecards, scenario narratives |
| **T8** | Authorship — a human wrote the parameters | Credit policy rulebooks, deterministic eligibility logic. The one class whose parameter object the platform can *read*: see [Rule sets](/help/rule-sets) |

### It is derived, never declared

You cannot send `"trainability_class": "T2"`. There is no such request field
anywhere in the API. The derivation is decided in this order:

1. **Parameters you cannot see are T6.** `parameter_kind: opaque` means `P` is
   inaccessible, and inaccessibility dominates everything else.
2. **No parameter object at all is T0.** `parameter_kind: none` — `P` is the
   terminal object, and there is nothing to inhabit.
3. **Training that continues is T4.** `fit_procedure: train` **and**
   `adaptive: true`. Both, or it is not T4.
4. **Otherwise the fit procedure decides:** `calibrate` → T1, `estimate` → T2,
   `train` → T3, `configure` → T5, `elicit` → T7, `author` → T8, and `none` → T0.

Read the ordinary cases off that:

| `parameter_kind` | `fit_procedure` | `adaptive` | Class |
|---|---|---|---|
| `estimated_coefficients` | `estimate` | — | **T2** |
| `learned_weights` | `train` | `false` | **T3** |
| `learned_weights` | `train` | `true` | **T4** |
| `calibration_set` | `calibrate` | — | **T1** |
| `llm_configuration` | `configure` | — | **T5** |
| anything | anything | — | **T6** if `opaque` |

Two things follow from step 4 that surprise people. It is the **fit procedure**
that carries the class, not the parameter kind's name: an `llm_configuration`
whose fit procedure is `none` derives **T0**, not T5, because T5 is what
`configure` gives you. And `learned_weights` with `train` is **T3** — T4 is
reserved for the model that is still learning in production, which is a
materially different control problem. If the class that comes back is not the one
you expected, the fit procedure is what to look at.

The reason for deriving at all is behavioural. A declared class is a field
somebody fills in, and the value they fill in is the one that asks least of them.
*"It's T0, so there is no training data to produce"* is an appealing sentence,
and it is not one an owner should be able to write about a gradient boosting
model. Derivation moves the lie one step back, to `parameter_kind` and
`fit_procedure` — which are checkable against the artifact, and which the
version's schema and contract have to be consistent with.

### What the class actually changes

**What evidence is appropriate.** Asking a T0 analytic pricer for a training set
is a *type error*, not a missing document. MAYA will not ask for one and will not
record its absence as a gap. A T3 model with no training data lineage is a
genuine gap and is recorded as one.

**What operations are admissible.** You cannot `fit` a T0 or T6 model — one has
nothing to fit, the other has nothing you can reach. A warrant asking for it is
refused at the grammar level by law **L-W1**:

```json
{"law": "L-W1", "path": "operation.verb",
 "detail": "a T0 model cannot be fitted: its parameters come from theory, not
            from data — there is nothing to fit",
 "remediation": "ask for 'score', 'validate' or 'explain'; if this model really
                 is fitted, its parameter_kind and fit_procedure are wrong"}
```

**What monitoring makes sense.** A T1 calibrated model is re-solved daily, so
parameter movement is normal operation rather than an alert; what matters is
calibration error against the instruments. A T3 model's parameters should not
move at all between retrains, so any movement is an incident.

**How much scrutiny it attracts.** T3, T4, T5 and T6 raise complexity; T4 and T5
raise it twice. T0, T1, T2, T7 and T8 raise it not at all. See [Risk
tiering](/help/risk-tiering#materiality-is-a-join-complexity-is-not-a-lattice).

**Which profiles select the warrant request.** The class is one of the nine facts
a warrant profile may test, and profiles may only select on facts the platform
derives. See [Warrants](/help/warrants#profiles-templating-the-request-never-the-warrant).

### The uncomfortable one

**Most of a bank's model estate is not T3.** Counting by artifact, the T0/T1
population — pricing, capital, accrual, curve construction — usually dwarfs the
machine-learned population, and it is systematically under-governed because the
inventory was built for models that have training sets.

That inversion is the argument for classifying this way rather than asking "is it
AI?".

## Schemas are contracts, not documentation

The input and output schemas are checked when an alias moves. Input schemas are
**contravariant** and output schemas **covariant**: the replacement must accept at
least everything the incumbent accepted and promise at least everything it
promised. That is law **L-12**, and it is one comparison — `refines`, on the
schema lattice — used in four places that used to have four implementations of it:
an alias move, a fit warrant's featureset check (**L-W10**), a featureset
parent's refinement, and a typed dependency edge.

Be careful about the direction, because the intuition points the wrong way. A
*wider* acceptance is fine; a *narrower* one regresses. A version that narrows an
input range is not a drop-in replacement, however much better it scores, and the
alias move is refused naming the field that broke it.

## The operating contract

```json
"contract": {
  "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
  "guarantees":  [{"key": "gini", "minimum": 0.42}],
  "on_boundary_violation": "reject"
}
```

Read as: *given* inputs within the assumptions, the model *guarantees* the stated
properties. Outside the assumptions the guarantee is void — a far more honest
statement than a model that silently extrapolates.

`on_boundary_violation` is `reject`, `flag` or `clamp`, defaulting to `reject`.
It travels in the warrant with the rest of the contract, so an engine can check
the boundary **before** touching the artifact and refuse rather than produce a
number nobody should rely on.

When an alias moves, the replacement's contract must **refine** the incumbent's
— assume no more, guarantee no less. That is law **L-7**, discharged alongside
L-12 on every move, and the move's response carries both proofs and their
reasons.

Contracts also **compose**, and composing is not the same as adding two lists
together. Wire a PD model into an ECL stack and the pair's guarantees are both
promises together; its assumptions are what the *caller* must still meet — the
stack's own assumptions, less the ones the PD model's guarantee already implies.
A stack assuming a PD in `[0,1]` fed by a model guaranteeing exactly that does
not ask anybody outside the pair for it.

The case worth knowing about is the one in between. A PD model guaranteeing
`[0,2]` into a stack assuming `[0,1]` *looks* covered by the wiring and is not:
the assumption stays with the caller, and MAYA reports that key separately on the
composition screen rather than letting it disappear into a discharged list. The
same rule governs the quotient — *given what we have, what must the challenger
deliver?* — where a partner promising `gini ≥ 0.2` discharges nothing at all
against a target of `gini ≥ 0.4`.

## Artifacts

`artifact_digest` is the content hash of whatever actually runs — the ONNX graph,
the PMML document, the prompt bundle, the workbook. `artifact_uri` says where to
look. **A digest with no location cannot be fetched; a location with no digest
cannot be checked**, which is why a version records both.

MAYA can also hold the bytes. The **artifact store is content-addressed**: a
file's name is its own hash, so there is no separate identifier to get wrong.

```bash
curl -u d.raman:… -X POST \
  'localhost:5006/api/v1/artifacts?format=pmml' \
  --data-binary @sb_pd.pmml
```

`format` and the optional `digest` are query parameters; the body is the file.
Supply a digest and it is **checked, not trusted** —
`artifact_digest_mismatch` at 409 if the bytes disagree. Eight formats are
accepted: `onnx`, `pmml`, `safetensors`, `torchscript`, `pfa`, `json`, `tar`,
`gguf`. There is deliberately no `pickle`. `torchscript` and `tar` are flagged as
executing on load, and the flag travels into every warrant that names them.

```bash
GET /api/v1/artifacts/{digest}          # the bytes
GET /api/v1/artifacts/{digest}/verify   # re-derive the hash from disk
GET /api/v1/artifact-usage              # how many, how large
```

`verify` re-hashes what is on disk rather than reporting what was recorded. If it
comes back `intact: false`, the answer is not to investigate later: *the bytes on
disk are not what this address promises; do not run this artifact and raise a
security incident.*

Registering a version whose digest the store already holds rewrites
`artifact_uri` to `maya://artifact/{digest}` and fills the format from the store,
because **the store is the authority on its own contents**.

Why the digest matters even when MAYA does not hold the bytes:

- It works for artifacts MAYA must not hold — a vendor binary under licence, a
  container in a registry, a model too large to duplicate.
- It is checkable at execution time. The engine verifies what it loaded against
  what the warrant said, so a swapped artifact is detected rather than assumed
  away.
- It is stable. The same model registered twice from two pipelines produces the
  same digest, which is how duplicate registration gets caught.

### Descriptor-only is a state, not a flag

`artifact_digest` is optional on **any** version, and a version without one is
read as **descriptor-only**: MAYA holds the governance, somebody else holds the
artifact. That is an honest state and the platform records it as a limitation
rather than claiming an assurance it does not have — a compiled document prints
*"none recorded — this version is descriptor-only"* rather than leaving the field
blank, and the warrant carries the `descriptor_only` runtime, which law **L-W6**
forbids fitting.

It is not a flag somebody sets and it is not tied to `origin: vendor`. It is what
the register reads off the absence of a digest and a runtime, which is why it
cannot be switched off to make a dashboard look better.

## How one model stands to another

Five relations, recorded between **models** rather than versions — the estate
question is which models depend on this one, not which builds did.

| Relation | Means | Propagates | Type-checked |
|---|---|---|---|
| `input_to` | this model's **output is read as an input** by that one | yes | **yes** |
| `calibrated_by` | its parameters are solved by that model or procedure | yes | no — a calibration solves parameters rather than handing an output to an input |
| `derives_from` | built from it: a variant, a recalibration for another book | no | no |
| `challenger_of` | built to argue with it | no | no |
| `benchmark_for` | used as a reference point to judge it against | no | no |

`input_to` was called `feeds`, and that was a bad name in a bank, where a *feed*
means market data or a nightly file — so `A feeds B` read as though MAYA consumed
or produced one. **It does neither.** MAYA moves no data and runs no model; the
edge is a statement about two entries in the register, and the wire it describes
is carried by whatever engine runs the two ends. `feeds` is still accepted on the
way in and stored under the new name, and is deliberately not published in the
vocabulary: two words for one relation invites somebody to think they mean
different things.

`input_to` is **typed composition, not a drawing**. The edge is refused unless the
source's output schema refines the target's input schema — the same comparison
L-12 makes at an alias move, one level out. Extra outputs are fine and simply
unread; a missing output is a wire to nowhere; a narrowed output is the same
regression, refused. If either end has no version yet the edge is recorded
*without* a type check and the log says so, because refusing an edge for a schema
nobody has decided would make the register harder to build than the estate is to
describe.

`challenger_of` and `benchmark_for` are deliberately not type-checked and
deliberately not propagating: they record how somebody *thinks* about a model,
and a challenger counted as a dependency would inflate every blast radius it
appeared in.

```bash
POST /api/v1/model-relations         # record one, with a note
POST /api/v1/model-relations/remove  # remove one, with a reason
POST /api/v1/blast-radius            # what a change here reaches, and how far
POST /api/v1/shared-dependencies     # what two or more models both depend on
```

## Approval

A version is `draft` until approved, and an alias may only point at an approved
version:

```
version 3.2.2 is 'draft', not approved; an alias may only point at an
approved version
```

**Assessment comes before approval.** The tier decides how many signatures a
version's approval needs, so a version on an untiered model cannot be approved at
all — approving first would be choosing your own control depth. On tiers 1 and 2
approval is a quorum; on 3 and 4 it is one call:

```bash
POST /api/v1/models/{name}/versions/{semver}/approve
```

Moving the alias is the most tightly controlled operation in the platform. Three
things are checked, in this order: the target version is approved; no blocking
finding stands against the model; and L-7 and L-12 hold against the incumbent.
See [Warrants and execution](/help/warrants) for what a resolved alias produces.

## Through the interface

`/models/new` does the same two acts against the same two endpoints an execution
engine uses.

**Register the model** — the urn, the name, the class, the domain, the legal
entity, the owner and what it is for. Nothing about how it runs; that belongs to
a version.

**Upload a version** — the kernel. How `P` is inhabited and by what procedure
(the class is *derived* from those two, never declared), the runtime and its
entry, the input and output schemas, and the artifact's digest and location.

### The same path, from an execution engine

An engine that has just finished a fit does exactly this:

```
POST /api/v1/models                    # once, when the model first exists
POST /api/v1/models/{name}/versions    # the kernel that will run
POST /api/v1/artifacts                 # the bytes, addressed by their own hash
POST /api/v1/parameters                # the inhabitant of P it produced
```

Fitted parameters are accepted only against a warrant MAYA issued, and only when
they name the featureset version that produced them. Somebody other than whoever
recorded them approves them before anything runs on them. See [Featuresets and
fitted parameters](/help/featuresets-and-parameters).
