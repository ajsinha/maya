---
title: The estate and what needs doing
slug: estate-and-worklist
section: Assurance
order: 130
icon: list-check
summary: A computed condition nobody has looked at has had no consequence. Four mechanisms close that — a summary of the estate as it is, a worklist derived rather than assigned, eleven idempotent jobs that record what has become true, and a digest that reaches out — plus the compliance debt an imported estate carries honestly.
audience: Everyone, Model risk, Programme, Operators
---

# The estate and what needs doing

Almost everything in this platform is **derived rather than remembered**. Expiry,
staleness, cohort maturity, outstanding signatures and missing evidence are all
computed from the register when somebody asks, because a second table recording
the same facts would be wrong within a week.

That design has exactly one hole in it:

> A condition that is true, and that nobody has looked at, has had no
> consequence.

Four mechanisms close it, and they are four different acts on the same
computation — never four computations.

| | Turns a condition into | |
|---|---|---|
| **The estate summary** | something visible | the dashboard, above the register |
| **The worklist** | somebody's work | filtered to what *you* can act on |
| **The scheduler** | a record | a finding, a state change, an evidence entry |
| **Notifications** | a message | one digest per person, suppressed when nothing moved |

The last three all read `WorkList` or the same services the dashboard reads.
Two views of one derivation, never two derivations.

## The estate summary

Above the register, the numbers a risk committee actually asks for, in four
groups that each answer one question.

**Is the record complete?** Models registered, and how many are *in force* —
attested, not merely present — with a breakdown by tier and by state, a count of
the untiered, and the blocking findings standing across the estate.

**Is anything degrading, and would we know?** Open breaches, and how many models
are **unmonitored**. The second is often the more alarming number, because a
model with no monitor cannot breach.

**How much of this is the model and how much is us?** The aggregate overlay
adjustment, with a persistent count beside it.

**Where did the estate start?** A baseline debt burn-down: closed against
raised, kept apart from breach.

All of it is derived, and it is rendered on the dashboard rather than served as
its own API — there is no summary table to fall behind the register, which
matters because a stale summary is worse than none: somebody will act on it.

## Your worklist

The platform computes a great deal: outstanding attestation signatures, monitors
past their cadence, overlays whose window has elapsed, debt approaching its
expiry, documents that have gone stale, findings past their remediation date,
findings nobody has accepted.

A control nobody is told about is a control that operates when somebody happens
to look. So the same computation drives a list.

### Work is computed, not assigned

**There is no task table.** Every item is derived from the same state the rest
of the platform reads. Three consequences worth stating:

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

| Kind | Appears when | Needs |
|---|---|---|
| **Attestation** | a required role's signature is outstanding | `model:attest` |
| **Attestation renewal** | an attestation has lapsed, or expires within 30 days | `model:attest` |
| **Approval** | a record has been submitted and is waiting on the second line | `model:approve` |
| **Draft** | a model has no version, so it cannot be submitted | `version:create` |
| **Finding** | blocking, or past its remediation date | `finding:close` |
| **Finding acknowledgement** | an escalated finding whose owner never accepted it | `finding:acknowledge` |
| **Monitor** | its cadence has elapsed without an evaluation | `monitor:evaluate` |
| **Overlay** | its window elapsed, its magnitude is unmeasured, or it has become persistent | `overlay:approve` / `overlay:measure` |
| **Debt** | a baseline gap is unplanned or approaching expiry | `baseline:plan` |
| **Document** | it has gone stale relative to the register | `document:compile` |

Ordering is **overdue, then due, then open**, where *due* means within thirty
days. A low-severity finding with months left deliberately does not appear at
all, because it is *not yet worth anyone's attention*. A worklist that shows
everything shows nothing.

**Debt is one item per model, not one per gap.** A freshly baselined model has a
gap for every baseline check, and listing them individually buries every other
kind of work under a wall of rows that all say the same thing. The item names
the count, how many have no dated plan, the worst materiality and the earliest
expiry — which is what somebody deciding where to start actually needs.

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

A baselined model is in the inventory, tiered, and governed *going forward* —
and it carries explicit, dated **debt** for every piece of evidence it does not
have.

> **Existing use is not blocked. Change is.**

That sentence is the whole policy, and it is in the code path rather than in a
slogan: warrant resolution never inspects a model's lifecycle state, so a
baselined model resolves normally. Its *next material change* goes through the
full path — submit, approve, attest — because `baselined` is one of the mutable
states and `submit` accepts it as a source.

