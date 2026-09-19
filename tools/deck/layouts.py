"""
Slide layouts, each drawn from a plain dictionary.

A deck is data: a list of slide specs, each naming its ``kind``. Keeping the
content out of the drawing code is what lets the three decks share one set of
layouts, and what keeps every layout short enough to read — and to fit.

Kinds: ``title``, ``divider``, ``bullets``, ``table``, ``cards``, ``stats``,
``split``, ``flow``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any

import theme as T
from metrics import SH, SW, text_h

GAP = 0.18


def _items(tf: Any, items: list[Any], size: float) -> None:
    """Bulleted items; a tuple is ``(head, body)``."""
    for i, it in enumerate(items):
        first = i == 0
        if isinstance(it, tuple):
            T.runs(tf, [("▪  ", T.CRIMSON, True), (it[0], T.INK, True)], size=size,
                   space_after=1, first=first, space_before=0 if first else 5)
            T.runs(tf, [(it[1], T.SLATE, False)], size=size - 1.5, space_after=0, level=1)
        else:
            T.runs(tf, [("▪  ", T.CRIMSON, True), (it, T.INK, False)], size=size,
                   space_after=0, first=first, space_before=0 if first else 6)


def _intro(sl: Any, y: float, text: str | None) -> float:
    if not text:
        return y
    used = T.fitted(sl, T.ML, y, T.CW, 1.0, lambda tf, s: T.para(
        tf, text, size=s, color=T.INK, first=True, space_after=0, line=1.25), 14, 11)
    return y + used + GAP


def _note(sl: Any, text: str | None) -> float:
    """A crimson-ruled note pinned above the footer; returns its top."""
    if not text:
        return T.BODY_BOTTOM
    size = 12.0
    width = T.CW - 0.3
    while size > 9 and text_h(text, width * 0.94, size, False, "Calibri", 1.2) > 0.9:
        size -= 0.5
    h = text_h(text, width * 0.94, size, False, "Calibri", 1.2)
    top = T.BODY_BOTTOM - h
    T.rect(sl, T.ML, top, 0.045, h, fill=T.CRIMSON)
    T.fitted(sl, T.ML + 0.25, top, width, h + 0.02, lambda tf, s: T.para(
        tf, text, size=s, color=T.SLATE, italic=True, first=True, space_after=0, line=1.2),
        size, 8.5)
    return top - GAP


def title(s: dict[str, Any]) -> None:
    T._state["n"] = 1
    sl = T.blank()
    T.rect(sl, 0, 0, SW, SH, fill=T.WHITE)
    T.rect(sl, 0, 0, SW, 4.3, fill=T.CRIMSON)
    T.rect(sl, 0, 4.3, SW, 0.06, fill=T.GOLD)
    T.rect(sl, 0, 0, 0.20, 4.3, fill=T.CRIMSON_D)
    tf = T.txt(sl, T.ML + 0.3, 0.9, T.CW, 0.34)
    T.para(tf, s["kicker"], size=11, color=T.PINK, bold=True, first=True, space_after=0)

    def head(tf: Any, size: float) -> None:
        for i, line in enumerate(s["title"]):
            T.para(tf, line, size=size, color=T.WHITE, font="Georgia", first=i == 0,
                   space_after=0, line=1.1)
    T.fitted(sl, T.ML + 0.3, 1.4, T.CW * 0.9, 1.75, head, 38, 26)
    T.rect(sl, T.ML + 0.3, 3.25, 1.7, 0.035, fill=T.PINK)
    tf = T.txt(sl, T.ML + 0.3, 3.45, T.CW * 0.85, 0.7)
    T.para(tf, s["sub"], size=15, color=T.PINK_L, italic=True, first=True, space_after=0)
    tf = T.txt(sl, T.ML + 0.3, 4.75, T.CW * 0.5, 1.2)
    T.para(tf, "Ashutosh Sinha", size=20, color=T.INK, bold=True, font="Georgia",
           first=True, space_after=3)
    T.para(tf, s.get("date", "September 2026"), size=12, color=T.CRIMSON, space_after=1)
    T.para(tf, s.get("version", "MAYA 0.3.0 · specification revision 2.3"), size=11,
           color=T.SLATE, space_after=0)
    x0 = T.ML + T.CW * 0.56

    def agenda(tf: Any, size: float) -> None:
        T.para(tf, "IN THIS DECK", size=9.5, color=T.CRIMSON, bold=True, first=True,
               space_after=6)
        for i, c in enumerate(s["agenda"], 1):
            T.runs(tf, [(f"{i}   ", T.CRIMSON, True), (c, T.SLATE, False)], size=size,
                   space_after=3)
    T.fitted(sl, x0, 4.7, T.CW * 0.44, 2.2, agenda, 12, 9)
    T.footer(sl)


def divider(s: dict[str, Any]) -> None:
    T.divider(s["num"], s["title"], s["sub"], s["points"])


def bullets(s: dict[str, Any]) -> None:
    sl, y = T.content(s["title"], s.get("kicker"))
    y = _intro(sl, y, s.get("intro"))
    bottom = _note(sl, s.get("note"))
    T.fitted(sl, T.ML, y, T.CW, bottom - y, lambda tf, size: _items(tf, s["items"], size),
             s.get("size", 17), 9.5)


def table(s: dict[str, Any]) -> None:
    sl, y = T.content(s["title"], s.get("kicker"))
    y = _intro(sl, y, s.get("intro"))
    bottom = _note(sl, s.get("note"))
    T.fitted_table(sl, s["rows"], T.ML, y, T.CW, bottom - y, s.get("col_w"),
                   start=s.get("size", 14), bold_col0=s.get("bold_col0", True))


def cards(s: dict[str, Any]) -> None:
    sl, y = T.content(s["title"], s.get("kicker"))
    y = _intro(sl, y, s.get("intro"))
    bottom = _note(sl, s.get("note"))
    items = s["cards"]
    cols = s.get("cols", 3)
    rows = (len(items) + cols - 1) // cols
    cw = (T.CW - GAP * (cols - 1)) / cols
    ch = (bottom - y - GAP * (rows - 1)) / rows
    for i, (num, head, body) in enumerate(items):
        r, c = divmod(i, cols)
        T.card(sl, T.ML + c * (cw + GAP), y + r * (ch + GAP), cw, ch, num, head, body)


def stats(s: dict[str, Any]) -> None:
    sl, y = T.content(s["title"], s.get("kicker"))
    y = _intro(sl, y, s.get("intro"))
    T.statbar(sl, y, s["stats"])
    y += 1.25 + GAP + 0.05
    bottom = _note(sl, s.get("note"))
    if s.get("rows"):
        T.fitted_table(sl, s["rows"], T.ML, y, T.CW, bottom - y, s.get("col_w"),
                       start=s.get("size", 13.5))
    elif s.get("items"):
        T.fitted(sl, T.ML, y, T.CW, bottom - y, lambda tf, size: _items(tf, s["items"], size),
                 s.get("size", 16), 9.5)


def _column(sl: Any, x: float, y: float, w: float, h: float, col: dict[str, Any]) -> None:
    T.rect(sl, x, y, w, 0.42, fill=T.PARCH)
    T.rect(sl, x, y, 0.045, 0.42, fill=T.CRIMSON)
    tf = T.txt(sl, x + 0.18, y + 0.08, w - 0.3, 0.3)
    T.para(tf, col["head"], size=13, color=T.CRIMSON_D, bold=True, first=True, space_after=0)
    top = y + 0.42 + 0.14
    if col.get("rows"):
        T.fitted_table(sl, col["rows"], x, top, w, y + h - top, col.get("col_w"),
                       start=col.get("size", 13))
    else:
        T.fitted(sl, x, top, w, y + h - top,
                 lambda tf, size: _items(tf, col["items"], size), col.get("size", 15), 9)


def split(s: dict[str, Any]) -> None:
    sl, y = T.content(s["title"], s.get("kicker"))
    y = _intro(sl, y, s.get("intro"))
    bottom = _note(sl, s.get("note"))
    w = (T.CW - 0.4) / 2
    _column(sl, T.ML, y, w, bottom - y, s["left"])
    _column(sl, T.ML + w + 0.4, y, w, bottom - y, s["right"])


def flow(s: dict[str, Any]) -> None:
    """Boxes in a row, joined by straight arrows; then optional items beneath."""
    sl, y = T.content(s["title"], s.get("kicker"))
    y = _intro(sl, y, s.get("intro"))
    bottom = _note(sl, s.get("note"))
    steps = s["steps"]
    arrow = 0.28
    bw = (T.CW - arrow * (len(steps) - 1)) / len(steps)
    bh = s.get("box_h", 1.9)
    for i, (head, body) in enumerate(steps):
        x = T.ML + i * (bw + arrow)
        T.card(sl, x, y, bw, bh, "", head, body)
        if i:
            T.connect(sl, x - arrow + 0.03, y + bh / 2, x - 0.03, y + bh / 2, T.CRIMSON, 2.0)
    top = y + bh + GAP + 0.05
    if s.get("items"):
        T.fitted(sl, T.ML, top, T.CW, bottom - top,
                 lambda tf, size: _items(tf, s["items"], size), s.get("size", 15), 9)
    elif s.get("rows"):
        T.fitted_table(sl, s["rows"], T.ML, top, T.CW, bottom - top, s.get("col_w"),
                       start=s.get("size", 13))


KINDS = {"title": title, "divider": divider, "bullets": bullets, "table": table,
         "cards": cards, "stats": stats, "split": split, "flow": flow}


def render(slides: list[dict[str, Any]]) -> None:
    for i, spec in enumerate(slides, 1):
        try:
            KINDS[spec["kind"]](spec)
        except T.DoesNotFit as exc:
            raise T.DoesNotFit(f"slide {i} ({spec.get('title')!r}): {exc}") from exc
