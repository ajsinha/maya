---
title: Evidence, provenance and machine assistance
slug: evidence-and-provenance
section: Assurance
order: 110
icon: shield-check
summary: Three mechanisms behind "evidence, not assertion" — an append-only chain that proves the record was not edited, a provenance algebra that computes why a claim is believed, and a gate that lets the platform hold machine-generated work without believing it. Each section says what its mechanism does not prove.
audience: Model risk, Audit, Everyone
---

# Evidence, provenance and machine assistance

*Evidence, not assertion* is three separate claims wearing one slogan, and they
are worth keeping apart because they fail differently:

| | Proves | Does **not** prove |
|---|---|---|
| **The chain** | nobody edited the record after the fact | that what was recorded was true |
| **Provenance** | which facts a claim rests on, and how strongly | that those facts are the right ones |
| **The assistance gate** | machine output was checked or grounded before anyone saw it | that the prose is any good |

A platform that blurs those three is asking to be believed about the wrong
thing. Each section below states what its mechanism buys and then, explicitly,
what it does not.

## The chain

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
  "trust": 1.0,
  "parents": ["..."],
  "contains_personal_data": false,
  "content_hash": "sha256:...",
  "prev_hash": "sha256:...",
  "chain_hash": "sha256:..."
}
```

There is no second audit log. Two records of who did what are two records that
can disagree, and the one an examiner is shown would be the one nobody checks.

### What the content hash covers, and the case that decided it

`content_hash` is recomputed from the node's `kind`, its subject, its `payload`,
its `parents`, its `recorded_by` and its `trust`. `chain_hash` then covers the
sequence number, the previous chain hash, the content hash and the parents.

`recorded_by` being *inside* the content hash is the part worth explaining,
because leaving it out is the obvious design and it is wrong.
[Segregation of duties](/help/approval-and-attestation#segregation-of-duties) is
decided entirely by reading `recorded_by` off these nodes. If authorship were
outside the hash, a single `UPDATE` reassigning it would switch the control off
for that subject — and verification would go on reporting the chain intact.

### Verification checks four things, in order

1. **The sequence has no gap.** A deleted node is a gap, and a gap is a break.
   A pure Merkle DAG would not catch a removed leaf; contiguous sequence numbers
   do. This was **finding C-4** in adversarial review.
2. **`prev_hash` matches** — the links are intact.
3. **`content_hash` is what the node's own fields imply** — recomputed, never
   read back.
4. **`chain_hash` is what those imply together.**

The third was missing for a long time, and the absence was invisible. Re-linking
a *stored* content hash proves the links are intact; it says nothing about
whether the thing linked is still what was recorded. With only checks 1, 2 and
4, somebody editing a payload in the database left a chain that **verified
perfectly** and a record that lied — worse than a chain that visibly breaks,
because the whole point of the verification is to be believed.

The unit test that should have caught it was named for payload tampering and
actually altered the stored hash: a test that passed for a reason other than its
name. What found it was a run at five thousand nodes, which is the argument for
exercising the platform at a size where a difference is visible rather than only
at a size that is convenient.

### Two walks, because a full one is not free

```bash
GET /api/v1/evidence/chain      # the full walk from genesis; needs evidence:read
→ {"valid": true, "length": 47, "head": "sha256:…", "scope": "full"}
```

`/health/ready` runs the **incremental** walk instead — from the last
verification checkpoint forward — and reports **degraded** with 503 if it fails.
That is the only thing readiness fails on. Checking the whole chain on every
readiness probe would make readiness slower as the register grew, which is the
wrong direction for a probe.

The full walk is therefore something that *happens* rather than something
somebody remembers: the `evidence.verify` scheduler job walks the chain end to
end and advances the checkpoint. When the walk fails, **the checkpoint is not
advanced** — moving it past a break would bless the break:

```json
{"verified": false, "broken_at": 318, "reason": "content_hash mismatch: the
 node's payload, kind or subject is not what was recorded",
 "detail": "the chain is broken; the checkpoint was NOT advanced, because
            moving it past a break would bless it"}
```

The four break reasons are reported apart — `sequence gap`, `prev_hash
mismatch`, `content_hash mismatch`, `chain_hash mismatch` — because they are
four different accidents with four different first questions.

### Appending is contended, and says so

Sequence numbers are contiguous, which means two simultaneous appends race for
the same number. The append retries a bounded number of times with jittered
backoff and then **gives up loudly** rather than skipping a sequence number.
A chain with a hole in it is a chain that fails verification for a reason that
has nothing to do with tampering, and the first person to see that would spend a
day on it.

### Personal data is a marker, not a payload

Each node records whether its payload contains personal data, and when it does,
**the payload is not stored** — the hash is taken over what is stored, not over
what was passed. Append-only evidence and a data-subject erasure request are
otherwise irreconcilable: finding **H-3**, and the reason for law **L-18**. The
chain is not a place to put personal data, and the marker is how the platform
holds itself to that rather than trusting everyone who calls `append`.

### What the chain does not prove

It proves **internal consistency**: nobody edited a row in place without the
chain noticing. It does not prove the original claim was true. A validator who
records a Gini of 0.61 they never computed gets a chain that faithfully
preserves a false statement.

That is what [reproducibility replay](/help/validation) is for. The chain
protects the record; replay checks the claim. Neither substitutes for the other,
and a platform claiming that hash-chaining makes its numbers correct is
overselling arithmetic.

## Provenance: one traversal, six questions

Once evidence is a graph, *why do we believe this?* is a computation over it. A
claim is a disjunction of conjunctions — alternative derivations, each a set of
facts that together suffice — and one memoised bottom-up walk answers it,
parameterised by an algebraic structure rather than rewritten per question.

| Structure | `plus` | `times` | Answers |
|---|---|---|---|
| `BOOLEAN` | `or` | `and` | Is this claim supported at all? |
| `COUNTING` | `+` | `×` | How many distinct derivations support it? |
| `WHY` | union, then absorption | pairwise union | Which *minimal* sets of sources suffice? |
| `TRUST` | `max` | `×` | Best chain, degrading with every link in it |
| `COST` | `min` | `+` | What would the cheapest re-derivation cost? |
| `FRESHNESS` | `max` | `max` | How current are the supporting facts? |

Adding a seventh question means adding a structure, not another traversal that
can disagree with the first six.

**Citation soundness is the Boolean case.** A document that cites evidence nodes
is sound exactly when its citation set evaluates to true over `BOOLEAN`. That is
the check behind *"this validation report cites only evidence that exists"*, and
the same question a compiled document answers when it reports its dangling
citations.

### The reason it is one traversal is a theorem, and it runs

`ℕ[X]`, the free commutative semiring on the base facts, is implemented in
`core/evidence/semirings.py` as `POLYNOMIAL`. Evaluate a derivation once there
and **every other answer is a pushforward of it**: the homomorphism
`h : ℕ[X] → K` that sends each variable to its value in `K`.

```
polynomial = evaluate(claim, derivations, POLYNOMIAL, poly_variable)
pushforward(polynomial, valuation, BOOLEAN)   ==  evaluate(claim, …, BOOLEAN, valuation)
pushforward(polynomial, valuation, COUNTING)  ==  evaluate(claim, …, COUNTING, valuation)
…
```

That equality is law **L-9**, and it is executable: `tests/test_laws.py` builds
**200 random derivation DAGs** and checks the two routes agree for `BOOLEAN`,
`COUNTING`, `TRUST`, `COST` and `WHY`. Where they disagreed, one of the two
would not be a homomorphism — a fact about the structure, not about the
traversal, which is why it is worth asserting rather than assuming.

A polynomial is a map from monomial to coefficient. **Coefficients count
distinct derivations; exponents count how many times one fact is used in a
single derivation.** Boolean provenance throws both away, which is why it cannot
tell a claim supported by one document from a claim supported by four:

```python
# claim ← a, or claim ← b
{(("a", 1),): 1, (("b", 1),): 1}     # two independent supports, kept apart
pushforward(poly, lambda k: True, BOOLEAN)   # → True; collapsed to one bit
```

The same polynomial does a second job one layer across. A **derived feature** is
a term, so `rests_on()` is the free variables of its polynomial — the base
features and nothing else — while `lineage()` walks every ancestor including the
derived ones. Those answer two different questions (*what data does this
ultimately read* against *what would break if this changed*) and the difference
is asserted rather than assumed.

### `FRESHNESS` is not a semiring, and the law does not reach it

This is the one place to be careful, because the table above puts six rows
together and only five of them earn the name.

`FRESHNESS` is `(max, max)` with zero `0.0`. In a semiring the zero must
annihilate: `0 × x = 0`. Here `max(0, 5) = 5`. So it is a commutative idempotent
monoid used twice rather than a semiring, and the universal property of `ℕ[X]`
does not extend to it — the L-9 test deliberately excludes it and asserts the
failure, so it cannot be quietly re-included.

The practical consequence is the part to know:

> A claim resting on a **missing** fact reports the freshness of the facts that
> **are** present, rather than reporting that it has none.

Read a freshness figure as *how current is what we have*, never as *how current
is the whole basis of this claim*. The other four numeric answers do annihilate,
so a missing fact drags `BOOLEAN` to false, `COUNTING` to zero, `TRUST` to zero
and `COST` to infinity. Freshness is the one that will smile at you.

### When the answer is too large, it says so

`WHY` returns sets of sets, and a dense graph makes that grow badly. Past a
ceiling of 4,096 terms the result comes back marked `truncated` rather than
silently trimmed. A minimal-support answer that is quietly incomplete is worse
than no answer, because it reads as the whole story.

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

Allowing it into the registry would mean allowing something in that will one day
be wired into a decision path, because everything in a registry eventually is.
So the refusal is at registration, and it fires *before* the tier is even
checked against the valid set:

```json
{"error": "advisory_not_registrable",
 "detail": "a capability whose output can be neither checked nor grounded is
            advisory, and advisory AI is a person using a chat window",
 "remediation": "if the output can be checked, name the oracle and register it as
                 Tier A; if its claims can cite evidence, register it as Tier B"}
```

### Tier A — the oracles

An oracle is a predicate that decides whether a generated artifact is correct,
**mechanically, without asking the thing that generated it**. Very few tasks
have one, which is why the list is short — five, published at
`GET /api/v1/assist/tiers`:

| Oracle | Checks | Rests on |
|---|---|---|
| `warrant.conforms` | a generated warrant validates against the grammar | the warrant grammar |
| `contract.refines` | a proposed contract refines the incumbent (L-7) | the contract algebra |
| `schemas.substitutable` | proposed schemas satisfy variance (L-12) | the schema algebra |
| `test.registered` | a proposed validation test exists in the catalogue | the test catalogue |
| `citations.resolve` | every cited evidence node exists | the evidence graph |

Every one is backed by machinery that already exists for another reason, and
that is not a coincidence. A platform whose properties are formal enough to
check a *human's* work can check a *machine's*, and the same check serves both.
An oracle written specially to bless AI output would be an oracle nobody had
reason to trust.

A Tier A capability must name its oracle — registering one without an
`oracle_key` is refused. *"We validate the output"* without naming the check is
the sentence that precedes every AI incident. When the oracle fails
(`oracle_failed`), **nothing is recorded**. The check is the control.

### Tier B — the grounding gate

A Tier B output is a set of **claims**, each carrying the evidence it rests on.
The gate verifies every citation and then does the thing that makes it a gate
rather than a warning: it **removes** the claims that failed, and assembles the
published text from what survived. If nothing survives, the generation is
refused outright as `nothing_grounded`.

Flagging failures in place was considered and rejected. A document where the
unsupported sentences are marked is a document where the marks are what gets
skimmed past — and the sentence still reads as though the platform said it.

The rejected claims are kept on the generation, so a reviewer can see what the
model tried to assert and could not support. That is a far more useful artifact
than an annotated draft: it is the list of places the model was making things
up.

A claim citing **nothing** is not grounded — *the claim cites nothing, so
nothing supports it*. Uncited prose in a governance document is exactly what
this gate exists to stop, however true it happens to be.

### The evidence is fixed before the model is asked

`POST /api/v1/assist/drafts` asks a provider for a draft, and the order it does
things in is the design:

1. **The evidence is gathered from the register** — not from the model, and not
   from the prompt. At most forty nodes, because a claim citing one of four
   thousand is not a citation anybody can check.
2. **The prompt is assembled from that evidence**, and its digest recorded, so
   *what was it asked* has an answer that survives the model moving on.
3. **The provider drafts.** Anything it returns is a candidate.
4. **The gate runs unchanged** — oracle for Tier A, grounding for Tier B.

Step 1 bounds step 4. A provider cannot introduce a fact, only a *candidate*
fact, and a candidate citing nothing the platform holds is dropped before a
reader sees it. That is what makes it safe to point this at a model nobody has
audited.

### Nothing is evidence until a person attests it

A drafted generation carries no weight anywhere in the platform. The states are
`drafted`, `attested`, `rejected`, and attestation is the only transition that
gives a generation any weight — **and the person who asked for the draft cannot
be the person who attests it**:

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

**Edit distance** on attestation: how much the reviewer changed. The number
means little on its own; the *trend* is the point, which is why nothing is
reported until a reviewer has attested at least four times.

```bash
GET /api/v1/assist/reviewers/a.mehta
# → {"attested": 40, "known": true, "early_mean": 0.31, "late_mean": 0.04,
#    "falling": true,
#    "detail": "edit distance fell from 0.31 to 0.04 across 40 attestations —
#               this reviewer may have stopped reading"}
```

A reviewer who has approved forty correct drafts is not reviewing the
forty-first, and no amount of telling them to will change that. This is a
control failure the platform can detect without anyone reporting it.

**A review sample**: one generation in ten is marked for independent review when
it is drafted, regardless of how good it later looks. Marking at draft time
rather than at acceptance is what stops the sample being chosen by anyone with
an interest in the outcome.

### What this does and does not do

MAYA *can* ask a model — `GET /api/v1/assist/providers` says which one this
instance can reach and why it cannot reach the rest. One provider works; three
named remote providers **refuse by name** rather than returning something
plausible, because a stub returning fabricated prose into a governance register
is a machine writing into the record with nothing behind it, and the first
reader would have no way to tell.

Wiring a remote model up is not a matter of filling in an HTTP call. Four things
have to be answered first, and none of them is code: **egress** (everything else
here is vendored so the platform can run air-gapped), **confidentiality** (a
prompt assembled from this register carries inventory, findings and exposure
figures), **reproducibility** (weights move underneath a version string, which
is why the grammar treats `llm.prompt` and `llm.agent` as stochastic runtimes),
and **cost**. Until a deployment has answered them, refusing is the honest
behaviour.

What the platform does not do at all is judge whether the prose is any good. It
records what was produced, gates it, holds it until a person signs, and measures
whether that person is still reading.
