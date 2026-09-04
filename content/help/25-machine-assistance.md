---
title: Machine assistance
slug: machine-assistance
section: Assurance
order: 148
icon: robot
summary: Where the platform's own AI may act — decided by whether a human can check the output more cheaply than producing it, not by how good the model is.
audience: Everyone
---

# Machine assistance

The organising question is not *is the model good enough*. It is:

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

## Why Tier C is not registrable

A capability whose output can be neither checked nor grounded is advisory, and
advisory AI is a person using a chat window — not something the platform runs.

Allowing it into the registry would mean allowing something into the registry
that will one day be wired into a decision path, because everything in a registry
eventually is. So the refusal is at registration:

```json
{"error": "advisory_not_registrable",
 "detail": "a capability whose output can be neither checked nor grounded is
            advisory, and advisory AI is a person using a chat window",
 "remediation": "if the output can be checked, name the oracle and register it as
                 Tier A; if its claims can cite evidence, register it as Tier B"}
```

## Tier A: the oracles

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

## Tier B: the grounding gate

A Tier B output is a set of **claims**, each carrying the evidence it rests on.
The gate verifies every citation and then does the thing that makes it a gate
rather than a warning: it **removes** the claims that failed.

Flagging them in place was considered and rejected. A document where the
unsupported sentences are marked is a document where the marks are what gets
skimmed past — and the sentence still reads as though the platform said it.

The rejected claims are kept separately, so a reviewer can see what the model
tried to assert and could not support. That is a far more useful artifact than an
annotated draft: it is the list of places the model was making things up.

A claim citing **nothing** is not grounded. Uncited prose in a governance document
is exactly what this gate exists to stop, however true it happens to be.

## Nothing is evidence until a person attests it

A drafted generation carries no weight anywhere in the platform. Attestation is
the only transition that gives it any — and **the person who asked for the draft
cannot be the person who attests it**:

```json
{"error": "self_attestation",
 "remediation": "attestation is a person taking responsibility for machine output;
                 it must be somebody other than whoever asked for it"}
```

There is deliberately **no endpoint** that turns a generation into a governance
decision. The absence is the control; there is a test asserting it.

## Watching the watchers

Two measurements are taken that are not about the output at all.

**Edit distance** on attestation: how much the reviewer changed. The number means
little on its own; the *trend* is the point.

```bash
GET /api/v1/assist/reviewers/a.mehta
# → {"attested": 40, "early_mean": 0.31, "late_mean": 0.04, "falling": true,
#    "detail": "edit distance fell from 0.31 to 0.04 across 40 attestations —
#               this reviewer may have stopped reading"}
```

A reviewer who has approved forty correct drafts is not reviewing the
forty-first, and no amount of telling them to will change that. This is a control
failure the platform can detect without anyone reporting it.

**A review sample**: a fraction of accepted generations are pulled for
independent review regardless of how good they look. Deliberate friction against
the same bias.

## What this is not

MAYA does not call a language model. It records what one produced, gates it,
holds it until a person signs, and measures whether that person is still
reading. The generation itself happens wherever you run models — which is the
same boundary the platform draws everywhere else.
