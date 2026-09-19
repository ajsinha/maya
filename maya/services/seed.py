"""
Bootstrap (§12): default roles, the admin user, and the default workflow
policies — idempotent, run at every start, changing nothing that exists.

On an empty database MAYA creates ``admin`` / ``maya-dev-admin`` with
``must_change_password``, and warns in the log, on the login page and on the
health page while that password is unchanged.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
from typing import Any

from maya.core import kdf
from maya.core.clock import utcnow
from maya.security.roles import DESCRIPTIONS, MATRIX
from maya.services.auth import DEFAULT_ADMIN_PASSWORD
from maya.workflow.policy import default_policies

logger = logging.getLogger(__name__)


def seed(platform: Any) -> None:
    with platform.uow("system") as uow:
        _roles(uow)
        _admin(uow)
        _policies(uow)
    if platform.auth.default_admin_password_active():
        logger.warning("The bootstrap admin still uses the default password "
                       "'maya-dev-admin'. Change it now.")


def _roles(uow: Any) -> None:
    for name, caps in MATRIX.items():
        role = uow.repo("roles").find_one(name=name)
        if role is None:
            uow.repo("roles").add({"name": name, "description": DESCRIPTIONS[name],
                                   "capabilities": caps, "builtin": True})
        elif role["builtin"] and role["capabilities"] != caps:
            uow.repo("roles").update(role["id"], {"capabilities": caps})


def _admin(uow: Any) -> None:
    if uow.repo("users").count() > 0:
        return
    user = uow.repo("users").add({
        "username": "admin", "display_name": "Administrator", "email": "",
        "auth_source": "db", "password_hash": kdf.hash_password(DEFAULT_ADMIN_PASSWORD),
        "must_change_password": True, "password_changed_at": utcnow()})
    role = uow.repo("roles").find_one(name="admin")
    uow.repo("user_roles").add({"user_id": user["id"], "role_id": role["id"]})
    uow.audit("bootstrap.admin_created", object_ref="user:admin", principal_type="system",
              channel="system")


def _policies(uow: Any) -> None:
    for object_type, policy in default_policies().items():
        if uow.repo("workflow_policies").find_one(object_type=object_type, scope="*"):
            continue
        uow.repo("workflow_policies").add({
            "object_type": object_type, "scope": "*", "version_no": 1, "state": "active",
            "policy": policy, "note": "Seeded default", "approved_by": "system",
            "activated_at": utcnow()})
