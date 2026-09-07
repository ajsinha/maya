"""Every form control names itself.

161 of 247 did not. A control with a visible `<label>` beside it and no
`for`/`id` pair is unlabelled as far as a screen reader is concerned — the
association is what carries the name, not the proximity — and 58 more carried
only a `placeholder`, which is not a label either: it disappears the moment
somebody types, and several assistive technologies never announce it at all.

This is not a cosmetic finding. MAYA is a control platform for regulated firms,
and a form somebody cannot fill in without sight is a control they cannot
operate.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"

#: `hidden` names nothing a person interacts with; `submit` and `button` take
#: their name from their own text.
UNNAMED_BY_NATURE = re.compile(r'type="(hidden|submit|button)"')
CONTROL = re.compile(r"<(input|select|textarea)\b([^>]*?)/?>", re.S)


def _unlabelled(body: str):
    labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', body))
    for match in CONTROL.finditer(body):
        attrs = match.group(2)
        if UNNAMED_BY_NATURE.search(attrs):
            continue
        ident = re.search(r'\bid="([^"]+)"', attrs)
        if "aria-label" in attrs or "aria-labelledby" in attrs:
            continue
        if ident and ident.group(1) in labelled:
            continue
        yield attrs.strip()[:70]


def test_every_control_in_every_template_is_named() -> None:
    offenders = []
    for path in sorted(TEMPLATES.glob("*.html")):
        offenders += [f"{path.name}: <… {a}>" for a in _unlabelled(path.read_text(
            encoding="utf-8"))]
    assert offenders == [], (
        f"{len(offenders)} form control(s) carry no programmatic name — a "
        "`<label>` sitting beside a control does not name it, only `for`/`id` "
        "or `aria-label` does:\n  " + "\n  ".join(offenders[:20]))


def test_the_scan_can_see_an_unlabelled_control() -> None:
    """A scan that matched nothing would pass on an interface with no labels at
    all, which is the shape of defect this repository keeps finding."""
    assert list(_unlabelled('<input class="x" name="y">')) == ['class="x" name="y"']
    assert list(_unlabelled(
        '<label for="a">A</label><input id="a" name="y">')) == []
    assert list(_unlabelled('<input aria-label="A" name="y">')) == []
    assert list(_unlabelled('<input type="hidden" name="csrf">')) == []


def test_a_label_that_points_at_nothing_is_caught_too() -> None:
    """`for="x"` with no `id="x"` names nothing, and reads as done."""
    dangling = []
    for path in sorted(TEMPLATES.glob("*.html")):
        body = path.read_text(encoding="utf-8")
        ids = set(re.findall(r'\bid="([^"]+)"', body))
        for target in re.findall(r'<label[^>]*\bfor="([^"]+)"', body):
            # A `for` built from a Jinja expression is resolved at render time.
            if "{{" in target or "{%" in target:
                continue
            if target not in ids:
                dangling.append(f"{path.name}: for=\"{target}\"")
    assert dangling == [], (
        "these labels point at an id that does not exist in their template: "
        + ", ".join(dangling))


def test_no_two_controls_share_an_id() -> None:
    """Two controls with one id is one labelled control and one that only looks
    labelled."""
    clashes = []
    for path in sorted(TEMPLATES.glob("*.html")):
        body = path.read_text(encoding="utf-8")
        seen = set()
        for ident in re.findall(r'\bid="([^"]+)"', body):
            if "{{" in ident:
                continue
            if ident in seen:
                clashes.append(f"{path.name}: id=\"{ident}\"")
            seen.add(ident)
    assert clashes == [], ", ".join(clashes)
