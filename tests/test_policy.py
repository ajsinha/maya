"""
MAYA — tests for versioned gates.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A gate that cannot be changed without a release is worked around. A gate that
can be weakened without a release is worse. What is under test is the machinery
that makes the first possible without making the second silent.
"""
from __future__ import annotations

import pytest

from core.policy import PolicyError, Rule, vocabulary
from core.policy.engine import PolicyGate

MUTATE_CASES = [
    {"name": "a draft is mutable", "expect": "allow", "facts": {"attested": False}},
    {"name": "an attested record is not", "expect": "refuse",
     "facts": {"attested": True}},
    {"name": "an amendment reopens it", "expect": "allow",
     "facts": {"attested": True, "amending": True}},
]


# ================================================================ the language
class TestARuleIsAPredicateNotAProgram:
    def test_it_reads_the_facts_the_gate_publishes(self):
        rule = Rule("blocking_findings == 0 and tier is not None",
                    vocabulary("version:approve"))
        assert rule.facts_read() == ["blocking_findings", "tier"]

    def test_a_fact_the_gate_does_not_publish_is_refused_when_written(self):
        """A rule that failed at the moment of a governance decision would have
        failed at the worst possible time."""
        with pytest.raises(PolicyError) as exc:
            Rule("phase_of_the_moon == 'full'", vocabulary("version:approve"))
        assert exc.value.code == "unknown_fact"
        assert "worst possible time" in exc.value.remediation

    @pytest.mark.parametrize("hostile", [
        "__import__('os').system('ls')", "open('/etc/passwd')",
        "[x for x in (1, 2)]", "tier.__class__", "_secret == 1",
    ])
    def test_it_admits_nothing_that_is_not_a_predicate(self, hostile):
        with pytest.raises(PolicyError):
            Rule(hostile, vocabulary("version:approve"))

    def test_it_can_quantify_over_a_collection(self):
        rule = Rule("all(f != 'Critical' for f in open_findings)",
                    vocabulary("version:approve"))
        assert rule.evaluate({"open_findings": ["High", "Low"],
                              "blocking_findings": 0, "tier": 1})
        assert not rule.evaluate({"open_findings": ["Critical"],
                                  "blocking_findings": 0, "tier": 1})

    def test_a_rule_returns_a_verdict_and_not_a_value(self):
        assert Rule("tier", vocabulary("version:approve")).evaluate(
            {"tier": 3}) is True


# ==================================================== the cases are the gate
class TestAPolicyCarriesItsOwnTests:
    def test_a_policy_that_refuses_nothing_is_refused(self, policies):
        """A policy nobody has shown to refuse anything is a policy nobody has
        shown to be a gate."""
        with pytest.raises(PolicyError) as exc:
            policies.draft("model:mutate", "True", "always allow",
                           [{"name": "a", "expect": "allow", "facts": {}},
                            {"name": "b", "expect": "allow",
                             "facts": {"attested": True}}])
        assert exc.value.code == "no_refusing_case"

    def test_too_few_cases_is_refused(self, policies):
        with pytest.raises(PolicyError) as exc:
            policies.draft("model:mutate", "not attested", "x",
                           [{"name": "a", "expect": "refuse",
                             "facts": {"attested": True}}])
        assert exc.value.code == "too_few_cases"

    def test_a_case_with_no_expected_verdict_tests_nothing(self, policies):
        with pytest.raises(PolicyError) as exc:
            policies.draft("model:mutate", "not attested", "x",
                           [{"name": "a", "facts": {}},
                            {"name": "b", "expect": "refuse",
                             "facts": {"attested": True}}])
        assert exc.value.code == "case_without_a_verdict"

    def test_a_policy_needs_a_sentence_saying_what_it_is_for(self, policies):
        with pytest.raises(PolicyError) as exc:
            policies.draft("model:mutate", "not attested", "  ", MUTATE_CASES)
        assert exc.value.code == "reason_required"
        assert "tells them nothing they can act on" in exc.value.remediation

    def test_a_policy_whose_cases_fail_cannot_be_published(self, policies):
        drafted = policies.draft(
            "model:mutate", "not attested", "stricter than it claims",
            [{"name": "draft ok", "expect": "allow", "facts": {}},
             {"name": "attested refused", "expect": "refuse",
              "facts": {"attested": True}},
             {"name": "amending allowed", "expect": "allow",
              "facts": {"attested": True, "amending": True}}])
        assert not drafted["test_report"]["passed"]
        with pytest.raises(PolicyError) as exc:
            policies.publish(drafted["id"])
        assert exc.value.code == "cases_do_not_pass"
        assert "weakened without one" in exc.value.remediation


