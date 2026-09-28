# Deck generator

Regenerates MAYA's deck from source, so it is reproducible rather than a binary
nobody can edit safely.

```bash
.venv/bin/python tools/deck/build.py                     # the deck, into docs/
.venv/bin/python tools/deck/audit.py docs/MAYA-Model-Management-Formalism-and-System-Design.pptx
.venv/bin/python -m pytest -q tests/test_deck_geometry.py            # the audit, as a test
```

## One deck

| Deck | Slides | Source |
|---|---|---|
| `docs/MAYA-Model-Management-Formalism-and-System-Design.pptx` | 72 | `maya_deck.py`, then `deck_part1.py` to `deck_part4.py` |

**Why one, where there were four.** The build previously carried an executive
briefing, a system design, a capabilities deck and a formalism deck. Four decks
is four places to keep one story current, and the story is one: what a model is,
what follows from that, and what MAYA does about it. The same argument retired
seven decks into three a version earlier; it applies again at four.

**What it does, in order.** It is written for the people who have to trust a
model's number, and answers their questions in the order they ask them, in nine
parts. (1) Why model governance fails: the question every model must answer, what
SR 11-7 and SS1/23 expect, four places a typed register breaks, and MAYA in one
slide. (2) The vocabulary from nothing — kernel and dials, features and their two
clocks, feature sets, training, pins, warrants — with no word used before it is
defined. (3) The lifecycle end to end, from a delivered file to a model reporting
back under a live licence. (4) The governance a model risk function works in:
findings, materiality, periodic review, monitoring, champion and challenger,
fairness and explainability, and the supervisory inventory. (5) Models beyond
formulas: black boxes scored blind, imports from MLflow and SageMaker, what MAYA does beside
an ML platform, and LLM applications. (6) The formal core, with an engineer's lens. (7) How it runs. (8)
Fifteen case studies, six of them in depth. (9) What is measured, what MAYA does
not do, and where to start.

**What it deliberately is not.** It carries no implementation-status register and
no slide whose subject is the research paper. A deck that spends its slides
comparing a paper with an implementation is a deck about the project rather than
about the product. Where the mathematics needs to be seen working, a worked model
does it. The paper is cited once, as where to read the proofs.

Every figure on the case-study slides was reproduced by running the study against
a MAYA built from nothing; where a study's README and its live run disagreed, the
run won and the discrepancy is not quoted.

## How it is put together

| File | Purpose |
|---|---|
| `metrics.py` | The text estimator: greedy word-wrap simulation and paragraph heights. Shared by the builder and the audit, so the builder never believes a box fits that the audit then reports |
| `theme.py` | The Harvard Crimson design system (#A51C30, spec §16.6): palette, typography, chrome, tables, cards, stat bars, and `fitted()`, which shrinks a text block until it fits or raises `DoesNotFit` |
| `layouts.py` | Slide kinds drawn from plain dictionaries: `title`, `divider`, `bullets`, `table`, `cards`, `stats`, `split`, `flow`, `context` (boxes placed on the content area and joined by arrows, for a system context diagram) |
| `maya_deck.py`, `deck_part1.py` … `deck_part4.py` | The deck, as data: the title slide in `maya_deck.py`, the nine parts in order in the four part modules. It is split only to keep each file under the repository's file-size gate; they are one deck and are meant to be read in order |
| `build.py` | Builds the deck and sets the document properties (author, title, subject) explicitly |
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
another shape. `tests/test_deck_geometry.py` runs it on the deck and asserts the
slide count above.

`python-pptx` does not measure text, and PowerPoint does not clip overflow. The
estimator is deliberately pessimistic (a 6% width margin), so rendered text sits
comfortably inside its boxes; it is an estimate, and a deck should still be looked
at after a large change (for example `soffice --headless --convert-to pdf`).

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
