---
title: Documentation
slug: documentation
section: Assurance
order: 120
icon: file-earmark-text
summary: What a document is about, and whether it still describes it. The six pinned subjects, the fifteen lenses that compile four documents from the register, the training record a daily calibration never had, the dossier that walks the whole graph naming its gaps, the export pack that carries it to somebody with no login, and a review that comments on a compiled document rather than editing one.
audience: Model risk, Model owners, Validators
---

# Documentation

Two questions decide everything on this page.

**What is this document *about*?** Get that wrong and nobody can find it from the
thing it describes, or it describes something that has since moved.

**Does it still describe it?** A document that was true when written and is
false now is worse than a missing one, because it is read.

Everything below is one of those two answers. The first is the subject
vocabulary and the graph it builds; the second is compilation, staleness and
named gaps.

## What a document is about

Documentation does not arrive all at once about one thing. It arrives at **five
moments about five objects**:

| When | About | Example |
|---|---|---|
| before anything runs | the **model** | the methodology paper, the literature the approach comes from |
| a version is created | the **model version** | the specification of that kernel |
| a fit warrant executes | the **parameter set** | the convergence study, the note explaining one morning |
| a featureset version is filled | the **featureset version** | the data dictionary, the source-system agreement |
| validation concludes | the **validation** | the independent recode, the reviewer's working |

Everything used to be filed against a model or a version, so the third and
fourth were **unfilable** — and they are the two that matter most in practice. A
calibrated model produces a parameter set every morning. A featureset's data
dictionary is read by every model fitted from it, so filing it against one of
them makes it invisible to the rest.

Six subjects, published at `GET /api/v1/document-subjects`:

| Subject | Pinned | What belongs here |
|---|---|---|
| `model` | no | methodology, literature, board papers — things true of every version |
| `model_version` | **yes** | one immutable kernel: its specification, its validation report |
| `parameter_set` | **yes** | one point of `P`: the convergence study, the note explaining the morning a calibration went wrong |
| `featureset_version` | **yes** | one filled schema: the data dictionary, the source-system agreement |
| `feature` | no | one governed signal: its business definition, the argument for how it is computed |
| `validation` | no | one episode: the independent recode, the challenger comparison |

### A subject is pinned, and `featureset` is not a subject

`featureset_version`, never `featureset`. A document filed against the *set*
would describe something that has since moved — finding C-2 in documentation's
clothing — so `featureset` is deliberately **absent from the vocabulary** rather
than discouraged in a comment. Ask for it and the filing is refused:

```json
{"error": "unknown_subject",
 "detail": "'featureset' is not something a document can be about",
 "remediation": "use one of model, model_version, parameter_set,
                 featureset_version, feature, validation; a subject the platform
                 cannot resolve is a document nobody will find from the thing it
                 describes"}
```

The default is unchanged and deliberately conservative: a caller that names no
subject files against the **current version**, or against the model if it passes
`model_level`. A model with no versions at all is refused as
`no_version_to_attach_to` rather than being quietly filed at model level.

## Compiled, or written

MAYA holds two kinds of document and keeps them apart on purpose.

| | Compiled | Attached |
|---|---|---|
| Who wrote it | nobody — a lens read the register | a person, in Word |
| Can it drift | no; staleness is computed from the chain | yes; that is why supersession exists |
| What it is for | the reproducible half a supervisor reads | the argument, the judgement, the vendor's manual |
| Kinds | four, plus the training record | nine |

MAYA cannot generate the second kind, and pretending otherwise would be
dishonest. What it can do is make those documents behave like evidence rather
than like files on a share drive.

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

Nobody has to remember to check. Compiling a *different* document does not make
this one stale — compilation events are filtered out of the count, because
otherwise every document would go stale the moment a second one existed.

### 3. Gaps say what is missing

A lens that cannot fill its section says so, in the document, in the place the
content would have been:

> **This section is required and could not be filled.**
>
> Nothing in the register supports a `validation` section for this model yet.
> That is a statement about the model's evidence, not about this document.

