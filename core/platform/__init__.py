"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The platform's opinions about itself.

What a firm may configure, what it may not, and why the line is where it is.
"""
from core.platform.configuration import (CONFIGURABLE, FORMAT,
                                         NOT_CONFIGURABLE, Configuration,
                                         ConfigurationError)

__all__ = [
           "CONFIGURABLE",
           "FORMAT",
           "NOT_CONFIGURABLE",
           "Configuration",
           "ConfigurationError",
]
