"""
The MAYA Python SDK (§18.2) — the only client of MAYA, used by the web UI,
the CLI, notebooks and CI alike.

    import maya.sdk as maya
    my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
    for f in my.features.list(namespace="equity.pricing"):
        print(f["name"])

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from maya.sdk._shared.errors import (
    ConflictError,
    ContractMismatch,
    LicenceBreach,
    MayaError,
    NotApproved,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    QuotaExceeded,
    ValidationFailed,
    WarrantExpired,
    WarrantSuspended,
)
from maya.sdk.client import AsyncClient, Client, connect
from maya.sdk.offline import Offline, offline

__all__ = [
    "AsyncClient",
    "Client",
    "connect",
    "offline",
    "Offline",
    "MayaError",
    "PermissionDenied",
    "ContractMismatch",
    "WarrantExpired",
    "WarrantSuspended",
    "QuotaExceeded",
    "ValidationFailed",
    "ConflictError",
    "NotApproved",
    "LicenceBreach",
    "NotFound",
    "NotAuthenticated",
]
