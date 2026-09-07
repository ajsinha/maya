# ADR-010 — The laws enforced by tests in CI

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

## As built

*An ADR records a decision; this section records how far the decision has been carried out, because the
decision above is the one thing in this document a reader could mistake for a description.*

There is **no `tests/laws/` package**. The executable laws live beside the code they constrain —
`tests/test_risk.py` (L-4, L-5), `tests/test_domain.py` (L-7, L-12), `tests/test_evidence.py` (L-18),
`tests/test_composition.py` (L-19), `tests/test_grammar.py` and `tests/test_api.py` (the eleven
warrant-admissibility laws). Hypothesis is used for L-4 and nowhere else; the rest are exhaustive or
example-based, which is adequate for a finite lattice and honest about being so.

The law count is now **twenty-one** foundational plus fourteen warrant laws. Of the twenty-one,
**eighteen** are executable and enforcing; three — `L-6`, `L-11` and `L-13` — are stated and not yet
executable, each marked as such in
[00 §12](../00-mathematical-foundations.md#12-the-laws-maya-enforces). Every warrant law runs.

This paragraph has been wrong three times, in three different directions — it undercounted the
foundational laws, undercounted the warrant laws, and undercounted the executable ones — and each
number was true on the day somebody typed it. The counts above are now derived by
`tests/test_documentation_counts.py` from the table in `00 §12` and from the code, so this paragraph
fails the build rather than ageing quietly. (The historical figures are deliberately not repeated
here: a document that recites its own old numbers gives that check something to match.)

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
