<p align="center">
  <img src="assets/logo/maya-lockup.svg" alt="MAYA" height="72">
</p>

# MAYA — Model &amp; AI Lifecycle Assurance

## © 2026 Ashutosh Sinha

> ### *Evidence, not assertion.*

**MAYA** is the system of record for quantitative **features**, **feature sets**, **models**, and the **warrants** that license a model to be trained or run. Definition, data, documentation, approval and evidence live in one place, so any number a model produced can be rebuilt exactly, years later, by someone who was not there.

It exists because four things are true in almost every quantitative shop, and each of them is a reproducibility failure waiting to be discovered by someone who is not on your side:

1. Feature logic lives in notebooks and SQL snippets, so two teams compute "adjusted close" differently and neither is wrong.
2. Training data is a file on a share drive. When results are challenged, nobody can produce the exact rows used.
3. A model's mathematics lives in a PDF, its code in a repo, its parameters in a spreadsheet, and the three drift apart.
4. Nothing binds *this model version* + *this data version* + *these parameters* into one auditable, transferable object.

The **warrant** is MAYA's distinguishing primitive. A *training warrant* freezes a model version against a feature set version and receives the parameters that training produced. An *execution warrant* packages a model, its parameters and its input contract into a licence that can be handed to a downstream system or a regulator — and, because it is a live instrument rather than a document, withdrawn on a Friday afternoon when the model is found to be wrong. Warrants make *who was allowed to run what, on which data, with whose approval* a query rather than an archaeology project.

