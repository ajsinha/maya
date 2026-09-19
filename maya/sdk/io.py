"""
Data helpers for SDK callers: the value-based checksum MAYA issues on every
download, recomputed locally so a caller verifies what it received (§18.2.5).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.core import canonical


def table_checksum(table: Any) -> str:
    """The canonical content hash of an Arrow table — identical to the server's."""
    return canonical.table_content_hash(table)
