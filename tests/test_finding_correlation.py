"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

M-8: one cause, and the findings it produced.

The finding was answered once already, honestly and at the wrong layer:
suppression at the last hop, one digest per person per run. That damped the
storm **where it reached a person** rather than where it was generated, and left
a cost the honest answer did not remove — the findings are still twelve
independent facts about twelve models, so the ageing report counts twelve
overdue items and the board pack shows twelve open findings in one domain, which
reads as twelve problems.

Almost every test here is about something this **refuses** to do, and each
refusal is the reason the feature is safe to have. Merging would leave eleven
models with a live defect and nothing in their own record saying so. Inferring
would hide one finding behind another's closure. Closing a root would be one act
discharging obligations several different people owe.
"""
from __future__ import annotations

import time

import pytest

from core.validation.common import FindingWorkflowError
from core.validation.correlation import (ADDRESSED, KINDS, OPEN, FindingRoots)
from db import FindingRepository, FindingRootRepository

HOUR = 3600.0


@pytest.fixture
def roots(db, evidence):
    return FindingRoots(FindingRootRepository(db), FindingRepository(db),
                        evidence)


@pytest.fixture
def raised(db):
    """Three open findings on three models, from one source and category."""
    repo = FindingRepository(db)
    now = time.time()
    made = []
    for index in range(3):
        row = {"model_id": f"m{index}", "source": "monitoring",
               "severity": "High", "category": "data_quality",
               "title": f"psi breach on m{index}", "description": "",
               "blocking": False, "owner": f"person/owner{index}",
               "raised_at": now - HOUR, "due_at": now + 30 * 86400,
               "status": "open"}
        repo.add(row)
        made.append(row["id"])
    return made


class TestItMergesNothing:
    def test_the_posture_says_so(self):
        out = FindingRoots.posture()
        assert out["merges_findings"] is False
        assert "nothing in their own record saying so" in out["why_not_merge"]

    def test_every_finding_keeps_its_own_owner_and_model(self, roots, raised,
                                                         db):
        roots.open_root(title="the curve stopped landing",
                        kind="upstream_data",
                        detail="the rates view has not landed since Tuesday",
                        findings=raised, actor="s.iqbal")
        repo = FindingRepository(db)
        owners = {repo.one(id=f)["owner"] for f in raised}
        assert len(owners) == 3
        assert {repo.one(id=f)["model_id"] for f in raised} == {"m0", "m1", "m2"}

    def test_the_answer_says_nothing_was_merged(self, roots, raised):
        out = roots.open_root(title="x", kind="platform", detail="y",
                              findings=raised)
        assert out["merged_anything"] is False
        assert "nothing was merged" in out["detail_note"]


class TestCorrelationIsAssertedNeverInferred:
    def test_candidates_group_nothing(self, roots, raised):
        out = roots.candidates()
        assert out["groups_anything"] is False
        assert out["suggestions"][0]["models"] == 3
        assert "nothing has been grouped" in out["detail"]

    def test_the_signal_is_deliberately_weak_and_says_so(self, roots, raised):
        """A platform that grouped on it would eventually hide one finding
        behind another's closure."""
        assert "deliberately weak" in roots.candidates()["detail"]

    def test_a_single_model_is_not_a_candidate_group(self, roots, db):
        repo = FindingRepository(db)
        now = time.time()
        for index in range(3):
            repo.add({"model_id": "m0", "source": "monitoring",
                      "severity": "High", "category": "data_quality",
                      "title": f"f{index}", "description": "",
                      "blocking": False, "owner": "o",
                      "raised_at": now, "due_at": now + 1, "status": "open"})
        assert roots.candidates()["suggestions"] == []

    def test_an_already_correlated_finding_is_not_suggested_again(self, roots,
                                                                  raised):
        roots.open_root(title="x", kind="platform", detail="y",
                        findings=raised)
        assert roots.candidates()["suggestions"] == []

    def test_naming_a_root_goes_on_the_chain(self, roots, raised, evidence):
        out = roots.open_root(title="the curve stopped landing",
                              kind="upstream_data", detail="since Tuesday",
                              findings=raised, actor="s.iqbal")
        blob = str(evidence.for_subject(out["id"]))
        assert "finding_root_opened" in blob
        assert "s.iqbal" in blob


class TestWhatACauseHasToSay:
    def test_an_unknown_kind_is_refused(self, roots):
        with pytest.raises(FindingWorkflowError) as e:
            roots.open_root(title="x", kind="vibes", detail="y")
        assert e.value.code == "unknown_root_kind"
        assert "forty spellings of one word" in e.value.remediation

    def test_a_cause_with_no_description_is_refused(self, roots):
        """A cause with no description is a grouping, and a grouping nobody
        can read is a way of hiding findings."""
        with pytest.raises(FindingWorkflowError) as e:
            roots.open_root(title="x", kind="platform", detail="  ")
        assert e.value.code == "root_detail_required"
        assert "way of hiding findings" in e.value.remediation

    def test_a_cause_with_no_title_is_refused(self, roots):
        with pytest.raises(FindingWorkflowError) as e:
            roots.open_root(title=" ", kind="platform", detail="y")
        assert e.value.code == "root_title_required"

    def test_every_kind_says_what_it_means(self):
        assert len(KINDS) >= 5
        for _kind, means in KINDS:
            assert means.strip()


