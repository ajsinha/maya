# ADR-009 — D-6: the lakehouse engine is `maya_delta`, native preferred, pure fallback

**Status:** Accepted, 2026-09-17. This is both D-6 of §26.3 and the "Lakehouse" call of
plan §4.2 — one decision, recorded once. Placement of the package is ADR-003.

## Context

Pins are written to Delta tables (§7.4). The first framing was "delta-rs only", to avoid a
JVM. The binding constraint turned out to be wider: `deltalake` is a native wheel, and an
air-gapped site, an unusual platform, or a broken wheel would leave MAYA unable to read its
own sealed data. A register whose evidence becomes unreadable when a wheel does is not a
register.

## Decision

**`maya_delta`, with two interchangeable backends.** `native` is delta-rs through the
`deltalake` wheel, chosen when it imports *and* passes a self-check (write and read a tiny
table). `pure` is MAYA's own implementation of a declared subset of the Delta
transaction-log protocol over pyarrow. `lake.backend: auto | native | pure` selects;
`auto` prefers native. No Spark, no JVM.

## Consequences

- An entire Delta implementation to write and keep honest. It is never trusted on its own:
  one conformance suite runs against both backends, tables written by each are read by the
  other, and interleaved writers are tested.
- **The pure backend refuses rather than approximates.** A table needing a protocol feature
  it does not implement — deletion vectors, v2 checkpoints, column mapping, an invariant it
  cannot enforce — raises `UnsupportedFeature` naming the feature.
- Selection is never silent: the chosen backend and why are in the banner, on the health
  page's `lake` section and in `/readyz`. Pinning `native` where it is unusable refuses to
  start. The operating procedure is the
  [maya_delta backend runbook](../../operations/runbooks/maya-delta-backend-fallback.md).
- Pure is slower; nothing in §24.3 has measured by how much.

## References

- Specification §7.4, §13.4, §26.3 (D-6); plan §4.1, §4.2, M2.
- Code: `maya_delta/__init__.py` (`select_backend`), `maya_delta/native.py`,
  `maya_delta/pure/`, `maya_delta/conformance/suite.py`, `maya/storage/lake.py`.
- Tests: `tests/test_maya_delta.py` — `test_conformance`, `test_cross_backend_round_trip`,
  `test_interleaved_writers`, `test_pure_reads_native_checkpoint`,
  `test_unsupported_reader_feature_is_refused_by_name`,
  `test_unsupported_writer_feature_is_refused_by_name`,
  `test_deletion_vector_on_a_file_is_refused`, `test_backend_selection_is_reported`.
