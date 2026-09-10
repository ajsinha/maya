"""Entities rather than tables, views that store the query, and returns that
say what they do not know.

Three failure modes: a dashboard inventing its own definition of `in force`, a
shared view carrying its author's scope to a reader, and a plausible value in a
box that gets sent to a supervisor.
"""
from __future__ import annotations

import csv
import io
import json

import pytest

from core.authz.scope import Scope
from core.reporting.returns import (ANNEX_III_DESIGNATIONS, NOT_HELD, RETURNS,
                                    RegulatoryReturns, ReturnError)
from core.reporting.semantics import (ADMISSIBLE, ENTITIES, MAX_ROWS,
                                      OPERATORS, QueryError, SemanticLayer)
from core.reporting.views import CSV, FORMATS, JSON, PARQUET, REFUSED, SavedViews
from tests.conftest import URN

DAY = 86400.0


@pytest.fixture
def semantics(db, registry, findings, monitoring):
    return SemanticLayer(db, registry, findings=findings, monitoring=monitoring)


@pytest.fixture
def saved(db, semantics, evidence):
    from db import SavedViewRepository
    return SavedViews(SavedViewRepository(db), semantics, evidence)


@pytest.fixture
def returns(registry, validation, findings, monitoring):
    return RegulatoryReturns(registry, validation=validation, findings=findings,
                             monitoring=monitoring)


# ------------------------------------------------------------- the catalogue
class TestTheCatalogueIsTheContract:
    def test_every_entity_publishes_its_fields(self, semantics):
        out = semantics.describe()
        assert out["entities"] and all(e["fields"] for e in out["entities"])

    def test_no_parameter_anywhere_takes_query_text(self):
        """The promise the whole layer rests on."""
        import inspect
        names = set(inspect.signature(SemanticLayer.query).parameters)
        assert not (names & {"sql", "query", "text", "expression"})

    def test_the_rows_carry_exactly_the_declared_fields(self, semantics,
                                                        a_model, approved_version):
        """A data dictionary that drifts from the data is the artefact this
        layer exists to replace, so the two are checked against each other."""
        for name, spec in ENTITIES.items():
            rows = semantics._rows(spec, 0.0)
            declared = {f.name for f in spec.fields}
            for row in rows:
                assert set(row) == declared, f"{name} row does not match its fields"

    def test_every_field_admits_at_least_one_operator(self):
        for spec in ENTITIES.values():
            for field in spec.fields:
                assert ADMISSIBLE[field.type]

    def test_every_admissible_operator_is_a_real_one(self):
        for operators in ADMISSIBLE.values():
            assert set(operators) <= set(OPERATORS)


class TestInForceIsThePlatformsDefinition:
    def test_a_blocked_model_is_not_in_force_despite_being_approved(
            self, semantics, registry, findings, a_model, approved_version):
        """`status = 'approved'` is the obvious answer a BI tool would reach
        for, and it is wrong."""
        before = semantics.query("model")["rows"][0]
        assert before["in_force"] is True
        findings.raise_finding(a_model["id"], "Critical", "Wrong",
                               "person/j.okafor", blocking=True)
        after = semantics.query("model")["rows"][0]
        assert after["in_force"] is False and after["blocking_findings"] == 1

    def test_derived_fields_are_marked_as_derived(self):
        model = ENTITIES["model"]
        assert model.field("in_force").derived
        assert not model.field("urn").derived


