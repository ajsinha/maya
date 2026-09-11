# 04 — Architecture

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Companion to** [00 — Mathematical Foundations](00-mathematical-foundations.md) ·
[03 — Requirements](03-requirements.md)
**Annexes:** [05 — Data Model](05-data-model.md) · [06 — Warrants & Execution](06-warrants-and-execution.md) ·
[07 — Feature Platform](07-feature-platform.md) · [08 — UI/UX](08-ui-ux.md) ·
[09 — Security & Compliance](09-security-compliance.md) · [14 — Detailed Design](14-detailed-design.md)

---

## 0. The argument this document makes

An architecture diagram is a drawing of boxes somebody agreed to. What makes it an architecture is
the **boundaries**, and a boundary is only real if crossing it is refused.

So this document is not a catalogue of components. It is **seven boundaries**. Each section states
what the boundary separates, the concrete failure that occurs when it is not there, and **what
enforces it** — a refusal in code, a test that walks the source, or, in two cases, nothing yet, which
is said rather than left to be discovered.

| # | The boundary | What it prevents | Enforced by |
|---|---|---|---|
| **B1** | governance ⊥ execution | governance in the serving path; a version move that makes every consumer redeploy | the warrant protocol — MAYA runs nothing |
| **B2** | control plane ⊥ data plane | a governance database becoming a data lake nobody chose | `tests/test_schema_discipline.py` walks the DDL |
| **B3** | domain ⊥ storage | a dialect change touching two hundred files; domain logic untestable without a database | `db/` is the only package that knows a table exists |
| **B4** | domain ⊥ transport | business rules in a route handler, enforced on one path and missing on the other | `core/domain/` imports nothing from MAYA; `routes/` is imported by nothing |
| **B5** | platform ⊥ artifact | a malformed graph taking the register down with it | a child process with limits from the warrant — **honestly scoped**, §5 |
| **B6** | record ⊥ assertion | two accounts of who did what, which can disagree | there is no audit log; the evidence chain is it |
| **B7** | derived ⊥ stored | a stored derivation going stale and being believed | nothing computable is a column; the tier stores its *derivation* |

Two boundaries the design names and does **not** yet enforce are called out where they belong: the
import-linter contract for B4 (`NFR-MNT-002`) is a plan rather than a CI gate, and B5 protects
against accident and not against malice.

---

## 1. The shape, in one paragraph

> MAYA is **one Python process** — a FastAPI application, `run_maya_web.py::create_app` — over a
> relational register that is SQLite by default and PostgreSQL by URL alone, a Delta Lake tree on the
> filesystem for feature and telemetry values, and a content-addressed artifact store keyed by
> digest. It holds a fibred registry of models as morphisms in `Para(Stoch)`, binds every governance
> claim to an append-only hash-chained evidence graph, evaluates supervisory obligations as
> institution-indexed policy, and issues **signed, expiring, entitlement-bound warrants** that let an
> external engine run a governed version on demand.

**What it deliberately is not.** There is no message bus, no cache tier, no task queue, no
orchestrator, no service mesh and no second deployable unit. Everything is vendored; nothing calls
out. The rule that decided most of this: **a governance system that cannot be deployed air-gapped is
one somebody works around**, and a system somebody works around records less than no system at all,
because it also reports success.

The cost is stated rather than hidden. §9 is one table of every place the production *target*
differs from the build, and §10 is what fails and how.

### 1.1 Drivers, ranked

1. **Evidential integrity.** The system's value is that its claims are checkable. Immutability and
   hash-chaining beat every other concern, including performance.
2. **Extensibility without migration.** A new model class or a new regulator must not need DDL.
   §8 is honest about how much of that is realised and how much is not.
3. **Warrant-path availability.** Production scoring depends on it (`NFR-PERF-002`, `P9`).
4. **Auditability of every derivation.** Nothing derived may be unexplainable (`P8`).
5. **Developer ergonomics.** If the compliant path is slower than the non-compliant path, the
   inventory rots. This is fifth in the list and first in practice.

---

## 2. B1 — Governance is separated from execution

### The failure it prevents

Put governance in the serving path and two things follow, both bad. Every scoring call now depends
on the availability of the control plane, so an inventory outage becomes a trading outage. And a
governed version move — promoting a challenger, rolling back after a breach — becomes a deployment
in every consuming system, which means it will be done rarely, late, and by exception.

### The mechanism

A consumer holds a **URN** and never a version:

```
maya://model/credit.pd.smallbiz#champion
```

Everything else resolves at the moment of use, against the policy in force at that moment. MAYA
returns a **warrant**: a signed document naming the version, the artifact and its digest, the input
and output schemas, the operating boundary, the resource ceiling, who may run it, for what, and until
when. An engine verifies the signature and acts. **MAYA never executes anything on the serving
path**, and there is no path by which a scoring call reaches the register.

The warrant is the product of four independent vocabularies, not a union of special cases —
`core/execution/grammar/vocabulary.py`:

