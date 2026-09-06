"""
MAYA — rule sets: the T8 parameter object, and what a structure buys.

A rule set was always `P` in the register — versioned, digested, approved by a
second person. It was also an arbitrary JSON blob, so the platform could tell
you it had changed and not one thing about what it said.

These tests are mostly about the three questions a structure makes answerable
and a blob does not: can this rule ever fire, do these two rules disagree, and
does every input have an outcome.
"""
from __future__ import annotations

import pytest

from core.rules import Condition, RuleSet, RuleSetEditor
from core.rules.common import RuleError
from core.rules.domains import covers, satisfiable

URN = "maya://model/credit.pd.smallbiz"
SCHEMA = {"ltv": "numeric", "dti": "numeric", "product": "categorical",
          "arrears": "integer"}
OUT = {"decision": "string"}


def rule(rule_id, when, then=None, because="policy CP-2024-11"):
    return {"id": rule_id, "when": when, "then": then or {"decision": "refer"},
            "because": because}


def doc(*rules, otherwise=None, note=""):
    return {"rules": list(rules), "otherwise": otherwise or {"decision": "accept"},
            "note": note}


# ===================================================================== atoms
class TestAConditionIsStructuredNotWritten:
    """Deliberately not the expression language `core/features/expressions.py`
    provides. A free expression is opaque to analysis, and the analysis is the
    entire reason a rule set is worth holding in a governance platform."""

    def test_a_condition_reads_back_in_english(self):
        c = Condition.parse({"all": [
            {"field": "ltv", "op": "gt", "value": 0.8},
            {"any": [{"field": "product", "op": "in", "value": ["BTL", "SECOND"]},
                     {"field": "dti", "op": "between", "value": [0.4, 0.6]}]}]})
        assert c.describe() == (
            "ltv is greater than 0.8 and (product is one of [BTL, SECOND] "
            "or dti is between 0.4 and 0.6)")

    def test_the_english_brackets_nested_groups(self):
        """'a and b or c' has two readings and a reviewer gets no warning."""
        c = Condition.parse({"any": [{"all": [{"field": "ltv", "op": "gt", "value": 0.8},
                                              {"field": "dti", "op": "gt", "value": 0.4}]},
                                     {"field": "arrears", "op": "ge", "value": 1}]})
        assert c.describe().startswith("(")

    def test_a_field_the_model_does_not_declare_is_refused(self):
        """Otherwise the rule silently never fires, which is the worst of the
        three outcomes available."""
        c = Condition.parse({"field": "income", "op": "gt", "value": 50000})
        with pytest.raises(RuleError, match="does not declare"):
            c.conforms(SCHEMA)

    def test_an_ordered_comparison_on_a_categorical_field_is_refused(self):
        """`product_code > 'MTG'` has an answer in every programming language
        and no meaning in any bank."""
        c = Condition.parse({"field": "product", "op": "gt", "value": "MTG"})
        with pytest.raises(RuleError, match="has no order"):
            c.conforms(SCHEMA)

    def test_a_value_on_a_nullary_operator_is_refused_not_ignored(self):
        """A value the platform silently dropped would make the rule mean
        something other than its author reads back."""
        with pytest.raises(RuleError, match="value_not_expected|carries a value"):
            Condition.parse({"field": "dti", "op": "is_null", "value": 3})

    def test_an_inverted_range_is_refused_at_parse(self):
        with pytest.raises(RuleError, match="empty range"):
            Condition.parse({"field": "ltv", "op": "between", "value": [0.9, 0.5]})

    @pytest.mark.parametrize("bad", [
        {"field": "ltv", "op": "gt", "value": 0.5, "all": []},
        {"all": [], },
        {"any": []},
        {"all": [{"field": "ltv", "op": "gt", "value": 0.5}],
         "any": [{"field": "dti", "op": "gt", "value": 0.4}]},
        {"field": "ltv", "op": "roughly", "value": 0.5},
        {"field": "ltv", "op": "gt"},
    ])
    def test_malformed_conditions_are_refused(self, bad):
        with pytest.raises(RuleError):
            Condition.parse(bad)

    def test_missing_is_not_false_it_is_missing(self):
        """A rule reading a field nobody supplied does not fire on a coerced
        default; `otherwise` catches it, and `otherwise` is where somebody wrote
        down what to do when the data is not there."""
        c = Condition.parse({"field": "dti", "op": "gt", "value": 0.4})
        assert c.holds({"dti": 0.5}) is True
        assert c.holds({"dti": None}) is False
        assert c.holds({}) is False
        assert Condition.parse({"field": "dti", "op": "is_null"}).holds({}) is True

    def test_a_type_mismatch_at_evaluation_refuses_rather_than_guesses(self):
        """Python would compare two strings lexically and return something
        plausible. That is a refusal, not a rule outcome."""
        c = Condition.parse({"field": "ltv", "op": "gt", "value": 0.8})
        with pytest.raises(RuleError, match="not_comparable|arrived as"):
            c.holds({"ltv": "high"})

    def test_parsing_round_trips(self):
        """The digest is taken over the parsed form, so two documents differing
        only in key order are one rule set rather than two."""
        raw = {"all": [{"op": "gt", "field": "ltv", "value": 0.8},
                       {"field": "arrears", "op": "ge", "value": 1}]}
        once = Condition.parse(raw).as_dict()
        assert Condition.parse(once).as_dict() == once


