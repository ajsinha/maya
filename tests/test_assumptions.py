"""What a model relies on being true, stated where it can be counted.

The sibling of `test_limitations`, and the distinction decides what each
register is for. A limitation is a boundary of competence and cannot stop being
true. An assumption is a claim about the world the model reads, and **can stop
being true while the model is running** — which is why the question this
register answers is not *what is enforced* but **what is monitored, and what is
merely believed**.
"""
from __future__ import annotations

import pytest

from core.assumptions import KINDS, MATERIALITIES, AssumptionRegister
from core.registry.common import RegistryError

URN = "maya://model/credit.assumes"
OTHER = "maya://model/credit.elsewhere"
KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
          "input_schema": [{"name": "dscr", "dtype": "numeric"}],
          "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]}


@pytest.fixture
def assumes(repos, db, registry, evidence):
    from db import AssumptionRepository, MonitorRepository

    for urn in (URN, OTHER):
        registry.register(urn, "Assumes", "credit", "retail", "person/o",
                          "LE-US-01", "assumption register")
        registry.create_version(urn, "1.0.0", dict(KERNEL), {})
    return AssumptionRegister(AssumptionRepository(db), registry, evidence,
                              monitors=MonitorRepository(db))


@pytest.fixture
def monitor_on(db, registry):
    """A monitor row on a named model, without going through the registry."""
    from db import MonitorRepository

    def _make(urn: str, monitor_id: str):
        model = registry.require(urn)
        MonitorRepository(db).add(
            {"id": monitor_id, "model_id": model["id"],
             "model_version_id": None, "name": "psi", "kind": "input_drift",
             "test_key": "stability.psi", "threshold": {}, "slice": {},
             "reference": {}, "cadence_days": 1.0, "label_delay_days": 0.0,
             "breach_severity": "Medium", "escalate_after": 3,
             "status": "active", "owner": "person/o", "created_at": 0.0})
        return monitor_id
    return _make


class TestStatingOne:
    def test_an_unmonitored_assumption_is_recorded_and_counted_as_such(self, assumes):
        assumes.record(URN, "1.0.0", "behavioural",
                       "borrowers prepay when it is rational to")
        out = assumes.for_version(URN, "1.0.0")
        assert out["standing"] == 1
        assert out["unmonitored"] == 1 and out["monitored"] == 0
        # The count the register exists to surface, phrased for a reader.
        assert "believed and unwatched" in out["detail"]

    def test_a_monitored_assumption_names_the_monitor_that_tests_it(
            self, assumes, monitor_on):
        mid = monitor_on(URN, "mon-1")
        assumes.record(URN, "1.0.0", "data", "the sector mix is stable",
                       monitor_id=mid)
        out = assumes.for_version(URN, "1.0.0")
        assert out["monitored"] == 1 and out["unmonitored"] == 0

    def test_references_are_sequential_within_a_version(self, assumes):
        for i in range(3):
            assumes.record(URN, "1.0.0", "structural", f"assumption {i}")
        refs = [a["reference"] for a in
                assumes.for_version(URN, "1.0.0")["assumptions"]]
        assert refs == ["ASM-0001", "ASM-0002", "ASM-0003"]

    @pytest.mark.parametrize("kind", KINDS)
    def test_every_declared_kind_is_accepted(self, assumes, kind):
        assumes.record(URN, "1.0.0", kind, f"a {kind} assumption")

    def test_a_kind_outside_the_closed_set_is_refused_by_name(self, assumes):
        with pytest.raises(RegistryError) as exc:
            assumes.record(URN, "1.0.0", "vibes", "something")
        assert "not a kind of assumption" in str(exc.value)
        assert "operational" in str(exc.value), "name the five"

    def test_an_assumption_with_no_statement_is_refused(self, assumes):
        with pytest.raises(RegistryError) as exc:
            assumes.record(URN, "1.0.0", "data", "   ")
        assert "and not what" in str(exc.value)

    def test_a_materiality_outside_the_ladder_is_refused(self, assumes):
        with pytest.raises(RegistryError) as exc:
            assumes.record(URN, "1.0.0", "data", "s", materiality="apocalyptic")
        assert "not a materiality" in str(exc.value)


