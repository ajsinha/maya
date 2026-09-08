---
title: Competitive analysis
slug: competitive-analysis
section: Positioning
order: 10
icon: graph-up
summary: The market is split in two and neither half is whole. Where the existing categories are genuinely strong, where they stop, the one claim about the data layer that is now testable rather than rhetorical — and an honest account of where MAYA is behind.
audience: Everyone
---

# Competitive analysis

## The split

Model management today is served by categories of product built for different
buyers, which barely overlap.

**GRC and MRM platforms** — IBM OpenPages, SAS Model Risk Management,
MetricStream, Moody's — were built for the second line. They have the workflow:
a model inventory, validation cycles, findings, attestations, committee routing,
regulatory reporting. What they do not have is any connection to the thing being
governed. The metadata is hand-keyed. Nothing in the platform can tell you
whether the version described in the record is the version running in
production, because nothing in the platform ever touched the artifact.

**MLOps platforms** — MLflow with Unity Catalog, SageMaker, Vertex, Domino,
Databricks — were built for the first line. They have the artifact: experiment
tracking, model registries, aliases, lineage from version to run to notebook to
dataset, serving, monitoring. What they do not have is model risk management: no
validation findings with blocking semantics, no overlay register, no tiering, no
regulatory documents — and, critically, no coverage of anything that is not a
trainable ML asset.

**Feature stores and semantic layers** are the third population, and the one
this platform has the most specific argument with. That argument is in its own
section below.

## Where each stops

| Category | Genuinely strong at | Stops at |
|---|---|---|
| **IBM OpenPages** | Enterprise GRC breadth on one platform; scales to global estates; two decades of workflow, escalation and regulatory report templates | Metadata is hand-keyed; **no binding to the artifact**; no feature store; no execution |
| **SAS MRM** | Deep MRM domain model; strong validation workflow and reporting | SAS-ecosystem gravity; weak for Python/OSS estates; artifact link by reference only |
| **MetricStream / LogicManager** | GRC workflow, mid-market friendly | A generic risk register with a "model" object type; no technical depth |
| **Credo AI / Holistic AI** | Regulatory mapping and structured AI assessments; close to the EU AI Act as written | Scoped to AI; the artifact is described rather than bound; no feature or execution layer |
| **MLflow / Unity Catalog** | Excellent tracking and registry; aliases as mutable pointers; real lineage | No MRM workflow, no findings, no overlays, no tiering, no vendor / EUC / quant coverage |
| **Databricks** | The strongest single *substrate* — Delta, lineage, monitoring, serving | Platform lock-in; no MRM domain objects; assumes everything is a trainable ML asset |
| **Domino Governance** | Policy templates for the EU AI Act and NIST AI RMF; governance placed in the IDE, which is the right *placement* | Tied to Domino workspaces; not an estate-wide inventory across SAS, C++, vendor and spreadsheet models |
| **Dataiku / DataRobot / H2O** | Broad AutoML with governance modules | Governance covers their own platform's models only |
| **Arize / Fiddler / Arthur / Evidently** | Drift, performance, explainability, fairness, LLM observability — done properly, at scale | Monitoring only, disconnected from approval state and validation findings |
| **Hopsworks** | **Genuine prior art for versioned feature groups and feature views**, with point-in-time joins and a real offline/online split | Not a governance system: no findings, no tiering, no approvals, no non-ML estate |
| **Tecton** | The strongest feature engineering story; on-demand transforms; offline/online consistency | Composition is Python function composition, so it is untyped and un-analysable |

## The gap nobody covers

Six capabilities recur as gaps across the whole market.

1. **Evidence bound to the artifact.** Everywhere else, "validated" is a field
   somebody set. It should be a claim you can verify against a digest.
2. **Non-ML models as first-class citizens.** Pricing libraries, capital
   engines, rulebooks, spreadsheets and vendor black boxes are models by every
   supervisory definition, and they are usually the *majority* of the estate by
   count. MLOps tools cannot hold them; GRC tools hold only a description of
   them.
3. **Controls that refuse.** A finding that does not stop a promotion is a log
   entry. A tier that does not change what is required is a label.
4. **Point-in-time correctness as an enforced property.** Feature stores offer
   PIT joins; almost none *refuse* an assembly that cannot be shown correct.
