"""
Shared plumbing for the benchmarks: a platform on a scratch storage root, on
SQLite by default or PostgreSQL when ``MAYA_BENCH_PG_URL`` is set (a fresh
database, created and initialised from the schema file), and timing helpers.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import atexit
import os
import shutil
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def platform(
    home: str | None = None,
    extra: list[str] | None = None,
    db_url: str | None = None,
    init: bool = True,
) -> Any:
    """A platform over ``home`` (new if None); ``db_url`` reuses an existing PG database."""
    sys.argv = ["bench"] + (extra or [])
    if home is None:  # scratch storage: gone when the benchmark exits
        home = tempfile.mkdtemp(prefix="maya-bench-")
        atexit.register(shutil.rmtree, home, True)
    os.environ["MAYA_HOME"] = home
    pg = db_url or os.environ.get("MAYA_BENCH_PG_URL")
    if pg:
        sys.argv.append("--db.dialect=postgresql")
    from maya.config import load_settings
    from maya.services.platform import Platform

    settings = load_settings(ROOT / "config" / "application.yaml", fresh=True)
    if pg:
        url = pg if db_url else fresh_pg(pg)
        settings.database_url = lambda: url  # type: ignore[method-assign]
        if init and not db_url:
            from maya.persistence.engine import database_from_settings

            db = database_from_settings(settings)
            db.init_schema(force=True)
            db.dispose()
        os.environ["MAYA_BENCH_DB_URL"] = url
    return Platform.build(settings, start_workers=False)


def fresh_pg(url: str) -> str:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    base = make_url(url)
    name = f"{base.database}_bench_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    atexit.register(_drop, base.set(database="postgres"), name)
    return base.set(database=name).render_as_string(hide_password=False)


def _drop(server: Any, name: str) -> None:
    from sqlalchemy import create_engine, text

    try:
        admin = create_engine(server, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
    except Exception:  # noqa: BLE001 - best effort at exit
        pass


def principal(p: Any, username: str) -> Any:
    with p.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        return p.auth.build_principal(uow, user["id"])


def timed(fn: Callable[[], Any]) -> tuple[float, Any]:
    t0 = time.perf_counter()
    out = fn()
    return time.perf_counter() - t0, out


def pct(samples: list[float], q: float) -> float:
    if not samples:
        return float("nan")
    s = sorted(samples)
    k = max(0, min(len(s) - 1, int(round(q / 100 * (len(s) - 1)))))
    return s[k]


def summary(samples: list[float]) -> dict[str, float]:
    return {
        "n": len(samples),
        "p50": round(pct(samples, 50), 4),
        "p95": round(pct(samples, 95), 4),
        "max": round(max(samples), 4),
        "mean": round(statistics.fmean(samples), 4),
    }


def machine() -> dict[str, Any]:
    import platform as pyplatform

    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "os": pyplatform.platform(),
        "cpus": os.cpu_count(),
    }
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
        mem = Path("/proc/meminfo").read_text().split()[1]
        info["memory_gb"] = round(int(mem) / 1024 / 1024, 1)
    except OSError:
        pass
    return info
