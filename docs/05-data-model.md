# 05 — Data Model

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [04 — Architecture](04-architecture.md), boundaries **B2**, **B3** and **B7**.
Implements the structures of [00 — Mathematical Foundations](00-mathematical-foundations.md).

---

## 0. The argument this document makes

**Everything in this database is here because it could not be derived.**

That is the whole design rule, and it is why the schema is forty-seven tables rather than two hundred.
A tier is stored *with its derivation* because the facts it was computed from have since moved. A
board pack is stored because a committee minute referring to "the March pack" needs the March pack.
Nothing else that can be computed is a column, because a stored derivation is one that can go stale
and be believed.

The second rule follows from the first: **a schema small enough to read is a schema you can change
by reading it.** That is the reason there are no migrations, and it is why this document describes
the schema that exists rather than a target.

> **`db/schema/sqlite.sql` and `db/schema/postgres.sql` are authoritative.** They are hand-written,
> they are the only definition, and they are applied idempotently with `CREATE TABLE IF NOT EXISTS`,
> so starting against an existing database is a no-op. Where this document and those files disagree,
> the files are right and this document is a defect.

Six things a reader coming from an ordinary enterprise schema will look for and not find are in §1,
each with the reason. §2 is the two dialects and the test that keeps them equal. §3 is what may be a
column and what must be a pointer. §4 is the forty-seven tables, grouped by the question each group
answers. §7 is what the *design* targets and the build does not have, named rather than omitted.

---

## 1. Six absences, and what each one buys

| Absent | Why | What holds the line instead |
|---|---|---|
| **Foreign keys** | Referential integrity in two places is integrity that can disagree, and the version that gets believed is the one that produces the friendlier error. It also made the schema uncreatable as written: three reference cycles (finding **H-4**) needed `DEFERRABLE` constraints applied in a post-creation step, which is a migration tool wearing a schema's clothes | the repositories, which are the only interface to a table |
| **`CHECK` constraints** | An enumeration is a domain fact, and a domain fact enforced by the database is one the domain layer cannot explain. A `CHECK` violation is an opaque `23514`; a refusal from `core/` names the value, the closed set and what to do | closed vocabularies in `core/`, and refusals that carry a remediation |
| **Triggers** | Finding **C-3**: the obvious immutability rule, `DO INSTEAD NOTHING`, reports success while dropping the write — the worst available failure mode for an integrity control. A trigger that `RAISE`s is correct and is still enforcement a reviewer cannot see from the code | immutability as a refusal in `core/registry/`, and `L-2` asserting that a version's digest never moves |
| **`BOOLEAN` columns** | This one is not a preference. Fourteen columns were declared `BOOLEAN` on the Postgres side while `db/repositories.py` coerced every boolean to `int` on the way in, and **PostgreSQL does not implicitly cast integer to boolean** — so every insert touching one of those tables failed and the whole dialect was unusable. Nothing raised, because nothing had ever run against Postgres | integer `0`/`1` in both dialects and in Delta, converted to a real `bool` at the repository boundary for thirteen named columns, and `tests/test_schema_discipline.py` refuses the word `BOOLEAN` anywhere |
| **Migrations** | Expand/contract with a tested down-path is the right answer for a schema nobody can hold in their head. This one fits in two files | two hand-written files, and a diff |
| **Views, partitions, an ORM, a separate audit database** | A view is a derivation that can go stale (**B7**). A partition is an operational answer to a volume problem the control plane does not have (**B2** moves the volume to Delta). An ORM puts a second model of the data beside the schema. A separate audit database is a second account of who did what (**B6**) | the evidence chain *is* the audit log |

Nothing here is free, and the cost is worth stating plainly: integrity now depends on one layer being
correct rather than two, so a repository bug is a data bug with nothing beneath it to catch the fall.
That trade is accepted because the alternative was two layers that disagreed, and it is why
`tests/test_schema_discipline.py` exists at all.

---

## 2. Two dialects, one meaning

SQLite is the default and PostgreSQL is selected by URL alone. A row written by one must read
correctly under the other, and that is a strong claim that was resting on whoever edited one file
remembering to edit the other. It had already failed once.

**One substitution, and it is the only one:** `REAL` in SQLite is `DOUBLE PRECISION` in Postgres
(seventy-one columns). Everything else is identical — same table names, same column names, same
order, same indexes.

| Kind of value | Type | Why |
|---|---|---|
| identifiers, enumerations, and **JSON documents** | `TEXT` | JSON stays `TEXT` in both dialects deliberately. The application serialises and parses it, so **one parser reads both dialects** and no query depends on a dialect-specific operator. `jsonb` would buy indexing this schema does not need and cost portability it does |
| counts, sequence numbers, truth values | `INTEGER` | truth values are `0`/`1` — see §1 |
| timestamps and scores | `REAL` / `DOUBLE PRECISION` | epoch seconds, because SQLite has no native date type and the two dialects disagree about time zones. A single number cannot be ambiguous about which zone it is in |

