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
        verdict = policies.decide("model:mutate", {"attested": True})
        assert not verdict["allowed"]
        assert verdict["policy_source"] == "built-in"
        assert verdict["policy_version"] == 0

    def test_the_built_in_rules_are_the_behaviour_already_shipped(self, policies):
        assert policies.decide("model:mutate", {"attested": False})["allowed"]
        assert policies.decide("alias:move", {
            "to_status": "approved", "blocking_findings": 0,
            "refinement_holds": True, "variance_ok": True})["allowed"]
        assert not policies.decide("alias:move", {
            "to_status": "approved", "blocking_findings": 1,
            "refinement_holds": True, "variance_ok": True})["allowed"]

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
        verdict = policies.decide("model:mutate", {"attested": True})
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
        verdict = policies.decide("model:mutate", {"attested": True})
        assert "built-in policy v0" in verdict["detail"]
        assert verdict["facts_read"] == {"attested": True, "amending": False}

    def test_a_gate_raises_the_caller_s_own_error(self, policies):
        from core.registry import RegistryError
        gate = PolicyGate(policies, RegistryError)
        with pytest.raises(RegistryError, match="refused by policy"):
            gate.check("model:mutate", {"attested": True}, "a model")

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
