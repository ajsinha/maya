---
title: Taking everything about a model, in one package
slug: model-package
section: Start here
order: 50
icon: file-earmark-zip
summary: One model, digested and zipped, for somebody who will never be given a login — how to see what is in a package before you cut one, why the named gaps are the part that matters, and what the zip honestly does and does not contain.
audience: Model risk managers, Model owners, Auditors
---

# Taking everything about a model, in one package

A supervisor asks for everything you hold on the small-business PD model. An
internal auditor wants the file. An acquirer's diligence team has three weeks and
no login to your platform.

You could send them screenshots. Instead, MAYA cuts a **model package** — one zip
holding the register record, every version, the compiled documents, the filed
documents, the validation episodes, the findings, the monitors, the warrants, the
documentation graph and the evidence chain, with a SHA-256 against every file and
a statement of where the chain stood when you cut it.

The rest of this page is what to click, what you get, and — the part that
matters — how to tell a thin model from a thin export.

---

## 1. Start at the package list

Sign in and go to **`/packages`**.

You get one row per model **you are entitled to read**. This is filtered, not
listed: an inventory of every model name in the estate is itself sensitive, and a
package is the most complete thing this platform will ever produce about a model,
so an export of one outside your scope would be the largest leak available. If a
model you expect is missing, that is a scope answer, not a bug.

The page also publishes what a package contains, member by member, before you
have cut anything. Read it once. A reader who does not know what *should* be in a
package cannot tell what is missing from one.

Click **the pack →** on the model you want.

---

## 2. See what is in it before you cut it

**`/packages/credit.pd.smallbiz`** is the whole screen for one model. The table
headed *What this pack will contain* is counted from the register **by the same
gatherer the packer uses**, so the page cannot promise a member the zip will not
carry. For the worked model on this page it reads:

| Member | What it holds today |
|---|---|
| `manifest.json` | written last, and excluded from the content digest |
| `README.md` | how to read it and how to verify it |
| `model.json` | 1 record, 1 alias move(s) |
| `versions.json` | 1 version(s) |
| `documents/` | 4 kind(s), rendered at the moment the pack is cut |
| `attachments/` | 1 filed document(s) |
| `evidence/chain.json` | 19 node(s); the chain verified True |
| `validations.json` | 1 episode(s), 1 result(s) |
| `findings.json` | 1 open |
| `monitoring.json` | 1 monitor(s), 0 open breach(es) |
| `overlays.json` | 0 overlay(s), 0 active |
| `warrants.json` | 2 standing grant(s) |
| `documentation/dossier.json` | 1 document(s) across 4 node(s); 4 gap(s) |
| `gaps.md` | written after gathering — preview the pack to read it |

Below it the same screen shows you the state itself, so you can sanity-check
before you send anything to anybody: every version with its status, trainability
class and manifest digest; every **parameter set** with its provenance, its
review state, the grant it was fitted under and — the pin that matters — the
featureset **version** it read, shown as `sb_core@v1` rather than `sb_core`. A
document filed against the set would describe something that has since moved.

Then the record around it — evidence nodes and whether the chain verifies,
validation episodes, open findings, monitors, overlays, standing grants, alias
moves — and the documents somebody actually filed, with who filed them, who
reviewed them, and their digests.

Everything on that screen is a read. Nothing has been exported yet.

---

## 3. The named gaps — read this before you send anything

This is the single most important idea on the page.

A package that quietly leaves out what it could not reach **reads as complete**.
Someone opening it months from now, with no login and no way to ask you, cannot
tell the difference between a model that is thin and an export that is thin. So
MAYA writes the absence down. Every part it could not gather goes into
`gaps.md`, with the reason, inside the zip.

Click **Preview the manifest and the gaps**.

The preview builds a real package, reads the manifest and `gaps.md` back out of
it, and throws the bytes away. **Nothing is recorded**, because nothing left the
platform — an export is evidence of a *copy being taken*, and looking at what one
would contain is not taking one.

You get the manifest header:

```
Would be called    maya-export-credit.pd.smallbiz-20260905.zip
Content digest     sha256:e6c0808249cccc1745387e3968c9e65bf53e50a2538bfcea7f15a02ef299a935
Pack digest        sha256:e10ab28510660c0ed3662dd26e1e9153cc831a7b5b6d564c2f6bab20ff30ea7c
Chain head         seq 31, sha256:2f2caec4a8b7…, verified true
Cut at             2026-09-05T21:19:07Z by s.iqbal
Size               0.03 MB, 22 file(s)
Gaps               8 recorded
```

every file with its byte count and its SHA-256, and then `gaps.md` **exactly as
the zip will carry it**:

