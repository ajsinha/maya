# ADR-003 — `maya_delta` beside `maya`, not inside it

**Status:** Accepted, 2026-09-17 (plan §3, taken in M0). The engine choice itself is
ADR-009.

## Context

MAYA writes every pin to Delta tables (§7.4). The code that does so is a general Delta
Lake implementation — a transaction log, snapshots, checkpoints, compaction, vacuum —
with nothing in it about features, pins or warrants. Two things follow. It has to be
testable on its own, against a conformance suite both of its backends must pass
identically, without a MAYA platform standing up around it. And it has to be
replaceable: a Delta implementation buried in the product package gets domain knowledge
leaking into it one convenient import at a time, and then it is neither.

## Decision

`maya_delta/` is its own top-level package beside `maya/`: the facade and backend
selection in `maya_delta/__init__.py`, the `deltalake`-backed backend in
`maya_delta/native.py`, MAYA's own protocol implementation in `maya_delta/pure/`, and the
conformance suite in `maya_delta/conformance/`. MAYA reaches it through one place —
`maya/storage/lake.py`, the `LakeStore` port of §25 — and nowhere else.

## Consequences

- `maya_delta` imports nothing from `maya`, and `maya` imports `maya_delta` only in
  `maya/storage/lake.py`. Both hold today. **Neither is gated**: `tools/ci/import_boundaries.py`
  checks the SQLAlchemy and web boundaries, not this one, and `tools/ci/seam_imports.py`
  only confines `deltalake` to `maya_delta`. The independence is a convention the code
  keeps, not a rule the build enforces.
- The conformance suite runs against both backends, and across them, without a platform
  (`tests/test_maya_delta.py`). That is what lets a pure-Python Delta implementation be
  trusted at all (ADR-009).
- Both packages ship in the one `maya` distribution (`pyproject.toml`); `maya_delta` is
  not published separately.

## References

- Specification §7.4, §25; plan §3, M2.
- Code: `maya_delta/`, `maya/storage/lake.py`, `tools/ci/seam_imports.py`.
- Tests: `tests/test_maya_delta.py` — `test_conformance`,
  `test_cross_backend_round_trip`, `test_backend_selection_is_reported`.