| Axis | Question | Values |
|---|---|---|
| `parameters.kind` | how is `P` inhabited? | **eight**, from `none` to `opaque` — and the trainability class `T0`–`T8` is **derived** from it, never declared |
| `realisation.runtime` | how does the kernel become runnable? | **eighteen**, each declaring the keys its `entry` block must carry |
| `operation.verb` | what is being asked of it? | ten: score, fit, validate, backtest, explain, simulate, stress, optimise, generate, monitor |
| `data.*.binding` | where do the inputs come from? | twelve, of which three are bitemporal and can therefore answer *what was known at time t* |

`descriptor_only` is one of the nineteen and matters most in a bank: much of the estate already runs
inside engines nobody is going to replace, and a warrant that carries governance and no execution is
the honest description of that case.

**Fourteen admissibility laws (`L-W0`–`L-W13`) are checked before the signature.** They quantify over
facts the platform *derives* rather than a category anybody attached, which is why one document
serves every family: a `fit` on a T0 kernel is refused because its parameter object is terminal, not
because somebody ticked a box. Full protocol in [06](06-warrants-and-execution.md).

### What is on the far side of the boundary

`core/execution/engine.py` ships a **captive engine** so that the protocol has a reference
implementation, and it is deliberately not privileged: it resolves a warrant like any other consumer
and refuses by name a runtime it does not have. It implements six of the nineteen —
`python.callable`, `onnx`, `pmml`, `quantlib`, `estimator` and `rules`, and answers for
`descriptor_only` as well. `RuntimeRegistry.invoke` distinguishes two refusals that need different
actions: a runtime never implemented (route the warrant elsewhere) and one whose dependency is
missing (install the package).

`rules` is the newest and the odd one out: it loads no artifact, needs no dependency, and its
parameter object is a document MAYA can read. The rule set reaches it the way every register-held
parameter object does — `CaptiveEngine._with_parameters` resolves the approved set and re-derives
its digest — so running a rule set at an unapproved point of `P` is refused by the same mechanism that
refuses running a scorecard at unapproved coefficients, rather than by anything written in the
runtime. It is also absent from `UNVERIFIABLE_DETERMINISM` (`L-W5`) for the same reason the captive
estimator is: MAYA holds the rules and can verify a determinism claim by executing them.

---

## 3. B2 — The control plane is separated from the data plane

### The failure it prevents

A governance record is something a person reads one at a time: a model, a finding, an approval. A
feature view is hundreds of millions of rows. Put both in one store and the register grows without
bound, backups stop fitting, and the thing an examiner needs to read in an afternoon has become a
data lake nobody chose.

### The rule

| | |
|---|---|
| **R1** | Anything that participates in a governance *decision* lives in the relational register |
| **R2** | Anything whose volume is proportional to *business events* rather than to *models* lives in Delta |
| **R3** | The register never stores feature or telemetry **values** — only definitions and pinned pointers |
| **R4** | Delta never stores authoritative governance state |

### What enforces it

`tests/test_schema_discipline.py::test_no_relational_table_holds_bulk_values` walks both schema files
and refuses a column named `rows`, `values`, `data`, `records`, `sample`, `observations`, `frame` or
`dataset`. The positive half is checked too: `feature_view`, `feature_view_version`,
`dataset_snapshot` and `telemetry_batch` must each name their Delta location, because a pointer that
does not say where it points is not a pointer.

### The Delta tree

`db/database.py::DeltaPaths` — four areas, and nothing else is a Delta area:

```
data/delta/
├── features/<entity>/<view>/v<n>/     one namespace per feature view VERSION (07 §5)
├── snapshots/<snapshot_id>/           immutable, PIT-verified training sets
├── telemetry/                         two bitemporal streams per model version:
│                                        scores (exist when the model runs)
│                                        outcomes (learned later)
└── monitoring/                        metric time series
```

A versioned table format rather than a plain table for one reason that decides it: **table versions
give the transaction-time axis for free**, which is the mechanism behind point-in-time correctness
(`L-10`). Every feature row carries `event_ts` and `ingest_ts`, and one missing either is refused at
the write.

**Delta or Iceberg, by configuration.** The six operations MAYA asks of a table format — open,
current version, read at a version, read whole, stream, write — exist in both, and nothing above
`db/` knows which is underneath. Delta is the default and is what the soak and every worked example
ran against; `MAYA_TABLE_FORMAT=iceberg` (or `data.table_format`) selects the other, for a bank whose
lakehouse is already Iceberg and whose query engines should be able to read the feature store
directly. `db/table_backend.py` decides once at start-up. Switching an estate that already holds data
**does not migrate it**, and start-up says so rather than letting an invisible table read as empty.
The one thing that reached the register: a snapshot id is int64, so the version columns are `BIGINT`.
[07 §9.4](07-feature-platform.md) is the treatment.

> **Not built.** Change Data Feed, deletion vectors, crypto-shredding, `VACUUM` retention by
> regulatory class, liquid clustering and Spark are all target and none is used. `DeltaPaths` carries
> a `retention_days`; nothing acts on it.

