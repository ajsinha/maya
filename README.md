<p align="center">
  <img src="assets/logo/maya-lockup.svg" alt="MAYA — Model &amp; AI Lifecycle Assurance" width="100%">
</p>

<h1 align="center">MAYA</h1>

<h3 align="center">Model &amp; AI Lifecycle Assurance</h3>

<p align="center"><strong><em>Evidence, not assertion.</em></strong></p>

<p align="center">
  <a href="#status--read-this-first">Status</a> ·
  <a href="#the-name">The name</a> ·
  <a href="#what-makes-it-different">What makes it different</a> ·
  <a href="#getting-started">Getting started</a> ·
  <a href="docs/MAYA_Requirements_and_Design.md">Specification</a>
</p>

---

**MAYA** is the system of record for quantitative **features**, **feature sets**, **models**, and the **warrants** that license a model to be trained or run. Definition, data, documentation, approval and evidence live in one place, so any number a model produced can be rebuilt exactly, years later, by someone who was not there.

It exists because four things are true in almost every quantitative shop, and each of them is a reproducibility failure waiting to be discovered by someone who is not on your side:

1. Feature logic lives in notebooks and SQL snippets, so two teams compute "adjusted close" differently and neither is wrong.
2. Training data is a file on a share drive. When results are challenged, nobody can produce the exact rows used.
3. A model's mathematics lives in a PDF, its code in a repo, its parameters in a spreadsheet, and the three drift apart.
4. Nothing binds *this model version* + *this data version* + *these parameters* into one auditable, transferable object.

The **warrant** is MAYA's distinguishing primitive. A *training warrant* freezes a model version against a feature set version and receives the parameters that training produced. An *execution warrant* packages a model, its parameters and its input contract into a licence that can be handed to a downstream system or a regulator — and, because it is a live instrument rather than a document, withdrawn on a Friday afternoon when the model is found to be wrong. Warrants make *who was allowed to run what, on which data, with whose approval* a query rather than an archaeology project.

