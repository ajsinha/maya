"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The feature platform.

Split by responsibility: catalogue (definitions), derived (values computed from
values), views (materialisation and namespacing), sets (a named, versioned
presentation of X), contracts (pinning), assembly (point-in-time training sets),
pit (the verification primitives they rest on), expressions (the small language a
derived feature is written in). FeatureRegistry wires them.
"""
from core.features.assembly import TrainingSetBuilder
from core.features.catalogue import FeatureCatalogue
from core.features.common import ENTITY, INGEST_TIME, VALID_TIME, FeatureError
from core.features.contracts import ContractBinder
from core.features.derived import DerivedFeatures
from core.features.expressions import Expression
from core.features.pit import (AssemblyRejected, AssemblyRequest, PitReport,
                              detect_leakage, screen_leakage, static_check,
                              verify_sampled)
from core.features.registry import FeatureRegistry
from core.features.sets import PIT_RULE, FeaturesetRegistry
from core.features.transfer import FORMATS, FeatureTransfer
from core.features.views import ViewManager

__all__ = [
                              "ENTITY",
                              "FORMATS",
                              "INGEST_TIME",
                              "PIT_RULE",
                              "VALID_TIME",
                              "AssemblyRejected",
                              "AssemblyRequest",
                              "ContractBinder",
                              "DerivedFeatures",
                              "Expression",
                              "FeatureCatalogue",
                              "FeatureError",
                              "FeatureRegistry",
                              "FeatureTransfer",
                              "FeaturesetRegistry",
                              "PitReport",
                              "TrainingSetBuilder",
                              "ViewManager",
                              "detect_leakage", "screen_leakage",
                              "static_check",
                              "verify_sampled",
]