# -------------------------------------------------------------- the refusals
class TestAQueryIsRefusedByName:
    def test_an_unknown_entity(self, semantics):
        with pytest.raises(QueryError) as e:
            semantics.query("models")
        assert e.value.code == "unknown_entity"

    def test_an_unknown_field(self, semantics):
        with pytest.raises(QueryError) as e:
            semantics.query("model", select=["urn", "colour"])
        assert e.value.code == "unknown_field"

    def test_an_operator_the_type_does_not_admit(self, semantics):
        """`contains` on a timestamp is how a query builder produces a form
        nobody can fill in correctly."""
        with pytest.raises(QueryError) as e:
            semantics.query("model", where=[
                {"field": "registered_at", "operator": "contains", "value": "x"}])
        assert e.value.code == "operator_not_admissible"

    def test_in_needs_a_list(self, semantics):
        with pytest.raises(QueryError) as e:
            semantics.query("model", where=[
                {"field": "urn", "operator": "in", "value": "one"}])
        assert e.value.code == "value_not_a_list"

    def test_a_limit_beyond_the_ceiling(self, semantics):
        with pytest.raises(QueryError) as e:
            semantics.query("model", limit=MAX_ROWS + 1)
        assert e.value.code == "limit_out_of_range"


class TestFilteringAndOrdering:
    def test_a_comparison_narrows(self, semantics, a_model):
        assert semantics.query("model", where=[
            {"field": "domain", "operator": "eq", "value": "credit"}])["returned"] == 1
        assert semantics.query("model", where=[
            {"field": "domain", "operator": "eq", "value": "market"}])["returned"] == 0

    def test_contains_is_case_insensitive(self, semantics, a_model):
        assert semantics.query("model", where=[
            {"field": "name", "operator": "contains", "value": "sb"}])["returned"] == 1

    def test_a_null_satisfies_no_comparison(self, semantics, registry, a_model):
        """SQL agrees, and the alternative is a filter that silently includes
        the rows it cannot judge."""
        registry.register("urn:maya:model:untiered", "No tier", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "unclear")
        out = semantics.query("model", where=[
            {"field": "tier", "operator": "lt", "value": 5}])
        assert {r["urn"] for r in out["rows"]} == {URN}

    def test_nulls_sort_last_whichever_direction(self, semantics, registry,
                                                 a_model):
        registry.register("urn:maya:model:untiered", "No tier", "x.y", "credit",
                          "person/j.okafor", "LE-US-01", "unclear")
        for descending in (False, True):
            rows = semantics.query("model", order_by="tier",
                                   descending=descending)["rows"]
            assert rows[-1]["tier"] is None

    def test_truncation_is_stated_rather_than_inferred(self, semantics, registry,
                                                       a_model):
        for i in range(3):
            registry.register(f"urn:maya:model:m{i}", f"M{i}", "x.y", "credit",
                              "person/j.okafor", "LE-US-01", "p")
        out = semantics.query("model", limit=2)
        assert out["truncated"] and "cut by the limit" in out["detail"]


class TestScopeFiltersRowsAndSaysSo:
    def test_a_scoped_reader_gets_a_shorter_table(self, semantics, registry,
                                                  a_model):
        registry.register("urn:maya:model:other", "Other", "x.y", "markets",
                          "person/j.okafor", "LE-UK-01", "p")
        out = semantics.query("model", scope=Scope(legal_entities=("LE-US-01",)))
        assert out["returned"] == 1 and out["outside_scope"] == 1

    def test_the_count_is_never_silently_short(self, semantics, registry,
                                               a_model):
        registry.register("urn:maya:model:other", "Other", "x.y", "markets",
                          "person/j.okafor", "LE-UK-01", "p")
        out = semantics.query("model", scope=Scope(legal_entities=("LE-US-01",)))
        assert "outside your scope" in out["detail"]

    def test_an_unrestricted_scope_removes_nothing(self, semantics, a_model):
        assert semantics.query("model", scope=Scope())["outside_scope"] == 0