> **Gaps**
>
> What this pack could not include, and why. An absence is recorded rather than
> omitted: a pack that silently dropped what it could not reach would read as
> complete, and a reader would have no way to tell a thin model from a thin
> export.
>
> | What | Why |
> |---|---|
> | `documentation/model SB PD` | nothing is filed here; expected the methodology, and the literature the approach comes from |
> | `documentation/parameter_set parameters sb-pd-2025q1` | nothing is filed here; expected the training record, and any note explaining this fit |
> | `documentation/validation validation ['discrimination']` | nothing is filed here; expected the independent recode, and the reviewer's working |
> | `documents/model_development_document.md § data_and_features` | a required section had no evidence to fill it |
> | `documents/annex_iv.md § overlays` | a required section had no evidence to fill it |

(Five of the eight rows are shown.) Read that list as your worklist. Eight gaps
on a Tier 2 model going to a supervisor is a conversation you want to have
*before* the zip leaves, not after. Three of the eight are places where nobody
filed a document; four are required sections of a compiled document that had no
evidence to fill them; the eighth is covered in §6. All of them are fixable, and
all of them are invisible in any export that does not name them.

Two things follow, and they are the reason this file exists:

- **Fewer gaps is not automatically better.** Narrowing a package narrows its
  gaps too. The same model cut down to the model card alone, with filed documents
  excluded, reports *"14 file(s), 4 gap(s) recorded"* — half the gaps, because
  half the documents were never asked for.
- **A package with no gaps is a real statement.** `gaps.md` is present even when
  it is empty, and then it says so: *"None. Every part of this pack was gathered,
  and every required section of every document was filled."* That is worth
  more than a hundred files.

---

## 4. Cut it and download it

Same card, same screen. Tick the document kinds you want (all four by default —
the audience differs per document, and a package cut for one reader is a package
the next reader has to ask for again), tick or untick the filed documents, and
press **Cut it and download**.

The browser downloads `maya-export-credit.pd.smallbiz-20260905.zip`. Two digests
come back on the response and are worth keeping in the covering email:
`X-Pack-Content-Digest` and `X-Pack-Digest`.

It is a form POST rather than a link, deliberately. Taking a complete record of a
model away is **recorded**, and an act that is recorded should not be reachable by
something a crawler, a link preview or a mistyped URL performs on your behalf.
What lands in the evidence chain is:

```
export_pack_cut   by s.iqbal
  urn: maya://model/credit.pd.smallbiz
  pack_digest: sha256:9bfe1dbe26c0…
  files: 21    gaps: 8
  documents: [model_development_document, validation_report, model_card, annex_iv]
  taken_from: the model package screen
```

recorded against **the package** — its content digest — and never against the
model. Against the model it would land inside the *next* package's own evidence
segment, and every package would then differ from the one before it for no reason
except that somebody had taken one. Three people cutting the same unchanged model
produce three `export_pack_cut` nodes under one subject, which is exactly the
answer an auditor is after: who took a copy, and when.

### For whoever automates it

The SDK, for a monthly export:

```python
from maya_sdk import Maya

maya = Maya("https://maya.internal", "s.iqbal", "…")

maya.packages.describe()          # what a package contains, before the first one
maya.packages.manifest(urn)       # the manifest without moving the bytes
maya.packages.cut(urn, "/exports/sb-pd-2026-09.zip")
```

`cut()` writes to a file and returns the path rather than handing you bytes — a
package carries every accepted attachment, and an SDK that returned it in memory
would be convenient until the first model with a scanned vendor manual in it.

And curl:

```bash
# what is in one, and the digest — without downloading anything
curl -u s.iqbal:… https://maya.internal/api/v1/export-packs/credit.pd.smallbiz/manifest

# the zip itself
curl -u s.iqbal:… -X POST -OJ \
  https://maya.internal/api/v1/export-packs/credit.pd.smallbiz
```

`?documents=model_card,validation_report` narrows the compiled documents;
`?attachments=0` leaves out the filed ones.

> The `/manifest` call is its own endpoint for one reason: comparing the content
> digest against last month's answers *has anything changed?* without moving a
> hundred megabytes to find out that nothing has.

---

## 5. Opening the zip

```
README.md                                   how to read and verify it
gaps.md                                     ← open this first
manifest.json                               every file, its size, its SHA-256
model.json                                  register record, assessment, lifecycle, alias moves
versions.json                               each version, kernel, contract, status, digests
documents/model_development_document.md/.json
documents/validation_report.md/.json
documents/model_card.md/.json
documents/annex_iv.md/.json
documentation/dossier.json                  the documentation graph
attachments/index.json                      what was filed, by whom, reviewed by whom
attachments/114e03d1-methodology.md         the bytes that were accepted
evidence/chain.json                         the nodes, and the verification result
validations.json  findings.json  monitoring.json  overlays.json  warrants.json
```

Twenty-two members. Attachments are named by digest **and** filename, because two
models may file documents called `methodology.md` and a package that collided
would silently lose one.

**To verify it**, re-hash every member and compare against `manifest.json`. Then
read three fields:

- **`content_digest`** — over every file *except the manifest*. This is the number
  to compare against your last package. Two packages of the same state produce
  the same content digest even though they were cut on different days; the moment
  of cutting lives only in the manifest, which is excluded. Answering *has
  anything changed since last quarter?* is one comparison, not a hundred-file
  diff.
