"""
§16.4 in a real browser: the pin button is disabled until a preview comes back
clean, disarms again the moment a field changes, and stays disabled when the
preview names a blocker — and the faceted catalog filters and pages from the
server without a script error.

Skipped where Playwright or Chrome is absent.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import re
import socket
import threading
import time

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

from tests.conftest import PASSWORD, World, build_platform, price_csv  # noqa: E402

PX = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "close", "type": "float64"}],
    "source": {"type": "csv"},
    "resolution": {"grid": "as_is", "rules": {"close": "forward_fill(limit=3)"}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "close"}],
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def site():
    import uvicorn

    from maya.server import build_app

    port = _free_port()
    platform = build_platform()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="bp", preset="regulated")
    # mick is a feature manager and holds P on feature_pin, so the pin form is his to arm
    platform.features.create(
        w.dana, namespace="bp", name="bp_px", definition=PX, tags=["eod", "prices"]
    )
    platform.features.ingest(w.dana, "bp/bp_px", price_csv(), fmt="csv")
    platform.features.transition(w.dana, "bp/bp_px", 1, "submit")
    platform.features.transition(w.mick, "bp/bp_px", 1, "approve")
    with platform.uow() as uow:
        for name in ("mick", "dana"):
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
    yield f"http://127.0.0.1:{port}", platform
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
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    return ctx, page


def _login(page, base, user="mick"):
    page.goto(f"{base}/login")
    page.fill("#username", user)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def test_the_pin_button_is_armed_only_by_a_clean_preview(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    page.goto(f"{base}/catalog/features/bp/bp_px?tab=pins")
    submit = page.locator("[data-pin-submit]")
    assert submit.is_disabled(), "the button starts disabled (§16.4)"
    page.fill("#pn", "eom")
    page.fill("#pa", "2026-01-20")
    page.click("[data-pin-check]")
    report = page.locator("[data-pin-report]")
    report.get_by_text(re.compile(r"row\(s\) over")).wait_for(timeout=15000)
    text = report.inner_text()
    assert "stored" in text and "B/row" in text
    assert "Fill report" in text
    assert "not_null" in text
    assert "already holds" in text
    submit.wait_for(timeout=5000)
    assert not submit.is_disabled(), "a clean preview arms it"
    assert page.errors == []
    ctx.close()


def test_changing_a_field_disarms_the_button_again(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    page.goto(f"{base}/catalog/features/bp/bp_px?tab=pins")
    page.fill("#pn", "eom2")
    page.fill("#pa", "2026-01-20")
    page.click("[data-pin-check]")
    submit = page.locator("[data-pin-submit]")
    page.locator("[data-pin-report]").get_by_text(re.compile(r"row\(s\) over")).wait_for(
        timeout=15000
    )
    assert not submit.is_disabled()
    page.fill("#pa", "2026-01-10")  # a different pin: the armed button must not carry over
    assert submit.is_disabled()
    assert page.errors == []
    ctx.close()


def test_a_preview_with_a_blocker_leaves_the_button_disabled_and_says_why(site, browser):
    base, platform = site
    ctx, page = _page(browser)
    _login(page, base)
    page.goto(f"{base}/catalog/features/bp/bp_px?tab=pins")
    page.fill("#pn", "clash")
    page.fill("#pa", "2026-01-20")
    with platform.uow() as uow:
        feature = uow.repo("features").find_one(name="bp_px")
        version = uow.repo("feature_versions").find_one(feature_id=feature["id"], version_no=1)
        uow.repo("feature_pins").add(
            {
                "feature_id": feature["id"],
                "feature_version_id": version["id"],
                "pin_name": "clash",
                "as_of_date": dt.date(2026, 1, 20),
                "as_of_known": dt.datetime(2026, 1, 21, tzinfo=dt.timezone.utc),
                "state": "sealed",
            }
        )
    page.click("[data-pin-check]")
    report = page.locator("[data-pin-report]")
    report.get_by_text(re.compile("This pin would be refused")).wait_for(timeout=15000)
    assert "never overwrites" in report.inner_text()
    assert page.locator("[data-pin-submit]").is_disabled()
    assert page.errors == []
    ctx.close()


def test_the_faceted_catalog_filters_and_pages_in_the_browser(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    page.goto(f"{base}/catalog")
    page.wait_for_selector("[data-maya-table][data-table-id=catalog] tbody tr")
    assert page.locator("tbody tr", has_text="bp_px").count() == 1
    page.select_option("#f-tag", "eod")
    page.click("form[method=get] button[type=submit]")
    page.wait_for_url(re.compile(r"tag=eod"))
    assert page.locator("tbody tr", has_text="bp_px").count() == 1
    page.select_option("#f-type", "model")
    page.click("form[method=get] button[type=submit]")
    page.wait_for_url(re.compile(r"type=model"))
    assert page.locator(".mt-empty:visible").count() == 1
    assert page.errors == []
    ctx.close()
