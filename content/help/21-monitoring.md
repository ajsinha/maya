---
title: Monitoring
slug: monitoring
section: Assurance
order: 135
icon: activity
summary: Drift you can measure today, performance you cannot measure for a year, and the loop that turns a breach into a refusal instead of a chart.
audience: Model risk, Engineers
---

# Monitoring

Monitoring here is not a dashboard. A breach raises a **finding**; a blocking
finding refuses warrant resolution and alias promotion. So a model whose
discrimination has collapsed becomes unservable *mechanically*, rather than
because somebody was looking at the right chart on the right morning.

## Two kinds of question, and when each can be answered

Monitors are grouped by what they can be computed from, because that determines
**when** they can be computed at all.

| Kind | Compares | Available |
|---|---|---|
| `input_drift` | today's feature distribution against the development one | immediately |
| `score_drift` | today's score distribution against the development one | immediately |
| `performance` | predictions against outcomes | only once outcomes exist |
| `calibration` | predicted rates against observed rates | only once outcomes exist |

Each kind admits only the tests that can answer it. Pairing `input_drift` with
`discrimination.gini` is refused **when the monitor is defined**, not at three in
the morning when the batch fails:

```json
{"error": "test_not_admissible",
 "detail": "'discrimination.gini' cannot answer a 'input_drift' question",
 "remediation": "for input_drift, use one of stability.psi"}
```

## Delayed labels — the reason most performance monitoring is wrong

A 12-month PD model scores a borrower today. Whether they default is not known
for twelve months.

So a performance number computed on this month's cohort is computed from the
outcomes that arrived early — and the outcomes that arrive early are the *fast*
defaults. The result is not noisy. It is **biased**, and publishing it beside
honestly-computed numbers is how a monitoring dashboard stops being trustworthy
in a way nobody notices.

The fix is bookkeeping, not statistics. A cohort has a maturity date:

```
scored_at ────────── label_delay ──────────▶ matures_at
                                                  │
                    immature: refused             ▼  measurable
```

A performance monitor **must** declare its delay:

```json
{"kind": "performance", "test_key": "discrimination.gini",
 "threshold": {"min": 0.40}, "label_delay_days": 365}
```

Omit it and the definition is refused. Evaluate over an immature cohort and the
evaluation is refused, with the date it becomes measurable:

```json
{"error": "cohort_immature",
 "detail": "no outcomes have matured yet — 0 of 400 rows have matured
            (365 day outcome window)",
 "remediation": "wait for the outcome window to close; the earliest maturity is 2027-02-14"}
```

Maturity is decided **per row**, not per batch. A monitoring window usually spans
several days, and the older end of it may be measurable while the newer end is
not. Discarding the whole window because part of it is immature throws away the
only data that could have been used — so the observation records how much of the
cohort it actually measured:

```
0.61 meets the minimum of 0.4 — 20 of 70 rows have matured (365 day outcome window)
```

## Breaches escalate with persistence

One breach is a data point. The same monitor breaching for the *n*th consecutive
evaluation is a condition, and it is raised as one:

```yaml
breach_severity: Medium     # where it starts
escalate_after: 3           # rise one level every 3 consecutive breaches
```

Medium → High at 3 → Critical at 6, and it stops there. Critical blocks by
default, which is the point at which the model stops being servable.

## Recovery closes the breach, not the finding

When a metric comes back inside its threshold, the **breach** is resolved. The
**finding stays open**.

That asymmetry is deliberate. A metric recovering is not evidence that anybody
understood what moved it, and closing the finding automatically would erase the
obligation to find out. Closing it needs a person, a verifier who is not the
owner, and closure evidence — see [Findings](/help/findings).

## Defining and running a monitor

```bash
POST /api/v1/monitors
{
  "urn": "maya://model/credit.pd.smallbiz",
  "name": "origination discrimination",
  "kind": "performance",
  "test_key": "discrimination.gini",
  "threshold": {"min": 0.40},
  "label_delay_days": 365,
  "cadence_days": 30,
  "breach_severity": "High",
  "escalate_after": 3,
  "owner": "person/j.okafor"
}

POST /api/v1/monitors/{id}/evaluate
{"rows": [{"scored_at": 1767225600, "score": 0.31, "label": 1}, ...]}
```

`monitor:evaluate` is granted to the `operator` role as well as to owners, so the
batch runner can evaluate on a schedule and decide nothing else.

## What is not built

Stated plainly: MAYA does not ingest inference telemetry for you. You pass the
scored rows in. There is no streaming collector, no sampling strategy and no
automatic reference-window management, and the scheduler that would run
`monitors.due()` on a cadence is not written — the cadence is recorded and
queryable, but something outside has to call it.
