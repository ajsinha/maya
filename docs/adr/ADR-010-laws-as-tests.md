# ADR-010 — The sixteen laws enforced by property-based tests in CI

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
[00 — Mathematical Foundations](../00-mathematical-foundations.md) commits to abstractions that only pay
off if their laws actually hold in the implementation. Documented-but-unenforced theory decays into
decoration within two releases, and then actively misleads.

## Decision
Every law in [00 §12](../00-mathematical-foundations.md#12-the-laws-maya-enforces) is implemented as a
property-based test (Hypothesis) in `tests/laws/test_L01.py` … `test_L16.py`. **A failing law fails the
build.** The alternative — mechanised proof in Coq or Lean — was considered and rejected as
disproportionate, except for isolated components (e.g. tiering monotonicity) if a regulator ever requires
machine-checked evidence.

## Consequences
- **+** The theory stays true. Tier monotonicity, PIT correctness, lens laws, contract refinement,
  schema variance and the satisfaction condition are continuously verified against generated inputs.
- **+** Regression protection where it matters most: the PIT verifier is tested by adversarial leakage
  injection, so it cannot silently stop working.
- **+** The laws double as executable documentation of intent.
- **−** Property tests are slower than unit tests and can be flaky if generators are poorly bounded.
  Mitigated by bounded strategies, fixed seeds in CI, and a nightly deep run with wider generation.
- **−** Writing good generators requires skill. Accepted as a deliberate investment.
