# MAYA — Implementation Plan

**From an empty repository to the platform in [`MAYA_Requirements_and_Design.md`](MAYA_Requirements_and_Design.md).**
Version 1.0 · 2026-09-17 · Ashutosh Sinha

---

## 0. What this document is

The specification says **what** MAYA is. This says **in what order it gets built, and how we know each piece actually works** — because on a platform whose entire value proposition is *evidence, not assertion*, a milestone that cannot be demonstrated has not landed.

Three jobs:

1. **Sequence.** Eight milestones (M0–M7), each with file-level deliverables and exit criteria that are *executable*, not adjectival. "Resolution works" is not an exit criterion; "a feature is pinned twice and the two content hashes are byte-identical" is.
2. **Gates.** The CI ladder, and which rung is installed at which milestone. Gates land *with* the capability they guard, never after it — a boundary rule added to a codebase that has already violated it is a refactor, not a gate.
3. **Decisions.** Eight open questions (spec §26.3) that must be answered before M2 code starts. They are listed in §4 with a recommendation each and, more usefully, with **what changes if the answer goes the other way**.

Effort tags: **S** (days) · **M** (a week or two) · **L** (weeks) · **XL** (a quarter or more). They are sizing, not dates.

Section references like §29.1 point into the specification unless they say "plan §".

---

## 1. Where we are

The repository was emptied on 2026-09-17 and restarted from the specification. It holds the specification, this plan, the brand, and the legal files. There is no package, no test, no server.

Everything that follows is therefore greenfield, which is worth saying plainly because it is the one and only time some of these decisions are cheap. Bitemporality, content-addressed storage and the two import boundaries are all *free* today and *a rewrite* in six months. The plan is shaped around that asymmetry more than around anything else.

---

## 2. Ground rules

These are not negotiated per milestone. They hold from the first commit.

### 2.1 Inherited from the estate

MAYA is a sibling of DishtaYantra and follows its conventions, so a developer moving between the two repositories finds the same idioms in the same places. Concretely:

| Rule | Detail |
|---|---|
| **Authorship** | **Never add an assistant attribution trailer** to a commit message — no `Co-Authored-By: Claude`, no `Generated with [Claude`. Authorship of this repository is Ashutosh Sinha's alone. MAYA's existing history carries none; install a `commit-msg` hook in M0 so it cannot regress |
| **Branches** | `develop` is where all work happens and is the branch to keep checked out. `main` is production and is *promoted to*, deliberately, never synced on a schedule. `main` sitting behind `develop` is normal and is not drift to close |
| **Version** | `maya/core/version.py::VERSION` is the single authority. Every module, template, banner and document reads it at runtime; a version string hard-coded anywhere else is a copy that will rot |
| **Config** | `config/application.yaml` is **tracked and carries no secret**. `config/application.local.yaml` is git-ignored and is where a real secret belongs. A test enforces the first half of that sentence |
| **No build pipeline for the UI** | Jinja2 templates plus vendored, pinned JavaScript. No bundler, no node toolchain at runtime. The app renders air-gapped |
| **Two requirements files** | `requirements.txt` is what a deployment needs. `requirements-dev.txt` is what the documented workflows need. Installing only the first must not silently produce a smaller green suite — see plan §7.4 |
| **Advertised numbers are derived** | A count, a list or a limit quoted in a second place will drift. Compute it from the same source the renderer uses, and stamp it from one file |

### 2.2 The failure mode to design against

DishtaYantra's hard-won lesson, and MAYA is if anything more exposed to it: **artifacts that build, validate and look right while being wrong.** A pin whose hash is computed over the wrong canonicalization still hashes. A leakage certificate whose check is inverted still signs. A fill report that counts the wrong rule still renders.

Three habits, applied to every milestone below:

- **Assert the rendered artifact, not the intent.** Check the bytes that came back, the served HTTP status, the text extracted from the PDF — not that the code meant to produce them.
- **Write the counterfactual.** A test that cannot fail is worth nothing. When fixing a defect, confirm the new test fails against the old code before you keep it.
- **Derive, never restate.**

For MAYA specifically there is a fourth, because of what the product claims: **every reproducibility guarantee needs a negative test.** It is not enough that two pins of unchanged data hash the same; a pin of *changed* data must hash *differently*, and the test that proves it must be the same test.

### 2.3 From the specification

