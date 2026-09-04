---
title: Evidence and provenance
slug: evidence-and-provenance
section: Assurance
order: 140
icon: shield-check
summary: The append-only hash chain, what tamper detection actually buys you, and why provenance is computed over semirings rather than hand-rolled per question.
audience: Model risk, Audit
---

# Evidence and provenance

The slogan is *evidence, not assertion*. This is the machinery behind it.

## An append-only chain

Every governance act — a model registered, a version created, an alias moved, a
warrant issued, a finding closed — appends a node:

```json
{
  "seq": 47,
  "kind": "alias_moved",
  "subject_type": "model",
  "subject_id": "01a06a...",
  "payload": {"alias": "champion", "environment": "prod", "to": "3.2.1",
              "refinement": {"holds": true}, "variance": {"ok": true}},
  "actor": "person/j.okafor",
  "prev_hash": "sha256:...",
  "chain_hash": "sha256:..."
}
```

Each node's `chain_hash` covers its own content **and** its predecessor's hash.
Change any historical payload and every subsequent hash fails to reconcile.

```bash
GET /api/v1/evidence/chain
→ {"valid": true, "length": 47, "checked_at": ...}
```

`/health/ready` includes this check: a node with a broken evidence chain reports
**degraded** and is not ready, because the assurance claims it serves cannot be
trusted.

## What this does and does not prove

It proves **internal consistency**: nobody edited a row in place without the chain
noticing.

It does not prove the original claim was true. If a validator records a Gini of
0.61 that they never computed, the chain faithfully preserves a false statement.
That is what [reproducibility replay](/help/validation) is for — the chain
protects the record, replay checks the claim.

Sequence numbers are contiguous, so *deletion* is detectable too. A pure Merkle
DAG would not catch a removed leaf; this was **finding C-4** in adversarial review.

## Provenance over semirings

Once evidence is a graph, "why do we believe this?" becomes a computation over
it. Rather than writing a bespoke traversal per question, one traversal is
parameterised by a **semiring**:

| Semiring | Answers |
|---|---|
| Boolean | Is this claim supported at all? |
| Counting | How many independent derivations support it? |
| Why-provenance | Which minimal sets of sources support it? |
| Trust | What is the weakest link in the chain? |
| Cost | What would it cost to re-derive this? |
| Freshness | What is the staleness of the oldest input? |

Six questions, one graph walk, one definition of what "supported" means. Adding a
seventh question means adding a semiring, not another traversal that can disagree
with the first six.

**Citation soundness** falls out of the Boolean case: a document that cites
evidence nodes is sound exactly when evaluating its citation set over the Boolean
semiring yields true. That is the check behind "this validation report cites only
evidence that exists".

## Actors

Every node records an actor. `system` is used for platform-initiated acts;
anything a person did carries their identifier. This is what makes the chain
answer "who" as well as "what" and "when", which is the first question in any
incident review.
