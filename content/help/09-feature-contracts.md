---
title: Feature contracts
slug: feature-contracts
section: Features
order: 90
icon: link-45deg
summary: Pinning a model version to exact feature view versions — and the silent failure that this design exists to make impossible.
audience: Engineers
---

# Feature contracts

## The failure mode

A model is trained against a feature view. Six months later the view is
recomputed — a source system changed, a bug was fixed, a definition was
sharpened. The table is updated in place.

The model now scores against different numbers than it was trained on. Nothing
alerts. The contract digest still matches, because the contract named the *view*,
not a version of it. Every monitor is green, because the monitors compare today's
scores to yesterday's and the change was gradual.

This was found in adversarial review as **finding C-2**, and it is the reason for
the design below.

## A version is a serving namespace

Each materialisation writes to its **own Delta path**:

```
features/customer/sb_financials/v1
features/customer/sb_financials/v2
```

Publishing v2 does not touch a single byte that v1 serves. There is no "latest"
and no in-place update, because the mechanism that makes the failure possible is
simply absent.

## Contracts pin exact versions

```bash
POST /api/v1/feature-contracts
{
  "model_version_id": "01a06a...",
  "items": [{"view": "sb_financials", "version": 1}]
}
```

The contract records the resolved namespace for each item and a digest over the
whole binding. Ask what a model version must read:

```bash
GET /api/v1/feature-contracts/{model_version_id}/namespaces
→ {"sb_financials": "features/customer/sb_financials/v1"}
```

Serving reads that namespace. Law **L-17** compares what serving *must* read
against what it *did* read, which turns "the model used the right features" from
an assumption into a check.

Binding to a version that does not exist is refused:

```
'sb_financials' has no version 3
```

## Retirement is guarded

You cannot delete a namespace something still depends on:

```bash
GET /api/v1/feature-views/sb_financials/versions/1/retirable
→ {"retirable": false, "consumers": ["01a06a..."]}
```

Storage costs money, so old versions will eventually be retired — but the
decision needs to know who breaks. This makes that answerable in one call
instead of a search across pipelines.

## The cost, stated honestly

This design trades storage for correctness. A view materialised weekly for two
years is 104 namespaces, and they are not deduplicated.

That is a real cost and it is the right trade for governed features: the
alternative saves disk and reintroduces exactly the silent failure the design
exists to prevent. Retirement is how the cost is managed, and the guard above is
what makes retirement safe rather than hopeful.
