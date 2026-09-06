---
title: Administering MAYA
slug: administering-maya
section: Reference
order: 145
icon: sliders
summary: Six screens about the platform rather than about any model in it — who may act, which rulebook is in force, what runs unattended, whether the record is still intact, and what may execute. All read-only, all gated by the same permission their API asks for.
audience: Operators, Platform, Model risk
---

# Administering MAYA

Everything here is about the machinery rather than about any model in it. It sits
behind **Admin** in the bar, and each entry appears only if you hold the
permission that screen's API asks for — so the menu you see is not the menu
somebody else sees.

That is deliberate and it is not tidiness. A menu that lists a screen which then
answers *403* teaches people that refusals are noise, and this platform's entire
argument is that a refusal means something.

All six screens are **read-only**. They show you the state and name the endpoint
that changes it. The acts themselves stay where their evidence and their
segregation checks already live, because an administrative act that skipped
those would be the one act in MAYA with no record.

---

## People and roles

`/admin/principals` — needs `principal:read`

Every principal, the roles they hold, and the column that actually matters: the
**effective** permissions, which is what the union of their roles adds up to.
Somebody holding two roles can do things neither role alone describes, and
reading the role names tells you nothing about that.

Below it, two tables that are easy to confuse and are not the same thing:

- **Roles nobody may hold together.** A static constraint on the *person*. A
  validator who may also approve is not performing effective challenge, whatever
  the org chart says, so the pair is refused at the moment roles are assigned.
- **Segregation.** A constraint on the *act*, evaluated against what this
  principal already did to this thing. Whoever developed a version may not
  approve that version — but they may approve a different one. This is checked
  at the act, not at the role, because it depends on history.

Creating a principal, changing roles and suspending an account need
`principal:manage` and go through `POST /api/v1/principals`,
`PUT /api/v1/principals/{username}/roles` and
`POST /api/v1/principals/{username}/suspend`. Each is recorded on the evidence
chain like any other governed act.

## Policy gates

`/policies` — needs `policy:read`

The four gates a model passes through, what each currently demands, the drafts
nobody has published, and the **drift** each publication caused — read off the
evidence chain rather than recomputed, because a comparison was made against the
rule in force at the time and that rule may since have been superseded twice.

Authoring a gate and putting it in force are separate permissions on purpose.

## Regulatory regimes

`/admin/regimes` — needs `regime:read`

A regime is a supervisor's rulebook written down as obligations over a vocabulary
of its own. MAYA holds its state in *its* words, so applying a regime means
translating — and a translation that quietly loses a term has not preserved the
obligation, it has weakened it.

Each regime therefore reports whether its encoding is **consistent**: whether
everything the obligations mention is something MAYA can actually answer. A
regime that fails this refuses to be activated, rather than activating and
abstaining on the parts it cannot see.

Every activated regime answers about a model **separately**, and the answers are
deliberately not merged into one verdict. Two supervisors disagreeing is
information; averaging them away is not.

## Scheduled jobs

`/admin/scheduler` — needs `scheduler:read`

What runs unattended, what each job is for, when it last ran and whether it
succeeded. The health of the **scheduler itself** is the first thing on the
page, because a scheduler nobody notices has stopped is the same failure as a
monitor nobody notices has stopped, one level up.

Every run is recorded on the evidence chain, successful or not. "The batch did
not run" is a governance fact, not an operational one: expiry, staleness and
review dates are all computed by these jobs, and an estate whose jobs stopped
looks exactly like an estate with nothing outstanding.

Running the batch by hand needs `scheduler:run` and records the same evidence a
scheduled run does, so a hand-run is never invisible.

## Evidence integrity

`/admin/evidence` — needs `evidence:read`

Two questions, kept apart, and the distinction is the whole point of the screen.

**The chain against itself.** Every node is walked, and each node's content hash
is *recomputed from its own fields* rather than trusted as stored — so an edited
payload breaks this check and not only a broken link.

**The chain against a second medium.** The anchors are heads copied to
write-once storage outside the database. This is the only check here that
somebody holding the database cannot simply satisfy, because a chain rewritten
from the first node passes the first check perfectly.

Merging the two into a single green tick would be this platform's own recurring
defect: a control that reports success while answering a narrower question than
the reader believes it answered.

An anchor is never written for an empty chain. An anchor for sequence zero is a
permanent claim that nothing can ever satisfy, which would make every fresh
instance accuse itself.

## Runtimes and fibres

`/admin/runtimes` — needs `model:read`

One question asked twice.

The **grammar** is what a warrant may say: the verbs, the runtimes that may host
a kernel, where inputs may be bound from and where outputs may be written. The
warrant JSON Schema is generated from this same vocabulary rather than kept
beside it, so a client validating against the schema is validating against what
the platform will actually admit.

The **fibration** is what each trainability class must carry once admitted — its
evidence, its lifecycle, its metrics, its templates. A class with a missing facet
is one the platform would answer questions about by omitting them, so start-up
refuses on a gap rather than booting partial. If the gaps table on this page is
ever populated, the instance should not have started.

---

## Backing it up

Two stores, one snapshot. The database holds the evidence chain; `data/worm/`
holds the heads anchored out of it. They must be backed up **together**.

Restore a database older than its anchors and `/admin/evidence` will report a
disagreement permanently — a write-once store has no operation that removes an
anchor, and giving it one would defeat the whole control. That is the anchoring
working, not a fault, and it is the reason the pair is a pair. The full table of
cases is in [09 §4.6](../docs/09-security-compliance.md).

If the anchor root is genuinely lost, do not reconstruct one from the database.
An anchor derived from the thing it checks proves nothing. Start a new root and
record that verification before that date rests on the chain alone.

## What is not here

Administration in MAYA is currently *reading* the platform's configuration.
Editing model classes, lifecycle definitions, document templates and the test
catalogue is still API work. Connectors and a discovery scanner do not exist at
all — see the roadmap. The estate is what somebody registered.