### Debt is not breach

This distinction is preserved on every view, and it is the reason the register
stays believable. A Tier 1 model that arrived last week with no validation
history, and a Tier 1 model that missed its scheduled validation, are completely
different situations. A dashboard that renders them the same colour is one the
model risk office stops believing within a month.

| | Debt | Breach |
|---|---|---|
| What it means | we know this is missing and when it will be fixed | a control that should have operated did not |
| Raises a finding | no | yes |
| Blocks | nothing | warrant resolution, alias promotion |
| Becomes the other | **yes** — at its expiry | — |

Debt expires by tier: 18 months for Tier 1, 30 for Tier 2, and 36 for Tiers 3
and 4 — counted as months of thirty days rather than calendar months. Past that
date, debt stops being debt. It raises a finding **at the gap's own
materiality**, which matters: `owner`, `version` and `tier` are Critical gaps,
and a Critical finding blocks by default. So an expired Tier 1 owner gap does
not just colour a chart — it stops the model being served.

The intent is that the expiry is a board decision; today the values are
constants in the code rather than a configuration key, so changing them is a
change to the platform.

### Gaps are computed, not declared

The obvious design lets whoever imports a model declare its gaps. That design
produces a register in which every imported model has exactly two gaps, because
declaring a third is work and nobody is checking.

So MAYA works out what is missing from the register itself — from the **same
state dictionary the document compiler reads**, which is why a gap cannot
disagree with what a compiled document would say. Thirteen gaps, published at
`GET /api/v1/baseline/gaps`:

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
POST /api/v1/baseline/imports        # needs baseline:import
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

Nobody marks an item done. It closes because the evidence is there — which makes
the burn-down chart a **measurement** rather than a self-report. Reconcile is
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

Not *how many models are compliant* — on day one, none of them are, and saying
so loudly is what kills the programme. **Is the debt going down.**

## The scheduler

An attestation that lapsed on Tuesday is visible on Wednesday to whoever opens
the model page, and invisible to everybody else. The scheduler takes conditions
the platform *already* computes and turns them into things that are
**recorded** — a finding, a state change, an evidence entry. After this, a
lapsed attestation raises a finding, and a finding can block.

### The eleven jobs

| Job | Records |
|---|---|
| `evidence.verify` | walks the whole evidence chain and moves the verification checkpoint |
| `notify.outstanding` | tells each person what is outstanding for them |
| `attestation.lapsed` | a High finding for a model in force on an attestation past its validity |
| `review.overdue` | a finding for a model past the review date its own tier set |
| `monitoring.stalled` | a Medium finding for a monitor far past its cadence |
| `overlays.expire` | closes overlays whose approved window has elapsed |
| `debt.reconcile` | closes baseline debt whose evidence arrived; expires what is overdue |
| `findings.overdue` | a High finding that an agreed remediation window was missed |
| `findings.unacknowledged` | a finding whose owner never accepted it |

Five are worth explaining.

**`evidence.verify`** exists because `/health/ready` verifies only what has
arrived since the last full walk — a readiness probe that re-hashed the whole
chain would get slower as the register grew, which is the wrong direction for a
probe. So the full walk has to be something that *happens* rather than something
somebody remembers. When it finds a break, **the checkpoint is not advanced**:
moving it past a break would bless the break.

**`review.overdue`** exists because the cadence was being computed and never
read. `TieringEngine` writes `next_review_due` onto every assessment — twelve
months at Tier 1, thirty-six at Tier 4 — and until this job existed, *nothing*
selected that column: no job, no screen, no endpoint. An estate could pass every
other control here while its Tier 1 models went four years unreviewed. It reads
the **latest** assessment only, because reassessing is what discharges the
obligation and an older row being overdue says nothing.

**`monitoring.stalled`** exists because *a monitor that is not running looks
exactly like a monitor that is passing*. The platform cannot evaluate one for
you — that needs data it does not hold — but it can say that nobody has. A
monitor a day late is a batch that ran late; one far past its cadence is a
control that has stopped operating.

**`findings.overdue`** does **not** raise the original finding's severity. That
would rewrite what a validator concluded. It records a *separate* finding that
the agreed remediation window was missed — a different failure, often belonging
to a different person. It also declines to escalate its own escalations.

**`findings.unacknowledged`** is where the reminder cycle ends. An unaccepted
finding sits on its owner's worklist and in the notification digest; when those
have been ignored, the fact is recorded as a finding of its own. Reminders that
are ignored have to end somewhere other than in more reminders.

