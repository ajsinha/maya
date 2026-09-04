"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Execution.

MAYA issues warrants; it does not run models. Split by responsibility: urn (the
consumer's only handle), grants (standing entitlements and revocation), signing
(credentials and expiry), descriptors (what an engine receives), warrants (the
order the checks happen in). CaptiveEngine is a reference CONSUMER of that
contract, bundled so a deployment works out of the box.
"""
from core.execution.descriptors import DescriptorFactory
from core.execution.engine import CaptiveEngine, ExecutionResult
from core.execution.errors import WarrantError
from core.execution.grants import WarrantGrants
from core.execution.warrants import WarrantService
from core.execution.signing import DescriptorSigner
from core.execution.urn import build_urn, model_urn, parse_urn

__all__ = ["WarrantService", "WarrantError", "parse_urn", "build_urn", "model_urn",
           "WarrantGrants", "DescriptorSigner", "DescriptorFactory",
           "CaptiveEngine", "ExecutionResult"]
