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
from core.execution.builder import WarrantBuilder
from core.execution.engine import CaptiveEngine, ExecutionResult
from core.execution.errors import WarrantError
from core.execution.sandbox import (InProcessSandbox, Limits, Sandbox,
                                    SubprocessSandbox)
from core.execution.grants import WarrantGrants
from core.execution.warrants import WarrantService
from core.execution.signing import WarrantSigner
from core.execution.grammar import GrammarValidator
from core.execution.grammar import validate as validate_warrant
from core.execution.grammar import vocabulary as warrant_grammar
from core.execution.urn import build_urn, model_urn, parse_urn

__all__ = ["WarrantService", "WarrantError", "parse_urn", "build_urn", "model_urn",
           "WarrantGrants", "WarrantSigner", "WarrantBuilder",
           "GrammarValidator", "validate_warrant", "warrant_grammar",
           "CaptiveEngine", "ExecutionResult", "Sandbox", "SubprocessSandbox",
           "InProcessSandbox", "Limits"]