`tests/test_schema_discipline.py` holds three assertions over the two files: no `BOOLEAN` anywhere,
the same `(table, column)` set in both, and an equivalent type for every shared column. It parses the
DDL rather than the database, and it strips a trailing comment *before* the comma — because a
commented column keeps its comma and reads as a different type from its twin, which is exactly the
kind of near-miss a hand-written pair of files produces.

### 2.1 Identifiers, timestamps, digests

| Convention | Form | Why |
|---|---|---|
| **Id** | `new_id()` — twelve hex characters of millisecond time, then sixteen of randomness | sortable by creation, not guessable, and generatable without a round trip. Not a sequence, because a sequence leaks how many of something there are |
| **Timestamp** | `REAL` epoch seconds, column named `*_at` | §2 |
| **Digest** | `"sha256:" + hexdigest` over canonical JSON — sorted keys, no whitespace | `db.database.digest`. Canonical, so two records with the same content have the same digest whatever order they were built in. This is what makes `manifest_digest`, `featureset_version.digest` and `telemetry_batch.digest` comparable at all |
| **Naming** | singular table names, `snake_case`, `_id` for a reference, `*_at` for a time | — |

---

## 3. What may be a column, and what must be a pointer

The control-plane / data-plane boundary (**B2**) is a rule about columns, so it belongs here.

> **The register holds definitions and pinned pointers. It never holds values.**

`tests/test_schema_discipline.py` enforces both halves. The negative half refuses a column named
`rows`, `values`, `data`, `records`, `sample`, `observations`, `payload_rows`, `frame` or `dataset`.
The failure it guards against is somebody adding a `rows` column "just for a preview", at which point
the register grows without bound, backups stop fitting, and a governance database becomes a data lake
nobody chose.

The positive half asserts that the four tables owning bulk data say where it is:

| Table | Must name | Which answers |
|---|---|---|
| `feature_view` | `delta_table` | where this view's namespaces live |
| `feature_view_version` | `delta_version` | **which bytes** a read of this version gets |
| `dataset_snapshot` | `delta_table` (and it carries `delta_version`) | which bytes a replay reads at |
| `telemetry_batch` | `delta_table` | where the scores and outcomes went |

A pointer that does not say *which version* is not a pointer; it is a name, and §5 of
[07](07-feature-platform.md) is five separate occasions on which that distinction mattered.

The one deliberate exception is `parameter_set`, which may hold values **inline** in
`values_inline` — a record of up to 4,096 values — with `values_uri` for anything larger. Forty
regression coefficients are a governance object a person reads, not a dataset, and making somebody
follow a pointer to see them would put the thing being approved one click away from the approval.
Past the cap it is a file, and a file has an artifact store.

---

## 4. The forty-seven tables

Grouped by the question each group answers. Every table is `id TEXT PRIMARY KEY`, no foreign keys,
JSON in `TEXT`, `REAL` epoch times. There are thirty-eight indexes and twenty-one `UNIQUE`
constraints, and the `UNIQUE`s are where most of the design lives — a uniqueness constraint is the
one integrity rule that survives having no foreign keys.

**One repository per table, and exactly forty-six of them.** `db/repositories.py` declares which
columns are JSON and which are truth values; nothing above `db/` knows either.

### 4.1 What models are there? — 5 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `model` | `urn UNIQUE`, `name`, `model_class`, `domain`, `owner`, `legal_entity`, `purpose`, `origin`, `status`, `tier`, `attributes`, `created_by` | `urn` is the identity every consumer holds; nothing else about a model is stable enough to be one. `tier` is a **cached pointer** at the current assessment, and §4.9 holds the derivation |
| `model_version` | `model_id`, `semver`, `manifest`, `manifest_digest`, `trainability_class`, `parameter_kind`, `fit_procedure`, `deterministic`, `input_schema`, `output_schema`, `contract`, `artifact_digest`, `artifact_uri`, `artifact_size`, `status`, **`UNIQUE (model_id, semver)`** | The **manifest is the source of truth** and the columns beside it are projections. `manifest_digest` is over the manifest and not over the row, so a status change cannot move it — that is `L-2`, and a digest over the row would have broken it silently. The three artifact columns answer three different questions and all three are needed: `artifact_digest` says *what* should be there, `artifact_uri` says *where to look*, and `artifact_size` lets a warrant tell an engine what it is about to fetch **before** it starts fetching it |
| `alias` | `model_id`, `environment`, `name`, `version_id`, `moved_at`, `moved_by`, **`UNIQUE (model_id, environment, name)`** | The one mutable pointer in the register. `#champion` in `prod` resolves here |
| `alias_history` | `from_version_id`, `to_version_id`, `refinement`, `variance`, `moved_at`, `moved_by`, `justification` | Append-only: the pointer moves and the history does not. `refinement` and `variance` are the stored evidence of the `L-7` and `L-12` checks that permitted the move, so *why was this allowed* survives the move |
| `model_edge` | `from_model`, `to_model`, `kind`, `note`, **`UNIQUE (from_model, to_model, kind)`** | Five kinds, and `input_to` is the only one that **composes** — see §4.1a. Edges are between **models**, not versions: a version-level graph would be rebuilt on every release and would answer a question nobody asks, since the estate question is which models depend on this one and not which builds did |

