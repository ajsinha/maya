"""
The lineage canvas's server side (§16.3) and the editors' server side (§17.3):
what ``/ui/lineage`` hands the canvas, what it refuses to name, what the cost
overlay prices, how a change in review becomes an overlay, and the sample rows
the expression editor previews against.

The canvas behaviour itself is in tests/test_browser_canvas.py, in a real browser.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.web.routes.lineage import bare, parts
from maya.web.routes.models import spec_diff
from maya.web.routes.workflow import review_overlay
from tests.conftest import PASSWORD, PX_DEF, World, build_platform, price_csv
from tests.test_warrants import complete_spec
from tests.test_web_journeys import Browser

CANVAS = "cv"
SHUT = "cvshut"


@pytest.fixture(scope="module")
def estate():
    """One namespace anybody in it may read, one private, and a lineage that spans both."""
    from maya.server import build_app

    platform = build_platform()
    w = World(platform)
    p = platform
    p.access.create_namespace(w.admin, name=CANVAS, default_visibility="namespace_read")
    p.access.create_namespace(w.admin, name=SHUT, default_visibility="private")

    def approved(ns: str, name: str, definition=None, csv=True):
        p.features.create(w.dana, namespace=ns, name=name, definition=definition or PX_DEF)
        if csv:
            p.features.ingest(w.dana, f"{ns}/{name}", price_csv(6), fmt="csv")
        p.features.transition(w.dana, f"{ns}/{name}", 1, "submit")
        p.features.transition(w.mick, f"{ns}/{name}", 1, "approve")

    approved(CANVAS, "px")
    # the private one is never approved: nothing in a private namespace is mick's to approve,
    # and for this estate its existence as a lineage node is the point
    p.features.create(w.dana, namespace=SHUT, name="px_private", definition=PX_DEF)
    # an inheritance chain three versions deep, for collapse and expand
    for child, parent in (("px_eur", "px"), ("px_eur_adj", "px_eur")):
        approved(
            CANVAS,
            child,
            {"extends": {"parent": f"maya://feature/{CANVAS}/{parent}@v1", "binding": "pinned"}},
            csv=False,
        )
    # a derived feature, so the graph carries an operator node
    approved(
        CANVAS,
        "px_both",
        {
            **PX_DEF,
            "source": {
                "type": "derived",
                "derivation": {
                    "operator": "union",
                    "operands": [
                        f"maya://feature/{CANVAS}/px@v1",
                        f"maya://feature/{CANVAS}/px_eur@v1",
                    ],
                    "options": {"collision": "prefer_left"},
                },
            },
        },
        csv=False,
    )
    p.features.pin(w.mick, f"{CANVAS}/px", version_no=1, pin_name="eom", as_of=dt.date(2026, 1, 5))
    w.drain()
    fs_def = {
        "index": ["date", "symbol"],
        "grid": "as_is",
        "alignment": {"mode": "inner"},
        "members": [
            {"attr": "close", "ref": f"maya://feature/{CANVAS}/px@v1", "source_attr": "close"}
        ],
    }
    p.featuresets.create(w.devi, namespace=CANVAS, name="panel", definition=fs_def)
    p.featuresets.transition(w.devi, f"{CANVAS}/panel", 1, "submit")
    p.featuresets.transition(w.mick, f"{CANVAS}/panel", 1, "approve")
    # two versions of a model whose specification document differs, for the side-by-side
    p.models.create(
        w.mona,
        namespace=CANVAS,
        name="linear",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    p.models.update_draft(w.mona, f"{CANVAS}/linear", spec_latex=complete_spec("linear"))
    p.models.transition(w.mona, f"{CANVAS}/linear", 1, "submit")
    p.models.transition(w.mgr, f"{CANVAS}/linear", 1, "approve")
    p.models.new_draft(w.mona, f"{CANVAS}/linear")
    p.models.update_draft(
        w.mona,
        f"{CANVAS}/linear",
        spec_latex=complete_spec("linear").replace(
            "Assumptions for linear: stated in full.",
            "Assumptions for linear: restated, with a caveat.\n\nAnd a further paragraph.",
        ),
    )
    # the private feature feeds the readable one: an outsider must see the count, not the name
    with p.uow("admin") as uow:
        uow.repo("lineage_edges").link(
            f"maya://feature/{SHUT}/px_private@v1", f"maya://feature/{CANVAS}/px@v1", "feeds"
        )
    yield w, build_app(platform)
    platform.shutdown()


@pytest.fixture(scope="module")
def people(estate):
    """One signed-in session per person: Browser changes a first-use password, so a
    second sign-in with the original would be refused."""
    app = estate[1]
    sessions = {u: Browser(app, u, PASSWORD) for u in ("dana", "devi", "mick", "mona")}
    sessions["admin"] = Browser(app, "admin", "maya-dev-admin")
    return sessions


@pytest.fixture(scope="module")
def devi(people):
    return people["devi"]


ROOT = f"maya://feature/{CANVAS}/px@v1"


def test_bare_and_parts_read_a_node_reference():
    assert bare("maya://feature/eq/px@v3") == "maya://feature/eq/px"
    assert bare("maya://feature/eq/px#eom/2026-01-05") == "maya://feature/eq/px"
    assert parts("maya://featureset/eq/panel@v1") == ("featureset", "eq")
    assert parts("maya://op/union/abcd1234") is None
    assert parts("maya://warrant/train/xyz") is None


def test_the_canvas_payload_carries_the_detail_the_overlays_need(devi):
    g = devi.get(f"/ui/lineage?root={ROOT}&direction=both&depth=3").json()
    ids = {n["id"] for n in g["nodes"]}
    assert ROOT in ids
    assert any(i.startswith("maya://op/union/") for i in ids), "an operator node is drawn"
    assert f"maya://feature/{CANVAS}/px#eom/2026-01-05" in ids, "the pin is a node"
    meta = g["meta"][f"maya://feature/{CANVAS}/px"]
    assert meta["owner"] == "dana" and meta["namespace"] == CANVAS
    assert meta["state"] in ("approved", "published") and meta["latest_version"] == 1
    assert meta["url"] == f"/catalog/features/{CANVAS}/px" and meta["updated_at"]
    # exact, in the same payload: the freshness overlay reads a feature's data, and the
    # cost overlay every sealed pin rather than the first page of them
    assert meta["data_freshness"], "the feature's newest knowledge time"
    assert meta["pinned_bytes"] > 0, "one sealed pin"
    assert g["meta"][f"maya://feature/{CANVAS}/px_eur"]["pinned_bytes"] == 0
    assert g["meta_complete"] is True
    assert g["direction"] == "both" and g["depth"] == 3


def test_what_the_caller_may_not_read_is_counted_never_named(devi):
    g = devi.get(f"/ui/lineage?root={ROOT}").json()
    assert g["hidden"] == 1, "the private feature upstream"
    assert all(SHUT not in n["id"] for n in g["nodes"])
    assert all(SHUT not in e["source"] + e["target"] for e in g["edges"])
    assert all(SHUT not in key for key in g["meta"])


def test_the_owner_sees_the_private_node_the_outsider_does_not(people):
    g = people["dana"].get(f"/ui/lineage?root={ROOT}").json()
    assert f"maya://feature/{SHUT}/px_private@v1" in {n["id"] for n in g["nodes"]}
    assert g["hidden"] == 0


def test_a_root_the_caller_may_not_read_does_not_exist_for_them(devi):
    r = devi.c.get(f"/ui/lineage?root=maya://feature/{SHUT}/px_private@v1")
    assert r.status_code == 404 and SHUT in r.json()["error"]


def test_one_draw_describes_nodes_from_every_namespace_it_spans(people):
    """The canvas asks once. It used to browse the catalog once per (type, namespace) the
    graph touched, capped at twelve calls, beyond which nodes came back with no detail at
    all. One call now, and it spans namespaces."""
    g = people["dana"].get(f"/ui/lineage?root={ROOT}&direction=both&depth=4").json()
    described = {ref: row for ref, row in g["meta"].items()}
    assert {row["namespace"] for row in described.values()} >= {CANVAS, SHUT}
    assert all(row.get("type") and "hidden" not in row for row in described.values())


def test_a_nodes_versions_and_pins_are_one_question_about_one_object():
    """A graph draws v1, v2 and a pin of the same feature as three nodes; they are one
    object, and one row answers for all three."""
    from maya.web.routes.lineage import catalog_refs

    refs = catalog_refs(
        [
            {"id": "maya://feature/eq/px@v1"},
            {"id": "maya://feature/eq/px@v2"},
            {"id": "maya://feature/eq/px#eom/2026-01-05"},
            {"id": "maya://op/union/abcd1234"},
            {"id": "maya://featureset/eq/panel@v1"},
        ]
    )
    assert refs == ["maya://feature/eq/px", "maya://featureset/eq/panel"]


def test_nodes_describes_only_what_the_caller_may_read_and_names_nothing_else(estate, people):
    """Read scoping, at the endpoint the canvas now depends on: the owner is described,
    the outsider gets ``hidden`` and not one field more — no namespace, no owner, no
    version, and no tally per namespace either, which would name the namespaces they are
    shut out of."""
    w, _ = estate
    private = f"maya://feature/{SHUT}/px_private"
    refs = [f"maya://feature/{CANVAS}/px", private]
    outsider = w.p.catalog.nodes(w.devi, refs)
    assert outsider[private] == {"hidden": True}
    assert outsider[f"maya://feature/{CANVAS}/px"]["owner"] == "dana"
    owner = w.p.catalog.nodes(w.dana, refs)
    assert owner[private]["namespace"] == SHUT and owner[private]["state"] == "draft"
    assert owner[private]["pinned_bytes"] == 0


def test_a_node_carries_the_state_of_the_version_it_names(estate):
    """The approval overlay was borrowing the object's latest state for a node naming an
    older version, so a graph drawn on v1 of something since superseded looked approved
    because v4 was."""
    w, _ = estate
    p = w.p
    p.features.create(w.dana, namespace=CANVAS, name="two_ver", definition=PX_DEF)
    p.features.ingest(w.dana, f"{CANVAS}/two_ver", price_csv(6), fmt="csv")
    p.features.transition(w.dana, f"{CANVAS}/two_ver", 1, "submit")
    p.features.transition(w.mick, f"{CANVAS}/two_ver", 1, "approve")
    p.features.new_draft(w.dana, f"{CANVAS}/two_ver")
    ref = f"maya://feature/{CANVAS}/two_ver"
    rows = p.catalog.nodes(w.dana, [f"{ref}@v1", f"{ref}@v2", ref])
    assert rows[f"{ref}@v1"]["state"] in ("approved", "published")
    assert rows[f"{ref}@v2"]["state"] == "draft"
    assert rows[f"{ref}@v1"]["latest_version"] == 2
    # a bare reference means the object, so it answers for the latest version
    assert rows[ref]["version"] == 2 and rows[ref]["state"] == "draft"


def test_nodes_refuses_a_reference_that_is_not_a_catalog_object(estate):
    from maya.core.errors import ValidationFailed

    w, _ = estate
    with pytest.raises(ValidationFailed, match="not a catalog object"):
        w.p.catalog.nodes(w.dana, ["maya://warrant/train/whatever"])


def test_the_canvas_page_offers_the_interactions_the_spec_lists(devi):
    html = devi.get(f"/lineage?root={ROOT}&direction=upstream&depth=4").text
    for control in (
        'id="cy-direction"',
        'id="cy-depth"',
        'id="cy-overlay"',
        'id="cy-f-type"',
        'id="cy-f-namespace"',
        'id="cy-f-status"',
        'id="cy-f-pinned"',
        'id="cy-collapse"',
        'id="cy-cluster"',
        'id="cy-detail"',
        'id="cy-nodes"',
        'id="cy-author"',
    ):
        assert control in html, control
    assert 'value="upstream" selected' in html and 'value="4" selected' in html
    assert 'data-root="' + ROOT in html


def test_the_review_screen_draws_the_change_as_an_overlay(estate, people):
    w, app = estate
    p = w.p
    p.features.new_draft(w.dana, f"{CANVAS}/px")
    p.features.update_draft(
        w.dana,
        f"{CANVAS}/px",
        {**PX_DEF, "schema": [{"name": "close", "type": "float64", "unit": "USD"}]},
    )
    p.features.transition(w.dana, f"{CANVAS}/px", 2, "submit")
    version = p.features.get(w.dana, f"{CANVAS}/px")["versions"][0]
    html = people["mick"].get(f"/workflow/review/feature_version/{version['id']}").text
    assert 'id="cy-review"' in html and "removed, struck through" in html
    assert 'data-root="maya://feature/' in html


def test_review_overlay_splits_the_diff_into_added_changed_and_removed():
    r = {
        "ref": "maya://featureset/eq/panel@v2",
        "diff": {
            "against": "v1",
            "entries": [
                {"was": "maya://feature/eq/a@v1", "now": "—", "change": "removed"},
                {"was": "—", "now": "maya://feature/eq/b@v3", "change": "added"},
                {
                    "was": "maya://feature/eq/c@v1 close",
                    "now": "maya://feature/eq/c@v1 close USD",
                    "change": "changed",
                },
            ],
        },
    }
    overlay = review_overlay(r)
    assert overlay["removed"] == ["maya://feature/eq/a@v1"]
    assert overlay["added"] == ["maya://feature/eq/b@v3"]
    assert overlay["changed"] == ["maya://feature/eq/c@v1", "maya://featureset/eq/panel@v2"]


def test_a_first_version_under_review_is_drawn_as_added():
    overlay = review_overlay(
        {"ref": "maya://feature/eq/new@v1", "diff": {"entries": [], "note": "nothing before"}}
    )
    assert overlay["added"] == ["maya://feature/eq/new@v1"] and overlay["changed"] == []


def test_the_expression_editor_gets_three_sample_rows(people):
    out = people["dana"].get(f"/ui/expr-sample?kind=feature&ref={CANVAS}/px").json()
    assert "close" in out["columns"] and 0 < len(out["rows"]) <= 3
    assert all("close" in row for row in out["rows"])


def test_the_designer_opens_prefilled_from_the_canvas(people):
    dana = people["dana"]
    operands = f"maya://feature/{CANVAS}/px@v1,maya://feature/{CANVAS}/px_eur@v1"
    html = dana.get(f"/workbench/features/new?operator=union&operands={operands}").text
    assert 'value="derived" selected' in html
    assert f"maya://feature/{CANVAS}/px@v1\nmaya://feature/{CANVAS}/px_eur@v1" in html
    assert "<option selected>union</option>" in html or "selected>union<" in html
    plain = dana.get("/workbench/features/new").text
    assert 'value="source" selected' in plain


def test_the_expression_editor_is_wired_where_expressions_are_written(people):
    dana, admin = people["dana"], people["admin"]
    designer = dana.get(f"/workbench/features/{CANVAS}/px/edit").text
    assert 'data-expr-attrs-from="input[name=attr_name]"' in designer
    assert 'data-expr-insert-into="#transform"' in designer
    assert f"/ui/expr-sample?kind=feature&amp;ref={CANVAS}/px" in designer
    builder = dana.get(f"/workbench/featuresets/{CANVAS}/panel/edit").text
    assert 'data-expr-attrs-from="input[name=m_attr]"' in builder
    assert "/static/js/expr.js" in builder
    grants = admin.get("/admin/grants?kind=feature&ref=" + f"{CANVAS}/px").text
    assert 'id="grf"' in grants and "data-expr" in grants


def test_the_document_diff_aligns_the_lines_and_drops_the_rest():
    old = "\n".join(f"line {i}" for i in range(12))
    new = old.replace("line 5", "line five") + "\ntail"
    out = spec_diff(old, new)
    kinds = [r["kind"] for r in out["rows"]]
    assert kinds.count("changed") == 1 and kinds.count("added") == 1
    assert out["changed"] == 2 and out["skipped"] > 0
    changed = next(r for r in out["rows"] if r["kind"] == "changed")
    assert changed["left"] == "line 5" and changed["right"] == "line five"
    assert changed["left_no"] == 6 and changed["right_no"] == 6
    added = next(r for r in out["rows"] if r["kind"] == "added")
    assert added["left"] is None and added["right"] == "tail"
    assert spec_diff("same\n", "same\n") == {"rows": [], "skipped": 1, "changed": 0}


def test_the_model_diff_page_shows_the_document_side_by_side(people):
    html = people["mona"].get(f"/models/{CANVAS}/linear/diff?v1=1&v2=2").text
    assert "The specification document, side by side" in html
    assert "line(s) differ" in html and "identical line(s) either side are not shown" in html
    assert "restated, with a caveat." in html
    assert "And a further paragraph." in html
    same = people["mona"].get(f"/models/{CANVAS}/linear/diff?v1=1&v2=1").text
    assert "The document is identical between these versions." in same
