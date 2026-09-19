# ADR-008 — D-5: namespaces are per team, nesting one level

**Status:** Accepted, 2026-09-17.

## Context

The namespace is the unit of bulk permission, quota, recertification and export (§4, §11).
Too coarse — one per business line — and a grant to one desk's features reaches another
desk's; too fine — one per project — and nobody can recertify the resulting hundreds of
scopes, so nobody does. Deep hierarchies add a third problem: inherited permissions nobody
can predict without walking the tree.

## Decision

**One namespace per team, nesting one level** (`credit` and `credit.pd`, never deeper).
Namespaces are created by holders of the `C` capability on namespaces — administrators, in the shipped roles. Each individual also gets a scratch namespace,
created on first use, for ungoverned work (§28.1).

## Consequences

- Quota, recertification scope and export control are all per team, which is the
  granularity at which somebody is accountable for them.
- A second level of nesting is refused where it would be created and where it would be
  named: `create_namespace` refuses a parent that already has one, and the reference
  parser refuses a path with more than one namespace segment.
- **Neither refusal has a test of its own.** The one-level rule is enforced in code and
  exercised nowhere in the suite.

## References

- Specification §4, §11, §26.3 (D-5), §28.1; plan §4.1.
- Code: `maya/services/access.py` (`create_namespace`: *"Namespaces nest one level only
  (D-5)"*), `maya/services/refs.py` (`parse`).
- Tests: `tests/test_features.py::test_scratch_quick_feature_has_zero_ceremony` (the
  scratch namespace). None for the nesting rule.
