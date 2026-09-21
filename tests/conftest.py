"""
Shared fixtures: a real platform (SQLite by default, PostgreSQL when
``MAYA_TEST_PG_URL`` is set) over a throwaway storage root, with one user per
role, and helpers to build principals and seed data.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASSWORD = "Test-password-1"
ROLES = {
    "dana": ["feature_designer"],
    "mick": ["feature_manager"],
    "mona": ["model_designer"],
    "devi": ["model_developer"],
    "mgr": ["model_manager"],
    "owen": ["model_owner"],
    "tess": ["techops"],
    "admin2": ["admin"],
}


def fresh_pg_database(url: str) -> str:
    """A new, empty database on the server behind ``url``, one per platform.

    Tests build several platforms at once (a module fixture plus one inside a test);
    on SQLite each has its own file, so on PostgreSQL each gets its own database —
    re-initialising one shared database would wipe a platform still in use."""
    import uuid

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    base = make_url(url)
    name = f"{base.database}_{uuid.uuid4().hex[:10]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    atexit.register(_drop_pg_database, base.set(database="postgres"), name)
    return base.set(database=name).render_as_string(hide_password=False)


def _drop_pg_database(server: Any, name: str) -> None:
    """The run's own database, dropped when the run ends (the server is left as found)."""
    from sqlalchemy import create_engine, text

    try:
        admin = create_engine(server, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
    except Exception:  # noqa: BLE001 - best effort at exit; never fail a run over cleanup
        pass


def build_platform(
    extra_argv: list[str] | None = None, lake: str = "auto", start_workers: bool | str = False
) -> Any:
    # MAYA_TEST_EXTRA_ARGV: settings for every platform in the run, e.g. the fallback
    # matrix's seam pins (tools/ci/gates.py --fallback); they come last, so they win
    sys.argv = (
        ["pytest", f"--lake.backend={lake}"]
        + (extra_argv or [])
        + os.environ.get("MAYA_TEST_EXTRA_ARGV", "").split()
    )
    home = tempfile.mkdtemp(prefix="maya-test-")
    atexit.register(shutil.rmtree, home, True)  # gone when the run ends
    os.environ["MAYA_HOME"] = home
    # The lake goes inside this platform's own home. The shipped configuration points it at
    # one lake for the whole project, which is what a demonstration wants and what a test
    # suite must not have: these run in parallel, and two workers sharing a lake are each
    # other's missing pins.
    sys.argv.append(f"--lake.root={home}/lake")
    pg = os.environ.get("MAYA_TEST_PG_URL")
    if pg:
        sys.argv.append("--db.dialect=postgresql")
    from maya.config import load_settings
    from maya.services.platform import Platform

    settings = load_settings(ROOT / "config" / "application.yaml", fresh=True)
    if pg:
        # The full suite on PostgreSQL (SC-10): each platform gets a freshly created
        # schema from schema/postgresql.sql, exactly as `init-db --force` would.
        own = fresh_pg_database(pg)
        settings.database_url = lambda: own  # type: ignore[method-assign]
        from maya.persistence.engine import database_from_settings

        db = database_from_settings(settings)
        db.init_schema(force=True)
        db.dispose()
    return Platform.build(settings, start_workers=start_workers)


class World:
    """A platform plus principals by username."""

    def __init__(self, platform: Any) -> None:
        self.p = platform
        self.admin = self.principal("admin")
        for name, roles in ROLES.items():
            platform.access.create_user(self.admin, username=name, password=PASSWORD, roles=roles)

    def principal(self, username: str) -> Any:
        with self.p.uow() as uow:
            user = uow.repo("users").find_one(username=username)
            return self.p.auth.build_principal(uow, user["id"])

    def __getattr__(self, name: str) -> Any:
        if name in ROLES:
            return self.principal(name)
        raise AttributeError(name)

    def drain(self) -> None:
        self.p.jobs.drain()


@pytest.fixture(scope="module")
def world() -> Any:
    platform = build_platform()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq", preset="standard")
    yield w
    platform.shutdown()


PX_DEF = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "close", "type": "float64"}],
    "source": {"type": "csv"},
    "resolution": {"grid": "as_is", "rules": {"close": "forward_fill(limit=3)"}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "close"}],
}


def price_csv(
    days: int = 20, symbols: tuple[str, ...] = ("AAA", "BBB"), bump: float = 0.0, start_day: int = 1
) -> bytes:
    import datetime as dt

    lines = ["date,symbol,close"]
    d0 = dt.date(2026, 1, 1)
    for i in range(start_day - 1, start_day - 1 + days):
        day = d0 + dt.timedelta(days=i)
        for j, s in enumerate(symbols):
            lines.append(f"{day.isoformat()},{s},{100 + j * 10 + i * 0.5 + bump:.4f}")
    return ("\n".join(lines) + "\n").encode()


def approved_feature(
    w: World,
    name: str,
    csv: bytes | None = None,
    definition: dict[str, Any] | None = None,
    ns: str = "eq",
) -> str:
    """Create, ingest, submit (designer) and approve (manager) a feature. Returns its ref."""
    w.p.features.create(w.dana, namespace=ns, name=name, definition=definition or PX_DEF)
    ref = f"{ns}/{name}"
    if csv is not None:
        w.p.features.ingest(w.dana, ref, csv, fmt="csv")
    w.p.features.transition(w.dana, ref, 1, "submit")
    w.p.features.transition(w.mick, ref, 1, "approve")
    return ref