5. **An execution contract, not an execution monopoly.** Governance platforms
   that also run models become a single point of failure for the trading day.
   Registries that do not touch execution cannot enforce anything at the point
   of use.
6. **Generative and agentic systems in the same register.** Bolt-on LLM
   observability sits beside the model inventory rather than inside it, so the
   estate has two populations and two sets of controls.

## The one claim about the data layer that is now testable

This is the sharpest position on the page, and it is worth stating precisely
because it is easy to overclaim.

> **No feature store has an algebra. The semantic layers have an algebra and no
> time. MAYA has both.**

**No feature store has an algebra.** Feast is deliberately un-opinionated.
Tecton's composition is Python function composition, so it is untyped and
un-analysable — you cannot ask whether two feature views are substitutable
without running them. Databricks leans on Delta time travel at *table*
granularity, which is a different question from *what was knowable at the label
date*. **Hopsworks is the honourable exception on versioning** and deserves the
credit: feature groups and feature views are versioned objects with point-in-time
joins, and that is genuine prior art for what MAYA calls a featureset version.
What none of them has is an *order* — a relation you can compute with, that
answers substitutability, admissibility and refinement as one question.

**And every one of them connects where MAYA copies.** A feature store that binds
a view to a warehouse table serves whatever that table holds at read time. That
is the right trade for a serving system and the wrong one for a governance
record: a table overwritten since March cannot say what was knowable in March,
and the read does not fail — it returns the restated number and says nothing.
MAYA *pulls*. A SQL query, a file or an object store is read once,
bitemporalised, and written into storage MAYA controls as an immutable versioned
snapshot; models read the snapshot. It costs a copy, and it is the only way the
point-in-time guarantee survives contact with somebody else's warehouse.

**The semantic layers have an algebra and no time.** dbt MetricFlow, Cube,
Malloy and LookML have real composition semantics, and MetricFlow's measure /
dimension / entity split is the right decomposition. None of them is bitemporal,
so none can answer *as we knew it* — which is the only form of the question a
training set or a restated regulatory figure actually asks.

MAYA has both, and it is a position rather than a slogan because each half is
asserted by a test that fails the build:

- **The order.** Schemas form a lattice (`L-20`). `A ⊑ B` means *A can stand in
  for B*; meet and join exist on every finite fragment. Alias substitutability,
  fit-warrant admissibility, parent refinement and "what must a featureset
  provide to serve both these models" are the **same** comparison, where they
  used to be four implementations that would eventually disagree — and the
  direction of disagreement is predictable, toward permitting more, because that
  is the direction in which nobody files a bug.
- **The time.** The point-in-time read is an operator with four asserted
  properties, the fourth being the guarantee (`L-10`): every read at or after
  the label gives the same answer, however many restatements arrived in between.
- **The composition.** An `input_to` edge holds only if what the source produces
  can stand in for what the target reads (`L-21`). The dependency graph is
  typed, so a blast radius follows edges that were checked rather than drawn.

Adjacent, and worth being equally precise about: the **provenance polynomial**.
Evidence is evaluated once in `ℕ[X]` and every other answer — sufficiency,
minimal support, corroboration, trust, cost — is a pushforward of it (`L-9`),
checked over two hundred random derivation DAGs. That is borrowed work (Green,
Karvounarakis & Tannen, PODS 2007), correctly attributed, and the contribution
is applying it to a governance chain and to derived features rather than
inventing it.

## What MAYA bets on

**The record is bound to the artifact.** Every governance claim is a node in an
append-only hash chain whose content hash covers the payload *and* its
authorship — because segregation of duties is read from that authorship, and a
single `UPDATE` reassigning it would otherwise switch the control off while
verification reported the chain intact. `/health/ready` fails if the chain does
not reconcile, and nothing else takes readiness down.

**One definition of "model" that actually stretches.** Trainability classes
T0–T8 classify by *how the parameter object is inhabited*, not by whether
something was trained. Black–Scholes, a Hull–White calibration, a gradient
boosting model, a prompt bundle, a vendor black box and a credit policy rulebook
are all models, all in one register, with class-appropriate evidence
expectations rather than one-size-fits-none. Asking a closed-form pricer for its
training set is a *type error* rather than an empty field.

