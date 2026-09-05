---
title: Features, end to end
slug: features-end-to-end
section: The platform
order: 40
icon: clock-history
summary: One borrower, one figure, restated in August. Follow that single row through definition, two clocks, a pinned contract and an assembly, and every rule in the feature platform turns out to be a consequence of the operator that reads it.
audience: Data scientists, Engineers
---

# Features, end to end

Here is the whole tutorial in three lines of data.

```csv
entity_id,event_ts,ingest_ts,dscr,revenue_ttm,months_on_book
C1,100,110,1.20,5.0,18
C1,100,900,0.40,3.0,18
C2,100,110,2.10,9.0,42
```

Look at `C1`. **Two rows, the same `event_ts`, different `ingest_ts`.** The Q1
debt-service figure was filed in March and revised downwards in August after an
audit. Nothing was overwritten.

A decision made in May saw `1.20`. A training set assembled today, about that
May decision, must also see `1.20` — or the model is being taught with an answer
nobody had. A dashboard built today should see `0.40`, because it is asking a
different question.

One store, two answers, no contradiction. Everything below is machinery for
making that true and provable.

---

## 1 · Define the feature, not the column

A feature is a governed object: an entity, a type, an owner and a definition
somebody can be held to.

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' -d '{
  "name": "dscr",
  "entity": "customer",
  "dtype": "numeric",
  "description": "Debt service coverage ratio, trailing twelve months",
  "business_definition": "EBITDA divided by scheduled debt service",
  "owner": "person/d.raman",
  "source_system": "FIN-DW",
  "sensitivity": "internal",
  "pii": false,
  "protected_basis": false,
  "proxy_risk": "none"}'
```

`business_definition` is separate from `description` deliberately: one is for
the engineer reading the column, the other is the definition a validator will
hold you to.

`protected_basis` and `proxy_risk` are what make fair-lending exposure
**queryable**. `zip3` is not a protected basis and its proxy risk is high, and
being able to ask *which models read a high-proxy-risk feature* is the
difference between a review that takes a day and one that takes a quarter.

The response also carries `possible_duplicates` — features whose name or
description is close to yours. It does not refuse; it says what already exists,
because the second `dscr` in a bank is defined by somebody who could not find
the first.

---

## 2 · A view, and both clocks

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_financials", "entity": "customer", "owner": "person/d.raman",
  "features": ["dscr", "revenue_ttm", "months_on_book"],
  "description": "Small-business financial statement features"}'
```

Naming an undefined feature is refused, with the names.

Then the values. Small batches inline:

```bash
curl -u d.raman:pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/materialise \
  -H 'Content-Type: application/json' -d '{"rows": [
  {"entity_id": "C1", "event_ts": 100, "ingest_ts": 110,
   "dscr": 1.20, "revenue_ttm": 5.0, "months_on_book": 18},
  {"entity_id": "C1", "event_ts": 100, "ingest_ts": 900,
   "dscr": 0.40, "revenue_ttm": 3.0, "months_on_book": 18},
  {"entity_id": "C2", "event_ts": 100, "ingest_ts": 110,
   "dscr": 2.10, "revenue_ttm": 9.0, "months_on_book": 42}]}'
```

Real ones as a file — CSV, NDJSON, Parquet or Arrow, streamed a batch at a time
so peak memory is one batch rather than one dataset:

```bash
curl -u d.raman:pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/data \
  -H 'Content-Type: text/csv' --data-binary @financials.csv
```

```python
maya.features.load("sb_financials", "financials.csv")
```

Omit either clock and the row is refused (`feature_refused`, 409):

```
row is missing 'ingest_ts'; feature rows carry two clocks — event_ts (when it
was true) and ingest_ts (when we learned it)
```

That is deliberately unhelpful to whoever is in a hurry. Defaulting `ingest_ts`
to now produces a store that looks fine and is silently wrong, and the wrongness
surfaces months later as unexplained model decay.

The response says which **version** you created:

```json
{"version": 1, "delta_version": 0, "row_count": 3,
 "features": ["dscr", "months_on_book", "revenue_ttm"],
 "quality_report": {"dscr": {"null_rate": 0.0, "distinct": 3}}}
```

The whole upload becomes one view version, because a version is what a
featureset pins and half a version is not something anybody can pin. Version 1
is its own Delta namespace, `features/customer/sb_financials/v1`; publishing v2
later does not touch a byte that v1 serves.

---

## 3 · The read, as a named operator

Everything so far is storage. This is the part that makes it governance.

```
AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                { r ∈ R : r.event ≤ ℓ  ∧  r.ingest ≤ min(ℓ, a) }
```

`ℓ` is the label time — when the decision was made. `a` is the assembly's
`as_of` — when we are asking. Both bounds are there because they refuse
different things: `ℓ` is what the model could have known when the decision was
made, `a` is what the platform could have known when the set was built.

Applied to `C1`, three reads:

| Assembled with | `dscr` | Why |
|---|---|---|
| `label_ts=500`, `as_of=500` | **1.20** | the restatement had not arrived |
| `label_ts=500`, `as_of=999` | **1.20** | it *still* had not arrived, by `ℓ` |
| `label_ts=950`, `as_of=999` | **0.40** | by then it had |
| `label_ts=50`, `as_of=999` | *nothing* | no fact was true by `t=50` |

