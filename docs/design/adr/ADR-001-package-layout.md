# ADR-001 — Everything under `maya/`, not at the repository root

**Status:** Accepted, 2026-09-17 (plan §3, taken in M0).

## Context

DishtaYantra, the project MAYA borrows most of its idioms from, puts `core/`, `routes/`
and `web/` at the repository root. MAYA cannot, for two reasons that are both about
boundaries.

The specification names packages as boundaries a gate must enforce: nothing outside
`maya.persistence` may import SQLAlchemy (§14), and nothing under `maya.web` may reach
deeper than `maya.sdk` (§16). A boundary that is a directory at the root is a boundary
a gate cannot name reliably — `web` could be anybody's `web`. The second reason is the
SDK (§18.2.3): a client that must one day install without the server needs a real
package root to be cut from.

## Decision

The product is one importable package, `maya/`, with its subpackages beneath it
(`api`, `cli`, `config`, `core`, `persistence`, `resolution`, `sdk`, `security`,
`services`, `storage`, `web`, `workflow` and the rest). Beside it sit exactly three
other things that are not the product package: `run_maya_web.py`, the one entry point
(ADR-018); `maya_delta/`, the lakehouse layer (ADR-003); and `config/`, `tools/`,
`tests/`, `docs/`. Inside the package, DishtaYantra's idioms are kept unchanged —
the properties configurator, the banner, the `--key=value` overrides.

## Consequences

- The import boundaries are enforced mechanically, by module name:
  `tools/ci/import_boundaries.py` fails on `sqlalchemy` outside `maya.persistence` and on
  anything under `maya.web` importing a `maya` module other than the SDK. Both are seen
  to fail on a planted violation, which is the only evidence that a gate works.
- A developer who knows DishtaYantra finds the same idioms one directory deeper.
- **Not delivered: the separate SDK distribution.** `pyproject.toml` builds one
  distribution, `maya`, containing both server and SDK, and its dependencies are the
  whole of `requirements.txt`. The layout makes the split possible; it has not been
  made, so installing the SDK today installs the server with it.
- Plan §3 draws `domain/` and `ports/` subpackages. They do not exist: domain rules live
  in `maya/services/` and the ports are the repository and lake interfaces in
  `maya/persistence/` and `maya/storage/`. The drawing is older than the code.

## References

- Specification §13, §14, §16, §18.2.3, §22.3; plan §3.
- Code: `maya/`, `pyproject.toml` (`[tool.setuptools.packages.find]`),
  `tools/ci/import_boundaries.py`.
- Tests: `tests/test_api_and_gates.py` —
  `test_gate_fails_on_a_planted_violation[import_boundaries.py]`,
  `test_web_import_boundary_fails_when_web_reaches_past_the_sdk`.
