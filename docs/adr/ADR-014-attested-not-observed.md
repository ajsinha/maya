# ADR-014 — Attested, not observed

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context

Five capabilities built at different times reached the same wall from different
directions:

| | What it wanted | Why MAYA cannot see it |
|---|---|---|
| External monitoring | a PSI computed nightly elsewhere | MAYA does not run the model |
| Training–serving agreement (`L-17`) | which namespaces serving read | [04 §7](../04-architecture.md): MAYA is not on the serving path |
| Cost attribution | what a model costs | MAYA does not run the model |
| Tiering facts | the exposure a model carries | MAYA holds no general ledger |
| Distributed monitoring | a metric over billions of rows | the estate does not fit in this process |

Each had the same two tempting answers, and both are wrong in the same way.

**Compute it anyway.** Multiply a price somebody typed by a call count nobody
observed. Estimate exposure from a peer cohort. The output is a number, printed
in the same typeface as a measurement, and nothing downstream can tell them
apart.

**Refuse it.** Decline to register a model until somebody produces a ledger
extract. That produces an *unregistered* model, which is strictly worse than a
tiered-from-a-guess one.

## Decision

**Take the fact attested, mark it, and never compute one.**

A fact arrives from a named source, over a stated period, with a reference
somebody can check it against. MAYA records it, attributes it from what the
register already holds, and **reports the attestation as an attestation**.

Four rules follow, and each is what makes the pattern honest rather than merely
convenient.

**The mark travels.** `sourced` / `asserted` / `stale` on a tiering fact;
`attributed` / `unattributed` on a cost line; `maya` / `external` on a monitoring
observation. A register that could not distinguish a claim from a measurement
would present both with the same confidence.

**What was NOT attested is the headline.** The number a cost report exists to
produce is not the total — a bill has that — but the **share nobody attributed**.
The number a fact-sourcing report exists to produce is the share of tiering that
rests on somebody's word. Both are findings about a *programme*, and both are
invisible the moment a claim and a measurement print identically.

**The verdict stays here.** External monitoring takes the number and refuses the
`passed` flag: the threshold is the register's and the comparison is the
register's, because a system that could mark its own homework is the failure
every *push your metrics to us* API has. Distributed evaluation goes further and
takes only **sufficient statistics**, so MAYA computes the metric itself — which
is why that one result can be *replayed* and an external observation cannot.

**A reference is required, not requested.** *Finance said so* cannot be checked
by whoever relies on it a year later, and the whole value of an attestation is
that somebody can go and look.

## Consequences

- **+** MAYA acquires no standing credentials. It holds no connection to a
  general ledger, an ML platform, a cloud bill or a serving path — and a
  governance register that could read all four is one that has to be trusted with
  considerably more than it needs.
- **+** The gap becomes **countable**. *Sixty percent of exposures are asserted*
  is a sentence a firm can act on. It does not exist in a system that computes.
- **+** Every one of these was buildable without a component MAYA does not own.
- **−** **MAYA cannot detect a lie.** A source can be named and wrong, and
  nothing here checks. What it can do is make the claim *falsifiable* — named,
  referenced, dated — so somebody else can.
- **−** An attested fact is often **not replayable**. An external observation
  cannot be recomputed, because MAYA holds neither the population nor the
  derivation, and that is a genuine loss of assurance stated on the observation
  rather than discovered by an auditor.
- **−** It puts work on the firm. Somebody has to produce the extract, and a
  platform that fetched would not have asked.

## Where it applies

`core/monitoring/external.py` · `core/features/serving.py` ·
`core/estate/cost.py` · `core/risk/sourcing.py` ·
`core/monitoring/distributed.py` · and, in the same spirit,
`core/discovery/connectors.py` and `core/discovery/contract.py`, which take
another system's *document* rather than reading its API.

[18 — The register's edges](../18-the-registers-edges.md) is the longer account.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
