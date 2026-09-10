"""Things a scanner found that might be models.

MAYA does not crawl the bank's drives: a discovery agent needs the broadest read
access anybody in the firm holds, granted to the system whose whole argument is
that it holds no standing power. What it does is take delivery, and be the place
the triage is recorded.
"""
from __future__ import annotations


import pytest

from core.discovery import OUTCOMES, DiscoveryError, DiscoveryRegister
from core.discovery.register import (DAY, MIN_FOR_PRECISION, USEFUL_PRECISION)


@pytest.fixture
def discovery(db, registry, evidence):
    from db import DiscoveryRepository
    return DiscoveryRegister(DiscoveryRepository(db), registry, evidence)


def _found(n, scanner="drive-crawler"):
    return {"fingerprint": f"fp-{n}", "location": f"/share/finance/model{n}.xlsx",
            "source": "shared drive", "proposed_as": "euc", "confidence": 0.7,
            "evidence": {"formulas": 412}}


class TestASweepIsIdempotent:
    def test_new_candidates_are_taken(self, discovery):
        out = discovery.ingest("drive-crawler", [_found(1), _found(2)])
        assert len(out["added"]) == 2

    def test_the_same_artifact_found_again_is_the_same_candidate(self,
                                                                 discovery):
        """What stops a monthly sweep re-raising four thousand spreadsheets
        nobody has time to look at twice."""
        discovery.ingest("drive-crawler", [_found(1)])
        out = discovery.ingest("drive-crawler", [_found(1)])
        assert out["added"] == [] and out["seen_again"] == 1

    def test_a_dismissed_candidate_does_not_come_back_open(self, discovery):
        """A candidate somebody dismissed coming back as open makes the triage
        pointless."""
        discovery.ingest("drive-crawler", [_found(1)])
        discovery.triage("DISC-0001", "not_a_model", "it is a chart")
        discovery.ingest("drive-crawler", [_found(1)])
        assert discovery.require("DISC-0001")["state"] == "triaged"

    def test_a_candidate_with_no_fingerprint_is_not_taken(self, discovery):
        """A path is not an identity, files move, and without one the next
        sweep would raise them all again."""
        out = discovery.ingest("drive-crawler",
                               [{"location": "/share/x.xlsx"}])
        assert out["added"] == []
        assert "a path is not an identity" in out["detail"]

    def test_an_unnamed_scanner_is_refused(self, discovery):
        with pytest.raises(DiscoveryError) as caught:
            discovery.ingest("  ", [_found(1)])
        assert caught.value.code == "scanner_required"

    def test_it_lands_on_the_evidence_chain(self, discovery, evidence):
        discovery.ingest("drive-crawler", [_found(1)])
        assert any(n["kind"] == "discovery_sweep_ingested"
                   for n in evidence.repo.many())


class TestTheTriageIsTheValue:
    def test_not_a_model_is_a_real_outcome(self, discovery):
        """A firm needs somewhere to put a decision it has already made, or it
        will make it again every month."""
        assert "not_a_model" in OUTCOMES
        discovery.ingest("drive-crawler", [_found(1)])
        out = discovery.triage("DISC-0001", "not_a_model",
                              "a pivot table over a report")
        assert out["outcome"] == "not_a_model"

    def test_euc_is_a_destination_not_a_lesser_one(self):
        """Sending a spreadsheet into the model register puts a tier-4
        obligation set on something that needs an owner and a review date."""
        assert "proportionate" in OUTCOMES["euc"]

    def test_deferred_is_distinguished_from_dismissed(self, discovery):
        """A backlog somebody is carrying is a different fact from a question
        somebody answered."""
        discovery.ingest("drive-crawler", [_found(1)])
        discovery.triage("DISC-0001", "deferred", "no capacity this quarter")
        assert discovery.require("DISC-0001")["state"] == "open"
        assert discovery.outstanding()["deferred"] == 1

    def test_a_triage_with_no_note_is_refused(self, discovery):
        discovery.ingest("drive-crawler", [_found(1)])
        with pytest.raises(DiscoveryError) as caught:
            discovery.triage("DISC-0001", "not_a_model", "  ")
        assert caught.value.code == "note_required"

    def test_registering_without_a_urn_is_refused(self, discovery):
        """Concluding a candidate IS a model without saying which leaves the
        record pointing at nothing."""
        discovery.ingest("drive-crawler", [_found(1)])
        with pytest.raises(DiscoveryError) as caught:
            discovery.triage("DISC-0001", "registered", "it is one")
        assert caught.value.code == "urn_required"

    def test_it_is_triaged_once(self, discovery):
        discovery.ingest("drive-crawler", [_found(1)])
        discovery.triage("DISC-0001", "not_a_model", "no")
        with pytest.raises(DiscoveryError) as caught:
            discovery.triage("DISC-0001", "euc", "actually yes")
        assert caught.value.code == "already_triaged"
        assert "lose the record that somebody decided" in (
            caught.value.remediation)

    def test_an_unknown_outcome_is_refused_naming_the_real_ones(self,
                                                                discovery):
        discovery.ingest("drive-crawler", [_found(1)])
        with pytest.raises(DiscoveryError) as caught:
            discovery.triage("DISC-0001", "maybe", "n")
        assert caught.value.code == "unknown_outcome"


