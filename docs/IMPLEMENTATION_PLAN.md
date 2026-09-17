# MAYA — Implementation Plan

**From an empty repository to the platform in [`MAYA_Requirements_and_Design.md`](MAYA_Requirements_and_Design.md).**
Version 1.1 · 2026-09-17 · Ashutosh Sinha

> **Revision 1.1.** All eight open decisions are closed (§4). Six further calls are folded
> in: no database migrations, `maya_delta` as the lakehouse layer, Windows/Linux/macOS
> parity, Bootstrap 5 + jQuery on a Harvard Crimson system, the universal table contract,
> and workflow managed in the UI. `maya_delta` is now a milestone of its own (M2) and the
> milestones after it are renumbered.

---

## 0. What this document is

The specification says **what** MAYA is. This says **in what order it gets built, and how we know each piece actually works** — because on a platform whose entire value proposition is *evidence, not assertion*, a milestone that cannot be demonstrated has not landed.

Three jobs:

1. **Sequence.** Nine milestones (M0–M8), each with file-level deliverables and exit criteria that are *executable*, not adjectival. "Resolution works" is not an exit criterion; "a feature is pinned twice and the two content hashes are byte-identical" is.
2. **Gates.** The CI ladder, and which rung is installed at which milestone. Gates land *with* the capability they guard — better still, *before* it, while the violation they forbid is still impossible. A boundary rule added to a codebase that has already violated it is a refactor, not a gate.
3. **Decisions.** The register of what was decided and what it costs (§4).

Effort tags: **S** (days) · **M** (a week or two) · **L** (weeks) · **XL** (a quarter or more). Sizing, not dates.

Section references like §29.1 point into the specification unless they say "plan §". Where the specification now carries the detail — the Harvard Crimson tokens, the table contract, the `maya_delta` protocol subset — this plan points at it rather than restating it, because a requirement written in two places is a requirement that will be true in one of them.

---

## 1. Where we are

The repository was emptied on 2026-09-17 and restarted from the specification. It holds the specification, this plan, the brand, and the legal files. There is no package, no test, no server.

Everything that follows is greenfield, which is worth saying plainly because it is the one and only time some of these decisions are cheap. Bitemporality, content-addressed storage, the two import boundaries, three-platform CI and the table contract are all *free* today and *a rewrite* in six months. The plan is shaped around that asymmetry more than around anything else.

---

## 2. Ground rules

Not negotiated per milestone. They hold from the first commit.

### 2.1 Inherited from the estate

MAYA is a sibling of DishtaYantra and follows its conventions, so a developer moving between the two repositories finds the same idioms in the same places.

| Rule | Detail |
|---|---|
| **Authorship** | **Never add an assistant attribution trailer** to a commit message — no `Co-Authored-By: Claude`, no `Generated with [Claude`. Authorship of this repository is Ashutosh Sinha's alone. MAYA's history carries none; a `commit-msg` hook lands in M0 so it cannot regress |
| **Branches** | `develop` is where all work happens and is the branch to keep checked out. `main` is production and is *promoted to*, deliberately, never synced on a schedule. `main` sitting behind `develop` is normal and is not drift to close |
| **Version** | `maya/core/version.py::VERSION` is the single authority, with the per-release highlights log inline. Every module, template, banner and document reads it at runtime; a version string hard-coded anywhere else is a copy that will rot |
| **Config** | Dishtayantra-style YAML. `config/application.yaml` is **tracked and carries no secret**; `config/application.local.yaml` is a git-ignored overlay loaded straight after it. `${VAR}` and `${VAR:default}` substitution resolve against other keys, the environment and `--key=value` flags. Values are read as strings and coerced on access. A test enforces the no-secret half |
| **Startup** | One entry point: `python run_maya_web.py`, in DishtaYantra's shape — `__main__` guard, `spawn` set before anything imports, banner, logging config, signal and `atexit` drain handlers. A second way to start a server is a second set of startup invariants to get wrong (§24.5) |
| **No build pipeline** | Jinja2 + **Bootstrap 5** + **jQuery**, vendored and pinned. No bundler, no node toolchain, no CDN. The app renders with the network cable unplugged |
| **Two requirements files** | `requirements.txt` is what a deployment needs. `requirements-dev.txt` is what the documented workflows need. Installing only the first must not silently produce a smaller green suite — plan §7.3 |
| **Advertised numbers are derived** | A count, a list or a limit copied into a second place will drift. Compute it from the same source the renderer uses, and stamp it from one file |

### 2.2 The failure mode to design against

DishtaYantra's hard-won lesson, and MAYA is if anything more exposed to it: **artifacts that build, validate and look right while being wrong.** A pin whose hash is computed over the wrong canonicalization still hashes. A leakage certificate whose check is inverted still signs. A fill report that counts the wrong rule still renders. A dark-mode palette that fails contrast still looks fine to the person who chose it.

Four habits, applied to every milestone below:

- **Assert the rendered artifact, not the intent.** Check the bytes that came back, the served HTTP status, the text extracted from the PDF, the computed contrast ratio — not that the code meant to produce them.
- **Write the counterfactual.** A test that cannot fail is worth nothing. When fixing a defect, confirm the new test fails against the old code before keeping it.
- **Derive, never restate.**
- **Every reproducibility guarantee needs a negative test.** It is not enough that two pins of unchanged data hash the same; a pin of *changed* data must hash *differently*, and the test that proves it must be the same test.

### 2.3 From the specification