#### 4.1a `input_to`, and the name it used to have

`KINDS` is `derives_from`, `input_to`, `challenger_of`, `benchmark_for`, `calibrated_by`. Two of
them answer genuinely different questions and conflating them makes a challenger look like a
dependency: *what did we base this on* is `derives_from` and is lineage; *what breaks if this
changes* is `input_to` and is blast radius, and only `input_to` propagates.

The relation was called **`feeds`**, and that was a bad name in a bank, where a *feed* means market
data or a nightly file — so `A feeds B` read as though MAYA consumed or produced one. **It does
neither**: MAYA moves no data and runs no model, and the edge is a statement about two entries in the
register whose wire is carried by whatever engine runs the two ends. `feeds` is still accepted on the
way in and stored as `input_to`, and is deliberately **not** published in `KINDS` — a vocabulary
offering two words for one relation invites somebody to think they mean different things.

An `input_to` edge is now **type-checked** (`L-21`): it holds only if what the source produces can
stand in for what the target reads, through the one order in `core/domain/lattice.py`. Where either
end has no version yet the edge is recorded without the check *and the log says so*, because refusing
an edge for a schema nobody has decided would make the register harder to build than the estate is to
describe.

### 4.2 What is `X`? — 8 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `feature` | `name UNIQUE`, `entity`, `dtype`, `description`, `business_definition`, `owner`, `sensitivity`, `pii`, `protected_basis`, `proxy_risk`, `certification`, `created_by`, and **eleven composition and lifecycle columns**: `shape`, `components`, `composes`, `operations`, `defaults`, `definition_version`, `sealed_at`, `sealed_by`, `seal_note`, `ephemeral`, `expires_at` | Eleven columns rather than a join table, because every one of them is a property of the definition and a definition has exactly one row. `composes` holds each parent **with the `definition_version` it was composed against** — and §4.2a is exact about what that stamp does, because the obvious reading is wrong |
| `feature_view` | `name UNIQUE`, `entity`, `owner`, `delta_table` | `delta_table` is `features/{entity}/{name}` — the root, not a namespace |
| `feature_view_version` | `feature_view_id`, `version`, `features`, `delta_version`, `valid_time_column`, `ingest_time_column`, `row_count`, `quality_report`, **`UNIQUE (feature_view_id, version)`** | A version **is** a namespace, `features/{entity}/{name}/v{n}`. Writing v8 cannot touch what v7 serves — finding **C-2** |
| `feature_contract` | `model_version_id UNIQUE`, `digest`, `items` | `items` pins each `(view, version, namespace)`. Serving with a non-matching contract fails closed. `UNIQUE` on the version because a version has one input contract or none |
| `derived_feature` | `feature_id`, `name`, `expression`, `inputs`, `evaluator`, `on_error`, `definition_version`, `digest`, **`UNIQUE (name, definition_version)`** | The definition is **versioned**, so amending a derivation does not rewrite what earlier featuresets resolved against — somebody may already have trained on the old one. Corrections are new definition versions, never edits |
| `featureset` | `name UNIQUE`, `entity`, `owner`, `slots`, `label_slot`, `outcome_window_days`, `grain`, and nine of `feature`'s eleven: `defaults`, `composes`, `operations`, `definition_version`, `sealed_at`, `sealed_by`, `seal_note`, `ephemeral`, `expires_at`. Not `shape` or `components` — a set has no shape of its own; its slots do | `slots` is the **schema**, `slot → {dtype, nullable}`, and it is separate from any version's bindings. That separation is what lets two versions hold entirely different features and remain the same `X`, because a kernel is defined over the slots |
| `featureset_version` | `featureset_id`, `version`, `bindings`, `label_binding`, `digest`, **`UNIQUE (featureset_id, version)`** | `bindings` is `slot → {feature, view, view_version, namespace, delta_version, …}`. **The `delta_version` inside each binding** is what makes *same featureset version → same bytes* true rather than true-until-Tuesday |
| `dataset_snapshot` | `name`, `kind`, `delta_table`, `delta_version`, `row_count`, `as_of`, `pit_verified`, `pit_report`, `featureset`, `featureset_version`, `digest` | `delta_version` is the pin a replay reads at. Without it, replay would follow a restatement and then report a mismatch about the *data* as though it were about the test. `featureset` and `featureset_version` are recorded rather than recomputed, because *which schema did these columns come from* has to survive reading the row back. `digest` hashes the **rows**, canonicalised and order-independent: it was computed from the name, the `as_of` and the row count, so every 60-row set of one name at one instant shared a digest — and this is the value a fit warrant pins to say *this model was trained on this data* |

#### 4.2a What `composes` stamps, and what it does not

