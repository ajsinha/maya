# ADR-011 — D-8: one parameter set per composite, namespaced by member alias

**Status:** Accepted, 2026-09-17.

## Context

A composite model is a DAG of member models (§8.7). Each member has parameters. They can be
kept as one set per member — reusable across composites, independently approved — or as one
set for the whole composite. Per-member sets are more flexible, and they mean a composite's
behaviour is the product of several separately versioned, separately approved things, any of
which can move. Reproducing it then means reassembling the right combination.

## Decision

**One parameter set per composite**, its keys namespaced by member alias (`base.a`,
`skew.b`); the composite's own combining parameters are unprefixed. Per-member seeds are
derived deterministically from the composite's one seed. A member may be `frozen` only if it
borrows an approved parameter set.

## Consequences

- The composite reproduces as one unit, under one training warrant (§9.5).
- Cross-composite reuse of parameters is less convenient: a member's parameters live inside
  each composite's set.

## References

- Specification §8.7, §9.5, §26.3 (D-8); plan §4.1.
- Code: `maya/formula/composite.py` (`member_seeds`, structure validation);
  `maya/formula/evaluate.py` (`evaluate_composite`).
- Tests: `tests/test_formula.py::test_composite_union_maturity_seeds_and_eval`,
  `::test_composite_reference_code_matches_the_evaluator`;
  `tests/test_sdk_modes.py::test_a_composite_model_is_re_executed_by_the_bundle_verifier`.
