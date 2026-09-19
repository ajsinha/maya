#!/usr/bin/env python
"""
MAYA — Model & AI Lifecycle Assurance · the one supported entry point.

    python run_maya_web.py                          # config/application.yaml
    python run_maya_web.py --config=path/to.yaml    # another configuration
    python run_maya_web.py --db.dialect=postgresql --server.port=9000
    python run_maya_web.py --worker                 # job workers, no web server

Any setting can be overridden as ``--key=value`` (spec §24.2). This script is
the only supported way to start MAYA (§24.5): a second way to start a server
is a second set of startup invariants to get wrong — which is exactly why the
worker fleet of §15.1 and §24.1 is a flag here and not a second script. With
``--worker`` the process binds no port and serves no request; it opens the
database an already-running MAYA prepared, registers the same job handlers and
drains the same queue, so a forty-minute pin runs somewhere other than the
interpreter a user is waiting on. Run as many as the database will carry
(PostgreSQL: SQLite admits one writer, so a worker there contends with the web
process). It is not the process that creates or seeds the estate, and it runs
neither the scheduler nor the webhook dispatcher: those stay with the launcher.

It must be run as ``python run_maya_web.py``: the multiprocessing start
method is set to ``spawn`` here, before anything else imports, because MAYA
runs identically on Windows, Linux and macOS and ``spawn`` re-imports.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import multiprocessing


def _setup_multiprocessing() -> None:
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass


if __name__ == "__main__":
    _setup_multiprocessing()

import atexit  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402
import sys  # noqa: E402
from datetime import datetime  # noqa: E402

from maya.core.version import APP_SLOGAN, APP_TAGLINE, BUILD_DATE, VERSION  # noqa: E402

logger = logging.getLogger("maya")
_platform = None
_shutting_down = False

BANNER = r"""
================================================================================
     ███╗   ███╗ █████╗ ██╗   ██╗ █████╗
     ████╗ ████║██╔══██╗╚██╗ ██╔╝██╔══██╗     {tagline}
     ██╔████╔██║███████║ ╚████╔╝ ███████║     "{slogan}"
     ██║╚██╔╝██║██╔══██║  ╚██╔╝  ██╔══██║
     ██║ ╚═╝ ██║██║  ██║   ██║   ██║  ██║     Version {version}  ·  Build {build}
     ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝     Python {python}  ·  {platform}
