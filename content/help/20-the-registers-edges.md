---
title: What MAYA takes on trust
slug: the-registers-edges
section: Oversight
order: 95
icon: shield-exclamation
summary: Ten places where the record is not MAYA's own — an authority's clock, a firm's own package, another system's export, somebody else's scanner, a pack that left the building. Each is narrower than its name suggests, and this page is where that is said out loud.
audience: Model risk managers, Platform, Architects, Auditors
---

# What MAYA takes on trust

Almost everything in this library describes MAYA's own record: what it holds,
what it works out from what it holds, and what it refuses to conclude. This page
is about the other kind of place — where the platform is **relying on somebody
it does not control**, or where somebody is relying on it.

There are ten. The screen is `/admin/perimeter`, and if you read one thing
before relying on any of them, read this:

> At a boundary, the natural thing to report is the answer you wish you had —
> and the overstatement is invisible, because nobody can see past the boundary to
> check it.

Everything below is that sentence applied to a different boundary.

---

## The clock that is not ours

The evidence chain is hash-linked, and its heads are copied to write-once
storage outside the database. Both are checks MAYA performs **on MAYA** — which
is the party being asked making a statement about itself.

So an RFC 3161 token can be taken over an anchored head, from an authority
outside this platform. Read what it proves before you rely on it, because it is
narrower than *tamper-evident* suggests.

**A token bounds a head from above only.** It proves this hash existed *no later
than* that time. That is exactly what stops a chain being written after the fact
and dated before it — which is the attack that matters. It says nothing about how
early the head existed, nothing about whether anything was deleted, and nothing
at all about the period before the first token was taken.

**MAYA is not the authority, and does not verify.** Checking a token means
holding a certificate chain and deciding which roots to trust, and your security
function has already made that decision once, for the whole institution. So
`unverified` is a real state: a token is held and nothing here can check it. It
is not *no token*, and it is certainly not *a verified one*. Wire a verifier and
the state can reach `verified`.

If no authority is wired at all, the evidence screen says so rather than showing
a tick.

## Installed is not enabled

Your own package can add a test type, a metric type, a template, a notification
channel or a fibre. Two states, and the gap between them is the control.

**Discovery reads packaging metadata and imports nothing.** Enabling is a
separate act that configuration has to name.

> A control that switched itself on when somebody bumped a dependency is a
> control nobody turned on — and one that switched itself *off* the same way is
> worse, because the platform would then report a control operating that is not.

`seen` is the ordinary state and not a fault. The two refusals are different
problems: `not_enabled` means it is installed and nothing names it, which is
safe; `not_installed` means configuration names something absent, which means
somebody believes a control is running.

Closed axes are listed with what each closure protects. A closed axis here is the
feature rather than a missing one.

## What another system's export can and cannot say

MLflow, Unity Catalog, git, SageMaker, Vertex, SAS metadata and a CMDB extract
can all be read — from a **document that platform exported**, never from its API.
A governance register with read credentials to every ML platform in the bank
holds the broadest standing access anybody has, granted to the system whose whole
argument is that it holds none.

What comes back is **candidates for triage, never registrations**. Five
governance facts are in no ML platform anywhere:

| | |
|---|---|
| ownership | in the bank's sense, not who last pushed a commit |
| approved use | what decision this is authorised for |
| legal entity | which one carries it |
| materiality | what rides on it |
| *is it a model at all* | rather than an experiment somebody ran once |

A connector that inferred any of those would have manufactured exactly the facts
the register exists to hold, at import scale, in one afternoon.

**And watch the `do_not_read_as` list.** It is the harder half of the same
problem. An *absent* governance fact is the easy case — somebody notices. A
**present** field with the right word on it is not. SageMaker's `Approved` means
a pipeline step passed. MLflow's `Production` is a deployment stage. A Unity
Catalog owner is a read grant.

> Nobody goes looking for the difference between two things called *approved*.

## What a scanner has to send back

MAYA does not sweep your drives, for the same reason it does not hold ML
platform credentials: a EUC scanner needs read access to every shared drive in
the institution.

What it publishes instead is the **contract** — what a candidate and a sweep have
to carry, with the reason for each, and a confidence ceiling strictly below
certainty. A scanner asserting `1.0` is asserting a registration decision it is
not in a position to make.

**A sweep is admitted whole or refused whole.** Keeping the good rows and
dropping the rest is the obvious kindness and it is wrong: the precision figure
computed afterwards would grade *the rows MAYA chose to keep* rather than the
scanner that produced the sweep.

