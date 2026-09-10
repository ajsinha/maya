"""What a model of this class, at this tier, owes before each lifecycle move.

The states stay one machine — nine graphs would mean nine reachability proofs
and nine answers to *can this be changed*. What varies is what each move costs:
the class says which evidence kinds must be on file, the tier says how many
signatures a move takes and how long it may sit before somebody should ask.

`Fibre.evidence` had been declared for all nine classes since the fibres were
written and had no consumer anywhere in the platform. These tests are the first
thing that reads it.
"""
from __future__ import annotations

import pytest

from core.fibres import FibreRegistry
from core.lifecycle.common import LifecycleError
from core.lifecycle.profiles import (DAY, SIGNATURES, SLA_DAYS,
                                     LifecycleProfiles)
from core.lifecycle.states import STATES, TRANSITIONS

NOW = 1_800_000_000.0


class FakeRegistry:
    """The three questions a profile asks the register, and nothing else."""

    def __init__(self, models=None, versions=None):
        self._models = models or {}
        self._versions = versions or {}

    def require(self, urn):
        if urn not in self._models:
            raise LifecycleError("no_model", f"no model {urn}", "")
        return self._models[urn]

    def versions(self, urn):
        return self._versions.get(urn, [])

    def list(self, *a, **kw):
        return list(self._models.values())


class FakeAttachments:
    def __init__(self, rows=None):
        self._rows = rows or {}

    def for_model(self, model_id):
        return self._rows.get(model_id, [])


class FakeEvidence:
    def __init__(self, nodes=None):
        self._nodes = nodes or {}

    def for_subject(self, subject_id):
        return self._nodes.get(subject_id, [])


def _model(urn="urn:maya:model:pd", model_id="m1", tier=2, status="attested"):
    return {"id": model_id, "urn": urn, "tier": tier, "status": status,
            "owner": "quant.desk"}


def _attachment(kind, state="accepted"):
    return {"kind": kind, "state": state}


def _move(to, at):
    """A chain node for entering a state. The evidence kind is `model_` plus
    the TRANSITION name, not the state name — `model_submit`, not
    `model_submitted` — and getting that wrong here would test nothing."""
    name = next((t.name for t in TRANSITIONS if t.target == to), to)
    return {"kind": f"model_{name}", "recorded_at": at, "payload": {"to": to}}


@pytest.fixture
def fibres():
    return FibreRegistry()


@pytest.fixture
def profiles(fibres):
    return LifecycleProfiles(FakeRegistry(), fibres)


class TestOneMachineNineSetsOfObligations:
    def test_every_class_has_a_reference_lifecycle(self, profiles):
        """FR-LC-002: T0 through T8, and none of them missing."""
        out = profiles.reference()
        assert out["count"] == 9
        assert [r["trainability_class"] for r in out["lifecycles"]] == [
            f"T{i}" for i in range(9)]

    def test_every_class_shares_the_state_graph(self, profiles, fibres):
        """The narrowing, asserted rather than described. If a fibre ever
        declares a shorter lifecycle this test is the thing that notices."""
        for trainability in fibres.classes():
            profile = profiles.for_class(trainability)
            assert profile["shares_the_state_graph"]
            assert profile["states"] == list(STATES)

    def test_the_obligations_are_not_all_the_same(self, profiles):
        """If every class owed the same evidence, deriving from the fibre would
        be an elaborate way of writing one list."""
        out = profiles.reference()
        assert out["distinct_evidence_sets"] > 1

    def test_a_t3_owes_an_independent_review_and_a_t0_does_not(self, profiles):
        """The sentence the whole module exists for."""
        t3 = profiles.for_class("T3")
        t0 = profiles.for_class("T0")
        attest = lambda p: next(m for m in p["transitions"]
                                if m["transition"] == "attest")
        assert "independent_review" in attest(t3)["required_evidence"]
        assert "independent_review" not in attest(t0)["required_evidence"]

    def test_an_unknown_class_is_refused_and_says_why(self, profiles):
        with pytest.raises(LifecycleError) as caught:
            profiles.for_class("T99")
        assert caught.value.code == "no_fibre"
        assert "L-15" in caught.value.remediation