---

## 4. B3 and B4 — The domain is separated from storage, and from transport

### 4.1 The map, as built

The package is `core/`; every name below is a directory or a file on disk.

```
core/
├── domain/          the algebra, importing nothing else in MAYA
│   ├── algebra.py       Para(Stoch): kernel, parameter object, fit procedure — and
│   │                    trainability_class as a DERIVED property, so T0–T8 is computed
│   ├── schemas.py       the schema and its variance rule (L-12)
│   ├── lattice.py       ONE partial order: A ⊑ B, "A can stand in for B" (L-20)
│   ├── contracts.py     assume–guarantee: refines, compose, conjoin, quotient (L-7),
│   │                    over Bound.meet and Bound.join, both partial
│   ├── identity.py      probe-relative equivalence (Yoneda), version semantics
│   └── paging.py        OFFSET paging with a cap, so a listing cannot be a full
│                        scan. Offsets on purpose: a register is read by people
│                        who want page four. `core/http/conventions.py` holds the
│                        KEYSET cursor, which is for the other case — a queue
│                        being written to while somebody drains it, where an
│                        offset silently skips a row
├── registry/        models, immutable versions, governed aliases
│   └── composition.py   the model graph, and `input_to` TYPE-CHECKED (L-21)
├── rules/           the T8 parameter object, given a shape: a condition tree with no
│                    arithmetic, reachability over interval-and-set domains (sound and
│                    INCOMPLETE), contradiction, conformance — and an editor that mints
│                    no authority the parameter register did not already hold
├── features/        eighteen modules: catalogue, registry, views, contracts, assembly,
│                    pit, derived, expressions, sets, shapes, composition, lifecycle,
│                    policy, normalisation, preparation, alignment, transfer, common
├── parameters/      inhabitants of P — a fit makes one of these, never a version
├── execution/       warrants: grammar/ (four vocabularies + the admissibility laws),
│                    profiles.py (templating the REQUEST), runtimes/, sandbox.py,
│                    urn.py, grants.py, builder.py, signing.py, engine.py
├── artifacts/       the content-addressed store: a file's name is its own hash
├── evidence/        semirings.py (seven, including ℕ[X]) and the append-only chain
├── risk/            materiality and complexity as separate lattices; τ (L-4), req (L-5)
├── validation/      catalogue, statistics, findings, ageing, workflow, replay
├── monitoring/      definitions, observations, breaches, delayed labels
├── telemetry/       two bitemporal streams, ingestion idempotent on the batch digest
├── lifecycle/       the record machine, quorum approval, attestation, amendments,
│                    and what each move costs a class at a tier
├── policy/          versioned gates: a rule is a predicate over a closed vocabulary
├── regimes/         institutions: signature, sentences, translation, engine, library
├── docs/            lenses (15), compiler, templates, subjects, training, dossier
├── attachments/     the documents people wrote, content-addressed
├── export/          export packs: digested member by member, gaps named
├── reporting/       risk appetite as a computable limit; indicators; the board pack
├── overlays/        post-model adjustments, time-boxed, with an ageing analysis
├── authz/           roles, scope, segregation from the chain, OIDC, RS256, CSRF
├── classification/  the sensitivity lattice, and the join that propagates it
├── assist/          machine assistance: capabilities, oracles, grounding, providers,
│                    and what each capability may spend before it spends it
├── baseline/        cold-start import and dated compliance debt (C-5)
├── estate/          the worklist and the summary, derived from the register
├── scheduler/       26 idempotent jobs, a runner and an optional in-process loop
├── notify/          a digest per person per run; silence when nothing has changed
├── content/         help, about and tutorials as markdown, rendered server-side
├── config/          YAML with a git-ignored .local overlay and ${...} resolution
├── log.py           one logger; request id and principal on every line
└── ports.py         the protocols the layers above depend on

db/       the ONLY package that knows about storage. One typed schema,
          fifty-one tables, no migrations. Repositories are the only interface.
routes/   31 HTTP route modules over one piece of shared scaffolding. Thin, no
          domain logic, one refusal table for all of them.
web/      Jinja2 templates and vendored assets (Bootstrap 5, jQuery). No CDN.
          The rule-set editor is the one page with real client-side state, and it
          is jQuery over a vendored Bootstrap page like every other one.
sdk/      python/ (standard library only) and java/ (a contract, not a build).
```

### 4.2 The dependency rule

`core/domain/` depends on nothing in MAYA. `registry/`, `risk/`, `evidence/` depend only on
`domain/` and `db/`. `routes/` and `web/` depend on everything and are depended on by nothing.

That direction is what makes the domain testable without a web server and the register replaceable
without touching the domain — and it is why switching dialects is a URL rather than a project.

> **Enforced by convention, not by CI.** The import-linter contract of `NFR-MNT-002` is a plan. What
> *is* enforced by a walking test is size (`test_size_discipline`: no source file over 1,500 lines),
> logging (`test_logging_discipline`: no exception is ignored — every `except` logs, none is bare,
> none is only `pass`), and refusals (`test_refusal_discipline`, §4.4).