class TestAClaimOfBeingWatchedIsChecked:
    """A false claim of coverage reads as the safe case, which is why it is the
    one state the register refuses outright."""

    def test_naming_a_monitor_that_does_not_exist_is_refused(self, assumes):
        with pytest.raises(RegistryError) as exc:
            assumes.record(URN, "1.0.0", "data", "the mix is stable",
                           monitor_id="no-such-monitor")
        assert "no such monitor exists" in str(exc.value)
        assert "reads as the safe case" in str(exc.value)

    def test_naming_another_models_monitor_is_refused(self, assumes, monitor_on):
        """The one that would otherwise pass. A monitor on somebody else's
        model leaves the assumption unwatched and reporting itself watched."""
        elsewhere = monitor_on(OTHER, "mon-elsewhere")
        with pytest.raises(RegistryError) as exc:
            assumes.record(URN, "1.0.0", "data", "the mix is stable",
                           monitor_id=elsewhere)
        assert "defined on another model" in str(exc.value)

    def test_with_no_monitor_repository_it_holds_no_opinion(
            self, repos, db, registry, evidence):
        """Not wired is not the same as wrong. An unwired register accepts the
        id rather than refusing something it cannot check."""
        from db import AssumptionRepository

        register = AssumptionRegister(AssumptionRepository(db), registry,
                                      evidence, monitors=None)
        registry.register("maya://model/unwired", "U", "c", "r", "person/o",
                          "LE-US-01", "p")
        registry.create_version("maya://model/unwired", "1.0.0", dict(KERNEL), {})
        register.record("maya://model/unwired", "1.0.0", "data", "s",
                        monitor_id="anything")


class TestTheNumberWorthActingOn:
    """A material assumption that nothing watches and nothing compensates for
    is not a documentation gap; it is a decision nobody has taken."""

    def test_material_and_unmonitored_is_counted_separately(self, assumes):
        assumes.record(URN, "1.0.0", "data", "low one", materiality="low")
        assumes.record(URN, "1.0.0", "market", "grave one",
                       materiality="critical")
        out = assumes.for_version(URN, "1.0.0")
        assert out["unmonitored"] == 2
        assert out["unmonitored_material"] == 1, "only the critical one counts"
        assert "material or worse" in out["detail"]

    def test_a_mitigation_takes_it_out_of_the_unmitigated_count(self, assumes):
        assumes.record(URN, "1.0.0", "market", "grave one",
                       materiality="material",
                       mitigation="a management overlay caps the output")
        out = assumes.for_version(URN, "1.0.0")
        assert out["unmonitored_material"] == 1, "still unmonitored"
        assert out["unmitigated"] == 0, "but something compensates"

    def test_monitoring_it_removes_it_from_the_grave_count(self, assumes,
                                                           monitor_on):
        assumes.record(URN, "1.0.0", "market", "grave one",
                       materiality="critical",
                       monitor_id=monitor_on(URN, "mon-2"))
        assert assumes.for_version(URN, "1.0.0")["unmonitored_material"] == 0


class TestWithdrawal:
    def test_an_assumption_is_withdrawn_and_never_deleted(self, assumes):
        made = assumes.record(URN, "1.0.0", "data", "the mix is stable")
        assumes.withdraw(made["id"], "the mix moved and the model was refitted")
        out = assumes.for_version(URN, "1.0.0")
        assert out["standing"] == 0
        assert len(out["assumptions"]) == 1, "the row is still there"
        assert out["assumptions"][0]["withdrawal_reason"]

    def test_withdrawing_without_a_reason_is_refused(self, assumes):
        made = assumes.record(URN, "1.0.0", "data", "s")
        with pytest.raises(RegistryError) as exc:
            assumes.withdraw(made["id"], "  ")
        assert "needs a reason" in str(exc.value)

    def test_withdrawing_twice_is_refused(self, assumes):
        made = assumes.record(URN, "1.0.0", "data", "s")
        assumes.withdraw(made["id"], "no longer relied on")
        with pytest.raises(RegistryError) as exc:
            assumes.withdraw(made["id"], "again")
        assert "already withdrawn" in str(exc.value)


