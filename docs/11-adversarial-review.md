# 11 — Adversarial Review

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Posture:** adversarial. The objective is to break the platform, not to confirm it.
**Standard:** a claim counts as verified only when it was read out of `core/`, `routes/`, `db/schema/` or
`tests/` while writing this sentence. Nothing here is taken from another document, including the previous
version of this one.

---

## 1. What this document is for

The first version of this review was written against the design, before there was any code. It found
twenty-seven things, six of them critical, and two of those — an unversioned online feature store and the
absence of any cold-start path — would each independently have sunk the programme. That was worth doing and
the record of it is kept in [§5](#5-the-original-twenty-seven-re-dispositioned-against-the-code).

It is not the interesting part any more. The interesting part is what the *build* has since said about the
review, and the answer is uncomfortable enough to be the organising idea of this rewrite:

> **Almost nothing found since has been a missing control. Almost everything found since has been a control
> that was present, tested, documented, and inert.**

That is a different failure mode from the one a design review is good at, and it is worse, because an absent
control is visible to anybody who looks for it while an inert one is invisible to everybody — including to
the suite, including to the reviewer, and including to the person who wrote it. A missing control fails
closed on the day somebody needs it. An inert control reports success for years and then fails open on
exactly that day.

So this document is organised around inertness. [§3](#3-seven-ways-a-control-reports-success-while-doing-nothing)
gives the taxonomy, each entry with an instance found in this repository. [§4](#4-the-open-attacks) states
the attacks that are live today, in the order an attacker would try them. [§5](#5-the-original-twenty-seven-re-dispositioned-against-the-code)
re-dispositions the original findings against the code rather than against their own dispositions — which
turns out to matter, because a disposition is a plan and several of these were never carried out.
[§6](#6-what-survived) says what held, and [§8](#8-what-this-review-method-gets-wrong) says where this
method itself fails.

A note on what is deliberately absent. There is no severity table with counts in it any more. The original
review had one and it flattered the work: *"six critical, all dispositioned"* reads as six problems solved,
when what it recorded was six problems **described**. What replaces it is a column saying whether the
control the disposition promised exists in the source today, which is the only question worth asking a year
later.

---

## 2. The method, and why it changed

The original method applied five attack lenses to design claims: contradiction, silent failure, adversary,
scale and cold start, overclaim. Those still work and they are still applied. What the build added is a
sixth, and it is now the first one used, because it is the one that finds things the other five cannot.

| Lens | The question |
|---|---|
| **L1 · Contradiction** | Do two stated guarantees conflict under some reachable state? |
| **L2 · Silent failure** | What fails in a way nobody notices for six months? |
| **L3 · Adversary** | What does a motivated insider do with this? Assume they have database access, because in most banks somebody does |
| **L4 · Scale and cold start** | What breaks at fifty thousand models, or on day one with twelve hundred and no evidence? |
| **L5 · Overclaim** | Which stated guarantee is weaker than the words imply? |
| **L6 · Inertness** | **Trace the control from the claim to the line that executes it.** If there is no caller, no reachable branch, or no assertion that the refusal happened, the control is decoration and the suite will not tell you |

L6 is mechanical and unglamorous and it has the best yield of the six. The procedure is three greps: find
the symbol that implements the control; find its callers in `core/` and `routes/` rather than in `tests/`;
read the test that carries its name and check that the test asserts a **refusal** rather than a state. Two
of the findings in [§4](#4-the-open-attacks) came out of exactly that, and one of them is a control with a
docstring, a test, a mention in three documents, and no production caller at all.

The second change is that the review now assumes **database access**. The original threat model treated the
platform's own storage as trusted and reasoned about API-level attacks. That was the wrong boundary for a
system whose central claim is tamper evidence, and correcting it is what produced
[§4.1](#41-there-is-one-database-one-identity-and-a-generic-update-on-every-table).

---

## 3. Seven ways a control reports success while doing nothing

Each row is a shape, not an incident, and each has at least one instance found in this repository. The
shapes are the reusable part: the next control will fail in one of these ways rather than in a new one.

### 3.1 It has no caller

The control exists, is correct, is tested, and nothing in the running system invokes it.
`core/execution/engine.py::note_revocation` is the revocation floor — the mechanism finding **C-1** was
raised to obtain, so that grace could never become revocation ignorance. It is called from one place in the
repository: a test. Full detail in [§4.2](#42-the-revocation-floor-cannot-fire).

### 3.2 The branch it guards is unreachable

Worse than having no caller, because it *is* called and still cannot fire. `CaptiveEngine.execute` checks
`warrant["warrant_id"] in self._revoked_locally` — after re-resolving the warrant, and every resolution mints
a fresh `warrant_id` through `new_id()` in `core/execution/builder.py`. The identifier being checked is
never the identifier that was noted. The line runs on every execution and can never be true.

### 3.3 A test that passes for a reason other than its name

The oldest instance is the one that produced **C-4**'s recurrence: a unit test named for a tampered
*payload* that actually altered the *stored hash*, and so passed for years against a verifier that would
have accepted an edited payload. It has happened again, and the second instance is more honest about itself
than the first was — `tests/test_registry_execution.py::test_local_revocation_floor_beats_a_valid_descriptor`
contains the line

```python
# a fresh resolve yields a new id, so prove the check itself works
engine._revoked_locally.add("*")
```

and then asserts set membership. The author noticed that the control could not fire, wrote that down in a
comment, and asserted something else. The test is green, its name promises that grace does not extend
revocation ignorance, and nothing in it executes a model or observes a refusal.

The general rule this argues for: **a test for a refusal must assert the refusal.** A test that asserts a
data structure contains what was just put into it is testing `set.add`.

### 3.4 A mechanism named but not built

Law **L-18** says a node flagged `contains_personal_data` carries no inline payload, *only an erasable
pointer*. The first half is true and enforced in the append path. The second half does not exist: there is
no `payload_uri` column in either dialect, no per-subject key, and no shred path. `core/evidence/engine.py`
stores `{}` and the payload is **discarded**, not pointed at.

The law is satisfied and the design is not. What **H-3** promised was that erasure and immutability could
both hold — payload in Delta under a per-subject key, key destroyed, chain still valid. What runs is that
personal data is thrown away at the door, which satisfies the law by making the capability impossible.
Those are different systems, and four places in the source and two in
[00](00-mathematical-foundations.md) describe the one that was not built.

### 3.5 An anchor written by the thing it certifies

**C-4** disposition 3 was explicit: *"verification compares the head against the anchor, not merely against
itself — self-consistency of a chain an attacker controls proves nothing."* What shipped is
`evidence_checkpoint`, an ordinary table in the same database, written by
`EvidenceEngine._record_checkpoint` at the end of a successful verification, with `verified_by` set to
`"system"`. `verify_since_checkpoint` then trusts it and checks only what came after.

The reasoning behind it is sound and the measurement is real — the full walk was 2.9 seconds and 83 MB at
forty thousand nodes, and `/health/ready` cannot pay that. But the result is that the cheap check, which is
the one that runs continuously, compares the chain against a mark the same process wrote. C-4's third
disposition has recurred one abstraction higher than where it was written.

### 3.6 A fix applied to one call site

The full chain walk was moved off the readiness probe for the reason above. The docstring that records the
change names the other place it hurt — *"and the same call sat on the dashboard"* — and the dashboard still
calls it: the `/dashboard` route in `routes/ui_routes.py` runs `verify_chain()` on every load. So does
`core/docs/context.py`, which means every compiled document and every export pack walks and re-hashes the
whole chain. The probe is fixed; the two paths a person actually waits on are not, and the code comment
reads as though all three were.

### 3.7 A rule held on one side of a boundary

`tests/test_schema_discipline.py` enforces the rule that broke the PostgreSQL dialect once already: **no
`BOOLEAN` columns, in either dialect**. It reads the two `.sql` files and it is thorough about them —
identical columns, equivalent types, no bulk data. It does not read `db/repositories.py`, where
`_BOOL_COLUMNS` is the hand-maintained list of which integer columns get coerced from a Python `bool` on
the way in.

So the invariant has two halves and one enforcer. Today `warrant.revoked` is on the list and
`warrant_profile.retired` and `risk_appetite.retired` are not — both are written as literal `0` and `1`, so
nothing is broken. The moment somebody writes `retired=True`, SQLite stores `1` and PostgreSQL raises,
which is precisely the failure the rule exists to prevent, arriving through the half of the rule nothing
holds.

---

## 4. The open attacks

In the order somebody would actually try them. Each states the attack, then the honest answer — including,
twice, that there is not one.

### 4.1 There is one database, one identity, and a generic `UPDATE` on every table

**The attack.** I have write access to the platform's database, which in a bank is a database
administrator, a backup operator, a restore rehearsal, or anybody who has ever been handed production
credentials for an incident. I edit a `test_result` row from `failed` to `passed`.

`verify_chain` catches that, and it genuinely does: `content_hash_of` re-derives the digest from the node's
kind, subject, payload, parents, `recorded_by` and `trust`, so an edited payload breaks. So I re-derive it
myself. The hash is `sha256` over a canonical JSON form the source publishes; I recompute `content_hash`,
then `chain_hash` for that node, then every `chain_hash` after it, and set the `evidence_checkpoint` row to
the new head. The chain verifies. The readiness probe was already trusting the checkpoint and now the full
walk agrees with it.

**The honest answer: there is not one.** Every property the chain claims reduces to *"an attacker who can
write the row cannot recompute the hash"*, and the hash is unkeyed, unsigned and unanchored. What was
supposed to close this is C-4 disposition 2 — anchoring the daily head to WORM storage and an RFC-3161
timestamping authority, so back-dating needs two systems under different control — and it is not built and
is named as not built in [10 §2.1](10-roadmap.md). Disposition 4, an application role holding only
`INSERT`/`SELECT` with retention deletion under a separate dual-controlled role, is also not built: there
is no `GRANT`, `REVOKE` or `CREATE ROLE` anywhere in either schema file, `db/database.py` opens one engine
with one identity, and `EvidenceRepository` inherits `Repository.remove()` unchanged.

Deletion is the one part that does hold: removing a node leaves a sequence gap and `_walk` reports it. That
is worth having and it is much less than the design claims.

**What this costs while absent.** It is the single largest gap in the assurance story, larger than the
signing gap below, because tamper evidence is the property the phrase *evidence, not assertion* is about.
Until the head is anchored somewhere MAYA cannot write, the correct statement is that the chain detects
**accident and casual tampering** and not a determined insider — and that sentence should appear wherever
the chain is described.

### 4.2 The revocation floor cannot fire

**The attack.** MAYA revokes a warrant. My engine holds a descriptor with grace remaining and is
partitioned from the control plane. C-1's disposition says a locally persisted revocation list refuses it
regardless of grace state.

There is no such list. `CaptiveEngine._revoked_locally` is an unpersisted in-memory `set` of descriptor
identifiers on one engine object; `note_revocation` is called from no production code; and, as
[§3.2](#32-the-branch-it-guards-is-unreachable) records, the identifier it compares against is regenerated
on every resolve, so the branch cannot be taken. The `revocation.epoch` carried in every descriptor's
`authority` block — C-1 disposition 3 — is a per-process integer that starts at `0`, is incremented in
`WarrantGrants.revoke`, resets on restart while the persisted `warrant.epoch` values do not, and is compared
by nothing anywhere. The descriptor field says `"check": "required"` and no code performs a check.

**The honest answer, in two halves.** What genuinely stops a revoked warrant is the control-plane check in
`WarrantService.resolve`, which reads `grant["revoked"]` and refuses. That is real, it is tested end to end,
and it is why `test_revocation_stops_execution` passes. But it is a check made **by asking MAYA**, which is
the one thing an engine in a partition cannot do — so what exists is the mechanism C-1 said was
insufficient, and the mechanism C-1 added is inert.

The other half is that severity-scaled TTL, disposition 2, **is** built and is the reason the residual is
small: `DEFAULT_TTL = {1: 60, 2: 300, 3: 3600, 4: 3600}` and `DEFAULT_GRACE = {1: 0, 2: 0, 3: 900, 4: 900}`
in `core/execution/grants.py`, applied per model tier at issue and honoured in
`WarrantSigner.is_expired`. A Tier 1 descriptor lives sixty seconds with no grace, so for the models the
finding was about, the floor has almost nothing to do. That is a good reason for the residual being
tolerable and not a reason for a control that reports success while unable to fire.

**Disposition.** C-1 is reopened. The floor should either be built — persisted, keyed on something stable,
refreshed on every response, with a test that executes and expects `revoked` — or removed, with the TTL
argument stated as the whole answer. What must not stand is the present arrangement, where three documents
describe a floor and the code cannot reach one.

### 4.3 Nothing verifies a warrant without holding the key that mints one

**The attack.** I am an execution engine MAYA does not control. To verify a descriptor I need the HMAC
secret; with it I can mint any descriptor I like, for any principal, any use, any expiry.

**The honest answer: known, stated, unbuilt.** `core/execution/signing.py` is `HMAC-SHA256` and says so.
RS256 verification already exists in `core/authz/jws.py` for OIDC, written carefully — it constructs the
padded block rather than parsing what it recovers, and decides the algorithm itself rather than reading
`alg` — so the primitive is present and the gap is key management rather than cryptography. It is first in
the order in [10 §3](10-roadmap.md).

Until then, the accurate claim is that a warrant is **tamper-evident to the platform and to anybody the
platform has trusted with the secret**, which is a narrower claim than a signature usually implies. The
`descriptor_only` flavour makes it narrower still: those engines hold the secret precisely because they are
the ones MAYA does not run.

### 4.4 No transaction spans a governance act

**The attack.** I register a model and kill the process between the model row committing and the evidence
node appending. The model exists in the register; the record of its registration does not. Segregation of
duties is decided by reading the chain, so *"you cannot approve what you created"* has nothing to read, and
the developer can approve their own version.

That is not hypothetical — it is the exact defect `tests/test_concurrency.py` was written for, measured at
seven percent of appends under four threads. The fix made the append **atomic and retried**: `append` wraps
`_append` in `db.transaction()` and retries the `UNIQUE(seq)` collision with jittered backoff.

**The gap the fix leaves.** `db.transaction()` is opened in exactly **one place in the whole of `core/`**,
inside `EvidenceEngine.append` — and in no route and in no service. So every governance act is still two
transactions: the state change commits, then the evidence node commits. The race is closed; the crash
window is not. The window is now small, and small is a different property from impossible, and design rule
DR-4 in the previous version of [14](14-detailed-design.md) claimed the impossible one.

**Disposition.** New finding, open. The mechanism to close it exists and is re-entrant by construction —
`transaction()` joins an outer one rather than deadlocking against it — so a service can wrap a whole act
today. Nothing does.

### 4.5 Immutability has no enforcer

**The attack.** I call `versions.set({"manifest_digest": ...}, id=...)`. Nothing stops me.

`db/repositories.py::Repository` provides generic `set()` and `remove()` with no column whitelist, and
`VersionRepository` overrides neither. There are no triggers, no `CHECK` constraints and no `FOREIGN KEY`
constraints in either dialect — the schema files contain zero of each. What `db/schema/sqlite.sql` contains
is a comment: *"Versions are immutable. There is no UPDATE path other than status."* That is a description
of current callers, written where a reader expects a constraint.

**The honest answer.** C-3's disposition — a `BEFORE UPDATE` trigger raising on any change to an immutable
column — is not built, and [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces) already says
so in the `L-2` row. What holds today is that only one call site updates the table, and it updates
`status`. That is a convention, and conventions are what this platform exists to replace with proofs.

The absence of foreign keys deserves its own sentence, because it silently resolves **H-4**. That finding
was about circular and forward references making the DDL uncreatable, dispositioned as
`DEFERRABLE INITIALLY DEFERRED` constraints created in a dedicated step. What shipped has no referential
integrity in the database at all, so the cycles are gone and so is every other guarantee an FK would have
given. `LifecycleService.delete` hard-deletes a `model` row and leaves its versions, warrants, findings and
monitors orphaned; the evidence is retained, which is the important half, and the register is not.

### 4.6 Scope is a Python call somebody has to remember

**The attack.** I am a validator scoped to one legal entity. I look for a listing endpoint whose author
forgot `Scope.filter`.

**The honest answer.** There is no database backstop: **H-5** (row-level security, forced on the table so
the owner cannot bypass it) is not built, and there is one connection identity, so RLS would have nothing
to distinguish anyway. Everything rests on `core/authz/scope.py` being called, from `routes/base.py`, on
every path.

Two things make that better than it sounds and neither makes it safe. The first is that the same defect
already happened and was fixed structurally: listings filtered while directly-addressable pages did not, so
a validator who was correctly shown nothing on the dashboard could load the model page by URL and receive
its versions, alias history, warrant grants and evidence chain. `routes/base.py::may_view` now applies the
API's own rule to every page that resolves a named object. The second is that filtering happens **before**
paging, so page two of a filtered list is not page two of the unfiltered one with holes in it.

What is still missing is the negative test **H-5** actually asked for: a cross-entity read that must return
zero rows, run in the pipeline. Untested isolation is assumed isolation, and this isolation is untested.

### 4.7 Everything claimed about an engine MAYA does not run is unobserved

**The attack.** I am an `opaque` execution engine. I resolve a descriptor and then ignore the operating
boundary, cache the artifact past expiry, and send no telemetry.

**The honest answer: exactly as C-6 said, and less closed than C-6's disposition promised.** The
limitation was accepted with five mitigations. One of them — documenting it plainly — is done, in
[06 §10.3](06-warrants-and-execution.md#103-descriptor_only-and-the-governance-it-cannot-reach). The other four are not built. There is no engine certification
level: `warrant.flavour` is written at issue, defaults to `descriptor_only`, and is read by nothing.
Certification is not an input to tiering; `TieringEngine.assess` reads exposure, purpose class,
trainability class, feature count, alternative-data use and interpretability, and nothing about who runs the
model. Telemetry is unsigned — `TelemetryCollector.ingest` takes `source` as free text and digests the
batch for idempotence, not for integrity. Liveness is *reported* and not *controlled*:
`TelemetryCollector.estate()` classifies a version as `silent`, `never` or `sending`, and no scheduler job
consumes it, so a principal that resolves warrants and has never reported anything raises nothing.

The reference `CaptiveEngine` is the only engine that has ever run a MAYA warrant. Everything the platform
says about governed execution outside it is a statement about a document, not about an observation.

### 4.8 The laws are the acceptance criteria, and there is no build

**The attack.** The strongest claim this design makes is that its laws are executable and that a failing
law fails the build. Show me the build.

**There is not one.** No `.github/`, no pipeline configuration of any kind, no `.importlinter`, no
`pyproject.toml`, no `ruff` or `mypy` in `requirements.txt`, no coverage threshold anywhere. The whole of
the enforcement apparatus described in [12 §2 and §7](12-implementation-plan.md) — import contracts as a CI
gate, a spec-diff gate on breaking API changes, fibre totality, SAST, SCA, a signed SBOM, migration
rehearsal — names tools that are not dependencies and files that do not exist. What exists is `pytest.ini`,
nine lines, whose only directive is to exclude the scale suite from the default run.

**The honest answer, in three parts.** First, the tests themselves are real and are the thing that matters
most: 2,246 collected, of which 2,227 run by default and 19 are the scale suite. Second, the law suite is
real — fifteen of the twenty-one foundational laws are executable, and the six that are not are named in
`tests/test_laws.py` as well as in the table, which is more than most projects manage. Third,
none of that is a *gate*. It is a suite somebody runs. A law that fails on a developer's machine and is not
run before a merge has not prevented anything, and the sentence *"a failing law fails the build"* describes
a build that does not exist.

This is the cheapest finding in this document to close and the most damaging to leave, because it is the
one that turns every other assurance in the repository from a guarantee into a habit.

### 4.9 The interface and the API are two answers to one question

**The attack.** I plan management information against the public API and find that the screens see things
the API cannot.

**The honest answer: true, measured, and named.** `routes/ui_routes.py` makes **51 direct in-process
service calls**. Writes go out through `/api/v1`; reads do not, and no read a page performs is exercised
through the API. [08 §1](08-ui-ux.md) states this as a defect rather than a design, which is the right
posture. The asymmetry does not cost authorisation, because pages and endpoints ask the same authoriser,
and it does cost the property ADR-011 exists to obtain: an API that cannot rot behind a privileged
server-side path, because it is the only path.

Note the counting error this produced, since it is the point of [§3.7](#37-a-rule-held-on-one-side-of-a-boundary)
in a different costume: two documents in this repository state that number, one says 47 and one says 51, and
the count is not one `tests/test_documentation_counts.py` derives. Fifty-one is correct.

### 4.10 A published session secret is a warning, not a refusal

**The attack.** The deployment did not set `auth.session_secret`. I read the fallback out of
`run_maya_web.py`, forge `session={"username": "admin"}`, and sign in as an administrator with no password.

**The honest answer: accepted, deliberately, and stated in the source.** `PUBLISHED_SESSION_SECRETS`
enumerates the four values that ship in the repository and `_session_secret` logs a warning naming exactly
this attack. Refusing to start was considered and rejected because it would make a workstation unusable.

That is a defensible trade and it is the weakest control shape in the platform: a warning in a log that
nobody reads on the one instance where it matters. It belongs in this list because *"we decided to accept
it"* and *"nobody has looked at it since"* are indistinguishable from the outside, and the second is how a
platform ends up in production on a public key.

---

## 5. The original twenty-seven, re-dispositioned against the code

The original review produced twenty-seven findings — six critical, nine high, eight medium, four low —
of which seventeen required redesign. Those counts are historical and are left alone. What follows is the
column that was missing: whether the control the disposition promised is in the source **today**.

A disposition is a plan. Eight of these were written as fixes and never built; five are moot, because the
thing they were about was not built either; and the rest hold, several of them more strongly than the
disposition asked for.

### 5.1 The critical findings

The headings are kept verbatim because other documents link to them by anchor.

### C-1 · The kill switch and the availability guarantee contradict each other

**Reopened.** Severity-scaled TTL is built and is doing the work. The revocation floor and the epoch check
are not — see [§4.2](#42-the-revocation-floor-cannot-fire). The residual is smaller than the finding
feared, for a reason the finding did not give.

### C-2 · The online feature store is not versioned, silently defeating the feature contract

**Closed in the only sense available, and the sense matters.** There is no online store, so the specific
defect cannot occur; what was built instead is the discipline the defect argued for. `core/features/views.py`
resolves a serving namespace as `{delta_table}/v{version}` and the docstring says *"never latest"*;
`ContractBinder` records the resolved namespace at bind time; `serving_namespaces()` computes what serving
must read, which is the half of `L-17` that can exist without a store to compare against.

The reason C-2 remains the most valuable finding in the review is that it was never a defect. It is a
**class** — *a stable identifier over moving contents* — and it has now appeared six times:

| Where | The identifier that was not a pin | How it was found | What was done |
|---|---|---|---|
| **Feature view** — the original | An online store keyed by entity, serving whatever was latest | Design review | The version *is* the namespace |
| **Featureset slots** — one level out | A slot bound to a *path*, and a path is mutable: two writes make two Delta versions and a read gets whichever is current, so a snapshot was reproducible until somebody wrote to the view again | Building the roll-forward | A binding carries the **Delta version**; reads pin to it; `restated()` answers *has anything under this pin been written to since* |
| **Feature composition** — one level in | A child named a parent, and a definition is amendable, so amending a parent silently changed every child | Building the composition fold | `FeatureCatalogue._stamp` records the parent's `definition_version` and `drift()` **reports** movement on `/features/{name}/resolved` |
| **Featureset composition** — the same thing one level up | *A combination of featuresets is a featureset* has to mean the same thing at both levels or it means nothing | Building the featureset fold | `FeaturesetRegistry._stamp` and `drift()`, deliberately the same construction, reported on `/featuresets/{name}/resolved` |
| **Documentation** | A document filed against a featureset rather than a featureset *version* would describe something that has since moved | Building the dossier | The walk follows the pins — `sb_core@v1`, never `sb_core` |
| **Warrants** | A generative warrant naming a base model family rather than a build | Writing `L-W13` | Refused at issuance; it caught a shipped example on the day it was written |

Two of those are **detectors, not freezes**, and the distinction is the reason this table has four columns.
Resolution still reads a parent as it currently stands, because a child whose parent has moved is a thing
to be told about rather than a read that should fail — and calling that a pin would repeat the original
error one abstraction higher.

Rewriting this section is also where the previous version of this document was found to be wrong. It
recorded a sixth instance as **still open** — *a featureset carries `composes` without a
`definition_version` stamp* — and that was true when it was written and had been closed since, in the same
commit that built the featureset fold. A review that records an open finding and is not re-read against the
code is a document telling a reader to go and fix something that is already fixed, which costs less than
the reverse and is the same failure.

The habit, stated so it can be applied to the next object rather than rediscovered in it: **whenever one
governed object names another, ask what the name resolves to at read time, and whether that can differ from
what it resolved to at write time.** If it can, either pin the resolution or report the drift — and say in
the document which of the two you did, because they are not the same guarantee and the word *pinned* has
now been used for both.

### C-3 · `model_version` immutability is enforced by a rule that silently discards writes

**Open, and the shipped state is different from the one the finding described.** The Postgres
`RULE ... DO INSTEAD NOTHING` was never built, so its silent-success defect never shipped. Neither was the
replacement trigger. See [§4.5](#45-immutability-has-no-enforcer). The principle the finding established —
**silence is never an acceptable enforcement mechanism for an integrity control** — did survive and is
design rule E8 in [12 §2](12-implementation-plan.md).

### C-4 · The evidence chain detects mutation but not deletion or history insertion

**Partly closed, once recurred, and the third disposition has recurred again in a new place.**

Disposition 1 is built and was built *wrongly* first, in the way that matters most: `verify_chain` re-linked
each node's **stored** `content_hash` instead of re-deriving it, so an edited payload left a chain that
verified and a record that lied. Every property C-4 was raised to obtain was absent while the verification
job reported valid. Two things about the finding of it outlast the defect. **The scale suite found it, on
its first run** — a performance suite, not a correctness one, because it happened to be the first thing to
walk a long chain with a mutated node in it. And **the unit test that should have caught it was passing for
a reason other than its name**, which is the most expensive kind of test to own because it converts an
absent control into a reported one.

What runs now re-derives from the node's own fields and checks four things in order — sequence gap,
`prev_hash`, re-derived `content_hash`, `chain_hash` — and the derivation deliberately includes
`recorded_by` and `trust`, because segregation of duties is decided entirely by reading `recorded_by` off
these nodes and a single `UPDATE` reassigning authorship turned that control off for a subject while the
chain still verified.

Disposition 2 — anchoring — remains unbuilt and is now the largest open attack
([§4.1](#41-there-is-one-database-one-identity-and-a-generic-update-on-every-table)). Disposition 4 — role
separation — is unbuilt. And disposition 3, *compare the head against the anchor rather than against
itself*, has recurred inside the incremental verifier: see
[§3.5](#35-an-anchor-written-by-the-thing-it-certifies).

### C-5 · Day-one adoption fails: 1,200 imported models are all non-compliant

**Closed, and it is the finding whose disposition survived contact best.** Imported models enter a
`baselined` lifecycle state — which turned out to be a second *initial* object in the lifecycle graph, found
by writing `L-1` rather than by reading the design, because an imported record must not enter through
`draft` or the register would imply historical evidence was asserted when it was not. Each carries dated
compliance debt for thirteen gap kinds **computed from the register rather than declared**, so an importer
cannot under-declare. Debt closes by itself when the evidence arrives, which makes the burn-down a
measurement rather than a self-report, and expires into a finding at a board-approved date per tier —
eighteen months for Tier 1, thirty for Tier 2, thirty-six below. Debt and breach are reported separately
everywhere.

### C-6 · `descriptor_only` warrants make governance dependent on client honesty

**Accepted, and four of its five mitigations are unbuilt.** See
[§4.7](#47-everything-claimed-about-an-engine-maya-does-not-run-is-unobserved).

### 5.2 The high findings

| | State in the code today |
|---|---|
| **H-1** · Cache stampede on alias move | **Moot, and the mitigation that shipped is the least important one.** There is no descriptor cache at all — no Redis anywhere in the repository, and every `resolve()` re-reads model, grant and version. So there is nothing to stampede, and also nothing meeting the latency budget the finding was defending. The one control built is **TTL jitter** (`WarrantSigner.jittered`, ±20%), which is the part that matters only once a cache exists. Pre-warm, single-flight and stale-while-revalidate are not built |
| **H-2** · The warrant plane reads the control-plane schema | **Open.** There is no `warrant_projection` table. `WarrantService.resolve` reads normalised tables one at a time — model, grant, alias, version, findings, and optionally a parameter set — five or more round trips per resolution. Since there is one process and one database, the deployment independence the finding was protecting does not exist either, so the coupling costs nothing *today* and forecloses exactly what it was raised to protect |
| **H-3** · Immutable evidence versus erasure | **Satisfied in the law, not in the mechanism.** `contains_personal_data` exists as an `INTEGER` — correctly, since a `BOOLEAN` broke the Postgres dialect once and the rule is now absolute — and the append path stores an empty payload and hashes what it stored, so the node verifies against itself. There is no `payload_uri`, no per-subject key and no crypto-shredding. There is also no `CHECK` constraint, because the schema has none at all. See [§3.4](#34-a-mechanism-named-but-not-built) |
| **H-4** · Circular and forward foreign-key references | **Moot for an unintended reason.** There are no foreign-key constraints in either dialect, so there are no cycles and no referential integrity. See [§4.5](#45-immutability-has-no-enforcer) |
| **H-5** · Row-level security is bypassable by the table owner | **Not built.** Scope is enforced in Python. See [§4.6](#46-scope-is-a-python-call-somebody-has-to-remember) |
| **H-6** · PIT verification by sampling is presented as proof | **Closed, and the restatement is the part worth keeping.** Three layers exist. Layer 1 rejects rather than samples: `core/features/pit.py::static_check` refuses an assembly missing either bound, and `TrainingSetBuilder` raises `AssemblyRejected` on it. Layer 2 is stratified — strata over label period, entity and *label value*, because a leak confined to a rare high-value segment is where uniform sampling fails and where the damage is greatest — and it recomputes through `DeltaStore.as_of` rather than through the join path, so agreement means something. Layer 3 is adversarial injection in the suite. **The honest qualification the finding demanded is still owed on layer 1:** `static_check` reads two flags off the request rather than analysing a query, and the bound is structurally guaranteed because the assembler builds the join itself — so what it refuses is a caller opting *out*, which is a real refusal and a narrower one than "static analysis of the assembly query" implies |
| **H-7** · Delta partitioning by `model_urn` explodes | **Moot.** Nothing is partitioned. `DeltaStore.write` passes no `partition_by`; isolation is by directory path — one Delta table per view version, per telemetry stream, per snapshot. No Kafka, no streaming ingest, no compaction; `vacuum_horizon_days` returns a number and vacuums nothing. The partition explosion cannot happen and neither can the scale the finding assumed |
| **H-8** · Tier gaming through input manipulation | **Open, entirely.** `exposure` is a caller-supplied float on the assessment request. There is no system-of-record binding, no `unsourced` flag, no peer-cohort outlier detection, and no retrospective calibration. What does exist is the audit half: the fact snapshot is stored with every assessment, so *what was claimed* is on the record even though nothing distinguishes a claim from a measurement |
| **H-9** · Single Postgres primary as a scaling ceiling | **Open, and one component of it was answered sideways.** There is no separate audit database, because there is no `audit_log` table at all — the evidence chain is the audit trail, deliberately, and it lives in the same database as everything else. No replicas, no monthly partitioning. The traversal cost the finding worried about was instead attacked by the checkpoint, which bought the readiness probe and left the dashboard and the document compiler paying it — [§3.6](#36-a-fix-applied-to-one-call-site) |

### 5.3 The medium and low findings

| | State in the code today |
|---|---|
| **M-1** · `Para(Stoch)` handles adaptive (T4) models awkwardly | **Closed as a documentation fix, and the code says the same thing.** `T4` requires `fit=train` **and** `adaptive`; `adaptive` with any other fit derives the fit's own class, because *continuously updating* without a training procedure is a description rather than a class |
| **M-2** · Provenance polynomials blow up exponentially | **Closed.** `MAX_TERMS = 4096`, canonical form with absorption in `_why_plus`, memoised evaluation, and an explicit truncation marker rather than a silently partial answer |
| **M-3** · Outbox writes are not idempotent | **Moot.** There is no outbox and no message bus. Idempotence is obtained differently and in two places that do work: scheduler jobs re-derive their condition and check whether the finding was already raised, and telemetry ingestion is idempotent on `telemetry_batch.digest`, which is `UNIQUE`. Notification delivery is *not* transactional — a crash between the send and the record loses or repeats a digest |
| **M-4** · Composite warrants may re-resolve members mid-execution | **Not built, and neither are composite warrants.** What exists is typed model-to-model composition: `input_to` edges type-checked under `L-21`, blast radius, shared dependencies, and a derived composite schema. `WarrantBuilder.build` takes one model and one version |
| **M-5** · `L-6` only checks machine-parseable claims | **Superseded by the honest answer.** `L-6` is not executable at all and [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces) says so: the replay that would check a summary exists for validation episodes and not for documents, so there is no `γ` |
| **M-6** · No FinOps model | **Not built.** No cost, budget or chargeback accounting. The only `COST` in the tree is the tropical semiring for remediation planning, and the only budget is a per-process memory limit in the sandbox |
| **M-7** · Deletion of a model is undefined | **Partly built.** `LifecycleService.delete` is administrators-only, requires a reason, appends evidence *before* the rows go, and leaves the chain intact. There is no legal hold, no tombstone, no retention state machine, and no cascade |
| **M-8** · Notification storms | **Answered at the wrong layer, deliberately and honestly.** A breach still raises one finding per monitor per model; the `finding` table has no root, parent or correlation column, so a shared upstream failure produces N independent findings with N owners. What was built is suppression at the last hop: one **digest per person per run**, and an unchanged worklist suppressed until a quiet period passes, because nothing is more certain to be ignored than a daily message identical to yesterday's. The storm is damped where it reaches a person and not where it is generated. [13 §9](13-ai-in-the-platform.md#9-what-the-criterion-admits-and-nobody-has-built) records correlation as an assisted capability that is not built |
| **F-1 … F-4** | Closed. `docs/README.md` is gone entirely and the root `README.md` is the single front door; the trainability override rule is moot because the class is derived and never stored; the missing DDL was supplied; ADR-008 is superseded by ADR-011, which is accepted and not built |

### 5.4 The mandated architectural change, and what it taught

The sponsor's mandate that the interface and the backend run as separate processes produced
[ADR-011](adr/ADR-011-decoupled-frontend.md), and ADR-011 is **not built**. That is recorded plainly in
[08](08-ui-ux.md), which is now organised by tense for exactly this reason.

The lesson is worth more than the architecture. One row of ADR-011's cost table said that bearer tokens on
the API mean no ambient cookie authority, so CSRF does not apply. That was true of the decoupled front end
nobody built. What runs is a Jinja interface calling the same API under a session cookie, so ambient cookie
authority is precisely what the API has. Three reviewers read the sentence and believed it, and the API had
no CSRF defence for as long as it stood.

**A control described in the future tense reads as a control, and the tense is the part people skip.** The
defence exists now, in middleware, applying to exactly one case — a state-changing method whose authority
came from the session cookie — with exemptions as exact paths rather than prefixes, so the exempt set
cannot grow as routes are added beneath it. Middleware rather than per-route, because a hundred and four
mutating endpoints is a hundred and four chances to forget.

---

## 6. What survived

A review that criticises everything is as useless as one that criticises nothing, and the elements below
were attacked deliberately and held.

| | Verdict |
|---|---|
| **The `Para(Stoch)` definition and derived trainability** | **Held, and it is the load-bearing idea.** No artefact in the taxonomy resisted presentation as a `(P, φ)` pair. `trainability_class` is a property computed from how `P` is inhabited, in eight lines, never stored and never declared — inaccessible wins over everything including a declared fit, because a vendor who says they train it has told you about their process and nothing you can govern |
| **Non-compositional aggregate risk** | **Held.** Attempts to construct a compositional yet fragility-sensitive measure failed, as the theorem requires, and the board pack says so in itself rather than producing a number that would double-count a shared dependency or ignore it |
| **Institutions for plural regulatory scope** | **Held, and strengthened past the original claim.** The satisfaction condition is checked at *activation* over probe states spanning each regime's corners, so a regime whose encoding fails it cannot be put into service — which is stronger than a build assertion in the way that matters, because a failing build can be overridden and a failing activation cannot |
| **Semiring evidence** | **Held**, with the complexity bound of M-2 and one correction the suite found rather than the design: `FRESHNESS` is not a semiring, because `max(0, 5) ≠ 0` means its zero does not annihilate, so a claim resting on a *missing* fact reports the freshness of the facts that are present. That is kept as a test so it is not quietly re-assumed |
| **The schema lattice** | **Held, and it is the best structural change since the review.** Four places asked *can this stand in for that* with four implementations, and four implementations of one order disagree eventually, in the direction of permitting more. `L-20` gives one order and `L-12`, `L-W10` and `L-21` all go through it. The meet is **partial** and informatively so: two schemas whose shared slot has two types have no meet, which is the honest answer to *can one featureset serve both models* |
| **The overlay register** | **Held.** No defects found across two reviews; still the element with no equivalent in any competing product |
| **Refusals as the product** | **Held.** 272 coded refusals mapped to fourteen HTTP statuses in one table, each carrying what was violated and what to do about it, with `tests/test_refusal_discipline.py` asserting that every code maps to a status saying who must act and that no code is mapped twice |
| **Laws as acceptance criteria** | **Held in principle, and see [§4.8](#48-the-laws-are-the-acceptance-criteria-and-there-is-no-build) for what the principle currently rests on.** Fifteen of the twenty-one foundational laws are executable, plus fourteen warrant-admissibility laws checked before every signature. `L-W8`, `L-W11` and `L-W13` each caught a real error in a shipped example on the day it was written, which is the strongest available evidence that the discipline pays for itself |
| **Sandbox honesty** | **Held, and it is the shape every other boundary in the platform should copy.** `core/execution/sandbox.py::describe` publishes what the sandbox protects against — a runaway loop, an allocation storm, a hard crash — and what it does not, which is a hostile artifact, because the child shares the filesystem and the network namespace. Saying so beats implying an isolation the process model does not provide |

---

## 7. Disposition, as it stands

| | Findings | Control in the source today | Open or moot |
|---|---|---|---|
| **Critical** | C-1 … C-6 | C-2, C-4 (partly), C-5 | C-1 reopened; C-3 open; C-4 dispositions 2–4 open; C-6 four of five mitigations unbuilt |
| **High** | H-1 … H-9 | H-6 | H-2, H-5, H-8, H-9 open; H-1, H-4, H-7 moot because the thing they were about was not built |
| **Medium / low** | M-1 … M-8, F-1 … F-4 | M-1, M-2, F-1 … F-4 | M-4, M-6 not built; M-7, M-8 partial; M-3, M-5 moot |
| **New** | [§4](#4-the-open-attacks) | — | Ten, of which [§4.1](#41-there-is-one-database-one-identity-and-a-generic-update-on-every-table), [§4.2](#42-the-revocation-floor-cannot-fire), [§4.4](#44-no-transaction-spans-a-governance-act) and [§4.8](#48-the-laws-are-the-acceptance-criteria-and-there-is-no-build) are the ones that would change what MAYA can claim |

**The four to fix first**, and the argument for that order. **A build** first, because it is a day's work
and every other assurance in this repository is currently a habit rather than a gate. **The revocation
floor** second — build it or delete it, but not the present state, where three documents describe a control
the code cannot reach. **A transaction around a governance act** third, because the mechanism exists,
nothing uses it, and the failure it leaves open is the one that lets a developer approve their own version.
**Chain anchoring** fourth, and only fourth because it depends on infrastructure somebody has to provide
rather than on effort.

---

## 8. What this review method gets wrong

Three things, stated because a method that does not name its own blind spots is the thing this document
exists to find.

**It cannot see a control that is inert for a reason outside the repository.** Every check here is a grep,
a read and a test. A control that is correct in the source and disabled by configuration, unreachable
behind a load balancer, or never invoked because the deployment does not run the scheduler is invisible to
all three. The scheduler is the concrete case: eight idempotent jobs turn computed conditions into recorded
consequences, the in-process loop is **off by default**, and an instance whose operator never wired a cron
entry has a governance platform in which no attestation ever lapses, no monitor is ever recorded as
stalled, no overlay expires, no debt reconciles, and the evidence chain is never fully verified. Nothing in
this repository can tell that instance apart from a healthy one, and `/health/ready` reports the
scheduler's own state as *informational* precisely because a stopped scheduler is not a reason to take a
node out of service.

**It over-rewards what is written down.** This review is much harder on the components with the most prose
about them, because prose is what a claim can be checked against. A module with a terse docstring and no
document offers nothing to falsify and therefore attracts no findings, which is the opposite of what should
happen. The correction is not to write less; it is to notice that an absence of findings against a
subsystem is at least as likely to mean nobody could form a claim about it.

**It has never been run by somebody else.** Both passes were performed by the same intelligence that wrote
the design, and the failure that argument predicts is exactly the one observed: the findings that changed
the platform most — C-2, C-5, the re-linked hash, the inert revocation floor — were each found by *building
the next thing* or by *running a suite for another purpose*, never by re-reading a document. A review is a
way of noticing a class. The build is where you find out how many members it has, and the scale suite is
where you find out that one of them was in the control you trusted most.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
