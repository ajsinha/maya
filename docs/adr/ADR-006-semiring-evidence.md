# ADR-006 — Semiring-annotated provenance as the single evidence engine

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
MAYA must answer at least nine different questions about the same evidence structure: is there sufficient
evidence, what minimal set would satisfy an examiner, how confident are we, what classification does a
derived artifact inherit, which regimes accept this evidence, what is the cheapest way to close a gap, and
as of when is a claim current. Building nine engines guarantees they will disagree — and disagreement in an
evidence system is an audit finding.

## Decision
Implement provenance once, generically over a **commutative semiring** (Green–Karvounarakis–Tannen), using
`⊗` for joint dependence and `⊕` for alternative derivations. Provide nine semiring instances. Materialise
`ℕ[X]` (how-provenance, the universal semiring) for Tier 1 evidence and the cheaper `Why(X)` form below,
evaluating other semirings by homomorphism on demand.

## Consequences
- **+** Nine product capabilities from one implementation, guaranteed mutually consistent (law L-9).
- **+** A tenth analysis is a new semiring — roughly twenty lines — and is automatically consistent with
  the other nine.
- **+** Classification propagation and regime admissibility stop being bespoke code paths.
- **−** `ℕ[X]` polynomials can grow large on deep derivations. Mitigated by tier-based materialisation,
  depth limits, memoisation and periodic normalisation.
- **−** The abstraction is unfamiliar. Mitigated by confining it to `core/evidence/` behind a plain
  `EvidenceEngine.evaluate(claim, derivations, semiring, valuation)` API.

## As built

**Six semiring instances, not nine**, in `core/evidence/semirings.py`: `boolean`, `counting`, `why`,
`trust`, `cost`, `freshness`. The three not built are `ℕ[X]`, the security lattice for classification
propagation, and the regime-admissibility powerset.

`ℕ[X]` not being built has one consequence worth naming rather than leaving to be discovered:
**materialisation by homomorphism is not what happens.** There is no universal object to push forward
from, so each semiring is evaluated by its own traversal of the same memoised derivation DAG. That
costs a traversal per question and makes law L-9 vacuous as stated. It also removes the multiplicities
`ℕ[X]` would have carried, and no governance question we have found asks for one.

`Why(X)` is stored for every tier rather than below Tier 1, with absorption applied on every `⊕` and a
hard cap of 4,096 terms that sets `truncated = true` on the result.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
