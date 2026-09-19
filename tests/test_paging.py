"""
Cursor pagination (§18.1): opt-in envelopes on the list endpoints, keyset order
that survives inserts, signed cursors bound to their query, the authorization
filter applied before a page is cut, and the SDK iterators that follow cursors.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from maya.core.errors import InvalidCursor, ValidationFailed
from maya.sdk import AsyncClient, Client
from tests.conftest import PX_DEF


@pytest.fixture(scope="module")
def paged(world):
    from maya.api.app import create_api

    w = world
    w.p.access.create_namespace(w.admin, name="pg", preset="standard")
    for i in range(23):
        w.p.features.create(
            w.dana,
            namespace="pg",
            name=f"f{i:02d}",
            definition=PX_DEF,
            description="even" if i % 2 == 0 else "odd",
        )
    with w.p.uow() as uow:
        w.p.access.ensure_scratch(uow, w.admin)
    for i in range(7):
        w.p.features.create(
            w.admin, namespace="scratch.admin", name=f"hidden{i}", definition=PX_DEF
        )
    app = create_api(w.p)
    admin = Client(app=app, token=Client(app=app).auth.login("admin", "maya-dev-admin")["token"])
    return w, app, admin


def _walk(fetch, **kw):
    """Follow cursors to the end; returns the pages."""
    pages, cursor = [], None
    while True:
        page = fetch(cursor=cursor, **kw)
        pages.append(page)
        cursor = page["next_cursor"]
        if not cursor:
            return pages


# -- the envelope and the walk -----------------------------------------------------------------
def test_without_paging_params_the_response_shape_is_unchanged(paged):
    _, _, admin = paged
    rows = admin.features.list(namespace="pg")
    assert isinstance(rows, list) and len(rows) == 23


def test_pages_follow_cursors_to_exactly_the_whole_list(paged):
    _, _, admin = paged
    pages = _walk(lambda cursor: admin.features.page(namespace="pg", page_size=10, cursor=cursor))
    assert [len(p["items"]) for p in pages] == [10, 10, 3]
    assert pages[-1]["next_cursor"] is None and pages[0]["sort"] == "name"
    names = [f["name"] for p in pages for f in p["items"]]
    assert names == [f["name"] for f in admin.features.list(namespace="pg")]
    assert names == sorted(names) and len(set(names)) == 23
    assert {"latest_state", "pins", "ref"} <= set(pages[0]["items"][0])  # enriched


def test_an_exact_page_boundary_has_no_empty_trailing_page(paged):
    _, _, admin = paged
    first = admin.features.page(namespace="pg", page_size=23)
    assert len(first["items"]) == 23 and first["next_cursor"] is None


@pytest.mark.parametrize(
    "sort, key, reverse",
    [
        ("-name", "name", True),
        ("created", "created_at", False),
        ("-created", "created_at", True),
        ("updated", "updated_at", False),
    ],
)
def test_every_offered_sort_walks_in_order_with_an_id_tiebreak(paged, sort, key, reverse):
    _, _, admin = paged
    pages = _walk(
        lambda cursor: admin.features.page(namespace="pg", page_size=4, sort=sort, cursor=cursor)
    )
    rows = [f for p in pages for f in p["items"]]
    assert len(rows) == 23 and len({r["id"] for r in rows}) == 23
    keys = [(r[key], r["id"]) for r in rows]
    assert keys == sorted(keys, reverse=reverse)


def test_search_and_total(paged):
    _, _, admin = paged
    page = admin.features.page(namespace="pg", q="odd", page_size=5, total=True)
    assert page["total"] == 11 and len(page["items"]) == 5
    assert all(f["description"] == "odd" for f in page["items"])
    assert "total" not in admin.features.page(namespace="pg", page_size=5)


def test_the_page_is_cut_after_the_authorization_filter(paged):
    """dana cannot read the admin's private scratch: pages hold only what dana may read."""
    w, app, _ = paged
    dana = Client(app=app, token=Client(app=app).auth.login("dana", "Test-password-1")["token"])
    visible = [f["ref"] for f in dana.features.list()]
    assert visible and not any("scratch.admin" in r for r in visible)
    walked = [
        f["ref"]
        for p in _walk(lambda cursor: dana.features.page(page_size=3, cursor=cursor))
        for f in p["items"]
    ]
    assert walked == visible
    assert dana.features.page(page_size=3, total=True)["total"] == len(visible)


def test_state_keeps_objects_whose_latest_version_is_in_it(paged):
    """The workbench's filter: the latest version's state, one or several, paged or not;
    a cursor issued for one state is refused for another."""
    w, _, admin = paged
    w.p.features.transition(w.dana, "pg/f00", 1, "submit")
    try:
        drafts = {f["name"] for f in admin.features.list(namespace="pg", state="draft")}
        assert "f00" not in drafts and len(drafts) == 22
        both = admin.features.page(namespace="pg", state="draft,in_review", page_size=5, total=True)
        assert both["total"] == 23 and len(both["items"]) == 5
        assert [f["name"] for f in admin.features.list(namespace="pg", state="in_review")] == [
            "f00"
        ]
        first = admin.features.page(namespace="pg", state="draft", page_size=5)
        with pytest.raises(InvalidCursor):
            admin.features.page(
                namespace="pg", state="in_review", page_size=5, cursor=first["next_cursor"]
            )
        assert admin.featuresets.list(state="approved") == []
    finally:
        w.p.features.transition(w.dana, "pg/f00", 1, "withdraw")