# ================================================================== analysis
class TestCanThisRuleEverFire:
    """The question a spreadsheet cannot answer, and the reason rule sets belong
    in a governance platform."""

    @staticmethod
    def _c(raw):
        return Condition.parse(raw)

    def test_a_self_contradictory_condition_is_unsatisfiable(self):
        assert not satisfiable(self._c({"all": [
            {"field": "ltv", "op": "gt", "value": 0.9},
            {"field": "ltv", "op": "lt", "value": 0.5}]}))

    def test_an_ordinary_condition_is_satisfiable(self):
        assert satisfiable(self._c({"field": "ltv", "op": "gt", "value": 0.5}))

    def test_an_equality_against_an_excluded_value_is_unsatisfiable(self):
        assert not satisfiable(self._c({"all": [
            {"field": "product", "op": "eq", "value": "BTL"},
            {"field": "product", "op": "ne", "value": "BTL"}]}))

    def test_a_wider_condition_covers_a_narrower_one(self):
        assert covers(self._c({"field": "ltv", "op": "gt", "value": 0.5}),
                      self._c({"field": "ltv", "op": "gt", "value": 0.8}))

    def test_a_narrower_condition_does_not_cover_a_wider_one(self):
        assert not covers(self._c({"field": "ltv", "op": "gt", "value": 0.8}),
                          self._c({"field": "ltv", "op": "gt", "value": 0.5}))

    def test_membership_covers_equality_to_a_member(self):
        assert covers(self._c({"field": "product", "op": "in",
                               "value": ["BTL", "SECOND"]}),
                      self._c({"field": "product", "op": "eq", "value": "BTL"}))

    def test_adding_a_conjunct_narrows(self):
        wide = self._c({"field": "ltv", "op": "gt", "value": 0.5})
        narrow = self._c({"all": [{"field": "ltv", "op": "gt", "value": 0.8},
                                  {"field": "product", "op": "eq", "value": "BTL"}]})
        assert covers(wide, narrow) and not covers(narrow, wide)

    def test_the_analysis_is_sound_where_it_is_incomplete(self):
        """Two earlier rules that between them cover a third are NOT detected —
        `ltv > 0.8` and `ltv <= 0.8` cover everything, and a third rule after
        them is unreachable.

        This asserts the limitation rather than hiding it. Full coverage is
        satisfiability over the theory, which is a solver, and a solver in a
        governance platform is a dependency whose failure modes nobody in the
        bank can debug. What the platform promises is exactly *"no rule is
        shadowed by any single earlier rule"*, and it says that rather than
        "no rule is unreachable".
        """
        high = self._c({"field": "ltv", "op": "gt", "value": 0.8})
        low = self._c({"field": "ltv", "op": "le", "value": 0.8})
        anything = self._c({"field": "ltv", "op": "ge", "value": 0.0})
        assert not covers(high, anything) and not covers(low, anything)


# ================================================================== rule sets
class TestARuleSetIsCheckedBeforeItIsHeld:

    def test_a_valid_set_reports_what_it_reads(self):
        rs = RuleSet.parse(doc(
            rule("btl", {"all": [{"field": "product", "op": "eq", "value": "BTL"},
                                 {"field": "ltv", "op": "gt", "value": 0.75}]}),
            rule("high", {"field": "ltv", "op": "gt", "value": 0.95},
                 {"decision": "decline"})))
        report = rs.validate(SCHEMA, OUT)
        assert report["rules"] == 2
        assert report["fields"] == ["ltv", "product"]
        assert not report["shadowed"] and not report["contradictions"]

    def test_a_rule_an_earlier_rule_covers_is_refused(self):
        """A rule that never fires still appears in the model card and in every
        committee paper, and nobody reading either can tell."""
        with pytest.raises(RuleError, match="can never fire") as exc:
            RuleSet.parse(doc(
                rule("wide", {"field": "ltv", "op": "gt", "value": 0.5}),
                rule("narrow", {"field": "ltv", "op": "gt", "value": 0.8},
                     {"decision": "decline"}))).validate(SCHEMA, OUT)
        assert exc.value.code == "rule_unreachable"
        assert "wide" in exc.value.detail and "narrow" in exc.value.detail

    def test_the_same_rules_correctly_ordered_are_accepted(self):
        """A check that refuses everything is not a check."""
        RuleSet.parse(doc(
            rule("narrow", {"field": "ltv", "op": "gt", "value": 0.8},
                 {"decision": "decline"}),
            rule("wide", {"field": "ltv", "op": "gt", "value": 0.5}))
        ).validate(SCHEMA, OUT)

    def test_two_rules_that_disagree_are_reported_as_a_disagreement(self):
        """Identical conditions are also a shadowing, so reporting shadowing
        first made `rules_contradict` unreachable — in the checker written to
        find unreachable rules. The messages point somewhere different: the
        ordering is not the mistake, the policy is."""
        with pytest.raises(RuleError) as exc:
            RuleSet.parse(doc(
                rule("a", {"field": "ltv", "op": "gt", "value": 0.9},
                     {"decision": "decline"}),
                rule("b", {"field": "ltv", "op": "gt", "value": 0.9},
                     {"decision": "accept"}))).validate(SCHEMA, OUT)
        assert exc.value.code == "rules_contradict"

    def test_two_identical_rules_are_a_duplicate_not_a_disagreement(self):
        with pytest.raises(RuleError) as exc:
            RuleSet.parse(doc(
                rule("a", {"field": "ltv", "op": "gt", "value": 0.9},
                     {"decision": "decline"}),
                rule("b", {"field": "ltv", "op": "gt", "value": 0.9},
                     {"decision": "decline"}))).validate(SCHEMA, OUT)
        assert exc.value.code == "rule_unreachable"

    def test_a_rule_no_input_satisfies_is_refused(self):
        with pytest.raises(RuleError, match="no input can satisfy"):
            RuleSet.parse(doc(rule("nope", {"all": [
                {"field": "ltv", "op": "gt", "value": 0.9},
                {"field": "ltv", "op": "lt", "value": 0.5}]}))).validate(SCHEMA, OUT)

    def test_otherwise_is_required(self):
        """Totality by construction. A rule set without one behaves by accident
        on exactly the cases its author did not think of."""
        with pytest.raises(RuleError, match="otherwise") as exc:
            RuleSet.parse({"rules": [rule("a", {"field": "ltv", "op": "gt",
                                                "value": 0.9})]})
        assert exc.value.code == "otherwise_required"

    def test_a_rule_must_say_why_it_exists(self):
        """The field an author will most want to skip, and the one that makes
        the difference between a rule set and a stored procedure."""
        with pytest.raises(RuleError, match="does not say why") as exc:
            RuleSet.parse({"rules": [{"id": "a", "then": {"decision": "refer"},
                                      "when": {"field": "ltv", "op": "gt",
                                               "value": 0.9}}],
                           "otherwise": {"decision": "accept"}})
        assert exc.value.code == "reason_required"

    def test_an_outcome_field_the_model_does_not_declare_is_refused(self):
        with pytest.raises(RuleError, match="output schema does not declare"):
            RuleSet.parse(doc(rule("a", {"field": "ltv", "op": "gt", "value": 0.9},
                                   {"verdict": "decline"}))).validate(SCHEMA, OUT)

    def test_the_otherwise_is_checked_too(self):
        with pytest.raises(RuleError, match="otherwise sets"):
            RuleSet.parse(doc(rule("a", {"field": "ltv", "op": "gt", "value": 0.9}),
                              otherwise={"verdict": "accept"})).validate(SCHEMA, OUT)

    def test_duplicate_ids_are_refused(self):
        with pytest.raises(RuleError, match="two rules are called"):
            RuleSet.parse(doc(rule("a", {"field": "ltv", "op": "gt", "value": 0.9}),
                              rule("a", {"field": "dti", "op": "gt", "value": 0.4})))


