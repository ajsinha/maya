# Deck generator

Regenerates `docs/Models-as-Parametric-Kernels.pptx` from source, so the deck is reproducible rather
than a binary nobody can edit safely.

```bash
python -m venv .venv && .venv/bin/pip install python-pptx
.venv/bin/python tools/deck/slides.py docs/Models-as-Parametric-Kernels.pptx
.venv/bin/python tools/deck/audit.py            # must report no geometry issues
```

| File | Purpose |
|---|---|
| `theme.py` | Harvard-Crimson design system: palette, typography, and the layout primitives |
| `slides.py` | Slide content — edit this to change the deck |
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
