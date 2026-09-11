---
title: What MAYA is
slug: what-is-maya
section: Getting started
order: 10
icon: compass
summary: One definition every other page derives from, the refusals that make it a control rather than a list, what MAYA deliberately does not do, and a map of the rest of this library.
audience: Everyone
---

# What MAYA is

MAYA is the **register of record for every model a bank runs**, and the machinery
that makes claims about those models checkable instead of asserted.

The name is the Sanskrit *māyā* — appearance, the representation that stands in
for reality and is so easily mistaken for it. Model risk is what happens when an
organisation forgets the difference between the map and the territory.

## One definition, and what falls out of it

Everything on the other fifteen pages derives from one line:

```
f : P ⊗ X → D(Y)
```

A **parameter object** `P`, tensored with an **input** `X`, mapping to a
*distribution* over outputs. Three consequences do most of the work, and each one
dissolves a problem rather than managing it.

**Trainability is derived, never declared.** The useful question is not *is it
AI* but *how is `P` inhabited?* — from theory, from a solver against market
quotes, from a statistical estimator, from a training run, from a configuration,
from a room full of people, or from inside a vendor's binary. The class **T0–T8**
falls out of that answer, so nobody self-reports it, and asking a closed-form
pricer for its training set is a type error rather than an empty field. See
[Registering a model](/help/registering-a-model#trainability-classes-t0-to-t8).

**Parameters are not versions.** A version is the kernel; a parameter set is a
point of `P`. Refitting picks a new point, not a new kernel — which is what lets
a daily recalibration procedure be approved once rather than pretending a
committee meets every morning. See
[Featuresets and fitted parameters](/help/featuresets-and-parameters).

**A model's inputs are half of it.** `X` is a **featureset**: a schema of named
slots, each version binding every slot to an exact feature and an exact pinned
view version. The model is defined over the *slots*, so changing what fills one
does not change its input space — it changes what it was fitted on, which is a
different event with a different control. See
[Features and the two clocks](/help/features-and-two-clocks).

The model page shows that type for the version you are looking at — `P`, `X`,
`D(Y)`, with the trainability class printed beside the two facts it is derived
from, because a class shown next to its derivation is an explanation and a class
shown alone is a label.

## Why a register needs to refuse things

Most model estates are governed by **assertion**: a document says a model was
validated, a field says who owns it, a ticket says a finding was closed. Nothing
connects the assertion to the artifact, so the two drift apart quietly and are
reconciled only when something goes wrong.

MAYA binds every governance claim to the artifact it rests on, by digest, in an
append-only hash chain — and then puts the chain in the decision path. The
interesting behaviour is what it will **not** do:

| It refuses | Because |
|---|---|
| A warrant for a model with an open blocking finding | `423 blocked` — a validation finding should stop the model, not generate an email |
| An alias move to a version that narrows an input range | The replacement must accept at least what the incumbent accepted (**L-12**), however much better it scores |
| A `fit` warrant for a model whose `parameter_kind` is `none` | `nothing_to_fit` — `P` is the terminal object, so there is no point of `P` to move to |
| A version approved by whoever created it | `segregation_of_duties`, decided by reading the evidence chain rather than a second table |
| A training assembly with either clock unbounded | Without both, leakage cannot be excluded, and a warning would be ignored |
| A new version on an attested model | A new version *is* a change to the model; open an amendment |

Every refusal names what was violated and what to do about it. If you are
learning the platform, being refused is the fastest way to see what it is for —
[Quickstart](/help/quickstart) ends by making it happen on purpose.

## Two more properties worth knowing up front

**Versions are immutable.** A version is created once and never edited, which is
what makes a manifest digest worth computing and what lets a warrant name
`3.2.1` and still mean the same thing two years later.

**Conditions are computed, not remembered.** The tier, staleness, expiry, cohort
maturity, outstanding work, compliance debt, the estate summary, the documents,
the board pack: all derived from the register when asked. There is no second
table to fall out of step with the first.

## What MAYA does not do

This matters as much as the list above.

**It does not execute models.** It issues **warrants** — signed, expiring,
entitlement-bound JSON documents an execution engine acts on. The separation is
deliberate: a governance platform that is also the runtime is a single point of
failure for the trading day, and every outage becomes a governance outage. A
captive engine ships as a reference consumer of the same public contract an
external engine uses, so a fresh deployment works without that ever becoming the
only way to run.

**It does not decide your policy.** Thresholds, tier bands, remediation windows
and approval routes are configuration. The platform enforces what you declared;
it does not tell you what to declare.

**It does not author models — with one stated exception.** No ONNX editor, no
PMML editor, and there will not be one: those formats serialize a *fitted* map,
and hand-authoring one would put an artifact in the register that had never been
trained or validated and was indistinguishable from one that had. The exception
is a **rule set**, whose provenance *is* its authorship — so MAYA edits a
parameter object it already held, and publishing is the ordinary parameter-set
record with the ordinary second person. See [Rule sets](/help/rule-sets).

**It does not observe what it cannot see, and does not pretend to.** It does not
run your models, so it cannot measure what one costs or what it computed; it
does not hold your general ledger, so it cannot check an exposure; it does not
crawl your drives, so it cannot find an unregistered spreadsheet. In every one
of those places it takes an **attested** fact from a named source, marks it as
attested, and reports how much of the estate rests on somebody's word — because
a register that could not tell a claim from a measurement would present both
with the same confidence. See [The register's edges](/help/administering-maya)
and `/admin/perimeter`.

**It is not legal or regulatory advice.** It implements controls that map onto
published supervisory expectations. The three supervisory encodings that ship are
illustrative, not complete. Whether your implementation satisfies your supervisor
is a judgement your second line and your regulator make.

## Where things are in the interface

| Page | What it is for |
|---|---|
| `/dashboard` | The estate, the worklist, and what is overdue |
| `/model/{name}` | One model as its type, its versions, aliases, findings and evidence |
| `/models/new` | Register a model and upload its first version |
| `/features` · `/featuresets` | Definitions, view versions, pins and what has been restated |
| `/rules/{model}/{semver}` | The rule set of one T8 version: the rules in order, what they say in English, and what the checks found |
| `/dossier/{name}` | Every document about a model, its versions, its parameter sets and the featureset versions they were fitted from — with the gaps named |
| `/board-pack` | Risk appetite against the estate, for a committee |
| `/policies` | What is in force on each gate |
| `/telemetry` · `/notifications` | Delivered predictions and outcomes; digests of what needs doing |
| `/admin/perimeter` | **What this platform is relying on somebody else for** — a firm's own extension, another system's export, somebody else's scanner, a pack that left the building — and how narrow each answer is |

## The rest of this library

| If you want to | Read |
|---|---|
| Run the whole governed path, and watch it fail closed | [Quickstart](/help/quickstart) |
| Know what counts as a model, and what a version declares | [Registering a model](/help/registering-a-model) |
| Know how much scrutiny a model gets, and which supervisor asks | [Risk tiering and supervisory regimes](/help/risk-tiering) |
| Know who may act, and how a record comes into force | [Approval, attestation and segregation of duties](/help/approval-and-attestation) |
| Build training data that is not quietly wrong | [Features and the two clocks](/help/features-and-two-clocks) |
| Name a set of features and store what a fit produced | [Featuresets and fitted parameters](/help/featuresets-and-parameters) |
| Author, check and run the rules a policy is made of | [Rule sets](/help/rule-sets) |
| Run a model, or write an engine that does | [Warrants and execution](/help/warrants) |
| Record independent challenge and what it found | [Validation and findings](/help/validation) |
| Watch a live model, and control the adjustments on top of it | [Monitoring and post-model adjustments](/help/monitoring) |
| Verify the record itself, or govern the platform's own AI | [Evidence, provenance and machine assistance](/help/evidence-and-provenance) |
| Produce documents a supervisor will read | [Documentation](/help/documentation) |
| Bring an existing estate in, and see what needs doing | [The estate and what needs doing](/help/estate-and-worklist) |
| Set a risk appetite and report the estate to a committee | [Risk appetite and the board pack](/help/portfolio-reporting) |
| Look up an endpoint, a refusal or a configuration key | [The API, refusals and configuration](/help/api-reference) |
| Look up a term | [Glossary](/help/glossary) |

Worked walkthroughs with real calls are in the [tutorials](/tutorials/end-to-end).
Seven cover the platform; [seven are one per kind of
model](/tutorials/defining-a-model), each complete from registration to
monitoring, so a pricing library and a neural network can be seen getting the
same treatment. The last of the seven —
[governing what you cannot see](/tutorials/governing-what-you-cannot-see) — is
about the other half of a real estate: a model a vendor built, a challenger
running in shadow, a model that changes itself, and data you are only allowed to
keep for so long.
