---
title: Registering a model
slug: registering-a-model
section: The register
order: 30
icon: box-seam
summary: What counts as a model, what the register asks for and why, how an immutable version declares its kernel and its operating contract, and the T0–T8 class derived from it.
audience: Model owners, Engineers
---

# Registering a model

Registration creates the record. A **version** hangs off it and carries
everything consequential — the kernel specification, the schemas, the operating
contract, the artifact digest. This page covers the whole of that: what may be
registered, how it is identified, what a version declares, and the trainability
class derived from what it declares.

## What counts as a model

Supervisory guidance is broad on purpose. SR 26-2 and its predecessors define a
model as a quantitative method that applies statistical, economic, financial or
mathematical theories to process input data into quantitative estimates.

Read literally — and it is meant literally — that includes a great deal that no
inventory captures:

| It looks like | It is still a model |
|---|---|
| A pricing library call (Black–Scholes, SABR, Hull–White) | Yes — theory-derived parameters, quantitative estimate |
| A spreadsheet an analyst maintains | Yes — this is the classic end-user-computed model |
| A vendor black box you cannot open | Yes — opacity is a control problem, not an exemption |
| A prompt bundle with a foundation model behind it | Yes — configured, not trained, but a model |
| A rules engine encoding credit policy | Yes — authored parameters |
| A regulatory capital calculator (SA-CCR, RWA) | Yes — and usually Tier 1 |

