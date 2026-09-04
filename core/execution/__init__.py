"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Execution.

MAYA issues hooks; it does not run models. HookService mints the signed
contract. CaptiveEngine is a reference CONSUMER of that contract, bundled so a
deployment works out of the box and disabled by a single configuration key.
"""
from core.execution.engine import CaptiveEngine, ExecutionResult
from core.execution.hooks import HookError, HookService, parse_urn

__all__ = ["HookService", "HookError", "parse_urn", "CaptiveEngine", "ExecutionResult"]