| Rule | Source | Gate |
|---|---|---|
| No non-UI source file over 1,500 non-comment lines | §22.1 | `tools/ci/file_size.py`, non-overridable |
| Nothing outside `maya.persistence` imports `sqlalchemy` | §14 | import-linter, non-overridable |
| Nothing under `maya.web` imports deeper than `maya.sdk` | §13, §16 | import-linter, non-overridable |
| Every endpoint has an SDK method and vice versa | §18.2.1 | `tools/ci/sdk_parity.py` |
| The two `.sql` files match the ORM metadata exactly | §14.3 | `tools/ci/gen_schema.py --check`, non-overridable |
| Every `<table>` comes from the table macro | §16.7 | `tools/ci/table_contract.py`, non-overridable |
| Every colour pair in `tokens.css` clears WCAG AA | §16.6 | `tools/ci/contrast.py` |
| Scripts are Python, not shell | §22.4 | Reviewed; `gates.py` is the entry point |
| `mypy --strict` on `domain/` and `services/` | §22.2 | CI |
| Functions under 50 lines, complexity under 10 | §22.1 | `ruff` |
| No silent config defaults | §22.2, §24.2 | startup validation + a test |
| Full suite green on SQLite **and** PostgreSQL | SC-10 | CI matrix |
| Full suite green on Windows, Linux **and** macOS | SC-14 | CI matrix |

§28.10 is right that a line count is a proxy and is defeatable by a 1,499-line `helpers.py`. The line limit stays as a cheap smoke alarm; the gates that actually constrain structure are the import boundaries, a maximum public-symbol count per module, cyclomatic complexity and a dependency-cycle check. **A module that fails those fails the build regardless of its length.**

---

## 3. Repository layout

Specification §22.3 is the authority. In summary:

```
<repo root>/
├── run_maya_web.py         # the one supported way to start MAYA
├── maya/                   # the product package
│   ├── core/version.py     #   VERSION, BUILD_DATE, APP_NAME — the only authority
│   ├── domain/ ports/ services/ resolution/ storage/
│   ├── persistence/        #   SQLAlchemy only; schema/ holds the two GENERATED .sql files
│   ├── workflow/ security/ api/ web/ jobs/ sdk/ cli/
│   └── config/ observability/
├── maya_delta/             # the lakehouse layer (§7.4) — its own top-level package
│   ├── native.py           #   deltalake-backed
│   ├── pure/               #   MAYA's own Delta protocol implementation
│   └── conformance/        #   the suite both backends must pass identically
├── config/                 # application.yaml (tracked) + application.local.yaml (ignored)
├── tools/ci/               # gates.py and friends — Python, so they run everywhere
└── tests/ docs/ assets/
```

Two layout decisions are recorded as ADRs in M0 because a decision that is not written down gets re-litigated every quarter:

- **ADR-001 — everything under `maya/`, not at the repository root.** DishtaYantra puts `core/`, `routes/` and `web/` at the root. MAYA does not, because `maya.persistence`, `maya.web` and `maya.sdk` are named import-boundary units (§13, §14, §16) and `pip install maya-sdk` must deliver a client of a few megabytes with no server in it (§18.2.3). Both need a real package root. Everything *inside* the package follows DishtaYantra's idioms unchanged.
- **ADR-003 — `maya_delta` beside `maya`, not inside it.** It holds no MAYA domain knowledge, is reachable only through the `LakeStore` port of §25, and must be independently testable and swappable. Burying a general-purpose Delta implementation inside the product package would make it neither.

---

## 4. Decision register

**All eight open decisions were closed on 2026-09-17, before any code.** Six further calls were taken at the same time. Each becomes a numbered ADR in M0; this table and specification §26.3 are the register.

### 4.1 The eight

| # | Decision | Taken | What it costs |
|---|---|---|---|
| D-1 | Feature set pin materialization | **Always materialize** | Disk. Bought: the difference between *"we can probably reproduce it"* and *"here are the bytes"* |
| D-2 | Pin uniqueness | **A pin series** — `(feature, pin_name)` is the series, `as_of_date` selects within it | Nothing, *now*. After pins exist it would mean rewriting sealed references, which sealing forbids. This is why it was answered first |
| D-3 | Non-causal fill in a training set | **Justified override**, never a silent allow and never a bare block | A justification field, surfaced on the warrant and recorded as an exception on the leakage certificate |
| D-4 | Model runtime in v2.0 | **Out**, with one conceded exception: blind scoring (§29.4) | Some execution happens outside MAYA and some lineage escapes. Accepted knowingly (§28.11) |
| D-5 | Namespace granularity | **Per team**, nesting one level | Sets quota, recertification scope and export control |
| D-6 | Lakehouse engine | **`maya_delta`** — native `deltalake` preferred, MAYA's own pure Python as fallback. No Spark, no JVM | An entire Delta implementation to write and keep honest. That is M2 |
| D-7 | Default parent binding for `extends` | **`pinned`**; `tracking` opt-in and blocked in production namespaces | Upstream fixes do not propagate automatically. Bought: a child's behaviour never changes without the child being touched |
| D-8 | Composite parameter granularity | **One set per composite**, namespaced by member alias | Less flexible for cross-composite reuse. Bought: the composite reproduces as one unit |

### 4.2 The six taken alongside

