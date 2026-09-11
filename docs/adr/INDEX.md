# Architecture Decision Records

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

Format: context → decision → consequences. Status is one of `proposed`, `accepted`, `superseded`.

Two rows carry a second note, because status alone was misleading. ADR-008 is superseded on paper
and is an accurate description of what runs today; ADR-011 supersedes it and describes something
that has not been built. A reader who trusted the status column would have had it exactly backwards,
and this index previously omitted 011 altogether while showing 008 as accepted.

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-modular-monolith.md) | Modular monolith with one extracted warrant service | accepted |
| [002](ADR-002-postgres-delta-split.md) | Postgres for governance, Delta Lake for data-plane volume | accepted |
| [003](ADR-003-para-stoch-model-definition.md) | `Para(Stoch)` as the universal definition of a model | accepted |
| [004](ADR-004-fibration-extensibility.md) | Model classes as fibres, delivered as plugins | accepted |
| [005](ADR-005-institutions-for-regimes.md) | Institutions for multi-regulator scoping | accepted |
| [006](ADR-006-semiring-evidence.md) | Semiring-annotated provenance as the single evidence engine | accepted |
| [007](ADR-007-warrant-protocol.md) | Signed, TTL'd, alias-aware warrant descriptors | accepted |
| [008](ADR-008-server-rendered-ui.md) | Server-rendered Jinja2 + Bootstrap + jQuery, no SPA | superseded by 011 — **but it is what ships** |
| [009](ADR-009-no-untrusted-deserialisation.md) | Sandbox-only artifact loading and a format policy | accepted |
| [010](ADR-010-laws-as-tests.md) | The laws enforced by tests in CI | accepted |
| [011](ADR-011-decoupled-frontend.md) | Front end and backend as separate processes | accepted — **not built** |
| [012](ADR-012-per-audience-warrant-keys.md) | Per-audience warrant keys instead of asymmetric signing | accepted — **supersedes** the asymmetric-signing item that led the roadmap |
| [013](ADR-013-cursors-and-offsets.md) | Offsets for people, cursors for queues | accepted |
| [014](ADR-014-attested-not-observed.md) | Attested, not observed — the rule under five capabilities | accepted |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
