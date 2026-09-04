"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The registry: models, immutable versions, and governed aliases.
"""
from core.registry.models import ModelRegistry, RegistryError

__all__ = ["ModelRegistry", "RegistryError"]
