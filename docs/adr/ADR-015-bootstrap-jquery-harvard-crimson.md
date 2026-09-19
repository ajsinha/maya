# ADR-015 — Bootstrap 5 and jQuery, vendored, on a Harvard Crimson token set

**Status:** Accepted, 2026-09-17. **Amended by ADR-020** (CodeMirror 5) and **ADR-021**
(the dark `--maya-crimson-deep` value), both revision 2.2.

## Context

MAYA's UI has to run in a bank's locked-down browser, be served by an air-gapped server, and
be maintainable by the people who maintain the Python. A JavaScript build pipeline — npm,
a bundler, a lockfile of hundreds of transitive packages — fails all three: it cannot be
installed offline without a mirror, it is a supply chain nobody reviews, and it is a second
toolchain for a team that has one. The rule is therefore "no build pipeline", and every
choice below follows from it.

## Decision

- **Bootstrap 5 and jQuery, vendored** under `maya/web/static/vendor/` with Bootstrap Icons,
  Cytoscape.js (lineage), KaTeX and CodeMirror — pinned files served as they are, no
  bundler, no CDN.
- **Theming through CSS custom properties**, not a Sass rebuild: the Harvard Crimson set of
  §16.6 is defined in `maya/web/static/css/tokens.css`, the only place a colour is defined,
  with a light and a dark scheme.
- **Contrast is computed, not asserted**: `tools/ci/contrast.py` recomputes every
  foreground/background token pair from `tokens.css` and fails the build below 4.5:1 for
  text and 3:1 for non-text, in both schemes.

## Consequences

- No build step means no tree-shaking and no modern module libraries: a library that ships
  only as ES modules for a bundler cannot be used. That is exactly how CodeMirror 6 was
  lost (ADR-020).
- Upgrading a vendored library is a deliberate file replacement, reviewed as a diff. Nothing
  upgrades itself.
- The contrast gate earned its place on the first build: it caught the specification's own
  dark `--maya-crimson-deep` at 2.20:1 (ADR-021). It has no planted-violation test.
- Templates carry no inline script, so the Content Security Policy needs no
  `unsafe-inline`; a test fails any template that would need it.

## References

- Specification §16, §16.6; plan §4.2, M0.
- Code: `maya/web/static/vendor/`, `maya/web/static/css/tokens.css`,
  `maya/web/static/css/theme.css`, `tools/ci/contrast.py`.
- Tests: `tests/test_web.py::test_static_vendor_assets_served`;
  `tests/test_browser.py::test_no_template_carries_script_the_csp_would_block`,
  `::test_the_theme_toggle_switches_and_is_remembered`; `tools/ci/gates.py` runs the
  contrast gate.
