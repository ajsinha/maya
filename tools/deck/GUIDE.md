# Deck generator

Regenerates MAYA's presentation decks from source, so each deck is reproducible
rather than a binary nobody can edit safely.

```bash
.venv/bin/python tools/deck/build.py                     # all four decks, into docs/
.venv/bin/python tools/deck/build.py design              # one: executive, design, capabilities or concepts
.venv/bin/python tools/deck/audit.py docs/MAYA-System-Design.pptx   # must report no geometry issues
.venv/bin/python -m pytest -q tests/test_deck_geometry.py            # the audit, as a test
```

## Four decks, four audiences

| Deck | Slides | For | Source |
|---|---|---|---|
| `docs/MAYA-Executive-Briefing.pptx` | 18 | Whoever decides whether to adopt MAYA: what it is, what it delivers, what has been measured, and what it does not do | `exec_deck.py` |
| `docs/MAYA-System-Design.pptx` | 41 | Whoever builds or operates it: every subsystem, with the module and the test behind each claim | `design_deck.py`, `design_deck_2.py` |
| `docs/MAYA-Capabilities.pptx` | 37 | Whoever wants to know what the product actually does: the platform through its own screens and objects, then one model — the IFRS 9 study — carried end to end, refusals included | `capabilities_deck.py`, `capabilities_deck_2.py` |
| `docs/MAYA-Concepts-and-Formalism.pptx` | 31 | Whoever wants to know why MAYA is shaped as it is: the definition, the order, the operator and the polynomial, and the two results that bound them | `concepts_deck.py`, `concepts_deck_2.py` |

**The fourth deck is not a summary of the paper.** *Concepts and Formalism*
presents the mathematics in its own right — a model as a kernel with a parameter
object, one order read as *A can stand in for B*, the point-in-time read as an
operator, provenance as a polynomial, and the two negative results that bound
them — each glossed in plain terms and carried by a worked example from a bank.
An earlier deck of that name walked the research paper construction by
construction and marked each with what the code implements. A deck whose subject
is a paper, or a register of what is and is not built, is a deck about the
project rather than about the ideas, so that one was removed. This one therefore
carries no implementation-status table and no slide whose subject is the paper,
and cites it once, on the closing slide, as where to read the proofs. Each
slide's note names the section its mathematics comes from, which is the
counterpart of the other decks naming a module.

## How it is put together

| File | Purpose |
|---|---|
| `metrics.py` | The text estimator: greedy word-wrap simulation and paragraph heights. Shared by the builder and the audit, so the builder never believes a box fits that the audit then reports |
| `theme.py` | The Harvard Crimson design system (#A51C30, spec §16.6): palette, typography, chrome, tables, cards, stat bars, and `fitted()`, which shrinks a text block until it fits or raises `DoesNotFit` |
| `layouts.py` | Slide kinds drawn from plain dictionaries: `title`, `divider`, `bullets`, `table`, `cards`, `stats`, `split`, `flow` |
| `exec_deck.py`, `design_deck.py`(`_2`), `capabilities_deck.py`(`_2`), `concepts_deck.py`(`_2`) | The decks, as data. A deck is split across two modules only to keep each file small enough to read |
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
