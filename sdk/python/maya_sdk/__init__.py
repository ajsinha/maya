"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The Python client for MAYA.

    from maya_sdk import Maya, Refused

    maya = Maya("https://maya.internal", "d.raman", "…")
    try:
        maya.models.register(urn="maya://model/credit.pd.smallbiz", …)
    except Refused as exc:
        print(exc.code, exc.detail, exc.remediation, exc.request_id)

Standard library only, because a governance platform that cannot be deployed
air-gapped is one somebody works around, and an SDK with a dependency tree moves
that problem into the client's build pipeline rather than solving it.
"""
from maya_sdk.client import Maya
from maya_sdk.errors import (Blocked, MayaError, NotAuthenticated, NotFound,
                             NotPermitted, Refused, Unreachable)
from maya_sdk.transport import HttpTransport, Response

__all__ = ["Maya", "MayaError", "Refused", "Unreachable", "NotAuthenticated",
           "NotPermitted", "NotFound", "Blocked", "HttpTransport", "Response"]

__version__ = "0.1.0"
