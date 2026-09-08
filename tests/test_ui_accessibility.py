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

import pytest

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


# ------------------------------------------------------------------ contrast
def _luminance(colour: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    h = colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _palette() -> dict:
    """The tokens as the stylesheet actually declares them."""
    body = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    block = body.split(":root{", 1)[1].split("}", 1)[0]
    found = dict(re.findall(r"--([a-z-]+):(#[0-9A-Fa-f]{6})", block))
    assert {"crimson", "ink", "slate", "muted", "rule", "parch", "edge"} <= set(found), found
    return {"white": "#FFFFFF", **found}


class TestContrastIsMeasuredRatherThanJudged:
    """`--muted` was #7A7F87 — 4.03 on white and 3.64 on the striped row,
    against a 4.5 requirement. It carries the gloss under every menu entry,
    every `.text-muted` note and every definition, all set SMALLER than body
    text, so the large-text allowance applies to none of them. The explanatory
    half of the interface was the half that failed.
    """

    #: Every token that carries text, and the grounds it appears on.
    TEXT_ON = [("ink", "white"), ("ink", "parch"),
               ("slate", "white"), ("slate", "parch"),
               ("muted", "white"), ("muted", "parch"),
               ("crimson", "white"), ("crimson", "parch")]

    def test_every_text_pair_clears_aa(self):
        palette = _palette()
        failures = []
        for fg, bg in self.TEXT_ON:
            ratio = contrast(palette[fg], palette[bg])
            if ratio < 4.5:
                failures.append(f"--{fg} on --{bg}: {ratio:.2f}")
        assert failures == [], (
            "these carry text below WCAG AA 4.5:1, and every one of them is "
            "used at a font size SMALLER than body text, so the large-text "
            "allowance does not apply: " + ", ".join(failures))

    def test_white_on_the_crimson_bar_clears_aa(self):
        assert contrast("#FFFFFF", _palette()["crimson"]) >= 4.5

    def test_a_controls_own_edge_clears_the_three_to_one_rule(self):
        """`--rule` is 1.47 on white. Fine for a table rule, which is
        decoration, and not fine for the edge of an input: the boundary is what
        tells somebody where to type."""
        palette = _palette()
        assert contrast(palette["edge"], palette["white"]) >= 3.0
        assert "border-color:var(--edge)" in (
            ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")

    @staticmethod
    def _tokens(css, theme):
        """The custom properties in force for one theme, resolved to hex.

        The palette moved into tokens so a theme could swap it, and this scan
        measured hex — so it silently matched nothing and reported that
        everything passed. Resolving the tokens first is what keeps the
        measurement honest, and it buys the dark theme the same scrutiny the
        light one has always had.
        """
        blocks = [re.search(r":root\{(.*?)\}", css, re.S)]
        if theme == "dark":
            blocks.append(re.search(r':root\[data-theme="dark"\]\{(.*?)\}',
                                    css, re.S))
        values = {}
        for block in blocks:
            if block is None:
                continue
            for name, value in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);",
                                          block.group(1)):
                values[name] = value.strip()
        # One pass of substitution is enough: no token here points at a token
        # that points at a third.
        resolved = {}
        for name, value in values.items():
            hit = re.fullmatch(r"var\(--([a-z0-9-]+)\)", value)
            if hit:
                value = values.get(hit.group(1), value)
            if re.fullmatch(r"#[0-9A-Fa-f]{3,6}", value):
                if len(value) == 4:
                    value = "#" + "".join(c * 2 for c in value[1:])
                resolved[name] = value
        return resolved

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_every_badge_carries_its_text_at_aa(self, theme):
        """The tier badge is the most consequential label on these screens, and
        two of the four failed: amber at 3.20:1 and grey at 4.03:1, both set
        small and bold — exactly where "it looks fine" stops being evidence.

        Measured in BOTH themes. A dark theme is where this goes wrong most
        easily: the fills lighten, and white text that was correct on a dark
        crimson is unreadable on a pale pink one.
        """
        css = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
        tokens = self._tokens(css, theme)
        assert tokens.get("crimson"), "the token block did not parse"

        def hexof(value):
            hit = re.fullmatch(r"var\(--([a-z0-9-]+)\)", value.strip())
            if hit:
                return tokens.get(hit.group(1))
            if re.fullmatch(r"#[0-9A-Fa-f]{6}", value.strip()):
                return value.strip()
            if re.fullmatch(r"#[0-9A-Fa-f]{3}", value.strip()):
                return "#" + "".join(c * 2 for c in value.strip()[1:])
            return None

        pairs = re.findall(
            r"\.([a-z0-9-]+)\{background:\s*(var\(--[a-z0-9-]+\)|#[0-9A-Fa-f]{3,6});"
            r"\s*color:\s*(var\(--[a-z0-9-]+\)|#[0-9A-Fa-f]{3,6})", css)
        assert len(pairs) >= 6, \
            "the scan found almost nothing, which means it is looking wrongly"

        failures = []
        for name, ground, ink in pairs:
            back, front = hexof(ground), hexof(ink)
            if not back or not front:
                continue
            ratio = contrast(front, back)
            if ratio < 4.5:
                failures.append(f".{name}: {ratio:.2f} in {theme}")
        assert failures == [], "badges below AA: " + ", ".join(failures)

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_a_menu_item_contrasts_with_the_menu_and_not_with_the_bar(self, theme):
        """The Manage and Admin menus hang off the crimson bar in the DOM and
        are painted on the page's own surface. `.navbar a{color:var(--on-bar)}`
        is right for the bar and wrong for them: in the light theme `--on-bar`
        is white, the panel is white, and every item LABEL was invisible —
        leaving a menu that read as a column of grey descriptions with nothing
        to click.

        It survived because in the dark theme `--on-bar` is a pale pink on a
        dark panel, which is legible by accident. Two themes, one of them
        looked at, and the accident is the one that got looked at.
        """
        css = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
        tokens = self._tokens(css, theme)
        rule = re.search(
            r"\.navbar \.dropdown-menu a,\s*\n?\.navbar \.dropdown-item\{color:\s*"
            r"var\(--([a-z0-9-]+)\)", css)
        assert rule, ("nothing sets the colour of a link inside a navbar "
                      "dropdown, so it inherits the BAR's text colour")
        ink = tokens[rule.group(1)]
        for surface in ("surface", "parch"):
            ratio = contrast(ink, tokens[surface])
            assert ratio >= 4.5, (
                f"a menu item is {ratio:.2f}:1 on --{surface} in the {theme} "
                f"theme; the bar's own --on-bar would be "
                f"{contrast(tokens['on-bar'], tokens[surface]):.2f}:1, which is "
                f"what it inherited before")

    def test_the_measurement_can_fail(self):
        """A contrast check that passes everything is a check nobody can trust."""
        assert contrast("#CCCCCC", "#FFFFFF") < 4.5
        assert contrast("#000000", "#FFFFFF") > 20