def test_inserts_between_pages_neither_repeat_nor_skip(paged):
    w, _, admin = paged
    first = admin.features.page(namespace="pg", page_size=10)
    w.p.features.create(w.dana, namespace="pg", name="a_before", definition=PX_DEF)
    w.p.features.create(w.dana, namespace="pg", name="z_after", definition=PX_DEF)
    rest = _walk(
        lambda cursor: admin.features.page(
            namespace="pg", page_size=10, cursor=cursor or first["next_cursor"]
        )
    )
    later = [f["name"] for p in rest for f in p["items"]]
    seen = [f["name"] for f in first["items"]]
    assert not set(seen) & set(later)
    assert "z_after" in later and "a_before" not in later  # it sorts before the cursor
    assert later == sorted(later) and later[0] > seen[-1]


# -- refusals ----------------------------------------------------------------------------------
@pytest.mark.parametrize("size", [0, -1, 1001])
def test_page_size_is_bounded(paged, size):
    _, _, admin = paged
    with pytest.raises(ValidationFailed, match="page_size must be between 1 and 1000"):
        admin.features.page(namespace="pg", page_size=size)


def test_an_unknown_sort_is_refused_naming_the_choices(paged):
    _, _, admin = paged
    with pytest.raises(ValidationFailed, match="sort must be one of name, -name"):
        admin.features.page(namespace="pg", sort="pins")


