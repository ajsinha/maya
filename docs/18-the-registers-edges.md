# 18 — The register's edges

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [14 — Detailed design §26](14-detailed-design.md) and
[11 — Adversarial review](11-adversarial-review.md).

---

## 1. Why this is a document rather than a section

Every other document here describes MAYA's own record — what it holds, what it
derives from what it holds, and what it refuses to conclude. This one is about
the places where the record is **not MAYA's own**: where the platform relies on
a party it does not control, or where a party relies on it.

There are ten such places. They were built at different times, for different
requirements, by different arguments, and it took building them all to notice
they are one problem:

> **At a boundary, the natural report is the answer you wish you had — and the
> overstatement is invisible precisely because nobody can see past the boundary
> to check it.**

That sentence is not a consequence of anything else in this design. The
mathematics in [00](00-mathematical-foundations.md) constrains what the register
may **conclude** from what it holds; it says nothing about the *epistemic status
of what it holds*, and at a boundary that status is the entire question. This
document exists because that turned out to be a discipline in its own right,
with a rule of its own.

## 2. The rule

**Widen a type. Never add a caveat.**

A caveat lives in prose, and prose is read once by the person who wrote it. A
type is in the answer every time the answer is given.

The clearest case is the timestamp. A held RFC 3161 token that nothing has
verified is not the same object as a verified one, and it is not the same object
as no token. Both collapses are convenient:

| Collapse | What it reports |
|---|---|
| `unverified` → `verified` | a verification the platform did not perform |
| `unverified` → `absent` | an absence of evidence it in fact holds |

So the state is three-valued and the third value is inhabited. No sentence in a
manual would have done that work, because the two collapses happen at the moment
somebody writes a status column with two possible values.

The same move, ten times:

| Boundary | The convenient answer | The wider type |
|---|---|---|
| An external timestamp | verified, or no token | `verified` / `unverified` / `absent` |
| A third-party package | loaded | `seen` / `enabled` / `refused` |
| Another registry's export | registrations | **candidates**, with what must still be established |
| A field that sounds like governance | an approval | `do_not_read_as`, naming what it actually means |
| Somebody else's sweep | rows | a sweep admitted **whole** or refused whole |
| A pack that left the building | a portal session | a link to a **content digest**, `is_a_portal: false` |
| A compiled document | a PDF | typesetting source with the citations intact |
| A bank's rulebook | a rule set | a **candidate**, with untranslated cells named |
| Attested cost | a total | attributed, with the **unattributed share** |
| A control with nothing to compare | *nothing fired* | `cannot_check`, counted separately |

## 3. The ten, and what each declines to claim

Each is specified in [14 §26](14-detailed-design.md). What follows is the
boundary itself, stated once, so a reader can see the shape rather than the
implementations.

### 3.1 An attested time

The chain is hash-linked and its heads are anchored outside the database. Both
are arguments **from MAYA's own clock** — the party being asked making a
statement about itself. A token from an RFC 3161 authority is the first
statement about this chain MAYA did not author.

**MAYA is not the authority and does not verify.** Checking a token means
holding a certificate chain and deciding which roots to trust, and that is a
decision the firm's security function has already made, once, for the whole
institution. A register that made its own would either duplicate it or quietly
contradict it.

**The bound is stated in the interface.** A token bounds a head **from above
only**: it proves this hash existed *no later than* that time, which is exactly
what defeats writing a chain after the fact and dating it before. It does not
bound below, says nothing about deletion, and cannot see behind the first token.
Every one of those is a limit of RFC 3161 rather than of this implementation,
and a platform shipping *tamper-evident* without them would be trading on the
reader not knowing.

### 3.2 What is installed against what is enabled

Discovery reads packaging metadata and **imports nothing**. Enabling requires
configuration to name the extension.

> A control that switched itself on when somebody bumped a dependency is a
> control nobody turned on — and one that switched itself off the same way is
> worse, because the platform then reports a control operating that is not.

