"""
The six diagrams of the Medium article, as SVG, then PNG for uploading.

    .venv/bin/python docs/articles/medium/diagrams.py

Medium does not render diagram code, so every figure is an image; drawing them from code
keeps them consistent and editable. Needs Inkscape on PATH for the PNGs.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "img"
CRIMSON, NAVY, INK, SLATE, LINE, PAPER, TINT, OK, BAD, SAND = (
    "#A51C30",
    "#293352",
    "#1A1A1A",
    "#5F6873",
    "#D9D3CB",
    "#FBF9F7",
    "#F8E6E9",
    "#1E6B3A",
    "#B42318",
    "#F4EFE8",
)
FONT = "Helvetica, Arial, sans-serif"
MONO = "Menlo, Consolas, monospace"


def svg(w: int, h: int, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto"><path d="M0 0L10 5L0 10z" fill="{CRIMSON}"/></marker>'
        f'<marker id="g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto"><path d="M0 0L10 5L0 10z" fill="{SLATE}"/></marker></defs>'
        f'<rect width="{w}" height="{h}" fill="{PAPER}"/>'
        f'<text x="40" y="52" font-family="{FONT}" font-size="26" font-weight="700" fill="{INK}">{title}</text>'
        f"{body}</svg>"
    )


def text(x, y, s, size=18, color=INK, weight=400, anchor="middle", font=FONT):
    return (
        f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}" text-anchor="{anchor}">{s}</text>'
    )


def box(x, y, w, h, fill=TINT, stroke=CRIMSON, r=12, sw=2):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def arrow(x1, y1, x2, y2, color=CRIMSON, marker="a", dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.5"{d} '
        f'marker-end="url(#{marker})"/>'
    )


def chain() -> str:
    stages = [
        ("data", "as it arrived", "a CSV, a SQL pull"),
        ("feature", "as it stood then", "two clocks per value"),
        ("pin", "readable for ever", "named by its hash"),
        ("model", "MAYA evaluates it", "ŷ = a·x + b"),
        ("warrant", "or it does not run", "a licence, refusable"),
        ("run", "reported, checked", "covenants on every run"),
    ]
    body, x0, gap, w = "", 50, 222, 180
    for i, (name, note, eg) in enumerate(stages):
        x = x0 + i * gap
        body += box(x, 120, w, 110)
        body += text(x + w / 2, 165, name, 24, CRIMSON, 700)
        body += text(x + w / 2, 196, note, 16, INK)
        body += text(x + w / 2, 262, eg, 15, SLATE, font=MONO if "·" in eg else FONT)
        if i < len(stages) - 1:
            body += arrow(x + w + 4, 175, x + gap - 6, 175)
    body += box(300, 310, 800, 56, SAND, LINE, 10, 1.5)
    body += text(
        700,
        345,
        "every link sealed by a content hash:  sha256 9f3a 61c0 … 7b2d e21c",
        18,
        SLATE,
        font=MONO,
    )
    return svg(1400, 400, body, "The chain MAYA keeps behind every number")


def clocks() -> str:
    body = ""
    body += text(60, 120, "event time e", 17, SLATE, 700, "start")
    body += text(60, 380, "known at k", 17, SLATE, 700, "start")
    body += f'<line x1="200" y1="115" x2="1330" y2="115" stroke="{LINE}" stroke-width="3"/>'
    body += f'<line x1="200" y1="375" x2="1330" y2="375" stroke="{LINE}" stroke-width="3"/>'
    for i, day in enumerate(["1 Mar", "2 Mar", "3 Mar", "4 Mar", "5 Mar", "6 Mar"]):
        x = 260 + i * 200
        body += text(x, 100, day, 15, SLATE) + text(x, 405, day, 15, SLATE)
    rows = [
        (260, 300, OK, "on time: known the next morning"),
        (460, 500, OK, "on time"),
        (460, 1060, SAND, "a restatement: a new record, never an overwrite"),
        (660, 1260, BAD, "known 3 days late: refused by the certificate"),
    ]
    for e, k, color, label in rows:
        c = SLATE if color == SAND else color
        body += f'<circle cx="{e}" cy="115" r="9" fill="{c}"/><circle cx="{k}" cy="375" r="9" fill="{c}"/>'
        body += f'<line x1="{e}" y1="124" x2="{k}" y2="366" stroke="{c}" stroke-width="2.5"/>'
    body += box(200, 450, 560, 96, "#fff", CRIMSON, 10)
    body += text(480, 488, "the leakage certificate", 19, CRIMSON, 700)
    body += text(
        480, 522, "k ≤ e + ℓ for every training row, or a written exception", 16, INK, font=MONO
    )
    body += text(790, 480, "green: admitted", 16, OK, 700, "start")
    body += text(790, 506, "grey: a restatement, kept beside the original", 16, SLATE, 700, "start")
    body += text(790, 532, "red: known too late, refused", 16, BAD, 700, "start")
    return svg(1400, 580, body, "Two clocks on every value, and the certificate that reads both")


def checksum() -> str:
    lanes = [(230, "Model developer"), (700, "MAYA"), (1170, "Their compute")]
    body = ""
    for x, name in lanes:
        body += box(
            x - 130,
            90,
            260,
            54,
            TINT if name == "MAYA" else "#fff",
            CRIMSON if name == "MAYA" else LINE,
            10,
        )
        body += text(x, 124, name, 19, CRIMSON if name == "MAYA" else INK, 700)
        body += f'<line x1="{x}" y1="150" x2="{x}" y2="640" stroke="{LINE}" stroke-width="2" stroke-dasharray="6 6"/>'
    steps = [
        (230, 700, 195, "draw a training warrant (model@v3 + pin #q1)"),
        (700, 230, 255, "the data, and the checksum c it issued (c recorded)"),
        (230, 1170, 315, "train, wherever the developer trains"),
        (1170, 230, 375, "parameters"),
        (230, 700, 435, "upload the parameters, naming the checksum c"),
    ]
    for a, b, y, label in steps:
        body += arrow(
            a, y, b - (8 if b > a else -8), y, NAVY if a == 1170 or b == 1170 else CRIMSON
        )
        mid = 935 if 1170 in (a, b) else (a + b) / 2  # clear of MAYA's lifeline
        body += text(mid, y - 12, label, 16, INK)
    body += box(470, 480, 460, 150, "#fff", CRIMSON, 10)
    body += text(700, 515, "c among the checksums MAYA issued?", 18, CRIMSON, 700)
    body += text(700, 552, "yes → verified, may be approved", 17, OK)
    body += text(700, 585, "no → flagged unverified_data:", 17, BAD)
    body += text(700, 610, "approval needs a written override", 16, SLATE)
    return svg(
        1400, 680, body, "The checksum cycle: what turns a warrant from paperwork into a control"
    )


def lifecycle() -> str:
    nodes = {
        "draft": (140, 200),
        "submitted": (380, 200),
        "approved": (620, 200),
        "live": (900, 200),
        "suspended": (900, 430),
        "expired": (1200, 120),
        "revoked": (1200, 290),
    }
    body = ""
    for name, (x, y) in nodes.items():
        fill = {
            "live": "#E3F1E7",
            "suspended": "#FBE9E7",
            "revoked": "#F1EFEC",
            "expired": "#F1EFEC",
        }.get(name, TINT)
        stroke = {"live": OK, "suspended": BAD}.get(
            name, CRIMSON if name not in ("expired", "revoked") else SLATE
        )
        body += box(x - 90, y - 32, 180, 64, fill, stroke, 32)
        body += text(x, y + 7, name if name != "live" else "sealed · live", 19, stroke, 700)
    body += arrow(232, 200, 288, 200) + text(260, 185, "submit", 14, SLATE)
    body += arrow(472, 200, 528, 200) + text(500, 185, "approve", 14, SLATE)
    body += arrow(712, 200, 808, 200) + text(760, 185, "seal", 14, SLATE)
    body += arrow(880, 234, 880, 396, BAD) + text(
        700, 300, "a covenant breach, or", 15, BAD, anchor="middle"
    )
    body += text(700, 322, "an overdue periodic review", 15, BAD)
    body += arrow(920, 396, 920, 234, OK, "a") + text(
        940, 352, "reinstated, with a reason", 15, OK, anchor="start"
    )
    body += arrow(992, 190, 1108, 130, SLATE, "g") + text(
        1030, 128, "validity ends", 14, SLATE, anchor="end"
    )
    body += arrow(992, 214, 1108, 280, SLATE, "g") + text(1030, 272, "revoked", 14, SLATE)
    body += text(
        700,
        530,
        "every call against a warrant that is not live fails closed, naming the person to contact",
        17,
        SLATE,
    )
    return svg(1400, 570, body, "An execution warrant is a live instrument, not a document")


def context() -> str:
    body = box(560, 230, 280, 190, TINT, CRIMSON, 16, 3)
    body += text(700, 290, "MAYA", 34, CRIMSON, 800)
    body += text(700, 325, "the record, the licence", 17, INK)
    body += text(700, 352, "and the evidence", 17, INK)
    body += text(700, 395, "trains nothing · serves nothing", 15, SLATE)
    left = [
        (110, "data sources", "files, SQL, producers"),
        (250, "feature pipelines", "two clocks, pinned"),
        (390, "model designers", "a formula or a black box"),
    ]
    for y, a, b in left:
        body += box(60, y, 300, 90, "#fff", LINE)
        body += text(210, y + 38, a, 19, INK, 700) + text(210, y + 64, b, 15, SLATE)
        body += arrow(364, y + 45, 552, 325 + (y - 250) / 3, SLATE, "g")
    right = [
        (80, "model registry (MLflow)", "an alias that follows the licence"),
        (205, "training compute", "a signed job, a one-day key"),
        (330, "scoring service", "a guard checks, then reports"),
        (455, "batch scoring", "sealed by hash, reported"),
    ]
    for y, a, b in right:
        body += box(1040, y, 320, 92, "#fff", NAVY)
        body += text(1200, y + 38, a, 19, NAVY, 700) + text(1200, y + 64, b, 15, SLATE)
        body += arrow(846, 325 + (y - 267) / 3, 1032, y + 46)
    body += box(460, 520, 480, 90, "#fff", LINE)
    body += text(700, 558, "validators, auditors, supervisors", 19, INK, 700)
    body += text(700, 584, "a bundle that verifies on a machine with no MAYA", 15, SLATE)
    body += arrow(700, 424, 700, 512, SLATE, "g")
    return svg(1400, 640, body, "Beside the ML platform, not instead of it")


def splits() -> str:
    import random

    rng = random.Random(8)
    body, n, x0, w = "", 28, 90, 42
    for row, (label, y) in enumerate((("a random split", 140), ("a time-ordered split", 330))):
        body += text(x0, y - 22, label, 20, CRIMSON if row else SLATE, 700, "start")
        test = set(rng.sample(range(n), 6)) if row == 0 else set(range(n - 6, n))
        val = (
            set(rng.sample([i for i in range(n) if i not in test], 3))
            if row == 0
            else set(range(n - 9, n - 6))
        )
        for i in range(n):
            fill = BAD if i in test else (NAVY if i in val else "#D6E4DA")
            body += (
                f'<rect x="{x0 + i * w}" y="{y}" width="{w - 6}" height="60" rx="6" fill="{fill}"/>'
            )
        body += text(x0, y + 92, "day 1", 14, SLATE, anchor="start") + text(
            x0 + n * w - 6, y + 92, f"day {n}", 14, SLATE, anchor="end"
        )
    body += text(
        700,
        250,
        "tests on the past, trains on the future; a recursion cannot run over scattered days",
        16,
        BAD,
    )
    body += text(
        700, 440, "the last dates are the test: the future of what the model saw, in order", 16, OK
    )
    body += '<rect x="90" y="470" width="18" height="18" rx="3" fill="#D6E4DA"/>' + text(
        116, 485, "train", 15, SLATE, anchor="start"
    )
    body += f'<rect x="200" y="470" width="18" height="18" rx="3" fill="{NAVY}"/>' + text(
        226, 485, "validation", 15, SLATE, anchor="start"
    )
    body += f'<rect x="350" y="470" width="18" height="18" rx="3" fill="{BAD}"/>' + text(
        376, 485, "escrowed test", 15, SLATE, anchor="start"
    )
    return svg(1400, 520, body, "A holdout for a series is a suffix, not a sample")


FIGURES = {
    "01-chain": chain,
    "02-two-clocks": clocks,
    "03-checksum-cycle": checksum,
    "04-warrant-lifecycle": lifecycle,
    "05-beside-the-platform": context,
    "06-splits": splits,
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    inkscape = shutil.which("inkscape")
    for name, draw in FIGURES.items():
        path = OUT / f"{name}.svg"
        path.write_text(draw(), encoding="utf-8")
        if inkscape:
            subprocess.run(
                [
                    inkscape,
                    str(path),
                    "--export-type=png",
                    f"--export-filename={OUT / name}.png",
                    "--export-dpi=144",
                ],
                check=True,
                capture_output=True,
            )
        print("wrote", path.name, "and .png" if inkscape else "(no Inkscape: SVG only)")


if __name__ == "__main__":
    main()
