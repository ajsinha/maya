---
title: The estate and what needs doing
slug: estate-and-worklist
section: Assurance
order: 130
icon: list-check
summary: The estate-level picture a risk committee asks for, a worklist derived from the register rather than assigned, the compliance debt an imported estate carries honestly, and the scheduler that turns a computed condition into a recorded consequence.
audience: Everyone, Model risk, Programme, Operators
---

# The estate and what needs doing

Almost everything in this platform is **derived rather than remembered**. Expiry,
staleness, cohort maturity, outstanding signatures and missing evidence are all
computed from the register when somebody asks, because a second table recording
the same facts would be wrong within a week.

That design has exactly one hole in it, and this page is about the hole and the
three things that close it: a summary that shows the estate as it is, a worklist
that tells a person what only they can do, and a scheduler that makes a condition
nobody looked at have a consequence anyway.

> A condition that is true, and that nobody has looked at, has had no
> consequence.

## The estate summary

Above the register, the numbers a risk committee actually asks for.

**Models registered**, and how many are *in force* — attested, not merely
present. With a breakdown by tier and by state, and a count of the untiered.

**Blocking findings** across the estate, and how many models are not in force.

**Open breaches**, and how many models are **unmonitored** — the second is often
the more alarming number, because a model with no monitor cannot breach.

**Aggregate overlay adjustment** — how much of the estate's numbers is the model
and how much is us — with a persistent count beside it.

And where an estate has been imported, a **baseline debt burn-down**: closed
against raised, as a proportion.

All of it is derived, and it is rendered on the dashboard rather than served as
its own API — there is no summary table to fall behind the register, which
matters because a stale summary is worse than none: somebody will act on it.

## Your worklist

The platform computes a great deal: outstanding attestation signatures, monitors
past their cadence, overlays whose window has elapsed, debt approaching its
expiry, documents that have gone stale, findings past their remediation date.

A control nobody is told about is a control that operates when somebody happens
to look. So the same computation drives a list.

### Work is computed, not assigned

**There is no task table.** Every item is derived from the same state the rest of
the platform reads. That has three consequences worth stating:

- It **cannot go stale.** Sign the attestation and the item disappears, because
  the item *was* the outstanding signature.
- It **cannot disagree with the register.** A task table is a second source of
  truth about what is outstanding, and it would be wrong within a week.
- It **cannot accumulate orphans.** Complete something by another route — the
  API, a script, another person — and nothing is left behind to be closed by
  hand.

The same principle as [document staleness](/help/documentation) and
[overlay expiry](/help/monitoring): compute it, do not remember it.

### It is filtered to what you can actually do