**Precision is computed; recall is not.** Precision comes from what triage
dismissed, which is a real measurement of the scanner rather than its opinion of
itself — and it exists only because the dismissals were recorded. Nothing here
knows what a scanner did not look at, so the contract asks the scanner to declare
its scope and treats *recall unknown* as the honest answer.

A reference scanner ships in `tools/scanner/`. It runs outside the platform and
imports nothing from it, deliberately: a scanner sharing code with the register
it reports to has findings that are partly the register's own opinion.

## What has left the building

Every export pack shared outside: who it went to, why, whether it is still live,
how many times it was read — and **how many reads were refused**, because in a
year *the link had expired* is a fact somebody will need.

A share points at a **content digest, never a path**. A link to a location serves
whatever is at that location later, which is how a supervisor ends up reading a
document nobody meant to send.

**It is not an examiner portal and it establishes no identity**, and both are
published rather than implied. A portal authenticates a third party *into* the
register, and whatever that session can reach, they can reach.

Revoking one ends access and does not unsend a document. The record keeps what it
already served.

## A document that leaves as source

A compiled document's sections name the evidence they rested on, which is what
makes staleness a number the platform computes rather than one somebody
remembers. So what leaves is **typesetting source** with the citations intact —
and PDF, `.docx` and standalone HTML are refused by name with their reasons.

Coverage gaps are written **into** the output, under a heading of their own. A
rendering that dropped them would produce something that looks complete, and
looking complete is the failure mode.

## A rulebook you already have

Your rulebook is a decision table four people maintain in a spreadsheet, or a DMN
file out of a BPM suite. Both can be read — into a **candidate**, which goes
through the same check, trial and publish path a hand-written rule set takes,
second-person approval included.

The difficulty is not the parsing. **A misread threshold does not fail.** It
produces a rule set that loads, validates, publishes and then decides differently
from the rulebook it claims to be, and nobody finds that by looking at it. So a
cell that is a human judgement is reported rather than guessed at, a document
with any such cell is refused whole, and a hit policy that cannot map is refused
by name with what the approximation would silently become.

A stored procedure is not translated and will not be.

## What a warrant signature proves

The one that runs the other way: somebody relies on **MAYA**.

Each audience's signing key is *derived* from its own principal, so a compromised
engine can forge warrants for **itself and for nobody else**. An engine collects
its own key and verifies what it receives without ever holding anything that
signs for another principal.

**What it does not prove is authorship to a third party.** A verifier holds the
key it verifies with, so it could have minted what it checks. A descriptor is
evidence **to the bank** and not to anybody outside it.

## Relying on somebody for the work, keeping the conclusion

An estate-wide monitoring sweep does not fit in one process, and MAYA does not
run a cluster.

But PSI, AUC, Gini and KS are functions of **sufficient statistics** — bin
counts, a rank sum, class counts — and those add across partitions. So the scan
runs where your data is, a few hundred numbers come back, and **MAYA computes the
metric and compares it to the threshold your second line set**. Unlike a number
somebody else computed, that result can be replayed.

What MAYA still cannot see is whether the job read the population it claims. A
`WHERE` clause that quietly excluded a segment produces statistics that are
arithmetically perfect and describe the wrong population — so the predicate and
the row count are recorded, and the population is **attested rather than
observed**.

---

## A control with nothing to compare against

The tenth is the one the others taught, and it is worth knowing because it
changes how you read every *nothing to report* in this platform.

MAYA watches for tier assessments whose facts have changed — and the first
thing it watches, *has the exposure moved*, turned out not to be answerable
unless somebody had **sourced** that model's exposure. The register holds no
standing exposure figure: it is supplied when a model is assessed and stored in
that assessment, so outside it the only number MAYA has is the one the
assessment was made from.

So there are three answers, not two:

| | |
|---|---|
| **fired** | the facts changed |
| **did not fire** | the facts were compared, and had not changed |
| **cannot check** | there was nothing to compare against |

The third never counts toward a stale figure and is reported on its own. A sweep
that said *nothing fired* over an estate it could not evaluate would be printing
its own blindness as an all-clear.

## Four of these will not be built

A list of absences reads as a backlog. Three of these four would make the
platform worse if they were closed.

| | What closing it would cost |
|---|---|
| An examiner portal | issuing a credential to somebody outside your firm, and owning its lifecycle |
| A PDF renderer | flattening away the citations that make a document traceable |
| Fetching exposure from the ledger | MAYA holding read credentials to your general ledger |
| Enforcing a cost budget | MAYA being on the serving path, which it will not be |

---

Where to look next: [Administering MAYA](/help/administering-maya) for the
screen, [Rule sets](/help/rule-sets) for the importer, and
[Monitoring](/help/monitoring) for the distributed sweep.