[![Status](https://img.shields.io/badge/status-specification%20complete-blue.svg)](docs/MAYA_Requirements_and_Design.md)
[![Implementation](https://img.shields.io/badge/implementation-v0.1.0-green.svg)](docs/IMPLEMENTATION_PLAN.md)
[![Python](https://img.shields.io/badge/python-3.13-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

---

## The name

**māyā** (माया) — in Indian philosophy, *māyā* is **appearance**: the representation that stands in
for reality and is so easily mistaken for it. The usual translation, "illusion", is too strong. Māyā
is not falsehood. It is a *rendering* of the world — useful, often necessary, and dangerous only when
you forget that it is a rendering.

That is exactly what a model is. The supervisory guidance says so in almost the same words:

> *"Models are simplified representations of real-world relationships… based on assumptions that make
> them useful in estimating values and predicting events, but which also can have limitations and
> create model risk."*
> — SR 26-2, §III

Model risk is what happens when an organisation forgets the difference between the map and the
territory. The platform is named for the thing it governs, and for the discipline of never mistaking
it for the world.

| | |
|---|---|
| **Name** | MAYA — from Sanskrit *māyā* (माया), *appearance*, *representation* |
| **Tagline** | Model & AI Lifecycle Assurance |
| **Slogan** | **Evidence, not assertion.** |
| **Principle** | A model is a representation of the world. Governance is knowing the difference. |

### The mark

![The MAYA mark — a square inscribed in a circle](assets/logo/maya-mark-128.png)

A **square inscribed in a circle** — the oldest model there is. Archimedes estimated π by inscribing
and circumscribing polygons and tightening the bound as the sides multiplied: a tractable figure
standing in for one that cannot be computed directly.

The **gap** between the square and the circle is the model error. The **four points** are where the
model and the world agree. Add sides and the gap closes but never vanishes — no model becomes the
thing it represents.

That is māyā, and it is model risk, in one figure.

---

## Status — read this first

**Version 0.1.0 (2026-09-19): the first end-to-end build from specification revision 2.1.**
The whole spine runs through the web UI, the REST API, the SDK and the CLI:
source → feature → feature set → pin → model → training warrant → parameter set →
execution warrant → reproducibility bundle.

| | |
|---|---|
| **Specification** | [`docs/MAYA_Requirements_and_Design.md`](docs/MAYA_Requirements_and_Design.md) — the authority |
| **Plan** | [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) |
| **Code** | `maya/` (the platform), `maya_delta/` (the lakehouse layer), `run_maya_web.py` |
| **Tests** | 447 passing on SQLite and on PostgreSQL 18, Linux. `python -m pytest -q` |
| **Gates** | `python tools/ci/gates.py`: all green (file size, both import boundaries, seam imports, version single source, no secrets, table contract, colour contrast, SDK↔API parity for 171 endpoints, schema drift) |

### Not yet — stated so nobody has to discover it

- **PostgreSQL is verified on 18 only.** The whole suite passes on PostgreSQL 18.6 as well as
  SQLite (`MAYA_TEST_PG_URL=postgresql+psycopg://user@host/db python -m pytest`; each test
  platform gets its own freshly created database). Earlier PostgreSQL majors have not been run.
- **Only Linux has been exercised.** There is no hosted CI: the gate ladder runs locally,
  in the pre-commit hook on every commit and as `python tools/ci/gates.py --tests`. Windows
  and macOS need a run on those machines.
- **SAML 2.0 and security keys are tested against software, not real products.** Single
  sign-on is OIDC or SAML 2.0 (`auth.sso.protocol: oidc | saml2`, SP-initiated; the IdP
  must sign assertions). Second factors are TOTP and WebAuthn security keys/passkeys. The
  SAML tests use a test IdP whose assertions are really signed with xmlsec, and every
  check (signature, issuer, audience, destination, recipient, expiry, unsolicited,
  replayed request, replayed assertion) is attacked on its own; the WebAuthn tests use a
  software ES256 authenticator verified by py_webauthn. No commercial IdP (Okta, Entra ID,
  ADFS) and no hardware key or browser has been exercised. WebAuthn attestation is not
  requested, so MAYA does not claim a key is hardware-backed; SAML AuthnRequests are
  unsigned, and SAML single logout is not built.
- **The `strong` sandbox tier is Linux-only.** On Linux, bubblewrap namespaces, a
  seccomp-bpf filter and a cgroup v2 scope are applied unprivileged, and the tier is
  claimed only when a probe child fails to escape. macOS runs at `moderate`
  (`sandbox-exec`); Windows at `minimal` (Job Objects are not built).
- **No Tectonic here**, so spec PDFs are watermarked drafts. `typeset.require_true_build`
  forbids approval on a draft render outside dev.
- **Not built:** the assistant (§29.8); server-side table paging; SDK record/replay and
  `offline()`; performance benchmarks (SC-3/4/5).
- **Spreadsheet import is v1 scope.** Arithmetic, standard functions, named cells and ranges,
  and VLOOKUP/HLOOKUP over constant tables lift into the formula IR; everything else is refused
  by cell. The check against a workbook's cached results was exercised on files written by
  openpyxl with injected results, not yet on workbooks saved by Excel itself.
- **Custody anchors are only as external as you make them.** The chain head is signed,
  appended to `custody.anchor.file` and emitted as a webhook event hourly; RFC 3161
  timestamping is off by default. Point the file at WORM or off-host storage: on the
  same disk as the database it only raises the bar. The TSA's own signature is checked
  with `openssl ts -verify`, not inside MAYA.
- **Search is a `LIKE` scan, not full-text search.** This, CodeMirror 5 instead of 6, and
  the corrected dark `--maya-crimson-deep` token are recorded in the specification as
  revision 2.2.

---

## What makes it different

No product occupies this position today (spec §27 compares MAYA head-to-head against feature stores, lakehouse versioning, ML registries, catalogs and model-risk tools). Five things are the reason.

- **Definitions are code; data is a consequence.** MAYA stores *how* a number is produced and materialises values only when asked. A **version** freezes *how*; a **pin** freezes *what*. A version resolved a hundred times may return different values as its source moves; a pin returns the same bytes forever. *(§4)*
- **A closed algebra over features and feature sets.** `union`, `intersect`, `compose`, `coalesce`, `extend`, `override`, `project`, `aggregate` — every operator takes features and yields a *feature definition*, not a one-off result, so a derived object is an ordinary object: named, versioned, pinnable, permissioned, and visible in lineage. Inheritance stores a **diff, not a copy**, so a fix to a parent reaches every child. *(§5.8, §6.8)*
- **Model mathematics as structured data.** A model's formula is a typed **expression tree**, not a LaTeX string and not prose. From it MAYA type-checks inputs against the bound feature set, renders the specification document, emits a reference implementation, and **diffs two model versions mathematically** — telling a reviewer *"the discount factor changed from continuous to simple compounding"* rather than showing a text diff. Where a model genuinely has no closed form, it is recorded as a **declared black box** rather than pretended otherwise. *(§8.1)*
- **Bitemporality from the first migration.** Every row carries an *event time* and a *knowledge time*. A vendor restatement is a new knowledge-time row, never an overwrite, so *"what did we know on 31 March"* stays answerable and a backtest cannot silently consume restated values. MAYA can then **prove** the absence of look-ahead and issue a signed **leakage certificate** against the warrant. Point-in-time correctness exists elsewhere as a join semantic; nobody issues a certificate. *(§5.1, §29.1)*
- **Evidence that survives leaving the building.** A pin's content hash is computed over a *canonical* Arrow representation, not over file bytes, so two pins of the same data hash identically even across engine versions. `maya export bundle` produces a signed archive — warrant, model, formula IR, code, parameters, every member pin, the pinned environment — with a `verify.py` that recomputes every hash **and re-executes**, on a machine with no MAYA access at all. *(§7.2, §18.4, §28.7)*

---

## The shape of the thing

```
Source ──▶ Feature ──▶ FeatureSet ──▶ ⟨pin⟩ ──┐
  sql        definition   attribute            ├──▶ Training Warrant ──▶ Parameter Set
  csv        + versions   mapping              │         │                      │
  parquet        │        + alignment          │         ▼                      ▼
  json           ▼                             │    (train offline,      Execution Warrant
  delta      Feature Pin ──────────────────────┘     upload params)       ── the licence
  derived    (materialised,                                                  you hand to
  python      content-addressed)        Model ──▶ Composite Model         a downstream
                                        formula · code · LaTeX             system, or
                                                                          to a regulator
```

Features and feature sets are **closed under their operators**, so the algebra loops back into the same flow: a derived feature re-enters as an ordinary feature. A composite model is an ordinary model and takes **one** warrant over **one** feature set, however many members it has.

---

## Ten innovations, and what each costs

Specification §29 states each of these precisely enough to build, and honestly about its price. They are listed here because they are the reason MAYA is worth building rather than buying.

| # | Innovation | Cost, stated |
|---|---|---|
| 29.1 | **Bitemporal features + leakage certificate** — signed proof a training set has no look-ahead | Two columns everywhere, a second index dimension, ~20–30% storage. Phase 1 or never |
| 29.2 | **Shadow replay** — re-run every dependent model on the proposed change and report the *numeric* shift, not a list of names | Compute, and a sampling strategy honest about coverage |
| 29.3 | **Content-addressed materialization** — a pin is a manifest of shared fragments; a month-end pin costs its delta | A fragment index and a GC provably safe against sealed pins. Phase 1 or never |
| 29.4 | **Escrowed holdout and blind scoring** — the developer never receives the test partition; MAYA scores and counts the attempts | MAYA must execute scoring — a narrow, bounded step into runtime |
| 29.5 | **Warrants with covenants** — machine-checked bounds whose breach *suspends* the warrant and fails every consuming call closed | A monitoring loop and a clear false-positive story |
| 29.6 | **Licence algebra + tamper-evident custody** — vendor terms propagate as the most restrictive of a derivation's operands; the audit chain anchors externally | Legal input on vocabulary; one external dependency |
| 29.7 | **Spec–code conformance testing** — differentially test the uploaded Python against a reference generated from the documented mathematics | An IR interpreter, and honesty that sampled agreement is not proof |
| 29.8 | **The assistant as a recorded challenger** — never approves, never blocks, never writes to a sealed object; its memo is attached and the human records whether they agreed | Prompt and output governance, and a strict no-write boundary |
| 29.9 | **Spreadsheets as first-class models** — lift an Excel formula graph into the IR and govern it like anything else | Scope v1 narrowly and refuse the rest loudly |
| 29.10 | **Vendor models under the same wrapper** — register the black box, mark what cannot be verified as unverifiable rather than omitting it | Low to build, high in value: completeness is what an examiner asks for |

---

## Deliberate non-goals

Stated because a design without stated losses is a sales pitch. MAYA **does not train models and does not serve predictions** (§2). It will be beaten on online serving latency, streaming freshness, raw scale, connector breadth and out-of-the-box regulatory report templates (§27.4). Where a firm needs sub-10 ms serving, the right answer is MAYA governing the definition and a serving layer consuming a sealed execution warrant — not MAYA growing a serving tier.

Four risks have no clean fix and are accepted with mitigation rather than waved away: two-store consistency on pin, Python's concurrency ceiling, execution that happens outside MAYA, and the fact that a catalog nobody seeds is an empty shop (§28.11).

---

## Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.13 (`.python-version`) | Matches the estate; `.venv` is git-ignored |
| API | FastAPI + Pydantic v2, OpenAPI 3.1 | Typed contracts, generated spec, async where it helps |
| Platforms | **Windows, Linux and macOS, equally first-class** | Not "Linux, and it probably works elsewhere" — all three green in CI or it does not release (SC-14) |
| ORM | SQLAlchemy 2.0, typed | Confined to one package, enforced by import-linter |
| Schema | **Two generated DDL files, no migration framework** | One typed metadata is the source; `schema/postgresql.sql` and `schema/sqlite.sql` are generated from it and CI fails on drift. Two files maintained by hand are two files that will disagree |
| Database | PostgreSQL 14+ in production, SQLite for laptop and dev | Full suite green on both, or the build fails |
| Compute | Apache Arrow + Polars in process, DuckDB for pushdown | Columnar, zero-copy, releases the GIL |
| Lakehouse | **`maya_delta`** — native `deltalake` preferred, MAYA's own pure-Python Delta as fallback | ACID and time travel with no JVM and no Spark, and no hard dependency on someone else's build matrix having a wheel for the platform in front of us |
| UI | Jinja2 + **Bootstrap 5** + **jQuery**, vendored, **no build pipeline**, Harvard Crimson | Renders air-gapped. A developer moves between MAYA and DishtaYantra without relearning the layout grammar |
| Startup | One entry point: `python run_maya_web.py` | A second way to start a server is a second set of startup invariants to get wrong |
| Dependency seams | **Twenty** optional or native components sit behind named MAYA seams, resolved once at startup and reported | A capability must not vanish because a wheel does not exist for the interpreter in front of us |
| LaTeX | Tectonic in a sandboxed worker | Deterministic PDFs, no system TeX |
| Observability | OpenTelemetry, Prometheus, structured JSON logs | Vendor-neutral |

Full rationale in spec §13.1; deployment topologies — laptop, single node, clustered, air-gapped — in §24.1, all four from one artifact with only configuration differing.

### Dependency seams

`maya_delta` is not a special case. Spec **§13.4** states the rule for the whole stack:
where a capability comes from something that might not be installed, MAYA depends on its
own named seam and never on the component directly — one resolver, resolved once at
startup, reported in the banner and on the health page, pinnable by configuration, and
**recorded in every pin's provenance** so a result nobody can reproduce for want of
knowing which implementation produced it never happens.

The part that matters is not the list but the **polarity** — which side is authoritative:

- **Type A — native preferred, pure fallback.** `maya_delta`, JSON, frames, pushdown, the
  PostgreSQL driver, full-text search, compression, the tz database. Absence costs
  throughput, not capability.
- **Type B — MAYA's implementation is authoritative; a native one is only an
  accelerator.** Everything feeding a content hash: the canonicalizer and the fragment
  chunker. Here an accelerator that disagrees is a *defect in the accelerator*, and CI
  byte-compares rather than tests. Get this polarity backwards and two pins of identical
  data hash differently depending on which machine wrote them — SC-1 passes on each
  machine separately while being false across them.
- **Type C — substitutable, never downgraded.** Signing, the sandbox, SSO, object store,
  job queue. A hand-rolled fallback signer is how a governance platform ships a
  vulnerability, so absence here is a **refusal with a named reason**, not a quiet
  substitution. SAML without `xmlsec` fails at *startup* with the package named, rather
  than at the first person's login.

§13.4.4 lists what is deliberately **not** proxied — Arrow, SQLAlchemy, FastAPI, the
database engines — and why, because a pattern applied everywhere stops being a decision.

---

## Repository layout

```
run_maya_web.py            # the one supported way to start MAYA
config/application.yaml    # tracked, no secrets; application.local.yaml overlay is git-ignored
maya/
├── core/                  # version, configurator (from DishtaYantra), seams: backends,
│                          #   djson, canonical, chunker, kdf, crypto, compress, typeset, calendars
├── config/                # typed settings over the configurator
├── persistence/           # SQLAlchemy and nowhere else
│   ├── models/            #   the ORM metadata: the single source of the schema
│   ├── repositories/      #   dict-returning repositories, hash-chained audit, job claim
│   └── schema/            #   sqlite.sql, postgresql.sql, both GENERATED
├── security/              # roles matrix, can(), per-platform sandbox
├── resolution/            # expressions, rules, grids, transforms, quality, algebra, shapes
├── formula/               # formula IR, parser, LaTeX, evaluator, diff, codegen, artifacts
├── workflow/              # engine, policy validation, default policies
├── storage/               # blob store, LakeStore (fragments over maya_delta)
├── services/              # use cases: features, featuresets, models, warrants, …
├── jobs/                  # queue and workers
├── api/                   # FastAPI routers under /api/v1
├── sdk/                   # the only client: Client, AsyncClient, inproc and http transports
├── web/                   # Jinja2 + vendored Bootstrap 5/jQuery; imports maya.sdk only
└── cli/                   # python -m maya.cli …
maya_delta/                # Delta Lake: native (delta-rs) and pure-Python backends
tools/ci/                  # the gates, in Python so they run on every OS
tests/
```

Two structural rules are worth stating in the README because they are load-bearing and non-negotiable (§14, §13, §16):

- **One door to the database.** Any module outside `maya.persistence` importing `sqlalchemy` fails the build.
- **The UI is an SDK client, with no private path to the backend.** Nothing under `maya.web` imports anything but `maya.sdk`. Any screen we can build, a customer can script, because the screen used the same methods — and a capability missing from the SDK cannot be quietly special-cased into the UI to hit a deadline.

- **Every table is paginated, searchable and sortable.** One macro produces every table in the product, and a template crawler fails the build on any `<table>` that did not come from it.
- **A proxied package is imported only inside its own seam.** No `deltalake` import outside `maya_delta`, no `orjson` outside `core/djson`. Which backend is running is a configuration fact reported at startup, never a scattered `try: import`.

All four are checked by non-overridable CI gates, not by review discipline. A gate that exists only in a review checklist has already been skipped.

---

## The interface

A governance platform lives or dies on whether people would rather use it than a
notebook (§28.1), so the UI is a first-class deliverable rather than a skin over the API.

**Harvard Crimson, used as a signal rather than a wash.** `#A51C30` is the primary —
measured at **7.48:1** against white, which clears WCAG AAA for body text — over a
parchment canvas, with a lightened crimson in dark mode at **5.67:1** because the brand
value itself measures only 2.44:1 on a dark background. The full token set is in spec
§16.6; a CI gate recomputes every foreground/background pair and fails below AA, because
a palette checked once by hand is a palette that drifts on the next well-meaning tweak.
Crimson marks the primary action, the active location, focus, and brand-bearing
headings — nothing else. Status is never carried by colour alone: every pill has a glyph
and a word.

**Every table, without exception, paginates, searches and sorts.** Rows-per-page
dropdown at 25 / 50 / 100 / 250 / All, remembered per table per user; search across
visible columns with the removed count stated; sort on every ordered column, applied to
the *whole result set* rather than the visible page; column show/hide; export of the
current view honouring the active filter and sort; keyboard paging for accessibility.
Past a threshold the macro switches to server-side cursor pagination without changing how
it looks or behaves. Spec §16.7 — and a crawler gate, because a rule that is merely
written down is a rule that holds until the first deadline.

**Workflow is something you operate, not something you configure in a file.** State
machines render with the live population on them — how many objects sit in each state,
how long they have been there, which transitions are blocked and by which check.
Policies are authored in a structured editor that refuses an unreachable state, an
unsatisfiable approval or an unknown check *at edit time*, and previews the change
against the live population before it is saved. The policy is itself versioned, diffed,
approved and audited, because a governance system whose own rules can be changed
silently does not govern anything. YAML remains — as an import/export projection for
GitOps, not as a second authority. Spec §10.6.

---

## Getting started

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
python run_maya_web.py                 # http://127.0.0.1:8600 — log in as admin / maya-dev-admin
```

Change the admin password when prompted. To switch the database, set `db.dialect` in
`config/application.yaml`, set `MAYA_DB_DIALECT`, or pass
`python run_maya_web.py --db.dialect=postgresql`, then supply `db.postgresql.*`, with the
password from `MAYA_PG_PASSWORD` or `config/application.local.yaml`. The schema is created
from the matching `.sql` file on first start, and verified by hash on every start.

```bash
python -m maya.cli feature quick prices.csv        # a scratch feature in one command
python -m maya.cli admin export-estate --out e.mayabundle   # the upgrade path, with
python -m maya.cli admin init-db --force                    #   no migrations (§14.3)
python -m maya.cli admin import-estate --in e.mayabundle
python -m maya.cli export verify bundle.zip        # offline; needs no MAYA
python tools/ci/gates.py --tests                   # the gate ladder
git config core.hooksPath .githooks                # commit-msg and pre-commit hooks
```

API documentation: `/api/v1/docs`. SDK: `from maya.sdk import connect`.

---

## Security posture

Specified before it is built, which is the only order that works (§12, §21):

- **No silent defaults.** Where a value materially changes behaviour — authentication mode, database URL, storage root, sandbox enablement — there is no default at all outside dev, and MAYA fails at startup naming the setting.
- **Secrets never in a tracked file.** `config/application.yaml` is tracked and carries no secret; `config/application.local.yaml` is git-ignored and is where a real one belongs.
- **The default admin password is a speed bump, not a door.** MAYA refuses to start with it outside dev unless explicitly allowed.
- **User Python is hostile until proved otherwise.** Static validation, import allowlist, a sandboxed subprocess with no network, no credentials and resource caps — and a determinism probe, because non-determinism undermines every reproducibility claim MAYA makes.
- **The sandbox tier is declared, not assumed.** Three operating systems do not have equivalent isolation primitives, so MAYA resolves a tier at startup — `strong` on Linux (separate user, seccomp, cgroups), `moderate` on macOS and Windows (`sandbox-exec` / restricted token and Job Objects), `minimal` if misconfigured — names it on the health page, refuses to start below the configured minimum outside dev, and records it permanently on every artifact validated under it. A reviewer needs to know what the green tick was worth.
- **The audit log cannot be edited.** Append-only, hash-chained, with the chain head anchored externally. Nothing in MAYA — not an administrator, not a migration — can alter an entry.

---

## Legal

© 2026 Ashutosh Sinha. All rights reserved. MAYA — including all source code, specification and design documents, data models, algorithms, build tooling, brand assets, the MAYA name and the MAYA mark — is the exclusive property of Ashutosh Sinha. This software is **proprietary and confidential**; unauthorized copying, modification, distribution, or use, in whole or in part, is strictly prohibited without express written permission. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY ARISING FROM THE USE OF THIS SOFTWARE.

---

## Contact

**Ashutosh Sinha** · ajsinha@gmail.com · https://github.com/ajsinha/maya

---

**MAYA** — Model &amp; AI Lifecycle Assurance · *Evidence, not assertion.* · © 2026 Ashutosh Sinha
