---
title: Monitoring and post-model adjustments
slug: monitoring
section: Assurance
order: 100
icon: activity
summary: Two registers, one purpose — degradation becomes a refusal rather than a chart. Drift you can measure today, performance you cannot measure for a year and the bookkeeping that keeps it honest, telemetry the platform holds, and the overlay register whose central rule is that a permanent adjustment is a model defect.
audience: Model risk, Engineers, Finance
---

# Monitoring and post-model adjustments

A model in production drifts away from the one that was approved, and there are
two ways to notice. One is to measure it, which is monitoring. The other is that
somebody is quietly correcting its output, which is an overlay — and an overlay
that never goes away is the same information arriving by a different route.

Both registers exist so that the drift becomes a **finding** rather than a chart
nobody opened. And both are shaped by a limit on *when* a question can be
answered: a monitor by the outcome window, an overlay by how long an adjustment
may stand before somebody has to ask whether the model should be fixed instead.

## Monitoring is not a dashboard

A breach raises a finding; a blocking finding refuses warrant resolution and
alias promotion. So a model whose discrimination has collapsed becomes
unservable *mechanically*, rather than because somebody was looking at the right
chart on the right morning.

### Two kinds of question, and when each can be answered

Monitors are grouped by what they can be computed from, because that determines
**when** they can be computed at all.

| Kind | Compares | Available | Admissible tests |
|---|---|---|---|
| `input_drift` | today's feature distribution against the development one | immediately | `stability.psi` |
| `score_drift` | today's score distribution against the development one | immediately | `stability.psi` |
| `performance` | predictions against outcomes | once outcomes exist | `discrimination.auc`, `discrimination.gini`, `discrimination.ks`, `accuracy.rmse`, `accuracy.mae` |
| `calibration` | predicted rates against observed rates | once outcomes exist | `calibration.brier`, `calibration.expected_vs_actual` |

Each kind admits only the tests that can answer it. Pairing `input_drift` with
`discrimination.gini` is refused **when the monitor is defined**, not at three in
the morning when the batch fails:

```json
{"error": "test_not_admissible",
 "detail": "'discrimination.gini' cannot answer a 'input_drift' question",
 "remediation": "for input_drift, use one of stability.psi"}
```

A monitor with **no threshold** is refused for the same reason at the same
moment: one that can never breach monitors nothing.

There is exactly one drift statistic, `stability.psi`, and saying so is more
useful than implying a suite. Its reference and current windows are compared
**whole**. They were once truncated to a common length, which kept the oldest
slice of a window — precisely the part that has not drifted yet — and so
reported stability by construction.

### Delayed labels — the reason most performance monitoring is wrong

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

Both label-dependent kinds — `performance` and `calibration` — **must** declare
a delay:

```json
{"kind": "performance", "test_key": "discrimination.gini",
 "threshold": {"min": 0.40}, "label_delay_days": 365}
```

Omit it and the definition is refused as `label_delay_required`, with the
remediation naming the number: *for a 12-month PD model that is 365*. Evaluate
over a cohort in which *nothing* has matured and the evaluation is refused, with
the date it becomes measurable:

```json
{"error": "cohort_immature",
 "detail": "no outcomes have matured yet — 0 of 400 rows have matured
            (365 day outcome window)",
 "remediation": "wait for the outcome window to close; the earliest maturity is 2027-02-14"}
```

Maturity is decided **per row**, not per batch. A monitoring window usually
spans several days, and the older end of it may be measurable while the newer
end is not. Discarding the whole window because part of it is immature throws
away the only data that could have been used — so a partly-mature cohort is
measured over the part that matured, and the observation records how much that
was:

```
0.61 meets the minimum of 0.4 — 20 of 70 rows have matured (365 day outcome window)
```

### Breaches escalate with persistence

One breach is a data point. The same monitor breaching for the *n*th consecutive
evaluation is a condition, and it is raised as one:

```yaml
breach_severity: Medium     # where it starts
escalate_after: 3           # rise one level every 3 consecutive breaches
```

Medium → High at 3 → Critical at 6, and it stops there. Critical blocks by
default, which is the point at which the model stops being servable. The
consecutive count is read backwards from the latest observation until one that
passed, so a single good month resets it — which is correct, and is why the
finding does not reset with it.

### Recovery closes the breach, not the finding

When a metric comes back inside its threshold, the **breach** is resolved. The
**finding stays open**, and the evidence entry says so explicitly.