class TestTheTierDecidesTheQuorum:
    def test_a_tier_one_attestation_takes_two_signatures(self, profiles):
        profile = profiles.for_class("T3", tier=1)
        attest = next(m for m in profile["transitions"]
                      if m["transition"] == "attest")
        assert attest["signatures"] == SIGNATURES[1] == 2

    def test_a_tier_four_attestation_takes_one(self, profiles):
        profile = profiles.for_class("T3", tier=4)
        attest = next(m for m in profile["transitions"]
                      if m["transition"] == "attest")
        assert attest["signatures"] == 1

    def test_returning_a_record_never_takes_a_quorum(self, profiles):
        """Requiring two signatures to send something BACK is how a review
        queue seizes up."""
        for tier in (1, 2, 3, 4):
            profile = profiles.for_class("T3", tier=tier)
            back = next(m for m in profile["transitions"]
                        if m["transition"] == "return")
            assert back["signatures"] == 1

    def test_an_untiered_model_gets_the_lightest_quorum_not_the_heaviest(
            self, profiles):
        """An untiered model is not a tier 1 model. The tiering gate refuses
        the move; this module must not silently invent a quorum for it."""
        profile = profiles.for_class("T3")
        assert profile["tier"] is None
        assert "no stated tier" in profile["detail"]
        attest = next(m for m in profile["transitions"]
                      if m["transition"] == "attest")
        assert attest["signatures"] == 1


class TestOnlyAttestingIsGuardedByEvidence:
    def test_drafting_and_submitting_carry_no_evidence_guard(self, profiles):
        """A control that fires before it can be satisfied teaches everybody to
        route around it: a draft cannot hold a validation report."""
        profile = profiles.for_class("T4")
        for move in profile["transitions"]:
            if move["transition"] != "attest":
                assert move["required_evidence"] == []

    def test_attesting_carries_the_whole_of_what_the_class_owes(
            self, profiles, fibres):
        profile = profiles.for_class("T4")
        attest = next(m for m in profile["transitions"]
                      if m["transition"] == "attest")
        assert attest["required_evidence"] == list(fibres.get("T4").evidence)


class TestWhatThisModelActuallyHolds:
    def _harness(self, fibres, attachments, trainability="T3", tier=2):
        model = _model()
        registry = FakeRegistry(
            {model["urn"]: model},
            {model["urn"]: [{"trainability_class": trainability}]})
        return LifecycleProfiles(
            registry, fibres, attachments=FakeAttachments({"m1": attachments}))

    def test_a_model_holding_everything_is_ready(self, fibres):
        held = [_attachment(k) for k in fibres.get("T3").evidence]
        out = self._harness(fibres, held).check("urn:maya:model:pd", "attest")
        assert out["ready"] is True
        assert out["missing_evidence"] == []
        assert "on file and accepted" in out["detail"]

    def test_a_missing_kind_is_named_with_the_class_that_owes_it(self, fibres):
        held = [_attachment("model_development_document")]
        out = self._harness(fibres, held).check("urn:maya:model:pd", "attest")
        assert out["ready"] is False
        assert "independent_review" in out["missing_evidence"]
        assert "a T3 model owes" in out["detail"]

    def test_on_file_but_unreviewed_is_a_different_answer_from_missing(
            self, fibres):
        """Collapsing the two sends somebody to write a report that is already
        written and sitting in a review queue."""
        held = [_attachment(k, state="attached")
                for k in fibres.get("T3").evidence]
        out = self._harness(fibres, held).check("urn:maya:model:pd", "attest")
        assert out["missing_evidence"] == []
        assert out["awaiting_review"] == list(fibres.get("T3").evidence)
        assert out["ready"] is False
        assert "that is what review is for" in out["detail"]

    def test_a_move_with_no_evidence_guard_says_so(self, fibres):
        out = self._harness(fibres, []).check("urn:maya:model:pd", "submit")
        assert out["required_evidence"] == []
        assert "authority, not documents" in out["detail"]

    def test_it_reports_whether_the_move_is_even_legal_from_here(self, fibres):
        """A model that holds every document and is in `draft` still cannot be
        attested, and a readiness answer that ignored the state would be a
        confident yes to a question with a no in it."""
        harness = self._harness(fibres, [])
        harness.registry._models["urn:maya:model:pd"]["status"] = "draft"
        out = harness.check("urn:maya:model:pd", "attest")
        assert out["legal_from_here"] is False
        assert harness.check("urn:maya:model:pd", "submit")["legal_from_here"]

    def test_a_model_with_no_version_has_no_class_and_is_refused(self, fibres):
        model = _model()
        registry = FakeRegistry({model["urn"]: model}, {})
        with pytest.raises(LifecycleError) as caught:
            LifecycleProfiles(registry, fibres).check(model["urn"], "attest")
        assert caught.value.code == "no_class"

    def test_an_unknown_transition_names_the_ones_that_exist(self, fibres):
        with pytest.raises(LifecycleError) as caught:
            self._harness(fibres, []).check("urn:maya:model:pd", "unsubmit")
        assert caught.value.code == "unknown_transition"
        assert "attest" in caught.value.remediation

    def test_without_an_attachment_service_it_says_nothing_rather_than_yes(
            self, fibres):
        """Degrading to silence, not to a confident wrong answer."""
        model = _model()
        registry = FakeRegistry(
            {model["urn"]: model},
            {model["urn"]: [{"trainability_class": "T3"}]})
        out = LifecycleProfiles(registry, fibres).check(model["urn"], "attest")
        assert out["ready"] is False
        assert out["missing_evidence"] == list(fibres.get("T3").evidence)