Resolution reads a parent **as it currently stands**. The stamped `definition_version` is compared
against the parent's current one and any difference is *reported* as drift on the resolved view. It
does not freeze the parent and it does not refuse the read. A child whose parent has moved is a thing
to be told about rather than a read that should fail — but **"pinned" would be the wrong word for
it**, and the schema is the place that has to be honest about which.

`featureset` carries `composes` and **does not carry the stamp**, so a composed featureset has no
drift to report. That is a gap in the build rather than a decision.

### 4.3 What is `P`? — 1 table

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `parameter_set` | `model_id`, `model_version_id`, `name`, `version`, `kind`, `provenance`, `values_inline`, `values_uri`, `cardinality`, `diagnostics`, `featureset_version_id`, `window_from`, `window_to`, `as_of`, `snapshot_id`, `warrant_id`, `digest`, `state`, `created_by`, `approved_by`, `approved_at`, `superseded_by`, **`UNIQUE (model_version_id, name, version)`** | **A fit produces a row here and not a `model_version`**, because fitting picks a point in `P` and does not change the kernel. That single decision is what lets a daily recalibration procedure be approved once instead of pretending a committee meets every morning. `warrant_id` is why a set has provenance at all — a fitted set with no warrant has no answer to *which data produced these numbers*, and the training record names that as a gap rather than leaving a blank. `approved_by` is separate from `created_by`, and the register refuses their equality |

### 4.4 Who may run it, and who is asking? — 3 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `warrant` | `model_id`, `environment`, `binding_kind`, `alias_name`, `version_id`, `flavour`, `principal`, `declared_use`, `ttl_seconds`, `grace_seconds`, `revoked`, `revoke_reason`, `epoch` | `binding_kind` is `pinned_version` or `alias`, and the two are different governance objects: a pin reproduces a decision made months ago, an alias follows the policy in force now. `epoch` is what makes revocation cheap to check |
| `warrant_profile` | `name`, `version`, `when_facts`, `defaults`, `specificity`, `retired`, `digest`, **`UNIQUE (name, version)`** | A profile templates the **request** and never the warrant. `when_facts` is a predicate over facts the platform **derives** — the trainability class, the parameter kind, the runtime — never a category somebody attached, because a declared taxonomy sitting beside a derived one is two answers to one question and they will disagree. `defaults` may only fill keys a caller could have typed; anything deciding who may act, for what, or until when is refused at creation. `specificity` orders the fold when several match, and the fold is the `L-19` monoid |
| `principal` | `username UNIQUE`, `display_name`, `kind`, `roles`, `legal_entities`, `domains`, `status`, `password_hash`, `password_salt`, `sso_issuer`, `sso_subject` | Scope is two dimensions — legal entity and domain — and an **empty list means unrestricted for that dimension**, because the alternative (enumerating every entity for every user) is the design that makes people grant `*` to get on with their day. `(sso_issuer, sso_subject)` is the durable identity a directory login binds to: a username is not one, and a directory user submitting `preferred_username: admin` was once signed in **as** the local admin because the username was what carried the roles. Service principals have no password and can sign in to nothing; they are addressed by warrants |

### 4.5 Is it any good? — 9 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `validation` | `model_id`, `model_version_id`, `kind`, `scope`, `plan`, `validators`, `independence`, `status`, `outcome`, `conditions`, `snapshot_id`, `due_at` | `snapshot_id` is what makes a replay possible: the episode names the pinned data it ran against, so a re-run recomputes nothing about the data |
| `test_result` | `validation_id`, `test_key`, `parameters`, `slice`, `value`, `threshold`, `passed`, `digest` | `slice` is a column and not a convention, because a metric with no slice is a portfolio average that hides exactly the segment fairness testing exists to find |
| `finding` | `model_id`, `model_version_id`, `validation_id`, `source`, `severity`, `category`, `title`, `blocking`, `owner`, `raised_at`, `due_at`, `status`, `closed_at`, `closure_verified_by`, `closure_evidence` | **`blocking` is the load-bearing column in the whole file.** An open blocking finding stops an alias move and refuses warrant resolution, so a model that failed challenge cannot reach production by a route that does not pass through the register. That is the difference between a findings log and a control |
| `finding_action` | `finding_id`, `act`, `actor`, `from_owner`, `to_owner`, `reason`, `plan`, `committed_at`, `due_before`, `due_after`, `acted_at` | Append-only and deliberately **not** a status table. Ageing, overdue-ness, whether the current owner ever accepted it, how many times the date has moved and whether it should escalate are all **computed** from these rows. A status column and a log can disagree, and when they do it is the column that gets believed and the log that is right |
| `monitor` | `model_id`, `model_version_id`, `name`, `kind`, `test_key`, `threshold`, `slice`, `reference`, `cadence_days`, **`label_delay_days`**, `breach_severity`, `escalate_after`, `status` | `label_delay_days` is what makes performance monitoring honest. A 12-month PD model's outcome is not known for twelve months, so a cohort scored last week has no measurable discrimination — and an evaluation over an immature cohort is **refused** rather than reported as a number nobody should act on |
| `observation` | `monitor_id`, `value`, `passed`, `sample_size`, `window_start`, `window_end`, **`matured`**, `digest` | `matured` travels with the answer, so a downstream reader cannot mistake an immature window for a passing one |
| `breach` | `monitor_id`, `model_id`, `observation_id`, `severity`, `consecutive`, `finding_id`, `status` | `consecutive` against `monitor.escalate_after`: one bad day is a bad day |
| `overlay` | `model_id`, `model_version_id`, `reference`, `name`, `kind`, `direction`, `rationale`, `basis`, `owner`, `proposed_by`, `approved_by`, `status`, `effective_from`, **`expires_at`**, **`renewals`**, `finding_id`, `closure_reason` | Three columns carry it. `expires_at`, because an overlay with no end date is a model change nobody versioned. `renewals`, because an overlay renewed again and again is evidence the **model** is wrong rather than evidence the overlay is needed — and that signal is the reason this register exists. `approved_by` separate from `proposed_by`, because an adjustment one person can both propose and approve is not a control |
| `overlay_measurement` | `overlay_id`, `period`, `base_value`, `adjusted_value`, `magnitude`, `pct_of_base`, `measured_by` | The quantified magnitude per period. Almost no bank can say how large its overlays are in aggregate; this is the column that answers it |