A model development document with a blank "Validation" heading and one that says
this look identical to a skim, and are completely different findings.

```json
{"sections": 12, "filled": 8, "missing_required": ["validation", "monitoring"],
 "complete": false}
```

### Sections are lenses, not templates

A template interpolates values it was handed. A **lens** goes and looks — so a
section cannot silently describe a state that no longer holds. A lens returns
prose and the evidence it cited, or `None`, which is how a gap gets named rather
than guessed. There are fifteen:

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
together: a compiled document reports on the attached ones, so a missing
development document becomes visible as a section that could not be filled.

### The four kinds compiled from a model

| Kind | For | Lenses |
|---|---|---|
| `model_development_document` | what the model is, how it was built, under what assumptions it may be relied on | all fifteen, all required |
| `annex_iv` | the technical documentation an EU AI Act high-risk system must keep | the same fifteen |
| `validation_report` | what independent challenge was performed and what it found | eleven, five of them optional |
| `model_card` | a short, plain description for anyone deciding whether to use it | seven, four of them optional |

A template is an ordered list of lenses and which are required — no prose,
because prose in a template is prose that cannot be checked against the model.
The model card is deliberately short: one nobody reads because it is forty pages
is not serving the purpose a model card exists for.

```bash
POST /api/v1/documents?urn=maya://model/…&kind=model_development_document
GET  /api/v1/documents/{id}/markdown     # the exportable form
```

`document:compile` is held by model owners, model risk managers and validators.
From the interface: open a model and press **Compile** on the Documentation
card. The result renders through the same markdown pipeline as this help system,
so it reads like the rest of the platform rather than like a report generator's
output.

## The training record — the fifth kind

Four documents are compiled from a model URN. The **training record** is
compiled from the id of one fit, which is why it sits outside that list.

```bash
GET  /api/v1/training-records/{parameter_set_id}/preview   # what it would say
POST /api/v1/training-records/{parameter_set_id}           # author it
```

Six sections, all required, all read from what the register already holds:

| Section | Reads |
|---|---|
| **What this is** | the parameter set, its provenance and its state |
| **Under what authority** | the warrant the fit ran under |
| **What it read** | the featureset version, the window, the `as_of`, the snapshot |
| **What it produced** | the values inline, or their URI and digest |
| **What the fit reported** | the diagnostics the estimator returned |
| **Who accepted it** | the review, once there is one |

Compiled rather than written, and that is the whole point. A model recalibrated
every morning produces **two hundred and fifty governed acts a year**, each with
a warrant behind it and a signature on it, and until now none of them had a
record anybody could read. Compiling means all of them exist whether or not
somebody had time to write one — and the fit that needs a human note has a place
to put it, as an attachment against the same `parameter_set` subject.

### A fit with no warrant is a named gap

```
**This section is required and could not be filled.**

Nothing in the register supports an `authority` section for this parameter set.
That is a statement about the record of this fit, not about this document.
```

A *fitted* set with no warrant has no answer to *which data produced these
numbers*, and that is worth saying out loud rather than papering over. A
**declared** set is different and says so: those values were chosen and
recorded, not produced by reading data, so there is no fit warrant to look for.

The same discipline applies one level down. If the set does not name a
featureset version, *What it read* is a gap rather than an invented name.

## The dossier — the graph, walked

```bash
GET /api/v1/dossiers/credit.pd.smallbiz
```

A model's documentation is a graph and was being read as a list. The dossier
walks it from the model down, following the **pins**:

```
model
 ├── attached: methodology paper, literature, vendor note
 ├── compiled: model development document, model card, Annex IV
 └── version 1.0.0
      ├── attached: kernel specification
      ├── compiled: validation report
      ├── parameter set ps-8817        (fitted 2026-03-31)
      │    ├── compiled: training record
      │    ├── attached: convergence study
      │    └── fitted from  featureset sb_core @ v1
      │         ├── attached: data dictionary, source agreement
      │         └── feature dscr
      │              └── attached: business definition
      └── validation val-3391
           └── attached: independent recode
```

