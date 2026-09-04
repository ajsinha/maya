"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Configuration. YAML with a git-ignored local overlay, ${...} resolution,
typed accessors, and the precedence order command line > environment > files.
"""
from core.config.properties_configurator import (ConfigError, PropertiesConfigurator,
                                                 config)

__all__ = ["ConfigError", "PropertiesConfigurator", "config"]
