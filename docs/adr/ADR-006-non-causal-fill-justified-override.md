# ADR-006 — D-3: non-causal fill in a training set is a justified override

**Status:** Accepted, 2026-09-17.

## Context

Some fill rules look forward in time: backward fill, interpolation, a negative as-of lag.
In a training set they leak the future into the past, and a model trained on them backtests
better than it will ever trade. Sometimes that is harmless or deliberate — a slowly moving
reference field back-filled over a gap of days — and sometimes it is the defect that makes a
model's validation meaningless. The three available positions were a silent allow, a bare
block, or an override that has to be argued for.

A silent allow is the leak. A bare block is routed around: the quant fills the data in a
notebook and uploads the result, and the leak is still there with no record of it.

## Decision

**Override with a written justification, never a silent allow and never a bare block.** The
resolver flags every non-causal rule it applied. A training warrant over such a set is
refused unless the warrant's spec sets `allow_non_causal` and carries a
`non_causal_justification`; the justification is then recorded on the warrant and as a named
exception on its signed leakage certificate, whose status becomes
`certified_with_exceptions`. Late knowledge — rows known after their event date plus the
lag — is treated the same way, with `leakage_justification`.

## Consequences

- The override is possible, and permanently visible to whoever reviews the warrant or
  reads its certificate.
- A justification is free text. MAYA records the argument; it cannot judge it. The reviewer
  still has to read it.
- **The justified path has no test of its own.** The refusal of late knowledge is tested
  end to end, and non-causality is tested through every rule and operator of the algebra,
  but no test drives a warrant through `allow_non_causal` to `certified_with_exceptions`.

## References

- Specification §5.3, §26.3 (D-3), §29.1; plan §4.1.
- Code: `maya/resolution/rules.py` (`non_causal`), `maya/resolution/algebra.py`,
  `maya/services/warrants.py` (the leakage certificate).
- Tests: `tests/test_warrants.py::test_leakage_certificate_refuses_late_knowledge`;
  `tests/test_resolution_edges.py::test_non_causal_rules_are_flagged_and_causal_ones_are_not`,
  `::test_non_causality_propagates_through_every_binary_operator`,
  `::test_a_negative_as_of_lag_is_named_as_look_ahead`.
