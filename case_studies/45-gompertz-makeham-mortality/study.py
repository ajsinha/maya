"""
What the steps of this case study share: names, the feed, the mortality law and the people.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

NS = "mortality"
DATA = Path(__file__).resolve().parent / "data"
FEED = "mortality_experience"
PANEL = "experience_panel"
PIN = "exp2024"
AS_OF = dt.date(2024, 12, 31)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL = "unisex_mortality"
WARRANT = "mortality_calibration_2024"
EXTRA_USERS = {"lara": ["model_manager"]}

LEAKAGE_JUSTIFICATION = (
    "Mortality experience for a year is published six months after it ends, so every row is "
    "known after the date it describes. The table is calibrated on completed history and "
    "used for the future; no row informs a decision about the year it describes."
)

FEATURE_DEF = {
    "index": ["date", "cell"],
    "index_types": {"date": "date", "cell": "string"},
    "schema": [
        {"name": "age", "type": "float64"},
        {"name": "t", "type": "float64"},
        {"name": "sex", "type": "string"},
        {"name": "region", "type": "string"},
        {"name": "exposure", "type": "float64"},
        {"name": "deaths", "type": "int64"},
        {"name": "rate", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "age", "min": 0, "max": 120}],
}
PANEL_DEF = {
    "index": ["date", "cell"],
    "grid": "as_is",
    "alignment": {"mode": "inner"},
    "members": [
        {"attr": a, "ref": f"maya://feature/{NS}/{FEED}@v1", "source_attr": a}
        for a in ("age", "t", "sex", "region", "rate")
    ],
}

FORMULA = r"mu = (A + B\,e^{\gamma\,age})\,e^{-\lambda\,t}"
ROLES = {
    "A": "parameter",
    "B": "parameter",
    "gamma": "parameter",
    "lambda": "parameter",
    "age": "feature",
    "t": "feature",
}

SECTIONS = {
    "Purpose": "A unisex table of central death rates by age for pricing annuities and life cover.",
    "Scope and Limitations": "Ages 40 to 95. Deliberately unisex: under the EU Gender Directive "
    "(Test-Achats, C-236/09) premiums may not differ by sex, so sex is not an input.",
    "Mathematical Formulation": "Gompertz-Makeham with an improvement factor: "
    "$\\mu(x, t) = (A + B e^{\\gamma x}) e^{-\\lambda t}$.",
    "Assumptions": "Mortality improves at a constant rate; regional differences are small.",
    "Data and Features Used": "Ten years of deaths and exposures by age, sex and region.",
    "Calibration Methodology": "Non-linear least squares: a grid over gamma and lambda with "
    "linear least squares for A and B inside it.",
    "Validation Evidence": "Blind scoring on the escrowed holdout; error and bias by sex and "
    "region; permutation importance of age and calendar time.",
    "Known Weaknesses": "Being unisex, it understates male and overstates female mortality; "
    "the size of that cross-subsidy is measured and reserved for.",
    "Change Log": "v1: calibrated to 2015-2024 experience.",
}


def spec_document() -> str:
    body = "".join(f"\\section{{{t}}}\n{x}\n" for t, x in SECTIONS.items())
    return f"\\documentclass{{article}}\n\\begin{{document}}\n{body}\\end{{document}}\n"


class Cast:
    def __init__(self, maya: Any) -> None:
        for name in ("dana", "mick", "mona", "devi", "mgr", "lara", "admin"):
            setattr(self, name, maya.client(name))


def feed() -> bytes:
    path = DATA / f"{FEED}.csv"
    if not path.exists():
        raise SystemExit(f"{path} is missing. Write it with make_data.py in this folder.")
    return path.read_bytes()


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet")