**Refusal as the primary control surface.** An alias will not move to a version
whose contract does not refine the incumbent's. A warrant will not resolve for a
model with an open blocking finding. A validation will not conclude "approved"
over a failed test. A performance monitor will not evaluate an immature cohort.
These are refusals in the code path with a reason and a remediation, not
warnings in a dashboard.

**Warrants, not execution.** MAYA issues a signed, expiring, entitlement-bound
document that an execution engine acts on, and the warrant is the product of
four independent vocabularies rather than a union of special cases. A
Black–Scholes pricer and a Hull–White calibration are the same document at
different coordinates, and the grammar refuses `fit` on the first because a T0
model has no parameters to fit. The JSON Schema is generated from the vocabulary
and published, so an engine in any language can check a warrant before acting on
it. A captive engine ships as a reference consumer of that same public contract
— it verifies the artifact's digest against the warrant before loading, runs
ONNX, evaluates the regression and scorecard subset of PMML natively without a
JVM, and prices a small set of instruments through QuantLib with the evaluation
date taken from the warrant rather than from the clock. Everything outside that
subset is refused **by name**, because a partial implementation that silently
mis-evaluates a tree ensemble is worse than one that says what it does.

**Documentation compiled, filed against what it is about, and walkable.** The
model development document is generated from the register: every section cites
what it rests on, staleness is computed from the chain rather than remembered,
and a section that cannot be filled says what is missing instead of leaving a
blank heading. Beyond that, two things no competitor has:

- A document is filed against a **pinned subject** — `featureset_version`, never
  `featureset` — so the two documents that were previously unfilable anywhere
  (the note about one calibration, the data dictionary for one filled schema)
  now have a place that will not move underneath them.
- A **training record** is compiled per parameter set. A model recalibrated
  every morning produces two hundred and fifty governed acts a year, each with a
  warrant behind it and a signature on it, and in every other system none of
  them has a record anybody can read.

The **dossier** walks that graph from a model down and names every node with
nothing filed as a gap, because a page that silently omits what it could not
find reads as complete. An **export pack** carries the same graph, digested
member by member, to somebody who will never be given a login.

**A featureset is an object, not a list inside a model.** Every platform in the
survey except Hopsworks binds features to a model and stops there — the
selection has no name, so it cannot be shared, compared, or reasoned about. Here
a featureset declares a *schema* of named slots, and a version fills each with a
feature and the exact feature view version supplying it. Two versions may draw
on entirely different features and still be the same input space, because the
kernel reads the slot; and a version that cannot fill the schema is refused,
which is the difference between a data refresh and an unversioned model change
nobody noticed.

**The parameters are in the register.** MLOps platforms store the artifact and
GRC platforms store a document about it; neither holds the coefficients as a
governed object. Fitting does not change the kernel — it inhabits `P` — so a fit
produces a *parameter set*, accepted only against a warrant MAYA issued, naming
the featureset version that produced it, and approved by somebody other than
whoever recorded it. A retrain is a governed event with lineage back to the rows
that were true and known at a stated moment, rather than a file that changed on
a Tuesday.

**Overlays treated as model defects, not management judgement.** Every bank has
post-model adjustments and almost none can say how large they are in aggregate
or which have quietly become permanent. Here each is time-boxed, approved by
someone other than the proposer, and cannot be renewed — by anyone but the owner
— without a measured magnitude for the period being renewed. One renewed past
its limit raises a finding, because a persistent overlay is an unversioned model
change. No MLOps platform models this at all; the GRC platforms hold it as a
list.

**Monitoring that refuses rather than reports.** A breach raises a finding, and
a blocking finding refuses warrant resolution — so degradation stops a model
mechanically instead of colouring a chart somebody has to be looking at. And
delayed labels are treated as the bookkeeping problem they are: a performance
monitor must declare its outcome window, maturity is decided per row rather than
per batch, and a wholly immature cohort is refused with the date it becomes
measurable, because a number computed from the outcomes that arrived early is
biased rather than merely noisy.

**Several supervisors at once, without flattening them.** Each regime is encoded
as an institution with its own vocabulary, and its translation into the core is
checked against the satisfaction condition — truth invariant under change of
notation — before it can be activated. A regime that obliges and forbids the
same term cannot be activated at all. Regimes that disagree about a model are
reported as disagreeing, because in scope for one and out for another is a fact
somebody needs. Adding a supervisor is a signature, some sentences and a
translation; the schema, the API and the interface do not move. Elsewhere, a new
regulator is a new column set and a migration.

