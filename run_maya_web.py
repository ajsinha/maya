#!/usr/bin/env python
"""
MAYA — Model & AI Lifecycle Assurance · the one supported entry point.

    python run_maya_web.py                          # config/application.yaml
    python run_maya_web.py --config=path/to.yaml    # another configuration
    python run_maya_web.py --db.dialect=postgresql --server.port=9000

Any setting can be overridden as ``--key=value`` (spec §24.2). This script is
the only supported way to start MAYA (§24.5): a second way to start a server
is a second set of startup invariants to get wrong.

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
    print(BANNER.format(tagline=APP_TAGLINE, slogan=APP_SLOGAN, version=VERSION,
                        build=BUILD_DATE, python=sys.version.split()[0], platform=sys.platform))
    s = platform.settings  # type: ignore[attr-defined]
    tier = sandbox_tier()
    rows = [("Environment", s.environment),
            ("Database", f"{platform.db.dialect}  (schema/{platform.db.dialect}.sql)"),  # type: ignore[attr-defined]
            ("maya_delta", f"{platform.lake.backend_name}  — {platform.lake.delta.info.reason}"),  # type: ignore[attr-defined]
            ("Sandbox tier", f"{tier['tier']}  — {tier['reason']}"),
            ("Storage root", str(s.storage_root.resolve())),
            ("Job workers", str(platform.jobs.n_workers))]  # type: ignore[attr-defined]
    for label, value in rows:
        print(f"  {label:<14}{value}")
    print("  Seams         " + ", ".join(
        f"{c['seam']}={c['selected']}" + ("*" if c["selected"] != c["preferred"] else "")
        for c in Backends.report()))
    print("                (* = not the preferred backend; see the health page for the cost)")
    if platform.auth.default_admin_password_active():  # type: ignore[attr-defined]
        print("\n  !! The bootstrap admin still uses the default password 'maya-dev-admin'. "
              "Change it now.")
    print("=" * 80)


def _shutdown(*_: object) -> None:
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    logger.info("MAYA shutting down: draining job workers")
    if _platform is not None:
        _platform.shutdown()


def main(argv: list[str]) -> int:
    global _platform
    if any(a in ("-h", "--help") for a in argv[1:]):
        print(__doc__)
        print(BANNER.format(tagline=APP_TAGLINE, slogan=APP_SLOGAN, version=VERSION,
                            build=BUILD_DATE, python=sys.version.split()[0],
                            platform=sys.platform))
        return 0
    from maya.config import load_settings
    from maya.observability.logs import configure
    settings = load_settings(_config_path(argv))
    configure(settings.get("logging.level", "INFO") or "INFO",
              settings.get("logging.format", "text") or "text",
              settings.get("logging.file"))
    logger.info("MAYA %s starting at %s (pid %s)", VERSION, datetime.now().isoformat(),
                os.getpid())
    from maya.services.platform import Platform
    from maya.server import build_app
    _platform = Platform.build(settings)
    _print_banner(_platform)
    atexit.register(_shutdown)
    signal.signal(signal.SIGINT, lambda *a: (_shutdown(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *a: (_shutdown(), sys.exit(0)))
    app = build_app(_platform)
    import uvicorn
    host = settings.get("server.host", "127.0.0.1") or "127.0.0.1"
    port = settings.int("server.port", 8600)
    from maya.core.backends import Backends
    loop = "uvloop" if Backends.selected("event_loop") == "uvloop" else "asyncio"
    print(f"\n  Serving on http://{host}:{port}   (API docs: /api/v1/docs)\n")
    uvicorn.run(app, host=host, port=port, log_level="warning", loop=loop,
                proxy_headers=True, access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
