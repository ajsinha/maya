# ADR-004 — Model classes as fibres, delivered as plugins

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
The requirement is that *"all kinds of models under the sun — big or small — are fair game"*, including
kinds nobody has invented yet. If the model class is a column, an enum or a table, every new class is a
schema migration touching every module — which in practice means new classes never get added and the
inventory silently excludes them.

## Decision
Make model classes the **base of a fibration**, not a column. A class supplies a *fibre*: evidence schema
(JSON Schema), lifecycle specialisation, default monitors, document templates, tiering hints, contract
template, introspector, and validation tests. Fibres are registered through Python entry points. The same
pattern is applied to eight other extension points (regimes, semirings, artifact formats, tests, metrics,
templates, hook flavours, connectors).

## Consequences
- **+** **Extension theorem:** adding a model class requires supplying a fibre and nothing else. No DDL, no
  core code change, no API change, no UI change — the metadata form is generated from the fibre's schema.
- **+** A bank can ship proprietary classes as a private package without forking MAYA.
- **+** Law L-15 (fibre totality) is checked at startup, so a half-implemented class cannot reach production.
- **−** Class-specific data lives in JSONB, so it is less queryable than columns. Mitigated by GIN indexes,
  JSON path queries, and promoting genuinely cross-class attributes into columns when they stabilise.
- **−** Plugin loading is a supply-chain surface. Mitigated by signed packages and an allow-list.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
