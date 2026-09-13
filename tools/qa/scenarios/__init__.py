"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The hand-written half of the case list, as code that runs.

Sections A–E are derived from source and driven generically by
`tools/qa/run.py`. These are the other half: orderings, races, re-runs, and
the specific ways two controls that are each correct combine into a hole. No
generator produces them and no generic driver executes them, so each one is
written out.

A scenario is a function taking `(ctx)` and returning `(verdict, evidence)`.
It is registered against the case id it answers, so a result can be reported
against the published list rather than against a private numbering.
"""
from __future__ import annotations