The featureset version hangs under the **parameter set**, not under the model,
because that is where the pin actually is: this fit read *that* version. A model
whose next fit reads `sb_core @ v2` gets a second branch rather than an edited
one.

**Computed, never stored.** Its inputs are all versioned or immutable, so there
is nothing to keep in step — and a stored dossier would be a second account of
the model's documentation, able to disagree with the first.

**Every node with nothing filed is a named gap**, with what was expected:

```json
{"counts": {"nodes": 14, "documents": 9},
 "gaps": [
   {"what": "feature dscr",
    "why": "nothing is filed here; expected the business definition"},
   {"what": "parameters ps-8820",
    "why": "a fitted set that does not name the featureset version it came from
            — 'what data produced these numbers' has no answer from here"}],
 "detail": "9 document(s) across 14 node(s); 2 gap(s)"}
```

A page that silently omits what it could not find reads as complete, and a
reader cannot tell a thin model from a thin page unless the page says which it
is. A subsystem that is unwired or refusing yields an empty list and a logged
warning rather than breaking the walk — the rest of the graph is still worth
seeing.

## Documents on file

### Filed against the version, not the model

A model development document does not describe *the model*. It describes a
particular version of it — the one whose coefficients it prints, whose
assumptions it states, whose back-test it reports. When that version is
replaced, the document does not automatically describe the replacement.

So the default is version-level. Filing at model level is possible — a board
paper covering the whole portfolio is genuinely about the model — but you have
to ask for it, because the ambiguous case should not be the default one.

```bash
POST /api/v1/attachments        # multipart/form-data
# urn, kind, title, file
# plus optional: semver, note, supersedes, model_level, subject_type, subject_id
```

`subject_type` and `subject_id` are for the documents that were previously
unfilable: a convergence study about one parameter set, a data dictionary about
one featureset version.

### Stored by digest, so it cannot be edited underneath you

Every document is stored under the SHA-256 of its bytes. Three properties
follow, and each is one this platform relies on elsewhere.

**The same file is stored once.** A board paper covering forty models is one
stored object with forty attachments pointing at it.

**A document cannot be edited in place.** Change a byte and the digest changes,
which makes it a different document. Replacing one is therefore a *supersession*
somebody declares, not an edit nobody sees — the same reasoning that makes model
versions immutable.

**What was reviewed is what is served.** The store re-hashes the bytes on the
way out rather than trusting the path it was given. If they disagree the read
fails with `document_corrupt` and tells you to raise an incident, because at
that point the store has been tampered with or has corrupted, and the document
should not be relied on.

### Review is segregated

Whoever attached a document cannot accept it. A model owner filing their own
validation report and marking it accepted is not a control, and the fact that
the document is genuine does not make the process one. This is checked twice, on
purpose:

| Line | Check | Refusal |
|---|---|---|
| Authorisation | Does this role hold `document:review` at all? | `forbidden` |
| The register | Is this the same person who filed it? | `self_review` |

Owners and developers hold `document:attach`. Validators and model risk managers
hold `document:review`. The second check exists anyway, because a role grant is
a policy that can change and segregation of duty is not.

**Rejection requires a reason** — `reason_required` — and a rejected document
stays in the register. The set of documents somebody tried to file and could not
is often the more interesting set, and a register that deletes them makes a
review look cleaner than it was.

### Supersession keeps the chain

When a revised document replaces an earlier one, the new attachment names what
it supersedes. The prior document moves to `superseded`, is linked forward to
its replacement, and drops out of the current set — but stays in the history.

That is what makes *"which MDD was in force in March"* an answerable question
rather than a guess, and why superseding the same document twice is refused as
`already_superseded`: the chain would fork.

### What machines can read, and what they cannot

Each attachment records whether its bytes are text the platform can actually
read. Plain text, markdown, CSV, HTML, JSON and XML are indexed. A PDF or a Word
document is stored and served faithfully, but reported as **not
machine-readable**, and asking for its text returns nothing rather than a guess.