================================================================================
"""


def _config_path(argv: list[str]) -> str:
    for arg in argv[1:]:
        if arg.startswith("--config="):
            return arg.split("=", 1)[1]
    return os.environ.get("MAYA_CONFIG_FILE", "config/application.yaml")


def _print_banner(platform: object) -> None:
    from maya.core.backends import Backends
    from maya.security.sandbox import sandbox_tier

    print(
        BANNER.format(
            tagline=APP_TAGLINE,
            slogan=APP_SLOGAN,
            version=VERSION,
            build=BUILD_DATE,
            python=sys.version.split()[0],
            platform=sys.platform,
        )
    )
    s = platform.settings  # type: ignore[attr-defined]
    tier = sandbox_tier()
    rows = [
        ("Role", platform.role),  # type: ignore[attr-defined]
        ("Environment", s.environment),
        ("Database", f"{platform.db.dialect}  (schema/{platform.db.dialect}.sql)"),  # type: ignore[attr-defined]
        ("maya_delta", f"{platform.lake.backend_name}  — {platform.lake.delta.info.reason}"),  # type: ignore[attr-defined]
        ("Sandbox tier", f"{tier['tier']}  — {tier['reason']}"),
        ("Storage root", str(s.storage_root.resolve())),
        ("Job workers", str(platform.jobs.n_workers)),
    ]  # type: ignore[attr-defined]
    for label, value in rows:
        print(f"  {label:<14}{value}")
    print(
        "  Seams         "
        + ", ".join(
            f"{c['seam']}={c['selected']}" + ("*" if c["selected"] != c["preferred"] else "")
            for c in Backends.report()
        )
    )
    print("                (* = not the preferred backend; see the health page for the cost)")
    if platform.auth.default_admin_password_active():  # type: ignore[attr-defined]
        print(
            "\n  !! The bootstrap admin still uses the default password 'maya-dev-admin'. "
            "Change it now."
        )
    print("=" * 80)


def _shutdown(*_: object) -> None:
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    logger.info("MAYA shutting down: draining job workers")
    if _platform is not None:
        _platform.shutdown()


def _supervise(workers: int, host: str, port: int, loop: str) -> None:
    """Run ``workers`` web processes, each on its own SO_REUSEPORT socket so the kernel
    spreads connections evenly; restart any that dies until MAYA is asked to stop."""
    import time
    from maya.server import serve_web_process

    ctx = multiprocessing.get_context("spawn")

    def start() -> multiprocessing.Process:
        proc = ctx.Process(target=serve_web_process, args=(host, port, loop), daemon=True)
        proc.start()
        return proc

    procs = [start() for _ in range(workers)]
    try:
        while not _shutting_down:
            for i, proc in enumerate(procs):
                if not proc.is_alive():
                    logger.warning(
                        "web process %s exited (%s); starting another", proc.pid, proc.exitcode
                    )
                    procs[i] = start()
            time.sleep(1.0)
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.join(10)


def _serve_jobs(platform: object) -> None:
    """A worker process: drain the queue until a signal asks it to stop.

    There is no server to block on, so the main thread waits on the stop event the
    signal handlers set. Draining is what ``platform.jobs`` threads already do; this
    only keeps the process alive and leaves through the same clean shutdown as the web
    process, so a job in flight finishes rather than being abandoned half-written.
    """
    import threading

    s = platform.settings  # type: ignore[attr-defined]
    print(
        f"\n  Job worker: {platform.jobs.n_workers} thread(s) draining the queue"  # type: ignore[attr-defined]
        f" on {platform.db.dialect}. No port is bound.\n"  # type: ignore[attr-defined]
    )
    logger.info("MAYA job worker ready (environment %s)", s.environment)
    idle = threading.Event()
    while not _shutting_down:
        idle.wait(0.5)


def main(argv: list[str]) -> int:
    global _platform
    if any(a in ("-h", "--help") for a in argv[1:]):
        print(__doc__)
        print(
            BANNER.format(
                tagline=APP_TAGLINE,
                slogan=APP_SLOGAN,
                version=VERSION,
                build=BUILD_DATE,
                python=sys.version.split()[0],
                platform=sys.platform,
            )
        )
        return 0
    from maya.config import load_settings
    from maya.observability.logs import configure

    settings = load_settings(_config_path(argv))
    configure(
        settings.get("logging.level", "INFO") or "INFO",
        settings.get("logging.format", "text") or "text",
        settings.get("logging.file"),
    )
    logger.info("MAYA %s starting at %s (pid %s)", VERSION, datetime.now().isoformat(), os.getpid())
    from maya.services.platform import Platform
    from maya.server import build_app

    worker_only = "--worker" in argv[1:]
    _platform = Platform.build(settings, role="worker" if worker_only else "primary")
    _print_banner(_platform)
    atexit.register(_shutdown)
    signal.signal(signal.SIGINT, lambda *a: (_shutdown(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *a: (_shutdown(), sys.exit(0)))
    if worker_only:
        _serve_jobs(_platform)
        return 0
    import uvicorn

    host = settings.get("server.host", "127.0.0.1") or "127.0.0.1"
    port = settings.int("server.port", 8600)
    workers = settings.int("server.workers", 1)
    from maya.core.backends import Backends

    loop = "uvloop" if Backends.selected("event_loop") == "uvloop" else "asyncio"
    print(
        f"\n  Serving on http://{host}:{port}   (API docs: /api/v1/docs)"
        + (f"   ·   {workers} web processes" if workers > 1 else "")
        + "\n"
    )
    if workers > 1:
        # This process keeps the job workers, webhooks and scheduler and starts
        # ``workers`` web processes (spawned, so each re-reads the same configuration
        # and --key=value overrides). Make the signing keys now, not in a race between them.
        from maya.server import balanced_sockets, check_web_processes

        check_web_processes(workers, _platform.db.dialect)
        os.environ["MAYA_CONFIG_FILE"] = os.path.abspath(_config_path(argv))
        _platform.signer_or_none()
        if balanced_sockets():
            _supervise(workers, host, port, loop)
        else:
            uvicorn.run(
                "maya.server:web_worker",
                factory=True,
                workers=workers,
                host=host,
                port=port,
                log_level="warning",
                loop=loop,
                proxy_headers=True,
                access_log=False,
            )
    else:
        uvicorn.run(
            build_app(_platform),
            host=host,
            port=port,
            log_level="warning",
            loop=loop,
            proxy_headers=True,
            access_log=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
