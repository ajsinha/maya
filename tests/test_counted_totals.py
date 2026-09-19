"""
A list's total, counted by the database in (namespace, owned) groups, equals the
row-by-row count of what the reader may see — across private and shared
namespaces, owners, and objects with grants of their own (allow and deny), for
several readers, with and without a search.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import pytest

from tests.conftest import PX_DEF


@pytest.fixture(scope="module")
def mixed(world):
    w = world
    w.p.access.create_namespace(w.admin, name="cnt_open", default_visibility="namespace_read")
    w.p.access.create_namespace(w.admin, name="cnt_shut", default_visibility="private")
    for ns in ("cnt_open", "cnt_shut"):
        for i in range(6):
            w.p.features.create(w.dana, namespace=ns, name=f"cf{i}", definition=PX_DEF,
                                description="even" if i % 2 == 0 else "odd")
    with w.p.uow() as uow:
        mick = uow.repo("users").find_one(username="mick")
        rows = {f"{r['namespace_id']}:{r['name']}": r for r in uow.repo("features").list()}
        ns = {n["name"]: n["id"] for n in uow.repo("namespaces").list()}
    shut = [rows[f"{ns['cnt_shut']}:cf{i}"] for i in range(6)]
    opened = [rows[f"{ns['cnt_open']}:cf{i}"] for i in range(6)]
    # object grants: an allow into the private namespace, a deny in the shared one
    w.p.access.grant(w.admin, kind="feature", obj=shut[0], principal_type="user",
                     principal_id=mick["id"], level="read")
    w.p.access.grant(w.admin, kind="feature", obj=opened[1], principal_type="user",
                     principal_id=mick["id"], level="read", deny=True)
    w.p.access.grant(w.admin, kind="feature", obj=shut[2], principal_type="role",
                     principal_id="model_developer", level="read")
    return w


@pytest.mark.parametrize("who", ["mick", "dana", "devi", "mona", "admin"])
@pytest.mark.parametrize("q", ["", "odd"])
def test_the_grouped_count_equals_the_row_by_row_count(mixed, who, q):
    w = mixed
    p = w.principal(who)
    with w.p.uow() as uow:
        listing = w.p.features.listing(uow, p, q=q or None)
        rows = uow.repo("features").slim(["id", "namespace_id", "owner_id"],
                                         search=listing.search, **listing.filters)
        scanned = sum(1 for r in rows if listing.keep(uow, r))
        counted = listing.keep.count(uow, "features", listing.search, listing.filters)
    assert counted == scanned
    page = w.p.features.page(p, q=q or None, page_size=5, total=True)
    assert page["total"] == scanned
