"""
The plumbing every command group shares: how a client is opened, how a result is
printed, and what the exit codes mean (§18.3).

It lives in its own module so that the command groups can too. ``__main__`` builds the
parser and holds the catalog, model, warrant, job and export commands; ``admin`` holds
the administrative ones and ``keys`` the credential ones. Were these helpers still in
``__main__``, a group importing them and ``__main__`` importing the group would be an
import cycle.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable

from maya.core.errors import MayaError

EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_NETWORK = 0, 1, 2, 3


def client(args: argparse.Namespace) -> Any:
    from maya.sdk import Client, connect

    if args.local:
        from maya.config import load_settings
        from maya.server import build_app
        from maya.services.platform import Platform

        # job workers only: a CLI run must not deliver webhooks or run the scheduler —
        # on a restored copy of production that would reach production's receivers
        platform = Platform.build(load_settings(args.config), start_workers="jobs")
        anon = Client(app=build_app(platform), channel="cli")
        user = os.environ.get("MAYA_USER", "admin")
        pw = os.environ.get("MAYA_PASSWORD")
        if not pw:
            raise MayaError("--local needs MAYA_USER and MAYA_PASSWORD in the environment")
        token = anon.auth.login(user, pw)["token"]
        return Client(app=anon._http.app, token=token, channel="cli")
    return connect(args.profile) if args.profile else connect()


def emit(args: argparse.Namespace, data: Any, human: Callable[[Any], str] | None = None) -> None:
    if args.json or human is None:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(human(data))


def rows_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    if not rows:
        return "(none)"
    widths = [max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols]
    lines = ["  ".join(c.upper().ljust(w) for c, w in zip(cols, widths))]
    lines += ["  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(cols, widths)) for r in rows]
    return "\n".join(lines)


def definition_file(path: str) -> dict[str, Any]:
    """A definition read from JSON or YAML, whichever the file is."""
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        import yaml

        return dict(yaml.safe_load(text))
    return dict(json.loads(text))


def local_ops(args: argparse.Namespace) -> tuple[Any, Any]:
    """A platform opened beside the database, and the principal naming who is acting."""
    from maya.config import load_settings
    from maya.services.platform import Platform

    platform = Platform.build(load_settings(args.config), start_workers=False)
    username = os.environ.get("MAYA_USER", "admin")
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        if user is None:
            raise MayaError(f"No such user '{username}'; set MAYA_USER")
        return platform, platform.auth.build_principal(uow, user["id"], channel="cli")


def local_platform(args: argparse.Namespace, seed: bool = True) -> Any:
    from maya.config import load_settings
    from maya.services.platform import Platform
    from maya.services import registry

    settings = load_settings(args.config)
    if seed:
        return Platform.build(settings, start_workers=False)
    from maya.persistence.engine import database_from_settings

    db = database_from_settings(settings)
    db.verify_schema()
    platform = Platform(settings, db)
    registry.wire(platform)
    return platform


__all__ = [
    "EXIT_NETWORK",
    "EXIT_OK",
    "EXIT_REFUSED",
    "EXIT_USAGE",
    "client",
    "definition_file",
    "local_ops",
    "local_platform",
    "emit",
    "rows_table",
]
