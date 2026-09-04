---
title: Point-in-time assembly
slug: point-in-time-assembly
section: Features
order: 80
icon: hourglass-split
summary: The rule that makes a training set honest, the three layers that verify it, and why an assembly is refused rather than warned about.
audience: Data scientists
---

# Point-in-time assembly

## The rule

For a training row with label timestamp `label_ts`, assembled as of `as_of`, the
admissible feature value is:

> the **latest** fact that was **true by `label_ts`** and **known by `as_of`**

In code that is one predicate:

```python
eligible = [r for r in records
            if r[VALID_TIME] <= label_ts and r[INGEST_TIME] <= as_of]
return max(eligible, key=lambda r: (r[VALID_TIME], r[INGEST_TIME]))
```

Both bounds are required. Drop the valid-time bound and you use facts from after
the label — classic leakage. Drop the transaction-time bound and you use the
*restated* version of a fact that, at the time, said something else.

## Assemblies are refused, not warned

```bash
POST /api/v1/training-sets
{
  "name": "sb_pd_2025h2",
  "spine": [{"entity_id": "C1", "label_ts": 500.0, "label": 1}],
  "views": [{"view": "sb_financials", "version": 1}],
  "as_of": 999.0,
  "valid_time_bound": true,
  "transaction_time_bound": true
}
```

Set either bound to `false` and the request is **rejected** before any data is
read:

```
assembly rejected: transaction_time_bound is false, so the assembly would
use facts restated after as_of
```

A warning would be ignored. Everyone under deadline pressure ignores warnings,
and the resulting dataset is indistinguishable from a correct one until the
model reaches production.

## Three layers of verification

Being refused for the obvious mistake is not enough — the assembly could still
be wrong for a subtle reason. So a completed assembly is checked three ways.

**Layer 1 — static gate.** Are both bounds declared? Is `as_of` present? Is the
spine well-formed? Cheap, and catches the common error.

**Layer 2 — independent recomputation.** A sample of assembled rows is
recomputed by a *different code path* — a bitemporal `as_of` read against Delta,
rather than the in-memory join the assembly used — and the two must agree. This
matters: verification that reuses the assembly path lets a bug hide behind
itself.

**Layer 3 — leakage detection.** Heuristics over the assembled frame looking for
columns suspiciously correlated with the label, which is what an accidental
future-fact join looks like from the outside.

The `pit_report` on the resulting snapshot records all three, and
`pit_verified` is `false` if any failed. The snapshot is still written — you may
need to inspect it — but it is marked, and its status travels with it.

## A worked example

Given the restatement from [the two clocks](/help/features-and-two-clocks):

```
C1 @ event_ts=100, ingest_ts=110  →  dscr 1.20
C1 @ event_ts=100, ingest_ts=900  →  dscr 0.40   (the restatement)
```

| Assembled with | Result | Why |
|---|---|---|
| `label_ts=500, as_of=500` | **1.20** | The restatement had not arrived yet |
| `label_ts=500, as_of=999` | **0.40** | Assembling today, we know the restated figure |
| `label_ts=50,  as_of=999` | *nothing* | No fact was true by t=50 |

The first row is what a September backtest of a March decision must use. The
second is what a fresh model trained today should use. A single-clock store
gives 0.40 for both, and the first is a lie.

## Snapshots

An assembly produces a **dataset snapshot**: a named, digested, immutable Delta
table with its PIT report attached. A validation episode can pin one, and a
replay can be run against it — which is what turns "the model was validated on
2025H2 data" into a checkable claim.