An item appears on your list only if you hold the permission it needs, and only
if the model is inside your
[scope](/help/approval-and-attestation#scope).

Attestation goes further: you are shown *your role's* outstanding signature and
not somebody else's. A model owner sees `model_owner` outstanding; the risk
manager's signature is somebody else's work.

A list of work you cannot act on is a list you learn to ignore — and ignoring
the list is how the control stops operating. The count of everything else is
still shown, so nothing is hidden:

> 3 item(s) you can act on; 5 more are outstanding for other roles.

### What lands on it

| Kind | Appears when |
|---|---|
| **Attestation** | a required role's signature is outstanding |
| **Attestation renewal** | an attestation has lapsed, or is about to |
| **Approval** | a record has been submitted and is waiting on the second line |
| **Draft** | a model has no version, so it cannot be submitted |
| **Finding** | blocking, or past its remediation date |
| **Monitor** | its cadence has elapsed without an evaluation |
| **Overlay** | its window elapsed, its magnitude is unmeasured, or it has become persistent |
| **Debt** | a baseline gap is unplanned or approaching expiry |
| **Document** | it has gone stale relative to the register |

Ordering is **overdue, then due, then open** — and a low-severity finding with
months left deliberately does not appear at all, because it is *not yet worth
anyone's attention*. A worklist that shows everything shows nothing.

One further detail: a subsystem that is unavailable or refusing does not blank
the list. Its items are skipped, the reason is logged, and everything else still
appears.

## Bringing an existing estate in

### The problem this exists for

Adversarial review of this design found one omission — **finding C-5** — judged
more dangerous than any error in it:

> On import day, 1,200 existing models arrive with no evidence graph, no feature
> contracts, no reproducible runs, and documentation in Word files. Every gate
> fails. Every dashboard is red. Every KRI breaches. The model risk office
> concludes the platform is broken; developers conclude it blocks them; the
> programme dies in month seven.

A platform can be technically correct and organisationally unusable, and this is
how.

### The answer is not to lower the gates

It is to make the register **honest about what it does not know**.

A baselined model is in the inventory, tiered, and governed *going forward* — and
it carries explicit, dated **debt** for every piece of evidence it does not have.

> **Existing use is not blocked. Change is.**

That sentence is the whole policy, and it is in the code path rather than in a
slogan: warrant resolution never inspects a model's lifecycle state, so a
baselined model resolves normally. Its *next material change* goes through the
full path — submit, approve, attest — because `baselined` is one of the three
mutable states and `submit` accepts it as a source.

### Debt is not breach

This distinction is preserved on every view, and it is the reason the register
stays believable.

A Tier 1 model that arrived last week with no validation history, and a Tier 1
model that missed its scheduled validation, are completely different situations.
A dashboard that renders them the same colour is one the model risk office stops
believing within a month.

| | Debt | Breach |
|---|---|---|
| What it means | we know this is missing and when it will be fixed | a control that should have operated did not |
| Raises a finding | no | yes |
| Blocks | nothing | warrant resolution, alias promotion |
| Becomes the other | **yes** — at its expiry | — |

Debt expires by tier, and the shipped position is 18 months for Tier 1, 30 for
Tier 2, and 36 for Tiers 3 and 4 — counted as months of thirty days rather than
calendar months. Past that date, debt stops being debt. It raises a finding, and
a finding can block. The intent is that the expiry is a board decision; today the
values are constants in the code rather than a configuration key, so changing
them is a change to the platform.

### Gaps are computed, not declared

The obvious design lets whoever imports a model declare its gaps. That design
produces a register in which every imported model has exactly two gaps, because
declaring a third is work and nobody is checking.

So MAYA works out what is missing from the register itself. Thirteen gaps,
published at `GET /api/v1/baseline/gaps`:

| Gap | Materiality |
|---|---|
| no accountable owner | Critical |
| no version — nothing pinned, nothing digested | Critical |
| no risk tier — the depth of control is undecided | Critical |
| no declared purpose — no approved use to check against | High |
| no artifact digest — what runs cannot be checked against what was approved | High |
| no operating contract — no stated assumptions | High |
| no validation episode | High |
| no monitors — degradation would not be detected | High |
| never attested | High |
| no model development document on file | High |
| no feature contract — serving is not pinned | Medium |
| no compiled documentation | Medium |
| no document accepted by a second person | Medium |

An importer cannot under-declare, and does not have to know the list.

### Importing

```bash
POST /api/v1/baseline/imports
{
  "source": "legacy-inventory-2026-01.csv",
  "models": [
    {"urn": "maya://model/legacy.pd.corporate", "name": "Corporate PD",
     "owner": "person/j.okafor", "legal_entity": "LE-US-01",
     "purpose": "PD for corporate lending", "domain": "credit", "tier": 1}
  ]
}
```

One bad row does not stop the batch. 1,199 models must not fail because of one,
so a failure is recorded against that model — with its URN and the reason — and
the import continues:

```json
{"models": 1199, "debt_items": 8412,
 "skipped": [{"urn": "…", "reason": "already in the register"}],
 "detail": "1199 model(s) baselined carrying 8412 debt item(s). These are
            governed going forward: existing use is not blocked, the next
            material change is."}
```

### Debt closes by itself

A debt item is a claim that something is missing, and the register can tell
whether it still is:

```bash
POST /api/v1/baseline/reconcile?urn=maya://model/legacy.pd.corporate
# → {"closed": [...], "breached": [], "remaining": 5,
#    "detail": "3 item(s) closed because the evidence arrived; 0 passed their
#               expiry"}
```

Nobody marks an item done. It closes because the evidence is there — which means
the burn-down chart is a **measurement** rather than a self-report. Reconcile is
idempotent and safe on a schedule: it only makes the stored position agree with
what the register can already see.

### The number a programme is judged on

```bash
GET /api/v1/baseline
# → {"models_baselined": 1199, "debt_raised": 8412, "debt_closed": 3106,
#    "debt_breached": 12, "burn_down": 0.369,
#    "detail": "3106 of 8412 baseline debt items closed (37%); 12 expired into
#               breaches"}
```

Not *how many models are compliant* — on day one, none of them are, and saying so
loudly is what kills the programme. **Is the debt going down.**

## The scheduler

An attestation that lapsed on Tuesday is visible on Wednesday to whoever opens
the model page, and invisible to everybody else. The scheduler takes conditions
the platform *already* computes and turns them into things that are **recorded** —
a finding, a state change, an evidence entry. After this, a lapsed attestation
raises a finding, and a finding can block.

### The five jobs

| Job | Records |
|---|---|
| `attestation.lapsed` | a High finding for a model in force on an attestation past its validity |
| `monitoring.stalled` | a Medium finding for a monitor past three times its cadence |
| `overlays.expire` | closes overlays whose approved window has elapsed |
| `debt.reconcile` | closes baseline debt whose evidence arrived; expires what is overdue |
| `findings.overdue` | a High finding that an agreed remediation window was missed |

Two are worth explaining.

**`monitoring.stalled`** exists because *a monitor that is not running looks
exactly like a monitor that is passing*. The platform cannot evaluate one for you
— that needs data it does not hold — but it can say that nobody has. A monitor a
day late is a batch that ran late; one at three times its cadence is a control
that has stopped operating, and that is what gets recorded.

**`findings.overdue`** does **not** raise the original finding's severity. That
would rewrite what a validator concluded. It records a *separate* finding that
the agreed remediation window was missed — a different failure, often belonging
to a different person. It also declines to escalate its own escalations.

### Everything is idempotent

Run a job twice and nothing more happens than running it once. That is not an
optimisation, it is a requirement:

> A schedule that must not be run twice is a schedule that will be, and the first
> duplicate run will be at three in the morning.

So the jobs check before they raise. The same lapsed attestation produces one
finding however many times the scheduler passes over it.

### MAYA does not insist on owning the clock

The same reasoning that keeps the platform out of model execution applies here. A
governance platform that must be running for a bank's schedule to advance is a
platform whose outage is a governance outage.

So **a run is an ordinary authenticated call**:

```bash
curl -u svc/scheduler:… -X POST localhost:5006/api/v1/scheduler/run \
  -H 'Content-Type: application/json' -d '{}'          # all jobs

curl … -d '{"jobs": ["debt.reconcile"]}'               # or just one
```

cron, a Kubernetes CronJob, an Airflow DAG or a person pressing a button are all
equally supported and produce **identical results**. That equivalence holds only
because the jobs are idempotent and derive their own work from the register.

An in-process loop is offered as a convenience so a fresh deployment does
something sensible without anyone wiring up a scheduler first:

```yaml
scheduler:
  loop:
    enabled: false        # off by default
    interval_seconds: 3600
```

It waits a full interval before its first pass, and will not run more often than
once a minute however it is configured. It is off by default because two replicas
both running it is two runs — harmless, since the jobs are idempotent, but
wasteful and confusing in a log. For more than one replica, use cron against the
endpoint.

### One broken job does not stop the others

The failure mode of a scheduler is a single broken job silently preventing four
working ones, and the symptom is *nothing happening* — which looks exactly like
nothing needing to happen.

Each job is run in isolation. A failure is caught, logged, recorded against that
job, and the pass continues:

```json
{"ran": 5, "failed": 1, "detail": "5 job(s) ran, 1 failed: debt.reconcile"}
```

### It reports on itself

A scheduler nobody notices has stopped is the same problem as a monitor nobody
notices has stopped, one level up. So `/health/ready` carries its state, and
`GET /api/v1/scheduler` and `GET /api/v1/scheduler/history` report what has run:

```json
{"status": "ready",
 "scheduler": {"jobs": 5, "ever_run": 5, "last_run_at": 1767225600.0,
               "hours_since": 1.0, "failing": [],
               "detail": "last ran 1.0 hours ago"}}
```

Deliberately **informational**: a stopped scheduler is worth knowing about and is
not a reason to take the node out of service. Readiness fails on a broken
evidence chain, and on nothing else.

### The run history is a record, not a queue

`scheduled_run` records what ran and what it did. It is not a work queue and
nothing reads it to decide what to do next — every job derives its own work from
the register. Deleting every row would change nothing about the next run.
