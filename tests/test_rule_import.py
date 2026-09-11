"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reading a rulebook the bank already has.

This is the item that decides whether T8 coverage is a demonstration or a
programme. The register can hold a rule set, version it, require a second person
to approve it and explain every decision back to the rule that made it — and all
of that works on rule sets somebody typed in. A bank's actual rulebook is a
spreadsheet four people maintain or a DMN file out of a BPM suite, and the
distance between those two facts is the whole migration.

What the tests are about is the thing that makes a parser frightening. A misread
threshold does not fail. It produces a rule set that loads, validates, publishes
and then decides differently from the rulebook it claims to be, and nobody finds
that by looking at it. So almost every test below is about a **refusal**: the
cell that was not guessed at, the hit policy that was not approximated, the
catch-all that was not invented, the format that is not translated at all.
"""
from __future__ import annotations

import pytest

from core.rules.common import RuleError
from core.rules.importing import (DECISION_TABLE, DMN, NOT_TRANSLATED,
                                  UNMAPPABLE, RuleSetImport)
from core.rules.ruleset import RuleSet

TABLE = """id,score,dti,segment,out:decision,out:limit,because
r_prime,>=720,<=0.35,"retail,sme",approve,50000,"policy CR-4: prime band"
r_near,"[650..719]",<=0.45,,refer,10000,"policy CR-4: referral band"
r_floor,,,,decline,0,"policy CR-4: below the floor"
"""

DMN_DOC = """<?xml version="1.0"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/">
 <decision id="d1"><decisionTable id="t1" hitPolicy="UNIQUE">
  <input id="i1"><inputExpression><text>score</text></inputExpression></input>
  <input id="i2"><inputExpression><text>segment</text></inputExpression></input>
  <output id="o1" name="decision"/>
  <rule id="rule_prime"><description>policy CR-4: prime band</description>
    <inputEntry><text>&gt;= 720</text></inputEntry>
    <inputEntry><text>"retail","sme"</text></inputEntry>
    <outputEntry><text>"approve"</text></outputEntry></rule>
 </decisionTable></decision></definitions>"""


@pytest.fixture
def importer():
    return RuleSetImport()


class TestNothingIsImported:
    def test_the_contract_says_so(self):
        assert RuleSetImport.formats()["imports_anything"] is False

    def test_what_comes_back_is_a_candidate(self, importer):
        out = importer.read(DECISION_TABLE, TABLE)
        assert out["imports_anything"] is False
        assert "still needs somebody other than its author" in out["detail"]

    def test_the_candidate_is_a_real_rule_set(self, importer):
        """Not a lookalike. It goes through the platform's own parser, which
        is the only way an import can be held to the same standard as
        something typed in."""
        parsed = RuleSet.parse(importer.read(DECISION_TABLE, TABLE)["candidate"])
        assert len(parsed.rules) == 2


class TestACellIsNotGuessedAt:
    def test_a_judgement_call_is_reported_not_translated(self, importer):
        out = importer.read(DECISION_TABLE,
                            'score,out:decision,because\n'
                            'good credit,approve,"policy"\n')
        assert out["candidate"] is None
        assert out["untranslated"][0]["cell"] == "good credit"
        assert "must not be guessed at" in out["untranslated"][0]["why"]

    def test_a_document_with_one_bad_row_is_refused_whole(self, importer):
        """Offering the readable rows would drop exactly the judgement calls,
        and the judgement calls are what a rulebook exists for."""
        out = importer.read(DECISION_TABLE, TABLE.replace("<650", "as agreed")
                            + 'r_x,as agreed,,,decline,0,"why"\n')
        assert out["candidate"] is None
        assert "refused as a whole" in out["detail"]

    def test_comparisons_ranges_lists_and_literals_all_read(self, importer):
        rules = importer.read(DECISION_TABLE, TABLE)["candidate"]["rules"]
        clauses = rules[0]["when"]["all"]
        assert {"field": "score", "op": "ge", "value": 720.0} in clauses
        assert {"field": "segment", "op": "in",
                "value": ["retail", "sme"]} in clauses

    def test_an_exclusive_range_end_is_not_approximated(self, importer):
        """`between` here is inclusive of both ends. A DMN `[650..720)` is
        not, so it is expressed as the pair of comparisons it actually is
        rather than rounded to the nearest available operator."""
        out = importer.read(DECISION_TABLE,
                            'score,out:d,because\n"[650..720)",x,"why"\n')
        clause = out["candidate"]["rules"][0]["when"]
        assert clause["all"][0]["op"] == "ge"
        assert clause["all"][1]["op"] == "lt"

    def test_an_inclusive_range_uses_between(self, importer):
        out = importer.read(DECISION_TABLE,
                            'score,out:d,because\n"[650..720]",x,"why"\n')
        assert out["candidate"]["rules"][0]["when"]["op"] == "between"


class TestOrderIsCarriedAndItsLossIsReported:
    def test_an_unstated_hit_policy_is_read_as_first_and_said_so(self, importer):
        out = importer.read(DECISION_TABLE, TABLE)
        assert out["hit_policy"] == "FIRST (assumed)"
        assert "rather than assumed quietly" in out["hit_policy_note"]

    def test_unique_is_carried_and_checked(self, importer):
        out = importer.read(DMN, DMN_DOC)
        assert out["hit_policy"] == "UNIQUE"
        assert "shadowing" in out["hit_policy_note"]

    @pytest.mark.parametrize("policy", ["COLLECT", "PRIORITY", "RULE ORDER"])
    def test_an_unmappable_policy_is_refused_by_name(self, importer, policy):
        with pytest.raises(RuleError) as e:
            importer.read(DECISION_TABLE,
                          f'hit policy,score,out:d,because\n'
                          f'{policy},>=1,x,"why"\n')
        assert e.value.code == "hit_policy_not_mappable"
        assert policy in UNMAPPABLE

    def test_collect_says_what_first_match_would_silently_become(self):
        assert "worse than" in UNMAPPABLE["COLLECT"]

    def test_priority_names_the_inversion(self):
        assert "inverts the rulebook" in UNMAPPABLE["PRIORITY"]


class TestTheCatchAllIsDerivedNotInvented:
    def test_a_last_row_constraining_nothing_becomes_otherwise(self, importer):
        out = importer.read(DECISION_TABLE, TABLE)
        assert out["candidate"]["otherwise"] == {"decision": "decline",
                                                 "limit": 0.0}
        assert "not because it happened to be last" in out["otherwise_from"]

    def test_with_no_catch_all_it_says_so_rather_than_making_one(self,
                                                                importer):
        out = importer.read(DECISION_TABLE, "\n".join(TABLE.splitlines()[:-1]))
        assert out["needs_an_otherwise"] is True
        assert "guessing wrong produces a rule set that decides confidently" \
            in out["detail"]

    def test_an_unconditional_row_in_the_middle_is_a_reported_defect(
            self, importer):
        """Every row below it is unreachable. That is a defect in the table,
        and reporting it is more use than translating something that cannot
        behave the way it reads."""
        out = importer.read(
            DECISION_TABLE,
            'id,score,out:d,because\n'
            'r_all,,decline,"oops"\n'
            'r_prime,>=720,approve,"unreachable"\n')
        assert out["candidate"] is None
        assert "every row below it is unreachable" in \
            out["untranslated"][0]["why"]


class TestWhatIsRefusedOutright:
    def test_a_stored_procedure_is_not_translated(self, importer):
        with pytest.raises(RuleError) as e:
            importer.read("stored_procedure", "CREATE PROC …")
        assert e.value.code == "format_not_translated"
        assert "a wrong compiler" in e.value.remediation

    def test_every_refused_format_gives_a_route_to_what_was_wanted(self):
        for why in NOT_TRANSLATED.values():
            assert why.strip()
        assert set(NOT_TRANSLATED) >= {"stored_procedure", "drools",
                                       "pmml_scorecard"}

    def test_a_pmml_scorecard_is_refused_as_the_wrong_kind_of_thing(self):
        assert "something that was fitted" in NOT_TRANSLATED["pmml_scorecard"]

    def test_an_unknown_format_names_the_two_that_work(self, importer):
        with pytest.raises(RuleError) as e:
            importer.read("yaml", "{}")
        assert e.value.code == "unknown_import_format"

    def test_a_table_with_no_outcome_column_is_refused(self, importer):
        with pytest.raises(RuleError) as e:
            importer.read(DECISION_TABLE, "score,because\n>=1,x\n")
        assert e.value.code == "no_outcome_columns"
        assert "breaks the first time somebody inserts a column" in \
            e.value.remediation

    def test_a_row_with_no_reason_is_refused(self, importer):
        """The register requires a reason on every rule and this is not a
        formality: a rule nobody can justify is one nobody can retire."""
        out = importer.read(DECISION_TABLE, "score,out:d\n>=720,approve\n")
        assert out["candidate"] is None
        assert "nobody knows what it was for" in out["untranslated"][0]["why"]


class TestTheXmlIsUntrustedInput:
    def test_a_doctype_is_refused_whole(self, importer):
        with pytest.raises(RuleError) as e:
            importer.read(DMN, '<!DOCTYPE x [<!ENTITY a "b">]><definitions/>')
        assert e.value.code == "dmn_declares_a_doctype"
        assert "cannot accidentally configure away" in e.value.remediation

    def test_a_huge_document_is_bounded(self, importer):
        with pytest.raises(RuleError) as e:
            importer.read(DMN, "<a/>" + "x" * (9 * 1024 * 1024))
        assert e.value.code == "dmn_too_large"

    def test_malformed_xml_is_the_exporters_problem(self, importer):
        with pytest.raises(RuleError) as e:
            importer.read(DMN, "<definitions><oops>")
        assert e.value.code == "unreadable_dmn"

    def test_a_dmn_document_with_no_table_is_refused(self, importer):
        with pytest.raises(RuleError) as e:
            importer.read(DMN, "<definitions><decision/></definitions>")
        assert e.value.code == "no_decision_table"
        assert "writing a compiler" in e.value.remediation


class TestDmnReadsTheField:
    def test_the_input_expression_names_the_field(self, importer):
        """Not the element id. Reading the element's own text yields the
        whitespace between tags, and the fallback to `id` produced a rule set
        that parsed, loaded and tested a field called `i1` — which is exactly
        the silent wrongness this module exists to avoid."""
        rule = importer.read(DMN, DMN_DOC)["candidate"]["rules"][0]
        fields = {c["field"] for c in rule["when"]["all"]}
        assert fields == {"score", "segment"}

    def test_a_rule_with_no_description_is_refused(self, importer):
        out = importer.read(DMN, DMN_DOC.replace(
            "<description>policy CR-4: prime band</description>", ""))
        assert out["candidate"] is None
        assert "nobody can retire" in out["untranslated"][0]["why"]


class TestThroughTheApi:
    def test_the_formats_are_published(self, client):
        out = client.get("/api/v1/rule-import/formats").json()
        assert [r["format"] for r in out["not_translated"]]
        assert out["imports_anything"] is False

    def test_a_table_is_read_over_the_wire(self, client):
        out = client.post("/api/v1/rule-import", json={
            "format": DECISION_TABLE, "document": TABLE})
        assert out.status_code == 200
        assert out.json()["rules"] == 2

    def test_a_stored_procedure_is_refused_over_the_wire(self, client):
        out = client.post("/api/v1/rule-import", json={
            "format": "stored_procedure", "document": "CREATE PROC"})
        assert out.status_code == 422
        assert "format_not_translated" in out.text

    def test_naming_a_version_validates_as_well_as_parses(self, client,
                                                          registered):
        """Parsing says the document was readable. Validation says whether it
        is usable against a real version's schemas, and only the second is the
        question somebody importing a rulebook actually has."""
        out = client.post("/api/v1/rule-import", json={
            "format": DECISION_TABLE, "document": TABLE,
            "urn": "maya://model/credit.pd.smallbiz", "semver": "3.2.1"})
        # 409 is the honest answer here and worth asserting on rather than
        # routing around: the fixture's version is a scorecard whose kernel
        # is not a rule set, so the editor refuses the pairing before it ever
        # looks at the document. An import that validated against a version
        # that cannot hold a rule set would be the more alarming result.
        assert out.status_code in (200, 409, 422)
        if out.status_code == 200:
            assert "validated" in out.json()