class TestFirstMatchWins:

    @pytest.fixture
    def rs(self):
        return RuleSet.parse(doc(
            rule("btl", {"all": [{"field": "product", "op": "eq", "value": "BTL"},
                                 {"field": "ltv", "op": "gt", "value": 0.75}]},
                 {"decision": "refer"}, "BTL above 75% LTV is outside appetite"),
            rule("high", {"field": "ltv", "op": "gt", "value": 0.95},
                 {"decision": "decline"}, "Above 95% needs a capital add-on")))

    def test_the_first_matching_rule_decides(self, rs):
        assert rs.decide({"product": "BTL", "ltv": 0.99})["decision"] == "refer"

    def test_a_later_rule_decides_when_the_earlier_does_not_match(self, rs):
        assert rs.decide({"product": "RESI", "ltv": 0.99})["decision"] == "decline"

    def test_the_otherwise_decides_when_nothing_matches(self, rs):
        out = rs.decide({"product": "RESI", "ltv": 0.5})
        assert out["decision"] == "accept" and out["matched_rule"] is None

    def test_the_decision_names_the_rule_and_its_reason(self, rs):
        """A decision a bank cannot attribute to a rule is one it cannot explain
        to the person it refused, and under most consumer-credit regimes the
        explanation is the obligation rather than the decision."""
        out = rs.decide({"product": "BTL", "ltv": 0.8})
        assert out["matched_rule"] == "btl"
        assert "outside appetite" in out["because"]

    def test_the_canonical_form_ignores_formatting_and_keeps_order(self, rs):
        """Reformatting a document must not produce a new parameter set;
        reordering the rules must, because order is meaning."""
        reordered = RuleSet.parse(doc(*reversed(rs.canonical()["rules"]),
                                      otherwise=rs.otherwise))
        assert reordered.canonical() != rs.canonical()
        assert RuleSet.parse(rs.canonical()).canonical() == rs.canonical()


# ==================================================================== editor
@pytest.fixture
def t8(registry):
    """A T8 model: parameter_kind rule_set, fit_procedure author."""
    registry.register(URN, "SB eligibility", "credit", "retail",
                      "person/j.okafor", "LE-US-01", "origination eligibility")
    registry.create_version(URN, "1.0.0", {
        "parameter_kind": "rule_set", "fit_procedure": "author",
        "runtime": "rules", "entry": {"ruleset": "eligibility", "engine": "maya"},
        "input_schema": [{"name": n, "dtype": d} for n, d in SCHEMA.items()],
        "output_schema": [{"name": "decision", "dtype": "string"}]})
    return registry.version(URN, "1.0.0")


@pytest.fixture
def editor(registry, parameters, evidence):
    return RuleSetEditor(registry, parameters, evidence)


VALID = doc(rule("btl", {"all": [{"field": "product", "op": "eq", "value": "BTL"},
                                 {"field": "ltv", "op": "gt", "value": 0.75}]},
                 because="BTL above 75% LTV is outside appetite (CP-2024-11)"),
            rule("high", {"field": "ltv", "op": "gt", "value": 0.95},
                 {"decision": "decline"}))


