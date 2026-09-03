# ADR-007 — Signed, TTL'd, alias-aware hook descriptors

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
Execution engines must be able to run any governed model version on demand. Three designs were considered:
(a) publish endpoints and let engines call them; (b) have MAYA proxy every inference; (c) have MAYA issue a
resolvable, signed execution contract that engines act on themselves.

## Decision
Option (c). A hook is a **signed, expiring, entitlement-bound descriptor** resolved from a stable URN.
Bindings are either pinned versions (mandatory for regulatory submissions) or aliases (`champion`,
`challenger`, `shadow`). Eleven flavours cover REST/OIP-v2 through to `descriptor_only` for engines MAYA
will never host.

## Consequences
- **+** Consumers hold only a URN; governed version moves require no consumer redeployment.
- **+** Governance is enforced *at execution*: no valid entitlement for an approved use, no execution.
- **+** MAYA is not on the inference hot path, so it cannot become the bank's scoring bottleneck.
- **+** Descriptor TTL plus a grace window means a MAYA outage does not stop already-authorised production
  scoring — governance is not a single point of failure.
- **+** Telemetry from resolution enables approved-use vs actual-use reconciliation, which no surveyed
  product offers.
- **−** Revocation is not instantaneous; it is bounded by TTL (≤ 60 s for Tier 1 with the event path).
  Accepted, and made explicit rather than hidden.
- **−** Clients must implement verification correctly. Mitigated by shipping SDKs that do it, and by
  refusing telemetry from unverified clients.