- **`pack_digest`** — over the zip itself. This one *does* change every time,
  because the manifest carries the timestamp. Use it to prove which copy you were
  sent; never to ask whether the model moved.
- **`chain.head_seq` / `chain.head_hash`** — where the evidence chain stood when
  this was cut. A later package with a higher `head_seq` means the record moved.
  The same head means it did not. That turns *"is this still current?"* into a
  question with an answer rather than an assurance.

### Three decisions worth knowing about

**The content digest excludes the manifest.** Otherwise every package would differ
from every other package — the manifest carries the moment it was cut — and the
one comparison you actually want would be destroyed by the timestamp.

**A gap is written down rather than omitted.** Covered above, and it is the reason
this format is worth trusting at all.

**Documents are rendered, not compiled.** Compiling a document in MAYA is an
*act*: it authors the document and records that it was authored. If cutting a
package compiled instead, a monthly export would author four documents a month
and twelve of each a year, and each package would differ from the last for no
reason except that somebody had asked for one. So the packer renders what the
compiler *would* say and writes nothing back. Your monthly export does not
pollute the documentation register.

---

## 6. What the package does not contain

Stated here rather than left for a reader to find out at the wrong moment.

- **There is no `parameters.json`, and the fitted values are not in the zip.**
  The coefficients themselves — `intercept`, `dscr`, `turnover` — appear nowhere
  in the package. What travels is the parameter set's *identity and provenance*:
  its name, whether it was fitted, calibrated or declared, its `as_of`, and in
  `evidence/chain.json` its digest, its cardinality, the grant it was fitted
  under, and the featureset pin `sb_core@v1`. A reader can prove which numbers
  were used and where they came from; they cannot read the numbers. If your
  recipient needs the values, send them separately and say so.
- **The documentation graph does not follow the featureset pin.**
  `documentation/dossier.json` records a gap reading *"a fitted set that does not
  name the featureset version it came from"* — for a set that plainly does name
  one, and which the screen you were just on displays correctly as `sb_core@v1`.
  Take the pin from `evidence/chain.json`, under the `parameter_set_recorded`
  node, until this is fixed.
- **`manifest.json` is in the zip but absent from its own file list.** The zip
  holds twenty-two members; `manifest.json`'s `files` array has twenty-one rows,
  for the same reason it is left out of the content digest. Anyone comparing the
  two counts is off by one, and so are MAYA's own numbers: the screen reports
  *"22 file(s)"* while the `export_pack_cut` evidence node records `files: 21`.
- **Unticking the filed documents leaves no trace in `gaps.md`.** The
  `attachments/` directory simply is not there, while `manifest.json`'s own
  `contents` map still lists it. That is a narrowing you chose, not something the
  platform could not reach — but a recipient cannot tell the difference from the
  file alone. Say in the covering note that you narrowed it.
- **Personal data is not re-materialised.** An evidence node flagged as carrying
  personal data holds no payload at all in the platform, and the package carries
  the same pointer. Resolving it into the export would put personal data into a
  file on somebody's laptop where an erasure request cannot reach it — defeating
  the control rather than exporting it. When this happens the package says so,
  in `gaps.md`.
- **A package over 2 GB is refused rather than streamed.** The refusal tells you
  to narrow it. An export that arrives as forty gigabytes is one nobody opens.

---

## 7. If you would rather look than download

**`/dossier/credit.pd.smallbiz`** is the same documentation graph, on screen.

Documentation is a graph, not a list: a methodology paper about the model, a
training record about one fit, a data dictionary about one featureset *version*.
The page draws those edges from the pins the register already holds, counts the
documents and the nodes, and — like everything else here — names what is missing
instead of leaving a blank. Same discipline, no zip.

Use the dossier when you are chasing a specific document. Use the package when
somebody outside needs the whole file.

---

## What to do next

1. Preview the package for your two most material models. Read `gaps.md`.
2. Turn each gap into an action — file the document, or record the evidence the
   section needs — and preview again.
3. Cut one and keep the content digest. Next quarter, call `/manifest` and
   compare. If the digest matches, nothing about that model changed.

---

## Related

- [Defining a model](/tutorials/defining-a-model) — the register record that
  becomes `model.json`
- [Features](/tutorials/features) and
  [Featuresets](/tutorials/featuresets) — what the pin `sb_core@v1` refers to
- [Warrants and training](/tutorials/warrants-and-training) — where parameter
  sets and their provenance come from
- [The whole path, end to end](/tutorials/end-to-end) — every part of this in one
  worked example
- [Documentation](/help/documentation) — how documents are compiled, and what a
  coverage gap means
- [Evidence and provenance](/help/evidence-and-provenance) — the chain the head
  digest refers to
- [Featuresets and parameters](/help/featuresets-and-parameters) — the register
  behind the parameter table
- [API reference](/help/api-reference) — the export endpoints in full

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE.
*Not legal, regulatory or financial advice — see NOTICE §4.*