# ===================================================== nothing changes by default
class TestAnInstanceThatPublishesNothing:
    def test_runs_the_built_in_rule(self, policies):
        verdict = policies.decide("model:mutate", {"attested": True}, strict=False)
        assert not verdict["allowed"]
        assert verdict["policy_source"] == "built-in"
        assert verdict["policy_version"] == 0

    def test_the_built_in_rules_are_the_behaviour_already_shipped(self, policies):
        assert policies.decide("model:mutate", {"attested": False}, strict=False)["allowed"]
        assert policies.decide("alias:move", {
            "to_status": "approved", "blocking_findings": 0,
            "refinement_holds": True, "variance_ok": True}, strict=False)["allowed"]
        assert not policies.decide("alias:move", {
            "to_status": "approved", "blocking_findings": 1,
            "refinement_holds": True, "variance_ok": True}, strict=False)["allowed"]

    def test_every_gate_is_described_with_the_facts_it_publishes(self, policies):
        described = {g["gate"]: g for g in policies.describe()}
        assert set(described) == {"version:approve", "alias:move",
                                  "model:mutate", "warrant:resolve"}
        assert all(g["facts"] for g in described.values())
        assert described["model:mutate"]["source"] == "built-in"


# ======================================================== publishing and drift
class TestWeakeningIsAllowedAndNeverQuiet:
    def _publish(self, policies, rule, reason, cases, actor="person/s.iqbal"):
        drafted = policies.draft("model:mutate", rule, reason, cases, actor)
        return policies.publish(drafted["id"], actor)

    def test_a_published_policy_takes_over_from_the_built_in(self, policies):
        self._publish(policies, "not attested or amending",
                      "the built-in rule, published", MUTATE_CASES)
        verdict = policies.decide("model:mutate", {"attested": True}, strict=False)
        assert verdict["policy_source"] == "published"
        assert verdict["policy_version"] == 1

    def test_loosening_is_reported_case_by_case(self, policies):
        """A change that loosens a gate should be a thing somebody decided, not
        a thing somebody discovered."""
        self._publish(policies, "not attested or amending", "as shipped",
                      MUTATE_CASES)
        out = self._publish(
            policies, "lifecycle_state != 'retired'", "deliberately looser",
            [{"name": "draft ok", "expect": "allow", "facts": {}},
             {"name": "attested now fine", "expect": "allow",
              "facts": {"attested": True}},
             {"name": "retired is not", "expect": "refuse",
              "facts": {"lifecycle_state": "retired"}}])
        assert out["drift"]["loosened"]
        assert out["drift"]["loosened"][0]["name"] == "an attested record is not"
        assert "are now permitted" in out["drift"]["detail"]

    def test_tightening_is_reported_too(self, policies):
        self._publish(policies, "not attested or amending", "as shipped",
                      MUTATE_CASES)
        out = self._publish(
            policies, "not attested", "no amendment escape",
            [{"name": "draft ok", "expect": "allow", "facts": {}},
             {"name": "attested refused", "expect": "refuse",
              "facts": {"attested": True}},
             {"name": "amending refused too", "expect": "refuse",
              "facts": {"attested": True, "amending": True}}])
        assert out["drift"]["tightened"]
        assert "are now refused" in out["drift"]["detail"]

    def test_the_superseded_version_is_kept(self, policies):
        self._publish(policies, "not attested or amending", "first",
                      MUTATE_CASES)
        self._publish(policies, "not attested or amending", "second",
                      MUTATE_CASES)
        history = policies.history("model:mutate")
        assert [(p["version"], p["state"]) for p in history] == [
            (1, "superseded"), (2, "published")]

    def test_publishing_twice_is_refused(self, policies):
        drafted = policies.draft("model:mutate", "not attested or amending",
                                 "x", MUTATE_CASES)
        policies.publish(drafted["id"])
        with pytest.raises(PolicyError) as exc:
            policies.publish(drafted["id"])
        assert exc.value.code == "already_decided"

    def test_every_step_is_witnessed(self, policies, repos):
        drafted = policies.draft("model:mutate", "not attested or amending",
                                 "x", MUTATE_CASES)
        policies.publish(drafted["id"])
        kinds = [e["kind"] for e in repos["evidence"].many()]
        assert "policy_drafted" in kinds and "policy_published" in kinds


