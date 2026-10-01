# ADR-004 — D-1: feature-set pins are materialized by default

**Status:** Accepted, 2026-09-17. **Amended by ADR-025** (0.3.0): the setting is the
namespace's `materialize_policy`, and a pin that is not written is sealed by hash and
replayed. The default — `always` — is unchanged.

## Context

A feature-set pin names its member pins, and the resolved frame can in principle be
rebuilt from them at any time. The question was whether to store that frame as well.
Rebuilding is cheaper on disk and depends on the resolver producing the same bytes years
later; storing it costs disk and removes that dependency. The original notes said
replay; the specification changed it deliberately (§6.6).

## Decision

**Always materialize.** Sealing a feature-set pin writes its resolved output to the lake
as content-addressed fragments, like any other pin, and verifies the written bytes
against the content hash before the pin is sealed.

## Consequences

- The price is disk, mitigated by content addressing: a set pin whose rows are already
  stored costs only the fragments that are new (SC-12, §29.3).
- What it buys is the difference between *"we can probably reproduce it"* and *"here are
  the bytes"*: a stored pin never depends on a later MAYA resolving the same inputs the
  same way. ADR-025 lets a namespace give that up, and names the price when it does.
- A cascade pin writes the members and the set in one saga, and rolls back whole if any
  member fails.

## References

- Specification §6.6, §26.3 (D-1), §29.3; plan §4.1.
- Code: `maya/services/featuresets.py` (`_materialize`, `stored`).
- Tests: `tests/test_materialization.py::test_every_policy_seals_the_same_content`;
  `tests/test_warrants.py::test_cascade_rolls_back_entirely_on_a_member_failure`.
