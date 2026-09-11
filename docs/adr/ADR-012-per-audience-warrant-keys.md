# ADR-012 — Per-audience warrant keys instead of asymmetric signing

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09 · **Supersedes** the *asymmetric warrant
signatures* item that led [10 §2.1](../10-roadmap.md) for two revisions

## Context

A warrant descriptor is a bearer credential, signed HMAC-SHA256 over its
canonical form. Every review of this platform has raised the same objection, and
[11 §4.3](../11-adversarial-review.md) states it precisely: **to verify a
descriptor an engine needs the secret, and with the secret it can mint any
descriptor it likes** — any model, any principal, any use, any expiry.

The standing answer was *asymmetric signing, not built*, with Ed25519 named as
the production target in [04](../04-architecture.md) and
[06 §12](../06-warrants-and-execution.md). It was first in the roadmap's order.

Two things were wrong with that answer, and neither was the cryptography.

**It deferred a live defect to a project nobody had started.** A key hierarchy
needs custody, rotation, revocation and somebody to own all three. While that was
pending, every engine held a key that forged the whole estate.

**It answered a question nobody had asked.** The objection is about *blast
radius* — what one compromised consumer can do. Asymmetry answers a different
question: whether MAYA can prove authorship to a party that is not MAYA. Those
are separable, and only the first was a live problem in a deployment where the
engines are inside the firm's trust boundary.

## Decision

**Derive each audience's signing key from the root and that audience's own
principal.**

```
k_audience = HMAC(root, "maya/warrant/v<generation>/" ‖ audience)
```

MAYA holds the root and derives every audience key. An engine is handed its own
(`POST /api/v1/warrant-signing/key`) and can derive nothing, because the step is
one-way.

Three details are load-bearing rather than incidental.

**The audience is read from the document being verified**, not from the signer.
An attacker who re-points a warrant they legitimately hold at another principal
has changed the key it should have been signed under, so the substitution fails
inside `verify()` rather than depending on a separate check somebody remembered
to write.

**A warrant with no principal gets an audience no principal can hold.** Falling
back to the root would restore the estate-wide key silently, and only for the
malformed cases — the worst of both.

**`key_id` is `<root>.g<generation>.<audience digest>`**, both halves one-way.
The root half makes rotation legible, the generation lets a warrant issued under
an earlier key be *distinguishable* rather than mysteriously invalid, and the
audience half makes it obvious at a glance that two engines are not sharing a
key.

Asymmetric signing is **removed as a requirement**, not deferred. If a firm ever
needs non-repudiation to a third party, that is a new requirement with its own
argument.

## Consequences

- **+** A compromised engine forges warrants for **itself and nobody else**. That
  is the containment the objection was actually about, and it arrives without a
  key hierarchy.
- **+** `GET /api/v1/warrant-signing` publishes what a signature proves *and*
  what it does not, in the same object. A descriptor is evidence **to the bank**
  and not to anybody outside it, said in those words rather than left for a
  reader to assume.
- **+** Rotation is a generation counter. Raising `warrants.key_generation`
  re-keys every audience without touching the root.
- **−** **No non-repudiation.** A verifier holds the key it verifies with, so it
  could have minted what it checks. An external party — a supervisor, an
  auditor's own tooling — cannot use a descriptor as proof MAYA issued it.
- **−** **Key distribution is real work.** `POST /warrant-signing/key` is the
  only endpoint in MAYA that returns a secret. It records the disclosure on the
  evidence chain and **not the key**, because writing a secret into an
  append-only chain publishes it to every holder of `evidence:read` — the defect
  `key_id` was fixed for.
- **−** MAYA cannot tell whether an engine stored its key safely, and the reply
  says so rather than letting the disclosure read as an assurance.

## Alternatives considered

| | Why not |
|---|---|
| **Ed25519 with an overlapping key set** | The stated target for two revisions. It solves both halves and costs a key-management programme to solve the half nobody asked about. Available later without unpicking this: the derivation is about *which* key, not about *what kind* |
| **A per-engine key, stored** | Same containment, plus a table of secrets to protect, rotate and lose. The derivation gives the property without the store |
| **Nothing, and document the limitation harder** | What was done for two revisions. A caveat in a design document is read once by the person who wrote it |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
