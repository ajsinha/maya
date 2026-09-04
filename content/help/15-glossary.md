---
title: Glossary
slug: glossary
section: Reference
order: 150
icon: book
summary: The vocabulary, in one place. These terms are used precisely and consistently in the code, the API and these pages — where a term has a narrow meaning here, this is the narrow meaning.
audience: Everyone
---

# Glossary

## A to C

**Alias** — a named, environment-scoped pointer at a version, such as
`champion` in `prod`. Consumers bind to aliases, never to versions, which is why
a version can be replaced without anyone redeploying.

**Amendment** — a declared change to an attested record. It names what is
changing and why, returns the record to `amending`, and must itself be
submitted, approved and attested.

**Artifact digest** — the content hash of whatever actually runs. MAYA stores the
digest and the reference, not necessarily the bytes.

**Assumption** — a bound on an input under which the model's guarantees hold.
Outside it, the guarantee is void.

**Attestation** — the quorum that puts a record in force: every required role
signs, and one decline ends it. Distinct from approval, which is one person in
the second line saying the work is sound.

**Baselined** — a model imported from an existing estate: in the inventory,
tiered, governed going forward, and explicitly not asserting historical
evidence. A mutable state.

**Bitemporal** — carrying two clocks: valid time (when a fact was true) and
transaction time (when we learned it). See
[the two clocks](/help/features-and-two-clocks).

**Blocking finding** — an open finding that refuses alias promotion and warrant
resolution. Critical severity blocks by default.

**Compliance debt** — a recorded, dated gap in a baselined model's evidence. Debt
is not breach: it blocks nothing, raises no finding, and closes by itself when
the evidence arrives. At its expiry it becomes a breach.

**Contract** — an assume-guarantee pair. Contracts *refine* one another: a
replacement must assume no more and guarantee no less (law L-7).

## D to G

**Declared use** — what a principal says it will do with a model. Resolution
refuses if it is not the approved use.

**Derived feature** — a feature computed from other features by a small,
total expression language. Its inputs are read from its expression, its ingest
clock is the maximum of its inputs', and it may not read the label.

**Descriptor-only** — a version MAYA holds the governance for without holding the
artifact: no digest recorded, or no runtime declared. It is read off the record
rather than set as a flag, and law L-W6 refuses to fit one.

**Evidence node** — one entry in the append-only hash chain. Carries a sequence
number, a payload, who recorded it, and hashes linking it to its predecessor.

**Featureset** — a named, declared **schema** of typed slots that a kernel can be
defined over, and that a warrant can ask for by name.

**Featureset version** — a binding of each slot to a feature and the exact
feature view version supplying its values. A version that cannot fill the schema
is refused.

**Feature contract** — a binding of a model version to exact feature view
versions. What serving *must* read (law L-17).

**Feature view** — a named, owned collection of features over one entity,
materialised into versioned Delta namespaces.

**Grace** — extra time a warrant's authorisation stays current when the control
plane is unreachable. It never extends revocation ignorance.

**Guarantee** — a property the model promises when its assumptions hold.

## H to P

**Kernel** — the shape every model in MAYA takes: `f : P ⊗ X → Y`, a parameter
object, an input and an output. Training does not change `f`; it inhabits `P`.

**Lens** — a section of a compiled document that goes and reads the register,
rather than a template that interpolates what it was handed.

**Manifest digest** — the content hash of a version's full specification. Stable,
so the same version registered twice from two pipelines is detected.

**Materiality** — how much is at stake: exposure joined with purpose. One of the
two lattices feeding the tier.

**Namespace** — the Delta path a specific feature view version serves from. A
version *is* a namespace.

**Operating boundary** — the assumptions in force, checked by the execution
engine before invoking the artifact.

**Oracle** — a predicate that decides mechanically whether a generated artifact
is correct, without asking the thing that generated it. A Tier A machine
assistance capability must name one.

**Overlay** — a human adjustment applied on top of a model's output. Time-boxed,
measured, approved by somebody who did not propose it, and a finding if it keeps
being renewed.

**Parameter object (P)** — the parameters of a model, in the sense
*f : P ⊗ X → Y*. How P is inhabited gives the trainability class.

**Parameter set** — a stored, immutable, versioned inhabitant of P, with the
featureset version, window and warrant that produced it. Fitted sets are accepted
only against a warrant MAYA issued.

**Point-in-time (PIT)** — the property that an assembled row uses only facts that
were true by the label time and known by the as-of time.

**Principal** — the identity a warrant is issued to. A service, not usually a
person.

## Q to Z

**Refinement** — the ordering on contracts. New refines old when it assumes no
more and guarantees no less. Checked on every alias move.

**Regime** — a supervisory framework encoded as its own signature, its own
obligations and a translation into MAYA's vocabulary. It cannot be activated
unless truth survives that translation.

**Revocation epoch** — a counter bumped by revocation. Warrants carry the epoch
they were minted under, so an engine can tell a stale credential from a current
one.

**Revocation floor** — the rule that a revoked warrant is refused regardless of
grace state.

**Scope** — the models a permission may be exercised over, by legal entity and
domain. An empty list is unrestricted; scope filters listings, not just detail
pages.

**Segregation of duties** — the rule that what you may do next depends on what
you already did, computed from the evidence chain rather than from a separate
table.

**Semiring** — the algebraic structure that parameterises one provenance
traversal into six different questions.

**Snapshot** — a named, digested, immutable dataset produced by an assembly,
with its PIT report attached.

**Tier** — 1 (highest scrutiny) to 4, computed from materiality and complexity
by a monotone function (law L-4).

**Trainability class** — T0–T8, derived from how the parameter object is
inhabited and by what procedure. See
[Registering a model](/help/registering-a-model#trainability-classes-t0-to-t8).

**URN** — the permanent model handle, `maya://model/<name>`. No version and no
environment in it.

**Variance** — the schema compatibility rule: inputs contravariant, outputs
covariant (law L-12).

**Warrant** — a signed, expiring, entitlement-bound document authorising a named
principal to perform a stated operation on a stated model version. Formerly
called a hook. Distinct from a **grant**, which is the standing entitlement a
warrant is minted against.

**Worklist** — what needs doing, derived from the register rather than assigned,
and filtered to what you personally hold the permission and the scope to do.