| Rule | Source | Gate |
|---|---|---|
| No non-UI source file over 1,500 non-comment lines | §22.1 | `tools/ci/file_size.py`, non-overridable |
| Nothing outside `maya.persistence` imports `sqlalchemy` | §14 | import-linter, non-overridable |
| Nothing under `maya.web` imports deeper than `maya.sdk` | §13, §16 | import-linter, non-overridable |
| Every endpoint has an SDK method and vice versa | §18.2.1 | `tools/ci/sdk_parity.py` |
| `mypy --strict` on `domain/` and `services/` | §22.2 | CI |
| Functions under 50 lines, complexity under 10 | §22.1 | `ruff` |
| No silent config defaults | §22.2, §24.2 | startup validation + a test |
| Full suite green on SQLite **and** PostgreSQL | §2 SC-10 | CI matrix |

§28.10 is right that a line count is a proxy and is defeatable by a 1,499-line `helpers.py`. The line limit stays as a cheap smoke alarm; the gates that actually constrain structure are the import boundaries, a maximum public-symbol count per module, cyclomatic complexity and a dependency-cycle check. **A module that fails those fails the build regardless of its length.**

---

## 3. Package layout, and one deliberate divergence

The target tree is specification §22.3, §14, §16 and §18.2.6 combined:

```
maya/                          # repository root
├── maya/                      # the importable package
│   ├── core/version.py        # VERSION, BUILD_DATE, APP_NAME — the only authority
│   ├── domain/                # entities, value objects, policies, state machines. No I/O
│   ├── ports/                 # protocols the domain requires of the outside world
│   ├── services/              # use cases, transaction boundaries, orchestration
│   ├── resolution/            # planner, kernels, rules, grids, shapes, fill reports
│   ├── storage/               # delta, object store, fragment store, cache adapters
│   ├── persistence/           # engine, session/UoW, models, repositories, mappers,
│   │                          #   types, locks, migrations, seed — SQLAlchemy lives here
│   ├── workflow/              # state machine, policies, pluggable checks, campaigns
│   ├── security/              # auth providers, the can() evaluator, the sandbox
│   ├── api/                   # FastAPI routers and schemas
│   ├── web/                   # templates, static, routes — an SDK client, nothing deeper
│   ├── jobs/                  # queue, workers, handlers, reaper
│   ├── sdk/                   # client, config, auth, transport, generated, resources,
│   │                          #   handles, io, cache, errors, testing
│   ├── cli/                   # the `maya` command
│   └── config/  observability/
├── config/                    # application.yaml, application.local.yaml (ignored)
├── tests/
├── tools/ci/                  # the gate scripts
├── docs/                      # spec, this plan, adr/, design/, runbooks/, research/
└── assets/logo/
```

**The divergence.** DishtaYantra puts `core/`, `routes/` and `web/` at the repository root. MAYA puts everything under a `maya/` package instead. This is deliberate and the specification requires it: `maya.persistence`, `maya.web` and `maya.sdk` are named as import-boundary units (§13, §14, §16), and `pip install maya-sdk` must deliver a client of a few megabytes with no server in it (§18.2.3). Both need a real package root. Everything *inside* the package follows DishtaYantra's idioms unchanged — route classes taking their dependencies in `__init__`, a Flask-shaped compat layer over FastAPI for `render`/`flash`/`redirect_to`, templates under `web/templates/` with shared chrome and macros, and `version.py` as the single source of truth.

**Recorded as ADR-001** in M0, because a layout decision that is not written down gets re-litigated every quarter.

---

## 4. Decisions that block M2

Specification §26.3 lists six open decisions plus two that arrive with the algebra. **All eight should be answered before Phase 1 code starts.** Each is cheap now. The first two and the last are the expensive ones to reverse.

