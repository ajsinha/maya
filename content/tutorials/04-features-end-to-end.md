---
title: Features, end to end
slug: features-end-to-end
section: The platform
order: 40
icon: clock-history
summary: Define features, materialise them with both clocks, pin a contract, and assemble a training set that is refused if it cannot be shown correct.
audience: Data scientists, Engineers
---

# Features, end to end

## 1. Define the features

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
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
  "proxy_risk": "none"}'
```

`business_definition` is separate from `description` on purpose: one is for the
engineer reading the column, the other is the definition a validator will hold
you to.

`protected_basis` and `proxy_risk` are what make fair-lending exposure
queryable. `zip3` is not a protected basis, but its proxy risk is high — and
being able to ask "which models read a high-proxy-risk feature" is the
difference between a review that takes a day and one that takes a quarter.

## 2. Create a view

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_financials", "entity": "customer", "owner": "person/d.raman",
  "features": ["dscr", "revenue_ttm", "months_on_book"],
  "description": "Small-business financial statement features"}'
```

Naming an undefined feature is refused, with the names.

## 3. Materialise — with both clocks

```bash
curl -u d.raman:pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/materialise \
  -H 'Content-Type: application/json' -d '{"rows": [
  {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0,
   "dscr": 1.20, "revenue_ttm": 5.0, "months_on_book": 18.0},
  {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0,
   "dscr": 0.40, "revenue_ttm": 3.0, "months_on_book": 18.0},
  {"entity_id": "C2", "event_ts": 100.0, "ingest_ts": 110.0,
   "dscr": 2.10, "revenue_ttm": 9.0, "months_on_book": 42.0}]}'
```

Look carefully at C1. **Two rows, same `event_ts`, different `ingest_ts`.** That
is a restatement: the Q1 figure filed on 31 March, then revised downward in
August after an audit. Nothing was overwritten, so both questions stay
answerable — see [the two clocks](/help/features-and-two-clocks).

Omit either clock and the row is refused. That is deliberately unhelpful to
whoever is in a hurry: defaulting `ingest_ts` to now produces a store that looks
fine and is silently wrong, and the wrongness surfaces months later as
unexplained model decay.

The response tells you which **version** you created:

```json
{"version": 1, "delta_version": 0, "row_count": 3,
 "quality_report": {"dscr": {"null_rate": 0.0, "distinct": 3}}}
```

Version 1 is its own Delta namespace, `features/customer/sb_financials/v1`.
Publishing v2 later does not touch a byte that v1 serves.

## 4. Pin the contract

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/feature-contracts \
  -H 'Content-Type: application/json' -d '{
  "model_version_id": "01a06a0a079c652f925c727c181a",
  "items": [{"view": "sb_financials", "version": 1}]}'
```

Now ask what serving *must* read:

```bash
curl -u a.mehta:pw \
  localhost:5006/api/v1/feature-contracts/01a06a0a079c652f925c727c181a/namespaces
# → {"sb_financials": "features/customer/sb_financials/v1"}
```

Law L-17 compares that against what serving *did* read. Without the pin, "the
model used the right features" is an assumption; with it, it is a check.

## 5. Assemble a training set

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/training-sets \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_pd_2025h2",
  "spine": [{"entity_id": "C1", "label_ts": 500.0, "label": 1},
            {"entity_id": "C2", "label_ts": 500.0, "label": 0}],
  "views": [{"view": "sb_financials", "version": 1}],
  "as_of": 999.0,
  "valid_time_bound": true,
  "transaction_time_bound": true}'
```

Both bounds are required. Set either to `false` and the request is **rejected
before any data is read**:

```
assembly lacks a bound on transaction_time; without both, leakage
cannot be excluded
```

## What actually came out

For C1, assembled at `as_of=999`:

| Assembled with | `dscr` | Why |
|---|---|---|
| `label_ts=500, as_of=500` | **1.20** | the restatement had not arrived yet |
| `label_ts=500, as_of=999` | **0.40** | assembling today, we know the revision |
| `label_ts=50, as_of=999` | *nothing* | no fact was true by t=50 |

A single-clock store gives 0.40 for all three, and the first is a lie.

## 6. Read the report

```json
{"name": "sb_pd_2025h2", "row_count": 2, "pit_verified": true,
 "pit_report": {"static": {"passed": true},
                "sampled": {"checked": 2, "agreed": 2},
                "leakage": []}}
```

Three layers: a static gate, an **independent recomputation** by a different code
path, and leakage heuristics. The second matters most — verification that reuses
the assembly path lets a bug hide behind itself.

The snapshot is a named, digested, immutable Delta table. A `fit` warrant binds
to it, which is how "the model was trained on 2025H2" becomes checkable:

```json
"data": {"inputs": [{"name": "training_set", "binding": "dataset_snapshot",
                     "snapshot": "snapshots/sb_pd_2025h2", "pit_verified": true}]}
```

Try binding training data to a plain `delta_table` and the warrant is refused by
grammar law **L-W3**: a source that cannot be read as-of cannot be shown not to
have leaked.
