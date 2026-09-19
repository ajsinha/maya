# ADR-002 — Branch and release workflow: `develop` → `main`, gates run locally

**Status:** Accepted. In use from the first milestone merge (2026-09-03). Amended by the
owner's decision that there is no hosted CI (see ADR-014).

## Context

MAYA has one maintainer and no hosted CI. A release checklist that lives in someone's
head is a checklist that gets skipped on the evening it matters, and the plan says so in
as many words: the gate script is the authority, "never a remembered list" (plan §7).
What remains to decide is where work happens, what promotion means, and what stops a
bad commit when no server is watching.

## Decision

- **All work is committed on `develop`.** `main` receives only merges from `develop`,
  never a direct commit.
- **The owner's shorthand is binding.** *Drill* means: commit and push `develop`, merge
  `develop` into `main`, push `main`. *Drill to develop* is the first half only;
  *drill to main* is the merge and push only.
- **Promotion to `main`** requires the gate ladder green with the suite
  (`python tools/ci/gates.py --tests`), built artifacts newer than their sources (the
  specification's `.docx` and `.pdf`, rebuilt by `tools/docs/build_spec.py`), and a
  clean tree.
- **The gate ladder runs on the developer's machine**, in two places: the `pre-commit`
  hook runs `tools/ci/gates.py` (the static gates) before every commit, and
  `gates.py --tests` runs the full suite under a 90% coverage floor before promotion.
  `--fallback`, `--security` and `--bench` add the fallback matrix, the dependency scan and
  sandbox escape tests, and the benchmark regression check, on demand.
  The hooks are enabled per clone with `git config core.hooksPath .githooks`.
- **No assistant attribution.** The `commit-msg` hook refuses `Co-Authored-By: Claude`,
  `Claude-Session:` and "Generated with Claude" trailers: authorship of MAYA is one
  person's (plan §2.1).

## Consequences

- The cost of no hosted CI is that **nothing on the server side rejects anything**. A
  clone without `core.hooksPath` set runs no gate at commit, `git commit --no-verify`
  skips them, and a push is accepted either way. The discipline is local and
  unwitnessed; the hook makes the right thing the default, not the only thing.
- The `pre-commit` hook runs the static gates only. The suite runs when somebody runs
  `--tests`, and its PostgreSQL half only on a machine with `MAYA_TEST_PG_URL` set
  (plan §7, rung 17). A commit can be green at the hook and red in the suite.
- Plan §10's condition "green on all three platforms and both backends" is reduced to
  Linux (ADR-014). The per-platform, per-backend test-count stamp of plan §7.3
  (`docs/test_counts.json`) was never built, so a suite that silently shrinks — a module
  skipped because an optional dependency is missing — is not caught by any hook.
  Check the total, not only the absence of failures.

## References

- Plan §7 (the gate ladder), §7.3, §10; specification §23.
- Code: `.githooks/pre-commit`, `.githooks/commit-msg`, `tools/ci/gates.py`,
  `tools/docs/build_spec.py`.
- Tests: `tests/test_api_and_gates.py` — `test_gate_is_green`,
  `test_gate_fails_on_a_planted_violation`. The hooks themselves have no test.
