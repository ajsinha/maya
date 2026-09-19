"""
Composition root: one ASGI application serving the API under ``/api/v1`` and
the web UI beside it. The UI reaches the API only through the SDK's
``inproc`` transport, so it holds no privileged path (§13, §16).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
import socket
import sys
from typing import Any

from fastapi import FastAPI

from maya.api import limits
from maya.api.app import create_api


def build_app(platform: Any) -> FastAPI:
    app = create_api(platform)
    from maya.web.app import mount_web

    mount_web(
        app,
        secret_key=platform.settings.session_secret(),
        secure_cookies=platform.settings.environment != "dev",
    )
    limits.install(app, platform.settings)  # body size, rate, concurrency, deadline
    return app


def web_worker() -> FastAPI:
    """uvicorn's application factory for each web process when ``server.workers`` is
    above 1. Every process serves the same application; only the launching process
    (``run_maya_web.py``) seeds, reaps and runs jobs, webhooks and the scheduler. Jobs
    submitted here are rows in the shared database, which its workers poll."""
    from maya.config import load_settings
    from maya.observability.logs import configure
    from maya.services.platform import Platform

    settings = load_settings(os.environ.get("MAYA_CONFIG_FILE"))
    configure(
        settings.get("logging.level", "INFO") or "INFO",
        settings.get("logging.format", "text") or "text",
        settings.get("logging.file"),
    )
    return build_app(Platform.build(settings, start_workers=False, primary=False))


def check_web_processes(workers: int, dialect: str) -> None:
    """Several web processes need a database that takes writers from several processes.
    SQLite serialises writers inside one process (the unit of work's mutex); across
    processes, read-then-write steps such as linking the audit chain could interleave."""
    if workers > 1 and dialect == "sqlite":
        from maya.core.errors import ConfigurationError

        raise ConfigurationError(
            f"server.workers is {workers}, but the database is SQLite, which admits one "
            "writing process. Use PostgreSQL (db.dialect: postgresql) for several web "
            "processes, or set server.workers: 1.",
            workers=workers,
        )


def balanced_sockets() -> bool:
    """Linux spreads new connections evenly across sockets bound with SO_REUSEPORT; a
    single shared socket lets a few processes take most long-lived connections."""
    return sys.platform.startswith("linux") and hasattr(socket, "SO_REUSEPORT")


def serve_web_process(host: str, port: int, loop: str) -> None:
    """One web process with its own SO_REUSEPORT socket (the target of each process
    ``run_maya_web.py`` starts when ``balanced_sockets()``)."""
    import uvicorn

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind((host, port))
    sock.listen(2048)
    sock.set_inheritable(True)
    config = uvicorn.Config(
        web_worker(), log_level="warning", loop=loop, proxy_headers=True, access_log=False
    )
    uvicorn.Server(config).run(sockets=[sock])