### Everything is idempotent

Run a job twice and nothing more happens than running it once. That is not an
optimisation, it is a requirement:

> A schedule that must not be run twice is a schedule that will be, and the
> first duplicate run will be at three in the morning.

So the jobs check before they raise. The same lapsed attestation produces one
finding however many times the scheduler passes over it.

### MAYA does not insist on owning the clock

The same reasoning that keeps the platform out of model execution applies here.
A governance platform that must be running for a bank's schedule to advance is a
platform whose outage is a governance outage.

So **a run is an ordinary authenticated call** needing `scheduler:run`:

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
once a minute however it is configured. It is off by default because two
replicas both running it is two runs — harmless, since the jobs are idempotent,
but wasteful and confusing in a log. For more than one replica, use cron against
the endpoint.

### One broken job does not stop the others

The failure mode of a scheduler is a single broken job silently preventing seven
working ones, and the symptom is *nothing happening* — which looks exactly like
nothing needing to happen.

Each job runs in isolation. A failure is caught, logged, recorded against that
job, and the pass continues:

```json
{"ran": 8, "failed": 1, "detail": "8 job(s) ran, 1 failed: debt.reconcile"}
```

### It reports on itself

A scheduler nobody notices has stopped is the same problem as a monitor nobody
notices has stopped, one level up. So `/health/ready` carries its state, and
`GET /api/v1/scheduler` and `GET /api/v1/scheduler/history` report what has run:

```json
{"status": "ready",
 "scheduler": {"jobs": 8, "ever_run": 8, "last_run_at": 1767225600.0,
               "hours_since": 1.0, "failing": [],
               "detail": "last ran 1.0 hours ago"}}
```

Deliberately **informational**: a stopped scheduler is worth knowing about and
is not a reason to take the node out of service. Readiness fails on a broken
evidence chain, and on nothing else.

The run history is a **record, not a queue**. Nothing reads it to decide what to
do next — every job derives its own work from the register. Deleting every row
would change nothing about the next run.

## Being told, rather than having to look

The worklist reaches whoever logs in and looks at it. An item nobody happens to
look at simply sits there, which is a control that operates only when somebody
remembers it. `notify.outstanding` reaches out, and it is an ordinary
authenticated call like every other scheduled act here:

```bash
curl -su you:… localhost:5006/api/v1/notifications/preview      # what you would get
curl -su svc/scheduler:… -X POST localhost:5006/api/v1/notifications/run \
     -H 'Content-Type: application/json' -d '{"dry_run": true}'
```

**A digest, not a firehose.** One message per person per run, summarising what
is outstanding *for them*, from the same `WorkList` call the dashboard makes. A
message per finding is how somebody starts filtering the sender, at which point
the platform has made itself invisible while appearing diligent. Somebody with
nothing outstanding is not messaged at all.

**Silence when nothing has changed.** Each delivery records the digest of the
work it described — *the work, not the prose* — and an unchanged worklist is
**suppressed** until the quiet period has passed:

```json
{"state": "suppressed",
 "detail": "the same outstanding work was notified 3.2 hours ago; a message that
            repeats yesterday's is a message somebody filters"}
```

**Escalation is by role, not by hierarchy.** MAYA does not know who reports to
whom and should not pretend to. What it does know is that an item overdue and
unactioned for a week has stopped being only its owner's problem, so the model
risk manager is told as well — and never about items already on their own list,
because that is noise. It is the same role, and the same reasoning, that a
finding's own [escalation](/help/validation) names.

### Channels

| Channel | What it needs |
|---|---|
| `log` | nothing; always available |
| `webhook` | a URL — Slack, Teams, a ticketing system, anything that accepts JSON |
| `email` | an SMTP relay |

Neither the webhook nor the email channel is a dependency: both use the standard
library. And **nothing but the log is enabled by default**, because an instance
that quietly needed an SMTP relay to work would fail in a way nobody could
diagnose from the outside.

```yaml
notifications:
  channel: log                 # log | webhook | email
  quiet_hours: 24
  escalate_after_days: 7
```

**A failed delivery is recorded**, and appends evidence against the principal
who should have been told. Silence about a failed send is how somebody concludes
they were never told — which is worse than not having sent at all, because then
they would at least have known.

`GET /api/v1/notifications` says which channels actually work and whether
anything is reaching anybody, and leads with failures when there are any.
`GET /api/v1/notifications/history` keeps the failures alongside the successes.
