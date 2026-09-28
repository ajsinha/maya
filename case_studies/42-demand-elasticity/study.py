"""
What the steps of this case study share: names, the feed, the two models and the people.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

NS = "pricing"
DATA = Path(__file__).resolve().parent / "data"
FEED = "weekly_sales"
PANEL = "weekly_demand_panel"
PIN = "fy2025"
AS_OF = dt.date(2025, 12, 31)
PIN_REF = f"maya://featureset/{NS}/{PANEL}#{PIN}/{AS_OF}"
SEED = 42

# Recorded on each warrant as its exception to the leakage certificate.
LEAKAGE_JUSTIFICATION = (
    "Weekly sales are finalised two days after the week closes, so every row is known after "
    "the date it describes. The models explain how demand responds to price, fitted on "
    "history; they are not forecasts made at the start of a week, and no row is used to "
    "decide anything about the week it describes."
)

CHAMPION = "weekly_demand_linear"
CHALLENGER = "weekly_demand_constant_elasticity"
CHAMPION_WARRANT = "demand_linear_fit"
CHALLENGER_WARRANT = "demand_loglog_fit"
OTHER_WARRANT = "demand_loglog_reseeded"

# dev2 fits the challenger as a second model developer; lara, a second manager, decides
EXTRA_USERS = {"lara": ["model_manager"], "dev2": ["model_developer"]}

FEATURE_DEF = {
    "index": ["date", "product"],
    "index_types": {"date": "date", "product": "string"},
    "schema": [
        {"name": "price_index", "type": "float64"},
        {"name": "demand_index", "type": "float64"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "range", "attr": "price_index", "min": 0.1, "max": 5.0}],
}
PANEL_DEF = {
    "index": ["date", "product"],
    "grid": "as_is",
    "alignment": {"mode": "inner"},
    "members": [
        {"attr": "price", "ref": f"maya://feature/{NS}/{FEED}@v1", "source_attr": "price_index"},
        {"attr": "demand", "ref": f"maya://feature/{NS}/{FEED}@v1", "source_attr": "demand_index"},
    ],
}

MODELS = {
    CHAMPION: {
        "formula": r"demand = a + b\,price",
        "roles": {"a": "parameter", "b": "parameter", "price": "feature"},
        "description": "Demand as a straight line in price: the model in production today",
    },
    CHALLENGER: {
        "formula": r"demand = e^{\alpha}\,price^{\beta}",
        "roles": {"alpha": "parameter", "beta": "parameter", "price": "feature"},
        "description": "Constant elasticity: demand as a power of price, beta the elasticity",
    },
}


def spec_document(name: str) -> str:
    sections = {
        "Purpose": f"{name}: weekly demand for a product, relative to its normal, from its relative price.",
        "Scope and Limitations": "The grocery range; prices between 0.6 and 1.4 of reference.",
        "Mathematical Formulation": MODELS[name]["formula"].replace("\\,", " "),
        "Assumptions": "One response to price shared by the whole range; no cross-price effects.",
        "Data and Features Used": "Weekly price and demand indices per product, two years.",
        "Calibration Methodology": "Least squares on the warrant's training rows; the log-log "
        "model is fitted by least squares on the logarithms.",
        "Validation Evidence": "Blind scoring on the escrowed holdout, and a paired comparison "
        "against the other model on the same rows.",
        "Known Weaknesses": "Ignores seasonality, competitor prices and stock-outs.",
        "Change Log": "v1: first version.",
    }
    body = "".join(f"\\section{{{t}}}\n{x}\n" for t, x in sections.items())
    return f"\\documentclass{{article}}\n\\begin{{document}}\n{body}\\end{{document}}\n"


class Cast:
    def __init__(self, maya: Any) -> None:
        for name in ("dana", "mick", "mona", "devi", "dev2", "mgr", "lara", "admin"):
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


def approved_parameters(warrant: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in warrant["parameter_sets"] if p["state"] == "approved")


# One line each, shown under the name in MAYA's lists: what the object is, in words.
DESCRIPTIONS = {
    "weekly_sales": "Weekly price and demand index per product",
    "weekly_demand_panel": "One row per product and week: price and demand",
    "weekly_demand_linear": "Demand as a straight line in price: the model in production today",
    "weekly_demand_constant_elasticity": "Constant elasticity: demand as a power of price, beta the elasticity",
}
