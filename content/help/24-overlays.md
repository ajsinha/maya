---
title: Post-model adjustments
slug: overlays
section: Assurance
order: 138
icon: sliders
summary: Overlays with an end date, a measured size, an independent approver — and the rule that an overlay renewed past its limit is a model defect, not a management judgement.
audience: Model risk, Finance
---

# Post-model adjustments

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

## The rule that matters

> An overlay renewed again and again is evidence that **the model is wrong**, not
> that the overlay is needed.

Past the renewal limit, the register raises a finding against the model:

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

## Four rules, each from a way overlays go wrong

**An overlay must be time-boxed.** An adjustment with no end date is a model
change nobody versioned, and it will still be running when the people who
approved it have left. A window longer than the configured maximum is refused —
propose a shorter one and renew it, so the adjustment is re-examined rather than
forgotten.

**The proposer may not approve.** An adjustment one person can both propose and
approve is a preference, not a control. This binds administrators too.

**Renewal requires a measurement.** You may not extend an adjustment whose size
you have not measured this period:

```json
{"error": "unmeasured",
 "detail": "this overlay has never been measured, so there is nothing to renew
            on the basis of"}
```

*"We still need the overlay"* and *"the overlay is £180,000, 18% of the
provision"* are different statements, and only the second can be challenged.

**The owner may not renew.** Renewal is the point at which somebody independent
asks whether the model should be fixed instead.

## The four kinds

| Kind | Means |
|---|---|
| `parameter` | an input or coefficient is overridden before the model runs |
| `output` | the model's answer is adjusted after it has produced one |
| `exclusion` | a population the model is not trusted on is carved out |
| `judgemental` | an expert addition for a risk the model cannot see |

## Reading the register

The interesting output is not the list. It is:

**Persistence** — renewals against the limit. Renewals rather than age, because
age alone punishes an overlay correctly given a long window, while a short one
renewed five times is the one that has quietly become part of the model.

**Materiality** — magnitude relative to the model's *own* output. An overlay of
£180,000 means nothing until you know whether the model produced £1m or £1bn.

**Trend** — a shrinking overlay is the model catching up; a growing one is the
model falling further behind, and the register says so.

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

## Working with one

```bash
# the owner proposes, saying what the model is getting wrong
POST /api/v1/overlays
{"urn": "…", "name": "SME sector uplift", "kind": "output",
 "rationale": "The model under-predicts hospitality default post-2025; this adds
               the shortfall observed in outcomes analysis.",
 "owner": "person/j.okafor"}

# somebody else approves, and the clock starts
POST /api/v1/overlays/{id}/approve

# its size is measured every period
POST /api/v1/overlays/{id}/measure
{"period": "2026-Q1", "base_value": 1000000.0, "adjusted_value": 1180000.0}

# renewal, by somebody who is not the owner, on the basis of that measurement
POST /api/v1/overlays/{id}/renew?period=2026-Q1
```

## The outcome to aim at

```bash
POST /api/v1/overlays/{id}/close
{"status": "absorbed", "reason": "built into version 3.3.0 and validated"}
```

`absorbed` means the adjustment stopped being an overlay because the model now
does it. That is the ending a well-run overlay has — not renewal into
perpetuity, and not quiet expiry, but the model being corrected.

## Expiry is computed

An overlay past its window is expired whether or not anything has run to notice.
There is a sweep that makes the stored status agree with the computed one, but
nothing depends on the sweep having run — the same principle as
[document staleness](/help/documentation).

## In the documentation

Overlays appear in every compiled model development document and Annex IV pack.
A post-model adjustment is part of the number the model produces, so a document
that omits them describes a model nobody runs.
