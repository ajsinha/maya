"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

How this platform's HTTP surface answers, and how it ages.
"""
from core.http.conventions import (FIELDS, SUNSET, Cursor, CursorError,
                                   Sunsetting, deprecations, derivation_of,
                                   page, project, sunset_headers)

__all__ = [
    "FIELDS",
    "SUNSET",
    "Cursor",
    "CursorError",
    "Sunsetting",
    "deprecations",
    "derivation_of",
    "page",
    "project",
    "sunset_headers",
]
