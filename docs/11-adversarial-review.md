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
repository: a test. Full detail in [§4.2](#42-the-revocation-floor--two-thirds-of-this-finding-aged-out-and-the-third-was-real).

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

**Closed, by deleting the rule rather than by extending the enforcer** — 2026-09-07. Recorded here
because the shape of the finding was right and the fix it implied was not.

The finding: `tests/test_schema_discipline.py` enforced the rule that broke the PostgreSQL dialect once
already — **no `BOOLEAN` columns, in either dialect** — by reading the two `.sql` files, thoroughly:
identical columns, equivalent types, no bulk data. It did not read `db/repositories.py`, where
`_BOOL_COLUMNS` was the hand-maintained list of which integer columns get coerced from a Python `bool` on
the way in. So the invariant had two halves and one enforcer. `warrant.revoked` was on the list;
`warrant_profile.retired` and `risk_appetite.retired` were not, and both were written as literal `0` and
`1`, so nothing was broken. The moment somebody wrote `retired=True`, SQLite would store `1` and
PostgreSQL would raise — precisely the failure the rule existed to prevent, arriving through the half of
the rule nothing held.

The obvious repair is to point the enforcer at the second half too. That would have worked, and it would
have preserved the thing actually generating the risk: **a column's type written twice**, once in each
`.sql` file, and a third time as a name in a Python list — with nothing tying the three together. The
repair taken instead was to remove the second and third copies. `db/schema/tables.py` is now the only
declaration, the `.sql` files are generated from it, and `_TRUTH` is *derived* from the same metadata, so
the list cannot disagree with the schema because it is no longer a list anybody writes. Truth values are
`Boolean` again. The count that made the case: the hand-kept list covered fourteen of the twenty truth
columns then in the schema, and nothing had noticed the other six.

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
is named in [10 §2](10-roadmap.md). Disposition 4, an application role holding only
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

### 4.2 The revocation floor — two thirds of this finding aged out, and the third was real

**The attack, as first written.** MAYA revokes a warrant. My engine holds a descriptor with grace remaining
and is partitioned from the control plane. C-1's disposition says a locally persisted revocation list
refuses it regardless of grace state. There is no such list: `_revoked_locally` is an unpersisted in-memory
`set`, `note_revocation` is called from no production code, the identifier it compares against is
regenerated on every resolve so the branch cannot be taken, and `revocation.epoch` starts at `0`, resets on
restart, and is compared by nothing.

**Re-checked against the source. Two of those five claims were fixed and this section did not notice**,
which is the same drift it exists to find and is worth recording rather than quietly correcting:

| The claim | Now |
|---|---|
| the compared identifier is regenerated, so the branch cannot fire | **Wrong.** `note_revocation` keys on the model URN, which survives a re-resolve, and `execute` checks the URN as well as the warrant id. The branch fires |
| the epoch resets on restart | **Wrong.** `WarrantGrants._highest_epoch` seeds it from `MAX(epoch)` in the register |
| the epoch is compared by nothing | **Right, and this was the live half** |
| `_revoked_locally` is unpersisted | **Still true**, and now stated rather than claimed away |
| `note_revocation` is called from no production code | **Still true.** MAYA has no channel to call it on |

**What was built, and it is narrower than C-1 asked for.** The epoch is stamped on every descriptor and
advances on every revocation, and *nothing read it* — a field on every warrant that nobody consults, which
is the defect this platform names as its own worst kind. So `CaptiveEngine._refuse_stale_epoch` compares it:
an engine shown epoch 7 refuses a descriptor stamped 5, because that descriptor was minted before at least
one withdrawal of authority. It is a genuine **offline** refusal — the comparison needs nothing but what the
engine has already been handed — and it catches a replay and a descriptor that waited in a queue across a
revocation.

**And the claim C-1 made is withdrawn rather than met.** The descriptor said `"check": "required"` and now
says `"check": "monotonic"`, because *required* was a claim the platform cannot back. **MAYA does not run
engines and has no channel to push a withdrawal down one**, so an engine that never sees a newer descriptor
will honour a revoked warrant until it expires. A persisted local list would not change that: the list
would still only contain what somebody told the engine, and MAYA is not the somebody.

**Disposition. C-1 closes as a narrowed control plus a withdrawn claim.** What bounds the residual is the
severity-scaled TTL, and it is stated as the whole answer rather than as a footnote: `DEFAULT_TTL = {1: 60,
2: 300, 3: 3600, 4: 3600}` with `DEFAULT_GRACE = {1: 0, 2: 0, 3: 900, 4: 900}`, so a Tier 1 descriptor
lives sixty seconds with no grace and for the models this finding was about there is almost nothing for a
floor to do. `tests/test_revocation_floor.py` pins both halves — what it refuses, and what it is not
allowed to claim. What does not stand, and no longer does, is three documents describing a floor the code
could not reach.

### 4.3 Nothing verifies a warrant without holding the key that mints one

**The attack.** I am an execution engine MAYA does not control. To verify a descriptor I need the HMAC
secret; with it I can mint any descriptor I like, for any principal, any use, any expiry.

**Closed, and not the way this finding proposed.** For two revisions the disposition here was *known,
stated, unbuilt — asymmetric signing is first in the order in [10 §3]*. That deferred a real defect to a
key hierarchy nobody had, and the deferral was the problem: the attack above is about **blast radius**,
and the proposed fix was about **provenance to a third party**. They are different problems and only one
of them was mine.

The blast radius is now contained without asymmetry. `core/execution/signing.py` derives each audience's
key from the root and that audience's own principal — `HMAC(root, "maya/warrant/v<gen>/" ‖ audience)` — so
the engine in the attack above holds a key that signs warrants **for itself and for nobody else**. The
derivation is one-way, so it cannot walk back to the root and cannot reach another engine's key. The
audience is read from the document being verified, so re-pointing a warrant I legitimately hold at another
principal breaks its signature rather than needing a check somebody remembered to write.

What remains true, and is now published at `GET /warrant-signing` rather than buried in this document: a
verifier holds the key it verifies with, so **a descriptor proves authorship to the bank and not to
anybody outside it**. That is non-repudiation, it is a different requirement from this finding, and no
reader of MAYA has asked for it. The `descriptor_only` flavour is no longer the aggravating factor it was
described as here — those engines hold their own key precisely because they are the ones MAYA does not
run, and that is now the point rather than the exposure.

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
constraints in either dialect — the schema contains zero of each. What `db/schema/tables.py` contains
is a comment: *"Versions are immutable. There is no UPDATE path other than status."* That is a description
of current callers, written where a reader expects a constraint.

**Built, in the half that was being claimed.** C-3's disposition — a `BEFORE UPDATE` trigger raising on any
change to an immutable column — now exists in both dialects, generated from `db/schema/immutable.py` and
**applied by `Database._apply_enforcement`** rather than only rendered into the `.sql` files. That last
part is the one worth checking in any similar fix: `create_all` builds from the typed metadata and never
reads those files, so a trigger living only in the rendered schema would have been the same defect one
level along — a constraint where a reader expects one, enforced by nothing.

Fourteen columns of `model_version` are guarded and `status` deliberately is not, because it is the one
field the lifecycle moves and the comment this replaces said so. `evidence_node` is append-only against
both `UPDATE` and `DELETE`. Every trigger **raises**: C-3 was raised against a rule that silently discarded
the write, and design rule E8 — *silence is never an acceptable enforcement mechanism* — is what survived
it. `tests/test_immutability_enforcer.py` attacks each declared column individually, because declared and
rendered is not enforced.

**The referential half is now a decision rather than a gap** — [ADR-015](adr/ADR-015-no-foreign-keys.md).
There are no foreign keys and there will not be: `core/references/index.py` refuses a deletion that
anything still refers to and *names what refers to it*, where a constraint would say `FOREIGN KEY
constraint failed` and leave somebody guessing which of twenty tables objected; and with
`CREATE TABLE IF NOT EXISTS` and no migrations, a constraint added later would reach a fresh install and
never a deployed one, which is worse than none. What it costs is stated in the ADR rather than here: orphan
rows are possible by any path that does not go through the index, and nothing in the database will say so.

**And the trigger is defence in
depth rather than the control** on the chain: a mutated row can still arrive by a path it does not cover —
a restore from a backup taken before it existed, a replica fed by something that does not carry triggers,
a database whose role could not create one, which `_apply_enforcement` warns about and carries on from.
`verify_chain` is still what detects that, and the evidence suite still proves it by standing the trigger
down to make the row it then catches.

The absence of foreign keys deserves its own sentence, because it silently resolves **H-4**. That finding
was about circular and forward references making the DDL uncreatable, dispositioned as
`DEFERRABLE INITIALLY DEFERRED` constraints created in a dedicated step. What shipped has no referential
integrity in the database at all, so the cycles are gone and so is every other guarantee an FK would have
given. `LifecycleService.delete` hard-deletes a `model` row and leaves its versions, warrants, findings and
monitors orphaned; the evidence is retained, which is the important half, and the register is not.

### 4.6 Scope is a Python call somebody has to remember

**The attack.** I am a validator scoped to one legal entity. I look for a listing endpoint whose author
forgot `Scope.filter`.

**Closed, and the blocker named in the old disposition is what moved.** This section used to say *there is
no database backstop; RLS is not built, and there is one connection identity, so it would have nothing to
distinguish anyway.* The second half was the real obstacle and it is gone: `routes/base.py::_identify` now
puts the acting principal's entity scope on the connection the request is using, transaction-scoped so a
pooled connection carries nothing to the next request, and the policies in `core/security/rls.py` read it.

`core/authz/scope.py` remains **the control** and this is a backstop under it — deliberately, because RLS
produces *no rows* rather than a refusal, and an empty list is indistinguishable from *there is nothing*.
What it covers is the case the control cannot: the listing endpoint somebody wrote last week and forgot to
filter.

Two things make it real rather than decorative, and the second was found by running it against a real
PostgreSQL 16 rather than by reasoning about it. `FORCE ROW LEVEL SECURITY` binds the table *owner*, and
with the session variable unset a non-superuser owner reads **zero rows** — the policy holds. But a
**superuser bypasses row-level security entirely**, `FORCE` or not, so a deployment can apply every
statement perfectly, connect as `postgres`, and have a backstop that does nothing while the configuration
looks correct. `GET /api/v1/row-level-security` therefore reports the connecting role's exemption
alongside the table flags, because that is the fact which decides whether any of the rest of it is true.

Two things make that better than it sounds and neither makes it safe. The first is that the same defect
already happened and was fixed structurally: listings filtered while directly-addressable pages did not, so
a validator who was correctly shown nothing on the dashboard could load the model page by URL and receive
its versions, alias history, warrant grants and evidence chain. `routes/base.py::may_view` now applies the
API's own rule to every page that resolves a named object. The second is that filtering happens **before**
paging, so page two of a filtered list is not page two of the unfiltered one with holes in it.

The negative test **H-5** actually asked for now exists — `tests/test_row_level_security.py`, a
cross-entity read that must return zero rows. It runs against a real PostgreSQL and **skips loudly**
without one, which is the honest arrangement rather than a compromise: asserting the policy text is not a
test of the policy, and a green suite that never ran a cross-entity read would be exactly the assurance
this finding objected to. `MAYA_TEST_POSTGRES=postgresql://…` runs it; `deploy/compose.yaml` stands up a
database with the two roles already separated.

What remains open is what row-level security cannot reach: rows that do not *carry* an entity. A version's
entity is its model's and a finding's is its model's, and expressing that as a policy is a subquery per row
on every read. `SCOPED_TABLES` is the list rather than a claim of completeness, and everything reached
through those tables is still the application's job.

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

### 4.8 The laws are the acceptance criteria, and there is now a build

**The attack.** The strongest claim this design makes is that its laws are executable and that a failing
law fails the build. Show me the build.

**When this section was written there was not one.** No `.github/`, no pipeline configuration of any kind,
no `pyproject.toml`, no `ruff` or `mypy` in the requirements, no coverage threshold anywhere. The whole of
the enforcement apparatus described in [12 §2 and §7](12-implementation-plan.md) named tools that were not
dependencies and files that did not exist. What existed was `pytest.ini`, nine lines, whose only directive
was to exclude the scale suite. The finding stood: *a law that fails on a developer's machine and is not
run before a merge has not prevented anything*, and the sentence *"a failing law fails the build"*
described a build that did not exist.

**It exists now**, and the finding is left in place rather than deleted, because what closed it is the
better half of the answer.

`.github/workflows/ci.yml` runs seven jobs on every push and pull request, and each is a refusal rather
than a report:

| Job | What fails the build |
|---|---|
| **Hygiene** | `ruff` over the whole tree; `mypy` gated on the modules that check clean, with the rest carried in `tools/ci/mypy_backlog.txt` so the backlog can only shrink; `pip-audit`; a signed SBOM; a secret scan that plants a private key to prove it can still see one |
| **Discipline** | The counts in this documentation against the code, refusal codes against their HTTP statuses, logging, imports, schema and file size — each its own suite |
| **Laws** | `tests/test_laws.py` and `tests/test_grammar.py` on their own, so a failing law is legible in the run list rather than buried among three thousand others |
| **Deck** | Slide geometry, because a deck that overflows its frame is a deck nobody can show |
| **Suite** | Four shards, each fanned across the runner's cores, over the full 3,914 tests |
| **Coverage** | Combined across the shards against a floor of 90% — a floor, not a target, set to catch a release that deletes tests |
| **Postgres** | The same suite against the other dialect, because a `BOOLEAN` column once broke it silently, and one declaration rendering to two dialects is a claim only the other dialect can check |

A spec-diff gate (`tools/ci/spec_lock.py`) refuses an unannounced change to the public API: the OpenAPI
document is locked, and a diff has to arrive in the same commit that made it.

**What is still true.** Eighteen of the twenty-one foundational laws are executable, and the three that
are not are named in `tests/test_laws.py` as well as in the table. That count was *sixteen* in this
paragraph and in nine other places for two milestones after `L-14` and `L-17` started running — which is
the same defect as this section, one level up: a check that exists to stop a number drifting, written
narrowly enough to miss the drift.

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

That was a defensible trade and it was the weakest control shape in the platform: a warning in a log that
nobody reads on the one instance where it matters. It belonged in this list because *"we decided to accept
it"* and *"nobody has looked at it since"* are indistinguishable from the outside, and the second is how a
platform ends up in production on a public key.

**Closed by taking the warning's own condition seriously.** The warning already named it — *before this
instance is reachable by anybody else* — so that is the refusal:
`_refuse_published_secret_on_a_reachable_address` stops the process before the app is built when a
published secret meets a bind address another machine can reach. Bound to loopback, a published secret
still starts and still warns, so the trade that rejected refusing outright survives intact: a developer on
`127.0.0.1` is not the deployment this protects. Neither half alone is the finding — a published secret on
a workstation is a workstation, and a real secret on a public interface is a deployment — and
`tests/test_published_secret.py` pins both.

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
are not — see [§4.2](#42-the-revocation-floor--two-thirds-of-this-finding-aged-out-and-the-third-was-real). The residual is smaller than the finding
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

**Closed, and the shipped state was never the one the finding described.** The Postgres
`RULE ... DO INSTEAD NOTHING` was never built, so its silent-success defect never shipped. The replacement
trigger was not built either, for a milestone, and now is — raising rather than discarding, in both
dialects. See [§4.5](#45-immutability-has-no-enforcer). The principle the finding established —
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

Disposition 2 — anchoring — **is built and this paragraph said otherwise for a milestone**:
`core/evidence/anchor.py` holds `ChainAnchor` and `core/evidence/worm.py` a filesystem WORM store, wired in
`run_maya_web.py`. What the original finding asked for beyond that is an anchor written somewhere the
platform cannot reach, and a filesystem the same process can write is a weaker thing than an external
notary — so this closes as *built, and narrower than the finding imagined*, not as met. Disposition 4 —
role separation — is unbuilt. And disposition 3, *compare the head against the anchor rather than against
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
| **H-3** · Immutable evidence versus erasure | **Satisfied in the law, not in the mechanism.** `contains_personal_data` exists as a `Boolean` in `db/schema/tables.py`, rendered to both dialects from that one declaration — and the append path stores an empty payload and hashes what it stored, so the node verifies against itself. There is no `payload_uri`, no per-subject key and no crypto-shredding. There is also no `CHECK` constraint, because the schema has none at all. See [§3.4](#34-a-mechanism-named-but-not-built) |
| **H-4** · Circular and forward foreign-key references | **Moot for an unintended reason.** There are no foreign-key constraints in either dialect, so there are no cycles and no referential integrity. See [§4.5](#45-immutability-has-no-enforcer) |
| **H-5** · Row-level security is bypassable by the table owner | **Closed.** `core/security/rls.py`, with `FORCE` so the owner binds, a non-owner application role, a default-deny policy over a per-request session variable, and the cross-entity negative test the finding asked for. The exemption one level below — a superuser bypasses RLS entirely — is *reported* rather than assumed. Scope in Python remains the control; this is the backstop. See [§4.6](#46-scope-is-a-python-call-somebody-has-to-remember) |
| **H-6** · PIT verification by sampling is presented as proof | **Closed, and the restatement is the part worth keeping.** Three layers exist. Layer 1 rejects rather than samples: `core/features/pit.py::static_check` refuses an assembly missing either bound, and `TrainingSetBuilder` raises `AssemblyRejected` on it. Layer 2 is stratified — strata over label period, entity and *label value*, because a leak confined to a rare high-value segment is where uniform sampling fails and where the damage is greatest — and it recomputes through `DeltaStore.as_of` rather than through the join path, so agreement means something. Layer 3 is adversarial injection in the suite. **The honest qualification the finding demanded is still owed on layer 1:** `static_check` reads two flags off the request rather than analysing a query, and the bound is structurally guaranteed because the assembler builds the join itself — so what it refuses is a caller opting *out*, which is a real refusal and a narrower one than "static analysis of the assembly query" implies |
| **H-7** · Delta partitioning by `model_urn` explodes | **Moot.** Nothing is partitioned. `DeltaStore.write` passes no `partition_by`; isolation is by directory path — one Delta table per view version, per telemetry stream, per snapshot. No Kafka, no streaming ingest, no compaction; `vacuum_horizon_days` returns a number and vacuums nothing. The partition explosion cannot happen and neither can the scale the finding assumed |
| **H-8** · Tier gaming through input manipulation | **Mostly closed** — `core/risk/sourcing.py`. The audit half always worked; what was missing was the difference between a **claim and a measurement**, and a register that cannot make that distinction presents both with the same confidence. A tiering fact is now attested to a named system of record with a **reference somebody can look it up by** — required, because *finance said so* is unfalsifiable a year later. Three states, and `stale` is not a demotion to `asserted`: a figure that *was* measured and has aged needs a refreshed extract, not an investigation. Peer-cohort comparison exists and deliberately **raises no finding** — a cohort of four is not a distribution, business lines differ by orders of magnitude, and a control that cried wolf at every small book would be switched off. Two things it does not do, both on purpose: it **fetches nothing**, because a register holding read credentials to the general ledger is trusted with one more thing than it needs; and it **refuses no unsourced fact**, because a register nobody can register into produces *unregistered* models, which is strictly worse than a tiered-from-a-guess one. Retrospective calibration is still not built |
| **H-9** · Single Postgres primary as a scaling ceiling | **Open, and one component of it was answered sideways.** There is no separate audit database, because there is no `audit_log` table at all — the evidence chain is the audit trail, deliberately, and it lives in the same database as everything else. No replicas, no monthly partitioning. The traversal cost the finding worried about was instead attacked by the checkpoint, which bought the readiness probe and left the dashboard and the document compiler paying it — [§3.6](#36-a-fix-applied-to-one-call-site) |

### 5.3 The medium and low findings

| | State in the code today |
|---|---|
| **M-1** · `Para(Stoch)` handles adaptive (T4) models awkwardly | **Closed as a documentation fix, and the code says the same thing.** `T4` requires `fit=train` **and** `adaptive`; `adaptive` with any other fit derives the fit's own class, because *continuously updating* without a training procedure is a description rather than a class |
| **M-2** · Provenance polynomials blow up exponentially | **Closed.** `MAX_TERMS = 4096`, canonical form with absorption in `_why_plus`, memoised evaluation, and an explicit truncation marker rather than a silently partial answer |
| **M-3** · Outbox writes are not idempotent | **Moot.** There is no outbox and no message bus. Idempotence is obtained differently and in two places that do work: scheduler jobs re-derive their condition and check whether the finding was already raised, and telemetry ingestion is idempotent on `telemetry_batch.digest`, which is `UNIQUE`. Notification delivery is *not* transactional — a crash between the send and the record loses or repeats a digest |
| **M-4** · Composite warrants may re-resolve members mid-execution | **Not built, and neither are composite warrants.** What exists is typed model-to-model composition: `input_to` edges type-checked under `L-21`, blast radius, shared dependencies, and a derived composite schema. `WarrantBuilder.build` takes one model and one version |
| **M-5** · `L-6` only checks machine-parseable claims | **Superseded by the honest answer.** `L-6` is not executable at all and [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces) says so: the replay that would check a summary exists for validation episodes and not for documents, so there is no `γ` |
| **M-6** · No FinOps model | **Built, in the only shape this platform can honestly take** — `core/estate/cost.py`. MAYA does not run models, so it **does not observe cost**: a figure it computed would be a price somebody typed multiplied by a call count it also did not observe, printed as a measurement. Cost arrives attested, over a stated period, from a named source. What MAYA adds is the half nobody else can — **attribution from the register's own ownership**, copied at record time so a report for last quarter says who owned it last quarter rather than who holds it today. The headline is not the total (a bill has that) but the **share nobody attributed**: a bill is complete by construction, so an unattributed cost looks exactly like an attributed one until somebody asks who owns it. Budgets **enforce nothing** — MAYA is not on the serving path and cannot decline the next invocation — and a breach raises a finding with an owner. Currencies are reported and never summed across |
| **M-7** · Deletion of a model is undefined | **Mostly built, and re-checking it found the live half.** `LifecycleService.delete` is administrators-only, requires a reason, appends evidence *before* the rows go, and leaves the chain intact. The *"there is no legal hold, no retention state machine"* this row carried was stale — `core/retention/holds.py` and `core/retention/schedule.py` have both existed for a milestone. What was true, and worse, is that **the deleter did not consult the hold**: `LegalHolds.held` has documented itself as *"the question a deleter asks"* since it was written, holds were checked by the inference log and the retention schedule, and the one act with no workflow, no reversal and no second signature never asked. A model under an active hold could be destroyed while the module that would have refused it sat in the same process. Now refused as `under_legal_hold`, before the evidence node, with no override — a hold a deletion could step over would not be a hold. Still no tombstone and no cascade |
| **M-8** · Notification storms | **Answered twice now, at both layers, and the first answer was the honest one available at the time.** `core/validation/correlation.py` adds a **root**: a cause named once, with the findings it produced hanging off it. It **merges nothing** — each finding keeps its own owner, model and due date, because a model whose feature stopped landing has a real problem whatever caused it, and dissolving twelve findings into one leaves eleven models with a live defect and nothing in their own record saying so. Correlation is **asserted, never inferred**: the platform can *suggest* candidates (same source, same category, one window, several models) and nothing is grouped until a person says so, because a guess that grouped two unrelated findings would hide one behind the other's closure. And **addressing a root closes no finding** — each needs its own closure with its own verifier, since a root that closed its children would be one act discharging obligations several different people owe. What changes is the counting: suppression damped the storm where it reached a person, and this damps it where it is *counted*, so a board pack showing twelve open findings in one domain can say they are one problem. The original answer, below, still runs. **Answered at the wrong layer, deliberately and honestly.** A breach still raises one finding per monitor per model; the `finding` table has no root, parent or correlation column, so a shared upstream failure produces N independent findings with N owners. What was built is suppression at the last hop: one **digest per person per run**, and an unchanged worklist suppressed until a quiet period passes, because nothing is more certain to be ignored than a daily message identical to yesterday's. The storm is damped where it reaches a person and not where it is generated. [13 §9](13-ai-in-the-platform.md#9-what-the-criterion-admits) records correlation as an assisted capability that is not built |
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
cannot grow as routes are added beneath it. Middleware rather than per-route, because two hundred and thirty-seven
mutating endpoints is a hundred and fourteen chances to forget.

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
| **Laws as acceptance criteria** | **Held in principle, and see [§4.8](#48-the-laws-are-the-acceptance-criteria-and-there-is-now-a-build) for what the principle currently rests on.** Eighteen of the twenty-one foundational laws are executable, plus fourteen warrant-admissibility laws checked before every signature. `L-W8`, `L-W11` and `L-W13` each caught a real error in a shipped example on the day it was written, which is the strongest available evidence that the discipline pays for itself |
| **Sandbox honesty** | **Held, and it is the shape every other boundary in the platform should copy.** `core/execution/sandbox.py::describe` publishes what the sandbox protects against — a runaway loop, an allocation storm, a hard crash — and what it does not, which is a hostile artifact, because the child shares the filesystem and the network namespace. Saying so beats implying an isolation the process model does not provide |

---

## 6a. The third pass: attacking four controls the week they shipped

The two earlier passes reviewed a design. This one attacked **four modules built in a single wave** —
decommissioning (`FR-INV-018`), the delegated authority matrix (`FR-LC-005`), access recertification
(`FR-SEC-005`) and the CLI (`FR-PLT-002`) — before anything but their own suites had touched them. Ten
hypotheses were written as failing tests; **nine reproduced**.

That hit rate is the finding underneath the findings. Every one of the four modules is *about* a control
that looks enforced and is not; each shipped with a defect of exactly that shape. A module argues its own
correctness most persuasively in the paragraph where it is wrong.

### 6a.1 Withdrawing a band moved the bar under an approval people were signing

The `version_approval.band` column carried a comment saying the bar could not move mid-approval. It moved.
`required_roles` was frozen onto the approval, but **sequencing was re-derived from the live matrix at
signing time** — so withdrawing or re-publishing a band silently changed the order an open approval was held
to, and an administrator could relax second-line challenge on an approval already in flight without touching
it.

The fix is the one the column was reaching for: the **stages travel with the approval**, and
`refuse_out_of_sequence` is now a pure function over them that cannot reach the matrix at all. The read that
answers *what would this be sequenced as* is a separate method, `sequence_for`, and only the read consults
the matrix.

> The general lesson: freezing the *name* of a rule does not freeze the rule. Either the decision travels
> with the record, or it will be recomputed against whatever is true later.

### 6a.2 A ceiling in one currency authorised an exposure in another

`delegate()` stores a currency. A sourced exposure has none — `tiering_fact_source` holds a number and no
unit, **and so do the tiering bands it is graded against**. So `500,000,000` JPY was compared against an
exposure of `200,000,000` as bare numbers, silently, in the permitting direction.

This is the platform's own position violated: `core/estate/cost.py` refuses to sum currencies for exactly
this reason. The fix states the assumption that had been load-bearing and unwritten since tiering was
built — every exposure in the register is read as the estate's **reporting currency** — and refuses the
comparison by name (`ceiling_not_comparable`) where a delegation is in any other. The tiering bands share
the blindness; this is the first place it had to be written down.

### 6a.3 A decommissioning record for a model still in service

The module's own docstring promises that everything is validated **before** the transition, so a refusal
leaves the model in service. It validated the four *facts* before the transition, then wrote the record and
attempted the retirement as two acts. `retire` is not reachable from `submitted` or `amending` — so the
record landed, the transition raised, and the register held a decommissioning for a model still in force.

Legality is now checked first, from the state machine rather than from a list repeated here, so a seventh
state cannot be added without this seeing it. A second decommissioning is refused as
`already_decommissioned` rather than arriving as an `IntegrityError`: *why was this taken out* is not a
question that may have two answers.

### 6a.4 The reviewer column nothing read

`recertification.reviewer` was recorded on every campaign and **never consulted**. Anybody holding
`principal:manage` could answer any campaign, and the column was decoration — which is precisely the
eleventh edge ([18 §3.11](18-the-registers-edges.md)) pointed at this repository's own new code, three days
after that section was written.

The named reviewer is now the only person who may answer, and handing a campaign over is `reassign`: an act
with a reason, because reviewers leave, go on secondment, and turn out to be in the population they were
asked to review.

### 6a.5 Revoking the last administrator, through a door the guard did not cover

`suspend` has always refused to remove the last principal who can administer principals. `set_roles` did
not — and revoking an access recertification calls `set_roles`. The guard existed, the second caller did
not exist when it was written, and recertification is the first thing that calls it over a population
including the administrators.

Fixed in `set_roles`, not in the caller, which closes it for every future caller too. **This is the whole
argument for building the thing that exercises an old control**: the hole was a year old and invisible
until something new walked into it.

### 6a.6 An answer from 2019 read exactly like yesterday's

`across_the_estate()` counted whether an account had **ever** been answered. A confirmation two and a half
years old was indistinguishable from one made this morning, which is the shape of every access review run
once and reported afterwards as a standing control. `overdue` is now its own population, keyed on the
latest answer per account against the expected cadence.

### 6a.7 An unreadable verdict exited zero

The CLI's contribution is that 1 (*MAYA refused*) and 2 (*MAYA was not reached*) are different, so a
pipeline cannot read an outage as compliance. A verdict-shaped command whose verdict field was **absent**
exited **0** — the identical defect one layer in, and the module's own test asserted that it should.

An absent verdict is now `UNDETERMINED`, exit 2. Not a yes.

### 6a.8 What did not reproduce, and the two that were races

One hypothesis failed to reproduce: a lapsed delegation already named expiry in its remediation. Two others
were the familiar read-then-write shape — a duplicate band name and a duplicate decommissioning both
surfaced as `IntegrityError`, i.e. a 500 where a refusal belonged. That is the same class as the dual-hat
quorum race found in the second pass, and finding it twice says the pattern needs a habit rather than a
fix: **any check that reads before it writes needs the unique index behind it and the `IntegrityError`
translated back into the refusal the reader was going to get anyway.**

### 6a.9 What this pass says about the method

[§8](#8-what-this-review-method-gets-wrong) claims the findings that change the platform most are found by
*building the next thing*, never by re-reading a document. This pass is the counter-example and the
qualification at once. The nine were found by re-reading — but only by re-reading **code written days
earlier against the documents that describe what it should do**, where the prose was fresh enough to be
checked line by line against the implementation and specific enough to be falsified. Two of the nine are
literally the module contradicting its own docstring.

The transferable rule: **attack a module in the paragraph where it is most confident.** Every one of these
four modules is about a control that reports itself as enforced while enforcing nothing, and every one of
them shipped with a defect of that exact shape.

---

## 7. Disposition, re-derived from the source

**This table was wrong, and how it was wrong is the useful part.** It is a summary of sections that were
themselves kept current, and it drifted from them: it recorded M-6 as *not built* while [§5.3](#53-the-medium-and-low-findings)
said **Built** and `core/estate/cost.py` had existed for a milestone; it recorded M-8 as *partial* after
`core/validation/correlation.py` closed it at both layers; it omitted H-3 from every column; and its
priority list opened with *build a CI pipeline* while [§4.8](#48-the-laws-are-the-acceptance-criteria-and-there-is-now-a-build)'s
own heading already said there was one.

`tests/test_documentation_counts.py` catches a number that drifts. Nothing catches a **disposition** that
drifts, and a review whose summary is stale is worse than one with no summary, because the summary is what
gets read. Every row below was re-checked against the code on 2026-09-12.

**Two tests now guard part of this** — one asserting no finding is answered in its own section and open in
this table, one asserting every source file the review cites exists. Both have a blind spot worth stating:
they compare the document against *itself* and against *filenames*. M-7 and C-4 were stale in their own
**detail** rows, which no test can see, and re-checking those against the code is what found a legal hold
the deleter never asked about. **The audit is the control; the tests only stop it rotting between audits.**

| | Closed, with the control in the source | Moot | Open |
|---|---|---|---|
| **Critical** | C-2, C-5; **C-1** (narrowed control, withdrawn claim — [§4.2](#42-the-revocation-floor--two-thirds-of-this-finding-aged-out-and-the-third-was-real)); **C-3** (the enforcer exists and raises); **C-4 disposition 2** (anchoring is built) | — | C-4 dispositions 3–4; C-6, four of five mitigations |
| **High** | H-5, H-6, H-8 (mostly) | H-1, H-4, H-7 — the thing they were about was never built | H-2; H-3 (satisfied in the law, not the mechanism); H-9 |
| **Medium / low** | M-1, M-2, **M-6**, **M-7** (the deleter now asks the hold), **M-8**, F-1 … F-4 | M-3, M-5 | M-4 (composite warrants are not built either); M-7's tombstone and cascade |
| **The ten attacks** | **§4.4** (152 `evidence.recording()` blocks span the act and its record; it said *nothing does*), **§4.8** (`.github/workflows/ci.yml`), §4.2, **§4.5** — immutability enforced, referential half **decided** ([ADR-015](adr/ADR-015-no-foreign-keys.md)), **§4.10** (a published secret on a reachable address now refuses to start) | — | **§4.9 accepted**: the interface reads in-process, named as a defect in [08 §1](08-ui-ux.md) and answered by ADR-011, which is accepted and not built |
| **§4 answered as refusals** | §4.1 and §4.6 — RLS is built and is a **backstop**; scope in Python remains the control. §4.3 — per-audience key derivation, with `does_not_prove: authorship to a third party` published. §4.7 — *attested, not observed* | | |
| **Third pass** ([§6a](#6a-the-third-pass-attacking-four-controls-the-week-they-shipped)) | all nine | — | — |

**What is genuinely left, in the order it is worth doing.**

**Nothing structural is left open.** §4.5 is closed in both halves: immutability is enforced by sixteen
triggers in SQLite and four statements in PostgreSQL, applied at schema time and attacked column by column
in the suite; and the referential half is a recorded decision rather than a gap
([ADR-015](adr/ADR-015-no-foreign-keys.md)) — the reference index is the control, it gives a better refusal
than a constraint would, and a constraint added under `CREATE TABLE IF NOT EXISTS` with no migrations would
reach only new databases.

**H-2, H-9 and §4.9 are one finding in three costumes, and none of them is a defect to fix here.** All
three are about a boundary that a single-process, single-database deployment has not drawn: the warrant
plane reads the control-plane schema, there is one primary, and the interface reads in-process rather than
through its own API. Every one of them costs **nothing today** and forecloses something later, and the
thing they foreclose is *deployment independence* — which is a topology decision
([19](19-deploying-maya.md)), not a code change. They stay open rather than being marked accepted, because
the day the platform is deployed as more than one process they all become real at once, and a reader
planning that deployment needs to find them.

**C-6 and M-4** are not work items in the ordinary sense: `descriptor_only` honesty and composite warrants
are both about capabilities this platform deliberately does not have. They stay listed because a reader who
finds them elsewhere should find them here too.

**Nothing else is open.** Every remaining row in the table above is closed, moot, or a recorded decision
with the cost of closing it written down.

---

## 8. What this review method gets wrong

Three things, stated because a method that does not name its own blind spots is the thing this document
exists to find.

**It cannot see a control that is inert for a reason outside the repository.** Every check here is a grep,
a read and a test. A control that is correct in the source and disabled by configuration, unreachable
behind a load balancer, or never invoked because the deployment does not run the scheduler is invisible to
all three. The scheduler is the concrete case: 26 idempotent jobs turn computed conditions into recorded
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