[![Status](https://img.shields.io/badge/status-specification%20complete-blue.svg)](docs/MAYA_Requirements_and_Design.md)
[![Implementation](https://img.shields.io/badge/implementation-not%20started-lightgrey.svg)](docs/IMPLEMENTATION_PLAN.md)
[![Python](https://img.shields.io/badge/python-3.13-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

---

## Status — read this first

**This repository currently contains a specification and a brand, and no product.**

On 2026-09-17 the previous build of MAYA was deleted in full and the platform restarted from the specification up. What survived is deliberate and small: the logo set in `assets/logo/`, the name, the tagline and the slogan (`assets/BRAND.md`), and the legal files. Everything else — every module, test, template, deck and paper — was removed.

| | |
|---|---|
| **Specification** | Complete. [`docs/MAYA_Requirements_and_Design.md`](docs/MAYA_Requirements_and_Design.md) — 30 sections, also published as `.docx` and `.pdf` |
| **Implementation plan** | Complete. [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — milestones M0–M7, gates, and the decisions that block Phase 1 |
| **Code** | None yet. There is no package, no test suite, no server to run |
| **Blocked on** | Eight open decisions (spec §26.3, restated in the plan). They are cheap to answer now and expensive to answer after Phase 1 code exists |

Nothing below describes behaviour that exists today. Where this README states a capability, it is stating a **commitment made by the specification**, and the section it comes from is cited so the claim can be checked against its source rather than believed. When a capability ships, its row moves from the plan into a *What's shipped* section and acquires a test that proves it. That order — spec, then plan, then code, then a test, then the claim — is not ceremony; it is the same discipline MAYA sells.

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

## Intended stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.13 (`.python-version`) | Matches the estate; `.venv` is git-ignored |
| API | FastAPI + Pydantic v2, OpenAPI 3.1 | Typed contracts, generated spec, async where it helps |
| ORM | SQLAlchemy 2.0 typed, Alembic | Confined to one package, enforced by import-linter |
| Database | PostgreSQL 14+ in production, SQLite for laptop and dev | Full suite green on both, or the build fails |
| Compute | Apache Arrow + Polars in process, DuckDB for pushdown | Columnar, zero-copy, releases the GIL |
| Lakehouse | `delta-rs` | ACID and time travel with no JVM and no Spark |
| UI | Jinja2 templates, **vendored JS, no build pipeline** | The DishtaYantra grammar, so a developer moves between the two codebases without relearning |
| LaTeX | Tectonic in a sandboxed worker | Deterministic PDFs, no system TeX |
| Observability | OpenTelemetry, Prometheus, structured JSON logs | Vendor-neutral |

Full rationale in spec §13.1; deployment topologies — laptop, single node, clustered, air-gapped — in §24.1, all four from one artifact with only configuration differing.

---

## Repository layout

What exists today:

```
maya/
├── assets/
│   ├── logo/                 # the mark, lockup, mono and white variants, raster fallbacks
│   └── BRAND.md              # name, tagline, slogan, and which mark to use where
├── docs/
│   ├── MAYA_Requirements_and_Design.md   # the specification — 30 sections
│   ├── MAYA_Requirements_and_Design.pdf  #   and .docx, same content
│   ├── IMPLEMENTATION_PLAN.md            # milestones, gates, blocking decisions
│   └── README.md
├── LICENSE · NOTICE · README.md
└── .gitignore · .python-version
```

The target layout, once M0 lands (spec §22.3, §14, §16, §18.2.6 — reproduced with its rationale in the implementation plan):

```
maya/
├── maya/
│   ├── domain/        # entities, value objects, policies, state machines — no I/O
│   ├── ports/         # protocols the domain requires
│   ├── services/      # use cases, transactions, orchestration
│   ├── resolution/    # planner, kernels, rules, shape handling
│   ├── storage/       # delta, object store, cache adapters
│   ├── persistence/   # SQLAlchemy, and nowhere else — CI enforced
│   ├── workflow/      # engine, policies, checks
│   ├── security/      # authn providers, authz evaluator, sandbox
│   ├── api/           # FastAPI routers, schemas
│   ├── web/           # templates, static, routes — imports maya.sdk and nothing deeper
│   ├── jobs/          # queue, workers, handlers
│   ├── sdk/  cli/     # client surfaces
│   └── config/  observability/  core/version.py
├── config/            # application.yaml (+ .local.yaml overlay, git-ignored)
├── tests/             # unit, property, repository × both backends, authz matrix, e2e
├── tools/             # CI gates, build scripts
└── docs/              # spec, plan, ADRs, design notes, runbooks, research
```

Two structural rules are worth stating in the README because they are load-bearing and non-negotiable (§14, §13, §16):

- **One door to the database.** Any module outside `maya.persistence` importing `sqlalchemy` fails the build.
- **The UI is an SDK client, with no private path to the backend.** Nothing under `maya.web` imports anything but `maya.sdk`. Any screen we can build, a customer can script, because the screen used the same methods — and a capability missing from the SDK cannot be quietly special-cased into the UI to hit a deadline.

Both are checked by a non-overridable CI gate, not by review discipline.

---

## Getting started

There is nothing to run yet. The productive thing to do today is read, in this order:

1. **[`docs/MAYA_Requirements_and_Design.md`](docs/MAYA_Requirements_and_Design.md)** — §1–§4 for the vision, the personas and the domain language; §5–§9 for the four subsystems; §28 for the design read adversarially; §29 for what is genuinely new.
2. **[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)** — the sequence, the gates, and the eight decisions that block Phase 1.
3. **[`assets/BRAND.md`](assets/BRAND.md)** — the name, the slogan, and which mark to use where.

When M0 lands, this section becomes an installation and a first-run walkthrough, and the specification's §2 success criteria start appearing as measured numbers rather than targets.

---

## Security posture

Specified before it is built, which is the only order that works (§12, §21):

- **No silent defaults.** Where a value materially changes behaviour — authentication mode, database URL, storage root, sandbox enablement — there is no default at all outside dev, and MAYA fails at startup naming the setting.
- **Secrets never in a tracked file.** `config/application.yaml` is tracked and carries no secret; `config/application.local.yaml` is git-ignored and is where a real one belongs.
- **The default admin password is a speed bump, not a door.** MAYA refuses to start with it outside dev unless explicitly allowed.
- **User Python is hostile until proved otherwise.** Static validation, import allowlist, a sandboxed subprocess as a separate OS user with seccomp, no network, no credentials, resource caps — and a determinism probe, because non-determinism undermines every reproducibility claim MAYA makes.
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