### 4.3 What a request actually does

Middleware order is a design decision here, not a default, and both directions are deliberate.
`add_middleware` registered later wraps *outside*:

```
request
  └─ request_context        registered LAST → OUTERMOST. Must see every request,
     │                      including the ones refused before any route runs, or the
     │                      lines with no id are exactly the ones somebody is chasing.
     │                      Binds a request id and the principal to contextvars; echoes
     │                      the id back; logs one line at the level the outcome deserves.
     └─ SessionMiddleware   SameSite=Strict; https_only configurable (it was hard-coded
        │                   False, so the cookie never carried Secure behind TLS).
        └─ csrf_guard       registered FIRST → INNERMOST, because a CSRF check that runs
           │                before the session is decoded has no session to compare against.
           └─ router        validates input, calls a service, renders. No domain logic.
              └─ core/…     the decision, and the refusal if there is one
                 └─ db/…    a repository. Nothing above it has seen a table.
```

The CSRF guard is middleware rather than a check per route because there are more than a hundred
mutating endpoints, and **a control that a hundred places have to remember is a control that will be
missing from the hundred-and-first**. Its condition is narrow, and the narrowness is the design: **a
token defends ambient authority, and only ambient authority needs defending.** A session cookie is sent by the browser
whether or not the page that triggered the request came from us. An `Authorization: Basic` header is
not, so demanding a token there would protect nothing and break every service client. The check
therefore applies to exactly one case — a state-changing method whose authority came from the
session cookie — and to nothing else.

### 4.4 A refusal has one shape and one table

`routes/base.py` holds a single `STATUS` map from refusal code to HTTP status, and every domain
package raises the same shape:

```json
{"error": "nothing_to_fit",
 "detail": "markets.pricing.vanilla 1.0.0 is T0: its parameter object is the terminal
            object, so there is no point of P to move to",
 "remediation": "if this model does have parameters, the kernel declares the wrong
                 parameter_kind; fix the version rather than the warrant"}
```

`tests/test_refusal_discipline.py` parses the AST of every file under `core/`, collects every code
raised as the first argument of a `*Error`, and asserts each appears in `STATUS` mapped to something
other than a bare `400`. **A status that tells the caller nothing about who must act is not a
mapping.** It exists because fifteen execution-layer codes accumulated over three milestones, each
surfacing as an unexplained 400, and nobody noticed because no test exercised that path.

---

## 5. B5 — The platform is separated from the artifact

### The failure it prevents

The engine loads ONNX graphs and PMML documents — files whose contents it did not write. A
governance platform that runs an arbitrary artifact in its own process has adopted that artifact's
bugs, and a malformed graph that exhausts memory takes the register down with it.

### The mechanism, and exactly how far it goes

Artifact-backed runtimes run in a **`spawn`ed child process with `RLIMIT_CPU` and `RLIMIT_AS` taken
from the warrant** — the grammar already carries `constraints.resources`, and
`core/execution/sandbox.py` is where that section stops being documentation.

| Protects against | Does **not** protect against |
|---|---|
| a runaway artifact — CPU and address space are bounded, and the parent reclaims the child on timeout | **a deliberately hostile artifact.** The child shares the filesystem and the network namespace. Blocking those needs a container, a VM or seccomp |
| a crash — a segfault in a native runtime kills the child, not the platform | **a callable bound in process.** You cannot sandbox a function handed to you in your own address space, and bound callables run unisolated — one more reason not to use them for anything real |
| unbounded allocation — a request past the limit fails in the child | |

Being precise about that boundary is the whole point. **An engine that claims isolation it does not
have is more dangerous than one that claims none**, because the claim is what people rely on. See
[09 §2.2](09-security-compliance.md).

### The store on the other side of it

`core/artifacts/` is a content-addressed store: **the digest is the address.** That is not storage
tidiness, it is what makes the guarantee cheap — *the bytes match the warrant* is true by
construction rather than by a check somebody remembered to write; storing the same weights twice
stores them once, which matters when a challenger differs from its champion by a configuration
rather than a file; and an artifact cannot be edited in place, because edited bytes are a different
address and the old one still resolves to what was approved.

**Streamed, never buffered.** Bytes are hashed and written as they arrive, into a staging file moved
into place only once the whole object has landed, so a reader never sees half an object under a
digest that promises the whole one. A model file does not fit in memory twice, and a governance
platform should not be the process that discovers this. Eight formats are recognised, and two of them
— `torchscript` and `tar` — are recorded as **executing code on load**, so nobody has to remember
which is which. The cap is 8 GiB: large enough for the weights of anything a bank runs on its own
hardware, and small enough that somebody has to think before putting a foundation-model checkpoint in
a governance platform.

---

## 6. B6 — The record is separated from assertion

### The failure it prevents

The usual design has a governance database and, beside it, an audit log. Two records of who did what
are two records that can disagree, and the moment they do, the control is worthless — because the
one that gets believed is the one that is easier to read, which is not the one that is right.

