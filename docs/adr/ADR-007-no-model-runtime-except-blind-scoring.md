# ADR-007 — D-4: no model runtime, with one exception — blind scoring

**Status:** Accepted, 2026-09-17.

## Context

MAYA is a register. It records what a model is, what data it may be trained on, which
parameters were approved and where it may run — and it hands those out under warrants. It
does not train, run, serve or deploy models. Every model platform is pulled towards
becoming a runtime, because once the data and the parameters are in one place, running the
model there looks like one more button. That is where the warrant boundary dissolves: a
register that also runs things becomes one more serving stack, judged as one, and its
evidence becomes whatever the runtime happened to log.

One piece of runtime is unavoidable. An escrowed holdout (§29.4) is only escrowed if the
person being evaluated never sees the rows, so the scoring has to happen where the rows are.

## Decision

**Model runtime is out of scope in v2.0, with exactly one conceded exception: blind scoring
against an escrowed holdout.** MAYA scores a submitted parameter set against the holdout,
returns metrics and never rows, and counts every attempt on the warrant. Everything else —
training, batch and online execution — happens outside MAYA, under a warrant, and is
reported back (§28.5).

## Consequences

- Some execution happens where MAYA cannot see it, and some lineage escapes. That is
  accepted knowingly (§28.11). Execution warrants narrow the gap — short-lived tokens,
  execution reported back, covenants whose breach suspends the warrant
  ([runbook](../runbooks/suspended-execution-warrant.md)) — and an offline copy is labelled
  `unattested` rather than forbidden.
- **As built, the exception is narrower than §26.3 states.** The specification says blind
  scoring runs in the §17.2 sandbox. It does not run user code at all: MAYA evaluates the
  model's formula IR (or composite) with its own evaluator, in process. A declared black
  box therefore cannot be blind-scored — the request is refused with *"A declared black box
  cannot be scored by MAYA"* — and a model with a Python artifact is scored by its formula
  IR, never by running the artifact.
- The scoring-attempt counter exists so that "score it forty times and report the best"
  shows on the warrant. It is a record, not a limit.
- The reproducibility bundle's verifier re-executes a model to compare outputs. It runs on
  the verifier's machine, from the bundle, not inside MAYA.

## References

- Specification §2 (non-goals), §26.3 (D-4), §28.5, §28.11, §29.4; plan §4.1.
- Code: `maya/services/warrants.py` (`score_holdout`), `maya/services/execution.py`.
- Tests: `tests/test_warrants.py::test_the_checksum_cycle_seal_score_execute_and_bundle`
  (the first scoring attempt is counted as attempt 1).
