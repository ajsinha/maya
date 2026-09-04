---
title: The scheduler
slug: scheduler
section: Reference
order: 165
icon: clock
summary: Where a computed condition becomes a recorded consequence — five idempotent jobs, runnable from cron, a loop, or a person, with identical results.
audience: Operators, Model risk
---

# The scheduler

## The hole it closes

Almost everything in this platform is **derived rather than remembered** — expiry,
staleness, maturity, debt. That is the right design, and it has exactly one hole
in it:

> A condition that is true, and that nobody has looked at, has had no
> consequence.

An attestation that lapsed on Tuesday is visible on Wednesday to whoever opens
the model page, and invisible to everybody else. The scheduler takes conditions
the platform *already* computes and turns them into things that are **recorded** —
a finding, a state change, an evidence entry. After this, a lapsed attestation
raises a finding, and a finding can block.

## The five jobs

| Job | Records |
|---|---|
| `attestation.lapsed` | a finding for a model in force on an attestation past its validity |
| `monitoring.stalled` | a finding for a monitor far past its cadence |
| `overlays.expire` | closes overlays whose approved window has elapsed |
| `debt.reconcile` | closes baseline debt whose evidence arrived; expires what is overdue |
| `findings.overdue` | records that a finding passed its remediation window |

Two are worth explaining.

**`monitoring.stalled`** exists because *a monitor that is not running looks
exactly like a monitor that is passing*. The platform cannot evaluate one for you
— that needs data it does not hold — but it can say that nobody has. A monitor a
day late is a batch that ran late; one at three times its cadence is a control
that has stopped operating, and that is what gets recorded.

**`findings.overdue`** does **not** raise the original finding's severity. That
would rewrite what a validator concluded. It records a *separate* finding that
the agreed remediation window was missed — a different failure, often belonging
to a different person.

## Everything is idempotent

Run a job twice and nothing more happens than running it once. That is not an
optimisation, it is a requirement:

> A schedule that must not be run twice is a schedule that will be, and the first
> duplicate run will be at three in the morning.

So the jobs check before they raise. The same lapsed attestation produces one
finding however many times the scheduler passes over it.

## MAYA does not insist on owning the clock

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

It is off by default because two replicas both running it is two runs — harmless,
since the jobs are idempotent, but wasteful and confusing in a log. For more than
one replica, use cron against the endpoint.

## One broken job does not stop the others

The failure mode of a scheduler is a single broken job silently preventing four
working ones, and the symptom is *nothing happening* — which looks exactly like
nothing needing to happen.

Each job is run in isolation. A failure is caught, logged, recorded against that
job, and the pass continues:

```json
{"ran": 5, "failed": 1, "detail": "5 job(s) ran, 1 failed: debt.reconcile"}
```

## It reports on itself

A scheduler nobody notices has stopped is the same problem as a monitor nobody
notices has stopped, one level up. So `/health/ready` carries its state:

```json
{"status": "ready",
 "scheduler": {"jobs": 5, "ever_run": 5, "last_run_at": 1767225600.0,
               "hours_since": 1.0, "failing": [],
               "detail": "last ran 1.0 hours ago"}}
```

Deliberately **informational**: a stopped scheduler is worth knowing about and is
not a reason to take the node out of service. Readiness fails on a broken
evidence chain, and on nothing else.

## The run history is a record, not a queue

`scheduled_run` records what ran and what it did. It is not a work queue and
nothing reads it to decide what to do next — every job derives its own work from
the register. Deleting every row would change nothing about the next run.
