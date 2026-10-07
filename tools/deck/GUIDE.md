# Deck generator

Regenerates MAYA's deck from source, so it is reproducible rather than a binary
nobody can edit safely.

```bash
.venv/bin/python tools/deck/build.py                     # the deck, into docs/
.venv/bin/python tools/deck/audit.py docs/publications/MAYA-Model-Management-Formalism-and-System-Design.pptx
.venv/bin/python -m pytest -q tests/test_deck_geometry.py            # the audit, as a test
```

## One deck

| Deck | Slides | Source |
|---|---|---|
| `docs/publications/MAYA-Model-Management-Formalism-and-System-Design.pptx` | 69 | `maya_deck.py`, then `story_part1.py` to `story_part4.py` |

**Why one, where there were four.** The build previously carried an executive
briefing, a system design, a capabilities deck and a formalism deck. Four decks
is four places to keep one story current, and the story is one: what a model is,
what follows from that, and what MAYA does about it. The same argument retired
seven decks into three a version earlier; it applies again at four.

**How it is told.** As a briefing, for the people who have to trust a model's number:
the answer first, then the argument, then the evidence. Most slides carry a title, a
handful of short lines and, where it helps, one *key insight* in a band at the foot —
not paragraphs. The opening answers a reader's questions before anything is
explained: a TL;DR as five questions and answers, the question every model must answer,
ten principles, what supervisors say (SR 11-7 quoted, SS1/23's principles), the objects
MAYA keeps, its architecture, one model's journey through it, and what that buys. Eight
numbered parts follow. (1) The vocabulary: kernel and dials; features, parameters and
constants; two clocks; pins; warrants. (2) The lifecycle end to end, with real
screenshots. (3) The platform: overview, what makes it different, the web UI, two teams
meeting at one contract, roles, security in layers, deployment and what is measured.
(4) Governance: findings, materiality, periodic review, monitoring, champion and
challenger, fairness, the inventory. (5) Beyond formulas: black boxes, conformance,
connectors, beside an ML platform, LLM applications. (6) Fifteen worked models, six in
depth. (7) The formal core, briefly. (8) What is built, how it compares by category —
including the two rows where MAYA loses — what it does not do, what comes next, and
where to start.

**The look.** Harvard Crimson throughout: a crimson header bar with the MAYA mark on
every content slide, a crimson footer bar with the slogan and the byline, bold sans
titles over a crimson rule, numbered discs for principles and steps, and part dividers
that are a numbered disc centred on crimson. The mark is drawn from shapes, because
`python-pptx` cannot place the SVG.

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
| `story.py` | The briefing kinds: `cover`, `tldr` (question-and-answer rows), `numbered` (principles, steps, worked examples, with a question above and a key insight below), `quotes`, `arch` (layered bands), `lanes` (two teams at one contract), `columns`, `compare` (a capability matrix graded by colour), `shot` (a real screenshot from `maya/web/static/help/screens/` with commentary) and `thanks` |
| `maya_deck.py`, `story_part1.py` … `story_part4.py` | The deck, as data: the opening and the eight parts in order in the four part modules. It is split only to keep each file under the repository's file-size gate; they are one deck and are meant to be read in order |
| `build.py` | Builds the deck and sets the document properties (author, title, subject) explicitly |
| `audit.py` | The geometry audit (below) |

A slide that cannot be made to fit **fails the build** naming the slide; the fix is
to shorten the text or split the slide, never to lower the floor. Every number on a
slide comes from the code, the README's "What's shipped", `docs/quality/BENCHMARKS.md` or the
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
