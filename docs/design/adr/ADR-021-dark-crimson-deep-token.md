# ADR-021 — The dark `--maya-crimson-deep` token is `#E07A8E`

**Status:** Accepted, revision 2.2 (2026-09-19). Corrects §16.6.

## Context

The specification gave `--maya-crimson-deep` the value `#A51C30` in the dark scheme — the
same as the light scheme's crimson. On the dark surface it measures **2.20:1**, which fails
the specification's own contrast rule even for non-text (3:1), let alone text (4.5:1). The
contrast gate (ADR-015) caught it on the first build. A document that states a rule and
violates it in its own palette is the case for computing contrast rather than asserting it.

## Decision

The dark value is **`#E07A8E`** (5.74:1 on the dark surface). The light value is unchanged.
Headings use a separate `--maya-heading` token, because a deep crimson that is fine for rules
and borders is too faint for heading text on the dark canvas.

## Consequences

- The dark scheme's deep crimson is lighter and pinker than the brand crimson. The brand
  concedes a little to legibility, not the reverse.
- `tokens.css` is the only place colours are defined, so the fix was one line and every
  screen took it.

## References

- Specification §16.6 (revision 2.2 note).
- Code: `maya/web/static/css/tokens.css`, `tools/ci/contrast.py`.
- Tests: the contrast gate, run by `tools/ci/gates.py`; it has no planted-violation test —
  this token was its real one.
