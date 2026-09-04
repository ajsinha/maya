"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The registry's shared refusal type.
"""
from __future__ import annotations


class RegistryError(RuntimeError):
    """A registry operation was refused. The message always says why."""