**So there is no audit log.** The evidence chain is it.

### Structure

`evidence_node` is append-only and hash-chained. Each node carries a monotonic `seq`, its parents
as a set, a `content_hash` over the node's own content, a `prev_hash`, and a `chain_hash` over
`(seq, prev_hash, content_hash, parents)` together. That last term is what makes the two structures
one: the DAG is *inside* the chain rather than beside it. It answers finding **C-4** — a Merkle DAG
alone detects content mutation but **not** deletion of a leaf or insertion into history, because a
DAG has no global ordering, and the linear chain supplies one.

Finding **H-3** — append-only evidence and erasure are irreconcilable *if* evidence holds personal
data — is answered by making sure it does not. A node flagged `contains_personal_data` carries an
**empty payload and a pointer**, and the append path hashes what it actually stored, so the node
verifies against itself. That is `L-18`, enforced in `core/evidence/engine.py` rather than in DDL.

**Verification is incremental, and the reason is operational.** Walking the whole chain on every
readiness probe was O(chain) — 2.9 seconds and 83 MB at forty thousand nodes, and a busy instance
reaches a million in half an hour, at which point an orchestrator takes the node out of service for
being slow to answer whether it is healthy. So `evidence_checkpoint` records how far the chain has been
verified and what its head hash was. Readiness asks *has anything broken since*, which is O(new); the
full walk stays available and runs as a scheduled job, because only the full walk can answer *is the
whole chain intact*. A broken chain does **not** advance the checkpoint, because moving it past a
break would bless it.

### One traversal, six questions

`core/evidence/semirings.py` — a claim is a query over the graph, evaluated in whichever semiring
answers the question you asked:

| Semiring | `+` (alternative derivations) | `×` (joint dependence) | Answers |
|---|---|---|---|
| `BOOLEAN` | or | and | is this claim supported at all? |
| `COUNTING` | + | × | how many derivations support it? |
| `WHY` | union of supports | pairwise union | *which* evidence — what to show an examiner |
| `TRUST` | max | × | how much do we trust it? |
| `COST` | min | + | what is the cheapest path to closing the gap? |
| `FRESHNESS` | max | max | how stale is the newest thing it rests on? |
| `POLYNOMIAL` | ℕ[X] `+` | ℕ[X] `×` | **the universal one** — all of the above as images |

`POLYNOMIAL` is `ℕ[X]`, the free commutative semiring, and `pushforward` maps a polynomial into any
other. `L-9` asserts the universal property over 200 random derivation DAGs against five semirings,
which turns *the same traversal answers a different question for each semiring* from an intention
into a theorem the suite checks.

> **And it found something.** `FRESHNESS` is **not** a semiring. It is `(max, max)`, and
> `max(0, 5) ≠ 0`, so its zero does not annihilate and the universal property does not reach it. The
> practical consequence, worth knowing before reading a number: a claim resting on a *missing* fact
> reports the freshness of the facts that are present. See
> [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces).

### Segregation of duties, read from the chain

The usual design is a separate table of who-did-what, consulted when somebody attempts a conflicting
act — which is a second source of truth about history. `core/authz/segregation.py` instead checks
against the chain itself: **the same artefact that proves what happened decides who may act next.**
There is nothing to keep in step, and tampering to clear a conflict breaks the chain. The
incompatible pairs are held as data, with the reason on each, because *who could have approved this
version?* is a question an examiner will ask and the answer should be readable rather than
reconstructed from conditionals.

---

## 7. B7 — Derived is separated from stored

### The failure it prevents

A stored derivation is one that can go stale, and a stale derivation is worse than an absent one
because it is believed. The tier on a dashboard that was computed from facts which have since moved
is a number nobody can defend and everybody quotes.

### The rule, and its two halves

**Nothing computable is a column.** The estate summary, the worklist, the documentation dossier, a
document's staleness, a finding's ageing and overdue-ness, an overlay's persistence, an appetite's
utilisation: computed on read, from the register. `core/estate/`, `core/docs/dossier.py`,
`core/validation/ageing.py`, `core/reporting/indicators.py`.

**What *is* stored is stored with its derivation.** `risk_assessment` keeps the fact snapshot at
assessment time, the ruleset version, the materiality and complexity joins, the resulting tier, the
required control set and a rationale — so the tier can be re-derived and disagreed with, which is the
only kind of tier worth having. `document` keeps `evidence_head`, the point the chain had reached
when it was compiled, so **staleness is computed** rather than flagged: anything recorded about the
subject since means the document no longer describes it.

### The three things that are stored anyway, and why

| | Why it is not derived |
|---|---|
| `board_pack` | a committee minute referring to "the March pack" needs the March pack **as it was read**. A pack recomputed today is a different document with the same name — and movement since the last meeting needs a previous pack to move from |
| `risk_appetite` (versions) | limits accumulate and nothing is edited. A limit that can be changed without a record is a limit that can be **relaxed** without one, and the relaxation is the event a reader six months later needs to find |
| `alias_history` | the pointer moves; the history does not. It carries the refinement (`L-7`) and variance (`L-12`) checks that permitted each move, so *why was this allowed* survives the move |

