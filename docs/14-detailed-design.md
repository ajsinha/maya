# 14 — Detailed Design

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Level.** One below [04 — Architecture](04-architecture.md). Where 04 answers *what the containers are and
why*, this answers *what each component does inside*: the interface it exposes, the order of its steps, the
decision that shaped it, and the thing it refuses.

**Audience.** Whoever has to change this code, and whoever has to decide whether to trust it.

---

## 0. The rule this document obeys

A detailed design earns its name only when a reader can go from a section to the file it describes and find
the thing the section promised. The previous version could not, in enough places to matter: it described a
Kafka event stream, a Redis descriptor cache, a Celery worker fleet, a Spark job, Postgres row-level
security, an online feature store, Ed25519 signing, a plugin loader, and a browser front end built on
server-side DataTables and a Cytoscape graph. **None of those exists.** Some are on the roadmap, some were
abandoned, and one — the graph page — was described so confidently that a reader would have gone looking for
a vendored library in a repository whose whole asset budget is six files.

So one rule governs every sentence below, and it is the same rule [08](08-ui-ux.md) adopted for the same
reason:

> **The present tense means it runs.** If a mechanism is described in the present indicative, it is in the
> source and a path is given. Anything designed and not built lives in
> [Part VI](#part-vi--designed-and-not-built), in the conditional, with the reason it is not built.

Two consequences worth stating rather than discovering. First, this document is *shorter on infrastructure
and longer on algebra* than a detailed design usually is, because that is the actual shape of the system.
Second, several sections end with a paragraph naming what the section does **not** cover; those paragraphs
are the most useful part of the document, because a design that only says what it does reads as complete.

The authoritative record of what exists at all is
[12 §0](12-implementation-plan.md#0-build-status); the order the remaining work should be done in is
[10](10-roadmap.md). This document does not duplicate either.

---

## Table of contents

**Part I — Foundations**
[1 The shape of the built system](#1-the-shape-of-the-built-system) ·
[2 The rules that bind every component](#2-the-rules-that-bind-every-component) ·
[3 Core domain](#3-core-domain) ·
[4 Registry, versions and composition](#4-registry-versions-and-composition)

**Part II — Governance subsystems**
[5 Evidence](#5-evidence) ·
[6 Risk and tiering](#6-risk-and-tiering) ·
[7 Regimes as institutions](#7-regimes-as-institutions) ·
[8 Versioned gates](#8-versioned-gates) ·
[9 Lifecycle, approval and attestation](#9-lifecycle-approval-and-attestation) ·
[10 Validation and findings](#10-validation-and-findings) ·
[11 Documentation](#11-documentation)

**Part III — Data and execution**
[12 The feature platform](#12-the-feature-platform) ·
[13 Monitoring and telemetry](#13-monitoring-and-telemetry) ·
[14 Warrants](#14-warrants) ·
[15 Machine assistance](#15-machine-assistance) ·
[16 Reporting, baseline and the operational jobs](#16-reporting-baseline-and-the-operational-jobs)

**Part IV — Interfaces**
[17 The HTTP surface](#17-the-http-surface) ·
[18 Authorisation](#18-authorisation) ·
[19 The interface and the SDK](#19-the-interface-and-the-sdk)

**Part V — Cross-cutting**
[20 Persistence and transactions](#20-persistence-and-transactions) ·
[21 Concurrency and idempotency](#21-concurrency-and-idempotency) ·
[22 Refusals](#22-refusals) ·
[23 Observability](#23-observability) ·
[24 Performance, and what is actually measured](#24-performance-and-what-is-actually-measured) ·
[25 Testing design](#25-testing-design)

**[Part VI — Designed and not built](#part-vi--designed-and-not-built)**

---

# Part I — Foundations

## 1. The shape of the built system

One Python process. One relational database, SQLite by default and PostgreSQL by URL alone. One Delta
Lake root on the filesystem for the data plane. No message broker, no cache tier, no worker fleet, no
container orchestration, no second process for anything.

```
        browser ──── HTTP ────┐
        SDK / engine ─────────┤
                              ▼
                     ┌──────────────────┐
                     │  one FastAPI app │   routes/  (232 registrations)
                     │  routes/base.py  │   203 under /api/v1, 29 unprefixed
                     └────────┬─────────┘
                              ▼
                     ┌──────────────────┐
                     │  core/           │   27 packages, no framework imports
                     └────────┬─────────┘
                              ▼
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌──────────────────┐            ┌──────────────────┐
    │  db/  —  51 tables│            │  Delta on disk   │
    │  SQLite | Postgres│            │  feature values, │
    │  no migrations    │            │  telemetry,      │
    └──────────────────┘            │  snapshots       │
                                     └──────────────────┘
```

Four properties of that shape are load-bearing and are worth stating before any component is described.

**The control plane and the data plane are separated by size, not by ceremony.** Anything a person reads one
at a time — a model, a version, a finding, an evidence node — is a row. Anything that runs to hundreds of
millions of rows lives in a versioned table format, and the register keeps a `delta_table` and a
`delta_version` that together name exactly which bytes a read gets. `tests/test_schema_discipline.py`
holds both halves of that: no relational table may grow a `rows` or `values` column, and the four tables
that own bulk data must name their table location.

That format is **Delta or Iceberg, by configuration** — `db/table_backend.py` chooses once at start-up,
`db/delta_store.py` and `db/iceberg_store.py` offer the same surface, and nothing above `db/` asks which.
Delta is the default. The columns are named for it and stay named for it, because what they hold is *the
version this read is pinned at* and that concept does not change with the format; they are `BigInteger`
because an Iceberg snapshot id is int64 and would not fit an `INTEGER` on PostgreSQL. Separately,
`db/delta_backend.py` chooses between two *implementations* of Delta — the compiled `deltalake` and
MAYA's own pure-Python `maya_deltalake/` — for estates that forbid binary wheels. Two independent
choices: [07 §9.3](07-feature-platform.md) is the second, [§9.4](07-feature-platform.md) the first.

**There are no migrations, on purpose.** `db/schema/tables.py` *is* the schema — fifty-one typed SQLAlchemy
Core tables, from which the DDL for each dialect is generated. `db/schema/sqlite.sql` and `postgres.sql`
are rendered from it by `tools/ci/render_schema.py` as reference for a DBA who wants to read the DDL
without running Python, and CI fails if they are stale.

It was two hand-written files until recently, kept in step by a test that compared them. That test was
sound and the arrangement was not: comparing two files can only report a divergence somebody has already
shipped, and it had shipped at least twice. One declaration cannot diverge from itself.

**Truth values are `Boolean`, and the column decides what reaches the driver.** For a long time the rule
was the opposite — no `BOOLEAN` columns anywhere, integer `0` and `1` everywhere — and it was earned:
fourteen columns were once declared `BOOLEAN` on the PostgreSQL side while `db/repositories.py` coerced
every Python `bool` to `int` on the way in, and PostgreSQL does not implicitly cast integer to boolean, so
every insert touching one of those tables would have failed. Silently, because nothing ran against that
dialect.

The rule fixed the symptom. The cause was that a column's type was written twice, in two files, and known
to neither the driver nor the code writing to it — and the coercion it forced was itself a hand-maintained
list of column names, which named fourteen of the twenty truth columns that existed. A typed declaration
removes both: `Boolean` compiles to `BOOLEAN` in both dialects, `db/repositories.py` reads the truth
columns off the metadata, and a bool in a non-boolean column is made an integer rather than sent as it is.
PostgreSQL refuses each of those mistakes and SQLite accepts both, which is exactly why SQLite could never
be the thing that told you which one you had made.

Delta is unchanged: truth values there are still integer `0` and `1`, because Delta has no schema of MAYA's
to consult.

**Drift is detected, and now it can be closed.** The schema is applied with `CREATE TABLE IF NOT EXISTS`,
so an existing table is *skipped* and a column added to the shipped DDL never reaches a deployed database.
`Database.drift()` has always reported precisely which columns and indexes are missing — and then said
"apply the difference by hand", which is a real chore and the reason a development database with months of
evidence in it got deleted rather than fixed. `Database.repair()` closes that loop, and
`run_maya_web.py --check-schema` / `--repair-schema` invoke it.

This does not make it a migration framework: there is no version history, no ordering, no down-step, and
the consolidated schema remains the only description of the shape. Repair asks that schema what is missing
and issues `ALTER TABLE … ADD COLUMN` for exactly that, which is non-destructive in both dialects and
cannot lose a row. The one case it will not attempt is a `NOT NULL` column with no default on a table that
already holds rows — there is no value to put in the existing ones, so it is reported with its declaration
for somebody to decide. Guessing on their behalf is how a governance register acquires a column full of
zeros that nobody chose. Repair is never run at start-up: a process that alters the schema every time
somebody starts it is one nobody can reason about, and the point of the drift report is that a person
decides.

**There are also no foreign keys, no triggers and no `CHECK` constraints.** Referential integrity and
immutability are properties of the application, not of the database. That is a real weakness and it is
[11 §4.5](11-adversarial-review.md#45-immutability-has-no-enforcer) rather than a design choice to be
defended here.

## 2. The rules that bind every component

Re-derived from the code rather than carried over from the previous version of this table. The two rules
that described an intention rather than the build have been removed from it and are named underneath,
because a design rule nothing enforces is the thing this document exists to stop.

| # | Rule | How it is held |
|---|---|---|
| **DR-1** | **The domain is framework-free.** `core/domain/` imports no web framework, no ORM and nothing else in MAYA except its own siblings | By construction; the package is six modules of dataclasses and functions |
| **DR-2** | **No SQL above `db/`.** Repositories are the only thing that knows a table name | By construction; every service takes repositories in its constructor |
| **DR-3** | **A derived value is never stored.** Tier, worklist, estate summary, ageing, staleness, escalation, the dossier and the board pack's arithmetic are computed at read time | A stored derivation is one that can go stale and then disagree with the thing it derives from |
| **DR-4** | **A governance act writes evidence.** The act and its node carry the same actor, and segregation of duties is decided by reading the chain rather than a second who-did-what table | Every service takes an `EvidenceEngine`. **The act and the node are not in one transaction** — see [§20](#20-persistence-and-transactions) |
| **DR-5** | **Every refusal is coded, and the code says who must act.** One table, `routes/base.py::STATUS`, 272 entries | `tests/test_refusal_discipline.py` |
| **DR-6** | **Nothing is silently swallowed.** Every `except` logs; none is bare; none is only `pass` | `tests/test_logging_discipline.py` |
| **DR-7** | **A refusal explains itself.** `error`, `detail`, `remediation` — the last naming what to do, not what went wrong | Enforced by the shape of every domain error class |
| **DR-8** | **Nothing is fetched at runtime.** No CDN, no external call, no network dependency in a governance path | Every asset vendored; the SSO verifier's RS256 is written against the standard library so an air-gapped deployment can use it |

Two rules from the previous version are **targets and not descriptions**, and saying so is the point of
this table. *"The API is the only interface"* is not true: `routes/ui_routes.py` makes fifty-one direct
in-process service calls, and reads never traverse `/api/v1`. *"Every write path is idempotent given an
`Idempotency-Key`"* is not true either: there is no such header and no replay window. What idempotence
exists is narrower and is described where it lives, in [§21](#21-concurrency-and-idempotency).

## 3. Core domain

`core/domain/` — the algebra, and nothing else. Six modules: `algebra`, `contracts`, `schemas`, `lattice`,
`identity`, `paging`.

### 3.1 The kernel, and the class derived from it

```python
# core/domain/algebra.py
class ParameterKind(str, Enum):
    NONE = "none"                     # P = I, the terminal object: nothing to fit
    CALIBRATION_SET = "calibration_set"
    ESTIMATED_COEFFICIENTS = "estimated_coefficients"
    LEARNED_WEIGHTS = "learned_weights"
    LLM_CONFIGURATION = "llm_configuration"
    RULE_SET = "rule_set"
    ELICITED_WEIGHTS = "elicited_weights"
    OPAQUE = "opaque"                 # exists, but the governing party cannot see it

@dataclass(frozen=True)
class ParametricKernel:
    parameters: ParameterObject
    input_schema: Schema
    output_schema: Schema
    output_kind: OutputKind = OutputKind.POINT_ESTIMATE
    deterministic: bool = True
    fit: FitProcedure = FitProcedure.NONE
    adaptive: bool = False

    @property
    def trainability_class(self) -> str:
        if not self.parameters.is_accessible:                    return "T6"
        if self.parameters.is_terminal:                          return "T0"
        if self.fit is FitProcedure.TRAIN and self.adaptive:     return "T4"
        return _FIT_TO_CLASS.get(self.fit, "T0")
```

with `_FIT_TO_CLASS` mapping `calibrate → T1`, `estimate → T2`, `train → T3`, `configure → T5`,
`elicit → T7`, `author → T8`.

**The order of those four lines is the design.** Each is a decision that is easy to get subtly wrong and
expensive to get wrong quietly.

**Inaccessibility wins over everything, including a declared fit.** A kernel with `opaque` parameters and
`fit=train` is `T6`, not `T3`. A vendor who tells you they train it has told you something about their
process and nothing you can govern; what you can observe is the composite.

**`T0` is checked before `T4` and is also the fallback.** An unmapped or absent fit derives `T0`, which is
right: no fitting procedure and no parameters to fit are the same statement from two directions.

**`T4` requires both `fit=train` and `adaptive`.** `adaptive` with any other fit derives that fit's own
class, because *continuously updating* without a training procedure is a description rather than a class.

**Nothing stores this.** `requires_fitting_evidence` is `trainability_class not in ("T0", "T6")`, so asking
a closed-form pricer for a training set is a type error rather than an empty field, and the warrant grammar
refuses a `fit` verb for those two classes on the same ground.

### 3.2 Contracts, and a deliberately small predicate language

```python
# core/domain/contracts.py
@dataclass(frozen=True)
class Contract:
    bounds: Tuple[Bound, ...]        # each: key, minimum, maximum, allowed values, side

    def check_inputs(self, values) -> List[str]: ...
    def refines(self, other) -> RefinementResult: ...   # L-7
    def compose(self, downstream) -> "Contract": ...     # guarantees meet; the upstream
    def composed_with(self, downstream) -> Composition:  #   discharges what it implies
    def conjoin(self, other) -> "Contract": ...          # guarantees meet, assumptions JOIN
    def quotient(self, have) -> "Contract": ...          # turns a gap into a specification

# and the two partial operations the three are written in terms of
class Bound:
    def meet(self, other) -> Optional["Bound"]: ...      # None where nothing satisfies both
    def join(self, other) -> Optional["Bound"]: ...      # None where the union is not a band
```

A `Bound` is a key with an optional minimum, an optional maximum and an optional allowed set, marked as an
assumption or a guarantee. Refinement is `A ⊆ A' ∧ (A ∧ G') ⊆ G` and it is decidable precisely because the
language is that small — intervals and set membership, nothing else. Anything richer is recorded as a
narrative assumption that **does not participate in automated refinement and is flagged as such**, so
nobody believes a check happened that did not.

`RefinementResult.reason()` names the failing clause rather than returning a boolean, which is DR-7 at the
level where the refusal is actually generated: the alias-move refusal quotes it verbatim.

### 3.3 One order, four questions

`core/domain/lattice.py` is the most consequential module in the package and the newest. `refines(a, b)`
answers *can `a` stand in for `b`* and it separates two failure modes deliberately:

```python
def refines(a: Schema, b: Schema) -> Refinement:
    mine = a.by_name()
    missing, narrowed = [], []
    for field in b.fields:
        held = mine.get(field.name)
        if held is None:            missing.append(field.name)
        elif not held.accepts(field): narrowed.append(field.name)
    return Refinement(not missing and not narrowed, tuple(missing), tuple(narrowed))
```

*Missing* means somebody bound the wrong featureset. *Narrowed* means somebody tightened a constraint and
did not notice it was a promise. Different mistakes, different remedies, so they are different fields.

`meet` and `join` exist on every finite fragment, the empty schema is top, and **meet is partial**: two
schemas whose shared slot carries two types have no meet, and `NoMeet` names the conflicting slots. That
partiality is the useful part — it is the honest answer to *can one featureset serve both of these models*,
and a total operation would have had to invent an answer.

The reason this module exists is that four places were asking one question with four implementations —
alias variance, warrant issuance, featureset satisfaction, composition type-checking — and four
implementations of one order disagree eventually, in the direction of permitting more, because that is the
direction in which nobody files a bug. `substitutable` (`L-12`) now delegates to `refines`, and so do
`L-W10` and `L-21`.

### 3.4 Identity relative to a probe set

`pi_equivalent(a, b, probes, tolerance)` is the formal content of a patch release: two runnables are
equivalent with respect to a probe set if every probe agrees within tolerance. The result carries
`coverage` — what fraction of the declared input domain the probe set touches — and stores it with the
claim, because an equivalence asserted on a probe set covering a tenth of the domain is a different claim
from one covering all of it and only one of them should be allowed to move a Tier 1 alias.

**What this package does not do.** There is no plugin loader and no fibre registry; a model class is a
string on the register, which is why `L-15` is not executable. There is no coalgebraic treatment of `T4`;
an adaptive model is a sequence of versions with a governed change process.

## 4. Registry, versions and composition

`core/registry/` — `models`, `versions`, `aliases`, `composition`, `catalogue`, `specs`.

### 4.1 A version is immutable, and what that currently means

`VersionService.create` refuses a semver that already exists for the model, computes the manifest digest,
and projects `input_schema`, `parameter_schema`, `output_schema`, `contract` and `trainability_class` out of the manifest into
columns so that a query does not have to parse JSON. The digest is over the **manifest**, never over the
row, because a digest over the row would move whenever a status column did — which `L-2` asserts by
carrying one version through assessment, approval and an alias move and checking the digest at each step.

One refusal at creation is worth stating in full, because it closed a hole that failed in the permissive
direction. `_refuse_unexplained_parameters` rejects a kernel whose `P` is inhabited and whose
`fit_procedure` is `none`. The derivation ends in `_FIT_TO_CLASS.get(self.fit, "T0")` and the only key
absent from that map is `none` — so a kernel with real, inspectable parameters and no declared procedure
came back **T0**, meaning `P` is *terminal*, meaning `requires_fitting_evidence` was false, meaning the
model was exempted from fitting evidence on the grounds that it has no parameters to have fitted while
carrying a set of them. Every legitimate way `P` gets inhabited has a procedure: hand-set weights are
`author` or `elicit`, a foundation model is `configure`, a fit is `estimate` or `train`. So the
contradiction is refused **at declaration** rather than resolved downstream, because a state nothing can
reach needs no downstream check and the permissive resolution is the one nobody would have noticed.

The honest boundary: only one call site updates the table and it updates `status`. There is no trigger and
no constraint, and `db/repositories.py::Repository.set` is generic. Immutability is a property of the
callers, and [11 §4.5](11-adversarial-review.md#45-immutability-has-no-enforcer) is where that is argued
rather than excused.

### 4.2 The alias move, which is the most dangerous operation here

```python
def move(self, urn, environment, name, to_semver, actor="system", justification=""):
    m   = self.catalogue.require(urn)
    new = self.versions.require(urn, to_semver)
    if new["status"] != "approved":
        raise RegistryError(...)              # an alias points only at an approved version
    self._check_not_blocked(m)                # an open blocking finding stops the move
    current   = self.aliases.one(model_id=m["id"], environment=environment, name=name)
    incumbent = self.versions.by_id(current["version_id"]) if current else None
    proof     = self.obligations(new, incumbent)      # L-7 and L-12, discharged here
    if not (proof["refinement"]["holds"] and proof["variance"]["ok"]):
        raise RegistryError(f"alias move refused: {…reason…} / {…reason…}")
    if self.policy is not None:
        self.policy.check("alias:move", {…facts…}, f"{urn} {environment}/{name}")
    self.aliases.point(…);  self.history.add({… proof …});  evidence.append(…)
```

Three things about that order are deliberate. The **proof is computed before the policy gate**, so a
published policy can add a condition and can never remove the algebraic one. The **proof is written into
the alias history**, so it survives the move and a reader six months later can see what was discharged
rather than being told it was. And the refusal **names the failing clause**, because *"refinement does not
hold"* sends somebody to read two contracts and *"the guarantee on `gini` was weakened from 0.55 to 0.50"*
sends them to one line.

There is no advisory lock and no pre-warm, because there is no cache to warm and one process to serialise.

### 4.3 Composition is typed, and the relation was renamed

`core/registry/composition.py` records how one model stands to another. Two relations do different work:
`input_to` **propagates** — change the source and this model's answer changes — and `derives_from` does
not, because a model built from another has its own versions and its own approvals. Conflating them makes a
challenger look like a dependency and inflates every blast radius it appears in.

The relation used to be called `feeds`. In a bank a *feed* means market data or a nightly file, so
`A feeds B` read as though MAYA consumed or produced one, which it does not and never has. It is `input_to`
now; `feeds` is accepted on input and stored as `input_to`, so an existing caller keeps working and an
existing *reading* does not persist. Nobody would have caught that from the code — it took a reader asking
what it meant.

**`L-21` makes the edge a claim about types rather than a drawing.** An `input_to` edge holds only if what
the source produces can stand in for what the target reads, checked through `lattice.refines`; an edge that
does not type-check is refused, and a composite gets a **derived** schema. Until that existed, blast radius
was computed over edges nobody had validated.

Traversals — blast radius, upstream, shared dependencies — are breadth-first with a depth bound of twenty,
which is a guard against a cycle rather than a modelling limit.

---

# Part II — Governance subsystems

## 5. Evidence

`core/evidence/` — two modules, `engine` and `semirings`. There is no separate audit log, deliberately:
two records of who did what are two records that can disagree.

### 5.1 The append path

```python
content_hash = canonical_digest({
    "kind": kind, "subject": [subject_type, subject_id],
    "payload": stored_payload,        # {} when personal_data — L-18
    "parents": parents,
    "recorded_by": actor, "trust": trust})
prev_seq, prev_hash = self.head()
node = {"seq": prev_seq + 1, …,
        "content_hash": content_hash, "prev_hash": prev_hash,
        "chain_hash": canonical_digest([seq, prev_hash, content_hash, parents])}
```

Three decisions inside those few lines.

**The hash is taken over what is stored, not over what was passed.** A node carrying personal data stores an
empty payload, and hashing the original would make every such node fail its own verification.

**`recorded_by` and `trust` are inside the content hash.** They were not, and the omission was worse than it
sounds: segregation of duties is decided entirely by reading `recorded_by` off these nodes, so a single
`UPDATE` reassigning authorship turned that control off for a subject while verification went on reporting
the chain intact. `trust` is there for the same reason — it weights the trust semiring, and a silently
re-weighted valuation is a conclusion nobody can check.

**The DAG and the chain are different structures doing different jobs.** `parents` expresses derivation;
`seq`/`prev_hash` makes deletion and back-dating detectable. A Merkle DAG alone has no global ordering, so
deleting a leaf leaves every remaining hash valid — which was finding **C-4**.

### 5.2 Verification, and the two questions it answers

`_walk` is one loop, shared, so the full walk and the incremental one cannot drift apart in what they
consider a break. It checks four things in order:

| | Break | What it catches |
|---|---|---|
| 1 | sequence gap | a deleted or inserted node |
| 2 | `prev_hash` mismatch | a re-ordered chain |
| 3 | **re-derived** `content_hash` mismatch | an edited payload, subject, kind, author or trust weight |
| 4 | `chain_hash` mismatch | a link rebuilt without the content |

Step 3 is the one that was wrong and is the reason this section exists. `verify_chain` used to **re-link**
each node's *stored* `content_hash` rather than re-deriving it, which proves the links are intact and says
nothing about whether the thing linked is still what was recorded — so an edited payload left a chain that
verified cleanly and a record that lied. It was found by the scale suite on its first run, and the unit
test that should have found it was named for payload tampering while actually altering the stored hash.

`verify_chain()` walks everything. `verify_since_checkpoint()` trusts `evidence_checkpoint` and checks only
what came after, which is what `/health/ready` calls, because the full walk was 2.9 seconds and 83 MB at
forty thousand nodes and an orchestrator will take a node out of service for being slow to say whether it
is healthy. The checkpoint is written by the same process that verifies, which is
[11 §3.5](11-adversarial-review.md#35-an-anchor-written-by-the-thing-it-certifies).

### 5.3 Semirings

Six semirings and the universal one, all in `core/evidence/semirings.py`, all evaluated by one memoised
bottom-up traversal of the derivation DAG.

| Semiring | `plus` / `times` | The question it answers |
|---|---|---|
| `BOOLEAN` | `or` / `and` | Is the claim supported at all? |
| `COUNTING` | `+` / `×` | How many independent derivations support it? |
| `WHY` | union with absorption / pairwise union | What is the minimal set I must show? |
| `TRUST` | `max` / `×` | How much does the platform believe it? |
| `COST` | `min` / `+` | What is the cheapest way to close the gap? |
| `FRESHNESS` | `max` / `max` | How stale is the evidence underneath? |
| `POLYNOMIAL` — `ℕ[X]` | free commutative semiring | All of the above, by homomorphism (`L-9`) |

`L-9` is checked over 200 random derivation DAGs against five targets, and writing it surfaced something a
table could not: **`FRESHNESS` is not a semiring.** It is `(max, max)`, and `max(0, 5) ≠ 0`, so its zero
does not annihilate and the universal property does not reach it. The practical consequence is stated
rather than hidden: a claim resting on a *missing* fact reports the freshness of the facts that are present.

`WHY` is worst-case exponential in the number of alternative derivations. The controls are canonical form
with absorption (`a ⊕ ab = a`, applied inside `_why_plus`), memoisation, and a hard cap of `MAX_TERMS =
4096` beyond which evaluation degrades and **sets an explicit truncation marker**. A silently partial answer
is never returned, because a partial provenance answer looks exactly like a complete one.

**What this package does not do.** There is no sheaf gluing and no consistency radius, so `L-13` is not
executable. There is no anchoring of the chain head to anything outside this database.

## 6. Risk and tiering

`core/risk/` is two modules: `lattices.py`, which is pure data, and `tiering.py`, which is the map.

Materiality and complexity are **separate lattices** and the tier is `τ(m, c)`, monotone by `L-4` — raising
either input can only raise the tier. The control set is `req(t)`, a Galois adjoint of the tier by `L-5`:
`req(t) ⊑ c ⟺ t ⊑ sup(c)`, checked exhaustively over the finite tier chain. That single adjunction decides
every control depth in the platform, including the version-approval quorum in [§9](#9-lifecycle-approval-and-attestation),
which is why it is worth having as a law rather than as a table.

Every assessment stores its **fact snapshot, ruleset version, derivation and rationale** in the same row.
That is DR-3's exception and it is deliberate: the tier is derived, but the *derivation* is a historical
fact about a moment and cannot be recomputed later against a ruleset that has moved.

**What this does not do.** The facts are not sourced. `exposure` is a float on the request; there is no
binding to a system of record, no `unsourced` flag, no peer-cohort outlier check and no retrospective
back-test of tier against realised incidents. Finding **H-8** is open in full, and the only part of it that
holds is that the snapshot records *what was claimed*.

## 7. Regimes as institutions

`core/regimes/` encodes a supervisory regime as an **institution**: a signature (the vocabulary in which
that regulator speaks), sentences over it, and a translation into the platform's core facts.

```python
determination = engine.determine(model_id, "sr_26_2")
# → {"determination": "in_scope", "derivation": {"sentence": …, "failing_conjunct": …,
#                                                "facts": …, "citation": …}}
```

Every verdict is a derivation carrying the terms it read and the citation it rests on, because a scope
determination somebody has to take on trust is a scope determination that cannot be defended in an
examination.

Two checks make this more than a rules table.

**The satisfaction condition (`L-8`) is checked at activation, not in CI.** For each sentence, evaluating
natively and evaluating the translation must agree; `core/regimes/translation.py::satisfaction_condition`
runs over six probe states spanning the corners of the vocabulary, and **a regime whose encoding fails it
cannot be activated**. That is stronger than a build assertion in the way that matters, because a failing
build can be overridden and a failing activation cannot. The weaker quantifier — probe states rather than
generated ones — is stated rather than hidden.

**Deontic consistency (`L-16`) is checked before activation.** `sentences.py::deontic_conflicts` finds every
term both obliged and forbidden and refuses activation as `obligation_contradiction`, and `undecidable()`
**names** the sentences the check cannot read rather than assuming them consistent. A conditional obligation
is not counted against an unconditional prohibition, because they may never both apply.

Regimes that disagree are **reported as disagreeing** rather than merged. Merging would produce a single
verdict defensible to nobody.

## 8. Versioned gates

`core/policy/` — `language`, `facts`, `engine`.

A gate that cannot be changed without a release is a gate people work around. A gate that *can* be changed
without one is a gate that can be **weakened** without one, which is worse. Everything here makes the first
possible without making the second silent.

**A rule is a predicate, not a program.** Comparison, membership, boolean connectives, `any` and `all` over
a generator, and a handful of whitelisted functions — checked at the AST. No loops, no assignment, no
function definitions, no attribute access, no subscripting. Rego was the obvious choice and was not taken
for exactly this reason: a gate written in a general language is a program, and a reviewer signing off a
governance control would have to run it to know what it does.

**Four gates**, each publishing its own closed fact vocabulary: `version:approve`, `alias:move`,
`model:mutate`, `warrant:resolve`.

```python
verdict = register.decide("version:approve", facts)
# {"allowed": bool, "decision": "allow"|"refuse", "policy_version": int,
#  "policy_source": "built-in"|"published", "rule": str, "reason": str,
#  "facts_read": {name: value}}      # computed from the rule's AST, never declared
```

Four properties do the real work.

**A fact the gate does not publish is refused when the rule is written**, not at evaluation, because a rule
that failed at the moment of a governance decision would fail at the worst possible time. Every call fills
the *complete* fact set from defaults, so behaviour never depends on which call site evaluated the rule.

**A policy ships with its own cases and at least one must be a refusal.** Publication re-runs them rather
than trusting the draft's report. A policy nobody has shown to refuse anything is a policy nobody has shown
to be a gate.

**Weakening is allowed and never quiet.** Publication replays the *outgoing* version's cases against the
incoming rule and buckets every flipped verdict as `loosened` or `tightened`, into the evidence node and
the log. A change that loosens a gate becomes something somebody decided rather than something somebody
discovered. A published version is never edited; it is superseded, and `history(gate)` returns every one.

**Policy tightens; the code's invariants are the floor.** `PolicyGate.check` raises when the verdict refuses
and does nothing when it allows — so a rule can add a condition and structurally cannot remove one. An
instance that publishes nothing runs exactly what it ran before, because the built-in rules are the default
for every gate and are written in the same language. There is no `warn` verdict: a gate that warns is not a
gate.

## 9. Lifecycle, approval and attestation

`core/lifecycle/` — `states`, `service`, `approval`, `attestation`, `amendments`.

### 9.1 The record machine

Seven states — `draft`, `baselined`, `submitted`, `approved`, `attested`, `amending`, `retired` — with
**two initial objects**. The path is `draft → submitted → approved → attested`, with amendment as the
only route out of immutability, retirement keeping everything, and deletion administrators-only with the
evidence chain left intact.

The second initial object is `baselined`, and it was found by writing `L-1` rather than by reading the
design: the law computes the reachable closure of the initial set and asserts it equals the declared state
set, and `baselined` was reachable by no declared edge. That is not a violation — an imported record **must
not** enter through `draft`, or the register would imply that historical evidence was asserted when it was
not — so `core/lifecycle/states.py::INITIAL` now says there are two.

### 9.2 Attestation is a quorum, and so is version approval

Attestation of the *record* is a quorum of configured roles, each signing once and only for a role they
hold; one decline returns the record to work; an attested record refuses field changes **and** new versions.

Version approval used to be one person, which was the wrong asymmetry: the record was attested by several
people while the version — the thing that actually runs — was approved by one. `core/lifecycle/approval.py`
now scales the depth of control with the tier, by the same `L-5` adjunction that decides every other control
set: Tier 1 and 2 need the second line *and* an independent validator; Tier 3 and 4 need one authorised
person, because saying so beats pretending a scheduling heuristic deserves the ceremony of a capital model.

Three refusals carry the weight. The same person may not sign twice under two hats, because a quorum is a
number of people rather than a number of roles. Signing is its own permission, so a validator signs a
quorum and may never approve alone. And **a version whose model has no tier cannot be approved at all** —
approving first and assessing afterwards would be a way of choosing your own control depth, and it is the
obvious way to game a rule like this one.

## 10. Validation and findings

`core/validation/` — `catalogue`, `service`, `findings`, `workflow`, `ageing`, `replay`, `storage`,
`statistics`.

### 10.1 An episode, and what it refuses

Eight catalogue tests computed from first definitions in `statistics.py` — AUC, Gini, KS, Brier,
expected-versus-actual, PSI, RMSE, MAE — each recorded with its **declared threshold**, so a threshold moved
after the fact is as detectable as a changed number.

The refusals are the design:

- an episode may not be opened by somebody who built the version;
- a conclusion of `approved` is refused if any recorded test failed;
- and refused again if a blocking finding is open against the model;
- an independence attestation is required and is checked against the evidence chain, not against a
  self-declaration.

### 10.2 Replay distinguishes three outcomes, not two

`replay_from_storage` re-reads the dataset snapshot the episode was pinned to, **at the Delta version it was
pinned at**, and recomputes. It reports `reproduced`, `differs`, or `skipped` — and the third is the one
that matters. A validation with no snapshot, a snapshot whose table is gone, or a test whose columns are
absent is reported as skipped with the reason, because *"we checked and it matched"* and *"we could not
check"* are opposite findings and collapsing them into one boolean is how a control becomes a formality.

It also does not follow a restatement: if the table has been written to since, the replay still sees what
the validation saw, and the report says **separately** that the ground has moved — which is a finding about
the data rather than about the test. `replayable()` answers what a second line actually asks: what fraction
of what was concluded can be checked without asking whoever concluded it.

### 10.3 A finding has a life, and it is derived from acts

`finding_action` rows are the record; ageing, overdue-ness, acceptance and escalation are **computed from
them** by `core/validation/ageing.py`, so there is no status column to disagree with the register.

The workflow: a finding can be handed over with a reason; it must be **accepted by its owner with a plan**
before its date can be moved; its date can only be moved by somebody who does not own it, with a reason,
counted — and past the limit the extension becomes a finding of its own. A finding nobody ever accepted is
recorded as another finding by the scheduler, because an unaccepted finding is the one nobody is working on
and the one nobody will report.

The blocking flag gates two things elsewhere: alias promotion and warrant resolution. That is what makes a
validation finding stop the model rather than generate an email.

**What this does not do.** Findings are flat. There is no root-cause finding with impact records, so a
shared upstream failure raises one finding per consuming model — **M-8**, answered at the notification layer
instead ([§16](#16-reporting-baseline-and-the-operational-jobs)).

## 11. Documentation

Three separate things, deliberately not one thing with a flag.

### 11.1 Compiled documents

`core/docs/` compiles four kinds — model development document, validation report, model card, EU AI Act
Annex IV — from the register and the evidence graph, through **fifteen lenses** in `lenses.py`. A fifth
kind, the **training record**, is compiled per parameter set rather than per version: a model recalibrated
every morning produces two hundred and fifty governed acts a year and until recently none of them had a
record anybody could read.

Four properties.

**Every section records the evidence it rested on**, so citation soundness is a Boolean evaluation over the
derivation rather than a claim. **Staleness is computed** from the chain head at compile time rather than
remembered. **A lens that cannot fill its section says so in the document**, so a gap in a model's evidence
is visible rather than blank. And `render` is separated from `compile`, because compiling is an *act* that
authors a document and records it — so cutting an export pack monthly must not silently author four
documents a month.

The context builder gathers evidence for the model **and every version**, which is not a detail: approvals,
validations, test results and parameter sets are recorded against the version, so a document built from the
model's id alone cited none of them, and a fully governed model compiled fifteen sections with two
citations while Classification, Methodology, Assumptions and Validation rendered as filled and cited
nothing.

`L-11` is not executable and the reason is that the design went the other way: fifteen lenses, all `get`.
The compiler regenerates whole documents, so there is no `put` and no round trip to test, and building one
to satisfy a law would be building the wrong thing.

### 11.2 Attached documents

`core/attachments/` holds the papers people wrote, as against the ones MAYA compiled.

Filed against the **version** by default, because a development document describes the coefficients it
printed and not their replacement; model-level filing exists — a board paper genuinely is about the model —
but has to be asked for, because the ambiguous case should not be the default.

Stored under the SHA-256 of their bytes and **re-hashed on the way out**, so *what an approver accepted is
what a reader fetches* is checked rather than assumed; a mismatch is `document_corrupt` with a remediation
that says raise an incident. Review is segregated twice — by role grant (`document:attach` is first line,
`document:review` is second) and again in the register, because a role grant is a policy that can change
and segregation of duty is not. Rejection requires a reason and the rejected document stays on file.
Supersession names what it replaces and superseding twice is refused, because the chain would fork.

`text_indexed` is set from the media type, so a PDF is stored and served faithfully and reported as **not
machine-readable**: `text()` returns `None` rather than a guess, and later machine review knows what has
genuinely been read and what has only been stored.

### 11.3 The dossier

`core/docs/dossier.py` walks the whole documentation graph from a model — versions, their parameter sets,
the featureset versions those were fitted from, and the features in those — and returns it with **every
node that has nothing filed named as a gap**.

It **follows the pins, not the names**: a training record links `sb_core@v1`, never `sb_core`, because a
document filed against the *set* would describe something that has since moved — finding C-2 in
documentation's clothing.

It is computed, never stored, and the walk is **structurally bounded at five levels** — five named methods
calling each other in one direction, with `_feature` returning a leaf. There used to be a `MAX_DEPTH = 8`
constant here with a comment saying the dossier "says so rather than running forever", and nothing read it.
It was removed rather than wired up, because a declared-but-unread constant reads to the next person as a
control that exists.

### 11.4 Export packs

`core/export/` answers a *person* — a supervisor, an internal auditor, a diligence team, none of whom will
be given a login. Self-contained because they cannot query; digested member by member because they cannot
take the platform's word for it; carrying **where the chain stood** because they will read it months later.

Three decisions are worth recording. **The content digest excludes the manifest**, which carries the moment
the pack was cut — including it would make every pack differ from every other and destroy the one
comparison a reader wants. The act of cutting a pack is recorded against the **pack**, whose identity is its
content digest, rather than against the model, since against the model it would land inside the next pack's
own evidence and every pack would differ from the last for no reason but that somebody had taken one. And
**a gap is written down**, in `gaps.md`, with its reason, because a pack that silently omits what it could
not reach reads as complete and a reader cannot tell a thin model from a thin export.

Personal data is not re-materialised: a flagged node is carried as flagged. Writing the digest test found a
real defect on the way — the provenance lens quoted the **platform-wide** chain length in a per-model
document, so every model's document changed whenever anything happened anywhere.

---

# Part III — Data and execution

## 12. The feature platform

`core/features/` is the largest package here: eighteen modules. This section covers the parts a reader has
to understand to change any of them.

### 12.1 Two clocks, and the read as an operator

Every feature value carries a **valid time** (`event_ts`, when it was true in the world) and an **ingest
time** (`ingest_ts`, when the platform learned it). The point-in-time read is:

```
AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                { r ∈ R : r.event ≤ ℓ  ∧  r.ingest ≤ min(ℓ, a) }
```

implemented in `TrainingSetBuilder.latest_admissible` as exactly

```python
knowable_by = min(label_ts, as_of)
eligible = [r for r in records
            if r[VALID_TIME] <= label_ts and r[INGEST_TIME] <= knowable_by]
return max(eligible, key=lambda r: (r[VALID_TIME], r[INGEST_TIME])) if eligible else None
```

and mirrored in `db/delta_store.py::as_of` for the Delta path.

**The `min` is the whole guarantee and it is a repair, not a decoration.** The ingest bound used to be `a`
alone, and `a` is a single scalar for the whole assembly, so a fact true before the label and *learned
afterwards* was admitted: knowable at assembly time, not at decision time. With the `min`, the operator
**saturates at `ℓ`** — every `a ≥ ℓ` gives the same answer — so a row assembled the day its label matured
and the same row re-assembled a year later are identical however many restatements arrived between. Without
it a re-run would quietly *improve* on the original, which is the least useful kind of reproducibility
because the numbers then agree with nothing, including themselves.

Both bounds are kept because they refuse different things: `ℓ` is what the model could have known when the
decision was made, `a` is what the platform could have known when the set was built.

This rule was recently wrong in **two** other places, both of them stating the pre-`min` form, and each is
a different lesson.

`FeaturesetRegistry.PIT_RULE` is the string a featureset *publishes* — the rule an execution engine is
handed and expected to implement. It said `ingest_ts <= as_of`. An engine implementing the published rule
faithfully would have admitted rows MAYA itself refuses, and the disagreement would have surfaced months
later as a reproducibility failure nobody could locate, because both sides would have been doing exactly
what they were told. **A published contract is code**, and it drifted from the implementation because
nothing compared them.

`TrainingSetBuilder._recompute` is the independent recomputation used by verification layer 2, and it also
bounded ingest by `as_of` alone — so it disagreed with the assembler whenever the set was built after the
label matured, which is the ordinary case, and the verifier reported a mismatch on a *correct* assembly.
**A false positive in the control that exists to verify a control is worse than no control**, because it
trains whoever reads it to discount the report.

The general shape: one rule, three expressions of it, and no test that they agreed. Stating it once as a
constant is the repair; the deeper repair would be for the verifier to consume the published string rather
than re-implement it.

That was the *clock* half. The **column** half of the same method was worse, and an outside review found
it: `_recompute` walked the same list of views the assembler walked, in the same order, and did the same
`update(payload(...))`. It therefore agreed with the assembler **by construction** — a binding the
assembler ignored was a binding the verifier could not notice, and `pit_verified: true` was incapable of
being false about it.

Independence now rests on two differences rather than one, and both are load-bearing:

| | `_join` | `_recompute` |
|---|---|---|
| **Point-in-time choice** | bulk-reads a view, chooses the admissible record in Python | asks `DeltaStore.as_of` for the frame directly |
| **Resolution order** | groups columns by source, one read per **view** | resolves each column alone, one read per **column** |

The second row is the new one. Grouping is right for cost and is exactly the step that can go wrong — a
mis-grouped source, or two columns of one view landing in the wrong slots — so the verifier deliberately
does not group. A control whose failure mode is shared with the thing it controls is not a control.

### 12.2 Three layers of verification, and what each actually proves

| Layer | Mechanism | What it proves |
|---|---|---|
| **1 · Static** | `pit.static_check` refuses an assembly missing either temporal bound; `TrainingSetBuilder` raises `AssemblyRejected` | A refusal, not a sample. The honest scope: it reads two flags off the request rather than analysing a query, and the bound is structurally guaranteed because the assembler builds the join itself — so what it refuses is a caller opting *out* |
| **2 · Stratified sample** | `verify_sampled`, 200 rows by default, strata over label period, entity and **label value**, recomputed through `DeltaStore.as_of` rather than through the join path, and **column by column rather than view by view** | Detection of systematic violation, never absence. Strata include the label value because a leak confined to a rare high-value segment is where uniform sampling fails and where the damage is greatest. The recomputation takes a *different route* to the same answer in two independent senses — a different point-in-time read and a different resolution order — which is why agreement means something. Sharing either with the assembler would let a bug hide behind itself, and sharing the second one did |
| **3 · Screens** | `detect_leakage` — a purity screen for repeating columns and a perfect-separation screen for continuous ones | A signal, not a proof, and labelled as one |

A failed verification raises a Critical finding and the snapshot records `pit_verified = 0`.
`tests/test_features.py::test_injected_leakage_fails_the_assembly` injects leakage the verifier was not
told about, because a verifier tested only on examples it is known to pass is a verifier that can silently
stop working.

### 12.3 Views, featuresets and the parameter object

A **feature view version** materialises into a Delta namespace `{delta_table}/v{version}` — the version *is*
the namespace, never "latest", which is finding C-2 answered structurally. A read is pinned to the **Delta
version** the materialisation produced, so *same featureset version → same bytes* is true rather than
true-until-Tuesday, and `restated()` answers the neighbouring question a reviewer asks before comparing two
runs: has anything underneath this pin been written to since?

A **featureset** declares a schema — named slots with types — and a version *fills* it:

```python
def publish(name, bindings, label=None) -> FeaturesetVersion:
    refuse_if_slots_unfilled(bindings)          # that is not a version of THIS set
    refuse_if_bindings_name_no_slot(bindings)   # adding a slot changes X
    refuse_leakage(bindings, label)             # BEFORE resolution, on purpose
    resolved = {slot: pin(feature, view, view_version) for slot in slots}
    return version(bindings=resolved, digest=canonical(resolved))
```

A model reads the **slot**, so swapping what fills one does not change the model's input space — it changes
what the model was fitted on, which is a different event with a different control. The leakage refusal runs
*before* resolution deliberately, so that *"you cannot train on the answer"* beats *"no view supplies that
slot"* as the message somebody gets.

**Derived features** compute values from values in a small whitelisted expression language, with lineage as
the transitive closure and an ingest clock inherited as `max` over the inputs — the easiest way to leak the
future, and arithmetic, so it is computed rather than trusted. The `external` evaluator exists for an
expression MAYA cannot evaluate, and it now accepts an explicit `inputs` list: the parser used to run before
the evaluator was consulted, so an expression the language could not *parse* could not be declared external
either, and the only escape was to register the result as a primitive and lose the lineage that was the
whole point. Inputs have exactly one source of truth at a time — parsed for `internal`, declared for an
`external` expression that does not parse, and MAYA records that the expression is **opaque to it** rather
than pretending to have understood it.

**Parameter sets** are inhabitants of `P`. A fit produces one and *not* a model version, because the kernel
did not change. They are accepted only against a warrant MAYA issued, named by the featureset version that
produced them, approved by somebody other than whoever recorded them, and refused as **ambiguous rather
than guessed at** when a version has two.

### 12.4 Five things a feature is not

`shapes`, `composition`, `lifecycle`, `policy`, `normalisation`, `preparation`, `alignment` exist because of
five assumptions that each turned out to be wrong.

**Not always a number.** A declared shape with named components makes a curve a vector and a correlation
structure a matrix; the component order *is* the axis order; and the shape is checked against the values,
because a declared shape nobody verifies is a comment.

**Not always defined in one place.** Inheriting from one parent and combining several are the same operation
at different arities, so there is one mechanism: a left-to-right fold in which the rightmost wins, with an
object's own operations applied last. That is a **monoid** — associative, with the empty composition as
identity, both asserted (`L-19`) — which is what makes *a combination of features is a feature* a statement
rather than an aspiration. Every operation is total: dropping something absent, adding something present,
overriding something absent are each **refused**, because the no-op alternative leaves a child quietly
differing from what its author wrote.

**Not always mutable.** A sealed object takes no amendment and no further versions and can still be composed
from — which is the point, since a parent that cannot move is a parent worth building on.

**Not always permanent.** An ephemeral object has a TTL, cannot be sealed, cannot be composed from, and
leaves its evidence behind when its rows go.

**Not always accountable to its author.** The creator is history; the owner is a responsibility, transferred
by name with the handover in the chain.

And between the store and the model: retrieval policy attaches to the object as default behaviour and a
request overrides it by the same left-to-right rule; statistics for normalisation and fitted fills come from
what was knowable at a **stated** moment, and a request without one is refused rather than served the leaky
answer somebody would get by accident. Alignment offers back-fill and interpolation without refusing them
and **stamps them honestly** — a value derived from a later observation inherits that observation's ingest
clock, so an ordinary point-in-time read excludes it and the leakage is arithmetically impossible to hide.

### 12.5 Bulk transfer: the one layer where the rules invert

Every other surface here moves small documents. Feature values are not small, and an API that turns a few
million rows into JSON objects spends most of its time and nearly all of its memory on punctuation. So for
`core/features/transfer.py` the rule is inverted: **nothing is materialised whole.** Reads iterate Arrow
record batches straight off the Delta files; writes parse a batch at a time; peak memory is one batch rather
than one dataset.

A batch is sized by **cells rather than rows**, because sixteen thousand rows of six columns is a few
megabytes and sixteen thousand rows of two thousand columns is not. Four formats: `arrow` for an execution
engine (zero-copy, incremental both ways), `parquet` for disk, `ndjson` for anything, and `json`
hard-capped for a page. Reads use the **pinned** Delta version, so what comes out is what a version *is*
rather than what its path has since become, and a featureset's `/parts` names each namespace and its pin so
an engine can pull a large set in parallel instead of waiting on a join. An upload missing either clock is
refused **at the upload** rather than two layers later during assembly, where it stops being fixable.

**What the feature platform does not do.** There is no online store, so `L-17` has nothing to compare
against and training–serving skew is undetectable. There is no Spark and no partitioning: `DeltaStore.write`
passes no `partition_by`, isolation is by directory path, and `vacuum_horizon_days` returns a number and
vacuums nothing. And a featureset carries `composes` without a `definition_version` stamp, so a composed
featureset has no drift to report — the sixth instance of the C-2 class and the one still open.

## 13. Monitoring and telemetry

### 13.1 Telemetry is two streams, not one

`core/telemetry/` writes **two bitemporal Delta streams per version**: a **score** exists when the model
runs, an **outcome** is learned later, and the gap between them is precisely what the delayed-label
discipline reasons about — so flattening them into one would take that reasoning away before it started.

Four refusals shape the ingest path. It is **idempotent on the digest of the batch's own rows**, because
real collectors deliver at least once and a monitor that double-counts a redelivered batch reports a
population that never existed. **A row without its own timestamp is refused** rather than stamped with the
batch's, which is how every window silently becomes wrong. The **sample rate travels on every row**, so a
statistic can say what population it speaks for. And the join happens **at read time against a stated
moment**, with unlabelled rows coming back unlabelled rather than dropped, because the monitor decides
maturity per row and a join that discarded them would hand it a cohort that looks complete and is not.

### 13.2 Monitors admit only the tests that can answer them

Four monitor kinds — `input_drift`, `score_drift`, `performance`, `calibration` — each with a declared set
of admissible tests, checked **at definition time** rather than at evaluation, so a monitor that could never
have answered its question is refused when somebody writes it.

Delayed labels are first-class. A performance monitor **must declare its outcome window**; maturity is
decided per row; and evaluation over an immature cohort is refused **with the date it becomes measurable**,
because reporting an AUC on immature outcomes is worse than reporting nothing. A drift monitor's reference
distribution is drawn from a *stated* earlier window, so *what is this drifting from* is part of the record
rather than part of whoever ran it.

A breach raises a finding, escalating with persistence; recovery closes the breach and **deliberately leaves
the finding open**, because the thing that went wrong having stopped is not the same as the thing that went
wrong having been addressed.

**What this does not do.** Monitors evaluate in process. Nothing sweeps the estate nightly, and there is no
distributed compute anywhere in this repository.

## 14. Warrants

`core/execution/` — `grammar/`, `builder`, `signing`, `grants`, `warrants`, `profiles`, `engine`,
`sandbox`, `runtimes/`, `urn`.

### 14.1 One document, four axes

A warrant is the product of four independent vocabularies, and their *product* is what covers the estate:
how `P` is inhabited × how the kernel is realised (**nineteen runtimes**) × what is asked of it (ten verbs)
× where its data comes from (twelve bindings). Six output sinks and ten named document sections complete
it.

**Warrants differ by kind of model as refusals over one document, never as different documents.** Were the
document to fork by type, every engine, replay path and audit query would branch on model type before it
could read anything, and the branch would grow a case per family without bound.

Fourteen admissibility laws `L-W0 … L-W13` are checked **before the signature**, in
`core/execution/grammar/rules.py`. They quantify over facts the platform derives — parameter kind, source
binding, runtime, trainability class — never over a category anybody attached. `fit` is refused for T0 and
T6 because that is what those classes *mean*. The last three quantify over how `P` is inhabited: a
calibration must state its `as_of` (`L-W11`) or staleness is silent; parameters living inside an artifact
need that artifact digested (`L-W12`); a generative runtime must pin the build rather than the model family
(`L-W13`). `L-W8`, `L-W11` and `L-W13` each caught a real error in a shipped example on the day it was
written. Thirteen are decided by the grammar over the document alone; `L-W10` is decided at issuance,
because it compares a featureset version's resolved slots against a model version's input schema and
neither is in the document being validated.

JSON Schema is **generated from the vocabulary** and published at `/api/v1/grammar/schema`, so the
vocabulary cannot drift from what is validated.

### 14.2 Profiles template the request, never the document

The recurring ask is that warrants be templated per kind of model. Half of that is right and this is the
half: the **request**, not the document.

Three constraints keep a profile from becoming a taxonomy. It **selects by a predicate over facts the
platform derives** — trainability class, parameter kind, runtime, artifact format, tier, domain,
environment — never by a category attached to a model, because a declared taxonomy sitting beside a derived
one is two answers to one question with no rule for which wins. It **cannot widen authority**: principal,
declared use, environment, TTL, grace and binding kind are refused *at creation* with
`authority_not_defaultable`, pointing at the `warrant:resolve` gate that *can* hold an obligation. And it
**fills holes rather than overriding a caller**, including a value identical to the default, because *"the
caller asked for this"* and *"nobody said, so we chose"* are different facts and only one is the caller's
responsibility.

Several matching profiles fold by the `L-19` monoid, ordered by specificity so the most specific speaks
last, and the result names which profile version supplied each value.

### 14.3 Resolution, signing and lifetime

```python
def resolve(urn, environment, principal, declared_use, verb="score"):
    name, semver, aliasname = parse_urn(urn)
    m = self._model(urn, model_urn(name))              # unknown model → not_found
    self._check_not_blocked(m)                         # open blocking finding → restricted
    grant   = self._grant(m, environment, principal, declared_use)
    version = self._version(m["urn"], environment, semver,
                            aliasname or grant["alias_name"], urn)
    if self.policy is not None:
        self.policy.check("warrant:resolve", {…facts…}, urn)
    return self.builder.build(urn, m, version, grant, principal, declared_use,
                              environment, self.epoch, verb=verb,
                              parameter_set=self._point_of_p(urn, version))
```

The order is the design, twice over. **The blocking-finding check comes before the entitlement lookup**, so
a model under a validation finding refuses everybody identically rather than refusing the entitled caller
for a different reason from the unentitled one. And inside `_grant` the order is entitlement, then
**revocation**, then declared use — revocation before the use comparison on purpose, because a withdrawn
warrant is withdrawn whatever the caller claims to be doing with it.

`_point_of_p` resolves which approved parameter set this run is at, which is `L-W8` — *every run must say
which point of `P` it is running at.* For an artifact-backed model that point is inside the artifact and
the artifact's digest speaks for it, so the lookup is skipped; for anything fitted here it is a row in the
register. It is deliberately **silent** when there is nothing approved rather than refusing, because a
version with no approved set fails for a better reason further on and refusing here would make every
artifact-backed model depend on a register it does not use.

Signing is `HMAC-SHA256` over a canonical form with the signature block excluded, and the key id is a
prefix of the hash of the key rather than the key itself, because the signing key was once used as the HMAC
secret *and* written into every descriptor it signed. Verification is `hmac.compare_digest`.

TTL and grace are **scaled by the model's tier**: `{1: 60, 2: 300, 3: 3600, 4: 3600}` seconds of TTL and
`{1: 0, 2: 0, 3: 900, 4: 900}` of grace. That is finding C-1's second disposition and it is the one doing
the work: a Tier 1 descriptor lives sixty seconds with no grace at all. The TTL carries ±20% jitter, so a
population of consumers does not expire in step.

**What resolution does not have.** No cache of any kind, so every resolve re-reads model, grant, version and
findings. No `warrant_projection` read model, so the warrant path reads the same normalised tables as
everything else — which costs nothing today, with one process, and forecloses exactly the independence
finding **H-2** was protecting. And the local revocation floor is present in `CaptiveEngine` and
**unreachable**; the `revocation.epoch` on every descriptor is a per-process counter that nothing compares.
Both are [11 §4.2](11-adversarial-review.md#42-the-revocation-floor-cannot-fire).

### 14.4 The captive engine, the runtimes and the sandbox

`CaptiveEngine` is a **consumer of the public warrant contract and nothing more**. Its order of operations
is the design:

1. resolve, then verify the signature;
2. check the local revocation set;
3. check expiry against `expires_at + grace_seconds`;
4. check the inputs against the operating boundary, refusing or referring by the warrant's own
   `on_boundary_violation` policy;
5. resolve the parameter object and **check its digest against the warrant** before anything runs at it;
6. dispatch to the runtime, in a sandbox if the runtime is artifact-backed.

Everything above step 6 is checked **without touching an artifact**, which is the order that makes a refusal
cheap and stops an artifact loading on an authorisation that was never valid. Step 5 is in the engine rather
than in the runtime because a runtime that resolved its own parameters would be choosing which numbers it
ran on, and that is the decision the approval exists to make.

Five runtime implementations are wired, answering six of the grammar's keys: registered Python callables
(also serving `descriptor_only`), ONNX, the regression and scorecard subset of PMML, QuantLib, and the
estimator. A warrant naming a key this engine does not implement is refused **by name**, listing what it
does implement — because an engine's usefulness lies in being precise about what it has rather than in
claiming everything.

Two of those deserve a note. **QuantLib** takes the evaluation date from the warrant and never from the
clock, and builds the curve from what the warrant carries and nothing else — a valuation that reads today
is not reproducible tomorrow, and reaching for a market data service would put an unversioned input into a
governed computation. Writing it surfaced a real hazard: QuantLib keeps fixing history in a **process-global**
manager, so one warrant's fixing would still be there for the next valuation, and each valuation now starts
from an empty history. **The estimator** is the only runtime whose job is to *inhabit* a parameter object
rather than read one: `ols` and `garch11`, with no randomness anywhere — fixed simplex, fixed coefficients,
Nelder–Mead written out rather than imported — because a parameter set nobody can reproduce is a number in
the register with no provenance. It refuses rather than guesses: exactly collinear regressors are refused
rather than arbitrated by the solver; a search that stopped early is refused rather than recorded with a
flag; a missing value is refused rather than dropped, because dropping changes the population the fit
speaks for without saying so.

The **sandbox** runs artifact-backed runtimes in a child process with CPU and address-space limits read from
the warrant's `constraints.resources`. The memory budget is additive to the interpreter's own footprint, and
the runtime's dependencies are imported *before* the limit is applied, so a library's import cost is never
charged to the model's budget. Its boundary is **published rather than implied**:

```python
describe(sandbox) -> {"sandbox": "subprocess", "isolates": True,
  "protects_against": ["runaway cpu", "unbounded memory", "artifact crash"],
  "does_not_protect_against": [
      "a deliberately hostile artifact: the child shares the filesystem and the network namespace",
      "bound callables, which run unisolated by construction"]}
```

A hostile artifact needs a container or a VM, and saying so is better than implying an isolation the process
model does not provide.

### 14.5 Artifacts

`core/artifacts/` is **content-addressed**: a file's name is its own SHA-256, stored under
`data/artifacts/ab/cd/<digest>` with two levels of fan-out because one directory holding a hundred thousand
files is slow on every filesystem that has ever existed. Three controls fall out rather than being
performed: the same weights stored twice are stored once; an artifact cannot be edited in place because
edited bytes are a different address; and *"these are the bytes the warrant names"* is true by construction.
A declared digest is **checked**, so a truncated upload is refused rather than stored under the address of
whatever arrived.

Eight formats, closed on purpose and with no `pickle` — `onnx`, `pmml`, `safetensors`, `torchscript`, `pfa`,
`json`, `tar`, `gguf`. `torchscript` and `tar` execute code when they load, are accepted, and are **named as
such** on the warrant so an engine is not inferring it from a file extension. A version naming a digest the
store holds takes its uri, size and format **from the store**; a digest it cannot resolve is *recorded*
rather than refused, because plenty of checkpoints live elsewhere and are named here so the engine can
verify them on load — and the warrant carries the difference as `held_by_maya`. The ceiling is 8 GiB,
deliberately: a governance platform is not a model store of last resort.

## 15. Machine assistance

`core/assist/` — capabilities, oracles, grounding, generations, providers.

A capability registers at **Tier A** (a named oracle checks the output) or **Tier B** (every claim cites
evidence). **Tier C cannot be registered**, and `CapabilityRegistry.register` refuses it by name before it
refuses an unknown tier, with `advisory_not_registrable` and a remediation that says what to do instead:
*if the output can be checked, name the oracle and register it as Tier A; if its claims can cite evidence,
register it as Tier B.* Tier A without an `oracle_key` is refused too, so the tier cannot be claimed
without the thing that makes it a tier.

The honest note is that this lives in the register and **not in the DDL** — `ai_capability.tier` is
`TEXT NOT NULL` with no `CHECK`, because the schema has no `CHECK` constraints at all. The prohibition is
therefore as structural as the register and no more, which is still the right shape: the pressure to ship
an impressive ungated demo is constant, and a control that has to be *remembered* at each call site is the
one that erodes.

Five oracles exist, each backed by machinery that exists for another reason — a generated warrant validating
against the grammar; a proposed contract refining the incumbent (`L-7`); proposed schemas satisfying
variance (`L-12`); a proposed test existing in the catalogue; every cited evidence node resolving. An
oracle that had to be built for the oracle's sake would be a second implementation able to disagree with the
first.

The **grounding gate removes unsupported claims rather than flagging them**, and keeps them for the
reviewer. Verification is a Boolean evaluation over the derivation, not a second model call.

Two rules bound the whole package. **Nothing is evidence until a person attests it, and never the person who
asked.** And **no AI principal holds a credential permitting a governance transition** — a capability cannot
make a governance decision because it holds no credential to attempt one, which is held by construction and
not by any check.

## 16. Reporting, baseline and the operational jobs

### 16.1 Risk appetite as a computable limit

An appetite statement in most banks is a sentence in a document, which is not a control: nobody can compute
against a sentence. Here a limit is a **declared threshold over a metric the platform derives**, so
utilisation is arithmetic and a breach is a fact.

Four refusals make it a governance object rather than a dashboard. A metric the platform cannot compute is
refused **when the limit is written**, not when the report runs. A limit with **no rationale** is refused,
because a number nobody can explain is either ignored or obeyed without thought. An **amber threshold on the
far side of the limit** is refused: a warning that can only fire after the thing it warns about has happened
is not a warning. And **direction belongs to the metric**, not to whoever sets the limit — whether more is
worse is a property of *open blocking findings*, and letting an author declare it would produce a limit
reporting green while the estate deteriorates.

The board pack answers the three questions a committee actually asks — inside the limits, what is outside,
what moved — which is why packs are **persisted**: movement needs something to move from, and a minute
referring to "the March pack" needs the March pack rather than a document with the same name recomputed
today. An **unmeasured indicator is never reported as clean**: a metric no wired service can answer comes
back null with a reason and is named in the headline, because zero is a measurement and an absent service is
not. **Slack is reported**, because an appetite under a quarter utilised pack after pack is a limit
constraining nothing. And there is **no composite score**, with the pack saying so in itself rather than
leaving an absence — aggregating requires the parts to compose, two models fed by the same curve are not
two independent risks, and any single figure either double-counts the shared dependency or ignores it.

### 16.2 Baseline import

Imported models enter the `baselined` lifecycle state — governed going forward, mutable so their debt can be
closed — carrying explicit dated debt for each of **thirteen gap kinds computed from the register rather
than declared**, so an importer cannot under-declare. Debt closes by itself when the evidence arrives, which
makes the burn-down a measurement rather than a self-report, and expires into a finding at a board-approved
date per tier: eighteen months for Tier 1, thirty for Tier 2, thirty-six below. Debt and breach are
reported separately everywhere, because a Tier 1 model with baseline debt and a Tier 1 model with a missed
validation must never render the same colour. One bad row does not stop the batch.

### 16.3 Fourteen idempotent jobs

`core/scheduler/` turns computed conditions into recorded consequences:

| Job | What it records |
|---|---|
| `evidence.verify` | walks the whole chain and advances the verification checkpoint |
| `attestation.lapsed` | a finding for a model in force on a lapsed attestation |
| `monitoring.stalled` | a finding for a monitor far past its cadence |
| `overlays.expire` | closes overlays whose approved window has elapsed |
| `debt.reconcile` | closes baseline debt whose evidence arrived; expires what is overdue |
| `findings.overdue` | records that a finding passed its remediation window, as **its own finding** rather than by rewriting the original |
| `findings.unacknowledged` | records that a finding's owner never accepted it |
| `notify.outstanding` | tells each person what is outstanding for them |

A run is an ordinary authenticated call, so cron, a Kubernetes `CronJob` or a person produce identical
results; the in-process loop is a convenience and is **off by default**. One failing job does not stop the
others, and the scheduler reports its own health on `/health/ready` — informationally, because a stopped
scheduler is not a reason to take a node out of service. That last decision has a consequence worth naming:
an instance whose operator never wires a trigger has a governance platform in which nothing ever lapses, and
nothing in this repository can tell it apart from a healthy one.

### 16.4 The worklist, the estate summary and notification

Outstanding work is **derived from the register rather than assigned** — no task table, so it cannot go
stale, disagree with the register, or accumulate orphans — and filtered to what a principal holds the
permission and scope to do, and for attestation to their own role's signature.

`core/notify/` is delivery, not a queue. Three channels and none of them a dependency: the log channel is
always available and is the honest default for an instance with nowhere to send; webhook and SMTP both use
the standard library. A **digest per person per run**, not a message per item, because a message per finding
is how somebody starts filtering the sender, at which point the platform has made itself invisible while
appearing diligent. **Silence when nothing has changed**: each delivery records the digest of the *work* it
described, and an unchanged worklist is suppressed until a quiet period passes. Escalation is **by role
rather than hierarchy**, because MAYA does not know who reports to whom and should not pretend to. A failed
delivery is recorded and raises evidence, because silence about a failed send is how somebody concludes they
were never told, which is worse than not having sent. And it notifies from the **same call the dashboard
makes** — two views of one derivation, not two derivations.

---

# Part IV — Interfaces

## 17. The HTTP surface

One FastAPI application, 232 route registrations across thirty modules in `routes/`. Two hundred and three sit
under `/api/v1`; the other twenty-nine are three health endpoints, five authentication endpoints and
twenty-one further pages — twenty-two page routes in all, since `GET /login` is both. A hundred and fourteen
mutating endpoints — `POST`, `PUT`, `PATCH`, `DELETE` — and the rest are reads.

### 17.1 Conventions, and which of them exist

| Concern | Today |
|---|---|
| Base path | `/api/v1`, defined once in `routes/base.py::API` |
| Spec | OpenAPI generated by FastAPI at `/api/v1/openapi.json` |
| Authentication | Session cookie for the interface; HTTP Basic against the same principal register for services |
| Refusals | `error` / `detail` / `remediation` at the top level, mapped in one table |
| Pagination | `?limit=` and `?offset=` through `core/domain/paging.py`, applied **after** scope filtering |
| Everything else | `ETag`/`If-Match`, `Idempotency-Key`, `?expand=`, `?fields=`, `?as_of=`, keyset cursors, SSE and `Sunset` headers are **not built** — [Part VI](#part-vi--designed-and-not-built) |

The pagination detail is not decoration. Filtering happens before the page is cut, because page two of a
filtered list must not be page two of the unfiltered one with holes in it.

### 17.2 Browser-surface security

The interface's authority is a session cookie, and a session cookie is **ambient** — the browser sends it
whether or not the page that triggered the request came from us. Two defects followed from that and both
are closed.

**The open redirect** was the sharper one. `POST /login` honoured whatever `next` carried, so
`/login?next=https://evil.example/phish` sent the browser there immediately after somebody typed real
credentials into the real form on the real domain. The same door stood open on the SSO path, where the
target survived a round trip through the identity provider before being followed, so it is now bounded
before it is *remembered*. A scheme, a host, a protocol-relative `//host`, the backslash spellings browsers
normalise and the control characters they strip are each **replaced by the fallback rather than sanitised**,
because a redirect target somebody had to repair is one nobody understands.

**CSRF** had exactly one defence, `SameSite=Strict`, which is real and is *somebody else's*: enforced by the
browser, removable by a client that does not implement it or an intermediary that strips the attribute, and
its removal invisible from here. The token added beside it applies to one case and states why — a
state-changing method whose authority came from the cookie. Requiring one from a Basic-authenticated engine
would protect nothing, since the browser never sends that header unprompted, while breaking every service
client, which is how a control ends up switched off in configuration.

Three implementation decisions carry weight. It is enforced in **middleware**, because a hundred and fourteen
mutating endpoints is a hundred and fourteen chances to forget. Exemptions are **exact paths rather than
prefixes**, so the exempt set cannot grow as routes are added beneath it. And the ordering is load-bearing:
the guard registers *before* the session middleware, which places it *inside* it, since Starlette wraps
later-added middleware outermost and a guard running before the session is decoded has nothing to compare
against.

## 18. Authorisation

`core/authz/` — eight roles across three lines of defence, seventy-two permissions, refused incompatible
pairs, and entity and domain scope.

Three properties are worth the space.

**Scope filters listings *and* detail pages.** `login_required` answers whether somebody is signed in; it
does not answer who they are or what they may see, and the pages once used it alone. A validator scoped to
one legal entity got a 403 from the API and correctly saw nothing on the dashboard — then loaded the model
page by URL and received its versions, alias history, warrant grants and full evidence chain. Every page
that resolves one named object now calls `may_view` before rendering, and a refusal renders a page-shaped
403 that says the thing exists and is outside your scope, rather than a 404 that pretends otherwise.

**Segregation of duties is read from the evidence chain**, not from a second who-did-what table. A rule may
name the payload field carrying the identity it is about, because an evidence node's subject is not always
the thing an act concerns: a finding is raised against the *model*, which is where a reader looks for it,
while the act being checked is about one finding. Without that, the raiser-may-not-close rule was inert over
HTTP — it searched under the finding's own id, found nothing, and permitted everything.

**Permissions are not uniformly held, and the distribution is the control.** `report:read`, for instance, is
held by four of the eight roles — admin, auditor, model risk manager and validator — which is why the board
pack page refuses rather than renders for the other four.

Single sign-on is the authorisation-code flow with PKCE, a state parameter and a nonce, with **RS256
verification in the standard library** for the same reason every asset is vendored. The verifier
**constructs** the padded block the signature should have produced and compares the whole of it rather than
parsing what it recovers — the difference between correct PKCS#1 v1.5 and the Bleichenbacher forgery — and
it decides the algorithm itself rather than reading `alg` from the token. What is not mechanical is roles:
an identity provider that grants MAYA roles is one that decides segregation of duties, and the person
administering it is very often the person whose duties are being segregated. So **group claims are mapped,
never obeyed** — a group with no mapping grants nothing — and the incompatible-roles check applies to a
directory exactly as it does to a local principal, *before* provisioning, so the lesser problem cannot hide
the greater. Provisioning on first login is off by default, because it hands everybody in the directory a
foothold in the model register.

## 19. The interface and the SDK

### 19.1 The interface

Server-rendered Jinja, twenty-two page routes, twenty-five templates, and six vendored files totalling
about 690 KB — Bootstrap, Bootstrap Icons and jQuery. There is no CDN and no external fetch, because a
governance platform that cannot be deployed air-gapped is one somebody works around.

**There is no vendored graph library, no charting library and no table plugin.** `web/static/js/tables.js`
is 220 hand-written lines giving every table search, sort and paging: sorting is always available, because a
reader who wants the worst finding first should not have to count rows; search and paging appear at eight
rows, because a pager under four is noise. Numbers sort as numbers and dates as dates, so a Gini of 0.61
does not sort below 0.7 as a string would.

The one structural fact about the interface is a defect rather than a design, and it is stated here because
this document is where a reader would look for it: **reads are in-process and writes go through the API.**
`routes/ui_routes.py` makes fifty-one direct service calls, so no read a page performs is exercised through
`/api/v1`. Authorisation does not suffer — a page asks the authoriser the API asks — but the property
ADR-011 exists to obtain does not hold, and nothing forces the two to agree on reads. Full treatment,
including the eight screens designed and not built, is [08](08-ui-ux.md).

### 19.2 The SDK

`sdk/python/maya_sdk`, standard library only, and one rule: **it decides nothing.** No local rule about who
may act, no copy of the tiering bands, no view of whether a version is approved, no enumeration of the verbs
a class admits — every one of those would be a second implementation of a governance rule, and a second
implementation disagrees with the first eventually, in the direction of permitting more, because that is the
direction in which nobody files a bug. A source walker in the suite enforces it by refusing a trainability
class that appears in client code rather than in prose.

Four other decisions. **Refusals are raised, never returned**, because a caller who forgets to check a
returned verdict has continued past a governance decision while their code reads as though it succeeded, and
`code`/`detail`/`remediation` all survive the crossing along with the request id. `Refused` and
`Unreachable` are **deliberately unrelated types** — *"MAYA said no"* and *"MAYA did not answer"* call for
opposite responses. **`POST` is never retried**, because a create that timed out may well have succeeded.
And the artifact digest is computed **client-side** and sent, so the platform checks what arrived against
what was meant rather than hashing whatever turned up.

It is tested against the real application in process through a transport seam, because a mock of the thing
under test proves only that the mock agrees with itself. `sdk/java/` contains a README stating the contract
a JVM client must honour and no source, because a stub that compiles and does the wrong thing is worse than
an empty folder.

---

# Part V — Cross-cutting

## 20. Persistence and transactions

`db/` is the only package that knows about storage. `Database` wraps one SQLAlchemy engine; `Repository` is
a table name plus the columns that hold JSON and the columns that hold `0`/`1`, declared rather than
handled, so no service has to know how a truth value is persisted.

`Database.transaction()` is a re-entrant context manager: a nested call joins the transaction already
running rather than opening a second one and deadlocking against it, and outside one every statement opens
its own connection.

**It is called in exactly one place in `core/`, inside `EvidenceEngine.append`, and in no service and no
route.** That is the honest state of DR-4 and it deserves to be stated in the section about transactions
rather than left to be discovered. Every governance act is therefore two commits: the state change, then the
evidence node. The window between them is small and it is not zero, and what falls into it is a model that
exists with no record of its registration — which matters more than a missing row, because segregation of
duties is decided by reading the chain, so *"you cannot approve what you created"* has nothing to read. The
mechanism to close this exists and is re-entrant by construction; nothing uses it.

There are no migrations and there is no outbox. Schema evolution is expand-and-contract by hand across two
files; there is no relay, no broker and no eventual consistency to reconcile, because there is nothing to be
eventually consistent with.

## 21. Concurrency and idempotency

| Hazard | What actually holds |
|---|---|
| **Two governance acts appending evidence at once** | The chain is a read-then-write — take the head, insert head+1 — and it was neither atomic nor retried. Measured at four threads: **7% of appends raised**, and twenty-four concurrent registrations produced twenty-four models and fourteen evidence nodes. It is now inside a transaction and **retried on contention with jittered backoff**. The jitter is not cosmetic: without it every loser retried at the same instant, so eight threads exhausted eight attempts without any making progress — the retry was there and the contention pattern defeated it |
| **Two versions with the same semver** | `UNIQUE (model_id, semver)`, and `VersionService.create` refuses before reaching it so the message is a governance sentence rather than a constraint violation |
| **The same artifact uploaded twice** | Content addressing: the same bytes are the same name, so the second upload is a no-op |
| **A telemetry batch delivered twice** | `telemetry_batch.digest` is `UNIQUE` over the digest of the batch's own rows |
| **A scheduler job running twice** | Every job re-derives its condition and checks whether the finding it would raise already exists. Two replicas running the same job produce one finding |
| **A notification sent twice** | Each delivery records the digest of the work it described and an unchanged worklist is suppressed. This is the one place with a genuine gap: delivery is not transactional, so a crash between the send and the record loses or repeats a digest |

There is no `Idempotency-Key`, no replay window, no advisory lock and no optimistic-concurrency header. With
one process those are cheap to add and currently absent.

## 22. Refusals

The interesting behaviour of this platform is what it will not do, so the refusal path is designed rather
than inherited.

**One table.** `routes/base.py::STATUS` maps 272 refusal codes onto fourteen HTTP statuses, and
`tests/test_refusal_discipline.py` asserts that every coded refusal maps to a status that says who must act
and that no code is mapped twice. The distribution is itself informative: 106 are `422` (the request is
incoherent), 58 are `409` (the platform's state conflicts with it), 35 are `403` (you may not), 28 are
`404`, and the rest are the specific ones — `410` for revoked and expired, `413` for too large, `423` for
restricted by a finding, `501` for a capability this instance was never wired for, `502` for a dependency
that answered wrongly.

**The status is a decision about who acts, not about who is at fault.** `provider_unavailable` is `501`
rather than `503` because it is not that the provider is down, it is that this instance was never wired to
one, which is a deployment decision rather than a transient fault. `parameter_mismatch` is `409` rather than
`422` because nothing about the request is wrong — the numbers in the register stopped matching what was
approved, which is a conflict in the platform's own state and a security event.

**Three fields, always.** `error` is the code, `detail` says what was violated, and `remediation` says what
to do — not what went wrong. A refusal a caller cannot act on is an error message with better grammar.

## 23. Observability

**One logger, one format, and every line says which request produced it.** `core/log.py` carries the request
id and the acting principal on **one mutable dict per request** rather than a context variable per field,
and that shape is a constraint rather than a preference: a sync route runs in a threadpool with a *copy* of
the context, so a `ContextVar.set` inside it is invisible to the middleware that resumes afterwards, and the
access line would have said every request was anonymous however carefully the route identified its caller. A
copied context still points at the same dict, so a write crosses that boundary while a rebind does not.

An inbound `X-Request-ID` is honoured when it is **safe to log** — that is what lets one trace span a
gateway, a queue and this process — and replaced when it is not, because the value lands in a log file and a
newline in it writes a line of somebody else's choosing. The context filter is installed on the **handler**
rather than on a logger, since a filter on a logger does not run for records propagating up from its
children.

One access line per request carries method, path, status and duration at a level that follows the outcome: a
refusal is a governance decision worth seeing at `WARNING`. JSON output is offered rather than imposed,
because a person reading a terminal is served worse by it.

**Three health endpoints.** `/health` and `/health/live` are trivial. `/health/ready` includes the evidence
chain — a broken chain means the assurance claims cannot be trusted, so the node is not ready and returns
`503` — using the incremental check, plus the scheduler's own state as informational.

The reason there is no separate audit log is the reason there is no separate anything: two records of who
did what are two records that can disagree.

## 24. Performance, and what is actually measured

**Every performance figure in [03 §7](03-requirements.md) is a target and not a result.** No load test has
been run, no p99 has been measured under concurrency, and the three spikes named in
[10 §2.3](10-roadmap.md) — a point-in-time join at a billion rows, warrant resolution under load, sandbox
escape testing — have never been performed.

What *is* measured is the scale suite (`tests/test_scale.py`, `tests/test_transfer_scale.py`, 19 tests),
and it is written to two rules that are worth copying.

**Assert shape, not stopwatch.** A threshold in milliseconds is a promise about somebody else's hardware,
and a suite that fails on a loaded machine is one people re-run rather than read. So the assertions are
mostly about *complexity*: that doubling the estate does not more than double the work; that an operation
claimed constant in estate size is; that a read claimed not to materialise a dataset does not. Where a
wall-clock budget appears it is generous by an order of magnitude, because its job is to catch a change from
linear to quadratic rather than to measure a machine.

**Run at a size the default suite will not.** Marked `scale` and excluded by default, because a slow suite
gets disabled and a disabled suite proves nothing. It found the evidence-chain defect in
[§5.2](#52-verification-and-the-two-questions-it-answers) on its first run.

Two known costs are worth naming here because a reader will meet them. Full chain verification was 2.9
seconds and 83 MB at forty thousand nodes; the readiness probe no longer pays it, and **the dashboard and
every document compile still do**. And warrant resolution touches four to six tables with no cache, which is
fine at one process and is not a design that reaches the latency targets in 03.

## 25. Testing design

2,246 tests across 62 files, of which 2,227 run by default and 19 are the scale suite.

| Layer | What it proves |
|---|---|
| **Unit and service** | Each package against real repositories on a temporary SQLite file. There are no mocks of the thing under test, because a mock of that proves only that the mock agrees with itself |
| **Laws** (`tests/test_laws.py`, `test_risk.py`, `test_domain.py`, `test_composition.py`) | Eighteen of the twenty-one foundational laws are executable, beside the code they constrain rather than in a `tests/laws/` package. The three that are not are named in the file with the reason |
| **API** (`test_api*.py`) | Every endpoint through the real application, including the pages, because three controls were once inert over HTTP while their unit tests were green |
| **Dialect** (`test_postgres_dialect.py`) | The second dialect actually runs — it did not, for as long as nobody tried |
| **Concurrency** | The chain under contention. There were zero of these in fourteen thousand lines of test code, and a reviewer found the defect that gap was hiding |
| **Scale** | Complexity, not stopwatch. Excluded by default |
| **Discipline walkers** | See below |

**The discipline walkers** do not test a feature. They walk the source and hold a rule that would otherwise
rot, and each exists because the rule it holds had already been broken once:

| | |
|---|---|
| `test_logging_discipline` | no exception is ignored: every `except` logs, none is bare, none is only `pass` |
| `test_refusal_discipline` | every coded refusal maps to a status that says who must act, and no code is mapped twice |
| `test_schema_discipline` | one typed declaration renders identically to both dialects; the checked-in `.sql` is not stale; a truth value is a `Boolean` and a count is not; no relational table holds bulk data |
| `test_size_discipline` | no source file over 1,500 lines |
| `test_documentation_counts` | every number claimed in prose is recounted from the code — **and from `.py` docstrings**, because two source files said "seventeen" against nineteen entries and survived every pass while the test read only markdown |
| `test_deck_geometry` | no slide has overlapping or escaping content |
| `test_ui_tables` | every HTML table has a header, and pagination where it needs one |
| `test_laws` | the foundational laws, run as tests, with the three that do not run named |

**This is now a gate.** It was not: for most of the build there was no pipeline, no linter, no type
checker and no coverage threshold, and the suite was real but run by a person — which is a different
thing from a build that fails.
[11 §4.8](11-adversarial-review.md#48-the-laws-are-the-acceptance-criteria-and-there-is-now-a-build) is
where that was argued, and it was right. `.github/workflows/ci.yml` now runs seven jobs: hygiene
(linter, types, dependency advisories, secrets, SBOM, spec lock), discipline, laws, deck geometry, the
suite in four shards, a combined coverage floor, and PostgreSQL.

Two of them are worth naming for how they are drawn rather than what they run. The type check gates on
the 223 modules that pass and carries 61 in a backlog file, because `mypy || true` is a step that
always passes — the defect this codebase is named for — and `--strict` across 284 modules in one
release produces a blanket ignore, which is the same step wearing a hat. And the linter's rule set is
**chosen**: the default reports three thousand findings, nearly all of them that the codebase writes
`Dict[str, Any]` rather than `dict[str, Any]`, which is a house style applied consistently across four
hundred files. `pyproject.toml` says why each rule is in or out, and the security set found a real
defect on its first run.

---

# Part VI — Designed and not built

Everything below this line is conditional. **None of it runs.** It is here because each item is a decision
already taken, and a reader planning against this system deserves the list rather than a discovery.

## 26. Infrastructure the design assumes and the build does not have

| Designed | Why it is not built, and what its absence costs |
|---|---|
| **Redis descriptor cache**, with pre-warm-before-invalidate, single-flight coalescing and stale-while-revalidate | Finding H-1's stampede cannot occur because there is no cache. TTL jitter — the one piece that only matters *once* a cache exists — is built. Without a cache, every resolution reads four to six tables and the p99 targets in 03 are unreachable |
| **Kafka event stream** (`maya.model.*`, `maya.warrant.*`, …) and a transactional **outbox** | There are no domain events leaving the process. Consumers integrate by polling the API |
| **`warrant_projection` read model** | H-2's disposition. The warrant path reads normalised tables. The coupling costs nothing with one process and forecloses the deployment independence it was raised to protect |
| **Spark** for point-in-time joins and monitor evaluation | Assembly and evaluation are in-process over pandas and Delta. Fine at hundreds of models; not at an estate-wide nightly sweep |
| **An online feature store**, namespaced by view version, with dual-write and governed namespace retirement | `L-17` has nothing to compare against, so training–serving skew is undetectable. This is the one absence that makes a whole law inert. `serving_namespaces()` computes the half that can exist without a store |
| **Postgres row-level security**, forced, with a non-owner application role and a cross-entity negative test | H-5. Scope is enforced in Python and the database offers no backstop |
| **A separate audit database**, read replicas, monthly partitioning | H-9. One database, one identity, one flat evidence table |
| **WORM anchoring and an RFC-3161 timestamp** on the daily chain head | C-4 disposition 2, and the largest open weakness in the platform. Verification compares the chain against itself |
| **Asymmetric warrant signing** | HMAC-SHA256 ships. RS256 verification already exists in `core/authz/jws.py` for OIDC, so the primitive is here and the gap is key management. Verifying a warrant currently requires holding the key that could mint one |
| **A plugin loader and a fibre registry** | `L-15` cannot be checked, so *no fibre is empty* is an intention. A model class is a string; adding a family is a convention rather than a validated extension |
| **Continuous integration** | Seven of the nine gates in [12 §7](12-implementation-plan.md) now run. What remains is DAST, a generated client and an accessibility run; migration rehearsal is not applicable, because there are no migrations |

## 27. Capabilities designed and not built

| Designed | Status |
|---|---|
| **The decoupled front end** ([ADR-011](adr/ADR-011-decoupled-frontend.md)) — two processes, OIDC in the browser, a generated client pinned to `openapi.lock.json`, CORS | Accepted and not built. There is no CORS middleware anywhere, which a two-origin deployment could not function without. [08 Part two](08-ui-ux.md) is the full design |
| **Eight screens** — dependency and blast-radius explorer, validation workbench, discovery triage, use reconciliation, examiner portal, campaigns, admin, schema-driven metadata form | None exists. The `input_to` edges are typed and stored and nothing draws them |
| **API conventions** — `ETag`/`If-Match`, `Idempotency-Key`, `?expand=`/`?fields=`, `?as_of=`, keyset cursors, SSE on `/events`, `Sunset` headers, `/derivations/{id}` | None built. Listings return whole and paging is limit/offset |
| **Composite warrants** and the interaction premium | `L-21` now gives `L-14` a derived composite schema to quantify over, and `shared_dependencies` computes the obstruction. The aggregate `ρ` is not built, so the question supervisors actually ask has a definition and no computation |
| **Correlated findings** — one root finding with impact records | M-8. The `finding` table has no root, parent or correlation column. Suppression happens at delivery instead |
| **Fact sourcing for tiering** — exposure bound to a system of record, an `unsourced` flag, peer-cohort outlier detection, retrospective calibration | H-8, open in full |
| **Crypto-shredded personal data** — payload in Delta under a per-subject key, key destroyed on erasure | H-3's mechanism. What runs discards the payload instead, which satisfies `L-18` by making retrieval impossible. There is no `payload_uri` column |
| **Legal hold, tombstones and a retention state machine** | M-7. Deletion is administrators-only, reasoned and evidenced, and cascades to nothing |
| **Cost attribution** — per-model and per-business-unit budgets, showback, cost as a monitored metric | M-6. Not built in any form |
| **Connectors** — MLflow, Unity Catalog, git — and EUC discovery | The inventory is what somebody registered |
| **PDF and DOCX rendering** | The compiler emits markdown, rendered through the same pipeline as the help system |
| **A Java SDK** | The contract it must honour is written down in `sdk/java/README.md`; the implementation is not |

---

## Traceability

| This document | Satisfies |
|---|---|
| [§3](#3-core-domain) Core domain | [00 §2–4](00-mathematical-foundations.md); `L-3`, `L-7`, `L-12`, `L-20` |
| [§4](#4-registry-versions-and-composition) Registry | `FR-VER-*`, `FR-INV-*`; `L-2`, `L-21`; findings C-3, H-4 |
| [§5](#5-evidence) Evidence | [00 §6](00-mathematical-foundations.md); `L-9`, `L-18`; findings C-4, H-3, M-2 |
| [§6](#6-risk-and-tiering) Tiering | [00 §10](00-mathematical-foundations.md); `FR-TIER-*`; `L-4`, `L-5`; finding H-8 |
| [§7](#7-regimes-as-institutions) Regimes | [00 §9](00-mathematical-foundations.md); `L-8`, `L-16` |
| [§8](#8-versioned-gates) Gates | [09 §5](09-security-compliance.md) |
| [§9](#9-lifecycle-approval-and-attestation) Lifecycle | `FR-LC-*`; `L-1`, `L-5`; finding C-5 |
| [§10](#10-validation-and-findings) Validation | `FR-VAL-*`; finding M-8 |
| [§11](#11-documentation) Documentation | `FR-DOC-*`; `L-11`; [17 §8](17-feature-and-model-algebra.md) |
| [§12](#12-the-feature-platform) Features | `FR-FEA-*`, `FR-PAR-*`; `L-10`, `L-17`, `L-19`, `L-W8`, `L-W9`; findings C-2, H-6; [15](15-featuresets-and-parameters.md), [16](16-features-composed-and-shaped.md) |
| [§13](#13-monitoring-and-telemetry) Monitoring | `FR-MON-*`; finding H-7 |
| [§14](#14-warrants) Warrants | `FR-WARRANT-*`; `L-W0 … L-W13`; findings C-1, C-6, H-1, H-2; [06](06-warrants-and-execution.md) |
| [§15](#15-machine-assistance) Assistance | [00 §11](00-mathematical-foundations.md); `FR-AI-*`; [13](13-ai-in-the-platform.md) |
| [§17](#17-the-http-surface)–[§19](#19-the-interface-and-the-sdk) Interfaces | `FR-PLT-*`; ADR-008, ADR-011; [08](08-ui-ux.md), [09 §1](09-security-compliance.md) |
| [§20](#20-persistence-and-transactions)–[§21](#21-concurrency-and-idempotency) | `NFR-DATA-*`; [05](05-data-model.md); finding M-3 |
| [§22](#22-refusals)–[§25](#25-testing-design) | `NFR-OPS-*`, `NFR-MNT-*`; ADR-010 |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