class TestTheQueueNobodyIsWatching:
    def _harness(self, fibres, models, nodes):
        registry = FakeRegistry({m["urn"]: m for m in models})
        return LifecycleProfiles(registry, fibres,
                                 evidence=FakeEvidence(nodes))

    def test_a_record_submitted_for_four_months_is_stalled(self, fibres):
        model = _model(status="submitted", tier=2)
        entered = NOW - 120 * DAY
        out = self._harness(fibres, [model],
                            {"m1": [_move("submitted", entered)]}).stalled(NOW)
        assert out["count"] == 1
        row = out["stalled"][0]
        assert row["days_in_state"] == pytest.approx(120.0)
        assert row["limit_days"] == SLA_DAYS["submitted"][2]
        assert row["days_over"] == pytest.approx(100.0)
        assert "allowed to have a queue" in out["detail"]

    def test_a_record_inside_its_window_is_not(self, fibres):
        model = _model(status="submitted", tier=2)
        entered = NOW - 5 * DAY
        out = self._harness(fibres, [model],
                            {"m1": [_move("submitted", entered)]}).stalled(NOW)
        assert out["count"] == 0
        assert "no record is sitting mid-move longer" in out["detail"]

    def test_the_tier_decides_how_long_is_too_long(self, fibres):
        """Thirty days submitted is a breach at tier 1 and fine at tier 4."""
        urgent = _model(urn="urn:a", model_id="m1", tier=1, status="submitted")
        relaxed = _model(urn="urn:b", model_id="m2", tier=4, status="submitted")
        entered = NOW - 30 * DAY
        out = self._harness(fibres, [urgent, relaxed],
                            {"m1": [_move("submitted", entered)],
                             "m2": [_move("submitted", entered)]}).stalled(NOW)
        assert [r["urn"] for r in out["stalled"]] == ["urn:a"]

    def test_attested_and_retired_carry_no_clock(self, fibres):
        """Where a record is supposed to REST. A clock here would report every
        model in force as overdue."""
        models = [_model(urn=f"urn:{s}", model_id=f"m{i}", status=s)
                  for i, s in enumerate(("attested", "retired", "draft"))]
        nodes = {f"m{i}": [_move(s, NOW - 5000 * DAY)]
                 for i, s in enumerate(("attested", "retired", "draft"))}
        out = self._harness(fibres, models, nodes).stalled(NOW)
        assert out["count"] == 0
        assert out["not_measurable"] == []

    def test_it_reads_the_chain_and_not_a_column(self, fibres):
        """The register row carries no `status_changed_at` at all, and a column
        would be a second copy of the chain that drifts from it."""
        model = _model(status="approved", tier=1)
        assert "status_changed_at" not in model
        nodes = {"m1": [_move("submitted", NOW - 200 * DAY),
                        _move("approved", NOW - 60 * DAY)]}
        out = self._harness(fibres, [model], nodes).stalled(NOW)
        # Measured from the APPROVAL, not from the submission before it.
        assert out["stalled"][0]["days_in_state"] == pytest.approx(60.0)

    def test_a_state_the_chain_never_recorded_is_named_not_skipped(
            self, fibres):
        """Reporting zero stalled records while some could not be measured
        would be a clean number covering an unclean one."""
        model = _model(status="submitted", tier=1)
        out = self._harness(fibres, [model], {"m1": []}).stalled(NOW)
        assert out["count"] == 0
        assert out["not_measurable"] == [{"urn": model["urn"],
                                          "status": "submitted"}]
        assert "could not be measured" in out["detail"]

    def test_the_worst_offender_is_first(self, fibres):
        models = [_model(urn=f"urn:{i}", model_id=f"m{i}", tier=2,
                         status="submitted") for i in range(3)]
        nodes = {f"m{i}": [_move("submitted", NOW - (30 + i * 40) * DAY)]
                 for i in range(3)}
        out = self._harness(fibres, models, nodes).stalled(NOW)
        assert [r["urn"] for r in out["stalled"]] == ["urn:2", "urn:1", "urn:0"]

    def test_without_a_chain_nothing_is_claimed(self, fibres):
        model = _model(status="submitted", tier=1)
        registry = FakeRegistry({model["urn"]: model})
        out = LifecycleProfiles(registry, fibres).stalled(NOW)
        assert out["count"] == 0
        assert len(out["not_measurable"]) == 1


