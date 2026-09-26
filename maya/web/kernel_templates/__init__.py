"""
The compute-kernel wizard's library of worked formulae.

Every entry is mathematics somebody in banking or insurance actually writes down, in the
notation they write it in, with each symbol's role declared. They are here to be read and
edited rather than used as they stand: the fastest way to learn what MAYA will accept is to
load something close to your problem and change it.

Two rules hold for every template, and ``tests/test_kernel_templates.py`` enforces both.
Each one parses into a valid formula IR, and each one generates a compute kernel -- so a
template cannot rot into an example that no longer works, which is the failure mode of every
library of samples that is not executed.

A third rule is a consequence of what the IR is. The formula IR is row-wise: one row in, one
row out, no state carried between rows and no aggregation. So a quantity that is an average,
a sum or a recursion over rows is an *input* here rather than a step -- a Sharpe ratio takes
the mean excess return and the volatility as inputs, because computing them is a different
kind of operation that belongs upstream of the model. Where a template does that, its note
says so.

The entries live in one module per domain, each well under the file-size gate; this
module assembles them in a fixed order and holds the group list the page shows.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.web.kernel_templates import (
    credit_lending,
    derivatives_rates,
    insurance_stats,
    markets_valuation,
)

TEMPLATES: list[dict[str, Any]] = [
    *derivatives_rates.TEMPLATES,
    *credit_lending.TEMPLATES,
    *markets_valuation.TEMPLATES,
    *insurance_stats.TEMPLATES,
]

GROUPS = [
    "Options and derivatives",
    "Rates and curves",
    "Credit risk",
    "Mortgages and retail",
    "Market risk",
    "Valuation",
    "Insurance",
    "Capital and treasury",
    "Climate and conduct",
    "Transforms and statistics",
]


def for_ui() -> list[dict[str, Any]]:
    """The library as the wizard's page needs it: roles flattened to the text of the box."""
    out = []
    for t in TEMPLATES:
        roles = "\n".join(f"{k}: {v}" for k, v in t["roles"].items())
        out.append({**t, "roles_text": roles})
    return out