class TestTheEditorEditsAGovernedObject:
    """MAYA does not become the authoring tool; it becomes an editor for a
    parameter set it already held. Publishing adds no authority — it is
    `parameters.record` with a validated document."""

    def test_the_version_derives_t8(self, t8):
        assert t8["trainability_class"] == "T8"

    def test_check_returns_the_english_form(self, editor, t8):
        report = editor.check(URN, "1.0.0", VALID)
        assert report["rules"] == 2
        assert any("BTL" in line for line in report["explanation"])

    def test_check_records_nothing(self, editor, t8, parameters):
        editor.check(URN, "1.0.0", VALID)
        assert parameters.for_version(URN, "1.0.0") == []

    def test_a_trial_reports_which_rules_never_fired(self, editor, t8):
        """Not necessarily wrong, but a set where most rules fire on no
        realistic input is one somebody should look at before approving it."""
        report = editor.trial(URN, "1.0.0", VALID, [
            {"product": "RESI", "ltv": 0.5},
            {"product": "RESI", "ltv": 0.6}])
        assert report["never_fired"] == ["btl", "high"]
        assert report["fell_through"] == 2

    def test_a_trial_row_that_cannot_be_decided_is_reported_not_raised(
            self, editor, t8):
        """One bad sample must not hide what the other nineteen would show."""
        report = editor.trial(URN, "1.0.0", VALID, [
            {"product": "BTL", "ltv": "high"},
            {"product": "RESI", "ltv": 0.99}])
        assert report["outcomes"][0]["refused"] == "value_not_comparable"
        assert report["outcomes"][1]["decision"] == "decline"

    def test_publishing_lands_proposed_like_any_parameter_set(self, editor, t8):
        row = editor.publish(URN, "1.0.0", "eligibility-q1", VALID,
                             actor="person/d.raman")
        assert row["state"] == "proposed"
        assert row["kind"] == "rule_set" and row["provenance"] == "declared"

    def test_the_author_cannot_approve_their_own_rules(self, editor, t8,
                                                       parameters):
        """No new authority means no new exemption: the rule that a parameter
        set is approved by somebody other than its author applies here
        unchanged, because this *is* that mechanism."""
        row = editor.publish(URN, "1.0.0", "eligibility-q1", VALID,
                             actor="person/d.raman")
        with pytest.raises(Exception) as exc:
            parameters.approve(row["id"], "person/d.raman")
        assert exc.value.code == "self_approval"

    def test_an_invalid_set_is_never_recorded(self, editor, t8, parameters):
        shadowed = doc(rule("wide", {"field": "ltv", "op": "gt", "value": 0.5}),
                       rule("narrow", {"field": "ltv", "op": "gt", "value": 0.8}))
        with pytest.raises(RuleError, match="can never fire"):
            editor.publish(URN, "1.0.0", "bad", shadowed)
        assert parameters.for_version(URN, "1.0.0") == []

    def test_the_diagnostics_travel_with_the_set(self, editor, t8):
        row = editor.publish(URN, "1.0.0", "eligibility-q1", VALID)
        assert row["diagnostics"]["rules"] == 2
        assert row["diagnostics"]["reads"] == ["ltv", "product"]

    def test_explain_renders_an_approved_set_once(self, editor, t8):
        """One rendering, so the model card, the committee paper and the export
        pack quote the same sentences."""
        row = editor.publish(URN, "1.0.0", "eligibility-q1", VALID)
        out = editor.explain(row["id"])
        assert out["rules"] == 2 and out["reads"] == ["ltv", "product"]
        assert out["explanation"][-1].startswith("otherwise")

    def test_a_model_whose_p_is_not_a_rule_set_is_refused(self, editor, registry):
        registry.register("maya://model/x.y", "X", "credit", "retail",
                          "person/o", "LE-US-01", "p")
        registry.create_version("maya://model/x.y", "1.0.0",
                                {"parameter_kind": "estimated_coefficients",
                                 "fit_procedure": "estimate"})
        with pytest.raises(RuleError, match="not a rule set"):
            editor.check("maya://model/x.y", "1.0.0", VALID)


# ================================================== the runtime, end to end
class TestARuleSetCanActuallyBeRun:
    """The grammar has named the `rules` runtime since the first milestone and
    no engine implemented it — so a rule set could be registered, versioned,
    approved and attested, and still be *scored* by whatever stored procedure
    the bank was already using. The governed artefact and the executing artefact
    were two documents nobody compared, which is the arrangement this platform
    exists to end.
    """

    @pytest.fixture
    def running(self, registry, parameters, evidence, warrants, t8, editor):
        from core.execution import CaptiveEngine
        # The application wires this (`run_maya_web.py`: `warrants.parameters =
        # parameters`) and the shared fixture does not, so without it every
        # register-held parameter object resolves to nothing and the warrant is
        # refused `no_approved_parameters`.
        warrants.parameters = parameters
        row = editor.publish(URN, "1.0.0", "eligibility-q1", VALID,
                             actor="person/d.raman")
        parameters.approve(row["id"], "person/a.mehta")
        registry.approve_version(URN, "1.0.0")
        registry.move_alias(URN, "prod", "champion", "1.0.0")
        warrants.issue(f"{URN}#champion", "prod", "svc/origination",
                       "origination_decision")
        return CaptiveEngine(warrants, parameters=parameters)

    def _run(self, engine, **inputs):
        return engine.execute(f"{URN}#champion", "prod", "svc/origination",
                              "origination_decision", inputs)

    def test_the_rules_run_at_the_point_of_p_that_was_approved(self, running):
        result = self._run(running, product="BTL", ltv=0.8)
        assert result.prediction["decision"] == "refer"

    def test_the_decision_names_the_rule_that_made_it(self, running):
        """It travels even when the output schema does not declare it: a bank
        that cannot attribute a refusal to a rule cannot explain it to the
        person refused, and the explanation is usually the obligation."""
        result = self._run(running, product="BTL", ltv=0.8)
        assert result.prediction["matched_rule"] == "btl"
        assert "appetite" in result.prediction["because"]

    def test_the_otherwise_is_reached_and_says_so(self, running):
        result = self._run(running, product="RESI", ltv=0.5)
        assert result.prediction["decision"] == "accept"
        assert result.prediction["matched_rule"] is None

    def test_the_engine_offers_the_runtime_the_grammar_names(self, running):
        assert "rules" in running.runtimes.keys()

    def test_the_engine_implements_the_number_its_docstring_claims(self, running):
        """This said "three real runtimes" while five were registered — the
        code's own account of itself, wrong, and checked by nobody."""
        import re
        from core.execution.engine import CaptiveEngine
        claimed = re.search(r"with (\w+) real runtimes", CaptiveEngine.__doc__)
        words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
        distinct = {id(running.runtimes.get(k)) for k in running.runtimes.keys()}
        assert words[claimed.group(1)] == len(distinct)


