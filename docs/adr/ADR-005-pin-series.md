# ADR-005 — D-2: a pin name is a series, the as-of date selects within it

**Status:** Accepted, 2026-09-17. Answered first of the eight, because it could not be
answered later.

## Context

A pin is immutable and sealed, and other sealed objects — feature-set pins, training
warrants, bundles — refer to it. Whatever a pin's identity is, it is copied into those
references at the moment they are sealed. Changing the identity afterwards would mean
rewriting sealed references, which sealing forbids. So this had to be settled before the
first pin existed, and was.

The candidates were a pin name unique per feature, or a name that recurs — "the month-end
pin", taken every month.

## Decision

**A pin series.** `(feature, pin_name)` is the series and `as_of_date` selects one pin
within it; the natural key is `(feature_id, pin_name, as_of_date)` for feature pins and
`(feature_set_id, pin_name, as_of_date)` for feature-set pins. The reference grammar
follows: `maya://feature/<ns>/<name>#<series>/<YYYY-MM-DD>`.

## Consequences

- "The month-end series" is a browsable, subscribable object rather than a naming
  convention people must keep by hand.
- The same name and date can be pinned once. A failed attempt is the one exception: it
  is replaced by the next request rather than blocking that name and date for good.
- It cost nothing when taken. It could never be revisited without rewriting sealed
  references, which is the whole reason it was taken first.

## References

- Specification §4 (identity and naming), §14.2, §26.3 (D-2), §30 A; plan §4.1, §5.
- Code: `maya/persistence/models/catalog.py` (the unique constraints),
  `maya/services/refs.py` (the grammar), `maya/services/features.py` (`pin`).
- Tests: `tests/test_cli.py::test_pin_download_and_diff` (a pin read back by its
  `#series/date` reference); `tests/test_features.py` exercises `#eom/2026-01-10`
  references throughout.
