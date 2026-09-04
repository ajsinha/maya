---
title: Features and the two clocks
slug: features-and-two-clocks
section: Features
order: 70
icon: clock-history
summary: Why every feature row carries both when a fact was true and when you learned it — and why a store with one clock silently corrupts every backtest built on it.
audience: Engineers, Data scientists
---

# Features and the two clocks

## The failure this prevents

A model scores 0.47 AUC in development and 0.31 in production. The usual
conclusion is that it degraded. Usually it did not: **it was never trained on the
data it is now being served.**

The mechanism is almost always the same. A borrower files Q1 financials on 31
March. They land in the warehouse on 20 May. In August the figures are
**restated** downward after an audit. The warehouse now holds one row: the
restated one, stamped 31 March.

Train a model in September on "what was true as of 31 March" and it learns from
the restated figure — a number nobody could have known in March. The backtest is
measuring the model's ability to use information from the future. In production
that information does not exist, and the performance evaporates.

## Two clocks, always

Every feature row in MAYA carries both:

| Column | Meaning |
|---|---|
| `event_ts` | **Valid time** — when the fact was true in the world |
| `ingest_ts` | **Transaction time** — when the platform learned it |

The restatement above is *two rows*, not an update:

```json
{"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 1.20}
{"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0, "dscr": 0.40}
```

Same valid time. Different transaction times. Nothing was overwritten, so both
questions remain answerable:

- *What was true on 31 March?* → depends when you ask.
- *What did we know on 20 May?* → 1.20.
- *What do we know now?* → 0.40.

A store with one clock can answer only the third, and will answer it to a
question that asked the second.

## Materialisation refuses rows without both

```bash
POST /api/v1/feature-views/sb_financials/materialise
```

A row missing either clock is refused:

```
row is missing 'ingest_ts'; feature rows carry two clocks —
event_ts (when it was true) and ingest_ts (when we learned it)
```

This is deliberately unhelpful to whoever is in a hurry. The alternative —
defaulting `ingest_ts` to now — produces a store that looks fine and is
silently wrong, and the wrongness surfaces months later as unexplained model
decay.

## Defining a feature

```json
{
  "name": "dscr",
  "entity": "customer",
  "dtype": "float",
  "description": "Debt service coverage ratio, trailing twelve months",
  "business_definition": "EBITDA divided by scheduled debt service",
  "owner": "person/d.raman",
  "source_system": "FIN-DW",
  "sensitivity": "internal",
  "pii": false,
  "protected_basis": false,
  "proxy_risk": "none"
}
```

**business_definition** is separate from `description` on purpose. One is for
the engineer reading the column; the other is the definition a validator or an
examiner will hold you to.

**protected_basis** and **proxy_risk** are how fair-lending exposure becomes
queryable. A feature like `zip3` is not a protected basis, but its proxy risk is
high, and being able to ask "which models in the estate read a high-proxy-risk
feature" is the difference between a fair-lending review that takes a day and
one that takes a quarter.

## Duplicate detection at creation time

Feature sprawl is what makes a large store unusable — the fourth
`customer_income_v2_final` is a discovery problem, not a storage problem. So
near-duplicates surface when a feature is defined, while renaming is still
cheap:

```bash
GET /api/v1/features?similar_to=...
```

The similarity is token overlap, deliberately not embeddings: it has to be fast
enough to run on every keystroke of a definition form and explainable enough
that a steward can see *why* two features were called alike.

## Next

- [Point-in-time assembly](/help/point-in-time-assembly) — using the two clocks correctly.
- [Feature contracts](/help/feature-contracts) — pinning what serving reads.