def test_a_tampered_or_foreign_cursor_is_a_400(paged):
    _, app, admin = paged
    cursor = admin.features.page(namespace="pg", page_size=5)["next_cursor"]
    payload, sig = cursor.split(".")
    flipped = payload[:-2] + ("A" if payload[-2] != "A" else "B") + payload[-1]
    for bad, why in (
        (f"{flipped}.{sig}", "not one MAYA issued"),
        (f"{payload}.{sig[:-1]}", "not one MAYA issued"),
        ("garbage", "not one MAYA issued"),
    ):
        with pytest.raises(InvalidCursor, match=why):
            admin.features.page(namespace="pg", page_size=5, cursor=bad)
    with pytest.raises(InvalidCursor, match="different query"):
        admin.features.page(namespace="pg", page_size=5, cursor=cursor, sort="-name")
    with pytest.raises(InvalidCursor, match="different query"):
        admin.features.page(namespace="pg", q="odd", page_size=5, cursor=cursor)
    with pytest.raises(InvalidCursor, match="different query"):
        admin.models.page(page_size=5, cursor=cursor)
    from starlette.testclient import TestClient

    token = Client(app=app).auth.login("admin", "maya-dev-admin")["token"]
    r = TestClient(app).get(
        "/api/v1/features", params={"cursor": "x.y"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 400 and r.json()["type"] == "invalid_cursor"


# -- the other lists -----------------------------------------------------------------------------
def test_audit_pages_newest_first_and_counts_exactly(paged):
    _, _, admin = paged
    page = admin.admin.audit_page(page_size=7, total=True)
    seqs = [e["seq"] for e in page["items"]]
    assert seqs == sorted(seqs, reverse=True) and len(seqs) == 7
    everything = list(admin.admin.iter_audit(page_size=50))
    assert len(everything) == page["total"] >= 7
    oldest = admin.admin.audit_page(page_size=3, sort="seq")["items"]
    assert [e["seq"] for e in oldest] == sorted(e["seq"] for e in everything)[:3]
    assert all(
        "feature" in e["action"]
        for e in admin.admin.audit_page(action="feature", page_size=20)["items"]
    )


def test_models_warrants_jobs_events_inbox_and_grants_page(paged):
    w, _, admin = paged
    admin.models.create("pg", "m1", formula="y = a*x", roles={"a": "parameter"})
    assert [m["name"] for m in admin.models.iter(namespace="pg", page_size=1)] == ["m1"]
    assert admin.featuresets.page(namespace="pg")["items"] == []
    for resource in (admin.training, admin.execution):
        page = resource.page(page_size=5)
        assert set(page) >= {"items", "next_cursor"} and page["sort"] == "-created"
    assert isinstance(admin.jobs.page(all=True, page_size=5)["items"], list)
    events = admin.events.page(page_size=5, sort="-seq")
    assert [e["seq"] for e in events["items"]] == sorted(
        (e["seq"] for e in events["items"]), reverse=True
    )
    assert admin.access.inbox_page(page_size=5)["items"] == admin.access.inbox()[:5]
    obj = w.p.access.resolve_object("feature", "pg/f00")
    w.p.access.grant(
        w.admin, kind="feature", obj=obj, principal_type="user", principal_id="mick", level="read"
    )
    grants = admin.access.grants_page("feature", "pg/f00", total=True)
    assert grants["total"] == len(admin.access.grants("feature", "pg/f00")) >= 1


def test_the_sdk_iterators_follow_cursors_sync_and_async(paged):
    _, app, admin = paged
    names = [f["name"] for f in admin.features.iter(namespace="pg", page_size=4)]
    assert names == [f["name"] for f in admin.features.list(namespace="pg")]

    async def collect():
        token = Client(app=app).auth.login("admin", "maya-dev-admin")["token"]
        async with AsyncClient(app=app, token=token) as client:
            return [f["name"] async for f in client.features.iter(namespace="pg", page_size=4)]

    assert asyncio.run(collect()) == names


# -- the web tables in server mode ----------------------------------------------------------------
@pytest.fixture(scope="module")
def web(paged):
    from starlette.testclient import TestClient

    from maya.server import build_app

    w, _, _ = paged
    with w.p.uow() as uow:  # not under test: skip the first-login change
        uow.repo("users").update(
            uow.repo("users").find_one(username="admin")["id"], {"must_change_password": False}
        )
    browser = TestClient(build_app(w.p))
    token = re.search(r'name="csrf_token" value="([^"]+)"', browser.get("/login").text).group(1)
    browser.post(
        "/login", data={"username": "admin", "password": "maya-dev-admin", "csrf_token": token}
    )
    return w, browser


def _names(rows):
    return [re.search(r'">([^<]+)</a>', r).group(1) for r in rows]


def test_big_pages_render_page_one_in_server_mode(web):
    _, browser = web
    html = browser.get("/catalog/features").text
    wrap = re.search(r'<div class="mt-wrap[^>]*>', html, re.S).group(0)
    assert 'data-source="/ui/table/features"' in wrap and 'data-sort="name"' in wrap
    assert re.search(r'data-next-cursor="[^"]+\.[^"]+"', wrap)  # more than one page
    assert re.search(r'data-total="\d+"', wrap)
    body = html[html.index("<tbody>") : html.index("</tbody>")]
    assert body.count("<tr>") == 25
    assert 'data-sort-key="name"' in html and 'data-sort-key="updated"' in html
    assert '<th scope="col" data-label="Owner">' in html  # not server-sortable
    assert '<option value="0">All</option>' not in html
    for path, source, sort in (
        ("/catalog/featuresets", "featuresets", "name"),
        ("/models", "models", "name"),
        ("/admin/audit", "audit", "-seq"),
        ("/admin/events", "events", "-seq"),
        ("/admin/jobs", "jobs", "-created"),
    ):
        page = browser.get(path)
        assert page.status_code == 200, path
        assert (
            f'data-source="/ui/table/{source}' in page.text and f'data-sort="{sort}"' in page.text
        )


def test_the_table_route_serves_later_pages_as_rendered_rows(web):
    _, browser = web
    html = browser.get("/catalog/features").text
    cursor = re.search(r'data-next-cursor="([^"]+)"', html).group(1)
    first = browser.get("/ui/table/features", params={"page_size": 25, "total": "1"}).json()
    second = browser.get("/ui/table/features", params={"page_size": 25, "cursor": cursor}).json()
    assert len(first["rows"]) == 25 and first["total"] >= 30 and second["total"] is None
    assert all(r.lstrip().startswith("<td>") for r in second["rows"])
    assert not set(_names(first["rows"])) & set(_names(second["rows"]))
    everything = _names(browser.get("/ui/table/features", params={"page_size": 250}).json()["rows"])
    assert everything[:25] == _names(first["rows"])
    assert everything[25 : 25 + len(second["rows"])] == _names(second["rows"])
    hits = browser.get(
        "/ui/table/features", params={"page_size": 25, "namespace": "pg", "q": "odd", "total": "1"}
    ).json()
    assert hits["total"] == 11 and len(hits["rows"]) == 11
    back = _names(
        browser.get("/ui/table/features", params={"page_size": 25, "sort": "-name"}).json()["rows"]
    )
    assert back == sorted(back, reverse=True)
    audit = browser.get("/ui/table/audit", params={"page_size": 50, "action": "feature"}).json()
    assert audit["rows"] and all("feature" in r for r in audit["rows"])
    assert "rows" in browser.get("/ui/table/jobs", params={"page_size": 25}).json()


def test_the_table_route_refuses_what_it_should(web):
    from starlette.testclient import TestClient

    from maya.server import build_app

    w, browser = web
    bad = browser.get("/ui/table/features", params={"page_size": 30})
    assert bad.status_code == 422 and "page_size is one of" in bad.json()["error"]
    assert browser.get("/ui/table/nope").status_code == 422
    tampered = browser.get("/ui/table/features", params={"page_size": 25, "cursor": "a.b"})
    assert tampered.status_code == 400 and tampered.json()["type"] == "invalid_cursor"
    assert TestClient(build_app(w.p)).get("/ui/table/features").status_code == 401