Machine validation of documents, and retrieval over them, both depend on knowing
which documents have genuinely been read. Saying plainly that a scanned PDF has
not been read is better than producing a confident summary of nothing.

### The nine kinds, and what the register answers

`model_development_document`, `validation_report`, `independent_review`,
`vendor_documentation`, `committee_minute`, `board_paper`,
`evidence_of_control`, `correspondence`, and `other` — named honestly rather
than forced into a category.

```bash
GET /api/v1/attachments?urn=…              # the current set, plus a summary
GET /api/v1/attachments?urn=…&history=true # superseded and rejected included
```

The summary is how many are accepted, how many await review, how many were
rejected, which kinds are present, and how many are not machine-readable. Two
[baseline gaps](/help/estate-and-worklist) read straight from it:
`model_development_document` (no MDD on file, so the method is undocumented) and
`accepted_documentation` (documents on file but none accepted by a second
person — filing is not review).

## Export packs

A compiled document answers a question. An **export pack** answers the person: a
supervisor, an internal auditor, an acquirer's diligence team — somebody who is
not going to be given a login, cannot query the platform, cannot take its word
for anything, and will read the result months later.

```bash
curl -u a.mehta:pw -X POST \
  localhost:5006/api/v1/export-packs/credit.pd.smallbiz -o pack.zip
```

```
manifest.json              what this is, when it was cut, the digest of every file
README.md                  how to read it and how to verify it
gaps.md                    what could NOT be included, and why
model.json                 identity, ownership, purpose, tier and its derivation
versions.json              every version, its kernel, its status, its approvals
documents/                 the four compiled documents, markdown and JSON
documentation/dossier.json the whole graph, with its gaps
attachments/               the documents somebody filed, as the bytes accepted
evidence/chain.json        the evidence for this model, with the verification result
findings.json  monitoring.json  overlays.json  warrants.json  validations.json
```

The dossier travels whole. The pack already held each document but not how they
relate, and a reader outside the platform cannot walk the register.

### Read `gaps.md` first

Everything the pack could not gather is listed there with the reason. A pack
that silently omits what it could not reach **reads as complete**, and a reader
has no way to tell a thin model from a thin export. A required document section
with no evidence behind it appears as a gap; an attachment whose bytes could not
be read appears as a gap; a document that would not compile appears as a gap
rather than killing the pack; and every dossier gap is carried across.

### The content digest is the comparison

`manifest.json` lists every file with its SHA-256 and carries a **content
digest** over all of them *except the manifest itself*.

That exclusion is the point. The manifest records the moment the pack was cut,
so a digest covering it would differ every time and answer nothing. Excluding it
means two packs of the same state share a digest — so *"has anything changed
since last quarter's pack?"* is one comparison rather than a diff of a hundred
files. Member order and timestamps inside the zip are fixed for the same reason.

```bash
curl -su a.mehta:pw \
  localhost:5006/api/v1/export-packs/credit.pd.smallbiz/manifest \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["content_digest"])'
```

The manifest endpoint exists for exactly that: comparing against the last pack
should not require moving a hundred megabytes to discover that nothing has
moved. **Where the chain stood** is in the manifest too — `chain.head_seq` and
`chain.head_hash` — and deliberately *not* in the digested content. A model's
pack should not change because a different team registered a model somewhere
else.

### What a pack deliberately does not do

**It does not author anything.** The documents are *rendered*, not compiled:
cutting a pack every month should not silently author four documents a month,
and a pack whose own production changed the record would differ from the last
one for no reason but that somebody had asked for it.

**It does not re-materialise personal data.** A node flagged as referencing
personal data was stored with an empty payload (L-18), so the pack carries the
empty node. There is nothing to re-materialise: the payload was discarded when
the node was appended, not held behind a pointer the pack could have followed.
`gaps.md` says so, rather than letting the reader mistake a thin model for a
thin export.