| # | Decision | Recommendation | What changes if it goes the other way |
|---|---|---|---|
| D-1 | **Feature set pin materialization default** — always materialize the resolved frame, or replay from member pins? | **Always.** Reproducibility over disk; it is the difference between *"we can probably reproduce it"* and *"here are the bytes"* | Replay needs the resolution planner to be *provably* deterministic across engine versions, which is a much stronger claim than hashing bytes. It also moves cost from pin time to every read |
| D-2 | **Pin uniqueness** — is a second pin with the same name and a different date a new pin, or a new version of a **pin series**? | **A pin series**, so "the month-end series" is a browsable object | Changes the `feature_pins` key and every URI that addresses a pin (`#eom_2026_03`). Changing it after pins exist means rewriting sealed references — which sealing forbids. **Decide before M2** |
| D-3 | **Non-causal fill inside training sets** — hard block, or justified override? | **Override with written justification**, surfaced on the warrant and in the leakage certificate | A hard block is simpler and will be routed around (§28.1). An override that is *invisible* is worse than either |
| D-4 | **Model runtime in v2.0** — does MAYA execute execution warrants? | **No**, per §2 — with one exception already conceded: §29.4 blind scoring, which is narrow and bounded | Changes the worker fleet, the sandbox design and the security model materially. §28.5 assumes it stays out; decide now, not at M6 |
| D-5 | **Namespace granularity** — per desk, per asset class, or per team? | **Per team**, nesting one level | Determines quota, recertification scope and export control. Cheap to change early, painful once grants exist |
| D-6 | **Delta engine** — `delta-rs` only, or optional Spark for very large pins? | **`delta-rs` only.** No JVM is a feature | Spark brings a cluster back into a design whose whole point is that it does not need one |
| D-7 | **Default parent binding for `extends`** — `pinned` or `tracking`? | **`pinned` by default**, `tracking` opt-in per object and **blocked outright in production namespaces** | `tracking` propagates upstream fixes automatically but means a child's behaviour changes without the child being touched — which is exactly the drift MAYA exists to remove |
| D-8 | **Composite parameter granularity** — one parameter set per composite namespaced by member alias, or independently versioned per-member sets rolled up at seal? | **One per composite.** It makes the composite reproducible as a single unit | Per-member sets are more flexible for reuse and much harder to reproduce atomically. Affects the `parameter_sets` and `composite_members` schema |

Two further calls are wanted early but do not block:

- **SoD preset for the first namespaces** — *Small team* (3 roles), *Standard* (6) or *Regulated* (all 8, strict) (§28.9). Ships as a preset either way; the question is only what the seeded namespaces get.
- **Who seeds the first two namespaces** (§28.11). The platform cannot create its own critical mass of curated features, and an empty catalog is an empty shop. This is a sponsorship question, not an engineering one, but it decides whether M7 lands into use or into silence.

---

## 5. The sequencing law

Most of this plan can be reordered under schedule pressure. **Three things cannot**, and the specification is explicit about why (§26.1, §29.11).

| One-way door | Must land in | Why it cannot be retrofitted |
|---|---|---|
| **Bitemporality** (§5.1, §29.1) | **M2**, in the first migration | Two columns, a second index dimension and a hash that covers them. Adding it later rewrites every table, every pin and every content hash in the system. Without it, a vendor restatement corrupts backtests silently and nothing in the system can detect it |
| **Content-addressed materialization** (§7.1, §29.3) | **M2**, in the first write path | A pin written as an opaque copy cannot be de-duplicated afterwards without rewriting sealed data, which sealing forbids. Without it, forty features pinned monthly for three years is tens of terabytes of near-identical bytes, and the quota becomes a reason not to pin — defeating the design |
| **Workspaces** (§28.3) | **M4**, with the workflow engine | Approval-as-merge is hard to retrofit onto an approval-as-button design. Every review surface built in M4 assumes it |

A fourth is softer but real: **the scratch namespace** (§28.1). Governance that is not the path of least resistance is governance nobody uses, and a quant with a deadline opens a notebook. The plan therefore builds `maya feature quick <file.csv>` — zero ceremony, typed and resolvable in one command — **in M2 alongside the governed path**, not in M7 as polish. The first five minutes must be faster than a notebook before the governed path is worth anyone's time.

Everything else in §28 and §29 is additive and sits behind a feature flag.

---

## 6. Milestones

### M0 — Repository skeleton and the gate ladder · **S**

*Nothing about the product. Everything about making the next seven milestones checkable.*

**Deliverables**

- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`; `.venv` on Python 3.13.15 per `.python-version`.
- `maya/core/version.py` — `VERSION = "0.1.0"`, `BUILD_DATE`, `APP_NAME`, and the per-release highlights log. Every other version string reads from here.
- Package skeleton: every directory in plan §3 with an `__init__.py` and a module docstring stating what belongs in it and what does not.
- `config/application.yaml` with `app`, `server`, `logging`, `db`, `storage`, `auth` sections; no secret; `${VAR:default}` substitution; `config/application.local.yaml` git-ignored.
- `.githooks/commit-msg` refusing assistant attribution trailers; `.githooks/pre-commit` running the fast gates. `git config core.hooksPath .githooks` documented in the README.
- `tools/ci/` — `file_size.py`, `import_boundaries.py` (import-linter contracts for both boundaries, written now while there is nothing to violate), `public_symbols.py`, `cycle_check.py`, `gates.sh` as the single entry point.
- `.github/workflows/ci.yml` running the ladder of plan §7.
- `docs/adr/ADR-001-package-layout.md`, `ADR-002-branch-and-release-workflow.md`.
- A rewritten `.gitignore`: the retained one still encodes the old build's rules (`docs/examples/*.xlsx`, tutorial filenames, `sdk/java/target`) and should be pruned to what MAYA actually produces.

**Exit criteria**

- `bash tools/ci/gates.sh` runs green on an empty package, and **each gate is demonstrated to fail** on a deliberately planted violation — a 1,600-line file, a `sqlalchemy` import in `maya/services/`, a `maya.persistence` import in `maya/web/`. A gate nobody has seen fail is a gate nobody knows works.
- `git commit` with a `Co-Authored-By: Claude` trailer is refused by the hook.
- The version string appears in exactly one file, proved by a grep test.

---

### M1 — Foundation: identity, authorization, persistence, jobs, audit · **L**
*Specification Phase 0*

**Deliverables**

- `maya/persistence/`: engine and dialect selection, `UnitOfWork`, `types.py` (`PortableJSON`, `PortableUUID`, UTC normalization, `NUMERIC(38,12)` mapped to text-and-convert on SQLite — **never float**), `locks.py` (PG advisory locks, SQLite write mutex), Alembic scaffolding, `seed.py`.
- Schema for `users`, `roles`, `user_roles`, `groups`, `group_members`, `namespaces`, `grants`, `audit_events`, `jobs` (spec §30 Appendix A).
- `maya/security/`: `AuthProvider` protocol with DB and OIDC/SAML2 implementations behind one config switch; Argon2id hashing; sessions with `HttpOnly`/`Secure`/`SameSite=Lax` and CSRF; API keys shaped `maya_<env>_<key_id>_<secret>`, stored as Argon2id hashes, shown once.
- `can(principal, action, object) -> Decision` — the **single** authorization function, with the §11.2 resolution order and the role ceiling. Nothing in the UI, API, SDK or CLI bypasses it.
- Append-only, hash-chained audit (§19). Each row carries the previous row's hash.
- `maya/jobs/`: the queue (PG `SKIP LOCKED`, SQLite in-process behind the same interface), worker loop, idempotency keys, cooperative cancellation, retry with backoff, dead-letter, the orphan reaper.
- `maya/api/` + `maya/sdk/` + `maya/web/` end to end for exactly one thing: log in, see an empty catalog, list your jobs. Thin, but it proves the whole stack including both import boundaries and the SDK-parity gate.
- Bootstrap: `admin` / `maya-dev-admin` with `must_change_password`, and a **refusal to start** outside dev unless `allow_default_admin_password: true`.

**Exit criteria**

- A user logs in over SSO *and* over DB auth, sees an empty catalog, and every authentication event is in the audit log.
- **The authorization matrix suite exists and is green**: every role × every action × every object state, with **zero unexpected allows** (SC-7). This suite grows with every later milestone and never shrinks.
- Full test suite green on **both** SQLite and PostgreSQL (SC-10), in CI, as a matrix.
- The hash chain is verified by a test that **tampers with a row and proves detection** — the negative case, not just the positive one.
- SDK-parity and both import-boundary gates are live and enforced.
- `/healthz`, `/readyz`, and a system health page naming every dependency and the schema version.

---

### M2 — Features, bitemporal and content-addressed · **XL**
*Specification Phase 1 · contains two of the three one-way doors*

**Deliverables**

- `maya/domain/feature.py` and friends: `Feature`, `FeatureVersion`, `FeaturePin`, `Schema`, `SourceBinding`, `ResolutionPolicy`, `Derivation`, `InheritanceLink`.
- **Bitemporal from the first migration** (§29.1): `event_time` and `knowledge_time` on every feature row, the second index dimension, and both covered by the definition and content hashes. A restatement writes a new knowledge-time row and never overwrites.
- `maya/resolution/`: the planner, the grid (`as_is`, `calendar`, `union`, `intersection`), all eleven rules with `limit` and `max_age` bounds, non-causal marking and propagation, and the **fill report** on every run.
- Source drivers as registered plugins (§25): `sql`, `csv`, `parquet`, `json`, `delta`, `derived`, `python`. Content-addressed uploads.
- The expression language and its Arrow-kernel compiler, shared by transforms, filters, ACL row filters and workflow checks (§17.3) — one grammar, learned once.
- Quality contracts (§5.5) that **block** a pin rather than warning.
- **Content-addressed materialization** (§29.3): fragments bounded by a rolling hash over the index — *not* by row count, or one inserted row invalidates everything downstream — a fragment index, a pin as a manifest, and a garbage collector provably safe against sealed pins.
- Canonical hashing (§7.2 Rule 4): schema sorted by name, rows sorted by index, IEEE-754 floats, nested values in declared order. Over the canonical representation, never over file bytes.
- Native Arrow nested types with axis manifests (§7.2 Rules 1–2) — no array is ever a string.
- The **feature algebra** (§5.8): all eleven operators, typed at definition time, with `extend` storing a diff rather than a copy; cycle rejection; depth cap; cost rollup.
- The **leakage certificate** (§29.1): signed, attached, naming the rule checked, the rows examined, and every exception with its justification.
- The **scratch namespace** and `maya feature quick <file.csv>` (§28.1).
- Feature designer and pin browser screens; the download dialog with explicit array-encoding choice (§7.2 Rule 3).

**Exit criteria**

- **SC-1**: a feature is pinned, the cache is wiped, it is re-resolved, and the content hashes are byte-identical — *and* a pin of changed data hashes differently, in the same test.
- **SC-11**: a feature is resolved as of a past knowledge instant *after* a restatement, and returns the pre-restatement values exactly.
- **SC-12**: a monthly pin of a feature whose history did not change costs under 5% of a full pin, measured.
- A property-based suite (Hypothesis) proves write → read → identical for **every** logical type including `list`, `fixed_vector`, `tensor`, `struct` and `map`, across Arrow IPC, Parquet, JSON and all three CSV encodings.
- A leakage certificate is produced, and a **deliberately leaky** feature set is refused with the offending rows named.
- `maya feature quick` takes a messy CSV to a typed, resolvable, shareable feature in one command, timed and under a minute.
- A pin interrupted mid-write leaves nothing visible and is reclaimed by the reaper (§15.3).

---

### M3 — Feature sets · **L**
*Specification Phase 2*

**Deliverables**

- Attribute mapping, the four alignment modes (`inner`, `outer`, `left`, `asof`), broadcast joins stated in the plan, and rejection — never a silent row pick — where a member index has columns the set does not.
- The five-layer policy precedence (§6.4), extended to six by inherited policy (§6.8), **with the winning layer and its source shown per attribute in the UI**. This is the requirement most likely to be quietly dropped; it is an exit criterion for that reason.
- Filters compiled to Delta partition pruning, including universe filters that reference another feature as of the row date, so survivorship bias is excluded by construction.
- The three materialization shapes: `tabular`, `wide`, `tensor`, each with its axis manifest.
- **Cascade pin** in one transaction with one approval, rolling back entirely if any member fails a quality check.
- The feature set algebra (§6.8), `extend` storing a diff, depth cap 8, access propagation that names withheld attributes rather than dropping them silently.
- Equivalence detection: `project(extend(S, …), attrs)` hashes identically to the directly-written form, and MAYA offers the existing set instead of letting the catalog fill with near-copies.

**Exit criteria**

- A tensor-bearing feature set pins and round-trips through CSV *and* Arrow with no loss, verified by extracting the values back.
- A cascade pin over forty members either completes or rolls back entirely — proved by injecting a quality failure at member 39.
- Two algebraically identical definitions are detected as duplicates at creation.
- A set derived from a feature the user cannot fully read resolves with the withheld attributes **named and null**, never silently absent.

---

### M4 — Workflow, workspaces and impact · **L**
*Specification Phase 3 · contains the third one-way door*

**Deliverables**

- The canonical state machine (§10.1) driving every object type, with states, transitions, approvals and notifications as **configuration** (§10.2) — a firm tightens production policy without a release.
- Pluggable named checks evaluated at transition time, each failing with the name of the check that blocked.
- Segregation of duties with the three strictness levels, and the **role presets** of §28.9 — *Small team*, *Standard*, *Regulated* — because a ten-person desk wearing all eight hats is otherwise blocked at every transition.
- **Workspaces** (§28.3): copy-on-write branches of the catalog. Edit, resolve against the edit, review as a branch diff, approve as a merge.
- Semantic diff per object type — schema, policy, formula rendered as mathematics, code, document.
- Lineage written **by the same transaction that creates the object**, so it cannot drift. Upstream and downstream queries answered in milliseconds.
- The algebra canvas (§16.3) on vendored Cytoscape.js: operator nodes, seven typed edge styles, four overlay modes, focus-plus-context beyond ~300 nodes.
- Campaigns (§10.5) and break-glass (§10.4) — loud, permanent, never erasable.

**Exit criteria**

- A feature reaches `approved` **only** through a compliant, audited path — proved by a suite that attempts every non-compliant route and is refused by each.
- Self-approval is refused under `strict` and permitted under a namespace explicitly configured otherwise, with the configuration visible on the review screen.
- A change is rehearsed in a workspace, its branch diff reviewed, and approved as a merge, with nothing production-facing touched before the merge.
- Break-glass leaves a permanent `force_approved` mark, notifies immediately, and appears in the monthly report.

---

### M5 — Models · **L**
*Specification Phase 4*

**Deliverables**

- The **formula IR** (§8.1) as a typed expression tree, and — critically — the fact that **nobody authors it by hand** (§28.6): parsed from LaTeX, lifted from Python by AST analysis, or drafted and corrected. The IR earns its place by type-checking against the bound feature set, rendering the document, and producing semantic diffs.
- The declared black-box node, so an opaque model is *recorded as opaque* rather than pretended otherwise.
- Input contract validation, ahead of warrant issuance.
- Code artifacts with the six-rung validation ladder (§17.2), ending in a sandboxed smoke run and a **determinism probe** — the run executed twice and compared, because non-determinism undermines every reproducibility claim MAYA makes.
- `ParameterSet` as a first-class versioned object with bounds checking, not a file attachment.
- The LaTeX editor with KaTeX preview, Tectonic PDF export in a sandboxed worker, required-section completeness blocking submission, and `\mayaformula{}` binding the document to the IR so the two cannot drift.
- **Composite models** (§8.7): five kinds, union contract, alias-namespaced parameters, frozen members, maturity capped at the lowest member's, opacity and access propagation, depth cap 4.
- **Spec–code conformance testing** (§29.7), behind a flag.

**Exit criteria**

- **SC-9**: a new model designer, unaided, publishes a first model in under 60 minutes — measured with a real person, not estimated.
- A model version's PDF is compiled by Tectonic and its **extracted text** is asserted, not the code path that produced it.
- Changing the IR marks the document for re-review automatically.
- A malicious artifact — filesystem write, socket open, `eval`, infinite loop, 10 GB allocation — is refused or contained at every one of the six rungs, one test per rung.
- A composite cannot reach `approved` while any member is `experimental`.

---

### M6 — Warrants and the evidence bundle · **L**
*Specification Phase 5*

**Deliverables**

- Training warrants: contract validation, split specification, seed, environment declaration, expiry, and the download-checksum-then-verify-on-upload cycle that **turns a warrant from paperwork into a control** (§9.1).
- Execution warrants as **live instruments** (§28.5): short-lived signed tokens rather than perpetual documents, execution reported back as lineage, and **covenants** (§29.5) whose breach suspends the warrant and fails every consuming SDK call closed with the covenant named. Offline use stays possible and is labelled `unattested` on the warrant.
- Sealing, chain of custody, cloning into experiment families, revocation that propagates to every consumer.
- Composite warrants: union contract validation per member, member manifest, deterministic per-member seed derivation from one seed, partial parameter upload, per-member metrics.
- **Escrowed holdout and blind scoring** (§29.4), including the **scoring-attempt counter** — twenty attempts against a holdout is itself overfitting and the count is the only honest way to say so.
- `maya export bundle` / `maya export verify` — signed archive with the pinned execution environment (image digest and lockfile) and the original run's **output** hash, so `verify` re-executes and compares outputs, not just inputs (§28.7). Where re-execution is impossible, the bundle says so explicitly rather than implying a verification it cannot perform.

**Exit criteria**

- **SC-2**: a two-year-old training run is reproduced from its warrant in under 10 minutes with no human archaeology — rehearsed against a warrant deliberately aged in the test fixture.
- Data modified outside MAYA between download and parameter upload is caught by the checksum and flagged `unverified_data`, and cannot be approved without an explicit justified override.
- A covenant breach suspends a live warrant and the next SDK call fails closed naming the covenant — end to end, against a running server.
- A bundle verifies **on a machine with no network route to any MAYA**, and a bundle with one byte altered fails verification.

---

### M7 — Hardening · **L**
*Specification Phase 6*

**Deliverables**

- Performance and soak against the §24.3 targets; the scaling levers pulled in the stated order and the result recorded.
- Concurrency: parallel pin attempts, cascade deadlock probes (locks taken in sorted id order, so deadlock is impossible by construction — tested, not assumed), double-submit idempotency, cancellation mid-job.
- SDK and CLI completeness and ergonomics; `maya.testing` fakes; the record/replay transport.
- **The UI test suite runs against the SDK fake** — which is the sharpest available proof that no screen holds a backdoor. If the SDK protocol is enough to render every screen, then nothing is special-cased.
- Runbooks shipped **with** the product (§20): stuck job, orphaned pin partition, Delta small-file explosion, database failover, IdP outage, sandbox escape suspicion, quota exhaustion, restore drill, default-password remediation.
- Backup and recovery with a **tested** quarterly restore drill, ending in `maya admin verify-integrity` re-reading every pin and recomputing hashes.
- External security review.
- The synthetic market dataset (§23) — symbols, calendars, gaps, corporate actions, a tensor volatility surface, deliberately messy CSVs — so every developer tests against the same realistic, awkward data rather than tidy fixtures. *(Seeded earlier, in M2; completed here.)*

**Exit criteria**

- **All thirteen success criteria measured and met**, each by a named test or benchmark (plan §8).
- The restore drill has been performed and its result recorded and visible.
- No unresolved high findings from the external review.

---

### Beyond M7 — the additive innovations

Each behind a feature flag, in roughly this order (§29.11): shadow replay (§29.2) → licence algebra and external audit anchoring (§29.6) → the recorded challenger (§29.8) → spreadsheet import (§29.9) → vendor model registration (§29.10). Shadow replay is first because it is the one that changes what a review *is*: *"this forward-fill limit change moves 3 of 11 dependent models; the PD model shifts by more than 2 bp on 0.4% of rows"* instead of a list of names.

---

## 7. The gate ladder

One entry point — `bash tools/ci/gates.sh` — run locally and in CI. **Never a remembered list**; the script is the authority, and a gate that exists only in someone's head has already been skipped.

| # | Gate | Lands | Overridable |
|---|---|---|---|
| 1 | `ruff` lint + format, function length, complexity | M0 | no |
| 2 | `mypy --strict` on `domain/`, `services/` | M0 | no |
| 3 | File size — 1,500 hard, 1,200 note, 800 warn | M0 | **no** |
| 4 | Import boundary: no `sqlalchemy` outside `maya.persistence` | M0 | **no** |
| 5 | Import boundary: nothing under `maya.web` imports deeper than `maya.sdk` | M0 | **no** |
| 6 | Public-symbol count per module, dependency-cycle check | M0 | no |
| 7 | Version single-source grep | M0 | no |
| 8 | No secret in `config/application.yaml` | M0 | no |
| 9 | SDK ↔ API parity, both directions | M1 | no |
| 10 | Unit + property-based suites | M1 | no |
| 11 | Repository suite on **real SQLite and real PostgreSQL** | M1 | no |
| 12 | Authorization matrix — zero unexpected allows | M1 | **no** |
| 13 | OpenAPI contract against a committed snapshot | M1 | explicit approval to change the snapshot |
| 14 | Reproducibility: pin → wipe → re-resolve → compare | M2 | **no** |
| 15 | Concurrency: parallel pins, deadlock probes, idempotency | M2 | no |
| 16 | Playwright end-to-end on the main journeys, real screenshots | M4 | no |
| 17 | Dependency scan, SAST, sandbox escape tests | M5 | no |
| 18 | Performance benchmarks — no regression over 10% without a note | M7 | note required |

### 7.4 Two things this ladder must not be allowed to do

**A green suite at the wrong total.** A module that cannot import its dependency *skips*, and a module-level skip removes its whole file from the collected count. Install `requirements.txt` without `requirements-dev.txt` and the suite goes green at a smaller number while real coverage has silently gone. From M1, the advertised count is stamped from one source (`docs/test_counts.json`) and the pre-commit hook re-collects and fails if the total moved. **Check the total, not merely the absence of failures.**

**A checker whose output is all noise.** A citation or accuracy checker that reports hundreds of false positives trains everyone to ignore it — and would then hide the real one. Any checker added here is sampled before its number is treated as debt.

---

## 8. Success criteria, mapped

Specification §2 states thirteen. Each is met by a named test, at a named milestone. A criterion with no test is a wish.

| # | Criterion | Met at | Proved by |
|---|---|---|---|
| SC-1 | Byte-identical re-resolution of any pinned feature set | M2 | Gate 14, with the negative case in the same test |
| SC-2 | Two-year-old training run reproduced in under 10 min | M6 | Bundle verify against an aged fixture |
| SC-3 | 200 concurrent interactive users per API pod | M7 | Soak benchmark |
| SC-4 | Metadata p95 under 300 ms | M7 | Benchmark; regression-gated from M1 |
| SC-5 | 50-col × 10-year resolution under 15 s warm, 60 s cold | M7 | Benchmark on the synthetic dataset |
| SC-6 | 100% of non-UI files under 1,500 lines | M0 | Gate 3, continuously |
| SC-7 | Zero unauthorized accesses succeed | M1 | Gate 12, grown by every later milestone |
| SC-8 | 100% of state changes audited immutably | M1 | Hash-chain suite, including the tamper case |
| SC-9 | New designer publishes a first model in under 60 min | M5 | Timed with a real person |
| SC-10 | Full suite green on SQLite and PostgreSQL | M1 | Gate 11, continuously |
| SC-11 | Point-in-time reconstruction after a restatement | M2 | Bitemporal suite |
| SC-12 | Monthly pin of unchanged history under 5% of full size | M2 | Fragment-store measurement |
| SC-13 | 100% UI ↔ SDK parity, both directions | M1 | Gate 9, continuously |

---

## 9. Risks, and where the plan answers them

| Risk (§26.2, §28.11) | Plan's answer |
|---|---|
| **Resolution semantics are silently wrong** | Property-based tests over every logical type; the synthetic *messy* dataset from M2; fill reports on every run; the winning policy layer displayed per attribute (M3 exit criterion) |
| **Nested/tensor fidelity leaks** | Native Arrow types, axis manifests, round-trip tests for every type × every format, no string encoding by default — all M2 exit criteria |
| **Python's concurrency ceiling** | Async I/O + native kernels + worker processes, benchmarked under soak at M7. Mitigated, not removed; a Rust resolution core is a decision worth revisiting **after M3 benchmarks**, not now |
| **The platform is routed around** | The scratch namespace and `maya feature quick` in M2, not M7. Ceremony scales with consequence |
| **Two-store consistency on pin** | Saga with hash verification, reaper for orphans, nothing visible before metadata commit — with the interrupted-pin case as an M2 exit criterion |
| **Cascade pins multiply storage** | Content-addressed fragments in M2. SC-12 measures it |
| **Workflow policy too rigid or too loose** | Policy as per-namespace configuration, role presets (M4), break-glass that is loud and audited |
| **SQLite mistaken for production** | UI banner, documented ceiling, and a refusal to run `environment: prod` on SQLite |
| **Scope creep into training and serving** | D-4 settled before M2. The warrant boundary is what keeps MAYA coherent |
| **An empty catalog** | Not an engineering risk. Named in §4 as a sponsorship decision because no amount of platform fixes it |

---

## 10. Working the plan

- **Branch.** All work on `develop`. Promote to `main` only when the suite is green, the counts are stamped, built artifacts are newer than their sources, and the tree is clean.
- **Commits.** One coherent change per commit, message stating what changed and why. **No assistant attribution trailers** — enforced by the `commit-msg` hook from M0.
- **ADRs.** Every architectural decision numbered in `docs/adr/` and referenced from the code it governs. The eight decisions in plan §4 each become an ADR when answered.
- **This document.** A living plan. When a milestone lands, its exit criteria move into the README's *What's shipped* section **with the test that proves each one**, and the milestone section here is marked done rather than deleted — the record of what was promised is part of the evidence.

---

**MAYA** — Model &amp; AI Lifecycle Assurance · *Evidence, not assertion.* · © 2026 Ashutosh Sinha