**Segregation of duties read from the evidence chain.** Most platforms enforce
separation with a second table of who-did-what, which becomes a second source of
truth the moment it disagrees with the record. Here the append-only chain that
proves what happened is the same artifact that decides who may act next: the
person who created a version cannot approve it, promote it, or conclude its
validation — and the refusal cites the evidence entry that disqualifies them.
This binds even for administrators, because break-glass exempts you from the
incompatible-roles check and not from history.

**A cold start that does not kill the programme.** An existing estate imports
into a `baselined` state carrying explicit, dated debt for what it lacks —
computed from the register rather than declared, so nobody under-declares — and
that debt closes by itself as the evidence arrives. Debt is kept apart from
breach on every view, because a Tier 1 model that arrived last week and one that
missed its validation are different situations. Every competitor's answer to day
one is a migration project; this is a first-class capability with its own
burn-down.

**AI admitted only where it can be checked.** The platform's own machine
assistance is registrable at two tiers — an oracle checks the output, or every
claim cites evidence a person then approves — and the third tier, output that
can be neither checked nor grounded, cannot be registered at all. The grounding
gate *removes* unsupported claims rather than flagging them; the evidence a
draft may cite is fixed from the register before the model is asked, so a
citation it invents has nowhere to land; nothing becomes evidence until somebody
other than the requester attests it; and a reviewer's falling edit distance is
treated as the control failure it is. Bolt-on LLM features elsewhere ship the
capability and leave the control to the operator.

**Immutability with a declared way out.** An attested record cannot be edited
and cannot take a new version — because a new version *is* a change to the
model, and allowing it is exactly how a record quietly stops describing what
runs. The only route out is an amendment that says what is changing and why, and
which must itself be approved and attested. Nothing is ever deleted: retirement
is a state, and even administrator deletion leaves the whole evidence chain
behind.

## Where MAYA is weaker today

Stated plainly, because a positioning page that only lists strengths is
marketing rather than analysis. Two items on this list a year ago — notification
and telemetry — have since been built, so what follows is the current position
and not a comfortable one.

- **Monitoring depth.** Ingestion is now real: two bitemporal streams,
  idempotent on the batch digest, joined at read time, with silence detection
  and a cohort endpoint. What is *not* there is everything Arize and Fiddler are
  actually good at — no streaming collector, no sampling strategy, no automatic
  reference-window management, no explainability, no fairness suite, no
  embedding or LLM-output observability, and exactly **one** drift statistic.
  Something outside still has to post the batches and call `evaluate`.
- **Workflow and reporting.** Work is derived rather than assigned, a digest
  reaches each person over log, webhook or email, and escalation happens by
  role. But escalation *by role* is a deliberate simplification — MAYA does not
  model an organisation chart — and there is no committee routing, no workflow
  designer, no ticketing integration beyond a generic webhook, and no library of
  regulatory report templates. OpenPages and SAS have two decades of exactly
  that, and it is the part a large programme buys.
- **Six of the twenty-one foundational laws do not run.** They are named, with
  the reason, rather than quietly counted among the ones that do. The two that
  matter commercially: there is no aggregate risk figure (`L-14`), which is
  argued for rather than apologised for, and there is no online feature serving,
  so contract–serving agreement (`L-17`) is half built — the platform computes
  what serving must read and cannot check what it did read.
- **Document handling stops at markdown.** No PDF renderer, no house template,
  no signature page, no full-text search over filed documents. Turning compiled
  output into a firm's document standard is somebody else's rendering problem
  today.
- **Scale.** The design targets a large estate; it has been exercised at
  thousands of evidence nodes, not at a bank's whole inventory over years. The
  one performance bug found so far was found by running it bigger, which is
  suggestive in both directions.
- **Ecosystem.** Databricks and Domino arrive with connectors, an installed base
  and a support organisation. This is a single-author project with a Python SDK,
  a Java contract written down and not built, and no partner network.

The bet is that everything on that list is **work**, and that the commitments
above it are **architecture** — that a platform built on evidence, refusal and a
stated algebra can add workflow, connectors, monitoring depth and scale, but a
platform built on workflow cannot retrofit evidence into a record that was never
bound to the artifact, and a feature store cannot retrofit an order onto
composition that was always Python.
