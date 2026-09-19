"""Gate 11 — every foreground/background token pair clears WCAG AA (§16.6).

Ratios are computed from tokens.css, never asserted: text pairs ≥ 4.5:1,
non-text pairs ≥ 3:1, in both the light and the dark scheme.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
import sys

from _common import ROOT, report

TOKENS = ROOT / "maya" / "web" / "static" / "css" / "tokens.css"
TEXT_PAIRS = [("--maya-ink", "--maya-surface"), ("--maya-ink", "--maya-canvas"),
              ("--maya-crimson", "--maya-surface"), ("--maya-slate", "--maya-surface"),
              ("--maya-crimson-deep", "--maya-surface"), ("--maya-ink", "--maya-crimson-tint"),
              ("--maya-on-nav", "--maya-nav-from"), ("--maya-on-nav", "--maya-nav-via"),
              ("--maya-on-nav", "--maya-nav-to")]
NON_TEXT = [("--maya-crimson", "--maya-canvas"), ("--maya-indigo", "--maya-surface")]


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def blocks(css: str) -> list[tuple[list[str], str]]:
    """Innermost rule bodies with the stack of headers enclosing them (brace-aware)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: list[tuple[list[str], str]] = []
    stack: list[str] = []
    buf = ""
    for ch in css:
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            if stack:
                out.append((list(stack), buf))
                stack.pop()
            buf = ""
        else:
            buf += ch
    return out


def schemes(css: str) -> dict[str, dict[str, str]]:
    light: dict[str, str] = {}
    dark: dict[str, str] = {}
    for headers, body in blocks(css):
        tokens = dict(re.findall(r"(--maya-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})", body))
        if not tokens:
            continue
        if any("dark" in h for h in headers):
            dark.update(tokens)
        else:
            light.update(tokens)
    return {"light": light, "dark": {**light, **dark}}


def main() -> int:
    if not TOKENS.exists():
        return report("colour contrast", [f"{TOKENS} is missing"])
    failures = []
    for scheme, tokens in schemes(TOKENS.read_text(encoding="utf-8")).items():
        for pairs, minimum in ((TEXT_PAIRS, 4.5), (NON_TEXT, 3.0)):
            for fg, bg in pairs:
                if fg not in tokens or bg not in tokens:
                    failures.append(f"{scheme}: token {fg if fg not in tokens else bg} missing")
                    continue
                r = ratio(tokens[fg], tokens[bg])
                if r < minimum:
                    failures.append(f"{scheme}: {fg} on {bg} is {r:.2f}:1 (< {minimum}:1)")
    return report("colour contrast (WCAG AA)", failures)


if __name__ == "__main__":
    sys.exit(main())