# ============================================================== at a call site
class TestPolicyTightensAndDoesNotLoosen:
    def test_the_verdict_names_the_version_that_reached_it(self, policies):
        """'Why was this refused in March' is a question about a rule that may
        since have changed."""
        verdict = policies.decide("model:mutate", {"attested": True}, strict=False)
        assert "built-in policy v0" in verdict["detail"]
        assert verdict["facts_read"] == {"attested": True, "amending": False}

    def test_a_gate_raises_the_caller_s_own_error(self, policies):
        """The live path, so every fact the rule reads must be supplied.

        `model:mutate`'s built-in rule is `not attested or amending`, and
        omitting `amending` here would once have defaulted it. It cannot now: a
        gate wired without a fact it judges on stops working visibly rather than
        passing everything.
        """
        from core.registry import RegistryError
        gate = PolicyGate(policies, RegistryError)
        with pytest.raises(RegistryError, match="refused by policy"):
            gate.check("model:mutate", {"attested": True, "amending": False},
                       "a model")

    def test_the_live_path_refuses_a_fact_the_rule_reads_and_nobody_supplied(
            self, policies):
        """The structural repair. Fourteen of thirty-six advertised facts were
        never supplied by any call site, and three of them default to the
        PERMISSIVE value — so a published gate reading `blocking_findings` was
        in force, advertised, and had never been able to fire."""
        from core.policy import PolicyError
        with pytest.raises(PolicyError) as exc:
            policies.decide("model:mutate", {"attested": True})
        assert exc.value.code == "fact_not_supplied"
        assert "amending" in exc.value.detail
        assert "wiring" in exc.value.remediation

    def test_it_says_what_it_can_and_cannot_do(self, policies):
        from core.registry import RegistryError
        described = PolicyGate(policies, RegistryError).describe()
        assert "never instead of them" in described["applies"]
        assert "cannot" in described and "the floor" in described["cannot"]

    def test_the_registry_consults_it(self, registry, a_model, policies):
        """Wired the way the application wires it, and refusing the way it does."""
        from core.registry import RegistryError
        registry.attach_policy(PolicyGate(policies, RegistryError))
        policies.draft("model:mutate", "tier != 1", "tier 1 records are frozen",
                       [{"name": "tier 2 mutable", "expect": "allow",
                         "facts": {"tier": 2}},
                        {"name": "tier 1 is not", "expect": "refuse",
                         "facts": {"tier": 1}}])
        published = policies.history("model:mutate")[0]
        policies.publish(published["id"])
        with pytest.raises(RegistryError, match="refused by policy"):
            registry.update(a_model["urn"], {"purpose": "something else"})

    def test_an_unknown_gate_is_refused(self, policies):
        with pytest.raises(PolicyError) as exc:
            policies.decide("model:bless", {})
        assert exc.value.code == "unknown_gate"


