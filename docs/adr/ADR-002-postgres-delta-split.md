# ADR-002 — Postgres for governance, Delta Lake for data-plane volume

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
Two data populations with incompatible characteristics. Governance data is small (10⁵ models, 10⁶
versions), highly relational, transactional, and read with complex joins. Feature values, inference logs
and monitoring observations are large (10¹¹ rows), append-mostly, columnar, and read analytically.
Both must be auditable and time-travellable.

## Decision
Split by **data gravity**, with five rules:
- **R1** anything in a governance decision transaction → Postgres.
- **R2** anything whose volume scales with business events → Delta.
- **R3** Postgres never stores feature or telemetry *values*, only definitions and pinned pointers.
- **R4** Delta never stores authoritative governance *state*.
- **R5** cross-store writes use the transactional outbox pattern.

## Consequences
- **+** Delta's `VERSION AS OF` supplies the transaction-time axis that makes point-in-time correctness
  verifiable rather than aspirational.
- **+** Retention economics work: 100B inference-log rows are affordable in object storage and not in Postgres.
- **+** Postgres RLS gives a real last line of defence for cross-entity isolation.
- **−** Two consistency models. Mitigated by the outbox pattern, idempotent writers and nightly reconciliation.
- **−** Operational surface is larger: Spark expertise required. Mitigated by confining Spark to the data
  plane and using `delta-rs` for small reads and writes.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
