"""Which parts of this platform a deployment may extend, and which it may not.

Built as eight open sockets, a plugin architecture would be the fastest way to
remove every control here. So the answer is a statement of which axes are open
and why the others are not, with the open ones genuinely open.
"""
from __future__ import annotations

import pytest

from core.plugins import AXES, CLOSED, ExtensionPoints, PluginError, describe


@pytest.fixture
def points(evidence):
    return ExtensionPoints(evidence)


class TestTheDividingLine:
    def test_all_eight_axes_the_requirement_names_are_addressed(self):
        assert set(AXES) == {"test_types", "metric_types", "templates",
                             "notification_channels", "connectors", "formats",
                             "policy_evaluators", "runtime_adapters"}

    def test_the_open_ones_do_not_change_a_governance_answer(self):
        """A notification channel changes how somebody is told; a runtime
        adapter changes what may execute."""
        out = describe()
        assert set(out["open"]) == {"test_types", "metric_types", "templates",
                                    "notification_channels"}
        assert "changes a governance ANSWER" in out["detail"]

    def test_every_closed_axis_says_what_the_closure_protects(self):
        """An axis closed with no reason recorded is one somebody will open."""
        for axis, spec in AXES.items():
            if spec["state"] == CLOSED:
                assert spec["protects"], axis

    def test_the_format_axis_protects_the_pickle_decision(self):
        assert "pickle loader arriving by pull request" in (
            AXES["formats"]["protects"])

    def test_a_closed_axis_is_the_feature(self):
        assert "not a missing feature, it is the feature" in describe()["detail"]


class TestRegisteringOnAnOpenAxis:
    def test_a_test_type_is_registered(self, points):
        row = points.register("test_types", "discrimination.somers_d",
                              owner="person/a.mehta",
                              does="Somers' D over a scored sample",
                              implementation=lambda a, b: 0.5)
        assert row["name"] == "discrimination.somers_d"
        assert "implementation" not in row, "never handed back out"

    def test_the_implementation_is_retrievable_for_dispatch(self, points):
        points.register("test_types", "t", owner="o", does="d",
                        implementation=lambda: 42)
        assert points.get("test_types", "t")() == 42

    def test_an_extension_with_no_owner_is_refused(self, points):
        """Code nobody answers for, running inside a governance platform."""
        with pytest.raises(PluginError) as caught:
            points.register("test_types", "t", owner=" ", does="d")
        assert caught.value.code == "owner_required"

    def test_an_extension_that_does_not_say_what_it_is_for_is_refused(
            self, points):
        with pytest.raises(PluginError) as caught:
            points.register("test_types", "t", owner="o", does="  ")
        assert caught.value.code == "purpose_required"

    def test_a_name_is_never_silently_replaced(self, points):
        """Replacing it would change what a recorded result MEANS without
        changing its name, and every measurement taken under the old one would
        still say it was taken under this."""
        points.register("metric_types", "m", owner="o", does="d")
        with pytest.raises(PluginError) as caught:
            points.register("metric_types", "m", owner="other", does="d")
        assert caught.value.code == "already_registered"
        assert "part of what the measurement claims" in caught.value.remediation

    def test_registration_lands_on_the_evidence_chain(self, points, evidence):
        """*Who added the test everybody has been passing* is a question
        somebody will ask."""
        points.register("test_types", "t", owner="o", does="d")
        assert any(n["kind"] == "extension_registered"
                   for n in evidence.repo.many())


class TestTheClosedAxesRefuseWithARoute:
    @pytest.mark.parametrize("axis", ["connectors", "formats",
                                      "policy_evaluators", "runtime_adapters"])
    def test_it_is_refused_naming_what_the_closure_protects(self, points,
                                                            axis):
        with pytest.raises(PluginError) as caught:
            points.register(axis, "x", owner="o", does="d")
        assert caught.value.code == "axis_closed"
        assert AXES[axis]["protects"][:30] in caught.value.detail

    @pytest.mark.parametrize("axis", ["connectors", "formats",
                                      "policy_evaluators", "runtime_adapters"])
    def test_every_refusal_names_a_route(self, points, axis):
        """A refusal that names no route is a wall."""
        with pytest.raises(PluginError) as caught:
            points.register(axis, "x", owner="o", does="d")
        assert len(caught.value.remediation) > 40

    def test_a_policy_evaluator_is_pointed_at_rule_sets(self, points):
        with pytest.raises(PluginError) as caught:
            points.register("policy_evaluators", "x", owner="o", does="d")
        assert "author a rule set" in caught.value.remediation
        assert "without executing anybody's code" in caught.value.remediation

    def test_a_runtime_adapter_is_pointed_at_the_grammar(self, points):
        """A new model technology is already a new value in one of four axes,
        which is extension without arbitrary code."""
        with pytest.raises(PluginError) as caught:
            points.register("runtime_adapters", "x", owner="o", does="d")
        assert "warrant grammar's vocabularies" in caught.value.remediation

    def test_an_unknown_axis_is_refused_naming_the_real_ones(self, points):
        with pytest.raises(PluginError) as caught:
            points.register("whatever", "x", owner="o", does="d")
        assert caught.value.code == "unknown_axis"


class TestReadingBack:
    def test_an_empty_deployment_says_the_open_axes_are_unused(self, points):
        out = points.registered()
        assert out["count"] == 0
        assert "closed on purpose" in out["detail"]

    def test_registrations_are_listed_with_the_axis_map(self, points):
        points.register("templates", "board_summary", owner="o",
                        does="a one-page cut for the committee")
        out = points.registered()
        assert out["count"] == 1
        assert out["closed"] and out["open"]

    def test_one_axis_can_be_asked_for(self, points):
        points.register("templates", "t", owner="o", does="d")
        points.register("test_types", "u", owner="o", does="d")
        assert points.registered("templates")["count"] == 1

    def test_names_are_listed_for_dispatch(self, points):
        points.register("metric_types", "b", owner="o", does="d")
        points.register("metric_types", "a", owner="o", does="d")
        assert points.names("metric_types") == ["a", "b"]


class TestOverHttp:
    def test_the_axes_are_served_with_their_reasons(self, client, people):
        r = client.get("/api/v1/extension-points", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["closed"]) == 4
        assert "not a missing feature, it is the feature" in (
            body["axes_detail"])

    def test_a_closed_axis_is_refused_with_a_route(self, client, people):
        r = client.post("/api/v1/extension-points", auth=people["s.iqbal"],
                        json={"axis": "formats", "name": "pickle",
                              "owner": "person/x", "does": "load a pickle"})
        assert r.status_code == 403, r.text
        assert r.json()["error"] == "axis_closed"
        assert "goes through review" in r.json()["remediation"]

    def test_an_open_axis_accepts_a_registration(self, client, people):
        r = client.post("/api/v1/extension-points", auth=people["s.iqbal"],
                        json={"axis": "metric_types", "name": "psi.custom",
                              "owner": "person/d.raman",
                              "does": "our own population stability index"})
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "psi.custom"

    def test_the_admin_page_says_what_the_closures_protect(self, client,
                                                           people):
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/admin/runtimes"})
        body = client.get("/admin/runtimes").text
        assert "changes a governance" in body
        assert "not a missing feature; it is the feature" in body