# ------------------------------------------------------------- saved views
class TestAViewStoresTheQueryNotTheRows:
    def test_the_stored_row_holds_no_result_set(self, saved, a_model):
        view = saved.save("credit models", "model",
                          {"where": [{"field": "domain", "operator": "eq",
                                      "value": "credit"}]}, "person/j.okafor")
        assert "rows" not in view and "query" in view

    def test_a_shared_view_runs_under_the_readers_scope(self, saved, registry,
                                                        a_model):
        """The disclosure that would otherwise be invisible: sharing a view
        would carry the author's scope to the reader."""
        registry.register("urn:maya:model:other", "Other", "x.y", "markets",
                          "person/j.okafor", "LE-UK-01", "p")
        view = saved.save("everything", "model", {}, "person/j.okafor",
                          shared=True)
        out = saved.run(view["id"], "person/a.reader",
                        scope=Scope(legal_entities=("LE-UK-01",)))
        assert out["returned"] == 1 and out["outside_scope"] == 1
        assert "under your scope rather than its author's" in out["detail"]

    def test_an_unshared_view_is_refused_to_anybody_else(self, saved, a_model):
        view = saved.save("mine", "model", {}, "person/j.okafor")
        with pytest.raises(QueryError) as e:
            saved.run(view["id"], "person/a.reader")
        assert e.value.code == "view_not_shared"

    def test_a_broken_view_is_refused_while_its_author_is_present(self, saved,
                                                                  a_model):
        with pytest.raises(QueryError) as e:
            saved.save("broken", "model", {"select": ["colour"]},
                       "person/j.okafor")
        assert e.value.code == "unknown_field"

    def test_two_views_cannot_share_a_name(self, saved, a_model):
        saved.save("mine", "model", {}, "person/j.okafor")
        with pytest.raises(QueryError) as e:
            saved.save("mine", "model", {}, "person/j.okafor")
        assert e.value.code == "view_already_saved"

    def test_only_the_owner_may_delete(self, saved, a_model):
        view = saved.save("mine", "model", {}, "person/j.okafor", shared=True)
        with pytest.raises(QueryError) as e:
            saved.delete(view["id"], "person/a.reader")
        assert e.value.code == "not_your_view"

    def test_a_stored_query_with_an_unknown_key_does_not_explode(self, saved,
                                                                 a_model):
        """A TypeError is a stack trace where a refusal belongs."""
        view = saved.save("mine", "model", {}, "person/j.okafor")
        saved.views.set({"query": {"select": ["urn"], "nonsense": 1}},
                        id=view["id"])
        assert saved.run(view["id"], "person/j.okafor")["fields"] == ["urn"]


class TestAnExportIsADisclosure:
    def test_csv_round_trips(self, saved, a_model):
        out = saved.export("model", CSV, {"select": ["urn", "domain"]},
                           "person/j.okafor")
        rows = list(csv.DictReader(io.StringIO(out["bytes"].decode())))
        assert rows[0]["urn"] == URN and out["media_type"] == "text/csv"

    def test_json_carries_its_field_list(self, saved, a_model):
        out = saved.export("model", JSON, {"select": ["urn"]}, "person/j.okafor")
        assert json.loads(out["bytes"])["fields"] == ["urn"]

    def test_parquet_is_readable_back(self, saved, a_model):
        import pyarrow.parquet as pq
        out = saved.export("model", PARQUET, {"select": ["urn", "tier"]},
                           "person/j.okafor")
        table = pq.read_table(io.BytesIO(out["bytes"]))
        assert table.column_names == ["urn", "tier"]

    def test_the_export_is_recorded(self, saved, evidence, a_model):
        saved.export("model", CSV, {}, "person/j.okafor")
        assert any(n["kind"] == "extract_taken"
                   for n in evidence.for_subject("model"))

    def test_xlsx_is_refused_by_name_with_the_reason(self, saved, a_model):
        with pytest.raises(QueryError) as e:
            saved.export("model", "xlsx", {}, "person/j.okafor")
        assert e.value.code == "format_refused"
        assert "CSV opens in Excel" in e.value.detail

    def test_a_typo_and_a_decision_are_different_refusals(self, saved, a_model):
        with pytest.raises(QueryError) as e:
            saved.export("model", "csvv", {}, "person/j.okafor")
        assert e.value.code == "unknown_format"

    def test_every_refused_format_gives_a_reason(self):
        assert all(why.strip() for why in REFUSED.values())
        assert not set(REFUSED) & set(FORMATS)


