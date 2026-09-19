"""
The sql source driver (§5.2, §21.1): administrator-managed connections that
never hold a password, one reviewed read-only SELECT with bound parameters, and
pulls that snapshot into the bitemporal ingest log — so a restatement upstream
is a new knowledge-time row here, and a past view stays reproducible.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from maya.persistence import external


@pytest.fixture(scope="module")
def warehouse(world, tmp_path_factory):
    path = tmp_path_factory.mktemp("wh") / "warehouse.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE px (d TEXT, sym TEXT, close REAL)")
    con.executemany(
        "INSERT INTO px VALUES (?, ?, ?)",
        [(f"2026-01-0{i}", s, 100.0 + i) for i in range(1, 6) for s in ("AAA", "BBB")],
    )
    con.commit()
    con.close()
    world.p.sources.create(
        world.admin, name="warehouse", url=f"sqlite:///{path}", description="test warehouse"
    )
    return world, path


SQL_DEF = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "close", "type": "float64"}],
    "source": {
        "type": "sql",
        "connection": "warehouse",
        "query": "SELECT d AS date, sym AS symbol, close FROM px WHERE sym = :sym AND d >= :start",
        "params": {
            "sym": {"type": "string", "value": "AAA"},
            "start": {"type": "date", "value": "2026-01-02"},
        },
    },
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [],
}


def test_pull_snapshots_the_query_and_restatements_append(warehouse):
    w, path = warehouse
    w.p.features.create(w.dana, namespace="eq", name="from_sql", definition=SQL_DEF)
    first = w.p.sources.pull(w.dana, "eq/from_sql")
    assert first["rows"] == 4 and first["source_type"] == "sql"
    w.p.features.transition(w.dana, "eq/from_sql", 1, "submit")
    w.p.features.transition(w.mick, "eq/from_sql", 1, "approve")
    before = dt.datetime.now(dt.timezone.utc)
    con = sqlite3.connect(path)
    con.execute("UPDATE px SET close = close + 50 WHERE sym = 'AAA'")
    con.commit()
    con.close()
    second = w.p.sources.pull(
        w.dana, "eq/from_sql", knowledge_time=before + dt.timedelta(seconds=5)
    )
    assert second["restatement"] is True
    old = w.p.features.preview(w.dana, "maya://feature/eq/from_sql@v1", as_of_known=before)
    new = w.p.features.preview(w.dana, "maya://feature/eq/from_sql@v1")
    assert old["rows"][0]["close"] == pytest.approx(102.0)
    assert new["rows"][0]["close"] == pytest.approx(152.0)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM px",
        "SELECT 1; DROP TABLE px",
        "WITH x AS (SELECT 1) INSERT INTO px VALUES ('a','b',1)",
        "UPDATE px SET close = 0",
        "PRAGMA writable_schema = 1",
    ],
)
def test_anything_but_one_select_is_refused_before_connecting(query):
    with pytest.raises(ValidationFailed):
        external.check_query(query)


def test_semicolons_and_keywords_inside_strings_are_harmless():
    assert external.check_query("SELECT 'a;drop' AS note FROM px")


def test_the_connection_itself_is_read_only(warehouse):
    w, path = warehouse
    engine = external._read_only_engine(f"sqlite:///{path}", None)
    from sqlalchemy import text

    with pytest.raises(Exception, match="readonly"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM px"))
    engine.dispose()


def test_passwords_never_enter_maya(warehouse):
    w, _ = warehouse
    with pytest.raises(ValidationFailed, match="environment variable"):
        w.p.sources.create(w.admin, name="leaky", url="postgresql://u:hunter2@db/x")
    with pytest.raises(PermissionDenied):
        w.p.sources.create(w.dana, name="mine", url="sqlite:////tmp/x.db")
    assert "hunter2" not in str(w.p.sources.list())


def test_an_invalid_sql_definition_is_refused_at_submit(warehouse):
    w, _ = warehouse
    bad = dict(SQL_DEF, source={**SQL_DEF["source"], "query": "DELETE FROM px"})
    w.p.features.create(w.dana, namespace="eq", name="bad_sql", definition=bad)
    with pytest.raises(ValidationFailed, match="SELECT"):
        w.p.features.transition(w.dana, "eq/bad_sql", 1, "submit")


def test_sources_admin_page_renders(warehouse):
    import re
    from starlette.testclient import TestClient
    from maya.server import build_app

    w, _ = warehouse
    web = TestClient(build_app(w.p))
    page = web.get("/login")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    web.post("/login", data={"username": "admin", "password": "maya-dev-admin", "csrf_token": csrf})
    listing = web.get("/admin/sources", follow_redirects=False)
    if listing.status_code == 303:  # forced password change for the bootstrap admin
        page = web.get("/account/password")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        web.post(
            "/account/password",
            data={
                "old_password": "maya-dev-admin",
                "new_password": "Admin-changed-9",
                "confirm_password": "Admin-changed-9",
                "csrf_token": csrf,
            },
        )
        listing = web.get("/admin/sources")
    assert listing.status_code == 200 and "warehouse" in listing.text
    assert "never stores a database password" in listing.text