A single-clock store gives `0.40` for all of them, and the first two are lies.

Four properties hold, and each is asserted in `tests/test_laws.py` under `L-10`
rather than argued in prose:

| | |
|---|---|
| **Idempotent** | reading the result again returns it |
| **Commutes with projection** | admissibility is decided on the clocks alone, so reading fewer columns cannot change which row wins |
| **Monotone in `a`** | a later `as_of` can only widen what is admissible; nothing knowable stops being knowable |
| **Saturating at `ℓ`** | **the reproducibility guarantee** |

The fourth is the one to carry away. Because the ingest bound is `min(ℓ, a)`,
**every `a ≥ ℓ` gives the same answer.** Rows 1 and 2 of that table are the same
number for that reason, and they would be the same number in ten years.

Without the `min`, a re-run would quietly *improve* on the original — which is
the least useful kind of reproducibility, because the numbers then agree with
nothing, including themselves. That is the concrete case the two clocks exist
for: a Q1 figure revised in August must not reach a row labelled in May, and
must reach a row labelled in September.

The bound was once `a` alone, and back-filled alignment made the leak concrete:
a value first observed in April, carried back onto a March grid point, arrives
carrying April's ingest stamp and was admitted into a March training row.

---

## 4 · Pin the contract

Which view version a model version reads is a fact, and a fact that has to be
written down before it can be checked.

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
```

```json
{"namespaces": {"sb_financials": "features/customer/sb_financials/v1"}}
```

Law **L-17** compares that against what serving *did* read. Without the pin,
*the model used the right features* is an assumption; with it, it is a
comparison. Half of L-17 exists: this side computes what must be read. The other
half needs an online store, and MAYA does not have one. Saying so is better
than a law that reads as enforced and is not — see
[features and two clocks](/help/features-and-two-clocks).

---

## 5 · Assemble a training set

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/training-sets \
  -H 'Content-Type: application/json' -d '{
  "name": "sb_pd_2025h2",
  "spine": [{"entity_id": "C1", "label_ts": 500, "label": 1},
            {"entity_id": "C2", "label_ts": 500, "label": 0}],
  "views": [{"view": "sb_financials", "version": 1}],
  "as_of": 999,
  "valid_time_bound": true,
  "transaction_time_bound": true}'
```

Both bounds are required. Set either to `false` and the request is **rejected
before any data is read**:

```
422 — assembly lacks a bound on transaction_time; without both,
leakage cannot be excluded
```

The spine is yours: which entities, at which label times, with which outcomes.
The views are the columns. `as_of` is the moment you are asking from. The
operator does the rest.

---

## 6 · Read the report before the numbers

```json
{"name": "sb_pd_2025h2", "row_count": 2, "as_of": 999,
 "pit_verified": true,
 "pit_report": {"passed": true, "layer": "sampled", "checked": 2,
                "violations": [], "leakage": [],
                "detail": "…"}}
```

Three layers, and they are not three versions of one check:

1. **A static gate.** Both bounds present, or nothing is read at all.
2. **An independent recomputation** of a stratified sample, by a different code
   path. Strata span label period, entity and label value, because a leak
   confined to a rare high-value segment is exactly where uniform sampling fails
   and where the damage is greatest.
3. **Leakage heuristics** over the assembled rows.

The second matters most. Verification that reuses the assembly path lets a bug
hide behind itself, and *we checked it with the same code that produced it* is
not a check.

The snapshot is a named, digested, immutable Delta table, written at a recorded
Delta version — so a replay reads the same **bytes** rather than the same paths.
A fit warrant binds to it, which is how *the model was trained on 2025H2*
becomes checkable:

```json
"data": {"inputs": [{"name": "training_set", "binding": "dataset_snapshot",
                     "snapshot": "snapshots/sb_pd_2025h2"}]}
```

Bind training data to a plain `delta_table` instead and the warrant is refused
by **L-W3**: a source that cannot be read as-of cannot be shown not to have
leaked. Only three bindings can — `feature_namespace`, `featureset` and
`dataset_snapshot` — and of those, only a `dataset_snapshot` is bounded by
construction. The other two are live sources, so **L-W9** additionally requires
the warrant to bound the read in both clocks.

---

## 7 · Has the ground moved?

A featureset version resolves to the same bytes by construction. The
neighbouring question — *has anything underneath it been written to since* — is
the one a reviewer actually asks before comparing two runs, and it has its own
endpoint:

```bash
curl -u a.mehta:pw \
  localhost:5006/api/v1/featuresets/sb_core/versions/1/restatements
```

Your pinned read is unaffected. That is what the pin is for. But if the answer
is yes, then somebody who dropped the pin would now see something else, and the
comparison you were about to make is between two different worlds.

---

## What this buys

Every rule on this page is a consequence of one operator, and each of them
refuses a specific way of being wrong:

- Two clocks on every row, or the operator has nothing to bound.
- A version per upload, or there is no `R` to read from.
- A pin per binding, or `R` changes underneath you.
- Both bounds on an assembly, or `min(ℓ, a)` is not computed.
- An independent recomputation, or the check is the thing it checks.

Next: [training a model, end to end](/tutorials/train-a-model), where a fit
consumes one of these snapshots and has to say so; or [the whole
path](/tutorials/the-whole-path), which puts featuresets, models and their
dependencies together.
