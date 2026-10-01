# ADR-018 — One startup script: `run_maya_web.py`

**Status:** Accepted, 2026-09-17.

## Context

Every way of starting a server carries its own startup invariants: the multiprocessing start
method, configuration path and overrides, logging, signal handling, the order in which the
schema is checked and the refusals run. Two ways of starting — a script and a
`uvicorn maya.server:app` line in somebody's service file — are two sets of invariants, and
the second is the one that skips the schema check.

## Decision

**`python run_maya_web.py` is the only supported way to start MAYA.** It sets the `spawn`
start method before anything else imports, loads and validates the configuration (path by
`--config=` or `MAYA_CONFIG_FILE`, any setting by `--section.key=value`), configures
logging, builds the platform — which verifies the schema identity, seeds, runs the startup
refusals and requeues jobs a dead process left running — prints a banner naming the version,
database and schema file, `maya_delta` backend and why, sandbox tier, storage root, workers
and every seam on a fallback, installs signal and `atexit` drain handlers, and serves.

## Consequences

- Every refusal that protects a deployment — schema mismatch, prod on SQLite, several web
  processes on SQLite, the default admin password outside dev, SSO misconfiguration, a
  sandbox below its minimum tier — runs on every start, because there is no other start.
- The CLI's `--local` mode builds the same platform in process, and the database commands
  (`admin init-db`, `export-estate`, `import-estate`) deliberately run beside the server
  rather than through it (§14.3).
- `--help` prints the usage and banner without building anything.

## References

- Specification §24.2, §24.5; plan M0.
- Code: `run_maya_web.py`, `maya/services/platform.py` (`Platform.build`,
  `startup_checks`), `maya/server.py`.
- Tests: `tests/test_api_and_gates.py::test_real_server_over_http_with_sdk_and_cli`;
  `tests/test_web_processes.py`.
