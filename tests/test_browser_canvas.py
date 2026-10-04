"""
The lineage and algebra canvas in a real browser (§16.3): the graph drawn on
vendored Cytoscape, the filters and what they say they removed, the four overlay
modes worded as well as coloured, an inheritance chain folded and expanded, the
far graph clustered, the direction toggle re-fetching in place, hover detail, the
withheld count drawn rather than swallowed, the review overlay, and two selected
features opening the designer prefilled.

Skipped where Playwright or Chrome is absent.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import socket
import threading
import time

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")
expect = playwright_sync.expect

from tests.conftest import PASSWORD, PX_DEF, World, build_platform, price_csv  # noqa: E402

NS = "cy"
SHUT = "cyshut"
ROOT = f"maya://feature/{NS}/px@v1"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def site():
    """An estate shaped for the canvas: an inheritance chain four deep, an operator
    node, a member edge, a sealed pin, and one feature in a namespace devi may not read."""
    import uvicorn

    from maya.server import build_app

    port = _free_port()
    platform = build_platform()
    w = World(platform)
    p = platform
    p.access.create_namespace(w.admin, name=NS, default_visibility="namespace_read")
    p.access.create_namespace(w.admin, name=SHUT, default_visibility="private")

    def approved(name, definition=None, csv=True, ns=NS):
        p.features.create(w.dana, namespace=ns, name=name, definition=definition or PX_DEF)
        if csv:
            p.features.ingest(w.dana, f"{ns}/{name}", price_csv(6), fmt="csv")
        p.features.transition(w.dana, f"{ns}/{name}", 1, "submit")
        p.features.transition(w.mick, f"{ns}/{name}", 1, "approve")

    approved("px")
    approved("px_alt", csv=True)
    chain = ["px", "px_eur", "px_eur_adj", "px_eur_adj2"]
    for child, parent in zip(chain[1:], chain[:-1]):
        approved(
            child,
            {"extends": {"parent": f"maya://feature/{NS}/{parent}@v1", "binding": "pinned"}},
            csv=False,
        )
    approved(
        "px_both",
        {
            **PX_DEF,
            "source": {
                "type": "derived",
                "derivation": {
                    "operator": "union",
                    "operands": [f"maya://feature/{NS}/px@v1", f"maya://feature/{NS}/px_alt@v1"],
                    "options": {"collision": "prefer_left"},
                },
            },
        },
        csv=False,
    )
    p.features.pin(w.mick, f"{NS}/px", version_no=1, pin_name="eom", as_of=dt.date(2026, 1, 5))
    w.drain()
    p.featuresets.create(
        w.devi,
        namespace=NS,
        name="panel",
        definition={
            "index": ["date", "symbol"],
            "grid": "as_is",
            "alignment": {"mode": "inner"},
            "members": [
                {"attr": "close", "ref": f"maya://feature/{NS}/px@v1", "source_attr": "close"}
            ],
        },
    )
    p.featuresets.transition(w.devi, f"{NS}/panel", 1, "submit")
    p.featuresets.transition(w.mick, f"{NS}/panel", 1, "approve")
    p.features.create(w.dana, namespace=SHUT, name="px_private", definition=PX_DEF)
    with p.uow("admin") as uow:
        uow.repo("lineage_edges").link(f"maya://feature/{SHUT}/px_private@v1", ROOT, "feeds")
    # a change in review, for the review overlay
    p.features.new_draft(w.dana, f"{NS}/px_alt")
    p.features.update_draft(
        w.dana,
        f"{NS}/px_alt",
        {**PX_DEF, "schema": [{"name": "close", "type": "float64", "unit": "USD"}]},
    )
    p.features.transition(w.dana, f"{NS}/px_alt", 2, "submit")
    review_id = p.features.get(w.dana, f"{NS}/px_alt")["versions"][0]["id"]
    with p.uow() as uow:
        for name in ("dana", "mick", "devi"):
            user = uow.repo("users").find_one(username=name)
            uow.repo("users").update(user["id"], {"must_change_password": False})
    server = uvicorn.Server(
        uvicorn.Config(build_app(platform), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}", review_id
    server.should_exit = True
    thread.join(10)
    platform.shutdown()


@pytest.fixture(scope="module")
def browser():
    with playwright_sync.sync_playwright() as pw:
        try:
            b = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # noqa: BLE001 - no Chrome on this machine
            pytest.skip(f"Chrome is not available: {exc}")
        yield b
        b.close()


def _page(browser):
    ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    return ctx, page


def _login(page, base, user="devi"):
    page.goto(f"{base}/login")
    page.fill("#username", user)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def _canvas(page, base, root=ROOT, query=""):
    page.goto(f"{base}/lineage?root={root}{query}")
    page.wait_for_selector("#cy canvas", timeout=10000)
    page.locator("#cy-status").get_by_text("node(s)").wait_for(timeout=10000)
    page.click("details > summary")
    page.wait_for_selector("#cy-nodes li", timeout=5000)


def _rows(page):
    return page.locator("#cy-nodes li").all_inner_texts()


def test_the_canvas_helpers_say_what_the_spec_asks_them_to_say(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)
    assert page.evaluate("MayaLineage.edgeLabel({type: 'extends', label: '3'})") == "extends ·3"
    assert page.evaluate("MayaLineage.edgeLabel({type: 'operand_of', label: '2'})") == "operand 2"
    assert "override" in page.evaluate("MayaLineage.extendsDetail({label: '3'})")
    assert "not carried in the graph" in page.evaluate("MayaLineage.extendsDetail({})")
    op = page.evaluate("MayaLineage.operatorInfo('maya://op/union/abcd1234')")
    assert op["notation"] == "F₁ ∪ F₂" and "prefer_left" in op["collision"]
    assert "unify" in op["typing"]
    assert page.evaluate("MayaLineage.operatorInfo('maya://feature/eq/px@v1')") is None
    assert "̶" in page.evaluate("MayaLineage.strike('gone')")
    # the overlay reads the state of the version the node names, and says separately that
    # something newer exists: "superseded" is not an answer to "was this ever approved?"
    superseded = page.evaluate(
        "MayaLineage.overlays.approval({id: 'maya://feature/eq/px@v1',"
        " meta: {state: 'approved', latest_version: 3}})"
    )
    assert superseded["word"] == "approved, superseded by v3"
    stale_draft = page.evaluate(
        "MayaLineage.overlays.approval({id: 'maya://feature/eq/px@v1',"
        " meta: {state: 'draft', latest_version: 3}})"
    )
    assert stale_draft["ov"] == "warn" and stale_draft["word"].startswith("draft")
    data_age = page.evaluate(
        "MayaLineage.overlays.freshness({meta: {data_freshness: '2026-09-12T00:00:00'},"
        " now: Date.parse('2026-09-19T00:00:00')})"
    )
    assert data_age["word"] == "7d of data"
    changed = page.evaluate(
        "MayaLineage.overlays.freshness({meta: {updated_at: '2026-09-12T00:00:00'},"
        " now: Date.parse('2026-09-19T00:00:00')})"
    )
    assert changed["word"] == "7d since a change"
    assert page.evaluate("MayaLineage.bytesText(2097152)") == "2.0 MB"
    assert page.evaluate("MayaLineage.bytesText(null)") == "not priced"
    assert page.errors == []
    ctx.close()


def test_the_canvas_draws_the_graph_and_says_what_it_left_out(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)
    status = page.locator("#cy-status").inner_text()
    assert "node(s)" in status and "edge(s)" in status
    assert "1 left out because you may not read them" in status
    rows = "\n".join(_rows(page))
    assert f"feature/{NS}/px@v1" in rows
    assert "op/union/" in rows and "featureset" in rows
    assert "1 object(s) you may not read" in rows
    assert SHUT not in rows, "the withheld object is counted, never named"
    assert page.errors == []
    ctx.close()


def test_a_filter_reports_what_it_removed(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)
    before = len(_rows(page))
    page.select_option("#cy-f-type", "feature")
    page.locator("#cy-status").get_by_text("hidden by your filters").wait_for(timeout=5000)
    after = _rows(page)
    assert len(after) < before
    assert all("op/union" not in row for row in after)
    page.select_option("#cy-f-type", "")
    page.check("#cy-f-pinned")
    pinned = _rows(page)
    assert any("#eom/2026-01-05" in row for row in pinned)
    assert all("@v1" not in row or "#eom" in row for row in pinned)
    assert page.errors == []
    ctx.close()


def test_each_overlay_words_its_value_as_well_as_colouring_it(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)
    page.select_option("#cy-overlay", "approval")
    page.locator("#cy-legend").get_by_text("Approval").wait_for(timeout=5000)
    assert any("approved" in row for row in _rows(page))
    page.select_option("#cy-overlay", "freshness")
    page.locator("#cy-legend").get_by_text("Freshness").wait_for(timeout=5000)
    assert any("0d" in row for row in _rows(page)), "just created, so nought days old"
    page.select_option("#cy-overlay", "access")
    page.locator("#cy-legend").get_by_text("Access").wait_for(timeout=5000)
    rows = _rows(page)
    assert any("you can read it" in row for row in rows)
    assert any("withheld" in row for row in rows)
    assert any("internal node" in row for row in rows)
    page.select_option("#cy-overlay", "cost")
    page.locator("#cy-legend").get_by_text("Cost").wait_for(timeout=5000)
    page.locator("#cy-nodes").get_by_text("nothing pinned").first.wait_for(timeout=10000)
    cost = "\n".join(_rows(page))
    assert " B" in cost or "kB" in cost, cost
    assert page.errors == []
    ctx.close()


def test_an_inheritance_chain_folds_to_one_node_and_expands_again(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base, query="&direction=downstream&depth=8")
    assert any("px_eur_adj@v1" in row for row in _rows(page))
    page.check("#cy-collapse")
    page.locator("#cy-nodes").get_by_text("inheritance chain").wait_for(timeout=5000)
    folded = "\n".join(_rows(page))
    assert "2 version(s) folded" in folded
    assert "px_eur@v1" not in folded and "px_eur_adj@v1" not in folded
    assert "px_eur_adj2@v1" in folded, "the end of the chain stays drawn"
    page.locator("#cy-nodes button", has_text="inheritance chain").first.click()
    page.locator("#cy-nodes").get_by_text("px_eur_adj@v1").first.wait_for(timeout=5000)
    assert page.errors == []
    ctx.close()


def test_clustering_counts_the_far_graph_and_expands_on_demand(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base, query="&direction=downstream&depth=8")
    page.check("#cy-cluster")
    page.locator("#cy-status").get_by_text("clustered by namespace").wait_for(timeout=5000)
    clustered = "\n".join(_rows(page))
    assert "node(s), click to expand" in clustered
    assert "px_eur_adj2@v1" not in clustered, "three hops out, so counted rather than drawn"
    page.locator("#cy-nodes button", has_text="namespace ").first.click()
    page.locator("#cy-nodes").get_by_text("px_eur_adj2@v1").first.wait_for(timeout=5000)
    assert page.errors == []
    ctx.close()


def test_the_direction_toggle_refetches_in_place(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)
    both = len(_rows(page))
    page.select_option("#cy-direction", "downstream")
    # the CSP forbids unsafe-eval, so waiting happens through expect(), never
    # wait_for_function, which would evaluate a string inside the page
    expect(page.locator("#cy-nodes li")).not_to_have_count(both)
    assert "direction=downstream" in page.url, "the URL follows, without a page load"
    assert page.evaluate("document.getElementById('cy-form-direction').value") == "downstream"
    assert len(_rows(page)) != both
    assert page.errors == []
    ctx.close()


def test_a_node_and_an_operator_show_their_detail(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)
    page.locator("#cy-nodes button", has_text=f"feature/{NS}/px@v1").first.click()
    detail = page.locator("#cy-detail")
    expect(detail).to_contain_text("dana")
    expect(detail).to_contain_text("approved")
    expect(detail).to_contain_text("Re-root the view here")
    page.locator("#cy-nodes button", has_text="op/union/").first.click()
    expect(detail).to_contain_text("Collision policy")
    expect(detail).to_contain_text("prefer_left")
    page.locator("#cy-nodes button", has_text="1 object").first.click()
    expect(detail).to_contain_text("never quietly dropped")
    assert page.errors == []
    ctx.close()


def test_two_selected_features_open_the_designer_prefilled(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base, "dana")
    # px and px_alt are both upstream of the feature derived from them; from px alone,
    # px_alt is a fellow operand -- a sibling, which lineage does not draw
    _canvas(page, base, root=f"maya://feature/{NS}/px_both@v1")
    page.locator("#cy-nodes button", has_text=f"feature/{NS}/px@v1").first.click()
    page.locator("#cy-nodes button", has_text=f"feature/{NS}/px_alt@v1").first.click()
    open_link = page.locator("#cy-author-open")
    open_link.wait_for(state="visible", timeout=5000)
    href = open_link.get_attribute("href")
    assert "operator=union" in href and "px_alt%40v1" in href
    expect(page.locator("#cy-author-note")).to_contain_text("2 features selected")
    open_link.click()
    page.wait_for_url(lambda url: "/workbench/features/new" in url, timeout=10000)
    assert page.locator("#operands").input_value().count("maya://feature") == 2
    assert page.locator("#mode").input_value() == "derived"
    assert page.errors == []
    ctx.close()


def test_one_feature_set_selected_offers_its_cascade_pin(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)
    page.locator("#cy-nodes button", has_text=f"featureset/{NS}/panel").first.click()
    pin = page.locator("#cy-author-pin")
    pin.wait_for(state="visible", timeout=5000)
    assert pin.get_attribute("href") == f"/catalog/featuresets/{NS}/panel?tab=pins"
    expect(pin).to_contain_text("Cascade pin")
    assert page.errors == []
    ctx.close()


def test_the_review_screen_marks_the_change_on_the_canvas(site, browser):
    base, review_id = site
    ctx, page = _page(browser)
    _login(page, base, "mick")
    page.goto(f"{base}/workflow/review/feature_version/{review_id}")
    page.wait_for_selector("#cy canvas", timeout=10000)
    page.locator("#cy-status").get_by_text("node(s)").wait_for(timeout=10000)
    page.click("#cy-nodes ~ *, details > summary")
    page.wait_for_selector("#cy-nodes li", timeout=5000)
    rows = "\n".join(page.locator("#cy-nodes li").all_inner_texts())
    assert "changed in this review" in rows
    assert page.errors == []
    ctx.close()


def test_the_view_can_be_rearranged_without_leaving_the_page(site, browser):
    """A lineage graph is a map, and no one arrangement suits every graph.

    The controls are checked for what they do to the drawing rather than for existing: a
    layout button that runs a layout nobody can tell apart from the last one is not a
    control. So each arrangement is asserted to move the nodes, and the zoom buttons to
    change the zoom, with the graph still drawn afterwards."""
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _canvas(page, base)

    def positions():
        return page.evaluate(
            "() => cy.nodes().map(n => [n.id(), Math.round(n.position('x')),"
            " Math.round(n.position('y'))])"
        )

    page.evaluate("() => { window.cy = document.getElementById('cy')._cyreg.cy; }")
    layered = positions()
    assert layered, "the graph has nodes to arrange"

    for name in ("layered-lr", "organic", "radial", "grid"):
        page.select_option("#cy-layout", name)
        page.wait_for_timeout(1200)
        moved = positions()
        assert len(moved) == len(layered)
        assert moved != layered, f"the {name} arrangement left every node where it was"

    # Back to the default, and the zoom controls answer.
    page.select_option("#cy-layout", "layered")
    page.wait_for_timeout(1200)
    before = page.evaluate("() => cy.zoom()")
    page.click("#cy-zoom-in")
    page.wait_for_timeout(300)
    assert page.evaluate("() => cy.zoom()") > before
    page.click("#cy-zoom-out")
    page.click("#cy-zoom-out")
    page.wait_for_timeout(300)
    assert page.evaluate("() => cy.zoom()") < before
    page.click("#cy-fit")
    page.wait_for_timeout(400)
    assert page.evaluate("() => cy.nodes().length") == len(layered)
    assert page.locator("#cy-status").inner_text().find("node(s)") >= 0