### 4.6 Who signed? — 5 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `version_approval` | `model_id`, `model_version_id`, **`tier`**, `required_roles`, `status`, `statement`, `opened_by`, `completed_at`, **`UNIQUE (model_version_id, opened_at)`** | `tier` is nullable and the service **refuses to open when it is null**: approving before assessing would be a way of choosing your own control depth. The depth follows the tier by the same `L-5` adjunction that decides every other control set |
| `version_approval_signature` | `version_approval_id`, `principal`, `role`, `decision`, `statement`, **`UNIQUE (version_approval_id, role)`** | One signature per role, in the schema. The *other* half — that one person may not sign twice under two hats — **cannot** be a `UNIQUE` and is checked in `core/lifecycle/approval.py`, because a quorum is a number of people rather than a number of roles |
| `attestation` | `model_id`, `amendment_id`, `kind`, `required_roles`, `status`, `statement`, `expires_at` | Attestation is a quorum, not a signature: the model becomes attested only when every required role has signed, and a single decline ends it. That is what makes it a committee act rather than a button |
| `attestation_signature` | `attestation_id`, `principal`, `role`, `decision`, `statement` | Note the absence: it has **no** `UNIQUE (attestation_id, role)`. `version_approval_signature` is the better shape, and this one is older |
| `amendment` | `model_id`, `reference`, `reason`, `scope`, `status`, `opened_by`, `closed_by` | An attested record is immutable — no field changes and no new versions — until an amendment returns it to a mutable state, and the amendment must itself be attested before the model is back in force |

### 4.7 What is the evidence? — 2 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `evidence_node` | **`seq INTEGER NOT NULL UNIQUE`**, `kind`, `subject_type`, `subject_id`, `payload`, `parents`, `contains_personal_data`, `content_hash`, `prev_hash`, `chain_hash`, `trust`, `recorded_at`, `recorded_by` | The append-only chain, and **there is no separate audit log** — two records of who did what are two records that can disagree. `parents` is a JSON set rather than an edge table, because a node's parents are written once with the node and never queried backwards. `seq` answers finding **C-4**: a Merkle DAG alone detects content mutation but **not** deletion of a leaf or insertion into history, because a DAG has no global ordering, so a linear chain is layered over it. `chain_hash` is `H(seq ‖ prev_hash ‖ content_hash ‖ parents)`. `contains_personal_data` answers **H-3** by making the conflict not arise: such a node carries an **empty payload and a pointer**, and the append path hashes what it actually stored, so the node verifies against itself (`L-18`). `trust` is the input the trust semiring propagates |
| `evidence_checkpoint` | `seq`, `chain_hash`, `verified_at`, `verified_by` | How far the chain has been verified and what its head was. Verifying the whole chain on every readiness probe was O(chain) — 2.9 seconds and 83 MB at forty thousand nodes, and a busy instance reaches a million in half an hour, at which point the orchestrator takes the node out of service for being slow to say whether it is healthy. Readiness now asks *has anything broken since*, which is O(new); the full walk runs on a schedule, because only the full walk can answer *is the whole chain intact*. **A broken chain does not advance the checkpoint**, because moving it past a break would bless it |

### 4.8 What has been written down? — 2 tables