**It refuses rather than truncating.** Past 2 GiB the pack is refused as
`pack_too_large` with the way out — exclude attachments, or ask for fewer
documents. An export nobody can open is not an export.

**Cutting one is recorded** — handing a complete record of a model to somebody
outside is a governance act, and who took a copy is what an auditor asks about
later. It is recorded against the **pack**, whose identity is its content
digest, rather than against the model: recorded against the model it would land
inside the next pack's own evidence, and every pack would differ from the last
for no reason but that somebody had taken one.

## Reviewing one, and the one thing you cannot do to it

`GET /document-review` holds comments on a compiled document — which section is
wrong, what about it, and what happened. What it does not hold is an edit.

> **A compiled document cannot be edited.** Every sentence in one is assembled
> from the evidence chain and cites a node. Editing the prose would break the
> citation without changing the record it cites, producing a document that reads
> correctly and is <strong>no longer traceable to anything</strong> — which is
> worse than a wrong sentence, because a wrong sentence can be found.

**So the fix for a wrong sentence is a fix to the record it was compiled from**,
and then a recompilation. That is not a workaround; it is the only correction
that leaves the document still meaning what it says.

A comment says what it is asking for, from a closed list, because *please look at
this* and *this is factually wrong* are different obligations:

| `asks_for` | What is owed |
|---|---|
| `comment` | Nothing. It is here so a reader in a year sees what a reviewer noticed |
| `clarification` | The section is unclear — usually a narrative fix, not a record fix |
| `factual` | The section says something the register does not support. **Fix the record** |
| `omission` | Almost always a missing piece of evidence rather than a missing paragraph |
| `objection` | The reviewer does not accept it. A standing disagreement, not something the compiler resolves |

Three rules are worth knowing before you use it.

**Comments attach to the version you read.** They are keyed on the document's
digest, so a recompilation starts with none open and the earlier round is
reported as *raised against an earlier version*. A comment moved forward onto a
recompilation would be a remark about text that may no longer be there — and
worse, one that looks answered.

**Closing a comment says what was done**, and where the fix was to the record it
names the node. A comment closed with *fixed* and nothing else is
indistinguishable a year later from one closed because the reviewer gave up, and
the difference is the entire value of a review history.

**A `factual` comment or an `objection` cannot be closed by the person who raised
it.** An objection somebody withdraws themselves is a disagreement that never
happened. Withdraw it explicitly instead — that is its own act and is recorded as
what it is.

The narrative sections your firm writes itself are attachments, and attachments
already carry versions. There is no second editor for them here.

## What is not built

There is no PDF renderer, no house template and no signature page, and each is
now refused **by name with its reason** at `GET /api/v1/document-rendering/
formats` rather than being simply absent.

What *is* emitted, besides markdown and JSON, is **typesetting source** —
LaTeX — with the citations intact. That is the part worth having. A section of a
compiled document names the evidence nodes it rested on, and a PDF produced by
flattening that away is a document whose claims can no longer be traced, which
is the state every hand-written model document in every bank is already in.
Coverage gaps go **into** the output under a heading of their own, because a
rendering that dropped them would produce something that *looks* complete.

Rendering it needs a TeX distribution or a browser engine — a large attack
surface for a formatting need — and a house template, which is your firm's
document standard rather than a register's decision. Three renderings of one
document are three things that can disagree.

Two laws touching documentation are stated and do **not** run. **L-6**
(abstraction soundness) needs a replay that checks a document's quantitative
claims against the register; the replay exists for validation episodes, not for
documents. **L-11** (the lens laws) needs a `put`, and the compiler regenerates
whole documents rather than editing them — so the lens here is a `get` and
nothing else, and building a `put` to satisfy a law would be building the wrong
thing.

Nothing here is a document management system either: no check-out, no rendering
pipeline for proprietary formats, no rich-text editor. It is a register. It knows
which subject a document describes,
who filed it, who accepted it, what was rejected and why, and that the bytes
served are the bytes approved.
