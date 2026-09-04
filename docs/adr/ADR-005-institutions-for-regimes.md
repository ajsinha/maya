# ADR-005 — Institutions for multi-regulator scoping

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
The same model is out of SR 26-2 scope, in SS1/23 scope, high-risk under the EU AI Act and possibly a SOX
key control — simultaneously. These are not four values of one attribute; they are four *logics*, each
with its own vocabulary, sentences and satisfaction relation. Modelling scope as a boolean or a tag set
forces a re-architecture every time a regulator publishes. SR 11-7 being replaced by SR 26-2 mid-design is
the concrete proof that this happens.

## Decision
Model each regulatory regime as an **institution** (Goguen–Burstall): signatures, sentences, models and a
satisfaction relation, connected to MAYA's core vocabulary by an institution comorphism. Scope
determinations are stored as **derivations** — sentence, evaluated facts, failing conjunct, citation,
regime version — not as flags.

## Consequences
- **+** Adding MAS, APRA, OSFI E-23 or a future GenAI regime is adding one module. No migration.
- **+** The satisfaction condition ("truth is invariant under change of notation") is a testable property
  (L-8) that catches the exact class of bug that produces indefensible scope determinations.
- **+** "Why is this out of scope?" is answered by a stored derivation with a regulatory citation —
  satisfying FR-INV-004 by construction rather than by discipline.
- **+** Regime versions are explicit, so a determination made under SR 11-7 remains interpretable after
  SR 26-2 supersedes it.
- **−** Conceptually heavier than a tag column. Justified by the frequency of regulatory change and the
  cost of getting scope wrong.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
