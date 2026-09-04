"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The model registry.

Split by responsibility: catalogue (identity), versions (immutable artifacts),
aliases (governed bindings), specs (JSON to domain adapters). ModelRegistry
wires the three services.
"""
from core.registry.aliases import AliasService
from core.registry.catalogue import ModelCatalogue
from core.registry.common import RegistryError
from core.registry.models import ModelRegistry
from core.registry.specs import contract_of, schema_of
from core.registry.versions import VersionService

__all__ = ["ModelRegistry", "RegistryError", "ModelCatalogue", "VersionService",
           "AliasService", "schema_of", "contract_of"]