The compiled document and the filed one are different things, and conflating them would make the
register unable to say which it was looking at. One MAYA generated from the register; one a person
wrote and somebody else accepted.

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `document` | `model_id`, `model_version_id`, **`subject_type`**, **`subject_id`**, `kind`, `title`, `sections`, `citations`, `coverage`, `digest`, `subjects`, **`evidence_head`**, `status`, `compiled_at`, `compiled_by` | `citations` records which evidence nodes each section rested on, so *this document is supported* becomes a claim that can be **evaluated in the Boolean semiring** rather than trusted. `evidence_head` is how far the chain had got at compile time, so **staleness is computed rather than stored** — anything recorded about the subject since means the document no longer describes it. `subjects` is the set staleness is measured against, because measuring it against the model alone meant a new version taken through a full quorum approval left the document reporting that nothing had happened |
| `attachment` | `model_id`, `model_version_id`, **`subject_type`**, **`subject_id`**, `kind`, `title`, `filename`, `media_type`, `digest`, `size_bytes`, `text_indexed`, `state`, `attached_by`, `reviewed_by`, `review_note`, `supersedes`, `superseded_by` | `digest` is the SHA-256 of the bytes **and the storage key**: the same board paper across forty models is one object with forty rows pointing at it, and editing in place is impossible because a changed byte is a changed digest, which is a supersession somebody has to declare. It is deliberately **not** `UNIQUE`. `text_indexed` records whether the platform can genuinely read it, so later machine review knows what has been read and what has only been stored. `reviewed_by` is never equal to `attached_by` |

#### 4.8a `subject_type` and `subject_id`, and the two documents that had nowhere to go

Both tables gained the pair, and the reason is the same on each. Documentation does not arrive all at
once about one thing; it arrives at **five moments about five objects**:

| When | About | Example |
|---|---|---|
| before anything runs | the **model** | the methodology paper, the literature the approach comes from |
| a version is created | the **version** | the specification of that kernel |
| a fit warrant executes | the **parameter set** | the convergence study, the note explaining one morning |
| a featureset is filled | the **featureset version** | the data dictionary, the source-system agreement |
| validation concludes | the **validation** | the independent recode, the reviewer's working |

Everything used to be filed against a model or a version, so the third and fourth were **unfilable** —
and they are the two that matter most. A calibrated model produces a parameter set every morning; a
featureset's documentation is read by every model fitted from it, so filing it against one of them
makes it invisible to the rest.

`SUBJECTS` is six values: `model`, `model_version`, `parameter_set`, `featureset_version`, `feature`,
`validation`. **A subject is always pinned** — `featureset_version`, never `featureset` — because a
document filed against the *set* would describe something that has since moved, which is finding
**C-2** in documentation's clothing. `featureset` is deliberately absent from the vocabulary rather
than discouraged in a comment.

`model_version_id` remains the normal filing target and `NULL` means model-level, **which has to be
asked for**: a development document describes the coefficients it printed, not their replacement, and
model-level filing is how a bank ends up with an MDD for v2.1 against a model serving v2.4.

### 4.9 What does the estate look like? — 5 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `risk_assessment` | `model_id`, `tier`, `materiality`, `complexity`, `facts`, `required_controls`, `rationale`, `ruleset_version`, `next_review_due`, `assessed_at` | The **derivation**, not just the answer: the exact fact snapshot at assessment time, the immutable ruleset version, the materiality and complexity joins, the resulting tier and the control set `req(tier)` gives by the `L-5` adjunction. That is what makes a tier something you can disagree with, which is the only kind worth having. `model.tier` is the cached pointer at the current one |
| `risk_appetite` | `metric`, `scope_key`, `scope`, `version`, `limit_value`, `amber_value`, `direction`, `unit`, `rationale`, `owner`, `review_at`, `retired`, `digest`, **`UNIQUE (metric, scope_key, version)`** | A limit is a **declared threshold over a metric the platform computes**, so utilisation is arithmetic and a breach is a fact rather than a judgement. Three refusals: a metric the platform cannot compute is refused **when the limit is written**, because a limit that failed while a committee was reading it would fail at the worst possible moment; a limit with no `rationale` is refused, because a number nobody can explain will be either ignored or obeyed without thought; and an `amber_value` on the far side of the limit is refused, because a warning that can only fire after the event is not a warning. **Versions accumulate and nothing is edited** — a limit that can be changed without a record is a limit that can be *relaxed* without one |
| `board_pack` | `period`, `scope`, `as_at`, `models`, `indicators`, `exceptions`, `unmeasured`, `digest`, `created_by` | **Persisted rather than recomputed**, which is the one deliberate exception to *nothing derived is stored*. Movement needs a previous pack to move from, and a committee minute referring to "the March pack" needs the March pack as it was read — a pack recomputed today is a different document with the same name. `unmeasured` is what the pack could not compute, said out loud, because a pack that silently omits what it could not reach reads as complete |
| `baseline_import` | `reference`, `source`, `models`, `debt_items`, `imported_by` | Finding **C-5**: on import day 1,200 existing models arrive with no evidence graph, no contracts and documentation in Word files. Every gate fails, every dashboard is red, and the programme dies in month seven — judged the single most likely cause of total failure |
| `compliance_debt` | `model_id`, `import_id`, `gap_key`, `description`, `materiality`, `tier`, `status`, `plan`, `owner`, `finding_id`, `raised_at`, **`expires_at`** | The answer to C-5 is not to lower the gates; it is to make the register **honest about what it does not know**. A baselined model is governed going forward and carries explicit, dated, tiered debt per missing piece of evidence. **Debt is not breach** — a Tier 1 model with baseline debt and a Tier 1 model with a missed validation must never render the same colour — and debt becomes a breach only when it passes `expires_at` |

