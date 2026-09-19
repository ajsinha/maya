# ADR-019 — Catalog search is MAYA's own inverted index, on both databases

**Status:** Accepted, revision 2.2 (2026-09-19). Replaces the search backends of §13.4.2
and §14.1 (PostgreSQL `tsvector`, SQLite FTS5) for now.

## Context

The specification planned full-text search on each database's native engine, with a scan as
the fallback. Two things argued against building that first. SQLite FTS5 is not compiled into
every Python's bundled SQLite, so it has to be detected rather than assumed — a seam with two
real sides to keep equivalent. And the two native engines tokenize, stem and rank
differently, so the same query would return different results on the two supported
databases, which is exactly the kind of difference the persistence layer exists to remove.

## Decision

**MAYA's own inverted index**, in the `search_terms` table, identical on SQLite and
PostgreSQL. Every write to a searchable object re-indexes it in the same transaction, through
a session hook, so the index never describes a state that did not commit. Queries are
tokenized like the documents; every term must match, as a prefix; hits are ranked by the
field they matched (name, then tags, then namespace and description) and filtered by the
caller's read permission, so a search never names an object the caller cannot read. The index
is derived data: startup rebuilds it when it is empty but the catalog is not, and an
administrator can rebuild it on demand (`POST /api/v1/search/reindex`).

## Consequences

- One behaviour on both databases, and one code path to test.
- No stemming, no language awareness, no phrase search. The `tsvector` and FTS5 backends
  follow if catalog size makes them matter; 100,000-object search already passes its target
  on SQLite (`docs/BENCHMARKS.md`).
- The specification's revision note at the top of the document calls this "a scan before
  FTS"; §13.4.2 and the code say an inverted index, which is what ships.

## References

- Specification §13.4.2, §14.1, revision 2.2 note; `docs/BENCHMARKS.md`.
- Code: `maya/persistence/search_index.py`, `maya/services/ops.py` (`search`,
  `reindex_search`), `maya/core/backends.py` (the `search` seam, one backend).
- Tests: `tests/test_search.py` — `test_the_index_follows_edits_in_the_same_transaction`,
  `test_a_failed_transaction_leaves_the_index_untouched`,
  `test_search_never_names_what_the_caller_cannot_read`,
  `test_the_index_rebuilds_when_emptied_and_on_request`.
