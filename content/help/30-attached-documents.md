---
title: Documents on file
slug: attached-documents
section: Assurance
order: 143
icon: paperclip
summary: The documents people wrote — development documents, validation reports, committee minutes — filed against the version they describe, stored by digest, and accepted by somebody other than whoever filed them.
audience: Model owners, Model risk, Validators
---

# Documents on file

MAYA holds two kinds of document and keeps them apart deliberately.

**Compiled documents** are generated from the register and the evidence graph.
Every section cites what it rests on, staleness is computed, and a gap is
reported rather than papered over. Those are covered in
[Compiled documentation](/help/documentation).

**Attached documents** are the other half: the papers somebody actually wrote.
The model development document a quant produced in Word. The validation report
the second line signed. The credit committee minute that approved the override
policy. The vendor's manual for a model the bank bought rather than built.

MAYA cannot generate those, and pretending otherwise would be dishonest. What it
can do is make them behave like evidence instead of like files on a share drive.

---

## A document is filed against a version, not a model

This is the rule that matters most, and it is the one most document stores get
wrong.

A model development document does not describe *the model*. It describes a
particular version of it — the one whose coefficients it prints, whose
assumptions it states, whose back-test it reports. When that version is replaced,
the document does not automatically describe the replacement.

So the default is version-level. If you do not name a version, the document lands
on the current one. Filing at model level is possible — a board paper covering
the whole portfolio is genuinely about the model rather than a version — but you
have to ask for it, because the ambiguous case should not be the default one.

A model with no versions is refused outright, with the remediation spelled out:
create a version first, or say explicitly that this document is model-level.

---

## Stored by digest, so it cannot be edited underneath you

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
rather than trusting the path it was given. If they disagree, the read fails and
tells you to raise an incident, because at that point the store has been
tampered with or has corrupted and the document should not be relied on.

---

## Review is segregated

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

**Rejection requires a reason**, and a rejected document stays in the register.
The set of documents somebody tried to file and could not is often the more
interesting set, and a register that deletes them makes a review look cleaner
than it was.

---

## Supersession keeps the chain

When a revised document replaces an earlier one, the new attachment names what it
supersedes. The prior document moves to `superseded`, is linked forward to its
replacement, and drops out of the current set — but stays in the history.

That is what makes *"which MDD was in force in March"* an answerable question
rather than a guess, and it is why superseding the same document twice is
refused: the chain would fork.

---

## What machines can read, and what they cannot

Each attachment records whether its bytes are text the platform can actually
read. Markdown, plain text, CSV, HTML and JSON are indexed. A PDF or a Word
document is stored and served faithfully, but reported as **not
machine-readable** rather than silently treated as read.

This matters for what comes next. Machine validation of documents, and retrieval
over them, both depend on knowing which documents have genuinely been read.
Saying plainly that a scanned PDF has not been read is better than producing a
confident summary of nothing.

---

## What the register answers

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

Compiled documents carry a **Documents on file** section listing what was filed,
who accepted it, and — deliberately — what was rejected.

---

## Kinds

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

---

## What this is not

It is not a document management system. There is no check-out, no collaborative
editing, no rendering pipeline for proprietary formats, and no full-text search.

It is a register: it knows which version a document describes, who filed it, who
accepted it, what was rejected and why, and that the bytes served are the bytes
approved. Everything else is a document management system's job, and MAYA does
not pretend to be one.
