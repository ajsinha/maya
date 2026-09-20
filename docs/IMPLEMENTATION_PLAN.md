# MAYA — Implementation Plan

**From an empty repository to the platform in [`MAYA_Requirements_and_Design.md`](MAYA_Requirements_and_Design.md).**
Version 1.1 · 2026-09-17 · Ashutosh Sinha

> **Revision 1.1.** All eight open decisions are closed (§4). Six further calls are folded
> in: no database migrations, `maya_delta` as the lakehouse layer, Windows/Linux/macOS
> parity, Bootstrap 5 + jQuery on a Harvard Crimson system, the universal table contract,
> and workflow managed in the UI. `maya_delta` is now a milestone of its own (M2) and the
> milestones after it are renumbered.
>
> **Revision 1.2.** `maya_delta` generalised: specification §13.4 now states the dependency-seam
> policy for the whole stack — twenty seams, three polarities, and the list of what is
> deliberately *not* proxied. The seam resolver lands in M0 and SC-18 is added.
>
> **Status at version 0.3.0 (2026-09-19).** Each milestone below now carries a *Status*
> note: what it delivered, with the tests, and what it promised and did not deliver.
> Nothing promised has been deleted — the record of what was promised is part of the
> evidence. The delivered capabilities, each with the test that proves it, are in the
> README's [*What's shipped*](../README.md#whats-shipped). Three things this plan asks
> for are **out of scope by the owner's decision**, not pending: Windows and macOS (only
> Linux is exercised, so SC-14 and gate 12 are not met), testing the assistant against
> the live Claude API (its Claude provider is verified against a stub only), and a
> dedicated benchmark host (SC-3 is not met reliably on the shared workstation).

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

*As of version 0.3.0 (2026-09-19):* the spine runs end to end through the UI, API, SDK and CLI, with 1,149 tests on Linux over SQLite and PostgreSQL 16, 17 and 18. M0–M7 are delivered with the exceptions each *Status* note names; M8 is delivered in part. The paragraph above is kept as the starting point it describes.

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
| A proxied package is imported only inside its own seam | §13.4.3 | `tools/ci/seam_imports.py`, non-overridable |
| Every Type A seam's suite runs on both backends; every Type B seam is byte-compared | §13.4.3, SC-18 | CI matrix |
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

Two layout decisions are recorded as ADRs because a decision that is not written down gets re-litigated every quarter ([ADR-001](adr/ADR-001-package-layout.md) and [ADR-003](adr/ADR-003-maya-delta-beside-maya.md), in [`docs/adr/`](adr/README.md)):

- **ADR-001 — everything under `maya/`, not at the repository root.** DishtaYantra puts `core/`, `routes/` and `web/` at the root. MAYA does not, because `maya.persistence`, `maya.web` and `maya.sdk` are named import-boundary units (§13, §14, §16) and `pip install maya-sdk` must deliver a client of a few megabytes with no server in it (§18.2.3). Both need a real package root. Everything *inside* the package follows DishtaYantra's idioms unchanged.
- **ADR-003 — `maya_delta` beside `maya`, not inside it.** It holds no MAYA domain knowledge, is reachable only through the `LakeStore` port of §25, and must be independently testable and swappable. Burying a general-purpose Delta implementation inside the product package would make it neither.

---

## 4. Decision register

**All eight open decisions were closed on 2026-09-17, before any code.** Six further calls were taken at the same time. Each is a numbered ADR in [`docs/adr/`](adr/README.md) — due in M0, written after 0.3.0; this table and specification §26.3 are the register.

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

