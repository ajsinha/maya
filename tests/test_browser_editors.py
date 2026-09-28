"""
The embedded editors in a real browser (§17): the LaTeX editor's live preview,
bracket matching, find and replace, spell check, figure embedding, the BibTeX
bibliography and the section outline; the Python editor's early view of the
ladder's static ban; and the expression editor — whose grammar is checked
against the server's own implementation, case by case, so the mirror cannot
quietly drift from maya/resolution/expr.py.

Skipped where Playwright or Chrome is absent.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import base64
import socket
import threading
import time

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")
expect = playwright_sync.expect

from tests.conftest import PASSWORD, PX_DEF, World, build_platform, price_csv  # noqa: E402
from tests.test_warrants import complete_spec  # noqa: E402

NS = "ed"
# a 1x1 transparent PNG: small enough to read, real enough for the browser to draw
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
BIB = (
    "@article{black1973,\n"
    "  author = {Black, Fischer and Scholes, Myron},\n"
    "  title = {The Pricing of Options and Corporate Liabilities},\n"
    "  journal = {Journal of Political Economy},\n"
    "  year = {1973}\n"
    "}\n"
)


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
    p = platform
    p.access.create_namespace(w.admin, name=NS, preset="standard")
    p.features.create(w.dana, namespace=NS, name="px", definition=PX_DEF)
    p.features.ingest(w.dana, f"{NS}/px", price_csv(6), fmt="csv")
    p.models.create(
        w.mona,
        namespace=NS,
        name="linear",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    p.models.update_draft(w.mona, f"{NS}/linear", spec_latex=complete_spec("linear"))
    with p.uow() as uow:
        for name in ("dana", "mona", "admin"):
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
    yield f"http://127.0.0.1:{port}", w
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


def _login(page, base, user="mona", password=PASSWORD):
    page.goto(f"{base}/login")
    page.fill("#username", user)
    page.fill("#password", password)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def _spec(page, base):
    """The specification tab's editor. The page carries three CodeMirrors — the
    definition tab's Python, this one, and the code tab's — so every selector here
    names the pane it means."""
    page.goto(f"{base}/models/{NS}/linear?tab=spec")
    page.wait_for_selector("#tab-spec .CodeMirror", timeout=10000)
    return page.locator("#spec-preview")


def _code(page, base):
    page.goto(f"{base}/models/{NS}/linear?tab=code")
    page.wait_for_selector("#tab-code .CodeMirror", timeout=10000)


def _set(page, editor, text):
    page.evaluate(f"MayaEditors.instances['{editor}'].set({text!r})")


def _get(page, editor):
    return page.evaluate(f"MayaEditors.instances['{editor}'].get()")


# ---------------------------------------------------------------- the expression editor
CASES = [
    "close > 100",
    "close * 2 - 1",
    "notnull(close) and symbol in ['AAA', 'BBB']",
    "round(close, 1)",
    "where(close > 100, 1, 0)",
    "min(close, 100)",
    "max(close, 100, 120)",
    "clip(close, 0, 100)",
    "close if close > 100 else 0",
    "-close",
    "close // 3",
    "close % 7",
    "sqrt(close)",
    "abs(0 - close)",
    "close == 101.5",
    "not (close > 100)",
    "symbol == 'AAA'",
    "isnull(close)",
    "symbol not in ['AAA']",
    "(close + 1) * 2 > close ** 2",
]
REFUSED = [
    # Membership takes a list, both sides, and both parenthesised forms are refused: the
    # language used to accept `(a, b)` while refusing `(a)`, which is the same thing to
    # read and documented nowhere.
    "close in (99.0, 120.25)",
    "symbol in ('AAA', 'BBB')",
    "close.mean()",
    "[x for x in close]",
    "lambda x: x",
    "open('/etc/passwd')",
    "banned(close)",
    "close in (1)",
    "{'a': 1}",
    "close +",
    "__import__('os')",
]


def _server_values(exprs, rows):
    """The same expressions, through maya/resolution/expr.py, over the same rows."""
    import pandas as pd

    from maya.resolution.expr import compile_expr

    frame = pd.DataFrame(rows)
    return {e: list(compile_expr(e).evaluate(frame)) for e in exprs}


def test_the_browsers_grammar_agrees_with_the_servers_case_by_case(site, browser):
    base, _ = site
    rows = [
        {"close": 101.5, "symbol": "AAA"},
        {"close": 99.0, "symbol": "BBB"},
        {"close": 120.25, "symbol": "CCC"},
    ]
    expected = _server_values(CASES, rows)
    ctx, page = _page(browser)
    _login(page, base)
    page.goto(f"{base}/admin/grants")  # a page that carries expr.js and nothing heavier
    disagreed = []
    for expr in CASES:
        out = page.evaluate(
            "([e, rows]) => MayaExpr.evaluate(e, rows, {close: 'float64', symbol: 'string'})",
            [expr, rows],
        )
        assert out["ok"], (expr, out["message"])
        for got, want in zip(out["values"], expected[expr]):
            same = got == want or (
                isinstance(want, float) and isinstance(got, (int, float)) and abs(got - want) < 1e-9
            )
            if not same:
                disagreed.append((expr, got, want))
    assert disagreed == [], disagreed
    assert page.errors == []
    ctx.close()


def test_what_the_server_refuses_the_browser_refuses(site, browser):
    from maya.core.errors import ValidationFailed
    from maya.resolution.expr import compile_expr

    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    page.goto(f"{base}/admin/grants")
    for expr in REFUSED:
        with pytest.raises(ValidationFailed):
            compile_expr(expr)
        out = page.evaluate("e => MayaExpr.check(e, {close: 'float64'})", expr)
        assert out["ok"] is False, expr
        assert out["message"], expr
    # the row filter's @user substitution is mirrored, so a legitimate filter is not flagged
    allowed = page.evaluate("MayaExpr.check(\"symbol == @user.desk\", {symbol: 'string'})")
    assert allowed["ok"] is True
    refused = page.evaluate("MayaExpr.check(\"symbol == @user.email\", {symbol: 'string'})")
    assert refused["ok"] is False and "@user.username" in refused["message"]
    assert page.errors == []
    ctx.close()


def test_the_expression_editor_names_the_attribute_and_previews_three_rows(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base, "dana")
    page.goto(f"{base}/workbench/features/{NS}/px/edit")
    field = page.locator("#filter-expr")
    field.click()
    field.fill("close > 100")
    status = page.locator("#filter-expr ~ .expr-panel .expr-status")
    expect(status).to_contain_text("Reads as a condition over close")
    preview = page.locator("#filter-expr ~ .expr-panel .expr-preview")
    expect(preview).to_contain_text("row 1:")
    expect(preview).to_contain_text("→")
    expect(preview).to_contain_text("the server evaluates the same grammar")
    field.fill("clos > 100")
    expect(status).to_contain_text("unknown attribute 'clos'")
    expect(status).to_contain_text("this expression may use close")
    assert "is-invalid" in (field.get_attribute("class") or "")
    field.fill("notnull(")
    expect(status).to_contain_text("the expression ends too early")
    field.fill("close > 100")
    page.locator("#filter-expr ~ .expr-panel button", has_text="Add as a filter step").click()
    assert '"op": "filter"' in page.locator("#transform").input_value()
    assert '"expr": "close > 100"' in page.locator("#transform").input_value()
    assert page.errors == []
    ctx.close()


def test_the_hints_offer_the_attributes_and_insert_one(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base, "dana")
    page.goto(f"{base}/workbench/features/{NS}/px/edit")
    field = page.locator("#filter-expr")
    field.click()
    field.fill("clo")
    hints = page.locator("#filter-expr ~ .expr-panel .expr-hints")
    expect(hints).to_contain_text("close")
    hints.locator("button", has_text="close").first.click()
    assert field.input_value() == "close"
    field.fill("sq")
    hints.locator("button", has_text="sqrt").first.click()
    assert field.input_value() == "sqrt("
    assert page.errors == []
    ctx.close()


# ---------------------------------------------------------------- the LaTeX editor
def test_the_preview_follows_the_source_within_a_moment(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    preview = _spec(page, base)
    expect(preview).to_contain_text("Purpose")
    # after \begin{document}: the preview renders the document body, as a build would
    page.evaluate(
        "var cm = document.querySelector('#tab-spec .CodeMirror').CodeMirror;"
        " cm.focus(); cm.setCursor({line: 2, ch: 0});"
    )
    page.keyboard.type("\\section{Typed In A Browser}\n\nA paragraph. $x^2$\n\n")
    expect(preview.locator("h4", has_text="Typed In A Browser")).to_be_visible(timeout=2000)
    assert preview.locator(".katex").count() > 0, "KaTeX renders the maths"
    assert "Typed In A Browser" in _get(page, "spec"), "the textarea keeps the source"
    assert page.errors == []
    ctx.close()


def test_a_section_command_anywhere_is_a_heading_and_no_command_is_shown_raw(site, browser):
    """The preview used to recognise \\section only as the first thing in a paragraph, so a
    source that wrote one straight after a sentence printed the command at the reader. The
    contract now is that structure is structure wherever it stands, and that no backslash
    command reaches the page as text — whether or not this renderer has heard of it."""
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    preview = _spec(page, base)
    _set(
        page,
        "spec",
        "\\section{Purpose}\nWhy it exists.\n\\section{Assumptions}\nStated in full.\n"
        "\\subsubsection{A finer point}\nFiner still. \\somethingnew{kept} and "
        "\\barecommand dropped.\n\\noindent Cost is \\$5, which is 10\\% of the line, "
        "see \\ref{fig:one}\\vspace{1em}.\n",
    )
    expect(preview.locator("h4", has_text="Assumptions")).to_be_visible(timeout=3000)
    expect(preview.locator("h6", has_text="A finer point")).to_be_visible()
    text = preview.inner_text()
    assert "\\" not in text, text
    assert "section" not in text, text
    assert "kept" in text and "somethingnew" not in text, text
    assert "Cost is $5, which is 10% of the line" in text, text
    assert page.errors == []
    ctx.close()


def test_lists_and_display_maths_are_rendered_and_a_table_is_named_as_skipped(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    preview = _spec(page, base)
    _set(
        page,
        "spec",
        "\\section{Purpose}\nThe inputs are:\n"
        "\\begin{itemize}\n\\item the loan to value,\nwhich runs onto a second line\n"
        "\\item the \\texttt{fico} score\n\\end{itemize}\n"
        "The steps:\n\\begin{enumerate}\\item fit\\item score\\end{enumerate}\n"
        "\\begin{align}\n\\label{eq:one}a &= b \\\\\nc &= d\n\\end{align}\n"
        "\\begin{tabular}{ll}\na & b \\\\\n\\end{tabular}\n",
    )
    expect(preview.locator("ul li")).to_have_count(2, timeout=3000)
    expect(preview.locator("ul li").first).to_contain_text("runs onto a second line")
    expect(preview.locator("ul li code")).to_contain_text("fico")
    expect(preview.locator("ol li")).to_have_count(2)
    assert preview.locator(".katex-display").count() > 0, "an align environment is display maths"
    # the table is not typeset here, and the preview says so rather than printing its source
    expect(preview.locator(".small-muted")).to_contain_text("table — rendered in the PDF build")
    # the items carry prose, not the environment's own commands
    items = preview.locator("ul li, ol li").all_inner_texts()
    assert all("\\" not in t and "item" not in t for t in items), items
    assert page.errors == []
    ctx.close()


def test_bracket_matching_marks_the_pair_and_flags_a_stray_one(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _spec(page, base)
    _set(page, "spec", "\\section{Purpose}\n\nf(x, g(y))\n")
    page.locator("#tab-spec .CodeMirror-code").click()
    page.keyboard.press("Control+Home")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("End")  # just after the closing bracket of f(...)
    expect(page.locator(".cm-maya-bracket")).to_have_count(2, timeout=3000)
    _set(page, "spec", "\\section{Purpose}\n\nf(x\n")
    page.locator("#tab-spec .CodeMirror-code").click()
    page.keyboard.press("Control+Home")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    expect(page.locator(".cm-maya-bracket-bad")).to_have_count(1, timeout=3000)
    assert page.errors == []
    ctx.close()


def test_find_and_replace_counts_the_matches_and_replaces_them_all(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _spec(page, base)
    _set(page, "spec", "\\section{Purpose}\n\nalpha and alpha and alpha.\n")
    page.click("[data-find-for=spec]")
    bar = page.locator("#tab-spec .cm-find")
    expect(bar).to_be_visible()
    bar.locator("[data-find]").fill("alpha")
    expect(bar.locator("[data-find-count]")).to_contain_text("3 match(es)")
    bar.locator("[data-find-next]").click()
    expect(bar.locator("[data-find-count]")).to_contain_text("1 of 3")
    bar.locator("[data-replace]").fill("beta")
    bar.locator("[data-find-all]").click()
    expect(bar.locator("[data-find-count]")).to_contain_text("3 replaced")
    assert "alpha" not in _get(page, "spec") and _get(page, "spec").count("beta") == 3
    bar.locator("[data-find-close]").click()
    expect(bar).to_be_hidden()
    assert page.errors == []
    ctx.close()


def test_prose_is_spell_checked_and_code_is_not(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _spec(page, base)
    prose = page.evaluate(
        "document.querySelector('#tab-spec .CodeMirror').CodeMirror.getInputField()"
        ".getAttribute('spellcheck')"
    )
    assert prose == "true", "the browser's own dictionary underlines the prose"
    _code(page, base)
    code = page.evaluate(
        "document.querySelector('#tab-code .CodeMirror').CodeMirror.getInputField()"
        ".getAttribute('spellcheck')"
    )
    assert code == "false", "a code editor underlining every identifier is noise"
    assert page.errors == []
    ctx.close()


def test_a_figure_is_embedded_in_the_document_and_drawn_in_the_preview(site, browser, tmp_path):
    base, w = site
    ctx, page = _page(browser)
    _login(page, base)
    preview = _spec(page, base)
    _set(page, "spec", "\\section{Purpose}\n\nBefore the figure.\n")
    path = tmp_path / "curve.png"
    path.write_bytes(PNG)
    page.set_input_files("#spec-figure", str(path))
    expect(page.locator("[data-figure-note=spec]")).to_contain_text("is in the document")
    source = _get(page, "spec")
    assert "% maya-figure curve.png" in source and "%~" in source
    assert "\\includegraphics[width=0.8\\textwidth]{curve.png}" in source
    # guarded, so a build that cannot write the image out prints a box and still succeeds
    assert "\\IfFileExists{curve.png}" in source and "could not write it out" in source
    expect(preview.locator("figure img")).to_be_visible(timeout=3000)
    assert preview.locator("figure img").get_attribute("src").startswith("data:image/png;base64,")
    expect(preview.locator("figcaption")).to_contain_text("curve")
    # and it survives the round trip through the server
    page.locator("button", has_text="Save document").click()
    page.wait_for_load_state("networkidle")
    saved = w.p.models.get(w.mona, f"{NS}/linear")["versions"][0]["spec_latex"]
    assert "% maya-figure curve.png" in saved
    assert page.errors == []
    ctx.close()


def test_a_figure_too_large_is_refused_with_its_size(site, browser, tmp_path):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _spec(page, base)
    big = tmp_path / "huge.png"
    big.write_bytes(PNG + b"\0" * (220 * 1024))
    page.set_input_files("#spec-figure", str(big))
    expect(page.locator("[data-figure-note=spec]")).to_contain_text("has to stay under 200 kB")
    assert "maya-figure huge.png" not in _get(page, "spec")
    assert page.errors == []
    ctx.close()


def test_bibtex_goes_into_the_document_and_the_citation_is_numbered(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    preview = _spec(page, base)
    _set(page, "spec", "\\section{Purpose}\n\nAs shown by \\cite{black1973}.\n")
    page.click("[data-bib-for=spec] summary")
    page.fill("#spec-bib", BIB)
    page.click("[data-bib-apply]")
    expect(page.locator("[data-bib-note]")).to_contain_text(
        "1 entry/entries are now in the document"
    )
    source = _get(page, "spec")
    assert "\\begin{filecontents*}[overwrite]{refs.bib}" in source
    assert "\\bibliography{refs}" in source and "@article{black1973" in source
    expect(preview).to_contain_text("[1]")
    expect(preview.locator("h4", has_text="References")).to_be_visible()
    expect(preview.locator(".bib-list li")).to_contain_text("Black, Fischer")
    _set(page, "spec", source.replace("\\cite{black1973}", "\\cite{missing}"))
    expect(preview).to_contain_text("[?missing]")
    assert page.errors == []
    ctx.close()


def test_the_outline_lists_the_sections_with_their_completeness(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _spec(page, base)
    _set(
        page,
        "spec",
        "\\section{Purpose}\n\nStated in full.\n\n\\section{Assumptions}\n\n"
        "\\subsection{Later}\n\nA detail.\n",
    )
    page.locator("summary", has_text="Outline and completeness").click()
    outline = page.locator("[data-outline-for=spec]")
    expect(outline).to_contain_text("Purpose")
    expect(outline).to_contain_text("Assumptions")
    rows = outline.locator("li").all_inner_texts()
    assert any("Assumptions" in r and "empty" in r for r in rows), rows
    assert any("Purpose" in r and "words" in r for r in rows), rows
    outline.locator("button", has_text="Later").click()
    cursor = page.evaluate(
        "document.querySelector('#tab-spec .CodeMirror').CodeMirror.getCursor().line"
    )
    assert cursor == 6, "clicking a section jumps the editor to its line"
    assert page.errors == []
    ctx.close()


def test_the_code_editor_names_the_line_the_ladder_would_refuse(site, browser):
    base, _ = site
    ctx, page = _page(browser)
    _login(page, base)
    _code(page, base)
    checks = page.locator("[data-checks-for=src]")
    expect(checks).to_contain_text("Nothing the static ban would refuse")
    _set(
        page,
        "src",
        "import os\n\n\nclass Model:\n    def fit(self, X, y, ctx):\n"
        "        open('/etc/passwd')\n        return {}\n",
    )
    expect(checks).to_contain_text("line 6")
    expect(checks).to_contain_text("the filesystem is not available")
    # the seam: a deployment may plug a real language server in behind it
    page.evaluate(
        "window.MayaEditors.languageServer = {diagnose: function () {"
        " return [{line: 1, message: 'from the plugged-in server'}]; }}"
    )
    _set(page, "src", "x = 1\n")
    expect(checks).to_contain_text("from the plugged-in server")
    assert page.errors == []
    ctx.close()


def test_a_py_file_chosen_from_disk_fills_the_artifact_editor(site, browser):
    """The artifact box takes a file as well as a paste; the form still submits the text."""
    base, _ = site
    ctx, page = _page(browser)
    try:
        _login(page, base)
        _code(page, base)
        source = "import numpy as np\n\nclass Model:\n    def predict(self, X, params, ctx):\n        return X['x']\n"
        page.set_input_files(
            "#src-file",
            files=[{"name": "model.py", "mimeType": "text/x-python", "buffer": source.encode()}],
        )
        page.wait_for_function(
            "MayaEditors.instances['src'].get().includes('class Model')", timeout=5000
        )
        assert _get(page, "src") == source
        assert page.input_value("#src") == source  # what the form submits
        assert "Loaded model.py" in page.inner_text("[data-load-status=src]")
        assert not page.errors, page.errors
    finally:
        ctx.close()
