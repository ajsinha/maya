---
title: Glossary
slug: glossary
section: Reference
order: 170
icon: book
summary: The vocabulary, in one place. Terms are used precisely and consistently in the code, the API and these pages.
audience: Everyone
---

# Glossary

**Alias** — a named, environment-scoped pointer at a version, such as
`champion` in `prod`. Consumers bind to aliases, never to versions, which is why
a version can be replaced without anyone redeploying.

**Artifact digest** — the content hash of whatever actually runs. MAYA stores the
digest and the reference, not necessarily the bytes.

**Assumption** — a bound on an input under which the model's guarantees hold.
Outside it, the guarantee is void.

**Bitemporal** — carrying two clocks: valid time (when a fact was true) and
transaction time (when we learned it). See
[the two clocks](/help/features-and-two-clocks).

**Blocking finding** — an open finding that refuses alias promotion and warrant
resolution. Critical severity blocks by default.

**Contract** — an assume-guarantee pair. Contracts *refine* one another: a
replacement must assume no more and guarantee no less.

**Declared use** — what a principal says it will do with a model. Resolution
refuses if it is not the approved use.

**Descriptor-only** — a version whose artifact MAYA cannot obtain, typically a
vendor black box. An honest state, recorded as a limitation.

**Evidence node** — one entry in the append-only hash chain. Carries a sequence
number, a payload, an actor, and hashes linking it to its predecessor.

**Feature view** — a named, owned collection of features over one entity,
materialised into versioned Delta namespaces.

**Feature contract** — a binding of a model version to exact feature view
versions. What serving *must* read.

**Grace** — extra time a warrant's authorisation stays current when the control
plane is unreachable. It never extends revocation ignorance.

**Guarantee** — a property the model promises when its assumptions hold.

**Manifest digest** — the content hash of a version's full specification. Stable,
so the same version registered twice from two pipelines is detected.

**Materiality** — how much is at stake: exposure and purpose. One of the two
lattices feeding the tier.

**Namespace** — the Delta path a specific feature view version serves from. A
version *is* a namespace.

**Operating boundary** — the assumptions in force, checked by the execution
engine before invoking the artifact.

**Parameter object (P)** — the parameters of a model, in the sense
*f : P ⊗ X → Y*. How P is inhabited gives the trainability class.

**Point-in-time (PIT)** — the property that an assembled row uses only facts that
were true by the label time and known by the as-of time.

**Principal** — the identity a warrant is issued to. A service, not usually a
person.

**Refinement** — the ordering on contracts. New refines old when it assumes no
more and guarantees no less. Checked on every alias move.

**Revocation epoch** — a counter bumped by every revocation. Warrants carry the
epoch they were minted under, so an engine can tell a stale credential from a
current one.

**Revocation floor** — the rule that a revoked warrant is refused regardless of
grace state.

**Semiring** — the algebraic structure that parameterises one provenance
traversal into six different questions.

**Snapshot** — a named, digested, immutable dataset produced by an assembly,
with its PIT report attached.

**Tier** — 1 (highest scrutiny) to 4, computed from materiality and complexity.

**Trainability class** — T0–T8, derived from how the parameter object is
inhabited. See [Trainability classes](/help/trainability-classes).

**URN** — the permanent model handle, `maya://model/<name>`.

**Variance** — the schema compatibility rule: inputs contravariant, outputs
covariant.

**Warrant** — a signed, expiring, entitlement-bound document authorising a named
principal to perform a stated operation on a stated model version. Formerly
called a hook.
