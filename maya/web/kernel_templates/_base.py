"""
The helper every template module builds its entries with.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any


# Roles reused across many templates, so that a change of mind about one is a change in one
# place. Anything not named in a template's own roles is a feature, which is the right
# default: a feature is a column the bound feature set has to supply.
_P = "parameter"
_C = "constant"


def _t(
    key: str,
    group: str,
    title: str,
    note: str,
    formula: str,
    roles: dict[str, str] | None = None,
    keywords: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "group": group,
        "title": title,
        "note": note,
        "formula": formula.strip("\n"),
        "roles": roles or {},
        # What a search matches on, beyond the title and the group: the words somebody would
        # actually type, including the names practitioners use that are not in the title.
        "keywords": keywords,
    }