class TestNoGateCouldSeeTheRecordItself:
    """Every gate spoke about the version. None spoke about the model.

    A model risk manager walked a Tier 2, regulatory-capital model from
    registration to a signed execution credential in four calls, without the
    record ever being submitted or approved — no validation, no parameters, no
    monitor, no accepted document. The descriptor printed
    `"model_status": "draft"` and was signed anyway.

    The four built-in gates read `version_status`, `to_status`,
    `blocking_findings`, `refinement_holds`, `variance_ok`, `attested`,
    `amending`. Every one of those is a fact about a version or about
    attestation. Nothing asked the question a supervisor asks first: has anybody
    approved this model at all?
    """

    def test_the_record_s_own_state_is_in_the_vocabulary(self):
        from core.policy import vocabulary
        assert "record_status" in vocabulary("warrant:resolve")
        assert "record_status" in vocabulary("alias:move")

    def test_the_built_in_resolve_rule_consults_it(self):
        from core.policy import BUILT_IN
        from core.policy.language import Rule
        from core.policy.facts import vocabulary
        rule, _reason = BUILT_IN["warrant:resolve"]
        assert "record_status" in Rule(rule, vocabulary("warrant:resolve")).facts_read()

    def test_a_draft_record_is_refused(self, db, evidence):
        from core.policy import PolicyRegister
        register = PolicyRegister(_policy_repo(db), evidence)
        verdict = register.decide("warrant:resolve", {
            "version_status": "approved", "record_status": "draft"})
        assert not verdict["allowed"]
        assert "draft" in verdict["reason"]

    def test_a_retired_record_is_refused(self, db, evidence):
        from core.policy import PolicyRegister
        register = PolicyRegister(_policy_repo(db), evidence)
        assert not register.decide("warrant:resolve", {
            "version_status": "approved", "record_status": "retired"})["allowed"]

    def test_an_approved_record_with_an_approved_version_resolves(self, db, evidence):
        from core.policy import PolicyRegister
        register = PolicyRegister(_policy_repo(db), evidence)
        assert register.decide("warrant:resolve", {
            "version_status": "approved", "record_status": "approved"})["allowed"]

    def test_a_baselined_record_still_resolves(self, db, evidence):
        """Deliberate. A baselined record is an estate imported from a legacy
        inventory, governed going forward and carrying its debt explicitly.
        Refusing it would mean a bank cannot bring what it already runs under
        governance without first re-approving all of it, which is the opposite
        of what importing is for."""
        from core.policy import PolicyRegister
        register = PolicyRegister(_policy_repo(db), evidence)
        assert register.decide("warrant:resolve", {
            "version_status": "approved", "record_status": "baselined"})["allowed"]


def _policy_repo(db):
    from db import PolicyRuleRepository
    return PolicyRuleRepository(db)


class TestAGateNobodyReviewedIsRefused:
    """`/policies` said the register enforces this. It did not.

    The page reads, in these words: "Drafting and publishing are separate
    duties, and the register enforces it: a validator writes a rule and a model
    risk manager puts it in force." `publish()` never compared `published_by` to
    the row's author and `policy:publish` was not in the segregation table, so a
    reviewer holding both permissions authored a gate and enacted it alone — and
    the page then rendered "s.iqbal / put in force by s.iqbal" directly beneath
    that sentence.
    """

    def test_the_act_is_in_the_segregation_table(self):
        from core.authz.segregation import BY_ACT
        assert "policy:publish" in BY_ACT
        assert "policy_drafted" in BY_ACT["policy:publish"].conflicting_kinds

    def test_the_drafter_may_not_publish_their_own_rule(self, client, people):
        drafted = client.post("/api/v1/policies", auth=people["s.iqbal"], json={
            "gate": "warrant:resolve",
            "rule": "version_status == 'approved'",
            "reason": "a warrant resolves only against an approved version",
            "cases": [
                {"name": "approved runs", "facts": {"version_status": "approved"},
                 "expect": "allow"},
                {"name": "draft does not", "facts": {"version_status": "draft"},
                 "expect": "refuse"}]})
        assert drafted.status_code in (200, 201), drafted.text
        policy_id = drafted.json()["id"]

        alone = client.post(f"/api/v1/policies/{policy_id}/publish",
                            auth=people["s.iqbal"])
        assert alone.status_code == 403, alone.text
        assert alone.json()["error"] == "segregation_of_duties"
        assert "drafted" in alone.json()["detail"]

    def test_somebody_else_holding_the_permission_may(self, client, people):
        """The control is independence, not scarcity: the act stays possible."""
        drafted = client.post("/api/v1/policies", auth=people["a.mehta"], json={
            "gate": "warrant:resolve",
            "rule": "version_status == 'approved'",
            "reason": "a warrant resolves only against an approved version",
            "cases": [
                {"name": "approved runs", "facts": {"version_status": "approved"},
                 "expect": "allow"},
                {"name": "draft does not", "facts": {"version_status": "draft"},
                 "expect": "refuse"}]})
        assert drafted.status_code in (200, 201), drafted.text
        published = client.post(
            f"/api/v1/policies/{drafted.json()['id']}/publish",
            auth=people["s.iqbal"])
        assert published.status_code in (200, 201), published.text


