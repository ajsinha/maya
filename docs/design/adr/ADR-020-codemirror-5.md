# ADR-020 — CodeMirror 5, not 6

**Status:** Accepted, revision 2.2 (2026-09-19). Corrects §17, which named CodeMirror 6.

## Context

MAYA has two embedded editors: Python for model artifacts and LaTeX for specification
documents (§17). The specification chose CodeMirror 6. CodeMirror 6 ships as ES modules
meant to be bundled, and the UI rule (ADR-015) is no build pipeline. The two cannot both
hold; the first build found that out.

## Decision

**CodeMirror 5**, vendored as a single file with its `python` and `stex` (LaTeX) modes, in
`maya/web/static/vendor/codemirror/`.

## Consequences

- CodeMirror 5 is in maintenance, not development. Its accessibility and mobile behaviour
  are older than 6's, and it will receive fewer fixes.
- The no-build rule survives intact, which is the thing it was chosen to protect.

## References

- Specification §16, §17 (revision 2.2 note).
- Code: `maya/web/static/vendor/codemirror/` (`codemirror.js`, `python.js`, `stex.js`),
  `maya/web/static/js/editors.js`, `maya/web/templates/_editor_scripts.html`.
- Tests: `tests/test_web.py::test_static_vendor_assets_served` (serves
  `codemirror.js`). No test drives the editors themselves.
