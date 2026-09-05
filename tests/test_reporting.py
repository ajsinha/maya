"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Risk appetite, and the pack a committee reads.

An appetite statement in most banks is a sentence in a document, which is not a
control: nobody can compute against a sentence, so the number in the quarterly
pack is prepared by hand and whether it is inside the limit is somebody's
judgement. Holding a limit as a threshold over a metric the platform computes
makes utilisation arithmetic and a breach a fact.

Four properties carry the design, and each is a refusal rather than a feature.

**A metric the platform cannot compute is refused when the limit is written.**
A limit that fails while a committee is reading it fails at the worst possible
time, and its author is long gone.

**A limit with no rationale is refused.** A number nobody can explain is a number
nobody will change, so it is either ignored or obeyed without thought.

**An unmeasured indicator is never reported as clean.** Zero is a measurement; an
absent service is not, and reporting one as the other tells a committee an estate
is healthy when it is unobserved.

**There is no composite score.** Aggregating requires the parts to compose, and
two models fed by the same curve are not two independent risks — so any single
figure either double-counts the shared dependency or ignores it, and a committee
cannot decompose it to find out which.
"""
from __future__ import annotations

import pytest

from core.reporting import (AMBER, BREACH, BY_KEY, NO_APPETITE, NO_COMPOSITE,
                            AppetiteRegister, BoardPackBuilder, IndicatorSet,
                            ReportingError, WITHIN, within_scope)


@pytest.fixture
def appetite(db, evidence):
    from db import RiskAppetiteRepository
    return AppetiteRegister(RiskAppetiteRepository(db), evidence)


@pytest.fixture
def packs(db, evidence, registry, appetite):
    from db import BoardPackRepository
    return BoardPackBuilder(BoardPackRepository(db),
                            IndicatorSet(registry), appetite, registry, evidence)


def status_of(pack, metric):
    return next(r for r in pack["indicators"] if r["metric"] == metric)["status"]


def a_model(**over):
    row = {"id": over.get("id", "m-1"), "urn": "maya://model/x",
           "tier": 2, "status": "attested", "domain": "credit",
           "legal_entity": "LE-1"}
    row.update(over)
    return row


class TestALimitMustBeAbleToDoItsJob:
    def test_a_metric_the_platform_cannot_compute_is_refused(self, appetite):
        """When the limit is WRITTEN. A limit that failed while a committee was
        reading it would fail at the worst possible time."""
        with pytest.raises(ReportingError) as exc:
            appetite.declare(metric="vibes", limit=3, rationale="because")
        assert exc.value.code == "unknown_metric"
        assert "worst possible time" in exc.value.remediation

    def test_a_limit_with_no_rationale_is_refused(self, appetite):
        with pytest.raises(ReportingError) as exc:
            appetite.declare(metric="blocking_findings", limit=5, rationale="  ")
        assert exc.value.code == "rationale_required"
        assert "nobody will change" in exc.value.remediation

    def test_amber_on_the_far_side_of_the_limit_is_refused(self, appetite):
        """A warning that can only fire after the thing it warns about has
        happened is not a warning."""
        with pytest.raises(ReportingError) as exc:
            appetite.declare(metric="blocking_findings", limit=5, amber=9,
                             rationale="tolerance for open blockers")
        assert exc.value.code == "amber_beyond_limit"

    def test_amber_is_checked_the_other_way_for_a_higher_is_better_metric(
            self, appetite):
        assert BY_KEY["monitored_share"].direction == "higher_is_better"
        with pytest.raises(ReportingError):
            appetite.declare(metric="monitored_share", limit=0.9, amber=0.8,
                             rationale="coverage")
        row = appetite.declare(metric="monitored_share", limit=0.9, amber=0.95,
                               rationale="coverage of models in force")
        assert row["amber_value"] == 0.95

    def test_a_scope_the_platform_cannot_filter_on_is_refused(self, appetite):
        with pytest.raises(ReportingError) as exc:
            appetite.declare(metric="blocking_findings", limit=1,
                             rationale="r", scope={"team": "quants"})
        assert exc.value.code == "unknown_scope"

    def test_direction_is_the_metric_s_not_the_author_s(self, appetite):
        """Whether more is worse is a property of open blocking findings, not
        an opinion somebody expresses while setting a limit."""
        row = appetite.declare(metric="blocking_findings", limit=5,
                               rationale="tolerance while remediating")
        assert row["direction"] == "lower_is_better"


class TestVersionsAccumulateAndARelaxationIsNamed:
    def test_declaring_over_a_limit_versions_it(self, appetite):
        appetite.declare(metric="blocking_findings", limit=5, rationale="r")
        second = appetite.declare(metric="blocking_findings", limit=3,
                                  rationale="tightened after Q3")
        assert second["version"] == 2
        assert appetite.current("blocking_findings")["limit_value"] == 3
        assert len(appetite.history("blocking_findings")) == 2

    def test_a_relaxation_is_computed_rather_than_left_to_a_reader(
            self, appetite, evidence):
        """A committee raising a limit because the estate grew is doing
        something reasonable; raising it because the estate breached it is doing
        something else, and only the record tells the two apart."""
        appetite.declare(metric="blocking_findings", limit=3, rationale="r")
        row = appetite.declare(metric="blocking_findings", limit=9,
                               rationale="tolerance raised for the migration")
        node = evidence.for_subjects([row["id"]])[0]
        assert node["payload"]["relaxed"] is True

    def test_tightening_is_not_reported_as_a_relaxation(self, appetite, evidence):
        appetite.declare(metric="blocking_findings", limit=9, rationale="r")
        row = appetite.declare(metric="blocking_findings", limit=3, rationale="r2")
        assert evidence.for_subjects([row["id"]])[0]["payload"]["relaxed"] is False

    def test_a_scoped_limit_does_not_supersede_the_estate_wide_one(self, appetite):
        appetite.declare(metric="blocking_findings", limit=10, rationale="estate")
        appetite.declare(metric="blocking_findings", limit=0, rationale="tier 1",
                         scope={"tier": 1})
        live = appetite.in_force()
        assert len(live) == 2
        assert live[0]["scope"] == {}, "least specific first: the order they fold"

    def test_retiring_stops_it_applying_and_keeps_the_versions(self, appetite):
        appetite.declare(metric="blocking_findings", limit=5, rationale="r")
        appetite.retire("blocking_findings")
        assert appetite.current("blocking_findings") is None
        assert appetite.history("blocking_findings"), "the record is not deleted"


class TestTheIndicators:
    def test_an_absent_service_is_unmeasured_rather_than_zero(self, registry):
        """Zero is a measurement; an absent service is not, and reporting one as
        the other tells a committee an estate is clean when it is unobserved."""
        out = IndicatorSet(registry).compute([a_model()])
        assert out["values"]["blocking_findings"] is None
        assert "blocking_findings" in out["unmeasured"]

    def test_counts_that_need_no_service_are_computed(self, registry):
        out = IndicatorSet(registry).compute(
            [a_model(id="a", tier=None), a_model(id="b", status="draft")])
        assert out["values"]["models_untiered"] == 1
        assert out["values"]["models_not_in_force"] == 1

    def test_a_share_over_an_empty_estate_is_undefined_not_perfect(self, registry):
        """Reporting a perfect ratio over an empty set is the most flattering
        possible lie."""
        out = IndicatorSet(registry).compute([])
        assert out["values"]["in_force_share"] is None

    def test_scope_is_equality_and_nothing_cleverer(self):
        model = a_model(tier=1, domain="credit")
        assert within_scope(model, {"tier": 1})
        assert within_scope(model, {"tier": 1, "domain": "credit"})
        assert not within_scope(model, {"tier": 2})
        assert within_scope(model, {})


class TestThePack:
    def test_an_indicator_with_no_limit_is_a_number_not_an_indicator(self, packs):
        pack = packs.build(models=[a_model()])
        row = next(r for r in pack["indicators"]
                   if r["metric"] == "models_untiered")
        assert row["status"] == NO_APPETITE
        assert "not an indicator" in row["status_means"]

    def test_within_amber_and_breach(self, packs, appetite):
        appetite.declare(metric="models_untiered", limit=2, amber=1,
                         rationale="tolerance while the campaign runs")
        untiered = [a_model(id=f"m{i}", tier=None) for i in range(4)]

        assert status_of(packs.build(models=untiered[:1]),
                         "models_untiered") == WITHIN
        assert status_of(packs.build(models=untiered[:2]),
                         "models_untiered") == AMBER
        assert status_of(packs.build(models=untiered),
                         "models_untiered") == BREACH

    def test_the_most_specific_limit_wins(self, packs, appetite):
        appetite.declare(metric="models_untiered", limit=10, rationale="estate")
        appetite.declare(metric="models_untiered", limit=0, rationale="tier 1",
                         scope={"tier": 1})
        pack = packs.build(scope={"tier": 1},
                           models=[a_model(tier=1, id="a")])
        row = next(r for r in pack["indicators"]
                   if r["metric"] == "models_untiered")
        assert row["limit"] == 0

    def test_the_exceptions_are_what_to_act_on(self, packs, appetite):
        appetite.declare(metric="models_untiered", limit=0,
                         rationale="every model is tiered before it is used")
        pack = packs.build(models=[a_model(tier=None)])
        assert [e["metric"] for e in pack["exceptions"]] == ["models_untiered"]

    def test_an_unmeasured_indicator_is_said_out_loud_in_the_headline(self, packs):
        pack = packs.build(models=[a_model()])
        assert "NOT MEASURED" in pack["detail"]

    def test_the_rationale_travels_with_the_number(self, packs, appetite):
        """A reader who was not in the room needs to know what the limit is FOR."""
        appetite.declare(metric="models_untiered", limit=0,
                         rationale="a model with no tier has no control set")
        row = next(r for r in packs.build(models=[a_model()])["indicators"]
                   if r["metric"] == "models_untiered")
        assert "no control set" in row["rationale"]
        assert row["matters"], "the metric says why a committee cares"


class TestThereIsNoCompositeScore:
    def test_the_pack_says_so_rather_than_leaving_an_absence(self, packs):
        """A reader who came looking for one finds the reason instead."""
        pack = packs.build(models=[a_model()])
        assert pack["no_composite"] is NO_COMPOSITE
        assert "double-counts" in pack["no_composite"]

    def test_no_indicator_is_an_aggregate_of_the_others(self):
        keys = set(BY_KEY)
        assert not {"model_risk_score", "composite", "overall"} & keys


class TestMovement:
    def test_the_first_pack_has_nothing_to_move_from(self, packs):
        pack = packs.build(models=[a_model()])
        row = pack["indicators"][0]
        assert row["movement"]["since"] is None

    def test_a_later_pack_reports_the_change_and_its_direction(self, packs,
                                                               appetite):
        appetite.declare(metric="models_untiered", limit=5, rationale="r")
        packs.cut(period="2026-Q1")
        packs.registry.register(
            urn="maya://model/a.b", name="A", model_class="c", domain="credit",
            owner="person/x", legal_entity="LE-1", purpose="p", actor="admin")
        later = packs.build(period="2026-Q2")
        row = next(r for r in later["indicators"]
                   if r["metric"] == "models_untiered")
        assert row["movement"]["was"] == 0 and row["movement"]["change"] == 1
        assert row["movement"]["improving"] is False, \
            "more untiered models is worse, and the direction belongs to the metric"

    def test_a_pack_is_kept_as_it_was_read(self, packs):
        """A committee minute referring to 'the March pack' needs the March pack,
        not a document with the same name recomputed today."""
        cut = packs.cut(period="2026-Q1")
        packs.registry.register(
            urn="maya://model/a.b", name="A", model_class="c", domain="credit",
            owner="person/x", legal_entity="LE-1", purpose="p", actor="admin")
        assert packs.get(cut["id"])["models"] == cut["models"]

    def test_an_unknown_pack_is_refused_by_name(self, packs):
        with pytest.raises(ReportingError) as exc:
            packs.get("nope")
        assert exc.value.code == "no_board_pack"


class TestSlack:
    def test_a_limit_never_approached_is_reported_after_two_packs(self, packs,
                                                                  appetite):
        """A control that has never fired is indistinguishable from one that
        cannot, and a committee reviewing its own appetite should hear which of
        its limits are doing no work."""
        appetite.declare(metric="models_untiered", limit=100,
                         rationale="deliberately generous")
        packs.cut(period="2026-Q1")
        second = packs.build(period="2026-Q2")
        row = next(r for r in second["indicators"]
                   if r["metric"] == "models_untiered")
        assert row["slack"] and row["slack"]["packs"] >= 2
        assert "not constraining anything" in row["slack"]["detail"]

    def test_one_quiet_quarter_is_just_a_quiet_quarter(self, packs, appetite):
        appetite.declare(metric="models_untiered", limit=100, rationale="r")
        first = packs.build(period="2026-Q1")
        row = next(r for r in first["indicators"]
                   if r["metric"] == "models_untiered")
        assert row["slack"] is None

    def test_slack_is_not_a_breach(self, packs, appetite):
        appetite.declare(metric="models_untiered", limit=100, rationale="r")
        packs.cut(period="2026-Q1")
        second = packs.build(period="2026-Q2")
        assert not second["exceptions"]


class TestOverTheApi:
    def test_the_metric_vocabulary_is_published(self, client):
        body = client.get("/api/v1/risk-appetite/metrics").json()
        keys = {m["key"] for m in body["metrics"]}
        assert "blocking_findings" in keys
        assert all(m["matters"] for m in body["metrics"]), \
            "an indicator whose purpose is not stated is a statistic"

    def test_a_limit_is_declared_and_read_back(self, client):
        r = client.post("/api/v1/risk-appetite", json={
            "metric": "blocking_findings", "limit": 5, "amber": 3,
            "rationale": "tolerance while the remediation programme runs",
            "owner": "person/s.iqbal"})
        assert r.status_code == 201, r.text
        assert client.get("/api/v1/risk-appetite").json()["appetite"]

    def test_a_bad_limit_is_refused_with_a_status_that_says_who_must_act(
            self, client):
        r = client.post("/api/v1/risk-appetite", json={
            "metric": "blocking_findings", "limit": 5, "rationale": ""})
        assert r.status_code == 422
        assert r.json()["error"] == "rationale_required"

    def test_a_pack_can_be_previewed_without_creating_one(self, client,
                                                          registered):
        """Somebody preparing for a meeting should be able to look before the
        committee is minuted against what they find."""
        preview = client.post("/api/v1/board-packs/preview", json={}).json()
        assert preview["indicators"]
        assert client.get("/api/v1/board-packs").json()["packs"] == []

    def test_cutting_one_records_it(self, client, registered):
        cut = client.post("/api/v1/board-packs",
                          json={"period": "2026-Q1"}).json()
        assert cut["period"] == "2026-Q1"
        listing = client.get("/api/v1/board-packs").json()
        assert len(listing["packs"]) == 1
        assert "double-counts" in listing["no_composite"]

    def test_the_history_of_a_limit_is_readable(self, client):
        for limit in (5, 3):
            client.post("/api/v1/risk-appetite", json={
                "metric": "blocking_findings", "limit": limit,
                "rationale": f"limit {limit}"})
        body = client.get("/api/v1/risk-appetite/history/blocking_findings").json()
        assert [v["version"] for v in body["versions"]] == [1, 2]


class TestThePage:
    """The pages read the SESSION, not the Basic header, so these sign in the
    way a browser does."""

    @pytest.fixture
    def page(self, client, registered):
        from tests.api_helpers import login
        login(client)
        return client

    def test_it_renders_with_the_indicators_and_the_reason_for_no_composite(
            self, page):
        rendered = page.get("/board-pack")
        assert rendered.status_code == 200
        assert "models_untiered" in rendered.text
        assert "double-counts" in rendered.text, \
            "a reader who came looking for one number should find the reason"

    def test_an_unmeasured_indicator_is_shown_as_unmeasured_not_clean(self, page):
        """The page must not let a committee read an absent service as a zero."""
        assert "Not measured" in page.get("/board-pack").text

    def test_the_cut_button_is_offered_only_to_somebody_who_may_cut(
            self, client, people):
        """A page that hides a control it cannot explain beats one that offers
        an action the caller may not take."""
        from tests.api_helpers import login
        login(client)
        assert "Record it" in client.get("/board-pack").text

        login(client, username="d.raman", password=people["d.raman"][1])
        assert "Record it" not in client.get("/board-pack").text
