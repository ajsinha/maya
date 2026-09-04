---
title: Documentation
slug: documentation
section: Assurance
order: 120
icon: file-earmark-text
summary: Documents compiled from evidence — citations that resolve, staleness that is computed, gaps that say what is missing — and the register of documents people actually wrote, filed against the version they describe and accepted by somebody else.
audience: Model risk, Model owners, Validators
---

# Documentation

MAYA holds two kinds of document and keeps them apart deliberately.

**Compiled documents** are generated from the register and the evidence graph.
Nobody writes them; a lens goes and looks, every section cites what it rests on,
and staleness is computed rather than remembered.

**Attached documents** are the papers somebody actually wrote — the development
document a quant produced in Word, the validation report the second line signed,
the committee minute, the vendor's manual. MAYA cannot generate those, and
pretending otherwise would be dishonest. What it can do is make them behave like
evidence instead of like files on a share drive.

## Compiled documentation

The model development document is the artifact a supervisor reads, and in most
banks it is the artifact that has drifted furthest from the model. It is written
once, by hand, for a version that has since been replaced, and nothing connects
the prose to the thing it describes.

Compiling it from the register gives three properties a written document cannot
have.

### 1. Citations resolve

Every section records the evidence entries it rested on. So *"this document is
supported"* stops being a claim about somebody's diligence and becomes a
computation — the same question the
[evidence engine](/help/evidence-and-provenance) answers by evaluating a
citation set over the Boolean semiring.

```bash
GET /api/v1/documents/{id}
# → "citations_verified": {"cited": 34, "sound": true, "dangling": []}
```

A section resting on nothing is visible as a section resting on nothing.

### 2. Staleness is computed, not remembered

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

Compiling a *different* document does not make this one stale — compilation
events are filtered out of the count, because otherwise every document would go
stale the moment a second one existed.

### 3. Gaps say what is missing

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

### Sections are lenses, not templates

A template interpolates values it was handed. A **lens** goes and looks — so a
section cannot silently describe a state that no longer holds. There are fifteen:

| Lens | Reads |
|---|---|
| Identity and ownership | the model record |
| Classification | the version's parameter kind and fit procedure, and the class derived from them |
| Risk tier and required controls | the assessment, with its full derivation |
| Methodology and interfaces | input and output schemas |
| Assumptions and limitations | the operating contract |
| Data and features | the feature contract's pinned namespaces |
| Validation | episodes, tests, thresholds, outcomes, independence |
| Open findings | the register, with blocking flagged |
| Ongoing monitoring | monitors, last observations, outcome windows |
| Post-model adjustments | the overlay register, with persistence |
| Approval and attestation | the lifecycle state and amendment history |
| Use and entitlement | warrant grants |
| Supervisory regimes | determinations, and where regimes disagree |
| Documents on file | what was filed, who accepted it, and what was rejected |
| Provenance | the evidence chain and its verification |

The last three are why the compiled and the filed halves of this page belong
together: a compiled document reports on the attached ones, and a required
section that cannot be filled is exactly how a missing development document
becomes visible.

### The four kinds

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

### Compiling one

From the interface: open a model and press **Compile** on the Documentation card.
The result is rendered with the same markdown pipeline the help system uses, so a
compiled document reads like the rest of the platform rather than like a report
generator's output.

```bash
POST /api/v1/documents?urn=maya://model/…&kind=model_development_document
GET  /api/v1/documents/{id}/markdown     # the exportable form
```

`document:compile` is held by model owners, model risk managers and validators.

### What is not built

There is no PDF renderer, no house template, no signature page and no export
pack. The output is markdown and JSON. Turning that into whatever your firm's
document standard requires is a rendering problem, and deliberately outside the
part MAYA is trying to get right.

## Documents on file

### A document is filed against a version, not a model

This is the rule that matters most, and it is the one most document stores get
wrong.

A model development document does not describe *the model*. It describes a
particular version of it — the one whose coefficients it prints, whose
assumptions it states, whose back-test it reports. When that version is replaced,
the document does not automatically describe the replacement.

So the default is version-level. If you do not name a version, the document lands
on the current one. Filing at model level is possible — a board paper covering
the whole portfolio is genuinely about the model rather than a version — but you
have to ask for it with `model_level`, because the ambiguous case should not be
the default one.

