# Deck generator

Regenerates MAYA's presentation decks from source, so each deck is reproducible
rather than a binary nobody can edit safely.

```bash
.venv/bin/python tools/deck/build.py                     # all three decks, into docs/
.venv/bin/python tools/deck/build.py design              # one: executive, design or concepts
.venv/bin/python tools/deck/audit.py docs/MAYA-System-Design.pptx   # must report no geometry issues
.venv/bin/python -m pytest -q tests/test_deck_geometry.py            # the audit, as a test
```

## Three decks, three audiences

| Deck | Slides | For | Source |
|---|---|---|---|
| `docs/MAYA-Executive-Briefing.pptx` | 16 | Whoever decides whether to use MAYA: what it is, what 0.3.0 delivers, what is measured, what it does not do | `exec_deck.py` |
| `docs/MAYA-System-Design.pptx` | 34 | Whoever builds or operates it: every subsystem, with the module and the test behind each claim | `design_deck.py`, `design_deck_2.py` |
| `docs/MAYA-Concepts-and-Formalism.pptx` | 21 | Whoever wants the theory: the paper `docs/research/models-as-parametric-kernels.tex`, with each construction marked for what MAYA 0.3.0 implements | `concepts_deck.py` |

**Why three, where the previous build had seven.** The decks were rewritten
against specification revision 2.3 and version 0.3.0, and merged where they had
become one subject:

* *System Design*, *Model and Feature Management*, *Feature Platform* and *Model
  and Feature Engineering* are now **MAYA-System-Design**. Under revision 2.3
  features, feature sets, models and warrants are one spine; four decks were four
  places to keep one system current.
* *Concepts and Formalism* and *Models as Parametric Kernels* are now
  **MAYA-Concepts-and-Formalism**. Both presented the paper's theory; one deck tied
  to the paper keeps the theory and its implementation status in one place.
* *Executive Briefing* is rewritten, not merged.

The previous build's slides described a system that no longer exists, so none of
their content was carried over; only the design system and the audit were.

## How it is put together

| File | Purpose |
|---|---|
| `metrics.py` | The text estimator: greedy word-wrap simulation and paragraph heights. Shared by the builder and the audit, so the builder never believes a box fits that the audit then reports |
| `theme.py` | The Harvard Crimson design system (#A51C30, spec §16.6): palette, typography, chrome, tables, cards, stat bars, and `fitted()`, which shrinks a text block until it fits or raises `DoesNotFit` |
| `layouts.py` | Slide kinds drawn from plain dictionaries: `title`, `divider`, `bullets`, `table`, `cards`, `stats`, `split`, `flow` |
| `exec_deck.py`, `design_deck.py`, `design_deck_2.py`, `concepts_deck.py` | The decks, as data |
| `build.py` | Builds the decks and sets the document properties (author, title, subject) explicitly |
| `audit.py` | The geometry audit (below) |

A slide that cannot be made to fit **fails the build** naming the slide; the fix is
to shorten the text or split the slide, never to lower the floor. Every number on a
slide comes from the code, the README's "What's shipped", `docs/BENCHMARKS.md` or the
specification, and the slide's note names its source.

## The audit

`audit.py` re-derives the geometry of every shape on every slide and reports: a
shape off the slide; a table taller than its frame (PowerPoint treats a row height as
a minimum); an opaque shape drawn over earlier content; anything printed over a
table; text escaping a filled or outlined container, or the card its textbox sits
in; content crossing the footer rule; and a free textbox whose overflow lands on
another shape. `tests/test_deck_geometry.py` runs it on every deck and asserts the
slide counts above.

`python-pptx` does not measure text, and PowerPoint does not clip overflow. The
estimator is deliberately pessimistic (a 6% width margin), so rendered text sits
comfortably inside its boxes; it is an estimate, and a deck should still be looked
at after a large change (for example `soffice --headless --convert-to pdf`).

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
