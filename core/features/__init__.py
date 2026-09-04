"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature platform.

Split by responsibility: catalogue (definitions), views (materialisation and
namespacing), contracts (pinning), assembly (point-in-time training sets), pit
(the verification primitives they rest on). FeatureRegistry wires the four.
"""
from core.features.assembly import TrainingSetBuilder
from core.features.catalogue import FeatureCatalogue
from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, FeatureError
from core.features.contracts import ContractBinder
from core.features.pit import (AssemblyRejected, AssemblyRequest, PitReport,
                              detect_leakage, static_check, verify_sampled)
from core.features.registry import FeatureRegistry
from core.features.views import ViewManager

__all__ = ["FeatureRegistry", "FeatureError", "FeatureCatalogue", "ViewManager",
           "ContractBinder", "TrainingSetBuilder", "AssemblyRejected", "AssemblyRequest",
           "PitReport", "detect_leakage", "static_check", "verify_sampled", "VALID_TIME", "INGEST_TIME", "ENTITY"]