`not_enabled` and `not_installed` are separate refusals for that reason. The
first is the safe state. The second means somebody believes a control is running.

### 3.3 Reading another system's export

A connector parses an **export document** the source produced with its own
credentials, on its own schedule. It never calls an API and holds no credential:
a governance register with read access to every ML platform in the bank holds the
broadest standing access anybody has, granted to the system whose entire argument
is that it holds none.

It produces **candidates for triage, never registrations**. Five governance facts
are in no ML platform anywhere — ownership in the bank's sense, the decision the
model is used for, the legal entity, materiality, and whether the thing is a
model at all — and a connector that inferred any of them would have manufactured
exactly the facts the register exists to hold, at import scale.

And `do_not_read_as` is the harder half of the same problem.
`must_still_be_established` protects against an *absence*, and an absence is the
easy case: somebody notices. A **present** field with the right word on it is
not. SageMaker's `Approved` means a pipeline step passed. MLflow's `Production`
is a deployment stage. A Unity Catalog owner is a read grant.

> Nobody goes looking for the difference between two things called *approved*.

### 3.4 What a scanner has to send

MAYA does not sweep drives. §3.3's argument applies with more force, since a EUC
scanner needs read access to every shared drive in the institution.

**A sweep is admitted whole or refused whole.** Dropping the malformed rows and
keeping the rest is the obvious kindness and it is wrong: the precision figure
computed afterwards would grade *the subset MAYA chose to keep* rather than the
scanner that produced the sweep.

**Precision is computable and recall is not**, and the grade says so. Precision
comes from the triage outcomes — a real measurement of the scanner rather than
its opinion of itself, and it exists only because the **dismissals** were
recorded. Recall would require knowing what the scanner did not look at.

`tools/scanner/` is a reference scanner that satisfies the contract and lives
outside `core/` deliberately: a scanner sharing code with the register it reports
to has findings that are partly the register's own opinion.

### 3.5 A pack that has left the building

A share points at a **content digest, never a path** — a link to a location
serves whatever is at that location later, which is how a supervisor ends up
reading a document nobody meant to send.

**Every read is recorded, including the refused ones.** In a year, *the link had
expired* is a fact somebody will need, and a system that logs only successes
cannot produce it.

**It is not an examiner portal, and both facts are published.** A portal
authenticates a third party *into* the register, and whatever that session can
reach they can reach. Letting a time-boxed link be mistaken for scoped
interactive access is the mistake that costs something here.

### 3.6 A document that leaves as source

A compiled document's sections name the evidence nodes they rested on, which is
what makes staleness computable rather than remembered. So what leaves is
**typesetting source** with the citations intact, and coverage gaps are written
*into* the output under a heading of their own.

> A PDF that flattened the citations away is a document whose claims can no
> longer be traced — the state every hand-written model document in every bank
> is already in. One that dropped the gaps would look complete, and looking
> complete is the failure mode.

### 3.7 Reading a rulebook the bank already has

The difficulty is not the parsing. It is that **a misread threshold does not
fail**: it produces a rule set that loads, validates, publishes and then decides
differently from the rulebook it claims to be, and nobody finds that by looking
at it.

Three refusals follow. A cell that is a human judgement is reported rather than
guessed at, and a document with any untranslated row is refused **whole**,
because the rows a parser finds hard are the judgement calls. A hit policy that
does not map is refused **by name** with what first-match would silently become
— `COLLECT` would agree with the source on most inputs, which is worse than
disagreeing on all of them. And the catch-all is **derived** from first-match
semantics rather than inferred from a row's position.

A stored procedure is not translated and will not be: SQL is a general language,
a translator would be a compiler, and a wrong compiler is undetectable by reading
its output.

### 3.8 A signature an engine can check without being able to forge

The mirror image: a party relies on **MAYA**.

For two revisions the position was *asymmetric signing, not built*, which
deferred a real defect to a key hierarchy nobody had. The defect was two
questions treated as one:

