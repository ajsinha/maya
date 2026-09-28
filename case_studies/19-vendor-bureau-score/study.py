"""
What the steps of this case study share: names, the two feeds, the panel, and the people.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

NS = "bureau"
DATA = Path(__file__).resolve().parent / "data"
VENDOR = DATA / "vendor"
INPUTS = ("utilisation", "delinquencies", "age_of_file", "inquiries")
PANEL = "credit_application_panel"
PIN = "fy2025"
AS_OF = dt.date(2025, 12, 31)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL = "vendor_bureau_credit_score"
WARRANT = "bureau_validation"
LIVE = "bureau_score_live"
CONTACT = "credit-risk-models@example.com"
EXTRA_USERS = {"lara": ["model_manager"]}

TARGET_JUSTIFICATION = (
    "The target is a twelve-month default flag, known a year after the application by "
    "construction. It is the outcome being validated against and never an input: the four "
    "bureau attributes the score reads are all known on the application date."
)

APPLICATIONS_DEF = {
    "index": ["date", "applicant"],
    "index_types": {"date": "date", "applicant": "string"},
    "schema": [
        {"name": "utilisation", "type": "float64"},
        {"name": "delinquencies", "type": "int64"},
        {"name": "age_of_file", "type": "float64"},
        {"name": "inquiries", "type": "int64"},
        {"name": "region", "type": "string"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "utilisation", "min": 0.0, "max": 1.0}],
}
OUTCOMES_DEF = {
    "index": ["date", "applicant"],
    "index_types": {"date": "date", "applicant": "string"},
    "schema": [{"name": "default_12m", "type": "int64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "default_12m"}],
}
PANEL_DEF = {
    "index": ["date", "applicant"],
    "grid": "as_is",
    "alignment": {"mode": "inner"},
    "members": [
        *(
            {"attr": a, "ref": f"maya://feature/{NS}/applications@v1", "source_attr": a}
            for a in (*INPUTS, "region")
        ),
        {
            "attr": "default_12m",
            "ref": f"maya://feature/{NS}/outcomes@v1",
            "source_attr": "default_12m",
        },
    ],
}

SECTIONS = {
    "Purpose": "BureauScore 4.1, bought from a credit bureau, estimates the probability that an "
    "applicant defaults within twelve months. It is used to decline or refer applications.",
    "Scope and Limitations": "Personal-loan applicants with a bureau file. Thin files and "
    "business borrowers are out of scope.",
    "Mathematical Formulation": "Proprietary. The vendor discloses the inputs and that the "
    "output is a probability; the mathematics is a black box to the bank.",
    "Assumptions": "The applicant population resembles the vendor's development sample.",
    "Data and Features Used": "Revolving utilisation, delinquencies, age of file and recent "
    "inquiries from the bureau file pulled at application.",
    "Calibration Methodology": "Calibrated by the vendor; the bank does not refit it.",
    "Validation Evidence": "Blind scoring of the vendor's code in MAYA's sandbox on an escrowed "
    "holdout of the bank's own outcomes; performance by region; permutation importance.",
    "Known Weaknesses": "Opaque. Sensitive to shifts in utilisation, which is why a drift "
    "covenant watches that input in production.",
    "Change Log": "4.1: first use at this bank.",
}


def spec_document() -> str:
    body = "".join(f"\\section{{{t}}}\n{x}\n" for t, x in SECTIONS.items())
    return f"\\documentclass{{article}}\n\\begin{{document}}\n{body}\\end{{document}}\n"


class Cast:
    def __init__(self, maya: Any) -> None:
        for name in ("dana", "mick", "mona", "devi", "mgr", "lara", "admin"):
            setattr(self, name, maya.client(name))


def feed(name: str) -> bytes:
    path = DATA / f"{name}.csv"
    if not path.exists():
        raise SystemExit(f"{path} is missing. Write it with make_data.py in this folder.")
    return path.read_bytes()


def find_warrant(client: Any, name: str) -> dict[str, Any]:
    for row in client.training.list():
        if row["name"] == name:
            return dict(client.training.get(row["id"]))
    raise SystemExit(f"No training warrant called '{name}' yet")


# One line each, shown under the name in MAYA's lists: what the object is, in words.
DESCRIPTIONS = {
    "applications": "Credit applications: bureau utilisation, delinquencies, file age, inquiries and region",
    "outcomes": "Whether each applicant defaulted within 12 months",
    "credit_application_panel": "One row per application: the bureau attributes and the 12-month default",
    "vendor_bureau_credit_score": "BureauScore 4.1, bought from a credit bureau",
}
