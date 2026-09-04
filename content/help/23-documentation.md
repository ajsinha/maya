---
title: Compiled documentation
slug: documentation
section: Assurance
order: 142
icon: file-earmark-text
summary: Model development documents, validation reports, model cards and Annex IV packs generated from evidence — with citations that resolve, staleness that is computed, and gaps that say what is missing.
audience: Model risk, Model owners
---

# Compiled documentation

The model development document is the artifact a supervisor reads, and in most
banks it is the artifact that has drifted furthest from the model. It is written
once, by hand, for a version that has since been replaced, and nothing connects
the prose to the thing it describes.

Here documents are **compiled** from the register and the evidence graph. Three
properties follow that a written document cannot have.

## 1. Citations resolve

Every section records the evidence entries it rested on. So *"this document is
supported"* stops being a claim about somebody's diligence and becomes a
computation — citation soundness reduces to evaluating the cited set over the
Boolean semiring, which the [evidence engine](/help/evidence-and-provenance)
already does.

```bash
GET /api/v1/documents/{id}
# → "citations_verified": {"cited": 34, "sound": true, "dangling": []}
```

A section resting on nothing is visible as a section resting on nothing.

## 2. Staleness is computed, not remembered

The compiler records how far the evidence chain had got. If anything has since
been recorded about this model — a finding raised, a version created, an alias
moved, an attestation signed — the document no longer describes it:

```json
{"stale": true, "events_since": 3,
 "kinds_since": ["finding_raised", "model_attest", "monitor_breached"],
 "detail": "3 governance event(s) recorded since this document was compiled"}
```

Nobody has to remember to check. The platform can always answer whether a
document still describes the model, because the answer is derived from the same
chain everything else rests on.

Compiling a *different* document does not make this one stale — otherwise every
document would go stale the moment a second one existed.

## 3. Gaps say what is missing

A lens that cannot fill its section says so, in the document, in the place the
content would have been:

> **This section is required and could not be filled.**
>
> Nothing in the register supports a `validation` section for this model yet.
> That is a statement about the model's evidence, not about this document.

A model development document with a blank "Validation" heading and one that says
this look identical to a skim, and are completely different findings.

Coverage is reported alongside:

```json
{"sections": 12, "filled": 8, "missing_required": ["validation", "monitoring"],
 "complete": false}
```

## Sections are lenses, not templates

A template interpolates values it was handed. A **lens** goes and looks — so a
section cannot silently describe a state that no longer holds.

| Lens | Reads |
|---|---|
| Identity and ownership | the model record |
| Classification | the version's parameter kind and fit procedure, and the class derived from them |
| Risk tier | the assessment, with its full derivation |
| Methodology and interfaces | input and output schemas |
| Assumptions and limitations | the operating contract |
| Data and features | the feature contract's pinned namespaces |
| Validation | episodes, tests, thresholds, outcomes, independence |
| Open findings | the register, with blocking flagged |
| Ongoing monitoring | monitors, last observations, outcome windows |
| Approval and attestation | the lifecycle state and amendment history |
| Use and entitlement | warrant grants |
| Provenance | the evidence chain and its verification |

## The four kinds

| Kind | For |
|---|---|
| `model_development_document` | what the model is, how it was built, under what assumptions it may be relied on |
| `validation_report` | what independent challenge was performed and what it found |
| `model_card` | a short, plain description for anyone deciding whether to use it |
| `annex_iv` | the technical documentation an EU AI Act high-risk system must keep |

A template is an ordered list of lenses and which are required — no prose,
because prose in a template is prose that cannot be checked against the model.
The model card is deliberately short: a model card nobody reads because it is
forty pages is not serving the purpose a model card exists for. An Annex IV pack
requires everything the development document requires, and then some.

## Compiling one

From the interface: open a model and press **Compile** on the Documentation card.
The result is rendered with the same markdown pipeline the help system uses, so a
compiled document reads like the rest of the platform rather than like a report
generator's output.

```bash
POST /api/v1/documents?urn=maya://model/…&kind=model_development_document
GET  /api/v1/documents/{id}/markdown     # the exportable form
```

`document:compile` is held by model owners, model risk managers and validators.

## What is not built

There is no PDF renderer, no house template, no signature page and no export
pack. The output is markdown and JSON. Turning that into whatever your firm's
document standard requires is a rendering problem, and deliberately outside the
part MAYA is trying to get right.