class TestTheEstateView:
    """`for_version` needs a urn AND a semver, so *what is this book relying on
    that nobody is watching* had no route that could be asked it."""

    def test_it_sorts_the_worst_read_first(self, assumes, monitor_on):
        assumes.record(URN, "1.0.0", "data", "watched",
                       monitor_id=monitor_on(URN, "mon-3"))
        assumes.record(OTHER, "1.0.0", "market", "grave and unwatched",
                       materiality="critical")
        estate = assumes.across_the_estate()
        assert estate["versions"][0]["urn"] == OTHER, \
            "a material unmonitored assumption outranks a monitored one"
        assert estate["standing"] == 2
        assert estate["unmonitored_material"] == 1

    def test_a_withdrawn_assumption_leaves_the_estate_view(self, assumes):
        made = assumes.record(URN, "1.0.0", "data", "s")
        assumes.withdraw(made["id"], "refitted")
        assert assumes.across_the_estate()["standing"] == 0

    def test_an_empty_register_says_so_as_a_claim(self, assumes):
        detail = assumes.across_the_estate()["detail"]
        assert "not an absence of one" in detail


class TestTheLadder:
    def test_materialities_are_ordered_worst_last(self):
        assert MATERIALITIES == ("low", "moderate", "material", "critical")


class TestALinkThatResolvesToNothing:
    """`finding_id` and `overlay_id` are ids into other subsystems.

    An id nobody checks is a link that silently does not exist — and the row
    that claims a monitor, a finding AND an overlay, all three dangling, reads
    as the best-governed assumption on the estate.
    """

    @pytest.fixture
    def linked(self, repos, db, registry, evidence):
        from db import (AssumptionRepository, FindingRepository,
                        MonitorRepository, OverlayRepository)

        for urn in (URN, OTHER):
            registry.register(urn, "A", "credit", "retail", "person/o",
                              "LE-US-01", "p")
            registry.create_version(urn, "1.0.0", dict(KERNEL), {})
        return AssumptionRegister(
            AssumptionRepository(db), registry, evidence,
            monitors=MonitorRepository(db), findings=FindingRepository(db),
            overlays=OverlayRepository(db))

    def test_a_finding_that_does_not_exist_is_refused(self, linked):
        with pytest.raises(RegistryError) as exc:
            linked.record(URN, "1.0.0", "data", "s", finding_id="nope")
        assert "no such finding exists" in str(exc.value)
        assert "reads as coverage" in str(exc.value)

    def test_an_overlay_that_does_not_exist_is_refused(self, linked):
        with pytest.raises(RegistryError) as exc:
            linked.record(URN, "1.0.0", "data", "s", overlay_id="nope")
        assert "no such overlay exists" in str(exc.value)

    def test_another_models_overlay_is_refused(self, linked, db, registry):
        """The one that would otherwise pass."""
        from db import OverlayRepository

        other = registry.require(OTHER)
        OverlayRepository(db).add(
            {"id": "ov-elsewhere", "model_id": other["id"],
             "model_version_id": None, "reference": "OVL-0001",
             "name": "cap", "kind": "output_adjustment", "direction": "increase",
             "rationale": "r", "basis": "", "owner": "person/o",
             "proposed_by": "person/o", "approved_by": None,
             "status": "approved", "effective_from": 0.0, "expires_at": None,
             "renewals": 0, "finding_id": None, "created_at": 0.0,
             "closed_at": None, "closure_reason": None})
        with pytest.raises(RegistryError) as exc:
            linked.record(URN, "1.0.0", "data", "s", overlay_id="ov-elsewhere")
        assert "is on another model" in str(exc.value)
