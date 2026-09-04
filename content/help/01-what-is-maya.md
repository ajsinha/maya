---
title: What MAYA is
slug: what-is-maya
section: Getting started
order: 10
icon: compass
summary: The problem MAYA exists to solve, what it does about it, what it deliberately does not do, and a map of the rest of this library.
audience: Everyone
---

# What MAYA is

MAYA is a **register of record for every model a bank runs**, together with the
machinery that makes claims about those models checkable rather than asserted.

The name is the Sanskrit *māyā* — appearance; the representation that stands in
for reality and is so easily mistaken for it. That is exactly what a model is,
and model risk is what happens when an organisation forgets the difference
between the map and the territory.

## The problem

Ask a large bank how many models it runs and you will get a number. Ask how that
number was arrived at and the answer is usually an inventory spreadsheet
maintained by people who were not told when a model changed.

The gap is structural, not clerical. Most model estates are governed by
**assertion**: a document says a model was validated, a field says who owns it, a
ticket says a finding was closed. Nothing connects the assertion to the artifact
it describes, so the two drift apart quietly and are only reconciled when
something goes wrong or an examiner asks.

Three consequences follow, and every bank has met all three:

- **The inventory is incomplete.** Spreadsheets, vendor black boxes, pricing
  libraries and — increasingly — prompt bundles are models by any supervisory
  definition, but they do not look like the "models" the inventory was designed
  for, so they are not in it.
- **Documentation describes a version nobody runs.** The model development
  document was written for v2.1. Production serves v2.4. Both statements are
  true and neither is discoverable from the other.
- **Controls are advisory.** A finding is raised, recorded, and the model is
  promoted anyway, because the register that holds the finding has no
  relationship to the pipeline that does the promoting.

## What MAYA does about it

**Evidence, not assertion.** Every governance claim is bound to the artifact it
is about, by digest, in an append-only hash chain. "This version was validated"
is a statement you can verify, not one you have to trust.

**One register, all model kinds.** Statistical, machine-learned, generative,
calibrated, vendor-supplied, expert-judgment, rule-based and end-user-computed
models sit in one population. They differ in what evidence is appropriate, not
in whether they are governed. See
[Registering a model](/help/registering-a-model) for how one definition stretches
that far without becoming vacuous.

**Controls that actually refuse.** An alias cannot be moved to a version whose
contract does not refine the incumbent's. A warrant cannot be resolved for a
model with an open blocking finding. These are not warnings in a dashboard;
they are refusals in the code path, and the refusal says which clause failed.

**Versions are immutable.** A version is created once and never edited, which is
what makes a manifest digest worth computing and what lets a warrant name a
version and still mean something two years later.

**Conditions are computed, not remembered.** Staleness, expiry, cohort maturity,
outstanding work and compliance debt are derived from the register when asked.
There is no second table to fall out of step with the first.

## What MAYA does not do

This matters as much as the list above.

**MAYA does not execute models.** It manages them and issues **warrants** — signed,
expiring, entitlement-bound JSON documents that an execution engine acts on. The
separation is deliberate: a governance platform that is also the runtime becomes
a single point of failure for the trading day, and every outage becomes a
governance outage. A captive engine ships with MAYA as a reference consumer of
the same public warrant contract an external engine uses, so a deployment works
out of the box without that ever becoming the only way to run.

**MAYA does not decide your policy.** Thresholds, tier bands, remediation windows
and approval routes are configuration. The platform enforces what you declared;
it does not tell you what to declare.

**MAYA is not legal or regulatory advice.** It implements controls that map onto
published supervisory expectations. Whether your implementation satisfies your
supervisor is a judgement your second line and your regulator make, not one this
software makes for you.

## The rest of this library

| If you want to | Read |
|---|---|
| Run the whole governed path in five minutes | [Quickstart](/help/quickstart) |
| Know what counts as a model, and how one is recorded | [Registering a model](/help/registering-a-model) |
| Understand how much scrutiny a model gets, and who requires it | [Risk tiering and supervisory regimes](/help/risk-tiering) |
| Know who may act, and how a record comes into force | [Approval, attestation and segregation of duties](/help/approval-and-attestation) |
| Build training data that is not quietly wrong | [Features and the two clocks](/help/features-and-two-clocks) |
| Name a set of features and store what a fit produced | [Featuresets and fitted parameters](/help/featuresets-and-parameters) |
| Run a model, or write an engine that does | [Warrants and execution](/help/warrants) |
| Record independent challenge and what it found | [Validation and findings](/help/validation) |
| Watch a live model, and control the adjustments on top of it | [Monitoring and post-model adjustments](/help/monitoring) |
| Verify the record itself, or govern the platform's own AI | [Evidence, provenance and machine assistance](/help/evidence-and-provenance) |
| Produce documents a supervisor will read | [Documentation](/help/documentation) |
| Bring an existing estate in, and see what needs doing | [The estate and what needs doing](/help/estate-and-worklist) |
| Look up an endpoint, a refusal or a configuration key | [The API, refusals and configuration](/help/api-reference) |
| Look up a term | [Glossary](/help/glossary) |

Worked walkthroughs, with real calls, are in the
[tutorials](/tutorials/end-to-end).
