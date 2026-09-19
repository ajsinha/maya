"""
The one clock: timezone-aware UTC now, at microsecond resolution.

Application code takes the time from here; the persistence package stores it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
