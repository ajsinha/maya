# ADR-022 — Several web processes need PostgreSQL; MAYA refuses them over SQLite

**Status:** Accepted, revision 2.3 (2026-09-19). Extends ADR-013.

## Context

One Python process serves roughly 40 page requests a second (`docs/quality/BENCHMARKS.md`), so the
200-user target of SC-3 needs several web processes on one node. On SQLite, MAYA serialises
its writes through a mutex in the unit of work, and that mutex is what makes read-then-write
steps atomic — linking each audit entry to the previous one's hash, numbering the next
version. The mutex lives in one process. Across processes it does not exist, and two
processes linking the audit chain at the same moment would fork it: a tamper-evident log
that reports tampering nobody did.

## Decision

`server.workers` above 1 **requires PostgreSQL**, and MAYA refuses to start the combination:

```text
server.workers is 2, but the database is SQLite, which admits one writing process. Use
PostgreSQL (db.dialect: postgresql) for several web processes, or set server.workers: 1.
```

With several web processes, the launching process alone prepares the database, seeds, and
keeps the job workers, webhook dispatcher and scheduler; a job submitted through any web
process is a row its workers pick up. On Linux each web process binds its own
`SO_REUSEPORT` socket so the kernel spreads connections evenly, and the launcher restarts
any web process that dies.

## Consequences

- SQLite deployments are one process, which is what SQLite is for.
- Anything held in a process is now per process: Prometheus metrics, and the principal
  cache, which is why a sign-out can take up to its window to reach another process
  (ADR-026).
- SC-3 is still not met reliably on the shared workstation that is the only benchmark
  host: p95 0.34, 0.22 and 0.43 s against 0.3 s over three runs with eight processes.

## References

- Specification §14.1 (revision 2.3 note), §24.3, SC-3; `docs/quality/BENCHMARKS.md`.
- Code: `run_maya_web.py` (`main`, `_supervise`), `maya/server.py`
  (`check_web_processes`, `balanced_sockets`, `serve_web_process`),
  `config/application.yaml` (`server.workers`).
- Tests: `tests/test_web_processes.py` — `test_sqlite_refuses_several_web_processes`,
  `test_requests_are_served_by_more_than_one_web_process`,
  `test_a_job_submitted_through_a_web_process_runs_in_the_launcher` (the last two need
  PostgreSQL).
