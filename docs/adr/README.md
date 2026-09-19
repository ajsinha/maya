# Architecture Decision Records

This directory is for anyone who needs to know **why** MAYA is built the way it is before
changing it: a maintainer about to reverse a decision, a reviewer asking whether a limit is
deliberate, a model risk function asking what was traded for what. A decision that is not
written down gets re-litigated every quarter, and one written down without its cost gets
reversed by the first person who only sees the cost.

Each record is short and has the same five parts: **Status**, **Context** (the failure the
decision prevents), **Decision**, **Consequences** — including what it costs and what is not
yet true — and **References** to the specification section, the code that carries it and the
tests that prove it. Every code path and test named was checked against the repository when
the record was written. Where a decision has no test, the record says so.

Specification §26.3 and plan §4 are the registers these records expand. Where a record and
the specification disagree, the record says which one the code follows and why. A record is
never deleted: a reversed decision is marked *Superseded* and points at its successor.

## Reading order

New to MAYA: read ADR-012 and ADR-023 (why there are no migrations, and the one upgrade path),
ADR-009 (the lakehouse), ADR-004 and ADR-025 (what a pin stores), ADR-007 (what MAYA will not
do), then ADR-014 (what is not exercised). The rest can be read when their subject comes up.

## Index

### Layout and working practice (plan §3, §10)

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-package-layout.md) | Everything under `maya/`, not at the repository root | Accepted; separate SDK distribution not built |
| [002](ADR-002-branch-and-release-workflow.md) | `develop` → `main`; the gate ladder runs locally and in the pre-commit hook | Accepted; no hosted CI |
| [003](ADR-003-maya-delta-beside-maya.md) | `maya_delta` beside `maya`, reached only through `LakeStore` | Accepted; independence not gated |

### The eight decisions of §26.3 (closed 2026-09-17)

| ADR | # | Decision | Status |
|---|---|---|---|
| [004](ADR-004-always-materialize-feature-set-pins.md) | D-1 | Feature-set pins are materialized by default | Accepted; amended by 025 |
| [005](ADR-005-pin-series.md) | D-2 | A pin name is a series; the as-of date selects within it | Accepted |
| [006](ADR-006-non-causal-fill-justified-override.md) | D-3 | Non-causal fill in a training set is a justified override | Accepted; justified path untested |
| [007](ADR-007-no-model-runtime-except-blind-scoring.md) | D-4 | No model runtime, except blind scoring | Accepted; exception narrower than §26.3 |
| [008](ADR-008-namespaces-per-team.md) | D-5 | Namespaces per team, nesting one level | Accepted; nesting rule untested |
| [009](ADR-009-maya-delta-lakehouse-engine.md) | D-6 | `maya_delta`: native `deltalake` preferred, pure-Python fallback | Accepted |
| [010](ADR-010-pinned-parent-binding.md) | D-7 | `extends` binds to a pinned parent by default | Accepted |
| [011](ADR-011-one-parameter-set-per-composite.md) | D-8 | One parameter set per composite, keyed by member alias | Accepted |

### The further calls (revision 2.1, 2026-09-17)

| ADR | Decision | Status |
|---|---|---|
| [012](ADR-012-no-migrations-two-generated-schema-files.md) | No migrations: two generated schema files | Accepted; amended by 023 |
| [013](ADR-013-sqlite-default-postgresql-by-config.md) | SQLite by default, PostgreSQL by configuration, never mixed | Accepted; extended by 022 |
| [014](ADR-014-platforms.md) | Platforms: only Linux is exercised | Amended by owner decision; SC-14 not met |
| [015](ADR-015-bootstrap-jquery-harvard-crimson.md) | Bootstrap 5 and jQuery, vendored, Harvard Crimson tokens | Accepted; amended by 020, 021 |
| [016](ADR-016-universal-table-contract.md) | Every table paginated, searchable, sortable, from one macro | Accepted |
| [017](ADR-017-workflow-policy-in-the-ui.md) | Workflow policy authored in the UI; YAML is a projection | Accepted |
| [018](ADR-018-one-startup-script.md) | One startup script, `run_maya_web.py` | Accepted |

### Revision 2.2 — corrections the first build proved (2026-09-19)

| ADR | Decision | Status |
|---|---|---|
| [019](ADR-019-own-inverted-index-search.md) | Catalog search is MAYA's own inverted index | Accepted |
| [020](ADR-020-codemirror-5.md) | CodeMirror 5, not 6 | Accepted |
| [021](ADR-021-dark-crimson-deep-token.md) | The dark `--maya-crimson-deep` is `#E07A8E` | Accepted |

### Revision 2.3 and version 0.3 (2026-09-19)

| ADR | Decision | Status |
|---|---|---|
| [022](ADR-022-several-web-processes-need-postgresql.md) | Several web processes need PostgreSQL | Accepted |
| [023](ADR-023-estate-export-reads-the-database-as-it-is.md) | The estate export reads the database as it is | Accepted |
| [024](ADR-024-saml-signed-requests-and-single-logout.md) | SAML signed requests and single logout, front channel | Accepted |
| [025](ADR-025-materialize-policy.md) | `materialize_policy`; unwritten pins sealed by hash and replayed | Accepted |
| [026](ADR-026-principal-cache-window.md) | A session's principal is reused for two seconds | Accepted |
| [027](ADR-027-oidc-logout-both-ways.md) | OIDC logout both ways | Accepted |
| [028](ADR-028-tsa-signature-checked-against-its-ca.md) | A TSA's signature checked against its CA, inside MAYA | Accepted |

## What these records do not cover

- **The two questions still open** (§26.3, plan §4.4) — which separation-of-duties preset the
  first namespaces get, and who seeds them — are not decisions yet, so they have no record.
- **Decisions below the level of the register** — the ten innovations of §29, the seam
  polarity rule of §13.4.1, the sandbox tiers — are argued in the specification itself and
  are not repeated here.
- **The code does not yet point back at these records.** Plan §10 asks for every
  architectural decision to be referenced from the code it governs; a handful of modules
  cite the D-numbers, none cites an ADR number.