A model with no versions is refused outright as `no_version_to_attach_to`, with
the remediation spelled out: create a version first, or say explicitly that this
document is model-level.

```bash
POST /api/v1/attachments        # multipart/form-data
# urn, kind, title, file — plus optional semver, note, supersedes, model_level
```

### Stored by digest, so it cannot be edited underneath you

Every document is stored under the SHA-256 of its bytes. Three properties follow,
and each of them is one this platform relies on elsewhere.

**The same file is stored once.** A board paper covering forty models is one
stored object with forty attachments pointing at it.

**A document cannot be edited in place.** Change a byte and the digest changes,
which makes it a different document. Replacing one is therefore a *supersession*
that somebody declares, not an edit nobody sees — the same reasoning that makes
model versions immutable.

**What was reviewed is what is served.** The digest an approver accepted is the
digest a reader later fetches, and the store re-hashes the bytes on the way out
rather than trusting the path it was given. If they disagree the read fails with
`document_corrupt` and tells you to raise an incident, because at that point the
store has been tampered with or has corrupted and the document should not be
relied on.

### Review is segregated

Whoever attached a document cannot accept it.

A model owner filing their own validation report and marking it accepted is not a
control, and the fact that the document is genuine does not make the process one.
This is checked twice and on purpose:

| Line | Check | Refusal |
|---|---|---|
| Authorisation | Does this role hold `document:review` at all? | `forbidden` |
| The register | Is this the same person who filed it? | `self_review` |

Owners and developers hold `document:attach`. Validators and model risk managers
hold `document:review`. The second check exists anyway, because a role grant is a
policy that can change and segregation of duty is not.

**Rejection requires a reason** — `reason_required` — and a rejected document
stays in the register. The set of documents somebody tried to file and could not
is often the more interesting set, and a register that deletes them makes a
review look cleaner than it was.

### Supersession keeps the chain

When a revised document replaces an earlier one, the new attachment names what it
supersedes. The prior document moves to `superseded`, is linked forward to its
replacement, and drops out of the current set — but stays in the history.

That is what makes *"which MDD was in force in March"* an answerable question
rather than a guess, and it is why superseding the same document twice is refused
as `already_superseded`: the chain would fork.

### What machines can read, and what they cannot

Each attachment records whether its bytes are text the platform can actually
read. Plain text, markdown, CSV, HTML, JSON and XML are indexed. A PDF or a Word
document is stored and served faithfully, but reported as **not
machine-readable**, and asking for its text returns nothing rather than a guess.

This matters for what comes next. Machine validation of documents, and retrieval
over them, both depend on knowing which documents have genuinely been read.
Saying plainly that a scanned PDF has not been read is better than producing a
confident summary of nothing.

### What the register answers

`GET /api/v1/attachments?urn=…` returns the current set plus a summary: how many
are accepted, how many await review, how many were rejected, which kinds are
present, and how many are not machine-readable. Add `history=true` for
everything, superseded and rejected included.

Two baseline gaps read from it:

- **`model_development_document`** — no MDD is on file, so the method is
  undocumented. Material, because a model whose method exists only in its author's
  head is a model the bank cannot maintain.
- **`accepted_documentation`** — documents are on file but none has been accepted
  by a second person. Filing is not review.

### Kinds

| Kind | What it means |
|---|---|
| `model_development_document` | How the model was built, by whom, on what data, with what assumptions |
| `validation_report` | Independent assessment of whether it works as claimed |
| `independent_review` | Review by a party outside both first and second line |
| `vendor_documentation` | What a supplier says about a model the bank did not build |
| `committee_minute` | The record of a governance body's decision |
| `board_paper` | Material put to the board or a board committee |
| `evidence_of_control` | Proof that a stated control operated |
| `correspondence` | Supervisory or internal correspondence bearing on the model |
| `other` | Everything else, named honestly rather than forced into a category |

### What this is not

It is not a document management system. There is no check-out, no collaborative
editing, no rendering pipeline for proprietary formats, and no full-text search.

It is a register: it knows which version a document describes, who filed it, who
accepted it, what was rejected and why, and that the bytes served are the bytes
approved. Everything else is a document management system's job, and MAYA does
not pretend to be one.
