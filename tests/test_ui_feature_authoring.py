"""
MAYA — the feature authoring screens.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Model developers rejected the platform because the feature flows existed only as
HTTP calls. These are the screens that answer that, and this suite drives them
the way a browser does rather than the way a fixture does: through `/login`, with
the session's CSRF token attached, against the real application.

The distinction matters. Every other feature suite here signs in with HTTP Basic,
which carries no ambient authority and therefore needs no token — so a page whose
JavaScript forgot the token would pass every one of them and fail for every real
user. The `browser` fixture below is deliberately cookie-authenticated.

What is asserted, and why each is here:

* **Every page renders.** A page with no test renders `Undefined` and nobody
  notices, which is how three of the existing ones were found.
* **A definition works end to end**, through the same endpoints the screens call
  — define, create a view, materialise, read back, and see the lineage.
* **A refusal reaches the user with its remediation.** A refusal delivered as a
  bare status is one nobody can act on, and the screens exist to render it.
* **The check decides nothing the API would not.** A draft the check accepts is
  one define accepts; a draft it refuses is one define refuses.
* **No asset is external.** The interface has to render air-gapped.
"""
from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
SCRIPT = ROOT / "web" / "static" / "js" / "feature-author.js"
TOKEN = re.compile(r'name="csrf-token" content="([^"]+)"')

PAGES = ("/features/new", "/features/load", "/features/point-in-time")


class Browser:
    """A signed-in browser: a session cookie and the token that defends it.

    Written as a small wrapper rather than as a bare client because the token is
    the thing the screens must get right, and a helper that forgets it would
    make the suite agree with a broken page.
    """

    def __init__(self, client: TestClient):
        self.client = client
        self.token = ""

    def get(self, path: str, **kw):
        response = self.client.get(path, **kw)
        if (found := TOKEN.search(response.text)) is not None:
            self.token = found.group(1)
        return response

    def post(self, path: str, **kw):
        headers = dict(kw.pop("headers", {}))
        headers["X-MAYA-CSRF"] = self.token
        return self.client.post(path, headers=headers, **kw)

    def delete(self, path: str, **kw):
        headers = dict(kw.pop("headers", {}))
        headers["X-MAYA-CSRF"] = self.token
        return self.client.delete(path, headers=headers, **kw)


@pytest.fixture
def catalogued(client):
    """Two primitives, one derivation and one materialised view.

    Set up with HTTP Basic, before any session exists, so the setup is not what
    is being tested. The restated row is the case point-in-time correctness is
    for: C1's first-quarter figure is revised months after it was filed.
    """
    for name, description in (("dscr", "debt service coverage ratio"),
                              ("revenue", "trailing twelve month revenue")):
        r = client.post("/api/v1/features", json={
            "name": name, "entity": "borrower", "dtype": "numeric",
            "description": description, "owner": "person/d.raman"})
        assert r.status_code == 201, r.text
    r = client.post("/api/v1/derived-features", json={
        "name": "coverage", "expression": "revenue / dscr", "dtype": "numeric",
        "description": "turnover per unit of cover"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/feature-views", json={
        "name": "sb_financials", "entity": "borrower", "owner": "person/d.raman",
        "features": ["dscr", "revenue"], "description": "as filed"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/feature-views/sb_financials/materialise", json={
        "rows": [
            # Filed at 100, landed at 110.
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0,
             "dscr": 1.20, "revenue": 5.0},
            # The SAME period, restated downward long afterwards.
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0,
             "dscr": 0.40, "revenue": 3.0},
            {"entity_id": "C2", "event_ts": 100.0, "ingest_ts": 110.0,
             "dscr": 2.10, "revenue": 9.0},
        ]})
    assert r.status_code == 201, r.text
    return client


@pytest.fixture
def browser(catalogued):
    """Signed in through the form, as a person is."""
    session = TestClient(catalogued.app)
    r = session.post("/login", data={"username": "admin", "password": "admin123",
                                     "next": "/dashboard"},
                     follow_redirects=False)
    assert r.status_code == 303, r.text
    b = Browser(session)
    b.get("/dashboard")               # mints and captures the token
    return b


