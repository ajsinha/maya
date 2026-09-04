---
title: Competitive analysis
slug: competitive-analysis
section: Positioning
order: 10
icon: graph-up
summary: The market is split in two and neither half is whole. Where the existing categories are strong, where they stop, and what MAYA is betting on.
audience: Everyone
---

# Competitive analysis

## The split

Model management today is served by two categories of product that were built
for different buyers and barely overlap.

**GRC and MRM platforms** — IBM OpenPages, SAS Model Risk Management,
MetricStream, Moody's — were built for the second line. They have the workflow: a
model inventory, validation cycles, findings, attestations, committee routing,
regulatory reporting. What they do not have is any connection to the thing being
governed. The metadata is hand-keyed. Nothing in the platform can tell you
whether the version described in the record is the version running in
production, because nothing in the platform ever touched the artifact.

**MLOps platforms** — MLflow with Unity Catalog, SageMaker, Vertex, Domino,
Databricks — were built for the first line. They have the artifact: experiment
tracking, model registries, aliases, lineage from version to run to notebook to
dataset, serving, monitoring. What they do not have is model risk management. No
validation findings with blocking semantics, no overlay register, no tiering, no
regulatory documents — and, critically, no coverage of anything that is not a
trainable ML asset.

## Where each stops

| Category | Strong | Stops at |
|---|---|---|
| **IBM OpenPages** | Enterprise GRC breadth on one platform; scales to global estates; mature workflow | Metadata is hand-keyed; **no binding to the artifact**; no feature store; no execution |
| **SAS MRM** | Deep MRM domain model; strong validation workflow and reporting | SAS-ecosystem gravity; weak for Python/OSS estates; artifact link by reference only |
| **MetricStream / LogicManager** | GRC workflow, mid-market friendly | A generic risk register with a "model" object type; no technical depth |
| **MLflow / Unity Catalog** | Excellent tracking and registry; aliases as mutable pointers; real lineage | No MRM workflow, no findings, no overlays, no tiering, no vendor / EUC / quant coverage |
| **Databricks** | The strongest single *substrate* — Delta, lineage, monitoring, serving | Platform lock-in; no MRM domain objects; assumes everything is a trainable ML asset |
| **Domino Governance** | Policy templates for the EU AI Act and NIST AI RMF; governance placed in the IDE, which is the right *placement* | Tied to Domino workspaces; not an estate-wide inventory across SAS, C++, vendor and spreadsheet models |
| **Dataiku / DataRobot / H2O** | Broad AutoML with governance modules | Governance covers their own platform's models only |
| **Arize / Fiddler / Arthur / Evidently** | Drift, performance, explainability, fairness, LLM observability | Monitoring only, disconnected from approval state and validation findings |

## The gap nobody covers

Six capabilities recur as gaps across the whole market:

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

## What MAYA bets on

**Bind the record to the artifact.** Every governance claim is a node in an
append-only hash chain, keyed by digest. Tamper detection is structural, and
`/health/ready` fails if the chain does not reconcile.

**One definition of "model" that actually stretches.** Trainability classes
T0–T8 classify by *how the parameter object is inhabited*, not by whether
something was trained. Black–Scholes, a Hull–White calibration, a gradient
boosting model, a prompt bundle, a vendor black box and a credit policy rulebook
are all models, all in one register, with class-appropriate evidence
expectations rather than one-size-fits-none.

**Refusal as the primary control surface.** An alias will not move to a version
whose contract does not refine the incumbent's. A warrant will not resolve for a
model with an open blocking finding. A validation will not conclude "approved"
over a failed test. These are refusals in the code path with reasons and
remediation, not warnings in a dashboard.

**Warrants, not execution.** MAYA issues a signed, expiring, entitlement-bound
document that an execution engine acts on. A captive engine ships as a reference
consumer of the same public contract, so a deployment works out of the box
without that ever becoming the only way to run.

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
claim cites evidence a person then approves — and the third tier, output that can
be neither checked nor grounded, cannot be registered at all. The grounding gate
removes unsupported claims rather than flagging them, nothing becomes evidence
until a person attests it, and a reviewer's falling edit distance is treated as
the control failure it is. Bolt-on LLM features elsewhere ship the capability and
leave the control to the operator.

**Overlays treated as model defects, not management judgement.** Every bank has
post-model adjustments and almost none can say how large they are in aggregate or
which have quietly become permanent. Here each is time-boxed, approved by someone
other than the proposer, and cannot be renewed without a measured magnitude — and
one renewed past its limit raises a finding, because a persistent overlay is an
unversioned model change. No MLOps platform models this at all; the GRC platforms
hold it as a list.

**Documentation compiled, not written.** The model development document is the
artifact a supervisor reads and, in most banks, the one that has drifted furthest
from the model. Here it is generated from the register and the evidence graph:
every section cites what it rests on, staleness is computed from the chain rather
than remembered, and a section that cannot be filled says what is missing instead
of leaving a blank heading.

**One grammar for every model family.** The warrant an execution engine acts on
is the product of four independent vocabularies — how the parameter object is
inhabited, how the kernel is realised, what is asked of it, where its data comes
from — rather than a union of special cases. A Black–Scholes pricer and a
Hull–White calibration are the same document at different coordinates, and the
grammar refuses `fit` on the first because a T0 model has no parameters to fit.
The JSON Schema is generated from the vocabulary and published, so an engine in
any language can check a warrant before acting on it.

**Monitoring that refuses rather than reports.** A breach raises a finding, and a
blocking finding refuses warrant resolution — so degradation stops a model
mechanically instead of colouring a chart somebody has to be looking at. And
delayed labels are treated as the bookkeeping problem they are: a performance
monitor declares its outcome window, and evaluating over an immature cohort is
refused, because a number computed from the outcomes that arrived early is biased
rather than merely noisy.

**Immutability with a declared way out.** An attested record cannot be edited and
cannot take a new version — because a new version *is* a change to the model, and
allowing it is exactly how a record quietly stops describing what runs. The only
route out is an amendment that says what is changing and why, and which must
itself be approved and attested. Nothing is ever deleted: retirement is a state,
and even administrator deletion leaves the whole evidence chain behind.

**Segregation of duties read from the evidence chain.** Most platforms enforce
separation with a second table of who-did-what, which becomes a second source of
truth the moment it disagrees with the record. Here the append-only chain that
proves what happened is the same artifact that decides who may act next: the
person who created a version cannot approve it, promote it, or conclude its
validation — and the refusal cites the evidence entry that disqualifies them.
This binds even for administrators, because break-glass exempts you from the
incompatible-roles check and not from history.

## Where MAYA is weaker today

Stated plainly, because a positioning page that only lists strengths is
marketing rather than analysis.

- **Workflow routing.** MAYA has the lifecycle — gated transitions, a quorum
  attestation, amendments that must themselves be attested — but nobody is *told*
  their signature is outstanding. OpenPages and SAS have two decades of task
  inboxes, reminders, escalation and regulatory report templates.
- **Telemetry ingestion.** Monitors, drift, delayed labels and breach-to-finding
  are built, but scored rows are passed in rather than collected: there is no
  streaming ingestion, no sampling strategy and no scheduler. Arize and Fiddler
  do that part properly today and MAYA does not do it at all.
- **Scale.** The design targets a large estate; it has not been run against one.
- **Ecosystem.** Databricks and Domino arrive with connectors, an installed base
  and a support organisation.

The bet is that the items above are **work**, and the four commitments before
them are **architecture** — that a platform built on evidence and refusal can
add workflow, ecosystem and scale, but a platform built on workflow cannot
retrofit evidence into a record that was never bound to the artifact.