| Question | Needs |
|---|---|
| Who can **forge** | containment. Operational, and the live problem |
| Who can **prove authorship to a third party** | public-key cryptography. Rare, and nobody had asked |

The first needs no asymmetry. It needs the key derived from the audience:
`HMAC(root, "maya/warrant/v<gen>/" ‖ audience)`. A stolen key forges warrants for
**one principal**. And the audience is read from **the document being verified**,
so re-pointing a warrant at another principal changes the key it should have been
signed under and fails inside `verify()` rather than depending on a separate
check somebody remembered.

What is not claimed is non-repudiation, and `GET /warrant-signing` says so: a
verifier holds the key it verifies with, so a descriptor is evidence **to the
bank** and not to anybody outside it.

### 3.9 Relying on somebody for the work, keeping the conclusion

The third shape, and the strongest where it is available.

An estate-wide monitoring sweep does not fit in one process. Putting Spark in
MAYA would make the governance platform own a cluster and sit on the compute path
for every model in the bank. Taking somebody's *number* — which
`core/monitoring/external.py` does, and correctly — gives up the derivation: an
external observation cannot be replayed.

But PSI, AUC, Gini and KS are functions of **sufficient statistics**, and those
add across partitions. So the scan runs where the data is, a few hundred numbers
come back, and **MAYA computes the metric and compares it to the threshold**.
The result is replayable.

What it still cannot see is whether the job read the population it claims. A
`WHERE` clause that quietly excluded a segment produces statistics that are
arithmetically perfect and describe the wrong population — so the predicate and
the row count are recorded, and the population is **attested rather than
observed**.

## 3.10 A control that cannot be evaluated

The ninth is the one the others taught. `core/risk/triggers.py` watches for
assessments whose facts have changed — and its first trigger, *has the exposure
moved*, turned out not to be answerable at all unless somebody had **sourced**
the exposure.

The register holds no standing exposure column. An exposure is supplied at
assessment time and stored in that assessment's own facts, so outside it the
only figure MAYA has is the one the assessment was made from. Comparing it
against itself answers nothing.

So the trigger reports **cannot check**, and that is a third state beside
*fired* and *did not fire*:

| | |
|---|---|
| fired | the facts changed |
| did not fire | the facts were compared and had not changed |
| **cannot check** | there was nothing to compare against |

Collapsing the third into the second is the convenient move, and it produces a
sweep that reports *nothing fired* over an estate it cannot evaluate — its own
blindness, printed as an all-clear. The estate view counts them separately for
that reason, and a `cannot_check` never counts toward the stale figure.

Which is the rule of this document arriving one more time, from a direction
nobody was looking: **widen the type**.

## 4. The boundaries that are refusals

Four of these could have been built the other way, and were not. Each closes only
by making something else untrue, which is what distinguishes a refusal from a
gap.

| | Closing it would require |
|---|---|
| An examiner portal | issuing a credential to somebody outside the firm, and owning its lifecycle |
| Rendering a PDF | flattening away the citations that make a document traceable |
| Fetching a tiering fact from the ledger | holding read credentials to the general ledger |
| Enforcing a cost budget | being on the serving path, which [04 §7](04-architecture.md) forbids |

A reader taking a list of absences for a backlog will plan to close all of them.
Three of the four would make the platform worse.

## 5. Where to look

| | |
|---|---|
| The design of each | [14 §26](14-detailed-design.md) |
| The screen | `/admin/perimeter` — four of them, for the people who own *what are we relying on somebody else for* |
| The SDK | `maya.timestamps`, `.plugins`, `.connectors`, `.scanner_contract`, `.shares`, `.rendering`, `.rule_import`, `.warrant_signing` |
| The reference scanner | `tools/scanner/` — runs outside, imports nothing from `core/` |
| The paper | `docs/research/models-as-parametric-kernels.tex` §5, *a fifth alteration* |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