# ====================================================================== API
class TestTheEditorApi:
    """`check` and `trial` carry no authority and record nothing, so an author
    iterates without touching the register. `publish` is the ordinary
    `parameter:record` act. That split is the design."""

    RULES_URN = "maya://model/credit.eligibility.retail"

    @pytest.fixture
    def rules_model(self, client, people):
        # Asserted, not fired and forgotten: a fixture that swallows its own
        # setup failure makes every test in the class fail somewhere else.
        made = client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": self.RULES_URN, "name": "Retail eligibility",
            "model_class": "credit",
            "domain": "retail", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "origination"})
        assert made.status_code == 201, made.text
        versioned = client.post("/api/v1/models/credit.eligibility.retail/versions",
                    auth=people["d.raman"], json={
                        "semver": "1.0.0",
                        "kernel": {"parameter_kind": "rule_set",
                                   "fit_procedure": "author", "runtime": "rules",
                                   "entry": {"ruleset": "e", "engine": "maya"},
                                   "input_schema": [{"name": n, "dtype": d}
                                                    for n, d in SCHEMA.items()],
                                   "output_schema": [{"name": "decision",
                                                      "dtype": "string"}]}})
        assert versioned.status_code == 201, versioned.text
        return client

    @property
    def BODY(self):
        return {"urn": self.RULES_URN, "semver": "1.0.0", "document": VALID}

    def test_the_vocabulary_comes_from_the_code(self, client, people):
        """A screen holding its own operator list is a second vocabulary that
        drifts from the first."""
        v = client.get("/api/v1/rulesets/vocabulary",
                       auth=people["d.raman"]).json()
        assert {o["op"] for o in v["operators"]} >= {"eq", "between", "in"}
        assert any(o["needs_ordered_field"] for o in v["operators"])

    def test_check_returns_the_english_form(self, rules_model, people):
        r = rules_model.post("/api/v1/rulesets/check", auth=people["d.raman"],
                            json=self.BODY)
        assert r.status_code == 200
        assert any("BTL" in line for line in r.json()["explanation"])

    def test_an_unreachable_rule_is_refused_with_both_names(self, rules_model,
                                                            people):
        bad = doc(rule("wide", {"field": "ltv", "op": "gt", "value": 0.5}),
                  rule("narrow", {"field": "ltv", "op": "gt", "value": 0.8}))
        r = rules_model.post("/api/v1/rulesets/check", auth=people["d.raman"],
                             json={**self.BODY, "document": bad})
        assert r.status_code == 422
        assert r.json()["error"] == "rule_unreachable"
        assert "wide" in r.json()["detail"] and "narrow" in r.json()["detail"]

    def test_a_trial_reports_coverage(self, rules_model, people):
        r = rules_model.post("/api/v1/rulesets/trial", auth=people["d.raman"],
                            json={**self.BODY,
                                  "rows": [{"product": "BTL", "ltv": 0.8},
                                           {"product": "RESI", "ltv": 0.5}]})
        assert r.status_code == 200
        assert r.json()["fired"]["btl"] == 1
        assert r.json()["never_fired"] == ["high"]

    def test_publishing_creates_a_proposed_parameter_set(self, rules_model,
                                                         people):
        r = rules_model.post("/api/v1/rulesets", auth=people["d.raman"],
                            json={**self.BODY, "name": "eligibility-q1"})
        assert r.status_code == 201
        assert r.json()["state"] == "proposed" and r.json()["kind"] == "rule_set"

    def test_explain_reads_it_back(self, rules_model, people):
        created = rules_model.post("/api/v1/rulesets", auth=people["d.raman"],
                                   json={**self.BODY, "name": "eligibility-q1"})
        r = rules_model.get(f"/api/v1/rulesets/{created.json()['id']}",
                           auth=people["d.raman"])
        assert r.status_code == 200 and r.json()["rules"] == 2

    def test_checking_needs_only_read(self, rules_model, people):
        """Requiring the recording permission to *look* at whether a draft is
        valid would push authors to skip the step."""
        r = rules_model.post("/api/v1/rulesets/check", auth=people["a.mehta"],
                             json=self.BODY)
        assert r.status_code == 200

    def test_publishing_needs_more_than_read(self, rules_model, people):
        """A validator may read a draft and check it; recording one against the
        model they will later review is not theirs to do."""
        r = rules_model.post("/api/v1/rulesets", auth=people["a.mehta"],
                             json={**self.BODY, "name": "sneaky"})
        assert r.status_code == 403