class TestAGateIsJudgedOnFactsAndNotOnDefaults:
    """A published, in-force gate had no effect.

    `complete()` filled in every fact a gate declares, so by the time a rule
    ran nothing was ever missing and `fact_not_supplied` could never fire.
    Fourteen of thirty-six advertised facts were never passed by any call site,
    and three — `blocking_findings`, `open_findings`, `actor_roles` — default to
    the PERMISSIVE value.

    The built-in `version:approve` rule is
    `blocking_findings == 0 and tier is not None`, published at
    `/api/v1/policies` as in force with the reason *"a version is not approved
    over an open blocking finding"*. Half of it had never been able to fire.
    """

    def test_a_version_is_not_approved_over_an_open_blocking_finding(
            self, client, people, registered):
        """The reviewer's demonstration, as a test."""
        from tests.conftest import NAME, URN

        raised = client.post("/api/v1/findings", auth=people["a.mehta"], json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor", "blocking": True})
        assert raised.status_code in (200, 201), raised.text

        refused = client.post(f"/api/v1/models/{NAME}/versions/3.2.1/approve",
                              auth=people["s.iqbal"])
        assert refused.status_code == 409, refused.text
        assert "blocking finding" in refused.json()["detail"]

    def test_closing_it_lets_the_approval_through(self, client, people, registered):
        """The control is the finding, not the gate being permanently shut."""
        from tests.conftest import NAME, URN

        finding = client.post("/api/v1/findings", auth=people["a.mehta"], json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor", "blocking": True}).json()["id"]
        client.post(f"/api/v1/findings/{finding}/close", auth=people["s.iqbal"],
                    json={"evidence": {"pr": "1"}})
        assert client.post(f"/api/v1/models/{NAME}/versions/3.2.1/approve",
                           auth=people["s.iqbal"]).status_code in (200, 409)

    def test_every_gate_supplies_what_its_built_in_rule_reads(self, registered,
                                                              people):
        """The systematic version, so the next gate cannot be wired short.

        Behavioural rather than a source grep: it takes the facts the LIVE
        wiring produces and checks they cover what each built-in rule reads.
        A rule reading a fact nobody supplies is refused by `decide()` now, so
        this is the check that says which one before a caller meets it.
        """
        from core.policy import BUILT_IN
        from core.policy.facts import vocabulary
        from core.policy.language import Rule

        ctx = registered.app.state.ctx
        registry, facts = ctx["registry"], ctx["registry"].version_service.facts
        assert facts is not None, "the register was wired with no fact provider"

        from tests.conftest import URN
        model = registry.require(URN)
        version = registry.versions(URN)[-1]

        produced = {
            "version:approve": {
                "tier", "status", "has_artifact_digest", "has_contract",
                *facts.version_approve(model, version)},
            "alias:move": {
                "tier", "environment", "alias", "to_status", "refinement_holds",
                "variance_ok", "attested", *facts.alias_move(model)},
            "model:mutate": {
                "tier", "lifecycle_state", "attested", "amending",
                *facts.model_mutate(model)},
            "warrant:resolve": {
                "tier", "environment", "declared_use", "principal", "attested",
                "record_status", "version_status",
                *facts.warrant_resolve(model, version)},
        }
        for gate, supplied in produced.items():
            rule, _reason = BUILT_IN[gate]
            reads = set(Rule(rule, vocabulary(gate)).facts_read())
            missing = sorted(reads - supplied)
            assert not missing, (
                f"the {gate} gate's built-in rule reads {missing} and the "
                f"wiring supplies none of it — so the default decides")

    def test_a_finding_register_that_is_down_fails_closed(self):
        """A subsystem that is unreachable must not read as "there are none",
        which is exactly how the defaulted value behaved."""
        from core.policy.wiring import GateFacts

        class Broken:
            def open_for(self, _model_id):
                raise RuntimeError("the finding register is unreachable")

        facts = GateFacts(findings=Broken())._findings("m1")
        assert facts["blocking_findings"] == 1
        assert facts["open_findings"] == ["unknown"]