### The board pack, and the number it refuses to produce

`core/reporting/` computes twelve indicators over the estate from the same services the model page
reads — because a board pack with its own numbers is a board pack that disagrees with the platform,
and the disagreement surfaces in a committee meeting where nobody can resolve it. There is no
caching: an indicator is cheap to compute and expensive to be wrong about.

**There is no composite score, and the pack says so in itself** rather than leaving an absence a
reader has to notice. Aggregating requires the parts to compose and they do not: two models fed by
the same curve are not two independent risks, so any single figure either double-counts the shared
dependency or ignores it, and a committee cannot decompose it to find out which. That is `L-14` — lax
monoidality — arriving as a product decision.

**Slack is reported.** An appetite whose utilisation stays below a quarter of its limit for two
consecutive packs is flagged. It is not a breach and not an error: a limit never approached is
indistinguishable from one that cannot fire, and it is the thing a committee reviewing its own
appetite should be told and never is.

---

## 8. Extension: what actually extends without a code change

The Extension Theorem of
[00 §8](00-mathematical-foundations.md#8-how-is-everything-indexed)
says that adding a model class should need no schema change and no core change. Here is how much of
that is true today, stated as three tiers rather than as an aspiration.

**Extends with data alone — no code, no DDL:**

| | |
|---|---|
| A new **model class** | it is a string on the register. Registering one is an insert |
| A new **policy gate rule** | drafted with its own cases, published once they pass. `facts_read` is computed from the rule's own AST, so a rule reading a fact the gate does not publish is refused *when it is written* rather than at the moment of a governance decision |
| A new **warrant profile** | a predicate over derived facts and a set of defaults. Several may match and they fold left-to-right by specificity, rightmost winning — the `L-19` monoid, which is what makes `(A∘B)∘C` and `A∘(B∘C)` the same profile |
| A new **risk-appetite limit** | over any of the twelve computed metrics. A metric the platform cannot compute is refused **when the limit is written**, because a limit that failed while a committee was reading it would fail at the worst possible moment |
| A new **monitor**, **validation test**, **overlay**, **featureset**, **document attachment** | all data |
| A new **rule set** for a T8 version | a parameter set, and nothing else. Written in the editor or posted as a document, checked against the version's schemas, landing `proposed` for a second person. Adding a rule changes no code, no DDL and no vocabulary — but adding an **operator** does, and would end the reachability analysis, which is why the eleven are closed |

**Extends with a module, no schema change:**

| | |
|---|---|
| A new **supervisory regime** | an institution: a signature (the vocabulary it reasons in), sentences (obligations in that vocabulary) and a comorphism into the core signature. `core/regimes/`. Adding MAS, APRA or OSFI E-23 is adding one module — and the **satisfaction condition** is *checked* against probe states before activation, so a regime whose encoding fails it cannot be turned on |
| A new **runtime** | a class with a `key`, an `available()` and an `invoke()`, registered on a `RuntimeRegistry`. A new model technology is a new *value* in one vocabulary, not a new section and not a new document type |
| A new **semiring** | a `Semiring` instance and a valuation |

**Does not extend — named, with the reason:**

| | |
|---|---|
| ~~**No `entry_points` discovery**~~ **Built** — `core/plugins/discovery.py` reads `entry_points(group="maya.extensions")` and **imports nothing**: a package is *seen* from its metadata and *enabled* only when configuration names it, because a control that switched itself on when somebody bumped a dependency is a control nobody turned on. What follows was the state before that, and the fibration part is unchanged | the fibration itself exists — nine fibres over the trainability classes, with a start-up gate that refuses to serve on a partial one (`L-15`) — so what is missing is third-party packaging, not the structure or the gate |
| **No fibre-specific evidence schema** | a class carries no JSON Schema, so class-specific evidence is not validated against anything |
| ~~**No connectors**~~ **Built, reading an export rather than an API** | `core/discovery/connectors.py` parses MLflow, Unity Catalog, git, SageMaker, Vertex, SAS metadata and a CMDB extract. It holds **no credential** and calls no API: a governance register with read access to every ML platform in the bank holds the broadest standing access anybody has, granted to the system whose whole argument is that it holds none. And what it produces is **candidates for triage, never registrations** — five governance facts are in no ML platform anywhere |

---

## 9. Target versus build

Read this as **the production target and what actually ships**, side by side, so that nobody
discovers the difference by looking for a service that is not there.

| Layer | Target | What ships |
|---|---|---|
| API | FastAPI, Pydantic, Uvicorn behind Gunicorn | as stated, one process |
| Front end | Bootstrap 5.3, jQuery 3.7, server-rendered Jinja2 | as stated, **vendored** — no CDN, no external call. See [08](08-ui-ux.md). The rule-set editor (`web/static/js/ruleset-editor.js`, ~300 lines) is the only page holding a document in the browser; it introduces no framework, no build step and no new asset host. It **decides nothing** — every question about whether a rule set is valid is answered by `POST /rulesets/check` and the screen renders the answer, so the publish button is enabled by the server's verdict and never by anything computed in the browser. That is the SDK's rule (§9, *Clients*) applied to a page: a client that re-implemented a governance check would be a second implementation, and it disagrees with the first eventually, in the direction of permitting more. The operator list is rendered into the page from `core/rules/common.py` rather than written into the script, because a screen holding its own vocabulary is a second vocabulary |
| Database | PostgreSQL 16 | PostgreSQL **or** SQLite, by URL alone. **No ORM, no migration tool.** SQLAlchemy Core metadata typed once and compiled to each dialect; fifty-one tables. `ltree`, `pgvector`, RLS and partitioning are **not used**; the shipped DDL has no foreign keys, no `CHECK` and no triggers, and referential integrity lives in the repositories ([05](05-data-model.md)). On SQLite the engine sets `journal_mode=WAL` and a 30-second `busy_timeout` on every connection: the default journal makes a writer block every reader, and the driver's own five-second give-up turns a moment of contention into a governance act that did not happen |
| Lakehouse | Delta Lake on Spark/Databricks | Delta via `delta-rs`, in-process, or **Apache Iceberg** via `pyiceberg` by configuration — `db/table_backend.py` decides once, CI runs the whole suite both ways. **No Spark**; the PIT join is Python over the table files. `deltalake` is OPTIONAL: it is a compiled Rust extension and some estates forbid binary wheels, so `maya_deltalake/` implements the six calls MAYA makes in pure Python and writes the real transaction log — tables stay readable by Spark, Databricks and `deltalake` itself. `db/delta_backend.py` chooses, preferring the reference implementation where it installs; CI runs the whole suite both ways and the counts must match |
| Object store | S3/ADLS/GCS with Object Lock for WORM | a content-addressed store on the local filesystem, digest as key, re-hashed on every read |
| Cache / queue | Redis 7 | **not used.** Warrant TTL and jitter are computed in process |
| Async | Celery, APScheduler | `core/scheduler/`: **26 idempotent jobs** invoked by an ordinary authenticated call, so cron, a Kubernetes CronJob or a person produce identical results. An in-process loop exists and is off by default |
| Eventing | Kafka with CloudEvents | **not used** |
| Policy | OPA/Rego | `core/policy/`: a rule is a predicate over a **closed vocabulary** of published facts — comparison, membership, boolean connectives, `any`/`all` and six other functions; no loops, no assignment, no attribute access — checked at the AST. Rego is a general language, and a gate written in one is a program a reviewer has to *run* rather than reason about |
| Auth | OIDC + SAML + SCIM + MFA | OIDC authorisation code with PKCE, state and nonce; HTTP Basic and a session cookie for people; CSRF on cookie authority. **No SAML, no SCIM, no MFA, no Authlib.** RS256 verification is in the standard library (`core/authz/jws.py`) for the air-gap reason: it *constructs* the padded block the signature should have produced and compares the whole of it, and decides the algorithm itself rather than reading `alg` from the token |
| Warrant signing | Ed25519 | HMAC-SHA256 with the key **derived per audience** — a compromised engine forges warrants for itself and nobody else. Ed25519 is not the target any more: asymmetry would buy non-repudiation to a *third party*, which is a requirement nobody has raised, and the containment it was wanted for is what the derivation provides |
| Artifact signing | Sigstore/cosign, in-toto | **not used** |
| Sandboxing | gVisor / Kata on Kubernetes | a `spawn`ed child with `RLIMIT_CPU` and `RLIMIT_AS` from the warrant — §5, and honestly scoped |
| Search | Postgres FTS + `pgvector` | **not used.** No semantic matching, no duplicate-feature detection |
| Observability | OpenTelemetry, Prometheus, Grafana | structured JSON logging with request id and principal on every line (`core/log.py`). The rest does not ship |
| Testing | pytest, Hypothesis, schemathesis, testcontainers | pytest and Hypothesis, plus a Docker build and a real PostgreSQL behind opt-in environment variables — both **skip loudly** rather than passing quietly, because a green suite that silently did not run the isolation test is the assurance finding H-5 objected to. The executable laws live beside the code they constrain, plus the discipline walkers of §4.2 and §4.4 — tests that walk the source and hold a rule a review would not catch |
| Packaging | uv/Poetry, Docker, Helm, Terraform | `requirements.txt`, a two-stage **`Dockerfile`** running as uid 10001 with a read-only root, **`deploy/compose.yaml`** with the owner and application database roles already separated, and **`deploy/helm`**, which *refuses to render* rather than templating a placeholder for a secret or accepting `ReadWriteOnce` with several replicas. No Terraform, and no Poetry |
| Clients | Python and JVM SDKs, CLI, notebook and CI plugins | `sdk/python/maya_sdk` — **standard library only**, no dependencies at all, because an SDK with a dependency tree moves the air-gap problem into the client's build pipeline rather than solving it. `sdk/java/` honours the same rule — `java.net.http` and a two-hundred-line `Json.java`, release 17, JUnit on the test classpath only. Its README was written as the **contract a JVM client must honour** before there was an implementation and is kept in that order, because what a MAYA client must do outlives any one client. **No CLI, no notebook plugin and no CI plugin** |

### 9.1 What deployment actually looks like

One process, one database file or connection string, one Delta directory, one artifact directory. The
multi-region topology in earlier drafts of this document — a separately scaled warrant service, a
Postgres standby, a Redis replica, a Kubernetes sandbox pool — described the target and none of it is
built. The one architectural claim that survives it is `P9`: a warrant descriptor remains valid for
its TTL whether or not MAYA is reachable, because the descriptor is signed and self-contained, and
that property costs nothing and needs no second region.

---

## 10. Failure modes

| Failure | Impact | What actually happens |
|---|---|---|
| Register unavailable | no governance decisions; **existing warrants keep working** until their TTL | `P9` by construction — the descriptor is signed and self-contained |
| Malicious artifact | code execution | the store refuses a declared digest that does not match what arrived, records which of the eight formats **execute code on load**, and the sandbox bounds the child. There is **no quarantine step** — an uploaded artifact is stored and readable at once — and §5 is honest that the sandbox stops accidents and not attacks |
| Alias move breaks a consumer | production incident | refused before it happens: contract refinement (`L-7`) and schema variance (`L-12`) are checked at the move, and the checks are stored on `alias_history` |
| An `input_to` edge that never composed | a blast radius over edges nobody validated | refused at the edge (`L-21`). Where either end has no version yet, the edge is recorded **without** a type check *and the log says so* |
| Feature source restated | silent degradation | `ViewManager.restated` reports that a namespace has moved past its pin, so anybody comparing two runs knows which case they are in. Tracing a restatement forward to the *decisions* that used the superseded values (`FR-FEA-016`) is not built |
| Evidence chain broken | loss of assurance | the incremental verifier fails readiness and **does not advance the checkpoint**; the scheduled full walk names the sequence number |
| Policy misconfiguration | operational gridlock | a gate ships with its own cases, at least one a refusal, and cannot be published until they pass. A published row is never edited; a change mints the next version |
| A scheduler job stops running | conditions never become consequences | `scheduled_run` records every run; one failing job does not stop the others, and a job that has stopped running is itself a finding |
| Redelivered telemetry | a population that never existed | `telemetry_batch.digest` is `UNIQUE`; a redelivered batch is accepted and not written again |
| Clock skew | bad temporal reasoning | all temporal logic uses server-assigned time, never client time |

---

## 11. Architecture decision records

[`docs/adr/INDEX.md`](adr/INDEX.md) holds the set. Summary:

| ADR | Decision |
|---|---|
| [ADR-001](adr/ADR-001-modular-monolith.md) | Modular monolith |
| [ADR-002](adr/ADR-002-postgres-delta-split.md) | Relational register for governance, Delta for data-plane volume — B2 |
| [ADR-003](adr/ADR-003-para-stoch-model-definition.md) | `Para(Stoch)` as the universal model definition |
| [ADR-004](adr/ADR-004-fibration-extensibility.md) | Model classes as fibres, delivered as plugins — §8 records how much is realised |
| [ADR-005](adr/ADR-005-institutions-for-regimes.md) | Institutions for multi-regulator scoping |
| [ADR-006](adr/ADR-006-semiring-evidence.md) | Semiring-annotated provenance as the single evidence engine — B6 |
| [ADR-007](adr/ADR-007-warrant-protocol.md) | Signed, TTL'd, alias-aware warrant descriptors — B1 |
| [ADR-008](adr/ADR-008-server-rendered-ui.md) | ~~Server-rendered Jinja2~~ — superseded by ADR-011 |
| [ADR-009](adr/ADR-009-no-untrusted-deserialisation.md) | Sandbox-only artifact loading; format policy — B5 |
| [ADR-010](adr/ADR-010-laws-as-tests.md) | The laws enforced by tests in CI |
| [ADR-011](adr/ADR-011-decoupled-frontend.md) | Decoupled front end consuming backend services over the public API — B4 |

> **Post-review.** This architecture carries the dispositions of
> [11 — Adversarial Design Review](11-adversarial-review.md): 27 findings, 17 requiring redesign. The
> two most consequential were **C-2** — the online feature store was unversioned, silently defeating
> the feature contract, and the same failure has since been found at four further levels
> ([07 §5](07-feature-platform.md)) — and **C-5**, day-one adoption with 1,200 evidence-less legacy
> models, answered by `core/baseline/`: a baselined model is governed going forward and carries
> explicit, dated, tiered **debt** for each piece of evidence it does not have. Debt is not breach,
> and a Tier 1 model with baseline debt must never render the same colour as one with a missed
> validation.

The authoritative record of what exists is
[12 §0, Build status](12-implementation-plan.md#0-build-status), kept current there rather than here.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
