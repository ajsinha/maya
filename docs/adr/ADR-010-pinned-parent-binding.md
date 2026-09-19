# ADR-010 — D-7: `extends` binds to a pinned parent by default

**Status:** Accepted, 2026-09-17.

## Context

A feature or feature set can `extend` a parent and store only its overrides (§5.8, §6.8).
The parent then changes. Either the child follows — upstream fixes propagate for free — or
it stays on the version it was built against. Following is convenient and is exactly the
drift MAYA exists to remove: a child whose numbers change on a Tuesday because somebody
edited something it depends on, with no version of the child minted and nobody reviewing
the child.

## Decision

**`pinned` by default.** A child binds to one approved parent version and never changes
without being touched. `tracking` — follow the parent — is opt-in per object and **blocked
outright in production namespaces**. A pinned binding is accepted only if the parent is an
approved version, which cannot itself change.

## Consequences

- Upstream fixes do not propagate on their own. Somebody has to rebase the child, and that
  is a new child version, reviewed like any other.
- What it buys: a child's behaviour never changes without the child being touched.
- In a production namespace, `tracking` is refused at validation: *"'tracking' parent
  binding is blocked in production namespaces (D-7)"*.

## References

- Specification §5.8, §6.8, §26.3 (D-7); plan §4.1.
- Code: `maya/services/catalog.py` (binding validation, `pinned_parent_errors`),
  `maya/services/features.py` (`clone` with `extend=True`).
- Tests: `tests/test_features.py::test_tracking_binding_is_blocked_in_production`.
