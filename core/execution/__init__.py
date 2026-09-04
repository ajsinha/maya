"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Execution.

MAYA issues hooks; it does not run models. Split by responsibility: urn (the
consumer's only handle), grants (standing entitlements and revocation), signing
(credentials and expiry), descriptors (what an engine receives), hooks (the
order the checks happen in). CaptiveEngine is a reference CONSUMER of that
contract, bundled so a deployment works out of the box.
"""
from core.execution.descriptors import DescriptorFactory
from core.execution.engine import CaptiveEngine, ExecutionResult
from core.execution.errors import HookError
from core.execution.grants import HookGrants
from core.execution.hooks import HookService
from core.execution.signing import DescriptorSigner
from core.execution.urn import build_urn, model_urn, parse_urn

__all__ = ["HookService", "HookError", "parse_urn", "build_urn", "model_urn",
           "HookGrants", "DescriptorSigner", "DescriptorFactory",
           "CaptiveEngine", "ExecutionResult"]