class TestPrecisionDecidesWhetherToScaleUp:
    def _triaged(self, discovery, right, wrong, scanner="drive-crawler"):
        found = [_found(n) for n in range(right + wrong)]
        discovery.ingest(scanner, found)
        for i in range(right):
            discovery.triage(f"DISC-{i + 1:04d}", "euc", "a real spreadsheet")
        for i in range(right, right + wrong):
            discovery.triage(f"DISC-{i + 1:04d}", "not_a_model", "a chart")

    def test_nothing_triaged_has_no_precision(self, discovery):
        """A programme that only records what it found can never grade the
        thing that found it."""
        out = discovery.precision()
        assert out["scanners"] == []
        assert "computed from DISMISSALS as much as" in out["detail"]

    def test_a_good_scanner_is_worth_scaling(self, discovery):
        self._triaged(discovery, right=MIN_FOR_PRECISION, wrong=2)
        row = discovery.precision()["scanners"][0]
        assert row["precision"] > USEFUL_PRECISION
        assert row["worth_scaling"] is True

    def test_a_poor_scanner_creates_more_work_than_it_finds(self, discovery):
        self._triaged(discovery, right=5, wrong=MIN_FOR_PRECISION)
        out = discovery.precision()
        assert out["scanners"][0]["worth_scaling"] is False
        assert "creates more work than it finds risk" in out["detail"]

    def test_too_few_judged_is_noise_not_a_measurement(self, discovery):
        self._triaged(discovery, right=2, wrong=1)
        out = discovery.precision()
        assert out["scanners"][0]["enough_to_read"] is False
        assert "noise rather than a measurement" in out["detail"]

    def test_deferred_counts_neither_way(self, discovery):
        """An unanswered question tells you nothing about precision, and
        counting it either way would flatter or punish a scanner for the
        reviewer's backlog."""
        discovery.ingest("drive-crawler", [_found(1), _found(2)])
        discovery.triage("DISC-0001", "euc", "real")
        discovery.triage("DISC-0002", "deferred", "no capacity")
        assert discovery.precision()["scanners"][0]["judged"] == 1


class TestTheBacklog:
    def test_an_old_untriaged_candidate_is_named(self, discovery):
        """What a discovery programme looks like just before everybody stops
        reading its output."""
        discovery.ingest("drive-crawler", [_found(1)], now=0.0)
        out = discovery.outstanding(now=90 * DAY)
        assert out["stale"] == 1
        assert "just before everybody stops reading" in out["detail"]

    def test_a_clean_backlog_says_so(self, discovery):
        discovery.ingest("drive-crawler", [_found(1)])
        discovery.triage("DISC-0001", "not_a_model", "no")
        assert "has been triaged" in discovery.outstanding()["detail"]

    def test_an_empty_estate_says_why_it_is_empty(self, discovery):
        out = discovery.across_the_estate()
        assert out["candidates"] == 0
        assert "no standing power" in out["detail"]