class TestKeyboardFocusIsVisible:
    """Only `.navbar .dropdown-item` had a focus ring. Everything else fell back
    to the browser default, which Bootstrap's reset removes on buttons and
    links — so somebody navigating by keyboard could not see where they were on
    any screen in the platform.
    """

    @staticmethod
    def _css() -> str:
        return (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")

    def test_every_focusable_kind_gets_a_ring(self):
        css = self._css()
        rule = [block for block in css.split("}")
                if ":focus-visible" in block and "outline:3px" in block]
        assert rule, "there is no focus-visible rule at all"
        combined = " ".join(rule)
        for element in ("a:", "button:", "input:", "select:", "textarea:"):
            assert f"{element}focus-visible" in combined, element

    def test_the_ring_inverts_on_every_crimson_surface(self):
        """A crimson ring on a crimson surface is not a ring.

        This asserted the inversion on the NAVBAR and stopped there — and the
        design has a second crimson surface: `table.maya thead th`. `tables.js`
        sets `tabIndex = 0` on every header of every table with two or more
        rows, so every sortable column on every screen was a tab stop with a
        1:1 contrast focus ring. Roughly forty invisible stops on
        /admin/principals alone.

        Enumerated from the stylesheet rather than named, so a THIRD crimson
        surface cannot be added without this failing.
        """
        css = re.sub(r"/\*.*?\*/", "", self._css(), flags=re.S)
        assert "outline:3px solid #fff" in css

        #: Crimson surfaces that hold no focusable content — a rule, a dot, a
        #: pseudo-element. Named rather than pattern-matched, so adding one is a
        #: decision somebody writes down.
        decorative = {".accent", ".flow .step.done .dot", ".sig.declined .ic",
                      # Tier badges are `<span>`s stating a fact. Nothing on
                      # them takes focus, and the crimson one is the same fill
                      # as the table header that IS focusable and IS inverted.
                      ".tier-1", ".tier-2", ".tier-3", ".tier-4"}

        painted = set(re.findall(
            r"([^{}]+)\{[^{}]*background:\s*var\(--crimson\)", css))
        surfaces = {sel.strip() for block in painted
                    for sel in block.split(",")
                    if sel.strip() and not sel.strip().startswith("@")
                    and "::" not in sel}          # a pseudo-element cannot focus
        surfaces -= decorative
        assert surfaces, "no crimson surface found; the pattern needs updating"

        inverted = re.search(r"([^{}]+)\{\s*outline:3px solid #fff", css)
        assert inverted, "nothing inverts the ring at all"
        for surface in surfaces:
            root = surface.split(":")[0].strip()
            assert root in inverted.group(1), (
                f"'{root}' is painted crimson and its focus ring is not "
                f"inverted, so focus on it is invisible. Either invert it, or "
                f"add it to `decorative` if nothing on it can take focus.")

    def test_there_is_a_way_past_the_navigation(self):
        """33 focusable elements in the bar against 8 in the page, and no skip
        link — so a keyboard user tabbed the whole mega-menu on every page
        load, on every page. WCAG 2.4.1, Level A."""
        base = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
        assert 'class="skip-link" href="#main"' in base
        assert 'id="main"' in base
        # And it must be the FIRST thing focusable, or it is not a skip link.
        body = base.split("<body>", 1)[1]
        assert body.strip().startswith('<a class="skip-link"')
        assert ".skip-link:focus{left:0" in self._css()

    def test_it_is_focus_visible_and_not_focus(self):
        """`:focus` would leave a ring behind after every mouse click, which is
        how a focus style gets removed again a week later."""
        css = self._css()
        assert "a:focus-visible" in css
        assert not re.search(r"\ba:focus\s*[,{]", css)

    def test_reduced_motion_is_honoured(self):
        assert "prefers-reduced-motion:reduce" in self._css()


class TestAnOutcomeIsAnnounced:
    """`grep -rn aria-live web/templates/` returned ZERO hits.

    Every result on the screens added most recently was injected into a plain
    `<div>`: add, roles, password, suspend, reinstate, role define/edit/remove,
    key issue/revoke — including the once-only secret — the dependency answer
    and the delete outcome. A screen-reader user clicked Suspend, heard
    nothing, and had no way to know whether it worked. The only live region in
    the platform was the table search's row count.
    """

    #: Containers a handler writes an outcome into. Enumerated from the
    #: JavaScript rather than listed by hand, so a new one is caught.
    def _written_into(self):
        import re as _re

        targets = set()
        for script in (ROOT / "web" / "static" / "js").glob("*.js"):
            body = script.read_text(encoding="utf-8")
            for match in _re.finditer(
                    r'(?:say|\$)\(\s*"#([a-z0-9-]*result[a-z0-9-]*|'
                    r'[a-z0-9-]*msg)"', body):
                targets.add(match.group(1))
        return targets

    def test_every_result_container_is_a_live_region(self):
        markup = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "web" / "templates").glob("*.html"))
        silent = []
        for target in sorted(self._written_into()):
            found = re.search(
                r'<[^>]*id="' + re.escape(target) + r'"[^>]*>', markup)
            if found is None:
                continue                       # written by a page not in templates/
            if "aria-live" not in found.group(0):
                silent.append(target)
        assert not silent, (
            f"these containers receive an outcome and announce nothing, so a "
            f"screen-reader user acts and hears silence: {silent}. Add "
            f'role="status" aria-live="polite".')


