---
title: Evidence, provenance and machine assistance
slug: evidence-and-provenance
section: Assurance
order: 110
icon: shield-check
summary: The append-only hash chain every governance act appends to, what tamper detection does and does not prove, why provenance is computed over semirings — and the rules that decide where the platform's own AI may act.
audience: Model risk, Audit, Everyone
---

# Evidence, provenance and machine assistance

The slogan is *evidence, not assertion*. This page is the machinery behind it,
and then the hardest case for it: claims produced by a machine, which are cheap
to generate and expensive to check.

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
  "recorded_by": "person/j.okafor",
  "parents": ["..."],
  "content_hash": "sha256:...",
  "prev_hash": "sha256:...",
  "chain_hash": "sha256:..."
}
```

Each node's `chain_hash` covers its own content **and** its predecessor's hash.
Change any historical payload and every subsequent hash fails to reconcile — the
verification distinguishes a `chain_hash mismatch` from a `prev_hash mismatch`
from a `sequence gap`, because those are three different accidents.

```bash
GET /api/v1/evidence/chain
→ {"valid": true, "length": 47, "checked_at": ...}
```

`/health/ready` includes this check: a node with a broken evidence chain reports
**degraded** and returns 503, because the assurance claims it serves cannot be
trusted. It is the only thing readiness fails on.

Sequence numbers are contiguous, so *deletion* is detectable too. A pure Merkle
DAG would not catch a removed leaf; this was **finding C-4** in adversarial
review.

Each node also records whether its payload contains personal data. That marker
exists because append-only evidence and a data-subject erasure request are
otherwise irreconcilable — finding **H-3**, and the reason for law **L-18**: the
chain is not a place to put personal data.

## What this does and does not prove

It proves **internal consistency**: nobody edited a row in place without the chain
noticing.

It does not prove the original claim was true. If a validator records a Gini of
0.61 that they never computed, the chain faithfully preserves a false statement.
That is what [reproducibility replay](/help/validation) is for — the chain
protects the record, replay checks the claim.

## Actors

Every node records who recorded it. `system` is used for platform-initiated acts;
anything a person did carries their identifier. This is what makes the chain
answer "who" as well as "what" and "when", which is the first question in any
incident review — and it is what
[segregation of duties](/help/approval-and-attestation#segregation-of-duties) is
computed from, rather than from a second table of who-did-what that could
disagree with it.

## Provenance over semirings

Once evidence is a graph, "why do we believe this?" becomes a computation over
it. Rather than writing a bespoke traversal per question, one memoised traversal
is parameterised by a **semiring**:

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

**Citation soundness** is the Boolean case: a document that cites evidence nodes
is sound exactly when evaluating its citation set over the Boolean semiring
yields true. That is the check behind "this validation report cites only evidence
that exists", and it is the same question a compiled document answers when it
reports its dangling citations.

## Machine assistance

The platform can hold machine-generated work. The organising question for where
it may act is not *is the model good enough*. It is:

> **Can a human check the output more cheaply than producing it?**

Where such a check exists, a language model can be wrong loudly and cheaply and
the system catches it. Where no check exists, it is wrong **quietly** — and in a
governance system quiet wrongness is the failure mode that matters.

That gives three tiers, and only two of them can exist here.

| Tier | Control | Registrable |
|---|---|---|
| **A — verified** | a formal property acts as an oracle; the check *is* the control | yes |
| **B — grounded** | every claim cites evidence, citations are verified, a person approves | yes |
| **C — advisory** | a person decides; AI never appears in the decision path | **no** |

### Why Tier C is not registrable

A capability whose output can be neither checked nor grounded is advisory, and
advisory AI is a person using a chat window — not something the platform runs.

Allowing it into the registry would mean allowing something into the registry
that will one day be wired into a decision path, because everything in a registry
eventually is. So the refusal is at registration, and it is checked before the
tier is even recognised as valid:

```json
{"error": "advisory_not_registrable",
 "detail": "a capability whose output can be neither checked nor grounded is
            advisory, and advisory AI is a person using a chat window",
 "remediation": "if the output can be checked, name the oracle and register it as
                 Tier A; if its claims can cite evidence, register it as Tier B"}
```

### Tier A — the oracles

An oracle is a predicate that decides whether a generated artifact is correct,
**mechanically, without asking the thing that generated it**. Very few tasks have
one, which is why the list is short:

| Oracle | Checks | Rests on |
|---|---|---|
| `warrant.conforms` | a generated warrant validates against the grammar | the warrant grammar |
| `contract.refines` | a proposed contract refines the incumbent (L-7) | the contract algebra |
| `schemas.substitutable` | proposed schemas satisfy variance (L-12) | the schema algebra |
| `test.registered` | a proposed validation test exists in the catalogue | the test catalogue |
| `citations.resolve` | every cited evidence node exists | the evidence graph |

Every one is backed by machinery that already exists for another reason, and that
is not a coincidence. A platform whose properties are formal enough to check a
*human's* work can check a *machine's*, and the same check serves both. An oracle
written specially to bless AI output would be an oracle nobody had reason to
trust.

A Tier A capability must name its oracle. *"We validate the output"* without
naming the check is the sentence that precedes every AI incident.

When the oracle fails, **nothing is recorded**. The check is the control.

### Tier B — the grounding gate

A Tier B output is a set of **claims**, each carrying the evidence it rests on.
The gate verifies every citation and then does the thing that makes it a gate
rather than a warning: it **removes** the claims that failed, and assembles the
published text from what survived.

Flagging them in place was considered and rejected. A document where the
unsupported sentences are marked is a document where the marks are what gets
skimmed past — and the sentence still reads as though the platform said it.

The rejected claims are kept separately on the generation, so a reviewer can see
what the model tried to assert and could not support. That is a far more useful
artifact than an annotated draft: it is the list of places the model was making
things up.

A claim citing **nothing** is not grounded — *the claim cites nothing, so nothing
supports it*. Uncited prose in a governance document is exactly what this gate
exists to stop, however true it happens to be.

### Nothing is evidence until a person attests it

A drafted generation carries no weight anywhere in the platform. Attestation is
the only transition that gives it any — and **the person who asked for the draft
cannot be the person who attests it**:

```json
{"error": "self_attestation",
 "remediation": "attestation is a person taking responsibility for machine output;
                 it must be somebody other than whoever asked for it"}
```

There is deliberately **no endpoint** that turns a generation into a governance
decision. The absence is the control, and the test that holds it in place reads
the OpenAPI document and asserts that no `/assist/` path contains `approve` or
`conclude`.

### Watching the watchers

Two measurements are taken that are not about the output at all.

**Edit distance** on attestation: how much the reviewer changed. The number means
little on its own; the *trend* is the point, which is why nothing is reported
until a reviewer has attested at least four times.

```bash
GET /api/v1/assist/reviewers/a.mehta
# → {"attested": 40, "known": true, "early_mean": 0.31, "late_mean": 0.04,
#    "falling": true,
#    "detail": "edit distance fell from 0.31 to 0.04 across 40 attestations —
#               this reviewer may have stopped reading"}
```

A reviewer who has approved forty correct drafts is not reviewing the
forty-first, and no amount of telling them to will change that. This is a control
failure the platform can detect without anyone reporting it.

**A review sample**: roughly one generation in ten is marked for independent
review when it is drafted, regardless of how good it later looks. Marking at
draft time rather than at acceptance is what stops the sample being chosen by
anyone with an interest in the outcome.

### What this is not

MAYA does not call a language model. It records what one produced, gates it,
holds it until a person signs, and measures whether that person is still
reading. The generation itself happens wherever you run models — which is the
same boundary the platform draws everywhere else.