### 4.10 What did the platform itself do? — 6 tables

| Table | Key columns | The constraint that carries the design |
|---|---|---|
| `policy_rule` | `gate`, `version`, `rule`, `reason`, `cases`, `facts_read`, `test_report`, `state`, `digest`, `published_by`, **`UNIQUE (gate, version)`** | `cases` ship **with** the rule and it cannot be published until they pass, at least one of them a refusal — a gate that can be changed without a release is a gate that can be weakened without one, and the cases are what stops that being silent. `facts_read` is computed from the rule's own AST, so a rule reading a fact the gate does not publish is refused **when it is written** rather than at the moment of a governance decision. A published row is never edited; a change mints the next `version` |
| `scheduled_run` | `job`, `outcome`, `ok`, `error`, `duration_ms`, `ran_by`, `ran_at` | A record of activity, not a queue and not a task list: every job is idempotent and derives its own work from the register, so deleting every row here would change nothing about what the next run does. One failing job does not stop the others, and **a job that has stopped running is itself a finding** |
| `notification` | `principal`, `channel`, `state`, **`digest`**, `item_count`, `overdue`, `summary`, `detail`, `sent_at` | `digest` is over the **work described**, not over the message. An unchanged worklist is suppressed until a quiet period passes, because nothing is more certain to be ignored than a daily message identical to yesterday's. A failed delivery is kept, because silence about a failed send is how somebody concludes they were never told |
| `telemetry_batch` | **`digest UNIQUE`**, `delta_table`, `row_count`, `at` | **The `UNIQUE` is the idempotency control.** Real collectors deliver at least once; a monitor that double-counts a redelivered batch reports a population that never existed. The digest is over the stream, the version and the rows themselves. Only the receipt is relational — the rows are two Delta streams per version, `scores` and `outcomes` |
| `ai_capability` | `capability_key UNIQUE`, `tier`, `oracle_key`, `autonomy`, `base_model`, `prompt_digest`, `review_sample`, `owner` | `tier` is `A` (an oracle checks the output) or `B` (every claim cites evidence), and the closed set is those two. **Tier C — advisory, neither checkable nor groundable — is deliberately not registrable**, because a Tier C capability in a registry is a Tier C capability that will one day be wired into a decision. No AI principal is granted a lifecycle-transition scope either |
| `ai_generation` | `capability_id`, `subject_type`, `subject_id`, `prompt_digest`, `base_model`, `output`, `claims`, **`rejected_claims`**, `oracle_verdict`, `state`, `sampled`, `attested_by`, **`edit_distance`** | `rejected_claims` is the column that matters: a claim whose citations do not resolve is **removed** from the output before anyone sees it and kept here, because the alternative — flagging it in place — means the flag is what gets skimmed past. `edit_distance` records how much a reviewer changed on attestation, and a **fall** in it over time is the signal for automation bias: a reviewer who has approved forty correct drafts is not reviewing the forty-first. Nothing is evidence until a person attests it, and never the asker |

---

## 5. The data plane

Postgres holds definitions and decisions; Delta holds values and events. Four areas
(`db/database.py::DeltaPaths`), and nothing else is one:

```
data/delta/
├── features/<entity>/<view>/v<n>/     one namespace per feature view VERSION
│                                      entity_id, event_ts (valid time),
│                                      ingest_ts (transaction time), features…
├── snapshots/<snapshot_id>/           immutable, PIT-verified training sets
├── telemetry/                         two bitemporal streams per model version:
│                                        scores    — exist when the model runs
│                                        outcomes  — learned later
└── monitoring/                        metric time series
```

**Every feature row carries two clocks**, and a row missing either is refused at the write rather
than two layers later during assembly, where it stops being fixable. Delta rather than a plain table
for one reason that decides it: **its table versions are the transaction-time axis**, which is the
mechanism behind `L-10`. There are **no `BOOLEAN` columns here either** — the rule is absolute across
all three stores.

[07 — Feature Platform](07-feature-platform.md) is the whole treatment.

---

## 6. Immutability, and where it actually lives

| Claimed immutable | Enforced by | Not enforced by |
|---|---|---|
| `model_version` manifest | a refusal in `core/registry/versions.py`; `L-2` carries a version through assessment, approval and an alias move and asserts the digest at each step | no trigger, no `CHECK`. Finding **C-3**'s `RAISE` trigger remains a Postgres design and is not in the shipped DDL |
| `evidence_node` | the append path only ever inserts; `chain_hash` makes tampering detectable and the checkpoint makes it *findable* | no database-role grant. The target is `INSERT`/`SELECT` only for the application role |
| `alias_history`, `finding_action`, `overlay_measurement`, `scheduled_run` | nothing writes an `UPDATE` to them | the same |
| `policy_rule` published rows, `risk_appetite` versions | the service mints the next `version` rather than editing | the `UNIQUE` on `(gate, version)` / `(metric, scope_key, version)` makes an edit-by-reinsert impossible, which is the half a schema *can* carry |

