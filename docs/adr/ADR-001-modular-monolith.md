# ADR-001 — Modular monolith with one extracted hook service

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
The governance domain is densely interconnected: a single promotion decision reads inventory, versions,
evidence, findings, overlays, policy and monitoring, and must be transactionally consistent. Meanwhile
hook resolution sits on the critical path of production scoring with a 10× tighter latency and
availability target than anything else in the system.

## Decision
Build `maya-control` as a **modular monolith** with strictly enforced internal boundaries (import-linter
contracts, hexagonal dependency rule). Extract exactly one service — `maya-hooks` — for resolution,
signing and revocation. Workers and sandboxes are separate processes but not separate domains.

## Consequences
- **+** Governance decisions are ACID transactions, not sagas. No eventual-consistency bugs in the place
  where correctness matters most.
- **+** One deployment, one migration path, one test suite for the domain.
- **+** The hook plane scales, fails over and is hardened independently, and survives control-plane outage.
- **−** The monolith will grow; boundaries must be enforced mechanically or they will erode. Mitigated by
  CI-enforced import contracts.
- **−** A single bad deploy affects all governance functions. Mitigated by blue/green and canary.
- Future extraction of a context (e.g. the feature platform) remains possible because the boundaries are
  already explicit.