MAYA registers all of them in one population. They differ in what evidence is
appropriate, not in whether they are governed. The
[trainability classes](#trainability-classes-t0-to-t8) below are how one
definition stretches that far without becoming vacuous.

## The URN

```
maya://model/credit.pd.smallbiz
```

This is the permanent handle. It is chosen once and never changes, because
consumers bind to it and everything downstream — warrants, evidence, findings —
hangs off it.

Conventions that hold up over time:

- **Domain first**, then subject, then variant: `credit.pd.smallbiz`,
  `market.var.equities`, `ops.kyc.summariser`.
- **No version in the URN.** Versions are separate objects; a URN that says
  `_v2` is a URN you will have to abandon.
- **No environment in the URN.** The same model runs in dev and prod; the
  environment is a coordinate on the alias, not on the identity.

A version or alias can be *appended* when resolving:

```
maya://model/credit.pd.smallbiz          the environment's champion
maya://model/credit.pd.smallbiz@3.2.1    a pinned version
maya://model/credit.pd.smallbiz#challenger   a named alias
```

## The fields, and why

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
nobody will be asked about. Findings need an owner who can be paged.

**legal_entity** — because model risk aggregates by entity, not by org chart.
The same model used by two entities is two exposures to two supervisors.

**purpose** — the *declared* use. This is load-bearing: a warrant carries a
`declared_use`, and resolution refuses if the use presented is not the use
approved. A model approved for origination decisioning that starts being used
for pricing has changed its risk profile without changing a line of code, and
this is the field that catches it.

**domain** and **model_class** — how the estate is sliced for reporting and how
class-appropriate evidence expectations are chosen.

**origin** — conventionally `internal`, `vendor`, `open_source` or `hybrid`. It
is free text rather than an enum, and it is descriptive: it records what
evidence is obtainable at all. You cannot ask a vendor black box for its
coefficients; you can ask for its validation report and its version notes.

## What registration does not do

Registration creates a **draft** model with no tier and no versions. It is
deliberately cheap, because the alternative — a heavyweight intake form — is
what drives people to route around the platform, and an estate governed by a
platform people avoid is worse than one governed by a spreadsheet they use.

Everything consequential attaches to the version.

## Versions are immutable

A version is created once and never edited. Attempting to create `3.2.1` twice
is refused:

```
version 3.2.1 already exists for maya://model/credit.pd.smallbiz;
versions are immutable
```

This is not fastidiousness. Three things depend on it:

1. **The manifest digest means something.** If a version could be edited, a
   digest recorded last March would prove nothing about what runs today.
2. **A warrant can name a version.** An execution engine that resolved
   `3.2.1` in January and again in June got the same model, and can prove it.
3. **Evidence stays attached.** A validation result is about a specific
   artifact. Let the artifact change underneath and the result becomes a
   statement about nothing.

Need a change? Create `3.2.2`. Versions are cheap; ambiguity is not.

A version can also be refused for a reason that is about the *model* rather than
the version: once a record is attested it is immutable, and a new version is a
change to the model. See
[Approval, attestation and segregation of duties](/help/approval-and-attestation).

## The kernel specification

Every model in MAYA is one shape:

> a parameter object **P**, an input **X**, an output **Y**, and a kernel
> **f : P ⊗ X → Y**

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
    "input_schema":  [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
    "output_schema": [{"name": "pd_12m", "dtype": "float"}]
  },
  "contract": { ... },
  "artifact_digest": "sha256:9f2c1a..."
}
```

`parameter_kind` — how P is inhabited. One of `none`, `calibration_set`,
`estimated_coefficients`, `learned_weights`, `llm_configuration`, `rule_set`,
`elicited_weights`, `opaque`.

`fit_procedure` — how it got that way: `none`, `calibrate`, `estimate`,
`train`, `elicit`, `configure`, `author`.

## Trainability classes T0 to T8

Most model inventories were designed around one implicit assumption: a model is
something that was **trained on data**. Ask that inventory to hold a Black–Scholes
pricer, a credit policy rulebook or a prompt bundle, and it either rejects them
or forces them into fields that make no sense — a "training dataset" for an
analytic formula, a "model performance" metric for a rulebook.

MAYA takes the opposite route. The class is about **how the parameter object is
inhabited**, and training is just one of the ways.

| Class | P is inhabited by | Bank examples |
|---|---|---|
| **T0** | Nothing — P is the unit. Parameters come from theory. | Black–Scholes closed form, SA-CCR, standardised RWA, accrual mechanics |
| **T1** | Calibration to market observables, re-solved each period | Hull–White to swaption vols, SABR surfaces, bootstrapped yield curves |
| **T2** | Statistical estimation from a sample | Logistic PD scorecards, OLS/GLM, ARIMA, Cox survival models |
| **T3** | Numerical optimisation over a loss | Gradient boosting, random forests, neural networks |
| **T4** | Training that continues after deployment | Online learners, bandits, adaptive fraud models |
| **T5** | Configuration of a pre-trained foundation model | Prompt bundles, RAG pipelines, fine-tune-free LLM applications |
| **T6** | Opaque — P exists, you cannot see it | Vendor black boxes, licensed scoring services |
| **T7** | Expert elicitation | Judgemental overlays, expert-weighted scorecards, scenario narratives |
| **T8** | Authorship — a human wrote the parameters | Credit policy rulebooks, deterministic eligibility logic |

### It is derived, never declared

The class is computed, and you cannot send `"trainability_class": "T0"`. There
is no such request field anywhere in the API.

The derivation is decided in this order:

1. **Parameters you cannot see are T6.** `parameter_kind: opaque` means P is
   inaccessible, and inaccessibility dominates everything else.
2. **No parameter object at all is T0.** `parameter_kind: none` — P is the unit,
   and there is nothing to inhabit.
3. **Training that continues is T4.** `fit_procedure: train` together with
   `adaptive: true`.
4. **Otherwise the fit procedure decides:** `calibrate` → T1, `estimate` → T2,
   `train` → T3, `configure` → T5, `elicit` → T7, `author` → T8, and `none` → T0.

Note what that means in practice: it is the **fit procedure** that carries the
class, not the parameter kind's name. An `llm_configuration` whose fit procedure
is `none` derives T0, not T5 — T5 is what `configure` gives you. If the class
that comes back is not the one you expected, the fit procedure is what to look
at.

The reason for deriving at all is behavioural. A declared class is a field
somebody fills in, and the value they fill in is the one that asks least of
them. "It's T0, so there is no training data to produce" is an appealing
sentence, and it is not one an owner should be able to write for a gradient
boosting model. Derivation moves the lie one step back, to `parameter_kind` and
`fit_procedure` — which are checkable against the artifact, and which the
version's schema and contract have to be consistent with.

### What the class actually changes

**What evidence is appropriate.** Asking a T0 analytic pricer for a training set
is a *type error*, not a missing document. MAYA will not ask for one, and will
not record its absence as a gap. Conversely a T3 model with no training data
lineage is a genuine gap and is recorded as one.

**What operations are admissible.** You cannot `fit` a T0 or T6 model — one has
nothing to fit, the other has nothing you can reach. A warrant requesting it is
refused at the grammar level by law **L-W1**.

**What monitoring makes sense.** A T1 calibrated model is re-solved daily, so
"parameter drift" is normal operation rather than an alert; what matters is
calibration error against the instruments. A T3 model's parameters should not
move at all between retrains, so any movement is an incident.

**How much scrutiny it attracts.** The class feeds the complexity half of the
risk tier — see [Risk tiering](/help/risk-tiering).

### The uncomfortable one

**Most of a bank's model estate is not T3.** Counting by artifact, the T0/T1
population — pricing, capital, accrual, curve construction — usually dwarfs the
machine-learned population, and it is systematically under-governed because the
inventory was built for models that have training sets.

That inversion is the argument for classifying this way rather than asking
"is it AI?".

## Schemas are contracts, not documentation

The input and output schemas are checked when an alias moves. Input schemas are
**contravariant** and output schemas **covariant** — the replacement must accept
at least everything the incumbent accepted and promise at least everything it
promised. That is law **L-12**. A version that narrows an input range is not a
drop-in replacement, however much better it scores, and the alias move is
refused with the field that broke it.

## The operating contract

```json
"contract": {
  "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
  "guarantees":  [{"key": "gini", "minimum": 0.42}],
  "on_boundary_violation": "reject"
}
```

Read as: *given* inputs within the assumptions, the model *guarantees* the stated
properties. Outside the assumptions, the guarantee is void — which is a much more
honest statement than a model that silently extrapolates.

`on_boundary_violation` is one of `reject`, `flag` or `clamp`, and defaults to
`reject`. It travels in the warrant with the rest of the contract, so an
execution engine can check the boundary **before** invoking the artifact and
refuse rather than produce a number nobody should rely on.

Contracts also compose. When an alias moves, the replacement's contract must
**refine** the incumbent's — assume no more, guarantee no less. That is law
**L-7**, and it is discharged alongside L-12 on every move.

## Artifacts

MAYA stores the **digest** and the reference; it is not a binary store by
default. `artifact_digest` is the content hash of whatever actually runs —
the ONNX graph, the pickle, the prompt bundle, the JAR, the workbook.

Why a digest rather than the bytes:

- It works for artifacts MAYA must not hold — a vendor binary under licence, a
  container in a registry, a model too large to duplicate.
- It is checkable at execution time. The engine verifies what it loaded against
  what the warrant said, so a swapped artifact is detected rather than assumed
  away.
- It is stable. The same model registered twice from two pipelines produces the
  same digest, which is how duplicate registration gets caught.

`artifact_digest` is optional on **any** version, and a version without one is
read as **descriptor-only**: MAYA holds the governance, somebody else holds the
artifact. That is an honest state and the platform records it as a limitation
rather than pretending to an assurance it does not have — a compiled document
prints *"none recorded — this version is descriptor-only"* rather than leaving
the field blank, and a version whose kernel declares no runtime is issued
warrants with the `descriptor_only` runtime, which law **L-W6** forbids fitting.

It is worth saying what descriptor-only is *not*: it is not a flag somebody
sets, and it is not tied to `origin: vendor`. It is what the register reads off
the absence of a digest and a runtime, which is why it cannot be turned off to
make a dashboard look better.

## Approval

```bash
POST /api/v1/models/{name}/versions/{semver}/approve
```

A version is `draft` until approved. An alias may only point at an approved
version:

```
version 3.2.2 is 'draft', not approved; an alias may only point at an
approved version
```

Moving the alias is the most tightly controlled operation in the platform. Three
things are checked, in this order: the target version is approved; no blocking
finding stands against the model; and the proof obligations L-7 and L-12 hold
against the incumbent. See [Warrants and execution](/help/warrants) for what a
resolved alias then produces.


## Creating a model through the interface

`/models/new` does the two acts that bring a model into the register, and it is
the same pair of endpoints an execution engine uses.

**Register the model** — the urn, the name, the class, the domain, the legal
entity, the owner and what it is for. Nothing about how it runs; that belongs to
a version.

**Upload a version** — the kernel. How the parameter object is inhabited and by
what procedure (the trainability class is *derived* from those two, never
declared), the runtime and its entry, the input and output schemas, and the
artifact's digest and location.

A digest with no location cannot be fetched; a location with no digest cannot be
checked. Supply neither and the version is `descriptor_only`: MAYA holds the
governance and the engine supplies the model. That is a legitimate state — a
vendor product under licence is the ordinary case — and the warrant says it out
loud rather than guessing around it.

Assessment comes before approval, not after. The tier decides how many signatures
a version's approval needs, so a version cannot be approved before its model is
assessed; approving first would be choosing your own control depth.

### The same path, from an execution engine

An engine that has just finished a fit does exactly this:

```
POST /api/v1/models                    # once, when the model first exists
POST /api/v1/models/{name}/versions    # the kernel that will run
POST /api/v1/parameters                # the inhabitant of P it produced
```

The parameters are accepted only against a warrant MAYA issued, and only when
they name the featureset version that produced them. Somebody other than whoever
recorded them approves them before anything runs on them.
