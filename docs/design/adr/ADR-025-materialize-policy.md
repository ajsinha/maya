# ADR-025 — `materialize_policy`: a feature-set pin not written is sealed by hash and replayed

**Status:** Accepted, 0.3.0 (2026-09-19); recorded in specification revision 2.3. Amends
ADR-004.

## Context

D-1 (ADR-004) made storing a feature-set pin's resolved output the default and left it
configurable per namespace, naming a configuration key, `featureset.pin.materialize`. Two
things were wrong with that as built. A per-namespace choice cannot be one global key; it
belongs to the namespace, where its administrator can see and change it. And "when `never`,
resolution replays deterministically from member pins" said nothing about what happens when
the replay does not come back the same — which is the only case that matters.

## Decision

- The choice is the namespace's **`materialize_policy`: `always` (the default),
  `on_demand` or `never`**, changed like any other namespace setting and audited.
- Under `on_demand` and `never`, a pin is **sealed by the content hash of its resolved
  output with nothing written**. A read replays it from its recorded member pins and serves
  it **only if the replay reproduces that hash exactly**; otherwise the read fails with
  `integrity_error` — *"Replaying this pin from its member pins did not reproduce its sealed
  content (sealed …, replayed …); it is not served"*. Under `on_demand` the first successful
  replay is written, and later reads come from the lake.
- Integrity verification replays such pins the same way, and reports a failed replay as drift.

## Consequences

- A namespace can trade disk for a dependency: an unwritten pin is only as readable as the
  resolver's determinism. If a later MAYA resolved those inputs differently by one byte, the
  pin would be refused — safe, never wrong numbers, but unavailable. `always` has no such
  dependency, which is why it stays the default.
- An upgrade can therefore surface as integrity drift on replayed pins, with no byte of the
  lake changed. The [integrity drift runbook](../../operations/runbooks/integrity-drift.md) says how to tell
  the two apart.
- Changing the policy affects pins sealed afterwards; pins already sealed keep the
  materialization recorded in their manifest.

## References

- Specification §6.6, §26.3 (D-1, revision 2.3 note); README *Not yet*.
- Code: `maya/services/featuresets.py` (`_materialize`, `stored`, `pin_table`, `replay`,
  `verify_pin`), `maya/services/access.py` (`MATERIALIZE_POLICIES`, `update_namespace`),
  `maya/persistence/models/identity.py` (`materialize_policy`), `maya/services/ops.py`
  (`verify_integrity`).
- Tests: `tests/test_materialization.py` — `test_every_policy_seals_the_same_content`,
  `test_never_replays_every_read_and_serves_the_same_rows`,
  `test_on_demand_is_written_at_the_first_read`,
  `test_integrity_verification_replays_unwritten_pins`,
  `test_a_replay_that_does_not_reproduce_the_seal_is_not_served`,
  `test_an_unknown_policy_is_refused`.
