"""
Catalog facets (§16.2): type, namespace, owner, status, tag and freshness, not
namespace alone — over the server-side paging of ADR-016, with the totals of a
row-filtered list still counted in the database.

The last part is the one worth guarding: a facet that is not a column (a tag, a
feature's data freshness) narrows an identifier set rather than the query, and
the total over that set must still equal what a row-by-row walk would count.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest

from maya.core.errors import ValidationFailed
from tests.conftest import PX_DEF, price_csv


@pytest.fixture(scope="module")
def estate(world):
    """Two namespaces, two owners, three object types, tags, and data in some of them."""
    w = world
    w.p.access.create_namespace(w.admin, name="fc_open", default_visibility="namespace_read")
    w.p.access.create_namespace(w.admin, name="fc_shut", default_visibility="private")
    for ns in ("fc_open", "fc_shut"):
        for i in range(4):
            w.p.features.create(
                w.dana,
                namespace=ns,
                name=f"fc_{ns[3:]}_{i}",
                definition=copy.deepcopy(PX_DEF),
                description="a closing price" if i % 2 else "a volume",
                tags=["eod", "prices"] if i % 2 else ["intraday"],
            )
    # one owned by somebody else, one with data, one approved
    w.p.features.create(
        w.admin,
        namespace="fc_open",
        name="fc_admins",
        definition=copy.deepcopy(PX_DEF),
        tags=["eod"],
    )
    w.p.features.ingest(w.dana, "fc_open/fc_open_1", price_csv(), fmt="csv")
    w.p.features.transition(w.dana, "fc_open/fc_open_1", 1, "submit")
    w.p.features.transition(w.mick, "fc_open/fc_open_1", 1, "approve")
    w.p.featuresets.create(
        w.dana,
        namespace="fc_open",
        name="fc_panel",
        definition={
            "index": ["date", "symbol"],
            "index_types": {"date": "date", "symbol": "string"},
            "members": [
                {"attr": "close", "ref": "maya://feature/fc_open/fc_open_1", "source_attr": "close"}
            ],
            "alignment": {"mode": "inner"},
        },
        tags=["eod"],
    )
    return w


def _names(rows):
    return {r["name"] for r in rows}


def test_the_type_facet_chooses_which_kind_of_object_is_listed(estate):
    w = estate
    features = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open")
    assert "fc_open_1" in _names(features)
    assert all(r["type"] == "feature" for r in features)
    sets = w.p.catalog.browse(w.dana, type="featureset", namespace="fc_open")
    assert _names(sets) == {"fc_panel"}
    assert sets[0]["url"] == "/catalog/featuresets/fc_open/fc_panel"
    assert w.p.catalog.browse(w.dana, type="model", namespace="fc_open") == []
    with pytest.raises(ValidationFailed):
        w.p.catalog.browse(w.dana, type="warrant")


def test_the_owner_facet_narrows_to_one_owner(estate):
    w = estate
    mine = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", owner="dana")
    assert "fc_admins" not in _names(mine)
    theirs = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", owner="admin")
    assert _names(theirs) == {"fc_admins"}
    assert theirs[0]["owner"] == "admin"


def test_the_status_facet_narrows_to_a_lifecycle_state(estate):
    w = estate
    approved = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", status="approved")
    assert _names(approved) == {"fc_open_1"}
    drafts = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", status="draft")
    assert "fc_open_1" not in _names(drafts)
    assert drafts


def test_the_tag_facet_narrows_to_a_tag(estate):
    w = estate
    eod = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", tag="eod")
    assert _names(eod) == {"fc_open_1", "fc_open_3", "fc_admins"}
    intraday = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", tag="intraday")
    assert _names(intraday) == {"fc_open_0", "fc_open_2"}
    assert w.p.catalog.browse(w.dana, type="feature", tag="no_such_tag") == []


def test_the_freshness_facet_keeps_features_whose_data_is_recent(estate):
    w = estate
    fresh = w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", freshness="24h")
    assert _names(fresh) == {"fc_open_1"}, "only the ingested feature has data at all"
    with pytest.raises(ValidationFailed):
        w.p.catalog.browse(w.dana, type="feature", freshness="sometime")


def test_freshness_for_a_feature_set_is_when_it_last_changed(estate):
    w = estate
    recent = w.p.catalog.browse(w.dana, type="featureset", namespace="fc_open", freshness="24h")
    assert "fc_panel" in _names(recent)
    facets = w.p.catalog.facets(w.dana, type="featureset")
    assert facets["freshness_means"] == "the object changed within the window"
    assert w.p.catalog.facets(w.dana, type="feature")["freshness_means"] == (
        "data known within the window"
    )


def test_facets_offer_only_values_that_exist(estate):
    w = estate
    facets = w.p.catalog.facets(w.dana, type="feature")
    assert facets["types"] == ["feature", "featureset", "model"]
    assert "dana" in facets["owners"] and "admin" in facets["owners"]
    assert {"eod", "intraday", "prices"} <= set(facets["tags"])
    assert "approved" in facets["statuses"] and "draft" in facets["statuses"]
    assert "fc_open" in facets["namespaces"]
    assert facets["freshness"] == ["24h", "7d", "30d", "90d"]


def test_facets_combine(estate):
    w = estate
    rows = w.p.catalog.browse(
        w.dana, type="feature", namespace="fc_open", owner="dana", tag="eod", status="approved"
    )
    assert _names(rows) == {"fc_open_1"}
    assert (
        w.p.catalog.browse(w.dana, type="feature", tag="eod", owner="admin", status="approved")
        == []
    )


def test_a_facet_never_shows_what_the_reader_may_not_read(estate):
    w = estate
    theirs = w.p.catalog.browse(w.mona, type="feature")
    assert not any(r["namespace"] == "fc_shut" for r in theirs), theirs
    owner = w.p.catalog.browse(w.dana, type="feature", namespace="fc_shut")
    assert len(owner) == 4


@pytest.mark.parametrize("who", ["dana", "mick", "mona", "admin"])
@pytest.mark.parametrize(
    "facet", [{}, {"tag": "eod"}, {"freshness": "90d"}, {"owner": "dana"}, {"status": "draft"}]
)
def test_the_total_equals_a_row_by_row_count_under_every_facet(estate, who, facet):
    """The regression guard: totals are counted by the database, and adding a facet that
    is not a column must not change the answer a row-by-row walk would give."""
    w = estate
    p = w.principal(who)
    with w.p.uow() as uow:
        listing = w.p.catalog.browse_listing(uow, p, type="feature", **facet)
        rows = uow.repo("features").slim(
            ["id", "namespace_id", "owner_id"], search=listing.search, **listing.filters
        )
        scanned = sum(1 for r in rows if listing.keep(uow, r))
    page = w.p.catalog.browse_page(p, type="feature", page_size=3, total=True, **facet)
    assert page["total"] == scanned
    assert len(page["items"]) <= 3


def test_paging_walks_the_whole_faceted_list_once(estate):
    w = estate
    seen, cursor = [], None
    while True:
        page = w.p.catalog.browse_page(
            w.dana, type="feature", tag="eod", page_size=2, cursor=cursor, sort="name"
        )
        seen += [r["name"] for r in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == sorted(seen)
    assert len(seen) == len(set(seen))
    assert set(seen) == _names(w.p.catalog.browse(w.dana, type="feature", tag="eod"))


def test_a_cursor_does_not_survive_a_change_of_facet(estate):
    from maya.core.errors import InvalidCursor

    w = estate
    page = w.p.catalog.browse_page(w.dana, type="feature", tag="eod", page_size=1)
    assert page["next_cursor"]
    with pytest.raises(InvalidCursor):
        w.p.catalog.browse_page(
            w.dana, type="feature", tag="intraday", page_size=1, cursor=page["next_cursor"]
        )


def test_an_old_ingest_is_not_fresh(estate):
    w = estate
    w.p.features.create(
        w.dana, namespace="fc_open", name="fc_stale", definition=copy.deepcopy(PX_DEF)
    )
    w.p.features.ingest(
        w.dana,
        "fc_open/fc_stale",
        price_csv(),
        fmt="csv",
        knowledge_time=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc),
    )
    assert "fc_stale" not in _names(
        w.p.catalog.browse(w.dana, type="feature", namespace="fc_open", freshness="90d")
    )
    assert "fc_stale" in _names(w.p.catalog.browse(w.dana, type="feature", namespace="fc_open"))