# ================================================================== the pages
class TestTheEditorPages:
    """The screen decides nothing. Every question about whether a rule set is
    valid is answered by `POST /rulesets/check`; a client that re-implemented
    any of it would be a second implementation of a governance rule, and a
    second implementation disagrees with the first eventually, in the direction
    of permitting more."""

    SLUG = "credit.eligibility.retail"

    @pytest.fixture
    def signed_in(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": f"maya://model/{self.SLUG}", "name": "Retail eligibility",
            "model_class": "credit", "domain": "retail",
            "owner": "person/j.okafor", "legal_entity": "LE-US-01",
            "purpose": "origination"})
        client.post(f"/api/v1/models/{self.SLUG}/versions", auth=people["d.raman"],
                    json={"semver": "1.0.0",
                          "kernel": {"parameter_kind": "rule_set",
                                     "fit_procedure": "author", "runtime": "rules",
                                     "entry": {"ruleset": "e", "engine": "maya"},
                                     "input_schema": [{"name": n, "dtype": d}
                                                      for n, d in SCHEMA.items()],
                                     "output_schema": [{"name": "decision",
                                                        "dtype": "string"}]}})
        # Published BEFORE signing in. Once the client holds a session cookie
        # its authority is ambient, and the CSRF guard correctly refuses a
        # state-changing request that carries no token — which is the control
        # working, not a test problem.
        created = client.post("/api/v1/rulesets", auth=people["d.raman"],
                              json={"urn": f"maya://model/{self.SLUG}",
                                    "semver": "1.0.0", "document": VALID,
                                    "name": "eligibility-q1"})
        assert created.status_code == 201, created.text
        client.post("/login", data={"username": "d.raman", "password": "dev-pw"},
                    follow_redirects=False)
        client.recorded_ruleset = created.json()["id"]
        return client

    def test_the_editor_renders_for_a_t8_version(self, signed_in):
        r = signed_in.get(f"/rules/{self.SLUG}/1.0.0")
        assert r.status_code == 200
        assert "first match wins" in r.text
        assert "ruleset-editor.js" in r.text

    def test_it_carries_the_vocabulary_and_the_schema(self, signed_in):
        """From the code, so a screen cannot hold a second operator list that
        drifts from the first."""
        r = signed_in.get(f"/rules/{self.SLUG}/1.0.0")
        assert "MAYA_RULES" in r.text
        assert "not supplied" in r.text                      # is_null's meaning
        assert "product" in r.text and "ltv" in r.text

    def test_a_version_that_is_not_registered_is_a_404(self, signed_in):
        assert signed_in.get(f"/rules/{self.SLUG}/9.9.9").status_code == 404

    def test_every_asset_is_local(self, signed_in):
        """No CDN, everything vendored — asserted rather than intended."""
        import re
        r = signed_in.get(f"/rules/{self.SLUG}/1.0.0")
        external = [u for u in re.findall(r'(?:src|href)="([^"]+)"', r.text)
                    if u.startswith(("http", "//"))]
        assert not external, external

    def test_a_recorded_set_reads_back_on_its_own_page(self, signed_in):
        r = signed_in.get(f"/rulesets/{signed_in.recorded_ruleset}")
        assert r.status_code == 200
        assert "BTL" in r.text and "otherwise" in r.text

    def test_the_page_states_what_no_shadowing_actually_means(self, signed_in):
        """The narrow promise, stated narrowly: no rule is covered by any
        *single* earlier rule. A page claiming more than the analysis delivers
        is the thing the analysis exists to find."""
        r = signed_in.get(f"/rulesets/{signed_in.recorded_ruleset}")
        assert "single" in r.text and "solver" in r.text


