---
title: What MAYA refuses to do
slug: what-maya-refuses
section: Start here
order: 80
icon: hand-raised
summary: Nine places where the platform declines to build the thing that was asked for — managed serving, converting an artifact, submitting a training job, editing a compiled document, configuring the state graph, promoting a challenger — and why each refusal is what makes every other control in the register mean anything.
audience: Model risk managers, Platform, Architects, Auditors
---

# What MAYA refuses to do

Most of this documentation is about what the platform does. This page is about
the nine places it deliberately does not — and it is the page to read if you are
deciding whether MAYA belongs in your architecture, because **the refusals are
load-bearing**. Take any one of them away and several controls elsewhere quietly
stop meaning anything.

There is a single sentence underneath all of them:

> **A platform that both authorises an act and performs it is the only witness
> to its own execution.**

Everything below is that sentence applied to a different request.

---

## 1. It will not serve your models

`FR-WARRANT-014` asks for an optional managed endpoint for teams without their
own runtime. It is refused, and this is the refusal the rest rest on.

Two things break at once.

**Operationally**, the register and the runtime become one process. An outage of
your governance platform becomes an outage of your credit decisions — and the
platform whose whole argument is that *a warrant survives its own
unavailability* would have made itself the thing that must not go down.

**In principle**, MAYA issues the authority. If it also performs the act, its
invocation log is a system describing itself.

The captive engine in the box is a **reference consumer of the public warrant
contract**: proof that the contract is usable by somebody other than its author.
It is off by one configuration key, and it is not a serving product.

---

## 2. It will not convert an artifact

Format migration is real work — a pickle no supported runtime will load, a vendor
artifact in a format your grammar does not admit. `FR-AI-009` asks for an agent
that converts and verifies. Converting means loading and running a model.

So MAYA holds the **claim** instead, and refuses on three things a real
equivalence report gets wrong:

| Refusal | The report it catches |
|---|---|
| A probe with **no result** fails, never skipped | A report over 40 of 50 probes looks exactly like one over 50 at the bottom of the page |
| A **thin probe set** yields `unsubstantiated`, never `passed` | Two implementations agree in the interior by construction; this one never reached the boundary |
| **Tolerance has no default** | One chosen after the divergences are known is a *description* of them, and will be exactly wide enough |

One case looks like a failure and is not: **both artifacts refusing is
agreement**, and about the most informative kind.

---

## 3. It will not submit your training jobs

`FR-TRN-004` asks for orchestration against a compute backend. MAYA is the
callee, always — a register that submitted jobs would be on the failure path of
the thing it exists to observe, and would need a client for every backend you
have.

What it does instead is the half a register is for, and it turns on one word:

> **A run is declared *before* it happens.**

Every experiment tracker writes its row when the activity finishes, which
produces a register of successes. A fit that started, consumed a warrant, read a
snapshot of somebody's data and then vanished appears in none of them — and it is
the run a supervisor asks about. Here it is **`lost`**, which is a state and not
an absence.

It also never reads `log_uri`. The field is there so a person can find the logs,
not so the platform can: fetching them would put MAYA's readiness on your object
store.

---

## 4. It will not take your verdict, only your number

You already have monitoring. MAYA takes the number — and there is no `passed`
field in the ingest body, the endpoint, or the SDK method.

**The threshold is your second line's and the comparison happens here.** A system
that could push its own metric *and* its own pass mark would be marking its own
homework, which is what every "send us your metrics" API quietly permits.

The price is stated rather than glossed: an external observation **cannot be
replayed**, because MAYA does not hold the population it was computed over. An
estate where most numbers cannot be re-derived is a real finding about the
programme — and an invisible one if both kinds print the same.

---

## 5. It will not recommend promoting a challenger

`/champion-challenger` answers two questions and refuses to collapse them.
**Significant** — is the difference bigger than the disagreement between windows?
With enough windows, everything is. **Material** — is it worth a revalidation and
a redeployment? That is your judgement, declared in the units of the test.

The strongest recommendation it will make is *open a validation of the
challenger*. Promotion is a second-line approval, and a monitoring module that
recommended it would be pre-empting the approval it exists to be evidence for.

---

## 6. It will not edit a compiled document

Every sentence in a compiled document cites an evidence node. Editing the prose
breaks the citation without changing the record it cites, producing a document
that reads correctly and is **no longer traceable to anything** — worse than a
wrong sentence, because a wrong sentence can be found.

> **The fix for a wrong sentence is a fix to the record it was compiled from.**

So you comment, saying which section and what kind of wrong, and the register
recompiles. A `factual` comment or an `objection` cannot be closed by whoever
raised it: an objection somebody withdraws themselves is a disagreement that
never happened.

---

## 7. It will not let you configure the state graph

You configure your gates, your warrant profiles, your monitoring defaults, your
appetite limits. You do not configure the lifecycle states, the tier lattice, the
trainability fibration, the refusal taxonomy, the evidence chain, or the
segregation-of-duties pairs.

Those are not settings somebody forgot to expose. A firm that could add a
transition could add one that skips approval; a firm that could edit the lattice
could make tier 1 owe what tier 4 owes.

And applying a configuration is a **governance act with a diff and a named
author**, not a deployment step — because config-as-code done naively means your
gates and your git repository have the same approval process, and that process is
a pull request reviewed by whoever is on shift.

A plan that **loosens** needs a named approver. A tightening can be a deployment;
a loosening is a decision, and the risk is that the two travel in the same pull
request.

---

## 8. It will not sign your artifacts

A digest establishes integrity; a signature establishes origin. MAYA verifies
attestations and does not mint them — signing belongs in a build system with keys
a build system holds, and **a governance platform that signed artifacts would
hold the key that could forge one**.

It ships no cryptographic library either. That would be shipping a trust-root
decision — whose keys, whose transparency log, whose revocation — that your
security function has already made differently.

---

## 9. It will not tell you a plan is cheap when the cheap route is wrong

`/models/{urn}/remediation` computes the shortest path to a model being in force,
in the tropical semiring, over a published derivation. The answer is arithmetic —
nothing asks a language model what to do next, and an arithmetic answer produced
by a model is a worse version of the same number.

Then it declines the obvious optimisation. A validation costs 40 units; a waiver
of the validation requirement costs 3. Both make the compliance predicate true
and only one makes the model safer, so a solver with no opinion about *kind*
recommends the waiver every time — correctly, and disastrously.

The cheap routes are computed too, and shown **beside** the plan under their own
heading, so you can take one deliberately rather than find it by accident. They
are excluded by kind and not by price: pricing a waiver at 400 units would make
the arithmetic come out right and would be a lie about what a waiver costs, and
the next person to read the table would correct it.

---

## What the nine have in common

Each one is a place where building the requested thing would have made a
different, quieter thing untrue.

| If MAYA did this | This would stop meaning anything |
|---|---|
| Serve models | Every claim that the register is an independent record of execution |
| Convert artifacts | The equivalence claim it holds to a standard |
| Submit jobs | The run register as an account of what somebody else did |
| Take a `passed` flag | The threshold your second line set |
| Recommend promotion | The second-line approval it is evidence for |
| Edit a document | The citation on every sentence in it |
| Configure the state graph | *Approved* meaning the same thing in two institutions |
| Sign artifacts | The provenance check, which would then verify its own signature |
| Hide the cheap route | The distinction between being safe and looking compliant |

When you are evaluating a governance platform, the useful question is not what it
can do. It is **what it declines to do, and whether it can tell you why** — and
whether the answer is a sentence about architecture or a sentence about a
roadmap.
