# 07 — The Feature Platform

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [04 — Architecture](04-architecture.md). Implements the bitemporal theory of
[00 §7](00-mathematical-foundations.md#7-when-did-we-know-it)
and law `L-10`.

---

## 0. One failure, and this document is about preventing it

A model scored 0.47 Gini in development and 0.31 in production. Almost always it has not degraded.
It was **never trained on the data it is now being served**, and nobody can tell, because the
training set and the serving payload have the same column names.

There are exactly two ways that happens, and the whole feature platform is the two answers.

| The failure | What it looks like | The answer |
|---|---|---|
| **A fact reached a row before it was knowable** | the training set used a figure restated three months after the decision; the backtest measured a fact the model could not have had | **two clocks**, and a point-in-time read that is an operator with a saturation law (§2, §3) |
| **A stable name's contents moved** | the contract digest still matches, every monitor is green, and the bytes behind the name are not the bytes that were fitted | **pin the thing, never the name** — the same fix at five levels (§5) |

Both are silent. Neither produces an error, a null, or a shape mismatch. That is why they are worth
a platform rather than a checklist: a failure that announces itself does not need one.

**What this document covers.** Features, views, contracts, assembly, verification, bulk transfer and
telemetry — the machinery. The *algebra* over it moved to documents of its own and is not repeated
here: featuresets and the parameter object in [15](15-featuresets-and-parameters.md), the five wrong
assumptions about a feature and everything that happens between the store and the model in
[16](16-features-composed-and-shaped.md), and the lattice, the `AsOf` operator and typed composition
in [17](17-feature-and-model-algebra.md).

---

## 1. The objects, and what each one pins

Every object below exists because something one level up could not be pinned without it. Read the
last column as the answer to *what moves if this is missing.*

| Object | What it is | What it pins | Table |
|---|---|---|---|
| **Feature** | A named, typed, owned signal about an entity, with a business definition. Not a column — a *meaning* | its own definition, versioned: `definition_version` moves rather than the row being edited | `feature` |
| **Feature view** | A group of features about one entity, materialised to one Delta path | the path: `features/{entity}/{name}` | `feature_view` |
| **Feature view version** | One materialisation of that view | **a Delta table version.** `v7` is its own namespace — `features/{entity}/{name}/v7` — so writing `v8` cannot touch what `v7` serves | `feature_view_version` |
| **Derived feature** | `Z = f(X, Y)` in nine whitelisted functions, checked at the AST | its own `definition_version`, unique per `(name, definition_version)`, so amending a derivation does not rewrite what earlier sets resolved against | `derived_feature` |
| **Featureset** | A declared **schema** of named slots. What a kernel is defined over | nothing yet — this is the schema, and it is deliberately separate from anything filling it | `featureset` |
| **Featureset version** | The schema **filled**: each slot bound to a feature, a view, a view version *and the Delta version* | the bytes. Same featureset version → same bytes, permanently | `featureset_version` |
| **Feature contract** | The exact view versions a model version was fitted on and must be served | the **namespaces**, not the views. `serving_namespaces()` is what serving must read | `feature_contract` |
| **Dataset snapshot** | A materialised, PIT-verified training set | `delta_table` **and** `delta_version` — the pin a replay reads at | `dataset_snapshot` |
| **Parameter set** | An inhabitant of `P`, produced by a fit | the featureset version, the window, the `as_of`, and the warrant that authorised the fit | `parameter_set` |
| **Entity** | The key a feature is about: customer, account, facility, instrument, counterparty, desk, book | — | a column, not a table |

Two of these are worth restating because they are the ones people expect to be one thing.

**A featureset is not its contents.** The schema is `slot → {dtype, nullable}`; a version binds each
slot. So `inflation@v1` may fill `daily_index` from a national series and `@v2` from a harmonised
one, and a model reading `daily_index` **has not changed** — its input space is the slots. Changing
what fills a slot is a different event from changing the model, and it gets a different control. A
version that cannot fill the schema is refused rather than published: it is a different set, or it
is a model change, and the register decides which instead of leaving somebody to remember.

**A view version is a serving namespace, not a row filter.** This is the load-bearing sentence in
`core/features/views.py`, and §5 is why.

---

## 2. Two clocks, and what a leak looks like

Every feature row carries two timestamps, and conflating them is the dominant silent failure in
model development.

| Clock | Column | Means | Set by |
|---|---|---|---|
| **Valid time** | `event_ts` | when the fact was true in the world | the business event |
| **Transaction time** | `ingest_ts`, and the Delta table version | when MAYA learned it | the pipeline |

A row missing either is refused at the write, in `ViewManager._check_clocks`, with the reason
stated. Accepting it here to be helpful would move the problem two layers away, into assembly, where
it stops being fixable because the moment the fact became knowable is gone.

The concrete case, in four dates:

```
2026-03-31   the borrower's Q1 accounts are true                (event_ts)
2026-05-20   they are loaded into the warehouse                 (ingest_ts)
2026-06-15   the borrower defaults                              (label_ts)
2026-08-02   the borrower restates Q1                           (a second row, later ingest_ts)
```

A set built naively on 1 September reads the **restated** March figure into a row labelled in June.
The model learns from a number that did not exist when the credit decision was made, validates
beautifully, and fails in production — and the failure is then misdiagnosed as drift, because
drift is what a degrading model looks like and this one never worked.

---

## 3. The point-in-time read, as an operator

The condition was always checked. What matters is that the *read* is a named operator with stated
properties, because reproducibility lives in the read rather than in the check.

`core/features/assembly.py::TrainingSetBuilder.latest_admissible`:

```
AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                { r ∈ R : r.event_ts ≤ ℓ  ∧  r.ingest_ts ≤ min(ℓ, a) }
```

`ℓ` is the label time; `a` is the assembly's own `as_of`. Four properties, all asserted in
`tests/test_laws.py::TestL10TheAsOfOperator`:

| Property | What it means |
|---|---|
| **Idempotent** | reading the result again returns it |
| **Commutes with projection** | admissibility is decided on the clocks alone, so reading fewer columns cannot change which row is chosen |
| **Monotone in `a`** | a later `as_of` can only widen what is admissible; nothing knowable stops being knowable |
| **Saturating at `ℓ`** | **the reproducibility guarantee** |

The fourth is the one to understand, and it is the reason for the `min`. Because the ingest bound is
`min(ℓ, a)`, **every `a ≥ ℓ` gives the same answer**. A row assembled the day its label matured and
the same row re-assembled a year later are identical, however many restatements arrived in between.

The bound used to be `a` alone. `a` is one scalar for the whole assembly, so a fact true before the
label and *learned after it* was admitted: knowable at assembly time, not knowable at decision time.
Back-filled alignment makes that concrete — a value first observed in April, carried back onto a
March grid point, arrives carrying April's ingest stamp and would have entered a March training row.
Without the `min`, a re-run would quietly *improve* on the original, which is the least useful kind
of reproducibility, because the numbers then agree with nothing including themselves.

Both bounds are kept because they refuse different things. `ℓ` is what the model could have known
when the decision was made. `a` is what the platform could have known when the set was built, so a
restatement arriving after assembly cannot creep into a re-run.

> **One divergence, named.** A featureset publishes its rule to an execution engine as
> `plan()["pit_rule"]`, and that string is `event_ts <= label_ts AND ingest_ts <= as_of` — it omits
> the `min`. An engine that implements the published rule literally will therefore admit rows MAYA's
> own assembly refuses. The implementation is the stricter of the two and the string is the stale
> one; it is stated here rather than left for an engine author to discover from a disagreement in
> the numbers.

---

## 4. Verification: three layers, and what each actually proves

MAYA does not trust the query author. It also does not claim more than it can show. Finding **H-6**
of the [adversarial review](11-adversarial-review.md) rejected an earlier single-layer claim that
sampling *proved* absence of leakage. It does not, and a leak confined to a rare, high-value
segment — where it does the most damage — is exactly what sampling misses.

| Layer | What it does | What it proves | Where |
|---|---|---|---|
| **1 · Static** | requires **both** temporal bounds. An assembly lacking either is **rejected**, not sampled | a genuine proof, for the dominant leakage class. This is the strong check | `pit.py::static_check` |
| **2 · Sampled** | independently recomputes a stratified sample by a **different route** and compares | detection of *systematic* violation. Never absence | `pit.py::verify_sampled` |
| **3 · Adversarial** | CI injects a deliberately leaky feature the verifier must catch | that the verifier still works — the failure that would otherwise be silent and catastrophic | the test suite |

Two honest qualifications on layer 2.

**Stratification is by label value alone.** `_stratified` buckets on `label` and nothing else.
Label value is the stratum that matters most — a leak that only shows on defaults is the one worth
catching — but the stated power is power against *systematic* violation and against nothing finer.
`verify_sampled`'s own docstring claims strata spanning label period and entity as well; the code
does not do that, and this document follows the code.

**Recomputation is deliberately a different route.** `_recompute` reads through
`DeltaStore.as_of` rather than replaying the join `_join` performed. An independent recomputation is
what stops a bug hiding behind itself; running the same code twice proves only that it is
deterministic.

Alongside the two layers sits a cheap screen, `detect_leakage`, for a feature that is a perfect
predictor of the label — almost always the label leaking under another name. It uses **two** tests
chosen by the column, and the reason is a defect it used to have. Bucketing values by label and
flagging a column whose every bucket held one label is meaningless for a *continuous* feature, where
every value is distinct and therefore every bucket trivially holds one row: an ordinary forty-row
set with one float column and random labels came back flagged, so `pit_verified` was false for
essentially every real training set, and **a control that is always false is a control nobody
reads**. A repeating column is now screened for purity; a continuous one for perfect separation by a
single threshold. Neither is a proof. Both fire on the shape a leak actually has.

**Law `L-10`, stated at its true strength:** no assembly passes without a static temporal bound;
sampling detects systematic violation at stated power; and the read `AsOf(R, ℓ, a)` is idempotent,
commutes with projection, is monotone in `a`, and saturates at `ℓ`. The last clause is the one that
makes reproducibility a theorem rather than a habit.

---

## 5. The same failure five times: a stable name whose contents moved

Adversarial finding **C-2** was found in the *design* of the online feature store, before one was
built. A store keyed only by entity silently defeats the feature contract: when a view advances from
v7 to v8 with a changed transformation, a model pinned to v7 begins receiving v8 values with **the
contract digest still matching and every guard reporting green**. That is the exact training–serving skew this platform
exists to prevent, introduced by the platform itself.

The same shape has since been found four more times, at four different levels, which is the
strongest available evidence that C-2 is a **class** rather than an incident. Every fix is the same
fix: *the name is not the thing; pin the thing.*

| # | Level | The name that moved | The pin |
|---|---|---|---|
| 1 | **View** | a serving key of `(view, entity)`, resolving to "latest" | a view version **is** a namespace, `features/{entity}/{name}/v{n}`, and a contract pins the namespace. `ContractBinder.serving_namespaces` computes what serving must read |
| 2 | **Featureset** | a set naming views without their Delta versions — same digest, different bytes next month | each binding carries `delta_version`. `plan()` publishes `pins` as `(namespace, delta_version)` pairs |
| 3 | **Composition** | a child naming a parent without recording *which definition* of it | `composes` stamps each parent with the `definition_version` it resolved against |
| 4 | **Document** | a data dictionary filed against a *featureset* rather than a featureset version | `featureset_version` is a document subject and `featureset` deliberately is not — see [17 §8](17-feature-and-model-algebra.md) |
| 5 | **Generative build** | `base_model` naming a family whose weights the host replaces unannounced | `L-W13` refuses a generative warrant that names a family and no build |

Levels 1–4 are dispositioned in
[11 · C-2](11-adversarial-review.md#c-2--the-online-feature-store-is-not-versioned-silently-defeating-the-feature-contract).

### 5.1 What the pin does, and what it does not

Level 3 is the one where the obvious reading is wrong, and the schema is the place that has to be
honest about it. Resolution reads a parent **as it currently stands**. The stamped
`definition_version` is compared against the parent's current one and any difference is *reported*
as drift on the resolved view. It does not freeze the parent and it does not refuse the read. A
child whose parent has moved is a thing to be told about rather than a read that should fail — but
"pinned" would be the wrong word for it, and calling it one would be the third occurrence of the
same mistake.

A featureset carries `composes` **without** a `definition_version`, so a composed featureset has no
drift to report. That is a gap in the build, not a decision.

### 5.2 Restatement is reported, not prevented

`ViewManager.restated` compares a namespace's *current* Delta version against the version pinned by
a view version. A namespace that has moved is not automatically wrong — correcting a stale row is a
legitimate act — but it means a read without the pin returns something other than what was
assembled, and anybody comparing two runs needs to know which case they are in.

That is as far as it goes today. Tracing a restatement *forward* — from the moved namespace to the
snapshots, the parameter sets and the decisions that used the superseded values (`FR-FEA-016`) — is
not built. Bitemporality is what would make it possible; nothing computes it.

### 5.3 Retirement is a consumer question, not a housekeeping one

`ContractBinder.can_retire(view, version)` names every contract still pinning a namespace, and
`GET /feature-views/{name}/versions/{v}/retirable` publishes it. MAYA knows the consumers **exactly**
— from the contracts, rather than from a convention about who was supposed to tell whom, which is
the usual reason a feature is deprecated and something breaks a month later.

**There is no retirement operation.** The question can be asked and there is nothing yet to refuse,
so this is a check waiting for the act it guards rather than a control in force.

---

## 6. Bulk transfer: the one layer where the rules invert

Everything else in MAYA moves small documents: a warrant, a contract, a finding. Feature values are
not small. A featureset over a few million entities is the ordinary case, and an API that turns it
into JSON objects — one dictionary per row, keys repeated on every line — spends most of its time
and nearly all of its memory on punctuation.

So `core/features/transfer.py` and `routes/transfer_routes.py` invert the rule: **nothing is
materialised whole.** Reads iterate Arrow record batches straight off the Delta files and write them
out as they go; writes parse a batch at a time and append. Peak memory is one batch, whether the
dataset is a thousand rows or a hundred million.

**A batch is sized by cells, not rows.** Sixteen thousand rows of six columns is a few megabytes;
sixteen thousand rows of two thousand columns is not, and a row count alone would make the
"peak memory is one batch" claim true for one shape and false for the other:

```python
BATCH_ROWS, TARGET_CELLS, MIN_BATCH_ROWS = 16_384, 1 << 20, 512
batch_for(columns) = max(512, min(16_384, 1_048_576 // columns))
```

Four output formats, and the choice is not cosmetic:

| Format | For | Why |
|---|---|---|
| `arrow` | an execution engine | zero-copy both ends; the only one genuinely incremental in both directions |
| `parquet` | disk | columnar and compressed. Assembled to a temporary file and streamed from it, because a Parquet footer cannot be written until the end |
| `ndjson` | anything | the lowest common denominator, and it streams |
| `json` | a page | hard-capped at 10,000 rows. A browser asking for ten million rows is a mistake, and answering it is not a kindness |

**CSV is accepted and never written.** It is what somebody has, so MAYA will read one. A CSV cannot
carry a type, so a feature exported as CSV comes back as text and both clocks come back as strings —
which is the failure of §2 arriving through a file format.

Reads use the **pinned** Delta version. A featureset's `/parts` names each namespace and its pin, so
an engine can pull a large set in parallel rather than waiting on a join.

> **One honest exception.** The *featureset* export in `arrow` and `parquet` joins its parts in
> memory before writing. The no-materialisation rule therefore holds for a single namespace and not
> yet for a join across several.

---

## 7. Telemetry: the half of monitoring that was missing

Monitors could always be *evaluated*. They had to be **handed** their rows, which made monitoring a
thing somebody remembered to do, and made the scheduler able to record only that a monitor had
*stopped* running. `core/telemetry/` holds the data instead.

**Two bitemporal Delta streams per model version, and flattening them would be the mistake.** A
**score** exists the moment the model runs; an **outcome** is learned later. The gap between them is
precisely what the delayed-label discipline reasons about, so one stream would take that reasoning
away before it started. Joining them is a read-time act performed against a stated moment, which
makes maturity decidable **per row** rather than assumed for a batch.

**Ingestion is idempotent on the digest of the batch's own rows.** Real collectors deliver at least
once, and `telemetry_batch.digest` is `UNIQUE`: a redelivered batch is accepted and not written
again. A monitor that double-counts a redelivered batch reports a population that never existed.

**A row without its own timestamp is refused** rather than stamped with the batch's. Stamping is how
every window silently becomes wrong.

**A sample knows it is a sample.** High-volume models are ingested at a rate, and the rate is
recorded on every row, so a statistic computed downstream can say what population it speaks for
instead of quietly speaking for the sample.

The relational side holds only the receipt — `telemetry_batch`: the digest, the Delta table, a row
count and a time. The rows are in Delta, because `tests/test_schema_discipline.py` holds a rule that
would otherwise rot: no relational table may hold bulk values.

---

## 8. Governance of a feature

| Control | Behaviour | Built |
|---|---|---|
| **Certification** | `experimental` → `certified` → `deprecated`, on the `feature` row | yes |
| **Sensitivity, PII, protected basis, proxy risk** | columns on `feature`; `protected_basis` and `proxy_risk` exist to be read by a gate | the columns, yes |
| **Ownership against authorship** | `created_by` is history and never moves; `owner` is a responsibility and transfers to somebody named, with the handover in the chain | yes — [16 §4](16-features-composed-and-shaped.md) |
| **Sealing and ephemerality** | a sealed feature is final and still composable; an ephemeral one carries a TTL and nothing may depend on it | yes — [16 §3](16-features-composed-and-shaped.md) |
| **Retrieval policy** | fill · normalise · align, defaulted on the object and overridable per request, resolved by the same left-to-right fold | yes — [16 §5](16-features-composed-and-shaped.md) |
| **Quality on materialisation** | `ViewManager.quality` computes a null rate and a distinct count per feature and stores it on the view version | a report, not a gate: nothing quarantines a version on it |
| **Consumer impact** | `can_retire` names every contract that pins a namespace | yes, for contracts |
| **Lineage** | `lineage()` is every ancestor including derived ones; `rests_on()` is the base features alone | yes — [17 §5](17-feature-and-model-algebra.md) |
| **Erasure and retention** | Delta deletion vectors, per-subject keys, retention by class | **design.** `DeltaPaths` carries a `retention_days`; nothing crypto-shreds |

---

## 9. Where values come from: uploaded, or pulled

Two ways in, and only two.

**Uploaded.** A file arrives at `POST /api/v1/feature-views/{name}/data` or through the screen. CSV,
JSONL, Parquet or Arrow — CSV and JSONL first because that is what a person has. A CSV is read and
never written: it cannot carry a type, so a feature exported as one would come back as text with both
clocks as strings.

**Pulled.** A view declares a *source* — a SQL query, a file on a volume, an object in S3 or GCS — and
MAYA fetches from it. `sql` goes through SQLAlchemy, so any driver the deployment installs works;
`file`, `s3` and `gcs` go through pyarrow, which carries its own filesystems, so an object store is the
same reader with a different prefix.

### 9.1 MAYA pulls; it does not read through

This is the whole design, and it is a consequence of §3 rather than a preference.

The point-in-time guarantee holds because the bound is `min(label_ts, as_of)` over rows that carry both
clocks and are **never amended in place**: a restatement is a new row with a later ingest time, so the
earlier read stays derivable. A source that overwrites has neither property. An ordinary warehouse
table, a view rebuilt nightly, a file replaced on a schedule — once August's restatement lands, May's
row is gone, and no operator applied at read time recovers what the June decision saw. The read does not
fail. It returns the restated number and says nothing, which is §2's leak arriving through the back
door.

So what a pull produces is an **ordinary feature view version**: bitemporal, immutable, pinned by
contracts, exportable, and MAYA's. A second pull is a second *version* and not an update, so a warrant
pinned to the first does not change meaning because somebody refreshed. Everything in §5 about a stable
name whose contents moved applies unchanged, because a pulled version is not a special kind of version.

The same argument is made formally in the research paper, §*A corollary about where the data may live*:
an operator defined over rows that can be overwritten is defined over the wrong object.

### 9.2 What a source may do, and what it may not

| | |
|---|---|
| **Read only** | A SQL source is refused unless its first keyword is a read — checked when it is **stored**, not when it is run, because a statement nobody may run is one nobody should be able to save. Matched on a word boundary at the start, so `SELECT … FROM updates` is still a perfectly good query: a control that refuses correct work is one people route around |
| **One statement** | A semicolon followed by anything is refused. A second statement appended to a read is how a read stops being one |
| **One source per view** | A view filled from two places at once has a provenance nobody can state. Declare a second view |
| **No credential** | A source names a `credential_ref`; the deployment resolves that name from `sources.credentials.<name>` or `MAYA_SOURCE_<NAME>`. The schema has nowhere to put a secret, and a test asserts it — a register holding a warehouse password is one nobody can hand to an auditor |
| **Column mapping** | A warehouse calls the entity `customer_number` and the clock `asof`. Renaming at the boundary rather than making somebody rewrite their query is the difference between a source people declare and a source people export a CSV to avoid |
| **Preview before commitment** | `GET …/source/preview` reads and writes nothing, and names the required columns that are missing. A row without both clocks is refused at load; saying so at preview means it is refused before a version exists rather than after |
| **A pull of nothing is not a version** | An empty result is refused. A version of nothing is not a version |

Every declaration, amendment, retirement and pull is on the evidence chain, carrying what was read, from
where, how many rows and with what digest — so *where did this number come from* has an answer that
survives the source being dropped. A pull that returned identical bytes says so: "we refreshed and
nothing changed" is a fact a reviewer wants, and a silent no-op is not.

**Not built:** no scheduled pull. A source is pulled on demand, by a person or by a script calling the
API; nothing in the batch refreshes one on a timer. Incremental pull is also absent — every pull reads
the whole source, which is correct and is not a strategy for a billion rows.

---

## 9.3 Two Delta implementations, and how they are held equal

`deltalake` ships as a compiled Rust extension, and some estates forbid binary
wheels outright — no amount of vendoring helps, since there is nothing to
vendor that is allowed to run. Those estates could not install MAYA at all.

`maya_deltalake/` implements the six calls MAYA makes — `DeltaTable(path)`,
`.version()`, `.load_as_version(n)`, `.to_pandas()`, `.to_pyarrow_dataset()`
and `write_deltalake(...)` — in pure Python over pyarrow. That is the whole
surface, verified by reading the codebase rather than assumed. It is **not** a
reimplementation of Delta Lake: no merge, no vacuum, no partitioning, no object
store, no deletion vectors. Everything outside the subset raises by name,
because a fallback that quietly does less than the thing it stands in for is
the failure it would be written to avoid.

**It writes the real format.** The transaction log is the actual protocol —
`_delta_log/NNN….json` carrying `protocol`, `metaData`, `add`, `remove` and
`commitInfo` — so a table written on a locked-down estate opens in Spark, in
Databricks and in `deltalake`, and one written by any of those opens here. A
private format that merely worked would quietly cost the portability that is
half of what Delta is chosen for.

`db/delta_backend.py` makes the choice once, preferring the reference
implementation wherever it installs. Three modules imported `deltalake`
directly and three import sites is three places to get a fallback wrong — the
usual way being that two fall back and the third raises `ImportError` at the
moment somebody exports a large table.

**How they are held equal** is the part that matters. Not by a shared type —
mypy correctly objects that they are different types, and no annotation can
claim otherwise without lying about the ninety per cent that differs. By
behaviour:

| | |
|---|---|
| One test body, both implementations | Every behavioural test in `tests/test_maya_deltalake.py` is parameterised over both. Two test bodies would be two specifications, and they drift |
| Each reads the other's tables | Append, overwrite and time travel, in both directions, including a table written alternately by the two — which is what happens when an estate installs the package after running without it |
| The schemas are compared | Parsed and compared as structures, including for a `shape: [12]` vector and a `[3, 3]` matrix, which Delta describes as an array and an array of arrays. A shape recorded differently is a curve arriving with the wrong number of tenors under the other reader |
| **The whole platform suite runs twice** | CI runs all 3,914 tests a second time with `MAYA_DELTA_BACKEND=maya_deltalake`, and the counts must match. That the fallback passes tests written for it proves little; that it passes the ones written for the platform is the claim |

**Why this is safe here and would not be everywhere.** Delta guarantees a set
of rows, not a sequence, and the two implementations return them in different
orders. MAYA does not depend on that, because the point-in-time read sorts by
`pit_order_key` — total and content-based — which was built so that two
point-in-time implementations could not break a tie opposite ways. Its own
comment says *a Delta rewrite cannot change the answer*; swapping the backend
is a Delta rewrite by another name. The property that stopped two readers
disagreeing is the property that makes a second writer safe.

**Single writer.** Commits are created with `O_EXCL`, which is the protocol's
own concurrency primitive on a POSIX filesystem: two writers racing for version
*N* means one fails and the loser's Parquet file is removed rather than left
orphaning bytes no commit references. That suffices because MAYA serialises
Delta writes above this layer. It does **not** suffice on NFS or an object
store, where exclusive create is not atomic, and the fallback refuses to be
pointed at one rather than appearing to work.

---

## 9.4 Delta or Iceberg, and why the pin survives the choice

§9.3 is about two *implementations* of one format. This is about two formats.

MAYA asks a table format for six things — open it, say which version is
current, read at a past version, read the whole thing, stream it in batches,
write a new version — and Delta and Iceberg both have all six. Nothing above
`db/` asks for a seventh, which is what makes the substitution possible at all.

**Why offer both.** A bank whose lakehouse is already Iceberg should not have to
hold its feature data in a second format its Trino, Athena or Snowflake cannot
read; keeping a second copy is how two answers to the same question start
existing. A bank with no preference should not have to think about it, so
**Delta stays the default** — and not by inertia: Delta is what the four-hour
soak, every worked example in this documentation, and the suite in its ordinary
configuration have actually run against.

    MAYA_TABLE_FORMAT=iceberg          # environment, wins
    data.table_format: iceberg         # or configuration

`db/table_backend.py` decides once, at start-up, and `build()` is the only
place that names either store. The `data.iceberg.catalog` block points at Glue,
Nessie, Polaris or any REST catalog a bank already runs; left empty, MAYA keeps
a SQLite catalog inside the warehouse directory, so a laptop needs no external
service and Linux and Windows behave the same.

**Set it once, at the start.** Switching format on an estate that already holds
data **does not migrate it**. The old tables are in the old format, the new
store does not find them, and a feature view whose data is invisible reads as
*empty* rather than failing — which is the worst available way to learn this.
So start-up logs it at `WARNING` when Iceberg is in use, naming the root and how
to go back, rather than leaving it to be discovered by a materialisation that
returns nothing.

### What actually differs, and what it cost

| | Delta | Iceberg |
|---|---|---|
| A version | `0, 1, 2, …` | a **snapshot id**: 19 digits, int64 |
| Metadata encoding | JSON | Avro manifests |
| A catalog | none — a directory is the table | a catalog names the table |
| An all-null column | stored as `null` type | **refused** — v2 has no such type |

Two of those reached the register rather than staying inside `db/`.

`delta_version` is `BigInteger` in `feature_view_version` and
`dataset_snapshot`. An Iceberg snapshot id does not fit in an `INTEGER` on
PostgreSQL, and the failure mode of getting this wrong is a pin that cannot be
written on the dialect a bank actually deploys — so the column is widened for
both formats rather than conditionally. The column keeps its name: it holds
*the version this read is pinned at*, the concept the platform is built on, and
renaming it would have churned the schema, the API and eleven pages to record a
storage detail. `db/table_backend.describe()` is what answers *which format is
this*, for `/health` and for a soak report.

The all-null column is the one that forced a real change. A column with no
values has no type Arrow can infer, and Iceberg v2 refuses to store one — so
the declared dtype now travels with the write. `core/features/views.py` and
`core/features/assembly.py` pass the catalogue's dtypes down, keyed by name and
by slot respectively, and `db/delta_store.typed_arrow` applies them to exactly
the columns that have nothing to infer from. Delta accepted the untyped case
and gained the same correctness for free: an empty numeric feature is now a
`double` column under both formats, rather than a column whose type depends on
whether anybody happened to have written a row yet.

**The pin survives all of it.** A featureset binding carries `(namespace,
version)` whichever format wrote it; the point-in-time read is the *same
function* under both — `tests/test_iceberg_store.py` asserts it is the same
object and not a copy, because two copies of a bitemporal rule is the defect
this document exists to prevent. What is *not* claimed: the two formats are
interchangeable for an estate's existing data, and nothing converts between
them.

**How it is held equal.** Thirty-two Iceberg-specific tests cover the store,
the identifier mapping (including Windows path separators), the catalog, and
the widened columns. But those are not the evidence. The evidence is that
**CI runs the whole suite a second time with `MAYA_TABLE_FORMAT=iceberg`**, and
the count must match the ordinary run — the same argument §9.3 makes for the
fallback writer, for the same reason: a suite written for a component proves the
component, and the platform's own suite is what proves the substitution.

---

## 10. What is not built, by name

A gap recorded in one place is a gap somebody has to go looking for, so it is recorded here as well
as in [12 §0](12-implementation-plan.md#0-build-status).

| | Why it matters, and what stands in its place |
|---|---|
| **No online store** | There is no Redis, no DynamoDB, no Cassandra and no online serving path anywhere in the codebase. Batch-only is the honest description of what ships. The **half** of C-2's fix that does not need one is built: a view version is a namespace, a contract pins it, and `serving_namespaces` computes what serving must read |
| **`L-17` does not run** | Contract–serving agreement compares what serving *must* read against what it *did* read. The second half cannot exist without a store to observe. C-2 was invisible to every design-time check, so this one has to run in production or not at all |
| **No skew detection** | Neither distributional nor value-level. Value-level skew — recomputing a feature offline for the exact serving timestamp and comparing — is the expensive one and the one that catches implementation bugs, and it needs a serving log this platform does not have. *Score* drift is built and is a different thing: `core/monitoring/service.py` computes PSI against a reference drawn from a **stated** earlier telemetry window, so *what is this drifting from* is part of the record. `FR-FEA-012` asks for the reference to be the training-time distribution stored in the contract, and no column holds one |
| **No semantic search, no duplicate detection** | `pgvector` appears in no dependency and no source file. The economics of a feature store are reuse, and reuse needs discovery; this is the largest unbuilt thing in this document |
| **No artifact introspection into features** | Uploading an ONNX graph does not extract its input schema and reconcile it against the register. Features and contracts are declared through the API. The sandbox exists and introspects for *execution*, not for feature identification |
| **No quarantine on quality failure** | Assertions are computed and stored; a failing view version is not quarantined and raises no finding |
| **No Spark** | The PIT join is a Python join over Delta files. It is correct and it is not a 1B-row engine; the range-join, bucketing and Z-order design is a target |
| **`featureset` composition carries no drift stamp** | §5.1 |

---

## 11. Traceability

| Section | Satisfies | Not satisfied, and §10 says so |
|---|---|---|
| §1 the objects | `FR-FEA-001`, `FR-FEA-002`, `FR-FEA-006` | — |
| §2 two clocks | `FR-FEA-003` | — |
| §3 the `AsOf` operator | `FR-FEA-004`; `L-10`, asserted in `tests/test_laws.py::TestL10TheAsOfOperator` | — |
| §4 verification | `L-10`'s static half; finding `H-6` | — |
| §5 pinning | finding `C-2` at five levels; `L-W13`; `FR-FEA-009` for contracts | `FR-FEA-016` restatement is *reported*, not traced to decisions |
| §6 transfer | — | `NFR-PERF-006`: correct, not a 1B-row engine |
| §7 telemetry | `FR-TEL-001` … `FR-TEL-006`, `FR-MON-004` | — |
| §8 governance | `FR-FEA-013`, `FR-FEA-014`, `FR-FEA-008` | `FR-FEA-011` quarantine on a failing assertion |
| §10 | — | `FR-FEA-005`, `FR-FEA-007`, `FR-FEA-010`, `FR-FEA-015`, `L-17` |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