Stating this precisely matters more than the mechanism. **Append-only enforced by convention is a
claim about discipline; append-only enforced by a grant is a claim about the database.** MAYA makes
the first claim today and the second is target.

---

## 7. What the design targets and the build does not have

Named here rather than omitted, because a gap discovered by writing a query against a table that does
not exist is the most expensive way to find one.

| | The design | What ships |
|---|---|---|
| **Row-level security** | `ENABLE` **and `FORCE`** per scoped table, driven by session variables set in middleware, with the application connecting as a non-owner. Finding **H-5** is that `ENABLE` alone does not apply to the table owner or a superuser, so RLS silently does nothing while appearing to be on | `core/authz/scope.py`, which filters listings **as well as** detail reads on two dimensions. Scoping in one layer rather than two |
| **A warrant projection** | Finding **H-2**: a separately deployed warrant service must not read the control plane's normalised tables, so it reads a flat, versioned `warrant_projection` maintained through an outbox | there is one process, so there is no coupling to break and no projection. If the service is ever extracted, the projection comes with it |
| **A separate audit database** | Finding **H-9**: `audit_log` is write-heavy and cannot be lost; evidence traversal is read-heavy and recursive; they compete on one primary | there is no `audit_log`. The evidence chain is the audit log (**B6**) |
| **Partitioning** | monthly on `evidence_node` and the audit log | none. The volume that would justify it is in Delta |
| **`jsonb`, `ltree`, `citext`, `text[]`, generated columns, expression indexes, advisory locks** | the Postgres feature set | none used. §2 says why JSON stays `TEXT`; the rest would make the two dialects behave differently, which is the one thing the pair of files exists to prevent |
| **Reference tables** | `model_class`, `legal_entity`, `business_unit`, `person`, `vendor`, `lifecycle_definition`, `probe_set` as first-class tables with their own integrity | strings and JSON on `model` and `principal`. The consequence is real and worth naming: an owner who leaves is not detected by the register, because there is no `person.left_at` for an orphaned-model sweep to read |
| **`model_use`, `warrant_grant`, `deployment`, `run`, `artifact`, `calibration_set`, `scope_determination`, `obligation`, `assumption`, `limitation`** | separate tables | folded into `warrant.declared_use`, `parameter_set`, `model_version.contract`, the artifact store's own filesystem index, and the regime engine's computed determinations. Each is a real reduction in what the register can be queried for, and the trade was made deliberately: a table nobody writes to is a table that lies |

---

## 8. Evolution, without migrations

| Change | Mechanism | DDL? |
|---|---|---|
| A new model class | a string on `model.model_class` | **no** |
| A new supervisory regime | an institution module; determinations are computed, not stored per model | **no** |
| A new policy gate rule | `INSERT` into `policy_rule` with its cases; the previous version is superseded, never edited | **no** |
| A new warrant profile, appetite limit, monitor, validation test, overlay, featureset, attachment kind | data | **no** |
| A new evidence semiring | a `Semiring` instance and a valuation | **no** |
| A new column | edit **both** files, in the same commit | yes |
| A new table | edit both files, add one repository, in the same commit | yes |

The last two are the whole migration strategy: **two files and a diff.** `CREATE TABLE IF NOT
EXISTS` makes application idempotent, so a new table appears on the next start and nothing else
moves. A new *column* on an existing table is the case this does not cover — `IF NOT EXISTS` does not
add columns to a table that already exists — and the honest statement is that adding one to a
populated database is a manual `ALTER` in both dialects, which is acceptable at forty-seven tables and
would not be at two hundred.

---

## 9. Traceability

| Section | Satisfies | Answers finding |
|---|---|---|
| §1 absences | `NFR-MNT-002` — the domain does not depend on the persistence technology | `C-3`, `H-4` |
| §2 dialects | `NFR-OPS-003` portability, in the form that actually ships: two dialects, one meaning | the fourteen `BOOLEAN` columns |
| §3 pointers | `NFR-DATA-002` content-addressed and hash-verified on read | — |
| §4.1a `input_to` | `L-21` | — |
| §4.2 featuresets | `FR-FEA-006`, `L-W10` | `C-2`, at the featureset level |
| §4.5 `blocking` | `FR-VAL-011`, `FR-LC-006` | — |
| §4.6 quorum | `L-5` | — |
| §4.7 evidence | `L-18` | `C-4`, `H-3` |
| §4.8a subjects | `FR-DOC-004` | `C-2`, in documentation's clothing |
| §4.9 debt | — | `C-5` |
| §6 immutability | `L-2` | `C-3` |
| §7 | `NFR-DATA-001` — in one store rather than two, so there is no outbox | `H-2`, `H-5`, `H-9`, all named as target |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
