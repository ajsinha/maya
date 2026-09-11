---
title: Monitoring and post-model adjustments
slug: monitoring
section: Assurance
order: 100
icon: activity
summary: Two registers, one purpose — degradation becomes a refusal rather than a chart. Drift you can measure today, performance you cannot measure for a year and the bookkeeping that keeps it honest, telemetry the platform holds, results computed elsewhere that MAYA judges rather than trusts, one health score whose band is not its arithmetic, and the overlay register whose central rule is that a permanent adjustment is a model defect.
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

There is also **no cluster**, and there will not be one — see *When the estate
will not fit in one process* below. What moves off the platform is the scan;
the arithmetic from statistics to metric, the reference, the threshold and the
comparison all stay here, which is why a distributed result can be replayed and
an external observation cannot.

Nor does anything evaluate a due monitor on your behalf. The cadence is recorded
and queryable, and something outside has to call `evaluate` — though it no
longer has to carry the data to do it. What the platform *does* do is notice
that nobody has: past three times its cadence, the `monitoring.stalled` job
raises a Medium finding titled *Monitoring has stopped*, because a monitor that
is not running looks exactly like a monitor that is passing.

## Numbers you already compute somewhere else

You almost certainly have monitoring already: an MLOps platform computing PSI
nightly, a quant notebook that produces the AUC the committee actually looks at,
a vendor dashboard for the vendor's own model. MAYA does not ask you to run any
of it twice.

Post the result to `POST /monitors/{id}/ingest` with the value, the window it
covers, the population size and **what computed it**. There is no `passed`
field. That is not an oversight and it will not be added.

> **MAYA takes the number and refuses the verdict.** The threshold on the
> monitor is the one your second line set. The comparison against it happens
> here. A system that could push its own metric *and* its own pass mark would
> be marking its own homework — which is what every "send us your metrics" API
> quietly permits.

An ingested number that breaches opens a breach, raises a finding and can block
warrant resolution, exactly as one MAYA computed would. Taking the number and
not acting on it would be filing rather than monitoring.

### What you give up, said out loud

An external observation **cannot be replayed**. MAYA does not hold the population
it was computed over and cannot re-derive the value from the evidence chain. The
register's record is that this system asserted this number over this window; the
assurance behind it is that system's, not MAYA's.

`GET /monitoring-provenance` reports the split for a monitor or for the whole
estate. Read it occasionally. An estate where most of the numbers cannot be
reproduced by the platform holding them is a real finding about the monitoring
programme — and one that is invisible if both kinds of number print the same.

## One number for a model

The **Model health** screen scores each model out of 100 from six things the
register already holds: performance monitors, drift monitors, feed health,
overlay reliance, validation currency and open findings.

Read two things before you read the score.

**Coverage.** A model with no monitors, no validation and no findings has
nothing bad to say about it, and most health scores read that as health. Here
the components that could not be measured are left out of the denominator and
named, and the share of the weight that *was* measurable sits beside the number.
**92 at 30% coverage is a model nobody has looked at, not a healthy one.**

**The band.** The band is not the score rounded into a colour. It is the score
capped by conditions no amount of good news elsewhere may outweigh — a lapsed
validation, a Critical finding past its date, an active overlay nobody has
measured. A model can score 84 and band `poor`, and the page shows both.

> Where the band is worse than the arithmetic, **the gap is the finding**. That
> row is a model whose numbers look fine and whose governance does not, which is
> the single most common way a health score misleads a committee.

The `health.declining` job raises a Medium finding on a `poor` band — but only
where at least half the weight was measurable. A model scoring badly because
nothing about it can be measured needs monitors rather than a finding about its
health, and `monitoring.stalled` already says so.

## Champion and challenger

`GET /champion-challenger` compares two versions on the monitors they share,
paired window by window. It answers two questions separately and will not
collapse them:

- **Significant** — is the difference bigger than the disagreement between
  windows? With enough windows, everything is.
- **Material** — is it big enough to be worth a revalidation and a
  redeployment? That threshold is yours, declared in the units of the test.

A challenger that is significant and immaterial is the ordinary result of a long
comparison, and the ordinary reason to leave the champion where it is.

Below five paired windows nothing is tested, and the refusal says why: three
windows agreeing is a coin landing the same way three times. Above five, the
p-value is an exact sign-flip permutation up to fourteen windows and a normal
approximation beyond it — and the answer tells you which, because a p-value
whose method is unstated is one nobody can reproduce.

> **It will never recommend promotion.** MAYA does not decide which model your
> bank uses, and promoting a version is a second-line approval. The strongest
> recommendation here is *open a validation of the challenger* — which is the
> thing this comparison is evidence for, not a substitute for it.

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

## When the estate will not fit in one process

`evaluate_from_telemetry` reads the cohort into memory. That is fine at hundreds
of models and a few million rows a night, and it is not fine at an estate-wide
sweep over billions.

MAYA does not solve that by running a cluster. Owning one would put the
governance platform on the compute path for every model in the bank, which is
the coupling the whole architecture avoids — a register that is down should stop
issuing warrants, not stop a hundred teams' nightly batch.

What moves is **the scan, and only the scan**. PSI, AUC, Gini and KS are
functions of *sufficient statistics* rather than of rows: bin counts against the
reference's edges, a rank sum and two class counts, bounded quantile buckets.
All of those add across partitions. So a job on whatever the firm already runs
computes them where the data is, a few hundred numbers come back, and **MAYA
computes the metric and compares it to the threshold your second line set**.

That is deliberately different from an [external
observation](#numbers-you-already-compute-somewhere-else). Both refuse the other system's
verdict. Only this one can be **replayed** — the statistics are what was
recorded, and the metric is recomputed from them whenever anybody asks.

**How to run one.** `GET /api/v1/monitors/{id}/distributed-plan` is the
contract: the statistics to return, the window, the partitioning, and — for a
drift monitor — the reference bin edges with a digest of the sample they came
from. Compute against *those* edges. PSI against edges somebody else chose is a
different measurement that prints the same, and a submission quoting a different
digest is refused.

Then `POST /api/v1/monitors/{id}/distributed-submit`. Every problem is reported
at once and the whole submission is refused rather than part of it, because a
metric computed over the partitions that happened to be well-formed is a
measurement of a population nobody chose.

**Two things to watch.** For AUC and Gini the plan sets
`global_ranking_required`: a rank sum over one partition's rows is a rank sum in
the *wrong ordering*, and summing those gives a number that looks like an AUC
and is not, with nothing in the result to show it — so the job has to rank
across the whole window and say that it did. And a statistic that does not
decompose is refused by name: Hosmer-Lemeshow's deciles depend on the global
distribution, so per-partition deciles are a different partitioning of a
different population.

**What MAYA cannot check, and says so.** Whether the job read the population it
claims. A `WHERE` clause that quietly excluded a segment produces statistics
that are arithmetically perfect and describe the wrong population. The predicate
and the row count are recorded, and the result says the population is
**attested** rather than observed.