# --------------------------------------------------------------- the pages
class TestThePagesRender:
    def test_each_authoring_page_renders(self, browser):
        for path in PAGES:
            r = browser.get(path)
            assert r.status_code == 200, f"{path}: {r.status_code}"

    def test_the_define_page_offers_both_kinds_and_the_language(self, browser):
        body = browser.get("/features/new").text
        assert "A primitive feature" in body
        assert "Z = f(X, Y)" in body
        # The language comes from the code, not from a copy on the page.
        assert "natural logarithm" in body and "year(event_ts)" in body
        assert "Certification is a meet" in body
        # The third kind: a combination of features is a feature.
        assert "A feature composed from others" in body
        assert "rightmost wins" in body

    def test_the_load_page_names_both_clocks_and_the_formats(self, browser):
        body = browser.get("/features/load").text
        assert "event_ts" in body and "ingest_ts" in body
        # CSV is accepted on the way in and never written; the page says so.
        assert "text/csv" in body and "cannot carry a type" in body
        assert "sb_financials" in body

    def test_the_point_in_time_page_states_the_operator_and_the_fill_rules(
            self, browser):
        body = browser.get("/features/point-in-time").text
        assert "AsOf(R" in body and "min(&#8467;, a)" in body
        assert "saturating at" in body, "the reproducibility law is stated"
        for rule in ("flat_forward", "flat_backward", "linear", "nearest", "none"):
            assert rule in body
        assert "reaches ahead" in body, "the unsafe rules are marked as unsafe"

    def test_a_feature_page_shows_lineage_in_both_directions(self, browser):
        body = browser.get("/feature/coverage").text
        assert "revenue / dscr" in body
        assert "Rests on" in body and "Rested on by" in body
        assert "dscr" in body and "revenue" in body

    def test_a_primitive_page_names_what_would_break(self, browser):
        body = browser.get("/feature/dscr").text
        assert "coverage" in body, "the dependant is named"
        assert "cannot be withdrawn while something derives from it" in body

    def test_the_feature_page_shows_where_the_values_are(self, browser):
        body = browser.get("/feature/dscr").text
        assert "sb_financials" in body
        assert "Where its values are" in body
        assert "Null rate" in body

    def test_an_unknown_feature_is_404(self, browser):
        assert browser.get("/feature/no-such-feature").status_code == 404

    def test_the_pages_redirect_when_anonymous(self, catalogued):
        anon = TestClient(catalogued.app)
        for path in PAGES + ("/feature/dscr",):
            r = anon.get(path, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"], path


# ------------------------------------------------------------- authoring
class TestDefiningThroughTheScreen:
    def test_the_check_accepts_a_sound_primitive_and_reports_near_duplicates(
            self, browser):
        r = browser.post("/api/v1/features/check", json={
            "kind": "primitive", "name": "revenue_ttm", "entity": "borrower",
            "dtype": "numeric", "description": "trailing twelve month revenue"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["ok"] == 1 and out["certification"] == "experimental"
        assert any(d["name"] == "revenue" for d in out["possible_duplicates"]), \
            "a near-duplicate is surfaced while renaming is still cheap"
        assert out["not_checked"], "the check says what it did not answer"

    def test_a_definition_the_check_accepts_is_one_define_accepts(self, browser):
        draft = {"name": "arrears_days", "entity": "borrower", "dtype": "integer",
                 "description": "days past due", "owner": "person/d.raman"}
        assert browser.post("/api/v1/features/check",
                            json={"kind": "primitive", **draft}).status_code == 200
        assert browser.post("/api/v1/features", json=draft).status_code == 201
        assert browser.get("/feature/arrears_days").status_code == 200

    def test_the_check_refuses_a_name_already_taken(self, browser):
        r = browser.post("/api/v1/features/check", json={
            "kind": "primitive", "name": "dscr", "entity": "borrower"})
        assert r.status_code == 409
        assert "already defined" in r.json()["detail"]

    def test_the_check_refuses_an_expression_outside_the_language(self, browser):
        r = browser.post("/api/v1/features/check", json={
            "kind": "derived", "name": "smuggled",
            "expression": "__import__('os').getcwd()"})
        assert r.status_code == 409
        body = r.json()
        assert "not one of the functions this language provides" in body["detail"]
        assert body["remediation"], "a refusal carries what to do about it"
        reserved = browser.post("/api/v1/features/check", json={
            "kind": "derived", "name": "sneaky", "expression": "__globals__ + 1"})
        assert reserved.status_code == 409
        assert "reserved by the language" in reserved.json()["detail"]

    def test_an_external_expression_declares_what_it_reads(self, browser):
        """The case `external` exists for and did not cover: an expression MAYA
        cannot parse, kept with its lineage rather than discarded."""
        opaque = {"kind": "derived", "name": "sentiment", "evaluator": "external",
                  "expression": "bert(filings[-1]).sentiment"}
        refused = browser.post("/api/v1/features/check", json=opaque)
        assert refused.status_code == 409
        assert "must declare the features it reads" in refused.json()["detail"]
        accepted = browser.post("/api/v1/features/check",
                                json={**opaque, "inputs": ["revenue"]})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["opaque"] == 1
        assert accepted.json()["inputs"] == ["revenue"]

    def test_the_check_refuses_a_loop_and_names_where_it_closes(self, browser):
        r = browser.post("/api/v1/features/check", json={
            "kind": "derived", "name": "revenue", "expression": "coverage * 2"})
        assert r.status_code == 409
        assert "would depend on itself through 'coverage'" in r.json()["detail"]

    def test_the_check_computes_certification_as_the_meet_of_the_inputs(
            self, browser):
        assert browser.post("/api/v1/features/dscr/certify?level=certified"
                            ).status_code == 200
        r = browser.post("/api/v1/features/check", json={
            "kind": "derived", "name": "cover2", "expression": "revenue / dscr"})
        assert r.status_code == 200, r.text
        out = r.json()
        levels = {i["name"]: i["certification"]
                  for i in out["certification_of_inputs"]}
        assert levels == {"dscr": "certified", "revenue": "experimental"}
        assert out["certification"] == "experimental", \
            "the meet is the weakest input; deriving does not launder it"

    def test_the_check_writes_nothing(self, browser):
        r = browser.post("/api/v1/features/check", json={
            "kind": "primitive", "name": "never_defined", "entity": "borrower"})
        assert r.status_code == 200, r.text
        assert browser.get("/feature/never_defined").status_code == 404, \
            "a check that left a feature behind would be a define wearing a "\
            "different name"


class TestComposingThroughTheScreen:
    """A combination of features is a feature, and the fold says so."""

    @pytest.fixture
    def curve(self, browser):
        r = browser.post("/api/v1/features", json={
            "name": "gbp_curve", "entity": "book", "dtype": "numeric",
            "description": "the sterling curve", "owner": "person/d.raman",
            "shape": "3", "components": ["1m", "1y", "5y"]})
        assert r.status_code == 201, r.text
        return browser

    def test_the_check_folds_the_parents_and_says_who_decided_each(self, curve):
        r = curve.post("/api/v1/features/check", json={
            "kind": "composed", "name": "gbp_curve_extended", "entity": "book",
            "composes": ["gbp_curve"],
            "operations": [{"op": "add", "name": "50y",
                            "value": {"dtype": "numeric"}},
                           {"op": "drop", "name": "1m"}]})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["members"] == ["1y", "5y", "50y"], \
            "insertion order, never sorted: for a vector the component order " \
            "IS the axis order"
        decided = {p["member"]: p["from"] for p in out["provenance"]}
        assert decided["1y"] == "gbp_curve"
        assert out["dimensionality"]["kind"] == "vector"

    def test_an_operation_that_would_do_nothing_is_refused(self, curve):
        """Totality: a drop of something absent is a mistake, not a no-op. A
        no-op leaves a child that differs from what its author wrote."""
        r = curve.post("/api/v1/features/check", json={
            "kind": "composed", "name": "gbp_curve_extended", "entity": "book",
            "composes": ["gbp_curve"],
            "operations": [{"op": "drop", "name": "30y"}]})
        assert r.status_code == 409
        assert "cannot drop '30y'" in r.json()["detail"]

    def test_composing_something_that_does_not_exist_is_refused(self, curve):
        r = curve.post("/api/v1/features/check", json={
            "kind": "composed", "name": "child", "entity": "book",
            "composes": ["no_such_parent"]})
        assert r.status_code == 409
        assert "no such feature" in r.json()["detail"]

    def test_a_composition_the_check_accepts_is_one_define_accepts(self, curve):
        body = {"name": "gbp_curve_extended", "entity": "book", "dtype": "numeric",
                "description": "with a fifty-year point", "owner": "person/d.raman",
                "composes": [{"name": "gbp_curve"}],
                "operations": [{"op": "add", "name": "50y",
                                "value": {"dtype": "numeric"}}]}
        assert curve.post("/api/v1/features/check",
                          json={"kind": "composed", **body}).status_code == 200
        assert curve.post("/api/v1/features", json=body).status_code == 201
        page = curve.get("/feature/gbp_curve_extended").text
        assert "What it is composed from" in page
        assert "Where each component came from" in page
        assert "50y" in page and "gbp_curve" in page


class TestLoadingValuesThroughTheScreen:
    def test_a_view_and_a_load_and_a_read_back(self, browser):
        assert browser.post("/api/v1/feature-views", json={
            "name": "sb_arrears", "entity": "borrower", "owner": "person/d.raman",
            "features": ["dscr"], "description": "arrears"}).status_code == 201
        r = browser.post("/api/v1/feature-views/sb_arrears/materialise", json={
            "rows": [{"entity_id": "C1", "event_ts": 10.0, "ingest_ts": 20.0,
                      "dscr": 1.0}]})
        assert r.status_code == 201, r.text
        version = r.json()
        assert version["row_count"] == 1
        assert version["valid_time_column"] == "event_ts"
        assert version["ingest_time_column"] == "ingest_ts"
        assert "dscr" in version["quality_report"]
        back = browser.get("/api/v1/feature-views/sb_arrears/versions/1/"
                           "data?format=json&limit=25")
        assert back.status_code == 200
        assert back.json()["rows"][0]["entity_id"] == "C1"

    def test_a_csv_upload_is_read_as_bytes(self, browser):
        """The page sends a file to the raw-body endpoint an execution engine
        uses. A CSV carries no types, which is why MAYA reads one and never
        writes one."""
        csv = ("entity_id,event_ts,ingest_ts,dscr\n"
               "C9,10.0,20.0,1.5\n")
        r = browser.client.post(
            "/api/v1/feature-views/sb_financials/data", content=csv,
            headers={"Content-Type": "text/csv",
                     "X-MAYA-CSRF": browser.token})
        assert r.status_code == 201, r.text
        assert r.json()["uploaded_rows"] == 1

    def test_a_row_missing_a_clock_is_refused_with_its_remediation(self, browser):
        """The refusal a developer will meet first, and the one the screen
        exists to render in full."""
        r = browser.post("/api/v1/feature-views/sb_financials/materialise", json={
            "rows": [{"entity_id": "C3", "event_ts": 100.0, "dscr": 1.0}]})
        assert r.status_code == 409
        body = r.json()
        assert "ingest_ts" in body["detail"] and "two clocks" in body["detail"]
        assert body["remediation"]


class TestTheTwoClocks:
    def test_the_point_in_time_read_refuses_what_was_not_yet_known(self, browser):
        """C1's figure was filed at 100, landed at 110 and was revised at 900.
        A decision taken at 200 could have seen the filing and could not have
        seen the revision, so the read must return the figure as first filed."""
        r = browser.post("/api/v1/feature-views/sb_financials/versions/1/as-of",
                         json={"label_ts": 200.0, "as_of": 1000.0})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["knowable_by"] == 200.0, "the ingest bound is min(label, as_of)"
        c1 = next(e for e in out["entities"] if e["entity_id"] == "C1")
        assert c1["read"]["ingest_ts"] == 110.0, "the restatement is excluded"
        refused = [c for c in c1["candidates"] if not c["admissible"]]
        assert len(refused) == 1
        assert refused[0]["ingest_ts"] == 900.0
        assert refused[0]["refused_by_ingest_clock"] == 1
        assert refused[0]["refused_by_event_clock"] == 0
        assert "not yet known" in refused[0]["detail"]

    def test_the_read_saturates_at_the_label(self, browser):
        """Every as_of at or after the label gives the same answer — the
        reproducibility law, asked through the screen's own endpoint."""
        answers = []
        for as_of in (200.0, 500.0, 10_000.0):
            r = browser.post("/api/v1/feature-views/sb_financials/versions/1/as-of",
                             json={"label_ts": 200.0, "as_of": as_of})
            assert r.status_code == 200, r.text
            c1 = next(e for e in r.json()["entities"] if e["entity_id"] == "C1")
            answers.append(c1["read"]["dscr"])
        assert answers == [1.20, 1.20, 1.20]

    def test_nothing_known_yet_is_an_answer_rather_than_a_gap(self, browser):
        """At the moment of filing, the platform had not yet learned the figure.
        The read returns nothing, and that is the correct answer — filling it
        would be inventing what somebody knew."""
        r = browser.post("/api/v1/feature-views/sb_financials/versions/1/as-of",
                         json={"label_ts": 100.0, "as_of": 1000.0})
        assert r.status_code == 200, r.text
        c1 = next(e for e in r.json()["entities"] if e["entity_id"] == "C1")
        assert c1["read"] is None
        assert "not a gap to be filled" in c1["detail"]
        assert all(c["refused_by_ingest_clock"] == 1 for c in c1["candidates"])

    def test_the_read_writes_nothing(self, browser):
        """The load page renders every version and its Delta pin, so a probe
        that wrote anything would move the page it is compared against."""
        before = browser.get("/features/load").text
        browser.post("/api/v1/feature-views/sb_financials/versions/1/as-of",
                     json={"label_ts": 200.0, "as_of": 1000.0})
        assert browser.get("/features/load").text == before

    def test_an_assembly_with_a_bound_removed_is_refused(self, browser):
        r = browser.post("/api/v1/training-sets", json={
            "name": "unbounded", "as_of": 1000.0,
            "spine": [{"entity_id": "C1", "label_ts": 100.0, "label": 0}],
            "views": [{"view": "sb_financials", "version": 1}],
            "transaction_time_bound": False})
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "assembly_rejected"
        assert "transaction_time" in body["detail"]
        assert body["remediation"]

    def test_an_assembly_with_both_bounds_is_verified(self, browser):
        r = browser.post("/api/v1/training-sets", json={
            "name": "bounded", "as_of": 1000.0,
            "spine": [{"entity_id": "C1", "label_ts": 100.0, "label": 0}],
            "views": [{"view": "sb_financials", "version": 1}]})
        assert r.status_code == 201, r.text
        assert r.json()["pit_verified"] is True


class TestFillRulesAndNulls:
    ROWS = [{"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 100.0, "dscr": 1.0},
            {"entity_id": "C1", "event_ts": 300.0, "ingest_ts": 300.0, "dscr": 3.0}]

    def _align(self, browser, rule, **extra):
        return browser.post("/api/v1/features/alignment-trial", json={
            "rows": self.ROWS, "rule": rule, "grid": "regular", "step": 100.0,
            **extra})

    def test_carrying_forward_is_safe_for_training(self, browser):
        r = self._align(browser, "flat_forward")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["point_in_time_safe"] is True
        filled = next(x for x in out["rows"] if x["event_ts"] == 200.0)
        assert filled["dscr"] == 1.0
        assert filled["ingest_ts"] == 200.0, \
            "carried from the past, so it was knowable at the grid point"

    def test_carrying_backward_stamps_when_the_value_became_knowable(self, browser):
        """It is not refused. It is stamped, and the point-in-time read then
        excludes it by the ordinary rule."""
        r = self._align(browser, "flat_backward")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["point_in_time_safe"] is False and out["looks_ahead"] == 1
        filled = next(x for x in out["rows"] if x["event_ts"] == 200.0)
        assert filled["dscr"] == 3.0
        assert filled["ingest_ts"] == 300.0, \
            "answered by an April observation, so it carries April's clock"

    def test_the_carry_limit_leaves_a_stale_value_out(self, browser):
        r = self._align(browser, "flat_forward", carry_limit=50.0)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["carried_beyond_limit"] >= 1
        filled = next(x for x in out["rows"] if x["event_ts"] == 200.0)
        assert filled["dscr"] is None

    def test_an_unknown_fill_rule_is_refused(self, browser):
        r = self._align(browser, "magic")
        assert r.status_code == 409 and "not a fill rule" in r.json()["detail"]

    def test_a_null_is_an_answer_and_refuse_is_the_other_choice(self, browser):
        rows = [{"entity_id": "C1", "event_ts": 1.0, "ingest_ts": 2.0,
                 "revenue": 5.0, "dscr": 0.0}]
        quiet = browser.post("/api/v1/features/trial", json={
            "expression": "revenue / dscr", "on_error": "null", "rows": rows})
        assert quiet.status_code == 200, quiet.text
        assert quiet.json()["rows"][0]["value"] is None
        assert quiet.json()["rows"][0]["refused"] == 0
        loud = browser.post("/api/v1/features/trial", json={
            "expression": "revenue / dscr", "on_error": "refuse", "rows": rows})
        assert loud.json()["rows"][0]["refused"] == 1
        assert "stop" in loud.json()["rows"][0]["detail"]

    def test_the_inherited_ingest_clock_moves_upward(self, browser):
        """ingest_ts(Z) = max over the inputs: you did not know Z before them."""
        r = browser.post("/api/v1/features/trial", json={
            "expression": "revenue / dscr", "rows": [
                {"entity_id": "C1", "event_ts": 1.0, "ingest_ts": 2.0,
                 "revenue": 6.0, "dscr": 2.0, "revenue__ingest_ts": 900.0}]})
        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]
        assert row["value"] == 3.0
        assert row["knowable_at"] == 900.0 and row["clock_moved"] == 1

    def test_a_row_the_expression_cannot_read_is_reported_not_raised(self, browser):
        r = browser.post("/api/v1/features/trial", json={
            "expression": "revenue / dscr",
            "rows": [{"entity_id": "C1", "revenue": 6.0}]})
        assert r.status_code == 200, r.text
        assert r.json()["rows"][0]["refused"] == 1
        assert "disagree" in r.json()["rows"][0]["detail"]


class TestRefusalsReachTheUser:
    def test_a_person_without_the_permission_is_told_which_one(self, catalogued,
                                                               client):
        """The developer may define a feature and may not certify one. The
        screen shows the button and lets the API refuse it, because a hidden
        control teaches nobody why."""
        r = client.post("/api/v1/principals", json={
            "username": "d.raman", "display_name": "D Raman",
            "roles": ["model_developer"], "password": "dev-pw"})
        assert r.status_code == 201, r.text
        session = TestClient(catalogued.app)
        session.post("/login", data={"username": "d.raman", "password": "dev-pw",
                                     "next": "/dashboard"})
        dev = Browser(session)
        dev.get("/feature/dscr")
        refused = dev.post("/api/v1/features/dscr/certify?level=certified")
        assert refused.status_code == 403
        body = refused.json()
        assert "feature:certify" in body["detail"] or "certify" in body["detail"]
        assert body["remediation"]

    def test_a_state_changing_request_without_the_token_is_refused(self, browser):
        """The control working, asserted rather than assumed: the screens rely
        on `csrf.js` attaching it, and a page that stopped including the base
        template would fail here rather than in production."""
        r = browser.client.post("/api/v1/features/check",
                                json={"kind": "primitive", "name": "x",
                                      "entity": "borrower"})
        assert r.status_code == 403 and r.json()["error"] == "csrf_token_invalid"

    def test_a_durable_feature_is_not_destroyed_but_retired(self, browser):
        r = browser.delete("/api/v1/features/dscr")
        assert r.status_code == 409
        assert "not ephemeral" in r.json()["detail"]

    def test_a_sealed_feature_refuses_an_amendment(self, browser):
        assert browser.post("/api/v1/features/revenue/seal",
                            json={"note": "final"}).status_code == 200
        r = browser.post("/api/v1/features/revenue/amend",
                         json={"fields": {"description": "changed"}})
        assert r.status_code == 409
        assert browser.get("/feature/revenue").status_code == 200


# ------------------------------------------------------------- the assets
class TestNothingIsFetchedFromTheInternet:
    def test_no_page_references_an_external_asset(self, browser):
        for path in PAGES + ("/feature/dscr", "/feature/coverage"):
            body = browser.get(path).text
            for marker in ("cdn.", "//code.jquery", "googleapis", "jsdelivr",
                           "unpkg", "http://", "https://"):
                assert marker not in body, f"{marker} referenced in {path}"

    def test_the_script_is_served_from_disk_and_reaches_nowhere(self):
        assert SCRIPT.exists()
        source = SCRIPT.read_text(encoding="utf-8")
        assert "http://" not in source and "https://" not in source

    def test_the_templates_extend_the_base_that_carries_the_token(self):
        for template in sorted(TEMPLATES.glob("feature_author*.html")):
            body = template.read_text(encoding="utf-8")
            assert '{% extends "base.html" %}' in body, template.name
            assert "/static/js/feature-author.js" in body, template.name

    def test_every_table_on_these_pages_has_a_header_row(self):
        """Enforced globally by `test_ui_tables`, and asserted here too because
        these templates build tables in JavaScript as well as in Jinja."""
        for template in sorted(TEMPLATES.glob("feature_author*.html")):
            body = template.read_text(encoding="utf-8")
            for chunk in body.split("<table")[1:]:
                assert "<thead" in chunk.split("</table>")[0], template.name
        script = SCRIPT.read_text(encoding="utf-8")
        for chunk in script.split("<table")[1:]:
            assert "<thead" in chunk[:200], "a table built in JS needs a header too"


class TestTheCheckAnswersTheQuestionItClaimsTo:
    """"Would `define` accept this?" — so it must take what `define` takes.

    `DefinitionCheckIn` was missing `owner` and six governance attributes that
    `FeatureIn` carries. While unknown fields were silently dropped this was
    invisible: a caller building one draft and posting it to both endpoints got
    a cheerful 200 from a check that had discarded half of it, then a different
    answer from the real call.
    """

    def test_every_field_define_takes_the_check_takes(self):
        from routes.feature_routes import FeatureIn
        from routes.ui_feature_routes import DefinitionCheckIn

        defines = set(FeatureIn.model_fields)
        checks = set(DefinitionCheckIn.model_fields)
        missing = sorted(defines - checks)
        assert not missing, (
            f"the check refuses fields `define` accepts, so it is answering a "
            f"different question: {missing}")

    def test_a_full_draft_passes_both(self, browser):
        draft = {"name": "arrears_ratio", "entity": "borrower", "dtype": "numeric",
                 "description": "arrears over limit", "owner": "person/d.raman",
                 "business_definition": "days past due divided by the limit",
                 "source_system": "collections", "sensitivity": "confidential",
                 "pii": False, "protected_basis": False, "proxy_risk": "low"}
        assert browser.post("/api/v1/features/check",
                            json={"kind": "primitive", **draft}).status_code == 200
        assert browser.post("/api/v1/features", json=draft).status_code == 201
