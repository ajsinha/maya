"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The refusal type shared by hook issuance, resolution and execution.

``code`` is not decoration. It is the key into the error taxonomy that maps a
domain refusal onto an HTTP status in exactly one place, which is what design
rule DR-6 (no failure unmapped) and DR-7 (a refusal explains itself) rest on.
"""
from __future__ import annotations

from typing import Any, Dict


class HookError(RuntimeError):
    """Resolution or issuance refused. code maps to the error taxonomy."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, Any]:
        return {"error": self.code, "detail": self.detail, "remediation": self.remediation}