# ---------------------------------------------------- the regulatory returns
class TestAnExtractIsNotAFiling:
    def test_the_catalogue_publishes_the_gaps_before_anybody_runs_one(self):
        out = RegulatoryReturns.catalogue()
        registration = next(r for r in out["returns"]
                            if r["return"] == "ai_act_registration")
        assert "authorised_representative" in registration["not_held"]
        assert registration["complete"] is False

    def test_a_field_the_register_cannot_answer_comes_back_empty(
            self, returns, registry, a_model):
        registry.designate(URN, ["consumer_impacting"], actor="person/j.okafor")
        out = returns.extract("ai_act_registration")
        assert out["rows"][0]["authorised_representative"] == ""
        assert "not_held" in out and out["complete"] is False

    def test_the_header_says_the_extract_is_incomplete(self, returns, registry,
                                                       a_model):
        registry.designate(URN, ["consumer_impacting"], actor="person/j.okafor")
        assert "not a filing" in returns.extract("ai_act_registration")["detail"]

    def test_an_unknown_return_is_refused(self, returns):
        with pytest.raises(ReturnError) as e:
            returns.extract("cocoa_production")
        assert e.value.code == "unknown_return"

    def test_every_declared_field_appears_in_every_row(self, returns, registry,
                                                       a_model):
        registry.designate(URN, ["consumer_impacting"], actor="person/j.okafor")
        for name in RETURNS:
            out = returns.extract(name)
            for row in out["rows"]:
                assert set(row) == set(out["fields"]), name

    def test_a_field_held_in_principle_and_empty_is_reported_separately(
            self, returns, a_model):
        """A limit of the platform and a gap in this firm's data are different
        facts, and only the second is somebody's work."""
        out = returns.extract("model_inventory")
        assert "last_validated" in out["empty_in_this_extract"]
        assert "materiality_amount" in out["not_held"]


class TestThePopulationIsDerivedAndPublished:
    def test_a_designation_puts_a_model_in_annex_iii(self, returns, registry,
                                                     a_model):
        registry.designate(URN, ["consumer_impacting"], actor="person/j.okafor")
        out = returns.extract("ai_act_registration")
        assert out["count"] == 1
        assert out["rows"][0]["annex_iii_ground"] == "consumer_impacting"

    def test_a_model_out_of_scope_is_listed_with_the_reason(self, returns,
                                                            a_model):
        out = returns.extract("ai_act_registration")
        assert out["count"] == 0 and len(out["excluded"]) == 1
        assert "Annex III" in out["excluded"][0]["why"]

    def test_no_purpose_class_at_all_is_an_absence_not_a_negative(self, returns,
                                                                  a_model):
        why = returns.extract("ai_act_registration")["excluded"][0]["why"]
        assert "an absence rather than a negative answer" in why

    def test_the_detail_says_what_happened_to_the_rest(self, returns, a_model):
        assert "what happened to the" in returns.extract(
            "ai_act_registration")["detail"]

    def test_an_unrecorded_origin_is_a_gap_rather_than_a_no(self, returns,
                                                            a_model):
        out = returns.extract("third_party_models")
        assert "a gap rather than a negative answer" in out["excluded"][0]["why"]

    def test_the_grounds_are_a_published_list(self):
        assert "consumer_impacting" in ANNEX_III_DESIGNATIONS

    def test_scope_narrows_the_population(self, returns, registry, a_model):
        registry.register("urn:maya:model:other", "Other", "x.y", "markets",
                          "person/j.okafor", "LE-UK-01", "p")
        out = returns.extract("model_inventory",
                              scope=Scope(legal_entities=("LE-US-01",)))
        assert out["count"] == 1

    def test_not_held_is_a_source_and_not_a_value(self):
        for spec in RETURNS.values():
            for field in spec["fields"]:
                assert field["source"] in ("held", "derived", NOT_HELD)