That asymmetry is deliberate. A metric recovering is not evidence that anybody
understood what moved it, and closing the finding automatically would erase the
obligation to find out. Closing it needs a person, a verifier who is not the
owner, and closure evidence — see
[Validation and findings](/help/validation#the-one-column).

### Defining and running a monitor

```bash
POST /api/v1/monitors                          # needs monitor:define
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

POST /api/v1/monitors/{id}/evaluate            # needs monitor:evaluate
{"rows": [{"scored_at": 1767225600, "score": 0.31, "label": 1}, ...]}
```

The two monitoring permissions are deliberately apart, and the roles show why.
`monitor:observe` — delivering rows — is held by the `service` role, the
identity a running engine authenticates as. `monitor:evaluate` — deciding
whether a monitor has breached — is held by the `operator` role and by model
owners. The principal that runs the model holds the population; it should be
able to hand it over without also being able to rule on it.

### Telemetry the platform holds

MAYA takes delivery of scored rows and outcomes, per model version, as two
streams.

| Stream | Every row must carry |
|---|---|
| `scores` | `entity_id`, `scored_at`, `score` |
| `outcomes` | `entity_id`, `label`, `label_ts` |

```bash
POST /api/v1/telemetry                         # needs monitor:observe
{"urn": "maya://model/credit.pd.smallbiz", "semver": "3.2.1",
 "stream": "scores", "sample_rate": 1.0,
 "rows": [{"entity_id": "B1", "scored_at": 1767225600, "score": 0.31}]}
```

Every row carries **two clocks**: its own valid-time stamp, which it must
supply, and an `ingest_ts` applied on arrival. A row missing its own timestamp
is refused as `malformed_row` rather than stamped with the batch's arrival time,
because *when this was scored* cannot be inferred from *when it turned up*. That
is what makes a read at `known_by=<last quarter's end>` return the population
last quarter saw, rather than the one this morning's redelivery produced.

**Ingestion is idempotent.** A batch carries the digest of its own rows, and a
digest already recorded is accepted and not written again — real collectors
deliver at least once, and a monitor that double-counted a redelivery would
report a population that never existed.

```bash
GET /api/v1/telemetry?urn=…&semver=…           # what one version has sent
GET /api/v1/telemetry/cohort?urn=…&semver=…&since=&until=&known_by=
```

**Scores and outcomes are joined when they are read, not when they arrive**, so
maturity is decided per row instead of assumed for a batch. A score with no
outcome yet comes back **unlabelled rather than dropped**: a join that silently
discarded the unlabelled would hand back a cohort that looks complete and is
not.

And a monitor can then be evaluated against what the platform already holds,
with nothing passed in:

```bash
POST /api/v1/monitors/{id}/evaluate-from-telemetry     # needs monitor:evaluate
{"since": …, "until": …, "reference_from": …, "reference_to": …}
```

It reads with `known_by` set to the end of the window, so a review of last
quarter sees what last quarter saw.

**Telemetry** in the navigation shows what every version has sent, ordered so
that a version which has stopped sending comes first, then one that never
started. That ordering is decided in the collector rather than in the page,
because which of those facts is the alarming one is a judgement about model risk
and not about layout — and a monitor evaluated over a stale window still returns
a number, describing a population nobody is producing any more.

### What is not built

There is no streaming collector and no automatic reference-window management.
Something outside still has to post the batches, and the reference window is
named on the evaluation rather than chosen for you.

Nor does anything evaluate a due monitor on your behalf. The cadence is recorded
and queryable, and something outside has to call `evaluate` — though it no
longer has to carry the data to do it. What the platform *does* do is notice
that nobody has: past three times its cadence, the `monitoring.stalled` job
raises a Medium finding titled *Monitoring has stopped*, because a monitor that
is not running looks exactly like a monitor that is passing.

## Post-model adjustments

An overlay is a human adjustment applied on top of a model's output: a
management add-on to an IFRS 9 provision, a haircut on a valuation, an exclusion
of a segment the model handles badly, an expert uplift for a risk the model
cannot see.

Every bank has them. Almost none can answer three questions about them in
aggregate:

1. **How large are they?**
2. **How long have they been running?**
3. **Which of them have quietly become permanent?**

The third is what this register exists for.

### The rule that matters

> An overlay renewed again and again is evidence that **the model is wrong**,
> not that the overlay is needed.

Past the renewal limit, the register raises a finding against the model — once,
not once per sweep:

```json
{"severity": "High",
 "title": "Persistent overlay: SME sector uplift (OVL-001)",
 "description": "renewed 3 times against a limit of 2; an overlay that keeps
   being renewed is evidence the model is wrong, not that the overlay is needed.
   A persistent overlay is an unversioned model change: either the model should
   be corrected, or the adjustment should be built into it and validated."}
```

The point at which a temporary adjustment stops being temporary should be a
threshold in a register, not a judgement nobody is ever asked to make. That is
how a "temporary" management adjustment reaches its fourth year.

```yaml
overlays:
  max_days: 180        # the longest a single window may run
  renewal_limit: 2     # renewals before persistence is a finding
```

### Four rules, each from a way overlays go wrong

**An overlay must be time-boxed.** An adjustment with no end date is a model
change nobody versioned, and it will still be running when the people who
approved it have left. A window longer than the configured maximum is refused as
`window_too_long` — propose a shorter one and renew it, so the adjustment is
re-examined rather than forgotten. The clock does not start until approval.

**The proposer may not approve.** An adjustment one person can both propose and
approve is a preference, not a control. The check compares who proposed it
against who is approving it, with no role exemption, so it binds administrators
too (`self_approval`).

**Renewal requires a measurement.** You may not extend an adjustment whose size
you have never measured:

```json
{"error": "unmeasured",
 "detail": "this overlay has never been measured, so there is nothing to renew
            on the basis of"}
```

Renew against a named period and the requirement sharpens: a measurement for
*that* period, or `period_unmeasured`. *"We still need the overlay"* and *"the
overlay is £180,000, 18% of the provision"* are different statements, and only
the second can be challenged.

**The owner may not renew** (`self_renewal`). Renewal is the point at which
somebody independent asks whether the model should be fixed instead. That
control was inert over HTTP until the identity comparison was made the same one
every other duties check uses — an exact string match let `person/j.okafor` and
`j.okafor` past each other.

### The four kinds

| Kind | Means |
|---|---|
| `parameter` | an input or coefficient is overridden before the model runs |
| `output` | the model's answer is adjusted after it has produced one |
| `exclusion` | a population the model is not trusted on is carved out |
| `judgemental` | an expert addition for a risk the model cannot see |

Each also declares a **direction** — `increase`, `decrease` or `either` — so an
adjustment that starts moving the other way is visible as a change of character
rather than as a smaller number.

### Reading the register

The interesting output is not the list. It is:

**Persistence** — renewals against the limit. Renewals rather than age, because
age alone punishes an overlay correctly given a long window, while a short one
renewed five times is the one that has quietly become part of the model.

**Materiality** — magnitude relative to the model's *own* output. An overlay of
£180,000 means nothing until you know whether the model produced £1m or £1bn;
past five per cent of the base it is flagged.

**Trend** — a shrinking overlay is the model catching up; a growing one is the
model falling further behind, and the register says which.

**Aggregate** — the number a risk committee actually asks for and almost never
gets: not "how many overlays", but *how much of this number is the model and how
much is us*.

```bash
GET /api/v1/overlays?urn=maya://model/credit.pd.smallbiz
# → {"active": 3, "persistent": 1, "aggregate_magnitude": 412000.0,
#    "unmeasured": 0, "expired_but_open": 0,
#    "detail": "3 active overlay(s) adjusting this model by 412,000.00 in
#               aggregate; 1 has outlived its renewal limit"}
```

### Working with one

```bash
# the owner proposes, saying what the model is getting wrong
POST /api/v1/overlays                                  # needs overlay:propose
{"urn": "…", "name": "SME sector uplift", "kind": "output",
 "direction": "increase",
 "rationale": "The model under-predicts hospitality default post-2025; this adds
               the shortfall observed in outcomes analysis.",
 "owner": "person/j.okafor"}

# somebody else approves, and the clock starts
POST /api/v1/overlays/{id}/approve?days=180            # needs overlay:approve

# its size is measured every period
POST /api/v1/overlays/{id}/measure                     # needs overlay:measure
{"period": "2026-Q1", "base_value": 1000000.0, "adjusted_value": 1180000.0}

# renewal, by somebody who is not the owner, on the basis of that measurement
POST /api/v1/overlays/{id}/renew?period=2026-Q1        # needs overlay:approve
```

A rationale is required at proposal (`rationale_required`), and one period may
be measured once (`already_measured`).

### The outcome to aim at

```bash
POST /api/v1/overlays/{id}/close
{"status": "absorbed", "reason": "built into version 3.3.0 and validated"}
```

`absorbed` means the adjustment stopped being an overlay because the model now
does it. That is the ending a well-run overlay has — not renewal into
perpetuity, and not quiet expiry, but the model being corrected. The other two
closures, `withdrawn` and `expired`, are recorded as what they are, and every
closure needs a reason.

### Expiry is computed

An overlay past its window is expired whether or not anything has run to notice.
The `overlays.expire` job sweeps to make the stored status agree with the
computed one, but nothing depends on the sweep having run.

### In the documentation

Overlays are a required section of every compiled model development document and
Annex IV pack. A post-model adjustment is part of the number the model produces,
so a document that omits them describes a model nobody runs. See
[Documentation](/help/documentation).
