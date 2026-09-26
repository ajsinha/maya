"""
The UI in a real browser: headless Chrome driven by Playwright against a live
MAYA server — the navigation, the server-paged tables, the help search, the
theme, the phone layout, and the security-key ceremony through Chrome's own
virtual authenticator. Skipped where Playwright or Chrome is absent.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import copy
import re
import socket
import threading
import time

import pytest

from pathlib import Path  # noqa: E402

TEMPLATES = Path(__file__).resolve().parents[1] / "maya" / "web" / "templates"


def test_no_template_carries_script_the_csp_would_block():
    """script-src 'self': inline <script> blocks and on*= handlers never run in a browser."""
    bad = []
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"<script(?![^>]*\b(?:src=|type=\"application/json\"))[^>]*>", text):
            bad.append(f"{path.name}: inline <script>")
        if re.search(r"\son[a-z]+\s*=\s*[\"']", text):
            bad.append(f"{path.name}: inline event handler")
    assert not bad, bad


playwright_sync = pytest.importorskip("playwright.sync_api")
expect = playwright_sync.expect

from tests.conftest import PX_DEF, World, build_platform  # noqa: E402

ADMIN_PW = "maya-dev-admin"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def site():
    import uvicorn

    from maya.server import build_app

    port = _free_port()
    platform = build_platform(
        [f"--auth.webauthn.origins=http://localhost:{port}", "--auth.webauthn.rp_id=localhost"]
    )
    w = World(platform)
    platform.access.create_namespace(w.admin, name="eq")
    for i in range(30):
        platform.features.create(
            w.dana,
            namespace="eq",
            name=f"feat_{i:02d}",
            definition=copy.deepcopy(PX_DEF),
            description=f"feature {i}",
        )
    with platform.uow() as uow:
        for name in ("admin", "dana", "mick"):
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
    yield f"http://localhost:{port}", w
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


def _page(browser, **kw):
    ctx = browser.new_context(**kw)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    return ctx, page


def _login(page, base, user="admin", password=ADMIN_PW):
    page.goto(f"{base}/login")
    page.fill("#username", user)
    page.fill("#password", password)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def test_sign_in_and_the_home_page_render_without_script_errors(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    assert page.locator(".maya-welcome h1").inner_text().startswith("Welcome back")
    assert page.locator(".maya-nav .nav-link", has_text="Catalog").is_visible()
    assert page.errors == []
    ctx.close()


def test_the_mega_menu_opens_on_hover_and_navigates(site, browser):
    base, _ = site
    ctx, page = _page(browser, viewport={"width": 1400, "height": 900})
    _login(page, base)
    page.hover(".maya-nav .nav-link:has-text('Catalog')")
    panel = page.locator(".mega-panel.show")
    panel.wait_for(state="visible", timeout=3000)
    assert panel.locator(".mega-desc").first.is_visible()
    panel.locator("a.mega-item[href='/catalog/features']").click()
    page.wait_for_url(re.compile(r"/catalog/features$"))
    assert page.locator(".maya-nav .nav-link.active", has_text="Catalog").count() == 1
    assert page.errors == []
    ctx.close()


def test_a_server_paged_table_pages_searches_and_sorts(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    page.goto(f"{base}/catalog/features")
    table = page.locator("[data-maya-table]").first
    rows = table.locator("tbody tr")
    info = table.locator(".mt-info")
    expect(info).to_contain_text("1–25 of")
    expect(rows).to_have_count(25)
    table.locator(".mt-next").click()
    expect(info).to_contain_text("26–30")
    expect(rows).to_have_count(5)
    table.locator(".mt-prev").click()
    expect(info).to_contain_text("1–25")
    table.locator(".mt-search").fill("feat_07")
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("feat_07")
    assert table.locator("mark").count() >= 1
    table.locator(".mt-search").fill("")
    expect(rows).to_have_count(25)
    header = table.locator("th[data-sortable]").first
    header.click()
    first = rows.first.inner_text()
    header.click()
    expect(rows.first).not_to_have_text(first)
    assert page.errors == []
    ctx.close()


def test_every_theme_can_be_chosen_and_is_remembered(site, browser):
    """Four themes from one menu, each one surviving a reload.

    Bootstrap is told dark only for the dark theme: blue and green are light schemes with a
    different accent, and telling Bootstrap otherwise would give them dark form controls."""
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    for theme, bs in (("dark", "dark"), ("blue", "light"), ("green", "light"), ("light", "light")):
        page.click("#theme-toggle")
        page.click(f"[data-theme-choice='{theme}']")
        assert page.evaluate("document.documentElement.getAttribute('data-theme')") == theme
        assert page.evaluate("document.documentElement.getAttribute('data-bs-theme')") == bs
        page.reload()
        assert page.evaluate("document.documentElement.getAttribute('data-theme')") == theme
        accent = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--maya-crimson').trim()"
        )
        assert accent, f"{theme}: no accent token resolved"
    ctx.close()


def test_the_phone_layout_collapses_the_menu_behind_a_button(site, browser):
    base, _ = site
    ctx, page = _page(browser, viewport={"width": 390, "height": 844})
    _login(page, base)
    menu = page.locator("#maya-menu")
    assert not menu.is_visible()
    page.click(".navbar-toggler")
    menu.wait_for(state="visible", timeout=3000)
    page.click(".maya-nav .nav-link:has-text('Models')")
    page.locator(".mega-panel.show").wait_for(state="visible", timeout=3000)
    width = page.evaluate("document.documentElement.scrollWidth")
    assert width <= 390, f"horizontal scroll at phone width ({width}px)"
    ctx.close()


def test_help_search_filters_cards_and_copy_works_signed_out(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    page.goto(f"{base}/help")
    assert page.locator(".maya-nav a", has_text="Sign in").is_visible()
    all_cards = page.locator(".help-item:visible").count()
    page.fill("#help-q", "covenant")
    visible = page.locator(".help-item:visible")
    expect(visible.first).to_be_visible()
    assert 0 < visible.count() < all_cards
    page.fill("#help-q", "zzzz-nothing")
    expect(page.locator("#help-none")).to_be_visible()
    page.goto(f"{base}/help/getting-started")
    button = page.locator("[data-copy]").first
    button.click()
    expect(button).to_contain_text("Copied")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert "git clone" in copied
    assert page.errors == []
    ctx.close()


def test_a_security_key_registers_and_then_answers_the_challenge(site, browser):
    """Chrome's virtual authenticator stands in for a hardware key: the real ceremony,
    run by the real webauthn.js, verified by the server."""
    base, w = site
    ctx, page = _page(browser)
    cdp = ctx.new_cdp_session(page)
    cdp.send("WebAuthn.enable")
    cdp.send(
        "WebAuthn.addVirtualAuthenticator",
        {
            "options": {
                "protocol": "ctap2",
                "transport": "usb",
                "hasResidentKey": True,
                "hasUserVerification": True,
                "isUserVerified": True,
            }
        },
    )
    _login(page, base, "mick", "Test-password-1")
    page.goto(f"{base}/account/mfa")
    page.fill("#key-name", "virtual key")
    page.click("[data-webauthn=register]")
    page.wait_for_selector("text=virtual key", timeout=10000)
    with w.p.uow() as uow:
        mick = uow.repo("users").find_one(username="mick")
        assert uow.repo("webauthn_credentials").count(user_id=mick["id"]) == 1
    page.goto(f"{base}/")
    page.click(".maya-tools .user")
    page.locator("form[action='/logout'] button").click()
    page.wait_for_url(re.compile(r"/$"))  # the landing page, not the sign-in form
    _login(page, base, "mick", "Test-password-1")
    auth = page.locator("[data-webauthn=authenticate]")
    auth.wait_for(state="visible", timeout=5000)
    auth.click()
    page.wait_for_url(re.compile(r"localhost:\d+/$"), timeout=10000)
    assert page.locator(".maya-welcome").is_visible()
    assert page.errors == []
    ctx.close()


JOURNEY = [
    ("home", "/"),
    ("catalog", "/catalog/features"),
    ("feature", "/catalog/features/eq/feat_00"),
    ("featuresets", "/catalog/featuresets"),
    ("models", "/models"),
    ("workbench", "/workbench"),
    ("workflow", "/workflow"),
    ("warrants", "/warrants"),
    ("search", "/search?q=feat"),
    ("health", "/admin/health"),
    ("help", "/help"),
    ("about", "/about"),
]


@pytest.mark.parametrize(
    "viewport",
    [{"width": 1366, "height": 900}, {"width": 390, "height": 844}],
    ids=["desktop", "phone"],
)
def test_the_main_journeys_render_and_are_captured(site, browser, viewport, tmp_path):
    """Gate 24: every main screen, as a person sees it, in a real browser, saved as a
    screenshot (to MAYA_SCREENSHOT_DIR when set). Each must load without a script error
    or an error page, and its screenshot must be a real render, not a blank page."""
    import os

    from PIL import Image, ImageStat

    base, _ = site
    out = Path(os.environ.get("MAYA_SCREENSHOT_DIR") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    ctx, page = _page(browser, viewport=viewport)
    _login(page, base)
    label = "desktop" if viewport["width"] > 800 else "phone"
    for name, path in JOURNEY:
        response = page.goto(f"{base}{path}")
        page.wait_for_load_state("networkidle")
        assert response is not None and response.status == 200, (path, response)
        assert "/login" not in page.url, path
        shot = out / f"{label}-{name}.png"
        page.screenshot(path=str(shot), full_page=True)
        with Image.open(shot) as img:
            spread = ImageStat.Stat(img.convert("L")).stddev[0]
        assert shot.stat().st_size > 5_000 and spread > 5, (path, "blank render")
    assert page.errors == [], page.errors
    ctx.close()
