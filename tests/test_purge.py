"""
Purging a namespace: the one deletion MAYA allows, and only where nobody relies on it.

A case study that fails half way leaves a half-built namespace in the shared demonstration
estate. The purge removes it -- every row, every lake file -- in a development environment,
by an administrator who types the name again, and records the purge in the audit log.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import PermissionDenied, ValidationFailed
from tests.conftest import World, build_platform

DEFN = {
    "index": ["date"],
    "index_types": {"date": "date"},
    "schema": [{"name": "x", "type": "float64"}],
    "source": {"type": "csv"},
}


def _counts(p):
    from sqlalchemy import func, select

    from maya.persistence.models import Base

    with p.db.engine.connect() as c:
        return {
            n: c.execute(select(func.count()).select_from(t)).scalar()
            for n, t in Base.metadata.tables.items()
        }


def _fill(p, w, ns):
    p.access.create_namespace(w.admin, name=ns, preset="standard")
    p.features.create(w.dana, namespace=ns, name="f1", definition=DEFN)
    p.features.ingest(w.dana, f"{ns}/f1", b"date,x\n2026-01-01,1\n2026-01-02,2\n", fmt="csv")
    p.features.transition(w.dana, f"{ns}/f1", 1, "submit")
    p.features.transition(w.mick, f"{ns}/f1", 1, "approve")
    p.features.pin(w.mick, f"{ns}/f1", version_no=1, pin_name="p", as_of=dt.date(2026, 1, 31))
    p.jobs.drain()
    p.models.create(w.mona, namespace=ns, name="m1", formula="y = a*x", roles={"a": "parameter"})


@pytest.fixture(scope="module")
def estate():
    p = build_platform()
    yield p, World(p)
    p.shutdown()


def test_a_purge_removes_every_row_and_lake_file_and_is_audited(estate):
    p, w = estate
    before = _counts(p)
    _fill(p, w, "scratchpad_ns")
    out = p.access.purge_namespace(w.admin, "scratchpad_ns", confirm="scratchpad_ns")
    after = _counts(p)
    grown = {t for t in after if after[t] > before[t]}
    # only history is left: the audit log, the event stream, the job records, and the
    # content-addressed blob of the upload, which another namespace may share
    assert grown <= {"audit_events", "events", "jobs", "blobs"}, grown
    assert out["rows_removed"] > 0 and out["lake_folders_removed"] >= 1
    assert not list(p.lake.root.rglob("scratchpad_ns"))
    with p.uow() as uow:
        audit = uow.repo("audit_events").find_one(action="namespace.purged")
    assert audit and audit["detail"]["rows"]["features"] == 1


def test_a_purge_is_refused_without_the_name_or_by_a_non_administrator(estate):
    p, w = estate
    _fill(p, w, "kept_ns")
    with pytest.raises(ValidationFailed, match="Type the namespace"):
        p.access.purge_namespace(w.admin, "kept_ns", confirm="wrong")
    with pytest.raises(PermissionDenied, match="administrator"):
        p.access.purge_namespace(w.mick, "kept_ns", confirm="kept_ns")
    p.access.create_namespace(w.admin, name="kept_child", parent="kept_ns", preset="standard")
    with pytest.raises(ValidationFailed, match="child namespaces"):
        p.access.purge_namespace(w.admin, "kept_ns", confirm="kept_ns")
    assert any(n["name"] == "kept_ns" for n in p.access.list_namespaces())


def test_outside_a_development_environment_nothing_is_purged():
    p = build_platform(["--app.environment=uat", "--app.allow_default_admin_password=true"])
    try:
        w = World(p)
        p.access.create_namespace(w.admin, name="uat_ns", preset="standard")
        with pytest.raises(PermissionDenied, match="app.environment is dev"):
            p.access.purge_namespace(w.admin, "uat_ns", confirm="uat_ns")
    finally:
        p.shutdown()