class TestTheDoorConformanceWasNotWatching:
    """`conforms` checked that a field is declared, and that an ordered operator
    is not asked of a field with no order. It never checked the *value*.

    So `{"field": "ltv", "op": "eq", "value": "high"}` on a numeric `ltv` passed
    every check clean — field declared, operator innocent, condition satisfiable
    in the abstract, nothing shadowing it — and could never fire, because no
    number is ever equal to a string.

    That is the exact outcome the conformance check exists to prevent, reached
    through the one door it was not watching. The ordered operators were checked
    because the *operator* looked suspicious; `eq` looked innocent.
    """

    @staticmethod
    def _validate(when, schema):
        return RuleSet.parse(doc(rule("r", when, {"decision": "decline"}))
                             ).validate(schema, OUT)

    @pytest.mark.parametrize("when,schema", [
        ({"field": "ltv", "op": "eq", "value": "high"}, {"ltv": "numeric"}),
        ({"field": "ltv", "op": "ne", "value": "high"}, {"ltv": "numeric"}),
        ({"field": "ltv", "op": "in", "value": ["high", "low"]}, {"ltv": "numeric"}),
        ({"field": "ltv", "op": "between", "value": ["a", "b"]}, {"ltv": "float"}),
        ({"field": "product", "op": "eq", "value": 3}, {"product": "categorical"}),
        ({"field": "product", "op": "in", "value": ["BTL", 7]}, {"product": "string"}),
    ])
    def test_a_comparison_that_can_never_be_true_is_refused(self, when, schema):
        with pytest.raises(RuleError, match="would never fire") as exc:
            self._validate(when, schema)
        assert exc.value.code == "value_wrong_type"

    @pytest.mark.parametrize("when,schema", [
        ({"field": "ltv", "op": "eq", "value": 0.8}, {"ltv": "numeric"}),
        ({"field": "arrears", "op": "ge", "value": 1}, {"arrears": "integer"}),
        ({"field": "product", "op": "in", "value": ["BTL"]}, {"product": "categorical"}),
        ({"field": "ltv", "op": "is_null"}, {"ltv": "numeric"}),
    ])
    def test_an_ordinary_comparison_is_admitted(self, when, schema):
        self._validate(when, schema)

    @pytest.mark.parametrize("when,schema", [
        # An epoch in some registers, an ISO string in others. Refusing either
        # spelling would refuse correct rules.
        ({"field": "opened", "op": "eq", "value": "2026-01-01"}, {"opened": "date"}),
        ({"field": "opened", "op": "eq", "value": 1767225600}, {"opened": "date"}),
        # Somebody's own dtype. The platform has no basis for an opinion.
        ({"field": "x", "op": "eq", "value": "anything"}, {"x": "widget"}),
    ])
    def test_it_declines_to_judge_what_it_cannot_be_sure_of(self, when, schema):
        """A conformance check that produces false refusals is one somebody
        turns off, and the real refusals go with it."""
        self._validate(when, schema)

    def test_a_boolean_is_not_a_number_here(self):
        """`bool` subclasses `int` in Python, so `True` would slip through a
        plain isinstance check — and this platform uses 0/1 rather than booleans
        everywhere by rule, so a `True` in a rule set is a mistake."""
        with pytest.raises(RuleError, match="would never fire"):
            self._validate({"field": "ltv", "op": "eq", "value": True},
                           {"ltv": "numeric"})


class TestTheRegisterShowsHowBigAPolicyIs:
    """`cardinality` answers *how big is this parameter object*, and the register
    shows it — "12 values" on the model page and the parameter page.

    A rule-set document has three top-level keys (`rules`, `otherwise`, `note`)
    whatever it holds, so a forty-rule lending policy and a one-rule one both
    reported **3 values**. No refusal, no wrong digest — just a number displayed
    beside a governed object that measured nothing, which is worse than showing
    no number, because a reader cannot tell.
    """

    def test_a_rule_set_is_measured_in_rules(self, editor, t8):
        row = editor.publish(URN, "1.0.0", "eligibility-q1", VALID)
        assert row["cardinality"] == len(VALID["rules"]) == 2

    def test_a_larger_policy_reports_a_larger_number(self, editor, t8):
        many = doc(*[rule(f"r{i}", {"field": "ltv", "op": "eq", "value": i / 100},
                          {"decision": "refer"}) for i in range(1, 12)])
        row = editor.publish(URN, "1.0.0", "big", many)
        assert row["cardinality"] == 11

    def test_a_record_of_numbers_is_still_measured_in_keys(self, parameters,
                                                           registry, a_model):
        """The change must not have moved the meaning for everything else."""
        registry.create_version(URN, "2.0.0", {
            "parameter_kind": "estimated_coefficients", "fit_procedure": "estimate"})
        row = parameters.record(URN, "2.0.0", "coeffs", "estimated_coefficients",
                                {"a": 1.0, "b": 2.0, "c": 3.0},
                                provenance="declared")
        assert row["cardinality"] == 3


class TestTheUnionOfEarlierRulesIsNowChecked:
    """The stated limit, removed — and removed without a solver.

    The promise was written narrowly on purpose: *no rule is shadowed by any
    single earlier rule*. Two earlier rules that between them cover a third —
    `ltv > 0.8` and `ltv <= 0.8` covering everything after them — were not
    detected, and `domains.py` said why: full coverage is satisfiability over
    the theory, "decidable here but a solver, and a solver inside a governance
    platform is a dependency whose failure modes nobody in the bank can debug".

    The premise was right and the conclusion did not follow. A conjunction in
    this analysis is already a **box** — one interval-with-exclusions per field
    — and a condition is a finite union of boxes. "Is this box covered by those
    boxes" is geometry, answered exactly by subtraction. No solver, no
    dependency, and an exact answer rather than a conservative one.
    """

    @staticmethod
    def _at(field, op, value):
        from core.rules.conditions import Condition
        return Condition.parse({"field": field, "op": op, "value": value})

    def test_the_example_the_documentation_named(self):
        from core.rules.domains import covers, union_covers
        above = self._at("ltv", "gt", 0.8)
        below = self._at("ltv", "le", 0.8)
        anything = self._at("ltv", "ge", -1e9)

        assert not covers(above, anything), "one rule alone should not cover it"
        assert union_covers([above, below], anything), (
            "`ltv > 0.8` and `ltv <= 0.8` between them cover everything, and "
            "this is the case the old promise excluded by name")

    def test_a_real_gap_stays_a_gap(self):
        """Soundness is the property that matters most here: a check that cries
        wolf is a check somebody turns off, and the real ones go with it."""
        from core.rules.domains import union_covers
        assert not union_covers(
            [self._at("ltv", "gt", 0.8), self._at("ltv", "lt", 0.5)],
            self._at("ltv", "ge", -1e9)), "0.5 to 0.8 is uncovered"

    def test_one_rule_alone_is_not_enough(self):
        from core.rules.domains import union_covers
        assert not union_covers([self._at("ltv", "gt", 0.8)],
                                self._at("ltv", "ge", -1e9))

    def test_it_covers_a_subset(self):
        from core.rules.domains import union_covers
        assert union_covers(
            [self._at("ltv", "gt", 0.8), self._at("ltv", "le", 0.8)],
            self._at("ltv", "between", [0.1, 0.9]))

    def test_a_set_of_rules_covered_only_jointly_is_reported(self):
        """End to end, through the rule set rather than the geometry."""
        from core.rules import RuleSet
        from core.rules.common import RuleError

        with pytest.raises(RuleError) as exc:
            RuleSet.parse({
                "rules": [
                    {"id": "high", "when": {"field": "ltv", "op": "gt", "value": 0.8},
                     "then": {"action": "refer"}, "because": "high LTV"},
                    {"id": "rest", "when": {"field": "ltv", "op": "le", "value": 0.8},
                     "then": {"action": "accept"}, "because": "everything else"},
                    {"id": "never", "when": {"field": "ltv", "op": "ge", "value": 0.0},
                     "then": {"action": "review"}, "because": "cannot ever fire"},
                ],
                "otherwise": {"action": "refer"}}).validate(
                    {"ltv": "numeric"}, {"action": "string"})
        assert exc.value.code in ("rule_unreachable", "rule_never_fires")
        assert "never" in exc.value.detail

    def test_undecided_is_not_reported_as_no_problem_found(self):
        """The budget exists so the check terminates. Reaching it must report
        that the answer is unknown, not that there is nothing to report —
        which is the defect the whole module is written against."""
        import inspect

        from core.rules import ruleset
        source = inspect.getsource(ruleset.RuleSet._shadowed)
        assert "Undecided" in source and "undecided" in source
        assert "self.undecided.append" in source


