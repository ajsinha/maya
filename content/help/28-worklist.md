---
title: The estate view and your worklist
slug: estate-and-worklist
section: Getting started
order: 28
icon: list-check
summary: What needs doing, derived from the register rather than assigned — and the estate-level picture a risk committee actually asks for.
audience: Everyone
---

# The estate view and your worklist

## A control nobody is told about

The platform computes a great deal: outstanding attestation signatures, monitors
past their cadence, overlays whose window has elapsed, debt approaching its
expiry, documents that have gone stale, findings past their remediation date.

Until this, it surfaced almost none of it. A control nobody is told about is a
control that operates when somebody happens to look.

## Work is computed, not assigned

**There is no task table.**

Every item on your worklist is derived from the same state the rest of the
platform reads. That has three consequences worth stating:

- It **cannot go stale.** Sign the attestation and the item disappears, because
  the item *was* the outstanding signature.
- It **cannot disagree with the register.** A task table is a second source of
  truth about what is outstanding, and it would be wrong within a week.
- It **cannot accumulate orphans.** Complete something by another route — the
  API, a script, another person — and nothing is left behind to be closed by
  hand.

The same principle as [document staleness](/help/documentation) and
[overlay expiry](/help/overlays): compute it, do not remember it.

## It is filtered to what you can actually do

An item appears on your list only if you hold the permission it needs, and only
if the model is inside your [scope](/help/authorisation).

Attestation goes further: you are shown *your role's* outstanding signature and
not somebody else's. A model owner sees `model_owner` outstanding; the risk
manager's signature is somebody else's work.

A list of work you cannot act on is a list you learn to ignore — and ignoring
the list is how the control stops operating. The count of everything else is
still shown, so nothing is hidden:

> 3 item(s) you can act on; 5 more are outstanding for other roles.

## What lands on it

| Kind | Appears when |
|---|---|
| **Attestation** | a required role's signature is outstanding, or an attestation has lapsed |
| **Approval** | a record has been submitted and is waiting on the second line |
| **Draft** | a model has no version, so it cannot be submitted |
| **Finding** | blocking, or past its remediation date |
| **Monitor** | its cadence has elapsed without an evaluation |
| **Overlay** | its window elapsed, its magnitude is unmeasured, or it has become persistent |
| **Debt** | a baseline gap is unplanned or approaching expiry |
| **Document** | it has gone stale relative to the register |

Ordering is **overdue, then due, then open** — and a low-severity finding with
months left deliberately does not appear at all. A worklist that shows everything
shows nothing.

One further detail: a subsystem that is unavailable or refusing does not blank
the list. Its items are skipped, the reason is logged, and everything else still
appears.

## The estate summary

Above the register, four numbers that a risk committee actually asks for:

**Models registered**, and how many are *in force* — attested, not merely
present.

**Blocking findings** across the estate, and how many models are not in force.

**Open breaches**, and how many models are **unmonitored** — the second is often
the more alarming number, because a model with no monitor cannot breach.

**Aggregate overlay adjustment** — how much of the estate's numbers is the model
and how much is us — with a persistent count beside it.

And where an estate has been imported, a **baseline debt burn-down**: closed
against raised, as a proportion. Not *how many models are compliant* — on day one
none of them are — but whether the debt is going down. Debt is shown apart from
breach here as everywhere, because a Tier 1 model that arrived last week and one
that missed its validation must never contribute to the same number.

Like the worklist, all of it is derived. There is no summary table to fall behind
the register, which matters because a stale summary is worse than none: somebody
will act on it.