> **Status at 0.3.0 — delivered, except the three-platform parts and three deliverables.** The
> package, `run_maya_web.py`, the configuration, the seam resolver (`maya/core/backends.py`,
> including `tzdb` and `procstat`), the Type B seams, the `maya_delta` seam, the vendored
> shell, both hooks and the gates in `tools/ci/` all exist; each gate is seen to fail on a
> planted violation (`tests/test_api_and_gates.py`). **Not delivered:** `public_symbols.py`
> and `cycle_check.py`; and the CI job that runs the suite with every Type A seam pinned to
> its fallback. The `docs/adr/` records, due here, arrived after 0.3.0: ADR-001 to ADR-028
> in [`docs/adr/`](adr/README.md). The code does not yet reference them. **Out of scope by decision:** CI on Windows and
> macOS, and with it the cross-platform byte comparison of the Type B seams — only Linux
> is exercised, and there is no hosted CI.
>
> **Since 0.3.0:** delivered. `public_symbols.py` and `cycle_check.py` are gates, and
> `gates.py --fallback` runs the whole suite with every Type A seam pinned to its
> fallback (1,150 passed). Each rung of the ladder is proven to catch a planted fault
> (`tests/test_gate_ladder.py`).

*Nothing about the product. Everything about making the next eight milestones checkable.*

**Deliverables**

- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`; `.venv` on Python 3.13.15 per `.python-version`.
- `maya/core/version.py` — `VERSION` (the current release), `BUILD_DATE`, `APP_NAME`, and the per-release highlights log.
- Package skeleton: every directory in plan §3 with an `__init__.py` and a module docstring stating what belongs in it **and what does not**.
- **`run_maya_web.py`** — the startup script, complete before there is a server to start: `__main__` guard, `multiprocessing.set_start_method('spawn', force=True)` at module level, the banner (version, build date, Python, platform, DB dialect, `maya_delta` backend, sandbox tier), logging configuration, signal and `atexit` drain handlers, config path and `--key=value` overrides.
- **Configuration**, DishtaYantra-style: `config/application.yaml` with `app`, `server`, `logging`, `db`, `storage`, `auth`, `sandbox`, `lake` sections and no secret; `${VAR:default}` substitution; `config/application.local.yaml` git-ignored and loaded straight after.
- **`maya/core/backends.py` — the one seam resolver** (§13.4). Every dependency seam is settled here, once, at startup; the result is reported in the banner, on the health page and in `/readyz`, and any seam can be pinned by configuration so CI can exercise the portable path deliberately rather than by accident of what happens to be installed. There is no `try: import X except ImportError` anywhere else in the codebase, and a gate enforces that.
- **The cheap seams, complete in M0** because they are load-bearing everywhere and trivial to build: `core/djson` (orjson → stdlib), `core/tzdb` (system → `tzdata`, a **hard requirement on Windows**), `core/compress` (zstd → zlib), `core/procstat` (psutil → per-platform). Each with its suite run twice, once per backend.
- **The Type B seams, authoritative from the first line**: `core/canonical` (§7.2 Rule 4) and `core/chunker` (§29.3). These define content hashes, so MAYA's pure implementation *is* the specification and any accelerator must match it byte for byte. Building them first — before anything hashes — is what keeps that inversion true.
- **`maya_delta/` skeleton**: the public API surface, backend detection, the self-check, the configuration pin, and startup reporting. The implementations come in M2; what lands here is the *seam*, so nothing above it ever imports `deltalake` directly.
- **Vendored UI shell**: Bootstrap 5, jQuery, Cytoscape.js, CodeMirror 6, KaTeX, pinned under `static/vendor/`. *As built: CodeMirror 5, because CodeMirror 6 ships as ES modules that need a bundler (specification revision 2.2, §17).* `static/css/tokens.css` with the Harvard Crimson set of §16.6. `_macros/table.html` and `static/js/table.js`.
- `.githooks/commit-msg` refusing assistant attribution trailers; `.githooks/pre-commit` running the fast gates.
- **`tools/ci/`** — `gates.py` as the single entry point (**Python, not shell**, so it runs on all three platforms), plus `file_size.py`, `import_boundaries.py`, `seam_imports.py`, `public_symbols.py`, `cycle_check.py`, `gen_schema.py`, `table_contract.py`, `contrast.py`, `version_single_source.py`, `no_secrets.py`.
- **CI on three operating systems from the first commit** — Windows, Linux, macOS — with SQLite everywhere and PostgreSQL at least on Linux.
- `docs/adr/` — ADR-001 package layout, ADR-002 branch and release workflow, ADR-003 `maya_delta` placement, and ADR-004…ADR-011 recording the eight decisions of §4.1.
- A rewritten `.gitignore`: the retained one still encodes the old build's rules and should be pruned to what MAYA actually produces. `.gitattributes` normalising line endings.

**Exit criteria**

- `python tools/ci/gates.py` runs green on an empty package **on all three operating systems**.
- **Each gate is demonstrated to fail** on a deliberately planted violation — a 1,600-line file, a `sqlalchemy` import in `maya/services/`, a `maya.persistence` import in `maya/web/`, a raw `<table>` in a template, a token pair below 4.5:1, a second hard-coded version string. A gate nobody has seen fail is a gate nobody knows works.
- `python run_maya_web.py --help` runs and prints the banner on all three platforms.
- `git commit` with a `Co-Authored-By: Claude` trailer is refused by the hook.
- Starting with a secret in `config/application.yaml` fails a test.
- **The seam resolver reports every seam** in the banner and on `/readyz`, and each seam can be forced to its fallback by configuration — proved by a CI job that pins every Type A seam to its fallback and runs the suite green.
- **Type B is byte-compared, not merely tested**: `core/canonical` and `core/chunker` produce identical output on Windows, Linux and macOS, with the pure implementation's output committed as the fixture.
- An `import orjson` outside `core/djson` fails the seam-import gate.

---

### M1 — Foundation: identity, authorization, persistence, jobs, audit, chrome · **L**
*Specification Phase 0*

> **Status at 0.3.0 — delivered, except the platform and fallback criteria.** DB and SSO
> sign-in (OIDC and SAML 2.0, tested against Keycloak 26.4), the generated schema and its
> drift gate, the estate round trip, the tamper-detecting hash chain, the stored-KDF
> rehash, the named crypto refusal, the authorization tests and the table contract are
> proved by the tests the README's *What's shipped* names. The suite runs green on SQLite
> and PostgreSQL 16, 17 and 18 (SC-10). **Not delivered:** the full M1 suite with every
> Type A seam pinned to its fallback. **Out of scope by decision:** all three platforms
> (SC-14). **Since 0.3.0:** the fallback matrix runs the whole suite (gate 11b).

**Deliverables**

- `maya/persistence/`: engine and dialect selection, `UnitOfWork`, `types.py` (`PortableJSON`, `PortableUUID`, UTC normalisation, `NUMERIC(38,12)` mapped to text-and-convert on SQLite — **never float**), `locks.py` (PG advisory locks, SQLite write mutex).
- **The schema, generated** (§14.3): typed SQLAlchemy metadata in `models/` as the single source; `tools/ci/gen_schema.py` emitting `schema/postgresql.sql` and `schema/sqlite.sql`; the drift gate; the schema-hash stamp and the startup refusal on mismatch.
- **`maya admin init-db` / `export-estate` / `import-estate`** — the *only* upgrade path (§4.3), built now and exercised from now on.
- Schema for `users`, `roles`, `user_roles`, `groups`, `group_members`, `namespaces`, `grants`, `audit_events`, `jobs`, `schema_meta`.
- `maya/security/`: `AuthProvider` with DB and OIDC/SAML2 implementations behind one config switch; sessions with `HttpOnly`/`Secure`/`SameSite=Lax` and CSRF; API keys shaped `maya_<env>_<key_id>_<secret>`, stored hashed, shown once.
- **`core/kdf`** (§13.4): Argon2id preferred, `hashlib.scrypt` then PBKDF2-HMAC-SHA512 as fallbacks, with **the algorithm and its parameters stored alongside every hash** rather than assumed globally — so verification survives a change and a login transparently rehashes to the strongest available. A password store that assumes one KDF can never change it.
- **`core/crypto`** (Type C): one API over `cryptography`, PKCS#11/HSM or cloud KMS, and a **refusal** naming the wanted backend when none is present. There is no pure-Python signer and there will not be one.
- **`core/search`**: PostgreSQL `tsvector` / SQLite FTS5, detected at startup — **FTS5 is not compiled into every Python's bundled SQLite** — with MAYA's own inverted index as the fallback. *As built: MAYA's own inverted index is the only backend, identical on both databases — ranked, prefix-matched, every term required, filtered by read permission and kept current in the writing transaction (`maya/persistence/search_index.py`, `tests/test_search.py`). Neither `tsvector` nor FTS5 is used; 100,000 objects search at p95 0.16 s (`docs/BENCHMARKS.md`). Specification §13.4.2, revision 2.2.*
- **SAML as a declared capability**: a deployment configured for SAML on a host without `xmlsec` fails at *startup* with the package named, not at the first person's login.
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
- A password hashed under Argon2id verifies after the seam is forced to scrypt, and logging in rehashes it — proved in one test, because this is the migration that a stored-KDF design exists to make possible.
- Removing the crypto backend produces a **named refusal at startup**, not a traceback at the first seal.
- The full M1 suite runs green with **every Type A seam pinned to its fallback**.
- `/healthz`, `/readyz`, and a system health page naming every dependency, the schema hash, the `maya_delta` backend and the sandbox tier.

---

### M2 — `maya_delta` · **L**
*New milestone. Specification §7.4*

> **Status at 0.3.0 — delivered on Linux.** The conformance suite passes on both backends,
> the cross-backend round trip holds both ways, and unsupported protocol features are
> refused by name (`tests/test_maya_delta.py`, SC-16); compaction and vacuum followed
> (`tests/test_lake_maintenance.py`). **Not delivered:** the lint check forbidding literal
> protocol versions (**since 0.3.0:** a gate, `protocol_literals.py`). The concurrent-writer race has run on ext4 only; NTFS and APFS are
> out of scope with Windows and macOS.

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

> **Status at 0.3.0 — delivered.** SC-1, SC-11 and SC-12 each have a named test
> (`tests/test_features.py`); every logical type round-trips in every format
> (`tests/test_resolution_algebra.py`); a deliberately leaky set is refused
> (`tests/test_warrants.py`); the scratch path is one command (`tests/test_cli.py`). **Not
> proved as written:** `maya feature quick` is tested, not timed; an interrupted pin is
> tested as ending `failed` rather than stuck (`test_an_unexpected_error_leaves_the_pin_failed_not_stuck`),
> not as reclaimed by a reaper mid-write.

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

> **Status at 0.3.0 — delivered, with two criteria built but not proved by a test.** The
> tensor round trip, the cascade rollback and the precedence layers are tested; since
> 0.3.0 the namespace's `materialize_policy` (`always`, `on_demand`, `never`) decides
> where a pin's output is kept, D-1's default unchanged (`tests/test_materialization.py`).
> The cascade test injects its quality failure into a two-member set, not at member 39
> of forty. Equivalence detection at creation and withheld attributes are in the code
> (`maya/services/featuresets.py`) with no test that proves either.

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

> **Status at 0.3.0 — delivered.** Every non-compliant route refused, SoD by preset,
> governed policy activation, byte-identical YAML, loud break-glass
> (`tests/test_workflow_and_estate.py`, `tests/test_workflow_matrix.py`); a change
> rehearsed in a workspace and approved as its merge (`tests/test_workspaces.py`).

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

> **Status at 0.3.0 — delivered on Linux, SC-9 not measured.** The formula IR, the
> validation ladder one rung per test, true Tectonic builds (a real PDF without the draft
> watermark — its extracted text is not asserted), and composite maturity capping are
> tested (`tests/test_formula.py`,
> `tests/test_sandbox.py`, `tests/test_sandbox_linux.py`, `tests/test_typeset.py`).
> **Not delivered:** SC-9, timed with a real person. PDFs on three platforms, and the
> escape tests on the `moderate` and `minimal` tiers, are out of scope with Windows and
> macOS.

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

> **Status at 0.3.0 — delivered, SC-2 not rehearsed.** The checksum cycle and
> `unverified_data`, covenant suspension failing closed, blind scoring, and a bundle that
> verifies offline and fails after one byte changes are tested (`tests/test_warrants.py`,
> `tests/test_sdk_modes.py`, `tests/test_cli.py`). **Not delivered:** SC-2 against a
> deliberately aged warrant (**since 0.3.0:** rehearsed — a warrant aged two years is
> reproduced from its bundle, byte-identical). The covenant test runs in process, not against a running
> server; the offline verification has run on Linux only.

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

> **Status at 0.3.0 — delivered in part.** Built: SDK record/replay and
> `maya.offline(bundle)`, server-side paging, several web processes on one node, the CLI,
> and the benchmarks in `docs/BENCHMARKS.md` — SC-4, SC-5 and 100k-object search pass,
> SC-3 is not met reliably, and most of §24.3 is not measured. **Not delivered:**
> `maya.testing` fakes and the UI suite run against them; the deadlock probes; the restore
> drill; the external security review; the synthetic market dataset of §23. The runbooks
> arrived after 0.3.0, in [`docs/runbooks/`](runbooks/README.md): nine of §20's procedures,
> schema rebuild and `maya_delta` fallback among them, with the rest named there as
> missing. The restore drill's procedure is one of them and was rehearsed on a throwaway
> estate; the drill itself has not been performed on a real deployment, nor its result
> recorded.
> The exit criterion *all eighteen success criteria met* is therefore not met (plan §8).
>
> **Since 0.3.0:** delivered — `maya.testing` (a throwaway platform with seeded users and
> SDK clients, and a pytest plugin), the synthetic market dataset, the concurrency and
> deadlock probes on SQLite and PostgreSQL, the rest of §24.3 measured by
> `tools/bench/bench_capacity.py` ([BENCHMARKS](BENCHMARKS.md#capacity-243)), and **the
> restore drill, performed on SQLite and PostgreSQL 17 and recorded** in
> [its runbook](runbooks/restore-drill.md#5-record-the-result) — which meets this
> milestone's criterion for the procedure; a deployment's own first drill remains its
> operator's. Still not delivered: the external security review, and SC-9.
> A dedicated benchmark host is out of scope by decision.
>
> **Since the specification audit** ([docs/audit](audit/spec-audit-2026-09-19.md)), which read
> the specification against the code requirement by requirement, 27 of its 36 ranked gaps are
> closed with tests and 3 are partly closed. The plan's milestones are not the whole
> specification, and the audit is the list of what the specification asks for beyond them;
> read it rather than this section for what is left.

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

- **All eighteen success criteria measured and met**, each by a named test or benchmark (plan §8).
- The restore drill has been performed and its result recorded and visible.
- No unresolved high findings from the external review.

---

### Beyond M8 — the additive innovations

> **Status at 0.3.0 — four of five delivered, ahead of M8.** Shadow replay
> (`tests/test_workspaces.py`), licence algebra and external anchoring, with the TSA's
> signature checked when its CA is configured (`tests/test_custody.py`), the recorded
> challenger (`tests/test_assistant.py`, its Claude provider against a stub only, by
> decision), and spreadsheet import (`tests/test_spreadsheet.py`,
> `tests/test_spreadsheet_libreoffice.py`). Vendor models exist as a model kind
> (`maya/services/models.py`) with no test of their own. The plan put each behind a
> feature flag; only the challenger has one (`assistant.enabled`, on by default).

Each behind a feature flag, in roughly this order (§29.11): shadow replay (§29.2) → licence algebra and external audit anchoring (§29.6) → the recorded challenger (§29.8) → spreadsheet import (§29.9) → vendor model registration (§29.10). Shadow replay is first because it changes what a review *is*: *"this forward-fill limit change moves 3 of 11 dependent models; the PD model shifts by more than 2 bp on 0.4% of rows"* instead of a list of names.

**Delivered outside the milestones.** The research paper and the presentation decks were rewritten against this specification and version 0.3.0. They were never part of M0–M8 and were not blocked by it. The paper is `docs/research/models-as-parametric-kernels.tex`, built to `docs/research/models-as-parametric-kernels.pdf` with Tectonic, with an article version beside it and `docs/research/LICENSE` restored, so `NOTICE` resolves again; every claim it makes about MAYA is marked with the module and test that carry it, or as not in the rebuilt system. The seven decks of the previous build became three — `docs/MAYA-Executive-Briefing.pptx`, `docs/MAYA-System-Design.pptx` and `docs/MAYA-Concepts-and-Formalism.pptx` — generated by `tools/deck/` and checked for layout by `tests/test_deck_geometry.py`.

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
| 6 | **Seam imports** — a proxied package is imported only inside its own seam | M0 | **no** |
| 7 | Public-symbol count per module, dependency-cycle check | M0 | no |
| 8 | Version single-source grep | M0 | no |
| 9 | No secret in `config/application.yaml` | M0 | no |
| 10 | **Table contract** — every `<table>` from the macro | M0 | **no** |
| 11 | **Colour contrast** — every token pair ≥ 4.5:1 text, 3:1 non-text | M0 | no |
| 11b | **Fallback matrix** — the suite with every Type A seam pinned to its fallback | M0 | **no** |
| 11c | **Type B byte-comparison** — canonical and chunker output identical across platforms | M0 | **no** |
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

*At 0.3.0:* `tools/ci/gates.py` runs rungs 3, 4, 5, 6, 8, 9, 10, 11, 13 and 15 as scripts,
and with `--tests` the suite under a 90% coverage floor. Rungs 14, 16, 17, 18, 20 and 22 are
tests in that suite, and 17 needs `MAYA_TEST_PG_URL` for the PostgreSQL half; rung 24 is
`tests/test_browser.py` in headless Chrome, without screenshots. **Not built:** 1, 2, 7,
11b, 19, 21, 23 as a gate, 25 and 26 — `ruff` and `mypy` are not part of the ladder,
and benchmarks are run on demand (`tools/bench/`), not gated. Rungs 11c and 12
are out of scope by decision with Windows and macOS.

### 7.3 Two things this ladder must not be allowed to do

**A green suite at the wrong total.** A module that cannot import its dependency *skips*, and a module-level skip removes its whole file from the collected count. Install `requirements.txt` without `requirements-dev.txt` and the suite goes green at a smaller number while real coverage has silently gone. From M1 the advertised count is stamped from one source (`docs/test_counts.json`) and the pre-commit hook re-collects and fails if the total moved. **Check the total, not merely the absence of failures.** This matters more here than in DishtaYantra, because `maya_delta`'s two backends and three platforms multiply the ways a suite can quietly shrink — the stamp is per platform and per backend, not one number.

**A checker whose output is all noise.** A checker that reports hundreds of false positives trains everyone to ignore it, and would then hide the real one. Any checker added here is sampled before its number is treated as debt.

---

## 8. Success criteria, mapped

Specification §2 states eighteen. Each is met by a named test at a named milestone. A criterion with no test is a wish.

| # | Criterion | Met at | Proved by | At 0.3.0 |
|---|---|---|---|---|
| SC-1 | Byte-identical re-resolution of any pinned feature set | M3 | Gate 22, with the negative case in the same test | Met: `test_sc1_repin_is_byte_identical_and_changed_data_is_not` |
| SC-2 | Two-year-old training run reproduced in under 10 min | M7 | Bundle verify against an aged fixture | Not rehearsed against an aged warrant |
| SC-3 | 200 concurrent interactive users per API pod | M8 | Soak benchmark | **Not met reliably**: p95 0.34, 0.22, 0.43 s on a shared workstation; a dedicated host is out of scope by decision |
| SC-4 | Metadata p95 under 300 ms | M8 | Benchmark; regression-gated from M1 | Met on the workstation: worst page p95 0.18 s |
| SC-5 | 50-col × 10-year resolution under 15 s warm, 60 s cold | M8 | Benchmark on the synthetic dataset | Met on SQLite: warm p95 6.1 s with forward fill |
| SC-6 | 100% of non-UI files under 1,500 lines | M0 | Gate 3, continuously | Met: the file-size gate |
| SC-7 | Zero unauthorized accesses succeed | M1 | Gate 18, grown by every later milestone | Tested by route (`tests/test_api_contract.py`) and by transition (`tests/test_workflow_matrix.py`), not as the full role × action × state matrix |
| SC-8 | 100% of state changes audited immutably | M1 | Hash-chain suite, including the tamper case | Met: the chain and the tamper case (`tests/test_workflow_and_estate.py`), anchors (`tests/test_custody.py`) |
| SC-9 | New designer publishes a first model in under 60 min | M6 | Timed with a real person | Not measured |
| SC-10 | Full suite green on SQLite and PostgreSQL | M1 | Gate 17, continuously | Met: SQLite and PostgreSQL 16, 17, 18 |
| SC-11 | Point-in-time reconstruction after a restatement | M3 | Bitemporal suite | Met: `test_sc11_point_in_time_after_restatement` |
| SC-12 | Monthly pin of unchanged history under 5% of full size | M3 | Fragment-store measurement | Met: `test_sc12_unchanged_month_costs_under_five_percent` |
| SC-13 | 100% UI ↔ SDK parity, both directions | M1 | Gate 15, continuously | Met for SDK ↔ API: 178 endpoints |
| SC-14 | Full suite green on Windows, Linux and macOS | M0 | Gate 12, continuously | **Out of scope by decision**: only Linux is exercised |
| SC-15 | Zero drift between the `.sql` files and the ORM metadata | M1 | Gate 13, continuously | Met: the schema-drift gate |
| SC-16 | `maya_delta` backend equivalence and cross-backend reads | M2 | Gate 20 | Met on Linux: `tests/test_maya_delta.py` |
| SC-17 | 100% of tables paginated, searchable, sortable | M0/M1 | Gate 10, continuously | Met: the table-contract gate and `tests/test_browser.py` |
| SC-18 | Seam equivalence — Type A both ways, Type B byte-identical | M0 | Gates 11b and 11c, continuously | In part: the seams exist and the fallback matrix runs the whole suite (since 0.3.0); the cross-platform byte comparison is out of scope with Windows and macOS |

---

## 9. Risks, and where the plan answers them

| Risk | Plan's answer |
|---|---|
| **Resolution semantics are silently wrong** (§26.2) | Property-based tests over every logical type; the synthetic *messy* dataset from M3; fill reports on every run; the winning policy layer displayed per attribute (M4 exit criterion) |
| **Nested/tensor fidelity leaks** (§26.2) | Native Arrow types, axis manifests, round-trip tests for every type × every format × **both `maya_delta` backends** — M3 exit criteria |
| **A seam's two sides silently disagree** *(new)* | The polarity rule of §13.4.1: anything near a hash is Type B, where MAYA's own implementation is authoritative and an accelerator that differs is a defect, byte-compared in CI on every platform. A seam on the hash path whose sides can disagree does not degrade gracefully — it makes SC-1 pass on each machine separately while being false across them |
| **A fallback path nobody ever runs** *(new)* | Gate 11b runs the whole suite with every Type A seam pinned to its fallback. A fallback exercised only when a wheel happens to be missing is a fallback discovered broken by a customer |
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
- **ADRs.** Every architectural decision numbered in `docs/adr/` and referenced from the code it governs. The calls in §4 are ADR-004 to ADR-018 in [`docs/adr/`](adr/README.md) — the eight decisions as ADR-004 to ADR-011, the lakehouse call recorded once with D-6, and SQLite-by-default and the one startup script given records of their own — and the later decisions of revisions 2.2 and 2.3 and version 0.3 continue the sequence to ADR-028. The second half of the rule is not yet kept: the code cites D-numbers in a few places and ADR numbers nowhere.
- **This document.** A living plan. When a milestone lands, its exit criteria move into the README's *What's shipped* section **with the test that proves each one**, and the milestone section here is marked done rather than deleted — the record of what was promised is part of the evidence. At 0.3.0 that section is [README → What's shipped](../README.md#whats-shipped), and each milestone above carries its *Status* note.

---

**MAYA** — Model &amp; AI Lifecycle Assurance · *Evidence, not assertion.* · © 2026 Ashutosh Sinha
