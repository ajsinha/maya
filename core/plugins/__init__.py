"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Which parts of this platform a deployment may extend, and which it may not.
"""
from core.plugins.common import PluginError
from core.plugins.registry import (AXES, CLOSED, OPEN, ExtensionPoints,
                                   describe)

__all__ = ["AXES", "CLOSED", "OPEN", "ExtensionPoints", "PluginError",
           "describe"]
