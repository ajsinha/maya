"""
What the steps of this case study share: names, the feature definition, the two versions
of the model, its specification document, and the people who act.

Nothing here talks to MAYA. The steps find each other's work by name, the way a person or
a scheduled job would.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

NS = "regulatory_capital"
DATA = Path(__file__).resolve().parent / "data"
FEED = "corporate_exposures"
PANEL = "irb_panel"
PIN = "ye2025"
AS_OF = dt.date(2025, 12, 31)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
MODEL = "irb_corporate"
WARRANT_V1 = "irb_reconcile_v1"
WARRANT_V2 = "irb_reconcile_v2"
LIVE = "irb_capital_live"
CONTACT = "regulatory-capital@example.com"

# Why a late knowledge time is not leakage here, recorded on each warrant as its exception.
LEAKAGE_JUSTIFICATION = (
    "This is a reporting calculation, not a forecast: capital at a quarter-end is computed "
    "after the quarter closes, from figures that are finalised twenty-five days later. Using "
    "values known after the date they describe is the purpose of the calculation, and no "
    "decision is taken at the quarter-end on the strength of it."
)

# lara is the independent validator: a model manager who did not build the model
EXTRA_USERS = {"lara": ["model_manager"]}

FEATURE_DEF = {
    "index": ["date", "obligor"],
    "index_types": {"date": "date", "obligor": "string"},
    "schema": [
        {"name": "pd", "type": "float64", "description": "one-year probability of default"},
        {"name": "lgd", "type": "float64", "description": "loss given default"},
        {"name": "ead", "type": "float64", "description": "exposure at default"},
        {"name": "maturity", "type": "float64", "description": "effective maturity, years"},
        {"name": "reference_k", "type": "float64", "description": "regulator's reference K"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "pd"},
        {"check": "range", "attr": "pd", "min": 0.0003, "max": 1.0},
        {"check": "range", "attr": "lgd", "min": 0.0, "max": 1.0},
    ],
}

PANEL_DEF = {
    "index": ["date", "obligor"],
    "grid": "as_is",
    "alignment": {"mode": "inner"},
    "members": [
        {"attr": "pd", "ref": f"maya://feature/{NS}/{FEED}@v1", "source_attr": "pd"},
        {"attr": "lgd", "ref": f"maya://feature/{NS}/{FEED}@v1", "source_attr": "lgd"},
        {"attr": "M", "ref": f"maya://feature/{NS}/{FEED}@v1", "source_attr": "maturity"},
        {
            "attr": "reference_k",
            "ref": f"maya://feature/{NS}/{FEED}@v1",
            "source_attr": "reference_k",
        },
    ],
}

# Version 1, as first written. It is the formula in CRE31 -- except that the maturity goes
# in as reported, where the regulation floors it at one year and caps it at five.
FORMULA_V1 = r"""
R = 0.12 \frac{1 - \exp(-50\,pd)}{1 - \exp(-50)} + 0.24 \left(1 - \frac{1 - \exp(-50\,pd)}{1 - \exp(-50)}\right)
b = (0.11852 - 0.05478 \log(pd))^2
mat = (1 + (M - 2.5)\,b) / (1 - 1.5\,b)
cond = ncdf((N^{-1}(pd) + \sqrt{R}\,N^{-1}(0.999)) / \sqrt{1 - R})
k = (lgd \cdot cond - pd \cdot lgd) \cdot mat
""".strip()
# Version 2: the floor and the cap, and nothing else.
FORMULA_V2 = FORMULA_V1.replace(r"(M - 2.5)", r"(\max(1, \min(M, 5)) - 2.5)")
ROLES = {"pd": "feature", "lgd": "feature", "M": "feature"}

SECTIONS = {
    "Purpose": "Computes the Pillar 1 credit-risk capital requirement K per unit of exposure at "
    "default for corporate exposures under the foundation IRB approach.",
    "Scope and Limitations": "Corporate exposures only. Not for retail, specialised lending, "
    "or exposures in default. The SME firm-size adjustment is not applied.",
    "Mathematical Formulation": "The single-factor Vasicek formula of Basel CRE31: asset "
    "correlation $R$ as a function of PD, the maturity adjustment $b$, and "
    "$K = [LGD \\cdot N((N^{-1}(PD) + \\sqrt{R} N^{-1}(0.999))/\\sqrt{1-R}) - PD \\cdot LGD] "
    "\\cdot (1 + (M - 2.5) b)/(1 - 1.5 b)$.",
    "Assumptions": "PD is floored at three basis points by the rating system upstream. "
    "Effective maturity is supplied in years.",
    "Data and Features Used": "PD, LGD and effective maturity per obligor at quarter-end, from "
    "the corporate exposures feed, known twenty-five days after the quarter closes.",
    "Calibration Methodology": "None. Every constant is prescribed by regulation; the model has "
    "no parameter to fit, and its evidence is reconciliation, not calibration.",
    "Validation Evidence": "Reconciliation, obligor by obligor, against the regulator's "
    "reference calculation on the year-end pin, scored blind by MAYA.",
    "Known Weaknesses": "Inherits every weakness of the single-factor model: one systematic "
    "factor, a correlation prescribed rather than estimated, and no diversification benefit.",
    "Change Log": "v1: first implementation. v2: effective maturity floored at one year and "
    "capped at five, as CRE31.46 requires (finding raised by the validator).",
}


def spec_document(version: int) -> str:
    body = "".join(f"\\section{{{title}}}\n{text}\n" for title, text in SECTIONS.items())
    return f"\\documentclass{{article}}\n\\begin{{document}}\n% version {version}\n{body}\\end{{document}}\n"


class Cast:
    """The people, each with their own roles and their own SDK client."""

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
