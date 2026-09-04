# Architecture Decision Records

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

Format: context → decision → consequences. Status is one of `proposed`, `accepted`, `superseded`.

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-modular-monolith.md) | Modular monolith with one extracted warrant service | accepted |
| [002](ADR-002-postgres-delta-split.md) | Postgres for governance, Delta Lake for data-plane volume | accepted |
| [003](ADR-003-para-stoch-model-definition.md) | `Para(Stoch)` as the universal definition of a model | accepted |
| [004](ADR-004-fibration-extensibility.md) | Model classes as fibres, delivered as plugins | accepted |
| [005](ADR-005-institutions-for-regimes.md) | Institutions for multi-regulator scoping | accepted |
| [006](ADR-006-semiring-evidence.md) | Semiring-annotated provenance as the single evidence engine | accepted |
| [007](ADR-007-warrant-protocol.md) | Signed, TTL'd, alias-aware warrant descriptors | accepted |
| [008](ADR-008-server-rendered-ui.md) | Server-rendered Jinja2 + Bootstrap + jQuery, no SPA | accepted |
| [009](ADR-009-no-untrusted-deserialisation.md) | Sandbox-only artifact loading and a format policy | accepted |
| [010](ADR-010-laws-as-tests.md) | The laws enforced by tests in CI | accepted |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