class TestTheAnalysisAgreesWithTheEvaluator:
    """The domain analysis and `Condition.holds` must describe the same rule.

    They did not, on one point: `_atom_holds` returns False for every comparison
    when the field is absent, and `NOT` is `not holds(...)`, so
    `not (country eq "GB")` is TRUE on a row with no country. The DNF flipped
    that to the atom `country ne "GB"`, which is FALSE there — a region smaller
    than the rule's, and small in the direction that makes `covers` over-claim.

    A rule reported as shadowed is a rule an author deletes. In a screening set
    the rule this hid is the one for records arriving with no country.
    """

    def test_a_negated_equality_still_fires_where_the_field_is_absent(self):
        from core.rules.conditions import Condition
        from core.rules.domains import covers, union_covers

        later = Condition.parse(
            {"not": {"field": "country", "op": "eq", "value": "GB"}})
        earlier = Condition.parse(
            {"all": [{"field": "country", "op": "not_null"},
                     {"field": "country", "op": "ne", "value": "GB"}]})
        absent = {"amount": 100}
        assert later.holds(absent) and not earlier.holds(absent)
        assert not covers(earlier, later), \
            "the later rule fires on rows the earlier one misses"
        assert not union_covers([earlier], later)

    def test_the_null_branch_is_covered_when_it_really_is(self):
        """And it must still say yes when the earlier rules do reach the nulls,
        or the fix would be a check that never concludes anything."""
        from core.rules.conditions import Condition
        from core.rules.domains import union_covers

        later = Condition.parse(
            {"not": {"field": "country", "op": "eq", "value": "GB"}})
        earlier = [Condition.parse({"field": "country", "op": "is_null"}),
                   Condition.parse({"all": [{"field": "country", "op": "not_null"},
                                            {"field": "country", "op": "ne",
                                             "value": "GB"}]})]
        assert union_covers(earlier, later)

    def test_no_row_contradicts_the_analysis(self):
        """Exhaustive over a small world: every condition, every row.

        If `covers(a, b)` is True then no row may fire `b` without firing `a`.
        That is the whole soundness claim, checked rather than argued — the
        defect above survived a suite that only ever asked the analysis about
        rows where the field was present.
        """
        import itertools

        from core.rules.conditions import Condition
        from core.rules.domains import covers

        atoms = [
            {"field": "c", "op": "eq", "value": "GB"},
            {"field": "c", "op": "ne", "value": "GB"},
            {"field": "c", "op": "in", "value": ["GB", "US"]},
            {"field": "c", "op": "is_null"},
            {"field": "c", "op": "not_null"},
            {"field": "n", "op": "gt", "value": 5},
            {"field": "n", "op": "le", "value": 5},
        ]
        shapes = ([Condition.parse(a) for a in atoms]
                  + [Condition.parse({"not": a}) for a in atoms]
                  + [Condition.parse({"all": [a, b]})
                     for a, b in itertools.combinations(atoms, 2)]
                  + [Condition.parse({"any": [a, b]})
                     for a, b in itertools.combinations(atoms, 2)])
        # Rows including the two absences, which is where it went wrong.
        rows = [{}, {"c": None}, {"n": None}, {"c": "GB"}, {"c": "US"},
                {"c": "DE"}, {"n": 1}, {"n": 9}, {"c": "GB", "n": 1},
                {"c": "DE", "n": 9}, {"c": None, "n": 9}]

        broken = []
        for earlier in shapes:
            for later in shapes:
                if not covers(earlier, later):
                    continue
                for row in rows:
                    if later.holds(row) and not earlier.holds(row):
                        broken.append((earlier.describe(), later.describe(), row))
        assert not broken, (
            f"{len(broken)} unsound coverage claims, first three: {broken[:3]}")