class TestMovesFromAState:
    def test_it_names_what_is_legal(self, profiles):
        assert set(profiles.moves_from("draft")) == {"submit", "retire"}
        assert set(profiles.moves_from("attested")) == {"amend", "retire"}

    def test_a_terminal_state_has_nothing(self, profiles):
        assert profiles.moves_from("retired") == []


class TestTheBatchJob:
    """The job is what makes the clock a control rather than a screen.

    A number only visible to somebody who opens a page is a number nobody sees.
    """

    def _context(self, fibres, models, nodes, findings):
        from core.scheduler.jobs import JobContext

        registry = FakeRegistry({m["urn"]: m for m in models})
        registry.get = lambda urn: registry._models.get(urn)
        return JobContext(
            registry=registry, now=NOW, findings=findings,
            lifecycle_profiles=LifecycleProfiles(
                registry, fibres, evidence=FakeEvidence(nodes)))

    def test_a_stuck_record_raises_one_finding(self, fibres):
        from core.scheduler.jobs import lifecycle_stalled

        raised = []
        findings = type("F", (), {
            "open_for": lambda self, mid: [],
            "raise_finding": lambda self, *a, **kw: raised.append((a, kw)),
        })()
        model = _model(status="submitted", tier=2)
        ctx = self._context(fibres, [model],
                            {"m1": [_move("submitted", NOW - 120 * DAY)]},
                            findings)
        out = lifecycle_stalled(ctx)
        assert out["count"] == 1
        assert raised and "submitted for 120 days" in raised[0][0][2]

    def test_it_never_blocks(self, fibres):
        """A queue is allowed to have a queue: the reviewer may be right to be
        taking their time. What is not allowed is for nobody to know."""
        from core.scheduler.jobs import lifecycle_stalled

        raised = []
        findings = type("F", (), {
            "open_for": lambda self, mid: [],
            "raise_finding": lambda self, *a, **kw: raised.append(kw),
        })()
        model = _model(status="submitted", tier=1)
        ctx = self._context(fibres, [model],
                            {"m1": [_move("submitted", NOW - 400 * DAY)]},
                            findings)
        lifecycle_stalled(ctx)
        assert raised[0]["blocking"] is False
        assert raised[0]["category"] == "lifecycle_delay"

    def test_it_does_not_raise_the_same_finding_twice(self, fibres):
        from core.scheduler.jobs import lifecycle_stalled

        findings = type("F", (), {
            "open_for": lambda self, mid: [
                {"title": "Record has been submitted for 120 days"}],
            "raise_finding": lambda self, *a, **kw: (_ for _ in ()).throw(
                AssertionError("raised a second time")),
        })()
        model = _model(status="submitted", tier=2)
        ctx = self._context(fibres, [model],
                            {"m1": [_move("submitted", NOW - 120 * DAY)]},
                            findings)
        assert lifecycle_stalled(ctx)["count"] == 0

    def test_without_the_service_it_skips_rather_than_reporting_nothing_wrong(
            self, fibres):
        from core.scheduler.jobs import JobContext, lifecycle_stalled

        out = lifecycle_stalled(JobContext(registry=FakeRegistry(), now=NOW))
        assert "skipped" in out
