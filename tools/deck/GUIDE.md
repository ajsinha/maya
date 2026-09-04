# Deck generator

Regenerates `docs/Models-as-Parametric-Kernels.pptx` from source, so the deck is reproducible rather
than a binary nobody can edit safely.

```bash
python -m venv .venv && .venv/bin/pip install python-pptx
.venv/bin/python tools/deck/slides.py             docs/Models-as-Parametric-Kernels.pptx
.venv/bin/python tools/deck/design_slides.py      docs/MAYA-System-Design.pptx
.venv/bin/python tools/deck/engineering_slides.py docs/MAYA-Model-and-Feature-Engineering.pptx
.venv/bin/python tools/deck/audit.py <deck>       # must report no geometry issues
```

The engineering deck embeds the two series its worked example is computed from,
so they travel inside the file and open on a double-click. The generator reads
those same files, so the figures on the slides and the data behind them cannot
drift apart.

They are embedded as **workbooks**, not as OLE packages. An OLE package must be
wrapped in a compound document, and PowerPoint handed raw bytes under that prog
id shows an icon that opens nothing — which is what the first attempt did, and
it looked correct from the outside because the bytes were demonstrably inside
the file. `xlsx.py` writes a minimal valid `.xlsx` from a CSV using nothing but
`zipfile`, keeping the deck free of a dependency for the same reason every other
asset here is vendored.

Three decks, three audiences. The research deck argues the theory; the design
deck is for whoever builds the platform; the engineering deck is for whoever
uses it to engineer a model, and opens with a single-slide process diagram of
model, feature and warrant management.

| File | Purpose |
|---|---|
| `theme.py` | Harvard-Crimson design system: palette, typography, and the layout primitives |
| `slides.py` | The research deck: models as parametric kernels |
| `design_slides.py` | The engineering deck: how the platform is built |
| `engineering_slides.py` | The practitioner's deck: model and feature engineering |
| `audit.py` | Geometry checker (see below). Run it after every change |

## Why there is a text-fitting layer

`python-pptx` does not measure or wrap text, and PowerPoint shapes do not clip overflow — text simply
spills outside its box and over whatever is beneath it. Hand-estimated box sizes therefore fail
silently, which is exactly what happened on the first build: nine slides had content overlapping other
elements or sitting outside its enclosing rectangle.

`theme.py` solves this rather than patching symptoms:

- **`est_lines()`** simulates greedy word wrapping to predict rendered line counts, with a 6% width
  safety margin so borderline cases round to the safe side.
- **`table()`** computes each row's height from its wrapped cell text and **returns the total rendered
  height**. Callers position what follows using that return value — never a hardcoded offset, which is
  the bug class that produced captions overlapping their own tables.
- **`card()`** shrinks the title until it fits two lines, then shrinks the body font until it fits the
  remaining space, so card content is guaranteed to stay inside the border.
- **`content()`** derives the title block height from the estimator, so two-line titles push the body
  down by the right amount.
- **`divider()`** shrinks a chapter title until it clears the contents strip on the right.
- **`connect()`** uses *straight* connectors. Elbow connectors (`add_connector(2, ...)`) auto-route into
  large rectangular detours that collide with the nodes they connect — do not use them.

## The audit

`audit.py` re-derives the geometry of every shape on every slide and reports three failure classes:

1. a shape positioned outside the slide bounds,
2. estimated text height exceeding its shape's height,
3. content crossing the footer rule.

It must report **no geometry issues** before the deck ships.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*


## What the audit measures, and what it once did not

It was presented as the shipping gate and was wired into no test, and it was
wrong in the same direction twice.

The first time it measured chevrons as rectangles, assumed one text margin for
every shape, and checked only filled shapes as collision targets — so a card's
unfilled body textbox could escape its card unreported.

The second time it could not see **tables**. A `GraphicFrame` has no text frame,
so the loop that measures everything skipped every table before measuring
anything, and excluded them as collision targets too. The three decks hold
twelve, sixty-two and twenty-eight tables, and seven real collisions were behind
that one `continue` — three of them an opaque shape drawn over a table, which
does not crowd the reader but deletes a row from the page.

So it now measures:

* a table's **real** height, summed from its row heights, because PowerPoint
  treats a declared row height as a minimum and grows the row to fit;
* whether an opaque shape drawn later covers something drawn earlier, measured
  against the covered shape's **text extent** rather than its box, since a
  caption's box is usually taller than its text;
* whether anything overlaps a table.

**`row_h` is a floor, not a height.** `theme.table()` adds padding plus one text
line on top of it, so any value below about a third of an inch is inoperative
and an author's mental `rows x row_h` is always short. Take the height the
function returns and place what follows from it; thirty-one of fifty-one call
sites did not, and every collision found was at one of them.
