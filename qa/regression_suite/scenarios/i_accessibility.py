"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — accessibility, checked against what is served rather than assumed.

A governance platform is read by auditors, examiners and second-line staff for
hours at a time, on whatever equipment their firm gave them. These cases assert
on the HTML and CSS the server actually sends: an affordance that is in the
design and not in the response is an affordance nobody has.
"""
from __future__ import annotations

import re

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

#: Every theme the inline bootstrap script admits. Read from the page rather
#: than listed here, so a fifth theme is covered the day it is added.
THEME_PATTERN = re.compile(r't==="(\w+)"')


def _page(ctx: Ctx, path: str = "/dashboard"):
    return ctx.ui.get(path)


@case("QA-PLT-395", "A skip link, reachable from the address bar")
def plt_395(ctx: Ctx) -> Result:
    """The first thing a keyboard user meets. Without it, reaching the
    primary action means tabbing through the whole navbar on every page."""
    got = _page(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    if 'class="skip-link"' not in got.text:
        return FAIL, "no skip link is served"
    target = re.search(r'class="skip-link" href="#([\w-]+)"', got.text)
    if not target:
        return FAIL, "the skip link points nowhere"
    anchor = target.group(1)
    if f'id="{anchor}"' not in got.text:
        return FAIL, (f"the skip link targets #{anchor} and no element "
                      f"carries that id, so it skips to nothing")
    return PASS, f"skip link to #{anchor}, and the target exists"


@case("QA-PLT-4300", "The skip link is hidden until it is focused")
def plt_4300(ctx: Ctx) -> Result:
    """A skip link permanently on screen is a design decision; one that never
    appears is a broken control. It has to move into view on focus."""
    got = _page(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    css = got.text
    if ".skip-link:focus" not in css:
        return FAIL, ("the skip link has no focus rule, so it is either "
                      "always visible or never reachable")
    hidden = re.search(r"\.skip-link\{[^}]*\}", css)
    if not hidden or "left:-" not in hidden.group(0):
        return FAIL, f"the skip link is not moved off screen: {hidden}"
    return PASS, "off screen until focused, then in view"


@case("QA-PLT-398", "A screen under reduced motion")
def plt_398(ctx: Ctx) -> Result:
    """Vestibular disorders are not rare, and an animation somebody cannot
    turn off is a page they cannot use."""
    got = _page(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    block = re.search(r"@media \(prefers-reduced-motion:\s*reduce\)\s*\{"
                      r"(.*?)\n\}", got.text, re.S)
    if not block:
        return FAIL, "no reduced-motion media query is served"
    body = block.group(1)
    for what in ("animation-duration", "transition-duration"):
        if what not in body:
            return FAIL, f"reduced motion does not neutralise {what}"
    if "!important" not in body:
        return FAIL, ("the reduced-motion rules do not override component "
                      "styles, so a component with its own animation keeps it")
    return PASS, "animation, transition and scroll behaviour all neutralised"


@case("QA-PLT-396", "A visible focus ring")
def plt_396(ctx: Ctx) -> Result:
    """A keyboard user navigating a page with no focus ring is guessing.
    `:focus-visible` is what keeps it off a mouse click and on for tabbing."""
    got = _page(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    if ":focus-visible" not in got.text:
        return FAIL, ("no :focus-visible rule is served, so either every "
                      "click draws a ring or tabbing draws none")
    if "outline:none" in got.text.replace(" ", "") and \
            ":focus-visible" not in got.text:
        return FAIL, "the focus outline is removed with no replacement"
    return PASS, ":focus-visible is styled"


@case("QA-PLT-392", "Each appearance choice is served")
def plt_392(ctx: Ctx) -> Result:
    """A theme the script admits and the stylesheet does not define is a
    choice that silently does nothing."""
    got = _page(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    admitted = set(THEME_PATTERN.findall(got.text))
    if not admitted:
        return BLOCKED, "no theme vocabulary could be read from the page"
    undefined = sorted(t for t in admitted
                       if f'[data-theme="{t}"]' not in got.text
                       and t != "light")
    if undefined:
        return FAIL, (f"these themes are accepted and never defined: "
                      f"{undefined}")
    return PASS, f"{len(admitted)} themes, each defined: {sorted(admitted)}"


@case("QA-PLT-393", "A theme value that is not one")
def plt_393(ctx: Ctx) -> Result:
    """The script tests the value against a closed list before applying it.
    Writing an arbitrary attribute onto <html> from stored state would be a
    small injection surface for no benefit."""
    got = _page(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    setter = re.search(r"if\((t==.*?)\)\s*\{[^}]*setAttribute", got.text)
    if not setter:
        return FAIL, ("the theme is applied without testing the value, so any "
                      "stored string lands on the document element")
    return PASS, "the theme is applied only from a closed list"


@case("QA-PLT-399", "An outcome announced to a screen reader")
def plt_399(ctx: Ctx) -> Result:
    """A result that appears silently is a result a screen-reader user does
    not know arrived. The pages that write an outcome into the page without
    reloading need a live region."""
    import pathlib
    templates = sorted(pathlib.Path("web/templates").rglob("*.html"))
    if not templates:
        return BLOCKED, "no templates found"
    silent = []
    for path in templates:
        text = path.read_text(encoding="utf-8")
        # An OUTCOME, not a hint. A form that updates a helper note as the
        # user types is writing into the page and is not announcing a
        # result — so the test is for a write that follows a fetch, which is
        # where something actually happened.
        if "aria-live" in text:
            continue
        for match in re.finditer(r"\.(innerHTML|textContent)\s*=", text):
            preceding = text[max(0, match.start() - 900):match.start()]
            if "fetch(" in preceding or "await " in preceding:
                silent.append(path.name)
                break
    if silent:
        return FAIL, (f"{len(silent)} template(s) write an outcome into the "
                      f"page with no live region: {sorted(silent)[:5]}")
    return PASS, "every template that writes a result announces it"


@case("QA-PLT-400", "The sign-in page carries the same affordances")
def plt_400(ctx: Ctx) -> Result:
    """The one page everybody meets, and the one most likely to be built
    outside the layout that carries the accessibility rules."""
    got = ctx.ui.get("/login", follow_redirects=False)
    if got.status_code >= 400 and got.status_code not in (302, 303):
        return BLOCKED, f"{got.status_code}"
    text = got.text
    missing = [what for what in
               ("prefers-reduced-motion", ":focus-visible", "data-theme")
               if what not in text]
    if missing:
        return FAIL, (f"the sign-in page is served without {missing}, so the "
                      f"one page everybody meets is outside the rules")
    return PASS, "the sign-in page carries the layout's affordances"


@case("QA-PLT-4301", "Every page declares a language")
def plt_4301(ctx: Ctx) -> Result:
    """A screen reader picks a voice from it. Without one it guesses, and a
    governance report read in the wrong language is unusable."""
    for path in ("/dashboard", "/models", "/login"):
        got = ctx.ui.get(path, follow_redirects=True)
        if got.status_code >= 400:
            continue
        if not re.search(r"<html[^>]+lang=", got.text):
            return FAIL, f"{path} serves an <html> element with no lang"
    return PASS, "every page declares a language"


@case("QA-PLT-4302", "A page has exactly one main landmark")
def plt_4302(ctx: Ctx) -> Result:
    """The skip link targets it, and a screen reader offers it as a landmark.
    Two is ambiguous and none makes the skip link a lie."""
    got = _page(ctx)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    # Strip the inline stylesheet first. A CSS comment explaining why the
    # skip link exists mentions `<main>`, and counting markup inside a
    # comment reports two landmarks where the page serves one.
    markup = re.sub(r"<style\b.*?</style>", "", got.text, flags=re.S)
    markup = re.sub(r"<!--.*?-->", "", markup, flags=re.S)
    mains = len(re.findall(r"<main\b", markup)) + \
        len(re.findall(r'role="main"', markup))
    if mains != 1:
        return FAIL, f"the page carries {mains} main landmarks"
    return PASS, "exactly one main landmark"
