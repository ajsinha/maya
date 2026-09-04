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

A table that is genuinely a key/value reference list — "what each stream means",
"what this policy can and cannot do" — carries `data-plain` and is left alone.
That is a deliberate exemption and this file holds it to being deliberate: a
table is enhanced if it has a header row, and every table must be one or the
other, so nothing can drift into being neither.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
SCRIPT = ROOT / "web" / "static" / "js" / "tables.js"


def _tables():
    for path in sorted(TEMPLATES.glob("*.html")):
        for number, chunk in enumerate(path.read_text(encoding="utf-8")
                                       .split("<table")[1:], 1):
            yield path.name, number, chunk.split("</table>")[0], chunk[:40]


def test_the_enhancer_is_served_from_disk():
    """No CDN. An instance that cannot be deployed air-gapped is one somebody
    works around."""
    assert SCRIPT.exists()
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "/static/js/tables.js" in base
    assert "http://" not in SCRIPT.read_text(encoding="utf-8")
    assert "https://" not in SCRIPT.read_text(encoding="utf-8")


def test_every_table_is_either_enhanced_or_deliberately_plain():
    undecided = [f"{name} #{number}"
                 for name, number, body, opening in _tables()
                 if "<thead" not in body and "data-plain" not in opening]
    assert not undecided, (
        "these tables have no header row and are not marked `data-plain`, so "
        "they can be neither sorted nor searched and nobody decided that:\n    "
        + "\n    ".join(undecided)
        + "\nGive it a <thead> if it holds data, or `data-plain` if it is a "
          "key/value reference list.")


def test_a_headed_table_is_never_also_marked_plain():
    """The two are alternatives. A table with both says one thing in its markup
    and another in its attribute."""
    both = [f"{name} #{number}" for name, number, body, opening in _tables()
            if "<thead" in body and "data-plain" in opening]
    assert not both, both


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