class TestTheThemeIsAThingSomebodyChooses:
    """Three states, not two.

    "System" is the default and is a POSITION rather than the absence of a
    choice: somebody whose machine switches at dusk should not have to correct
    this platform twice a day, and a two-way toggle cannot express that.
    """

    def _base(self):
        return (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")

    def test_all_three_choices_are_offered(self, client):
        from tests.api_helpers import login

        login(client)
        body = client.get("/dashboard").text
        for choice in ("light", "dark", "system"):
            assert f'data-theme="{choice}"' in body, choice

    def test_the_choice_is_applied_before_the_first_paint(self):
        """A deferred script shows a white page to somebody who chose dark.
        A flash of the wrong theme is the most visible bug a theme switch has,
        so the part that cannot wait is inline in <head>, above the stylesheet.
        """
        base = self._base()
        head = base.split("</head>", 1)[0]
        assert "maya.theme" in head
        assert head.index("maya.theme") < head.index("fonts.css")

    def test_every_colour_resolves_through_a_token(self):
        """The palette moved into custom properties so a theme could swap it.
        A colour written as hex in a rule is one the theme cannot reach — which
        is what made the first dark mode legible on some screens and not
        others."""
        base = self._base()
        rules = base.split("html{color-scheme:light dark;}", 1)[1]
        rules = rules.split("</style>", 1)[0]
        rules = re.sub(r"/\*.*?\*/", "", rules, flags=re.S)
        # `@media print` is deliberately literal: paper has one theme, and a
        # dark page sent to a printer is a black rectangle.
        rules = re.sub(r"@media print\{.*?\}\s*\}", "", rules, flags=re.S)
        stray = sorted(set(re.findall(r"#[0-9A-Fa-f]{3,6}\b", rules)))
        # `#fff` survives only as the inverted focus ring, which must stay
        # white on both themes because both bars are dark behind it.
        assert stray in ([], ["#fff"]), f"hardcoded colour in a rule: {stray}"

    def test_no_template_paints_its_own_colour(self):
        """Same rule, one layer out. Twelve templates carried their own hex and
        every one of them was a patch of light in the dark theme."""
        offenders = {}
        for path in sorted((ROOT / "web" / "templates").glob("*.html")):
            if path.name == "base.html":
                continue
            text = re.sub(r"&#\d+;", "", path.read_text(encoding="utf-8"))
            found = sorted(set(re.findall(r"#[0-9A-Fa-f]{6}\b", text)))
            if found:
                offenders[path.name] = found
        assert not offenders, f"templates painting their own colours: {offenders}"

    def test_dark_defines_every_token_light_does(self):
        """A token defined only in `:root` keeps its light value in dark, which
        is how a dark theme ends up with one white card on it."""
        base = self._base()
        light = re.search(r":root\{(.*?)\}", base, re.S).group(1)
        dark = re.search(r':root\[data-theme="dark"\]\{(.*?)\}', base, re.S).group(1)
        names = lambda block: set(re.findall(r"--([a-z0-9-]+)\s*:", block))
        # The brand crimson and the fonts do not move between themes.
        unchanged = {"sans", "serif", "code"}
        missing = names(light) - names(dark) - unchanged
        assert not missing, f"not redefined for dark: {sorted(missing)}"

    def test_the_media_query_and_the_toggle_agree(self):
        """Three states means the OS preference must be honoured when nobody
        has chosen, and overridden in BOTH directions when somebody has."""
        base = self._base()
        assert "prefers-color-scheme: dark" in base
        assert ':root:not([data-theme="light"])' in base, \
            "an explicit light choice must beat a dark OS"
        assert ':root[data-theme="dark"]' in base, \
            "an explicit dark choice must beat a light OS"


class TestTheTypefacesAreHere:
    def test_they_are_vendored_and_served(self, client):
        css = ROOT / "web" / "static" / "vendor" / "fonts" / "fonts.css"
        assert css.exists()
        assert client.get("/static/vendor/fonts/fonts.css").status_code == 200
        files = sorted((css.parent / "files").glob("*.woff2"))
        assert files, "no font files vendored"
        assert client.get(
            f"/static/vendor/fonts/files/{files[0].name}").status_code == 200

    def test_nothing_is_fetched_from_a_font_host(self):
        """`font-src 'self'`, and the interface has to render air-gapped."""
        css = (ROOT / "web" / "static" / "vendor" / "fonts"
               / "fonts.css").read_text(encoding="utf-8")
        assert "https://" not in css and "//fonts." not in css

    def test_each_role_has_a_face_and_a_fallback(self):
        base = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
        for token in ("--sans", "--serif", "--code"):
            line = re.search(rf"{token}:([^;]+);", base).group(1)
            assert "," in line, f"{token} has no fallback stack"