| Call | Taken | Where it lands | What it costs |
|---|---|---|---|
| **Database migrations** | **None.** Two generated `.sql` files, one per dialect; everything through SQLAlchemy | §14.3 · M1 | No in-place `ALTER` path. Schema change is export → recreate → import, and that path must be built in M1 and exercised every release — see §4.3 |
| **Lakehouse** | `maya_delta`, native-preferred with a pure fallback | §7.4 · M2 | A protocol implementation and a conformance suite |
| **Platforms** | Windows, Linux, macOS, equally first-class | §24.5 · M0 | Three-OS CI from the first commit; `spawn` everywhere; no `fork`, no `flock`, no POSIX-only sandbox |
| **UI stack** | Bootstrap 5 + jQuery, vendored; Harvard Crimson | §16.6 · M0/M1 | Theming through CSS custom properties rather than a Sass rebuild, which is what keeps "no build pipeline" true |
| **Table contract** | Every table paginated, searchable, sortable, from one macro | §16.7 · M0/M1 | One macro that must be good enough that nobody wants to bypass it — and a crawler that fails the build if they do |
| **Workflow management** | Authored and managed in the UI; YAML is a projection, not a second authority | §10.6 · M5 | A real policy editor with edit-time validation, and the policy itself governed by the workflow engine |

### 4.3 The one consequence worth flagging

**"No migrations" is a real trade, not a free simplification**, and it is worth being explicit about where the bill arrives. Before there is production data it costs nothing and removes an entire class of defect — no revision graph, no half-applied upgrade, no `downgrade()` that was never run. After there is production data, every schema change becomes a maintenance window: export the estate, drop, recreate from the `.sql` file, import.

That path is therefore **not optional and not late**. `maya admin export-estate` / `import-estate` is built in **M1**, alongside the schema it exports, and is exercised on **every release** thereafter — because an upgrade path that has never been run is not an upgrade path, it is a hope. The schema-hash startup check (§14.3) is what makes the failure loud instead of silent.

Feature data is unaffected: pins are immutable, content-addressed and independent of the metadata schema, so a metadata rebuild never touches a byte in Delta.

### 4.4 Still open, blocking nothing

- **SoD preset for the first namespaces** — *Small team* (3 roles), *Standard* (6) or *Regulated* (all 8, strict) (§28.9). All three ship; the question is what the seeded namespaces get.
- **Who seeds the first two namespaces** (§28.11). The platform cannot create its own critical mass of curated features, and an empty catalog is an empty shop. A sponsorship question, not an engineering one — but it decides whether M8 lands into use or into silence.

---

## 5. The sequencing law

Most of this plan can be reordered under schedule pressure. **Six things cannot.**

| One-way door | Must land in | Why it cannot be retrofitted |
|---|---|---|
| **Bitemporality** (§5.1, §29.1) | **M3**, in the first schema | Two columns, a second index dimension and a hash that covers them. Adding it later rewrites every table, every pin and every content hash. Without it, a vendor restatement corrupts backtests silently and nothing in the system can detect it |
| **Content-addressed materialization** (§7.1, §29.3) | **M3**, in the first write path | A pin written as an opaque copy cannot be de-duplicated afterwards without rewriting sealed data, which sealing forbids. Without it, forty features pinned monthly for three years is tens of terabytes of near-identical bytes |
| **Pin series as the key** (D-2) | **M3**, before the first pin | It fixes `feature_pins` and every `#` URI. Changing it later means rewriting sealed references |
| **Workspaces** (§28.3) | **M5**, with the workflow engine | Approval-as-merge does not retrofit onto an approval-as-button design. Every review surface built in M5 assumes it |
| **Three-platform CI** (§24.5) | **M0**, on an empty repository | Establishing it now costs an hour. Establishing it at M6 means discovering forty platform assumptions at once, each cheap alone and expensive together |
| **The table and boundary gates** (§16.7, §14, §13) | **M0**, before the first table or import exists | A gate installed while its violation is still impossible is strictly better than one installed after. These never have to be back-fitted because nothing ever violated them |

A seventh is softer but real: **the scratch namespace** (§28.1). Governance that is not the path of least resistance is governance nobody uses, and a quant with a deadline opens a notebook. The plan therefore builds `maya feature quick <file.csv>` — zero ceremony, typed and resolvable in one command — **in M3 alongside the governed path**, not in M8 as polish. The first five minutes must be faster than a notebook before the governed path is worth anyone's time.

Everything else in §28 and §29 is additive and sits behind a feature flag.

---

## 6. Milestones

### M0 — Skeleton, gates, three platforms · **S–M**

*Nothing about the product. Everything about making the next eight milestones checkable.*

**Deliverables**

- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`; `.venv` on Python 3.13.15 per `.python-version`.
- `maya/core/version.py` — `VERSION = "0.1.0"`, `BUILD_DATE`, `APP_NAME`, and the per-release highlights log.
- Package skeleton: every directory in plan §3 with an `__init__.py` and a module docstring stating what belongs in it **and what does not**.
- **`run_maya_web.py`** — the startup script, complete before there is a server to start: `__main__` guard, `multiprocessing.set_start_method('spawn', force=True)` at module level, the banner (version, build date, Python, platform, DB dialect, `maya_delta` backend, sandbox tier), logging configuration, signal and `atexit` drain handlers, config path and `--key=value` overrides.
- **Configuration**, DishtaYantra-style: `config/application.yaml` with `app`, `server`, `logging`, `db`, `storage`, `auth`, `sandbox`, `lake` sections and no secret; `${VAR:default}` substitution; `config/application.local.yaml` git-ignored and loaded straight after.
- **`maya_delta/` skeleton**: the public API surface, backend detection, the self-check, the configuration pin, and startup reporting. The implementations come in M2; what lands here is the *seam*, so nothing above it ever imports `deltalake` directly.
- **Vendored UI shell**: Bootstrap 5, jQuery, Cytoscape.js, CodeMirror 6, KaTeX, pinned under `static/vendor/`. `static/css/tokens.css` with the Harvard Crimson set of §16.6. `_macros/table.html` and `static/js/table.js`.
- `.githooks/commit-msg` refusing assistant attribution trailers; `.githooks/pre-commit` running the fast gates.
- **`tools/ci/`** — `gates.py` as the single entry point (**Python, not shell**, so it runs on all three platforms), plus `file_size.py`, `import_boundaries.py`, `public_symbols.py`, `cycle_check.py`, `gen_schema.py`, `table_contract.py`, `contrast.py`, `version_single_source.py`, `no_secrets.py`.
- **CI on three operating systems from the first commit** — Windows, Linux, macOS — with SQLite everywhere and PostgreSQL at least on Linux.
- `docs/adr/` — ADR-001 package layout, ADR-002 branch and release workflow, ADR-003 `maya_delta` placement, and ADR-004…ADR-011 recording the eight decisions of §4.1.
- A rewritten `.gitignore`: the retained one still encodes the old build's rules and should be pruned to what MAYA actually produces. `.gitattributes` normalising line endings.

**Exit criteria**

- `python tools/ci/gates.py` runs green on an empty package **on all three operating systems**.
- **Each gate is demonstrated to fail** on a deliberately planted violation — a 1,600-line file, a `sqlalchemy` import in `maya/services/`, a `maya.persistence` import in `maya/web/`, a raw `<table>` in a template, a token pair below 4.5:1, a second hard-coded version string. A gate nobody has seen fail is a gate nobody knows works.
- `python run_maya_web.py --help` runs and prints the banner on all three platforms.
- `git commit` with a `Co-Authored-By: Claude` trailer is refused by the hook.
- Starting with a secret in `config/application.yaml` fails a test.

---

### M1 — Foundation: identity, authorization, persistence, jobs, audit, chrome · **L**
*Specification Phase 0*

**Deliverables**

- `maya/persistence/`: engine and dialect selection, `UnitOfWork`, `types.py` (`PortableJSON`, `PortableUUID`, UTC normalisation, `NUMERIC(38,12)` mapped to text-and-convert on SQLite — **never float**), `locks.py` (PG advisory locks, SQLite write mutex).
- **The schema, generated** (§14.3): typed SQLAlchemy metadata in `models/` as the single source; `tools/ci/gen_schema.py` emitting `schema/postgresql.sql` and `schema/sqlite.sql`; the drift gate; the schema-hash stamp and the startup refusal on mismatch.
- **`maya admin init-db` / `export-estate` / `import-estate`** — the *only* upgrade path (§4.3), built now and exercised from now on.
- Schema for `users`, `roles`, `user_roles`, `groups`, `group_members`, `namespaces`, `grants`, `audit_events`, `jobs`, `schema_meta`.
- `maya/security/`: `AuthProvider` with DB and OIDC/SAML2 implementations behind one config switch; Argon2id; sessions with `HttpOnly`/`Secure`/`SameSite=Lax` and CSRF; API keys shaped `maya_<env>_<key_id>_<secret>`, stored hashed, shown once.
- `can(principal, action, object) -> Decision` — the **single** authorization function with the §11.2 resolution order and the role ceiling. Nothing in the UI, API, SDK or CLI bypasses it.
- Append-only, hash-chained audit (§19), each row carrying the previous row's hash.
- `maya/jobs/`: queue (PG `SKIP LOCKED`; SQLite in-process behind the same interface), worker loop on `spawn`, idempotency keys, cooperative cancellation, retry with backoff, dead-letter, the orphan reaper.
- **The UI chrome, themed**: `base.html`, nav, the Harvard Crimson system applied, light and dark, and the **first real tables** — users, roles, grants, jobs, audit — every one of them through the table macro.
- `maya/api/` + `maya/sdk/` + `maya/web/` end to end for exactly one journey: log in, see an empty catalog, list your jobs, browse the audit log. Thin, but it proves the whole stack including both import boundaries, the SDK-parity gate and the table contract.
- Bootstrap: `admin` / `maya-dev-admin` with `must_change_password`, and a **refusal to start** outside dev unless `allow_default_admin_password: true`.

**Exit criteria**

- A user logs in over SSO *and* over DB auth, sees an empty catalog, and every authentication event is in the audit log.
- **The authorization matrix suite exists and is green**: every role × every action × every object state, **zero unexpected allows** (SC-7). It grows with every later milestone and never shrinks.
- Full suite green on **both** backends (SC-10) and **all three platforms** (SC-14).
- **SC-15**: `gen_schema.py --check` is clean, and a hand-edit to either `.sql` file fails the build.
- The estate round-trips: seed → `export-estate` → `init-db --force` → `import-estate` → every hash verifies and the database is indistinguishable.
- The hash chain is verified by a test that **tampers with a row and proves detection** — the negative case, not just the positive one.
- **SC-17**: every table on every shipped screen paginates with a working rows dropdown, searches, and sorts across the whole result set rather than the visible page. The crawler gate is green and has been seen to fail.
- Contrast gate green; dark mode verified by computed ratio, not by eye.
- `/healthz`, `/readyz`, and a system health page naming every dependency, the schema hash, the `maya_delta` backend and the sandbox tier.

---

### M2 — `maya_delta` · **L**
*New milestone. Specification §7.4*

*Pins are written on top of this, and the physical layout is a one-way door, so it is solid before M3 rather than alongside it.*

**Deliverables**

- `maya_delta/native.py` — the `deltalake`-backed backend, plus the self-check that decides whether it is usable.
- `maya_delta/pure/` — MAYA's own implementation of the declared protocol subset (§7.4): the `metaData`, `protocol`, `add`, `remove` and `commitInfo` actions; Parquet checkpoints; optimistic concurrency by exclusive create; partition pruning; per-file min/max statistics; a space-filling-curve sort on write; time travel by version.
- **Loud refusal** on any table requiring a reader or writer feature the pure backend lacks — deletion vectors, column mapping, change data feed, liquid clustering — naming the feature. Never an approximation.
- `maya_delta/conformance/` — one suite, run twice, once per backend.
- The `LakeStore` port (§25) and MAYA's adapter over it, so nothing in `maya/` imports either backend directly.

**Exit criteria**

- **SC-16**: the conformance suite passes identically on both backends, and the **cross-backend round trip** holds in both directions — a table written by `native` is read by `pure` and vice versa, with bytes compared.
- Concurrent writers race for the same log entry and exactly one wins, on NTFS, ext4 and APFS.
- A table using an unsupported protocol feature is **refused by name**, not silently misread — with a fixture table for each unsupported feature.
- Protocol versions are read from the log and asserted as **ranges, never literals**. A test that hard-codes a version number passes for the wrong reason the moment a writer is upgraded; a lint check forbids the literal.
- Forcing `lake.backend: pure` in config runs the full M2 suite green, and the health page and every provenance record name the backend in use.

---

### M3 — Features: bitemporal and content-addressed · **XL**
*Specification Phase 1 · contains three of the six one-way doors*

**Deliverables**

- `maya/domain/feature.py` and friends: `Feature`, `FeatureVersion`, `FeaturePin` (**as a series**, per D-2), `Schema`, `SourceBinding`, `ResolutionPolicy`, `Derivation`, `InheritanceLink`.
- **Bitemporal from the first schema** (§29.1): `event_time` and `knowledge_time` on every row, the second index dimension, both covered by the definition and content hashes. A restatement writes a new knowledge-time row and never overwrites.
- `maya/resolution/`: planner, grid (`as_is`, `calendar`, `union`, `intersection`), all eleven rules with `limit` and `max_age` bounds, non-causal marking and propagation, and the **fill report** on every run.
- Source drivers as registered plugins (§25): `sql`, `csv`, `parquet`, `json`, `delta`, `derived`, `python`. Content-addressed uploads.
- The expression language and its Arrow-kernel compiler, shared by transforms, filters, ACL row filters and workflow checks — one grammar, learned once.
- Quality contracts (§5.5) that **block** a pin rather than warning.
- **Content-addressed materialization** (§29.3): fragments bounded by a rolling hash over the index — *not* by row count, or one inserted row invalidates everything downstream — a fragment index, a pin as a manifest, and a garbage collector provably safe against sealed pins.
- Canonical hashing (§7.2 Rule 4) over the canonical representation, never over file bytes.
- Native Arrow nested types with axis manifests — no array is ever a string.
- The **feature algebra** (§5.8): eleven operators, typed at definition time, `extend` storing a diff, `pinned` binding by default (D-7), cycle rejection, depth cap, cost rollup.
- The **leakage certificate** (§29.1), including D-3's justified exceptions recorded on it.
- The **scratch namespace** and `maya feature quick <file.csv>` (§28.1).
- Feature designer, pin-series browser, and the download dialog with explicit array-encoding choice — every table through the macro.

**Exit criteria**

- **SC-1**: a feature is pinned, the cache wiped, it is re-resolved, and the content hashes are byte-identical — *and* a pin of changed data hashes differently, in the same test.
- **SC-11**: a feature is resolved as of a past knowledge instant *after* a restatement and returns the pre-restatement values exactly.
- **SC-12**: a monthly pin of a feature whose history did not change costs under 5% of a full pin, measured.
- A property-based suite proves write → read → identical for **every** logical type including `list`, `fixed_vector`, `tensor`, `struct` and `map`, across Arrow IPC, Parquet, JSON and all three CSV encodings — **on both `maya_delta` backends**.
- A leakage certificate is produced, and a **deliberately leaky** feature set is refused with the offending rows named.
- `maya feature quick` takes a messy CSV to a typed, resolvable, shareable feature in one command, timed and under a minute.
- A pin interrupted mid-write leaves nothing visible and is reclaimed by the reaper (§15.3).

---

### M4 — Feature sets · **L**
*Specification Phase 2*

**Deliverables**

- Attribute mapping; the four alignment modes; broadcast joins stated in the plan; rejection — never a silent row pick — where a member index has columns the set does not.
- The five-layer policy precedence (§6.4), six with inherited policy (§6.8), **with the winning layer and its source shown per attribute in the UI**. The requirement most likely to be quietly dropped, and an exit criterion for that reason.
- Filters compiled to Delta partition pruning, including universe filters referencing another feature as of the row date, so survivorship bias is excluded by construction.
- The three materialization shapes, each with its axis manifest.
- **Cascade pin** in one transaction with one approval, rolling back entirely if any member fails a quality check. Materialize by default (D-1).
- The feature set algebra (§6.8), depth cap 8, access propagation naming withheld attributes rather than dropping them.
- Equivalence detection, so the catalog does not fill with near-copies.

**Exit criteria**

- A tensor-bearing feature set pins and round-trips through CSV *and* Arrow with no loss, verified by extracting the values back.
- A cascade pin over forty members either completes or rolls back entirely — proved by injecting a quality failure at member 39.
- Two algebraically identical definitions are detected as duplicates at creation.
- A set derived from a feature the user cannot fully read resolves with the withheld attributes **named and null**, never silently absent.

---

### M5 — Workflow, workspaces, and the policy UI · **L**
*Specification Phase 3 · contains the fourth one-way door*

**Deliverables**

- The canonical state machine (§10.1) driving every object type, with states, transitions, approvals and notifications as data.
- Pluggable named checks evaluated at transition time, each failing with the name of the check that blocked.
- SoD with three strictness levels and the **role presets** of §28.9 — *Small team*, *Standard*, *Regulated*.
- **Workspaces** (§28.3): copy-on-write branches of the catalog. Edit, resolve against the edit, review as a branch diff, approve as a merge.
- Semantic diff per object type — schema, policy, formula rendered as mathematics, code, document.
- Lineage written **by the same transaction that creates the object**, so it cannot drift.
- The algebra canvas (§16.3) on vendored Cytoscape.js: operator nodes, seven typed edge styles, four overlay modes, focus-plus-context beyond ~300 nodes.
- **The workflow UI, viewing and managing** (§10.6): state machines rendered with the live population on them; per-instance history; the **policy editor** as structured controls with edit-time validation (unreachable state, unsatisfiable approval, unknown check, permanently-unapprovable object) and a preview of the change against the live population; the policy itself versioned, diffed, approved and audited; YAML as an import/export projection with round-trip fidelity tested both ways.
- Campaigns (§10.5) and break-glass (§10.4) — loud, permanent, never erasable.

**Exit criteria**

- A feature reaches `approved` **only** through a compliant, audited path — proved by a suite that attempts every non-compliant route and is refused by each.
- Self-approval is refused under `strict` and permitted under a namespace explicitly configured otherwise, with the configuration visible on the review screen.
- A change is rehearsed in a workspace, reviewed as a branch diff, and approved as a merge, with nothing production-facing touched before the merge.
- **A policy is created, edited, approved and published entirely through the UI**, with no YAML touched — and the resulting behaviour is proved by a transition that the new policy blocks and the old one allowed.
- A policy edit that would strand objects is refused at edit time, naming the count and the objects.
- YAML export → import → export is byte-identical.
- Break-glass leaves a permanent `force_approved` mark, notifies immediately, and appears in the monthly report.

---

### M6 — Models · **L**
*Specification Phase 4*

**Deliverables**

- The **formula IR** (§8.1), and the fact that **nobody authors it by hand** (§28.6): parsed from LaTeX, lifted from Python by AST analysis, or drafted and corrected. It earns its place by type-checking against the bound feature set, rendering the document, and producing semantic diffs.
- The declared black-box node, so an opaque model is *recorded as opaque*.
- Input contract validation ahead of warrant issuance.
- Code artifacts with the six-rung validation ladder (§17.2) on the **per-platform sandbox**, ending in a smoke run and a **determinism probe**.
- `ParameterSet` as a first-class versioned object with bounds checking.
- The LaTeX editor: KaTeX preview, Tectonic PDF export in a sandboxed worker, required-section completeness blocking submission, `\mayaformula{}` binding the document to the IR.
- **Composite models** (§8.7): five kinds, union contract, alias-namespaced parameters (D-8), frozen members, maturity capped at the lowest member's, opacity and access propagation, depth cap 4.
- **Spec–code conformance testing** (§29.7), behind a flag.

**Exit criteria**

- **SC-9**: a new model designer, unaided, publishes a first model in under 60 minutes — measured with a real person, not estimated.
- A model version's PDF is compiled by Tectonic **on all three platforms** and its **extracted text** is asserted, not the code path that produced it.
- Changing the IR marks the document for re-review automatically.
- A malicious artifact — filesystem write, socket open, `eval`, infinite loop, 10 GB allocation — is refused or contained at every one of the six rungs, one test per rung, **on each sandbox tier**, with the tier recorded on the validation report.
- A composite cannot reach `approved` while any member is `experimental`.

---

### M7 — Warrants and the evidence bundle · **L**
*Specification Phase 5*

**Deliverables**

- Training warrants: contract validation, split specification, seed, environment declaration, expiry, and the download-checksum-then-verify-on-upload cycle that **turns a warrant from paperwork into a control** (§9.1).
- Execution warrants as **live instruments** (§28.5): short-lived signed tokens, execution reported back as lineage, and **covenants** (§29.5) whose breach suspends the warrant and fails every consuming SDK call closed with the covenant named. Offline use stays possible and is labelled `unattested`.
- Sealing, chain of custody, cloning into experiment families, revocation propagating to every consumer.
- Composite warrants: union contract validation per member, member manifest, deterministic per-member seed derivation from one seed, partial parameter upload, per-member metrics.
- **Escrowed holdout and blind scoring** (§29.4) — the one conceded piece of runtime (D-4) — including the **scoring-attempt counter**.
- `maya export bundle` / `verify` — signed archive with the pinned execution environment and the original run's **output** hash, so `verify` re-executes and compares outputs, not just inputs (§28.7). Where re-execution is impossible, the bundle says so rather than implying a verification it cannot perform.

**Exit criteria**

- **SC-2**: a two-year-old training run is reproduced from its warrant in under 10 minutes with no human archaeology — rehearsed against a warrant deliberately aged in the fixture.
- Data modified outside MAYA between download and parameter upload is caught by the checksum and flagged `unverified_data`, and cannot be approved without an explicit justified override.
- A covenant breach suspends a live warrant and the next SDK call fails closed naming the covenant — end to end, against a running server.
- A bundle verifies **on a machine with no network route to any MAYA**, on all three platforms, and a bundle with one byte altered fails verification.

---

### M8 — Hardening · **L**
*Specification Phase 6*

**Deliverables**

- Performance and soak against the §24.3 targets; scaling levers pulled in the stated order and the result recorded.
- Concurrency: parallel pin attempts, cascade deadlock probes (locks in sorted id order, so deadlock is impossible by construction — tested, not assumed), double-submit idempotency, cancellation mid-job.
- SDK and CLI completeness; `maya.testing` fakes; the record/replay transport.
- **The UI test suite runs against the SDK fake** — the sharpest available proof that no screen holds a backdoor.
- Runbooks shipped **with** the product (§20), including schema rebuild via export/import and `maya_delta` backend fallback.
- Backup and recovery with a **tested** quarterly restore drill ending in `maya admin verify-integrity`.
- External security review.
- The synthetic market dataset (§23) completed — seeded in M3.

**Exit criteria**

- **All seventeen success criteria measured and met**, each by a named test or benchmark (plan §8).
- The restore drill has been performed and its result recorded and visible.
- No unresolved high findings from the external review.

---

### Beyond M8 — the additive innovations

Each behind a feature flag, in roughly this order (§29.11): shadow replay (§29.2) → licence algebra and external audit anchoring (§29.6) → the recorded challenger (§29.8) → spreadsheet import (§29.9) → vendor model registration (§29.10). Shadow replay is first because it changes what a review *is*: *"this forward-fill limit change moves 3 of 11 dependent models; the PD model shifts by more than 2 bp on 0.4% of rows"* instead of a list of names.

**Deferred, and deliberately.** The research paper and the presentation decks are to be rewritten against this specification. They are not in M0–M8 and are not blocked by it. `NOTICE` still references `docs/research/LICENSE`; restore it with the paper or amend `NOTICE` then.

---

## 7. The gate ladder

One entry point — `python tools/ci/gates.py` — run locally and in CI, on all three platforms. **Never a remembered list**; the script is the authority, and a gate that exists only in someone's head has already been skipped.

| # | Gate | Lands | Overridable |
|---|---|---|---|
| 1 | `ruff` lint + format, function length, complexity | M0 | no |
| 2 | `mypy --strict` on `domain/`, `services/` | M0 | no |
| 3 | File size — 1,500 hard, 1,200 note, 800 warn | M0 | **no** |
| 4 | Import boundary: no `sqlalchemy` outside `maya.persistence` | M0 | **no** |
| 5 | Import boundary: nothing under `maya.web` imports deeper than `maya.sdk` | M0 | **no** |
| 6 | Import boundary: nothing in `maya/` imports `deltalake` directly | M0 | **no** |
| 7 | Public-symbol count per module, dependency-cycle check | M0 | no |
| 8 | Version single-source grep | M0 | no |
| 9 | No secret in `config/application.yaml` | M0 | no |
| 10 | **Table contract** — every `<table>` from the macro | M0 | **no** |
| 11 | **Colour contrast** — every token pair ≥ 4.5:1 text, 3:1 non-text | M0 | no |
| 12 | **Three-platform matrix** — Windows, Linux, macOS | M0 | **no** |
| 13 | **Schema drift** — regenerate both `.sql` files and diff | M1 | **no** |
| 14 | Estate export → recreate → import round trip | M1 | no |
| 15 | SDK ↔ API parity, both directions | M1 | no |
| 16 | Unit + property-based suites | M1 | no |
| 17 | Repository suite on **real SQLite and real PostgreSQL** | M1 | no |
| 18 | Authorization matrix — zero unexpected allows | M1 | **no** |
| 19 | OpenAPI contract against a committed snapshot | M1 | explicit approval to change the snapshot |
| 20 | **`maya_delta` conformance** — both backends, cross-backend round trip | M2 | **no** |
| 21 | No literal Delta protocol version numbers in assertions | M2 | no |
| 22 | Reproducibility: pin → wipe → re-resolve → compare | M3 | **no** |
| 23 | Concurrency: parallel pins, deadlock probes, idempotency | M3 | no |
| 24 | Playwright end-to-end on the main journeys, real screenshots | M5 | no |
| 25 | Dependency scan, SAST, sandbox escape tests per tier | M6 | no |
| 26 | Performance benchmarks — no regression over 10% without a note | M8 | note required |

### 7.3 Two things this ladder must not be allowed to do

**A green suite at the wrong total.** A module that cannot import its dependency *skips*, and a module-level skip removes its whole file from the collected count. Install `requirements.txt` without `requirements-dev.txt` and the suite goes green at a smaller number while real coverage has silently gone. From M1 the advertised count is stamped from one source (`docs/test_counts.json`) and the pre-commit hook re-collects and fails if the total moved. **Check the total, not merely the absence of failures.** This matters more here than in DishtaYantra, because `maya_delta`'s two backends and three platforms multiply the ways a suite can quietly shrink — the stamp is per platform and per backend, not one number.

**A checker whose output is all noise.** A checker that reports hundreds of false positives trains everyone to ignore it, and would then hide the real one. Any checker added here is sampled before its number is treated as debt.

---

## 8. Success criteria, mapped

Specification §2 states seventeen. Each is met by a named test at a named milestone. A criterion with no test is a wish.

| # | Criterion | Met at | Proved by |
|---|---|---|---|
| SC-1 | Byte-identical re-resolution of any pinned feature set | M3 | Gate 22, with the negative case in the same test |
| SC-2 | Two-year-old training run reproduced in under 10 min | M7 | Bundle verify against an aged fixture |
| SC-3 | 200 concurrent interactive users per API pod | M8 | Soak benchmark |
| SC-4 | Metadata p95 under 300 ms | M8 | Benchmark; regression-gated from M1 |
| SC-5 | 50-col × 10-year resolution under 15 s warm, 60 s cold | M8 | Benchmark on the synthetic dataset |
| SC-6 | 100% of non-UI files under 1,500 lines | M0 | Gate 3, continuously |
| SC-7 | Zero unauthorized accesses succeed | M1 | Gate 18, grown by every later milestone |
| SC-8 | 100% of state changes audited immutably | M1 | Hash-chain suite, including the tamper case |
| SC-9 | New designer publishes a first model in under 60 min | M6 | Timed with a real person |
| SC-10 | Full suite green on SQLite and PostgreSQL | M1 | Gate 17, continuously |
| SC-11 | Point-in-time reconstruction after a restatement | M3 | Bitemporal suite |
| SC-12 | Monthly pin of unchanged history under 5% of full size | M3 | Fragment-store measurement |
| SC-13 | 100% UI ↔ SDK parity, both directions | M1 | Gate 15, continuously |
| SC-14 | Full suite green on Windows, Linux and macOS | M0 | Gate 12, continuously |
| SC-15 | Zero drift between the `.sql` files and the ORM metadata | M1 | Gate 13, continuously |
| SC-16 | `maya_delta` backend equivalence and cross-backend reads | M2 | Gate 20 |
| SC-17 | 100% of tables paginated, searchable, sortable | M0/M1 | Gate 10, continuously |

---

## 9. Risks, and where the plan answers them

| Risk | Plan's answer |
|---|---|
| **Resolution semantics are silently wrong** (§26.2) | Property-based tests over every logical type; the synthetic *messy* dataset from M3; fill reports on every run; the winning policy layer displayed per attribute (M4 exit criterion) |
| **Nested/tensor fidelity leaks** (§26.2) | Native Arrow types, axis manifests, round-trip tests for every type × every format × **both `maya_delta` backends** — M3 exit criteria |
| **The pure Delta backend is subtly wrong** *(new)* | It is never trusted on its own: one conformance suite run twice, a cross-backend round trip in both directions, loud refusal of unsupported features, and version ranges rather than literals. M2 exists as a milestone so this is not done in the margins of M3 |
| **"No migrations" bites once there is data** *(new)* | The export/recreate/import path is the *only* upgrade path, is built in M1 rather than when first needed, and is exercised every release. The schema-hash startup check makes a mismatch loud. Feature data is untouched because pins are immutable |
| **Three platforms discovered late** *(new)* | Three-OS CI on an empty repository in M0. `spawn` everywhere, `pathlib` everywhere, no `flock`, and a sandbox whose tier is declared rather than assumed |
| **The table contract erodes** *(new)* | One macro, and a crawler gate installed in M0 before the first table exists. The macro has to be good enough that nobody wants to bypass it — if someone does, that is a defect in the macro, not a reason to weaken the gate |
| **Python's concurrency ceiling** (§26.2) | Async I/O + native kernels + worker processes, benchmarked under soak at M8. Mitigated, not removed; a Rust resolution core is worth revisiting **after M4 benchmarks**, not now |
| **The platform is routed around** (§28.1) | The scratch namespace and `maya feature quick` in M3, not M8. Ceremony scales with consequence |
| **Two-store consistency on pin** (§15.3) | Saga with hash verification, reaper for orphans, nothing visible before metadata commit — with the interrupted-pin case as an M3 exit criterion |
| **Cascade pins multiply storage** (§28.4) | Content-addressed fragments in M3. SC-12 measures it |
| **Workflow policy too rigid or too loose** (§26.2) | Policy as data, edited in the UI with edit-time validation, role presets, and break-glass that is loud and audited |
| **SQLite mistaken for production** (§26.2) | UI banner, documented ceiling, and a refusal to run `environment: prod` on SQLite |
| **Scope creep into training and serving** (§26.2) | Settled as D-4. The warrant boundary is what keeps MAYA coherent |
| **An empty catalog** (§28.11) | Not an engineering risk. Named in §4.4 as a sponsorship decision because no amount of platform fixes it |

---

## 10. Working the plan

- **Branch.** All work on `develop`. Promote to `main` only when the suite is green on all three platforms and both backends, the counts are stamped, built artifacts are newer than their sources, and the tree is clean.
- **Commits.** One coherent change per commit, message stating what changed and why. **No assistant attribution trailers** — enforced by the `commit-msg` hook from M0.
- **ADRs.** Every architectural decision numbered in `docs/adr/` and referenced from the code it governs. The fourteen calls in §4 become ADR-004 onward in M0.
- **This document.** A living plan. When a milestone lands, its exit criteria move into the README's *What's shipped* section **with the test that proves each one**, and the milestone section here is marked done rather than deleted — the record of what was promised is part of the evidence.

---

**MAYA** — Model &amp; AI Lifecycle Assurance · *Evidence, not assertion.* · © 2026 Ashutosh Sinha
