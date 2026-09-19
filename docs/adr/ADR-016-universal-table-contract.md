# ADR-016 — The universal table contract

**Status:** Accepted, 2026-09-17.

## Context

A governance platform is mostly tables: catalogs, pins, audit, jobs, grants, reviews.
Built one at a time, each ends up with its own idea of paging, searching and sorting, and
some with none — and the one with none is the audit log with forty thousand rows that
somebody needs to search during an incident. A rule that says "tables should be sortable"
is kept until the first deadline.

## Decision

**Every table is paginated, searchable and sortable, and is emitted by one macro,**
`maya/web/templates/_macros/table.html`, driven by `maya/web/static/js/table.js`. A gate,
`tools/ci/table_contract.py`, fails the build on any `<table>` in a template that did not
come from the macro. Large lists — features, feature sets, models, audit, events, jobs —
page from the server; smaller tables page in the browser.

## Consequences

- The macro has to be good enough that nobody wants to bypass it. If somebody does, that is
  a defect in the macro, not a reason to weaken the gate.
- In server mode a table sorts on the columns the server can order by, one key at a time,
  and searches the server's fields; lists filtered row by row for authorization compute an
  exact total by scanning. Those limits are stated in the README, not hidden.
- The gate was installed before the first table existed, so it has never had to be
  back-fitted, and it is seen to fail on a planted `<table>`.

## References

- Specification §16.7, SC-17; plan §4.2, §5.
- Code: `maya/web/templates/_macros/table.html`, `maya/web/static/js/table.js`,
  `tools/ci/table_contract.py`, `maya/services/paging.py`.
- Tests: `tests/test_web.py::test_only_the_macro_emits_tables`;
  `tests/test_api_and_gates.py::test_gate_fails_on_a_planted_violation[table_contract.py]`;
  `tests/test_browser.py::test_a_server_paged_table_pages_searches_and_sorts`;
  `tests/test_paging.py`.