class TestAttachingIsAllOrNothing:
    def test_an_unknown_finding_refuses_the_whole_call(self, roots, raised):
        """A root that silently covers fewer findings than somebody listed is
        a root somebody will rely on."""
        made = roots.open_root(title="x", kind="platform", detail="y")
        with pytest.raises(FindingWorkflowError) as e:
            roots.attach(made["id"], [raised[0], "not-a-finding"])
        assert e.value.code == "unknown_finding"
        assert "rely on" in e.value.remediation

    def test_nothing_was_attached_when_it_refused(self, roots, raised, db):
        made = roots.open_root(title="x", kind="platform", detail="y")
        with pytest.raises(FindingWorkflowError):
            roots.attach(made["id"], [raised[0], "not-a-finding"])
        assert FindingRepository(db).one(id=raised[0]).get("root_id") in (None, "")

    def test_attaching_twice_is_not_an_error(self, roots, raised):
        made = roots.open_root(title="x", kind="platform", detail="y",
                               findings=raised)
        again = roots.attach(made["id"], raised)
        assert again["attached"] == []
        assert len(again["already_attached"]) == 3

    def test_an_unknown_root_is_a_404(self, roots):
        with pytest.raises(FindingWorkflowError) as e:
            roots.require("nope")
        assert e.value.code == "unknown_root"


class TestAddressingClosesNothing:
    def test_the_findings_stay_open(self, roots, raised, db):
        made = roots.open_root(title="x", kind="upstream_data", detail="y",
                               findings=raised)
        out = roots.address(made["id"], "the view was backfilled")
        assert out["findings_closed"] == 0
        assert len(out["still_open"]) == 3
        assert all(FindingRepository(db).one(id=f)["status"] == "open"
                   for f in raised)

    def test_the_answer_says_why(self, roots, raised):
        made = roots.open_root(title="x", kind="platform", detail="y",
                               findings=raised)
        out = roots.address(made["id"], "restarted")
        assert "none was closed by this" in out["detail"]
        assert "several different people owe" in out["detail"]

    def test_a_cause_addressed_with_no_note_is_refused(self, roots):
        """A cause marked addressed with no account of how is a row that will
        be read as an all-clear."""
        made = roots.open_root(title="x", kind="platform", detail="y")
        with pytest.raises(FindingWorkflowError) as e:
            roots.address(made["id"], "  ")
        assert e.value.code == "root_note_required"

    def test_addressing_twice_is_refused(self, roots):
        made = roots.open_root(title="x", kind="platform", detail="y")
        roots.address(made["id"], "done")
        with pytest.raises(FindingWorkflowError) as e:
            roots.address(made["id"], "done again")
        assert e.value.code == "root_already_addressed"

    def test_the_status_moves_even_though_nothing_closed(self, roots):
        made = roots.open_root(title="x", kind="platform", detail="y")
        assert made["status"] == OPEN
        assert roots.address(made["id"], "done")["status"] == ADDRESSED


class TestCountingCausesRatherThanSymptoms:
    def test_the_estate_view_counts_causes(self, roots, raised):
        roots.open_root(title="the curve stopped landing",
                        kind="upstream_data", detail="y", findings=raised)
        out = roots.across_the_estate()
        assert out["count"] == 1
        assert out["findings_correlated"] == 3
        assert out["roots"][0]["models"] == 3
        assert "asks about the wrong thing" in out["detail"]

    def test_one_cause_names_how_many_owners_it_crosses(self, roots, raised):
        """Which is what makes a shared cause hard: each owner sees a problem
        they cannot fix."""
        made = roots.open_root(title="x", kind="upstream_data", detail="y",
                               findings=raised)
        out = roots.of(made["id"])
        assert len(out["owners"]) == 3
        assert "cannot fix" in out["detail"]

    def test_it_groups_by_kind(self, roots):
        roots.open_root(title="a", kind="platform", detail="d")
        roots.open_root(title="b", kind="platform", detail="d")
        roots.open_root(title="c", kind="vendor_change", detail="d")
        out = roots.across_the_estate()
        assert out["by_kind"] == {"platform": 2, "vendor_change": 1}


class TestThroughTheApi:
    def test_the_posture_is_published(self, client):
        out = client.get("/api/v1/finding-roots/posture").json()
        assert out["merges_findings"] is False
        assert out["closing_a_root_closes_findings"] is False

    def test_a_root_is_named_over_the_wire(self, client, registered):
        made = client.post("/api/v1/finding-roots", json={
            "title": "the rates view stopped landing",
            "kind": "upstream_data", "detail": "nothing since Tuesday"})
        assert made.status_code == 201, made.text
        out = client.get("/api/v1/finding-roots").json()
        assert out["count"] == 1

    def test_an_unknown_kind_is_refused_over_the_wire(self, client,
                                                      registered):
        out = client.post("/api/v1/finding-roots", json={
            "title": "x", "kind": "vibes", "detail": "y"})
        assert out.status_code == 422
        assert "unknown_root_kind" in out.text

    def test_candidates_answer_without_grouping(self, client, registered):
        out = client.get("/api/v1/finding-roots/candidates")
        assert out.status_code == 200
        assert out.json()["groups_anything"] is False
