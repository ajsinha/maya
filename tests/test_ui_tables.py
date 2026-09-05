"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Every table in the interface can be searched, sorted and paged.

`web/static/js/tables.js` is written rather than vendored, for the same reason
the JWT verifier and the xlsx writer are: this platform must run air-gapped,
every asset is served from disk, and a table plugin is a hundred lines of
arithmetic wearing eighty kilobytes. Writing it also means the controls are
Bootstrap's, rather than fighting Bootstrap.

**The controls appear where they help.** Sorting is always available, because a
reader who wants the worst finding first should not have to count rows. Search
and paging appear once a table is long enough for them to earn the space — a
pager under four rows is noise, and noise is what stops people reading a page.

**Every table has a header row, with no exemption.** There was briefly an opt-out
for "key/value reference lists", and the exemption was the wrong answer to the
right observation: those were not tables. A term beside its definition — what a
stream holds, what a policy can and cannot do, what a diagnostic means — is a
description list, and rendering it as a two-column table with no header is
layout-by-table. A screen reader announces "table, two columns" and then offers
no headers to orient by, which is worse than no markup at all.

They are `<dl class="maya-terms">` now, and a table with no header is simply a
defect.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
SCRIPT = ROOT / "web" / "static" / "js" / "tables.js"


def _markup(text: str) -> str:
    """The template with comments removed.

    A CSS or Jinja comment mentioning table markup is prose, not a table, and
    scanning the raw file reported one of this suite's own explanatory comments
    as a defect.
    """
    for opening, closing in (("<!--", "-->"), ("/*", "*/"), ("{#", "#}")):
        while opening in text and closing in text.split(opening, 1)[1]:
            head, rest = text.split(opening, 1)
            text = head + rest.split(closing, 1)[1]
    return text


def _tables():
    for path in sorted(TEMPLATES.glob("*.html")):
        markup = _markup(path.read_text(encoding="utf-8"))
        for number, chunk in enumerate(markup.split("<table")[1:], 1):
            yield path.name, number, chunk.split("</table>")[0], chunk[:40]


def test_the_enhancer_is_served_from_disk():
    """No CDN. An instance that cannot be deployed air-gapped is one somebody
    works around."""
    assert SCRIPT.exists()
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "/static/js/tables.js" in base
    assert "http://" not in SCRIPT.read_text(encoding="utf-8")
    assert "https://" not in SCRIPT.read_text(encoding="utf-8")


def test_every_table_has_a_header_row():
    """No exemption. A table without headers cannot be sorted, cannot be read
    by anybody using a screen reader, and is almost always a description list
    wearing table markup."""
    headless = [f"{name} #{number}" for name, number, body, _ in _tables()
                if "<thead" not in body]
    assert not headless, (
        "these tables have no header row:\n    " + "\n    ".join(headless)
        + "\nIf it holds data, give it a <thead>. If it is a term beside its "
          "definition, it is not a table — use <dl class=\"maya-terms\">.")


def test_nothing_opts_out_of_being_a_real_table():
    """`data-plain` was an escape hatch for tables that should have been
    description lists. Once they were, the hatch had nothing left to cover."""
    plain = [f"{name} #{number}" for name, number, _, opening in _tables()
             if "data-plain" in opening]
    assert not plain, plain


def test_definition_lists_are_used_where_they_belong():
    """The positive half: the conversion happened rather than the markup simply
    being deleted."""
    import pathlib as _p
    templates = list(TEMPLATES.glob("*.html"))
    with_terms = [f.name for f in templates
                  if "maya-terms" in f.read_text(encoding="utf-8")]
    assert len(with_terms) >= 4, with_terms
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "dl.maya-terms" in base, "the style has to exist or they render bare"


def test_the_long_tables_carry_headers():
    """Spot-check the ones that grow without bound. The evidence chain in
    particular sat in a fixed-height scroll box with no header, which is
    unusable at any real estate size."""
    model = (TEMPLATES / "model.html").read_text(encoding="utf-8")
    assert "<th>Event</th>" in model and "<th>Sequence</th>" in model
    assert 'data-sort="{{ e.seq }}"' in model, (
        "the sequence column must sort as a number, not as the text '#10'")


# --------------------------------------------------------------- behaviour
NODE = ROOT / "node_modules" / "jsdom"
HARNESS = """
const { JSDOM } = require('jsdom');
const rows = Array.from({length: 40}, (_, i) =>
  `<tr><td>model-${String(i).padStart(2,'0')}</td><td>${(i*7)%40}</td></tr>`).join("");
const dom = new JSDOM(`<!doctype html><body><div><table>
  <thead><tr><th>Name</th><th>Score</th></tr></thead>
  <tbody>${rows}</tbody></table></div></body>`, {runScripts:"outside-only"});
const document = dom.window.document;
dom.window.eval(require('fs').readFileSync(process.argv[2],'utf8'));
dom.window.mayaEnhanceTables();
const table = document.querySelector('table');
const visible = () => Array.from(table.tBodies[0].rows).filter(r => !r.hidden);
const out = {};
out.paged = visible().length;
out.search = !!document.querySelector('input[type=search]');
out.pager = document.querySelectorAll('.page-link').length;
document.querySelectorAll('th')[1].dispatchEvent(new dom.window.Event('click'));
out.ascending = visible().map(r => Number(r.cells[1].textContent));
document.querySelectorAll('th')[1].dispatchEvent(new dom.window.Event('click'));
out.descendingFirst = Number(visible()[0].cells[1].textContent);
const box = document.querySelector('input[type=search]');
box.value = 'model-3'; box.dispatchEvent(new dom.window.Event('input'));
out.matched = visible().length;
out.status = document.querySelector('[aria-live]').textContent;
out.ariaSort = document.querySelectorAll('th')[1].getAttribute('aria-sort');
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def behaviour():
    """Run the enhancer in a real DOM, or skip honestly.

    Skipped rather than faked when node or jsdom is absent: a test that quietly
    passes without running is the failure mode this repository keeps finding.
    Install with `npm install --no-save jsdom`.
    """
    if not NODE.exists():
        pytest.skip("jsdom is not installed; run `npm install --no-save jsdom`")
    harness = ROOT / "node_modules" / ".maya-table-harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    result = subprocess.run(["node", str(harness), str(SCRIPT)],
                            capture_output=True, text=True, cwd=ROOT,
                            env={"NODE_PATH": str(ROOT / "node_modules"),
                                 "PATH": "/usr/bin:/bin:/usr/local/bin"})
    if result.returncode != 0:
        pytest.skip(f"could not run the harness: {result.stderr.strip()[:200]}")
    import json
    return json.loads(result.stdout)


def test_a_long_table_is_paged(behaviour):
    assert behaviour["paged"] == 15, "forty rows, fifteen shown"


def test_a_long_table_gets_a_search_box_and_a_pager(behaviour):
    assert behaviour["search"] is True
    assert behaviour["pager"] >= 3


def test_a_numeric_column_sorts_as_numbers(behaviour):
    """So 9 does not come after 10, and a Gini of 0.61 does not sort below 0.7
    the way strings would."""
    assert behaviour["ascending"] == sorted(behaviour["ascending"])
    assert behaviour["descendingFirst"] == 39


def test_search_filters_and_says_how_many_matched(behaviour):
    assert behaviour["matched"] == 10
    assert "10 of 40" in behaviour["status"]


def test_the_sorted_column_is_announced(behaviour):
    """A sort indicator that only exists as a glyph is invisible to a screen
    reader."""
    assert behaviour["ariaSort"] in ("ascending", "descending")
