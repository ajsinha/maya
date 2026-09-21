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
| `docs/MAYA-Model-Management-Formalism-and-System-Design.pptx` | 90 | `maya_deck.py`, `maya_deck_1b.py`, `maya_deck_2.py`, `maya_deck_3.py` |

**Why one, where there were four.** The build previously carried an executive
briefing, a system design, a capabilities deck and a formalism deck. Four decks
is four places to keep one story current, and the story is one: what a model is,
what follows from that, and what MAYA does about it. The same argument retired
seven decks into three a version earlier; it applies again at four.

**What it does, in order.** It builds the vocabulary from nothing — a model as a
compute kernel with dials, parameters and the several ways they are set, a
feature and its two clocks, a feature set, what training means, what a pin
freezes, what a warrant licenses — and uses no word before it has defined it.
Then the formalism, with an engineer's lens: the four facts a register normally
asks somebody to type, and what each one derives from, motivated by the failure
it prevents rather than stated as theorem and proof. Then the objects MAYA keeps
and how it runs. Then four models carried the whole way, chosen to be different
in kind: a retail scorecard as the plainest complete pass, a neural network
nobody can see inside, a yield curve written in LaTeX whose loading bug only a
second reading finds, and an impairment composite whose two hardest numbers are
judgements. It closes on what is measured and what MAYA does not do.

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
| `maya_deck.py`, `maya_deck_1b.py`, `maya_deck_2.py`, `maya_deck_3.py` | The deck, as data. It is split across four modules only to keep each file under the repository's file-size gate; they are one deck and are meant to be read in order |
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
