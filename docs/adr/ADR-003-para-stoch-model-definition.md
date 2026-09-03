# ADR-003 — `Para(Stoch)` as the universal definition of a model

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
A bank's estate spans closed-form pricers, daily-calibrated vol surfaces, statistical scorecards, ML
classifiers, online-adaptive systems, LLM applications, vendor black boxes, expert-judgment scorecards and
deterministic rule sets. Every surveyed product picks one shape — usually "trained ML model" — and forces
everything else into it, which is why banks run four systems and a spreadsheet.

## Decision
Define a model as a **morphism in `Para(Stoch)`**: a triple `(P, X, Y)` with a Markov kernel
`f : P ⊗ X → Y`, where `P` is the parameter object. The nine trainability classes T0–T8 are not nine kinds
of object; they are nine answers to *how `P` is inhabited*, characterised by a fitting morphism `φ : D → P`.

## Consequences
- **+** One registry schema, one API, one interface for every model in the bank. `T0` is the case `P = 1`;
  `T6` is the case where `P` is inaccessible.
- **+** *"Some models do not need training"* becomes a type-level fact rather than a special case:
  training is one way of inhabiting `P`, not part of the definition of a model.
- **+** Determinism becomes a checkable property (`copy ∘ f = (f ⊗ f) ∘ copy`), which is exactly the
  reproducibility test.
- **+** Composition is inherited from the monoidal structure, so feeder graphs and composite hooks are
  typed and checkable.
- **−** The team must learn a small amount of category theory. Mitigated by keeping the vocabulary confined
  to `maya/domain/` and documenting it in [00](../00-mathematical-foundations.md).
- **−** Some models (heavily stateful simulation engines) fit awkwardly. Handled by making state part of `X`
  and documenting the modelling choice.
