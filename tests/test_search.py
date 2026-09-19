"""
Catalog search (§16.1): MAYA's own inverted index, kept current in the writing
transaction, ranked, prefix-matched, every term required — and never naming an
object the caller cannot read.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import copy

import pytest

from maya.core.errors import PermissionDenied
from maya.persistence.search_index import tokens
from tests.conftest import PASSWORD, PX_DEF


@pytest.mark.parametrize(
    "text, expected",
    [
        ("adj_close", ["adj_close", "adj", "close"]),
        ("adjClose", ["adjclose", "adj", "close"]),
        ("Equity Pricing, v2", ["equity", "pricing", "v2"]),
        ("credit.pd-12m", ["credit.pd-12m", "credit", "pd", "12m"]),
        ("", []),
        (None, []),
    ],
)
def test_tokenizer_splits_words_the_way_people_search(text, expected):
    assert tokens(text) == expected


@pytest.fixture(scope="module")
def cat(world):
    w = world
    w.p.access.create_namespace(w.admin, name="srch", preset="standard")
    w.p.features.create(
        w.dana,
        namespace="srch",
        name="adj_close",
        definition=copy.deepcopy(PX_DEF),
        description="Dividend-adjusted closing price",
        tags=["equity", "daily"],
    )
    w.p.features.create(
        w.dana,
        namespace="srch",
        name="volume",
        definition=copy.deepcopy(PX_DEF),
        description="Traded volume, not adjusted for close auctions",
    )
    w.p.features.create(
        w.dana,
        namespace="srch",
        name="pct_50_off",
        definition=copy.deepcopy(PX_DEF),
        description="wildcards in a name",
    )
    return w


def names(hits):
    return [h["name"] for h in hits]


def test_a_prefix_finds_the_part_of_a_name(cat):
    hits = cat.p.ops.search(cat.admin, "adj")
    assert names(hits)[0] == "adj_close" and hits[0]["namespace"] == "srch"
    assert hits[0]["tags"] == ["equity", "daily"] and hits[0]["score"] > 0


def test_a_name_match_outranks_a_description_match(cat):
    hits = cat.p.ops.search(cat.admin, "close")
    assert names(hits)[:2] == ["adj_close", "volume"]
    assert hits[0]["score"] > hits[1]["score"]


def test_every_term_must_match(cat):
    assert names(cat.p.ops.search(cat.admin, "adjusted closing")) == ["adj_close"]
    assert cat.p.ops.search(cat.admin, "adjusted nonsense") == []


def test_tags_and_namespaces_are_searchable(cat):
    assert "adj_close" in names(cat.p.ops.search(cat.admin, "equity"))
    hits = cat.p.ops.search(cat.admin, "srch")
    assert {"adj_close", "volume", "srch"} <= set(names(hits))


def test_sql_wildcards_in_a_query_are_literal(cat):
    assert cat.p.ops.search(cat.admin, "%") == []
    assert names(cat.p.ops.search(cat.admin, "pct_5")) == ["pct_50_off"]
    assert cat.p.ops.search(cat.admin, "p_t") == []


def test_the_index_follows_edits_in_the_same_transaction(cat):
    w = cat
    assert w.p.ops.search(w.admin, "microstructure") == []
    draft = w.p.features.get(w.dana, "srch/volume")["versions"][0]
    w.p.features.update_draft(
        w.dana,
        "srch/volume",
        draft["definition"],
        description="Microstructure volume",
        tags=["liquidity"],
    )
    assert names(w.p.ops.search(w.admin, "microstructure")) == ["volume"]
    assert names(w.p.ops.search(w.admin, "liquidity")) == ["volume"]
    assert "volume" not in names(w.p.ops.search(w.admin, "auctions"))


def test_a_failed_transaction_leaves_the_index_untouched(cat):
    w = cat
    with pytest.raises(RuntimeError):
        with w.p.uow("dana") as uow:
            feat = uow.repo("features").find_one(name="adj_close")
            uow.repo("features").update(feat["id"], {"description": "phantom rename"})
            raise RuntimeError("roll back")
    assert w.p.ops.search(w.admin, "phantom") == []


def test_search_never_names_what_the_caller_cannot_read(cat):
    w = cat
    w.p.access.create_user(w.admin, username="outsider", password=PASSWORD, roles=[])
    outsider = w.principal("outsider")
    assert [h for h in w.p.ops.search(outsider, "adj") if h["kind"] == "feature"] == []
    assert names(w.p.ops.search(w.dana, "adj"))[0] == "adj_close"


def test_short_queries_and_limits(cat):
    assert cat.p.ops.search(cat.admin, "a") == []
    assert len(cat.p.ops.search(cat.admin, "srch", limit=1)) == 1


def test_the_index_rebuilds_when_emptied_and_on_request(cat):
    w = cat
    with w.p.uow() as uow:
        uow.repo("search_terms").delete_where()
    assert w.p.ops.search(w.admin, "adj") == []
    w.p.ensure_search_index()
    assert names(w.p.ops.search(w.admin, "adj"))[0] == "adj_close"
    with pytest.raises(PermissionDenied):
        w.p.ops.reindex_search(w.dana)
    assert w.p.ops.reindex_search(w.admin)["objects"] >= 3
    with w.p.uow() as uow:
        assert uow.repo("audit_events").list(action="search.reindexed")
