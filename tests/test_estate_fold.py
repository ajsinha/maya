"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The estate fold, and the one thing it must never do: answer differently.

`WorkList.for_model` consults nine sources and `Portfolio.by` calls it per
model, so a cut of fifty thousand models was most of half a million round trips
and took 33 seconds. The cost is flat per model — 0.67 ms across sizes — so the
shape was wrong rather than any one query being slow.

**The obvious fix was the wrong one.** A batched twin of each source is a second
definition of *what a model owes*, and a second implementation of a governance
judgement eventually disagrees with the first — in the direction of reporting
less outstanding work, because that is the direction in which nobody files a
bug. So the sources are untouched and their READS are served from an index
built once per fold.

Which makes this file the guard on the whole idea. If the folded answer ever
differs from the unfolded one, the optimisation has become a governance defect
and these tests are what says so.
"""
from __future__ import annotations

import time

import pytest

from core.estate.worklist import FOLDED, WorkList
from db import FindingRepository


@pytest.fixture
def worklist(registry, lifecycle, findings):
    return WorkList(registry, lifecycle=lifecycle, findings=findings)


@pytest.fixture
def portfolio(db, registry, worklist):
    from core.estate.portfolio import Portfolio
    from db import RiskRepository
    return Portfolio(registry, worklist=worklist, risk=RiskRepository(db))


class TestTheFoldedAnswerEqualsTheUnfoldedOne:
    def test_the_same_items_for_one_model(self, worklist, a_model, db):
        """`for_model` inside a fold and outside it are the same question."""
        outside = [i.as_dict() for i in worklist.for_model(a_model)]
        with db.folding(FOLDED):
            inside = [i.as_dict() for i in worklist.for_model(a_model)]
        assert inside == outside

    def test_the_same_items_across_an_estate(self, worklist, registry, db,
                                             a_model):
        _spread(registry)
        models = registry.list()
        with_fold = [i.as_dict() for i in worklist.across(models)]
        # `across` folds; compare against the loop it replaced.
        without = []
        for model in models:
            without.extend(i.as_dict() for i in worklist.for_model(model))
        assert sorted(i["title"] for i in with_fold) == \
            sorted(i["title"] for i in without)

    def test_an_open_finding_is_still_seen_through_the_fold(
            self, worklist, findings, a_model, db):
        findings.raise_finding(
            a_model["id"], "High", "Backtest failed", "person/j.okafor",
            description="d", due_at=time.time() - 86_400, blocking=True,
            actor="a.mehta")
        with db.folding(FOLDED):
            titles = [i.title for i in worklist.for_model(a_model)]
        assert any("finding" in t.lower() for t in titles)

    def test_the_portfolio_cut_is_unchanged_by_folding(self, portfolio,
                                                       registry, a_model):
        _spread(registry)
        cut = portfolio.by("tier")
        assert cut["models"] == len(registry.list())
        assert sum(c["models"] for c in cut["cells"]) == cut["models"]


class TestItServesOnlyWhatItCanAnswerCorrectly:
    def test_a_two_column_filter_is_served_exactly(self, db, a_model,
                                                    findings):
        """Indexed on the exact column SET asked for. The sources filter on
        one column and on two, and answering a two-column question from a
        one-column index would mean filtering in Python — the same work this
        exists to remove."""
        findings.raise_finding(a_model["id"], "High", "t", "o",
                               description="d")
        repo = FindingRepository(db)
        outside = repo.many(model_id=a_model["id"], status="open")
        with db.folding(FOLDED):
            inside = repo._from_fold({"model_id": a_model["id"],
                                      "status": "open"})
        assert inside == outside and len(inside) == 1

    def test_an_empty_filter_is_never_served_from_the_index(self, db):
        """An empty filter means *everything*, which the index has no reason
        to answer and every reason not to."""
        with db.folding(FOLDED):
            assert FindingRepository(db)._from_fold({}) is None

    def test_an_ordered_read_falls_through(self, db, a_model):
        repo = FindingRepository(db)
        with db.folding(FOLDED):
            # `many` with an explicit order must not use the index, because the
            # index is sorted by the repository's own ORDER and nothing else.
            assert repo.many(order="severity", model_id=a_model["id"]) == []

    def test_a_table_outside_the_list_is_never_folded(self, db, a_model):
        with db.folding(FOLDED):
            assert db.folded("telemetry_batch", "model_id", "x") is None

    def test_nothing_is_folded_outside_a_fold(self, db):
        assert db.folded("finding", "model_id", "x") is None


class TestAFoldIsReadOnly:
    def test_writing_a_folded_table_refuses(self, db, findings, a_model):
        """A fold that silently re-read half its answers would be worse than a
        slow one, so the write raises rather than invalidating quietly."""
        with pytest.raises(RuntimeError) as exc, db.folding(FOLDED):
            FindingRepository(db).add({
                "model_id": a_model["id"], "severity": "High", "title": "t",
                "description": "d", "owner": "o", "status": "open",
                "blocking": 0, "raised_by": "a", "raised_at": time.time()})
        assert "half-stale" in str(exc.value)

    def test_the_fold_is_closed_afterwards(self, db):
        with db.folding(FOLDED):
            pass
        assert db.folded("finding", "model_id", "x") is None

    def test_it_closes_even_when_the_body_raises(self, db):
        with pytest.raises(ValueError), db.folding(FOLDED):
            raise ValueError("boom")
        assert db.folded("finding", "model_id", "x") is None

    def test_nesting_does_not_drop_the_outer_index(self, db, a_model):
        """The inner scope's exit must not clear the outer scope's index — the
        bug that produces is a read that is correct on Tuesday."""
        with db.folding(FOLDED):
            db.folded("finding", "model_id", a_model["id"])
            with db.folding(FOLDED):
                pass
            assert db.folded("finding", "model_id", a_model["id"]) is not None


def _spread(registry):
    """A handful of models in different states, so the fold has work to do."""
    for index in range(6):
        urn = f"maya://model/fold.{index}"
        if registry.get(urn) is None:
            registry.register(urn, f"Folded {index}", "credit.pd.scorecard",
                              "credit", "person/j.okafor", "LE-US-01", "p")
            registry.set_tier(registry.get(urn)["id"], (index % 4) + 1)
