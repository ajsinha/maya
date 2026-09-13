"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — regimes: a supervisor's sentences, translated into facts the
register holds.

The structure is what makes this defensible rather than a checklist. A regime
carries its actual SENTENCES, a signature of the terms those sentences use,
and a translation from each term to a predicate over the platform's own state.
A term with no translation is an obligation nothing can ever satisfy; a
predicate reading a fact the state does not carry is one nothing can ever
fail.
"""
from __future__ import annotations

from core.regimes.library import REGIMES
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

R = "/api/v1/regimes"


@case("QA-GOV-5800", "Every regime carries its own sentences")
def gov_5800(ctx: Ctx) -> Result:
    """A regime encoded as a list of controls is somebody's reading of a
    rule. Carrying the sentences makes the reading arguable against the
    text."""
    thin = []
    for key, regime in REGIMES.items():
        if not regime.get("sentences"):
            thin.append(key)
        if not (regime.get("title") or "").strip():
            thin.append(f"{key}(title)")
        if not (regime.get("authority") or "").strip():
            thin.append(f"{key}(authority)")
    if thin:
        return FAIL, f"regimes missing their own text or provenance: {thin}"
    return PASS, (f"{len(REGIMES)} regimes, each with sentences, a title and "
                  f"a named authority")


@case("QA-GOV-5801", "Every term a signature declares has a translation")
def gov_5801(ctx: Ctx) -> Result:
    """A term with no predicate is an obligation nothing can ever satisfy,
    and it reads on a report as an outstanding requirement for ever."""
    untranslated = []
    for key, regime in REGIMES.items():
        translation = regime.get("translation")
        signature = getattr(translation, "regime", None)
        if signature is None:
            return BLOCKED, f"{key} carries no signature to check"
        mapping = getattr(translation, "mapping", {}) or {}
        for term in getattr(signature, "terms", ()):
            if term not in mapping:
                untranslated.append(f"{key}:{term}")
    if untranslated:
        return FAIL, (f"{len(untranslated)} term(s) are declared and have no "
                      f"predicate, so nothing can ever satisfy them: "
                      + ", ".join(untranslated[:6]))
    total = sum(len(getattr(r.get("translation"), "mapping", {}) or {})
                for r in REGIMES.values())
    return PASS, f"{total} terms across {len(REGIMES)} regimes, all translated"


@case("QA-GOV-5802", "No translation reads a fact the state does not carry")
def gov_5802(ctx: Ctx) -> Result:
    """The sibling of QA-PLT-4701. A predicate reading an absent key is
    permanently False, so the obligation can never be satisfied by doing the
    thing it asks for.
    """
    import ast
    import inspect

    documents = ctx.ui.app.state.ctx.get("documents")
    regimes = ctx.ui.app.state.ctx.get("regimes")
    if documents is None or regimes is None:
        return BLOCKED, "no document or regime service reachable"
    name = ctx.unique("rg")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner",
                       "model_class": "logistic", "domain": "credit",
                       "legal_entity": "LE-US-01",
                       "purpose": "credit_decision"})
    state = regimes.core_state(documents.build_context(urn))

    missing = []
    for key, regime in REGIMES.items():
        mapping = getattr(regime.get("translation"), "mapping", {}) or {}
        for term, predicate in mapping.items():
            try:
                source = inspect.getsource(predicate)
            except (OSError, TypeError):
                continue
            # `inspect.getsource` of a lambda returns the whole line it sits
            # on — `"documented": lambda s: bool(...),` — which is not a
            # parseable expression. Take the lambda itself.
            import re as _re
            found = _re.search(r"lambda\s+\w+\s*:.*", source)
            if not found:
                continue
            expression = found.group(0).rstrip().rstrip(",").rstrip(")")
            try:
                tree = ast.parse(expression, mode="eval")
            except SyntaxError:
                try:
                    tree = ast.parse(expression + ")", mode="eval")
                except SyntaxError:
                    continue
            reads = {node.args[0].value
                     for node in ast.walk(tree)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute)
                     and node.func.attr == "get" and node.args
                     and isinstance(node.args[0], ast.Constant)
                     and isinstance(node.args[0].value, str)}
            for read in reads:
                if read not in state:
                    missing.append(f"{key}:{term} reads '{read}'")
    if missing:
        return FAIL, (f"{len(missing)} predicate(s) read a fact `core_state` "
                      f"does not produce, so the obligation is permanently "
                      f"unsatisfiable: " + "; ".join(sorted(set(missing))[:6]))
    return PASS, "every predicate reads a fact the state carries"


@case("QA-GOV-5803", "Activate a regime that does not exist")
def gov_5803(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{R}/qa-no-such-regime/activate", json={},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a regime nobody encoded was activated"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-GOV-5804", "A regime is not in force until it is activated")
def gov_5804(ctx: Ctx) -> Result:
    """Shipping three encoded regimes and applying them to every estate on
    upgrade would be the platform deciding which rules a firm is subject
    to."""
    got = ctx.api.get(R, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    rows = body.get("regimes") or []
    if not rows:
        return BLOCKED, f"no regimes listed: {sorted(body)}"
    if not any("active" in str(row) or "in_force" in str(row) for row in rows):
        return FAIL, ("nothing says whether a regime is in force, so an "
                      "encoded one is indistinguishable from an adopted one")
    return PASS, f"{len(rows)} regimes listed with their state"


@case("QA-GOV-5805", "Satisfaction for a regime nobody activated")
def gov_5805(ctx: Ctx) -> Result:
    """A satisfaction report for a rule a firm is not subject to is a list of
    failures against something nobody claimed."""
    key = sorted(REGIMES)[0]
    got = ctx.api.get(f"{R}/{key}/satisfaction", auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' for an inactive regime"
    body = got.json() or {}
    if not (body.get("detail") or "").strip():
        return FAIL, "the satisfaction report says nothing about its own state"
    return PASS, str(body.get("detail"))[:100]


@case("QA-GOV-5806", "The encoding language is published for a reader")
def gov_5806(ctx: Ctx) -> Result:
    """A reader cannot argue with a translation until they know what the
    translation is written IN. `/regime-encoding` publishes the forms a
    sentence may take, the modal phrases that suggest each, and the core
    terms — which is the vocabulary, not the regimes; those are at
    `/regimes`.
    """
    encoding = ctx.api.get("/api/v1/regime-encoding", auth=ctx.people["risk"])
    if encoding.status_code >= 400:
        return BLOCKED, encoding.text[:170]
    body = encoding.json() or {}
    for part in ("forms", "modals", "core_terms"):
        if not body.get(part):
            return FAIL, (f"the encoding publishes no {part}, so a reader "
                          f"cannot tell what a translation means")
    mute = [f for f in body["forms"]
            if isinstance(f, dict) and not (f.get("means") or "").strip()]
    if mute:
        return FAIL, f"{len(mute)} form(s) published with no meaning"
    listed = ctx.api.get(R, auth=ctx.people["risk"])
    if listed.status_code >= 400:
        return BLOCKED, listed.text[:170]
    for key in REGIMES:
        if key not in listed.text:
            return FAIL, f"'{key}' is encoded and not listed at {R}"
    return PASS, (f"{len(body['forms'])} forms and {len(body['modals'])} "
                  f"modal phrases published; {len(REGIMES)} regimes listed")


@case("QA-GOV-5807", "Two regimes do not share one term's meaning by accident")
def gov_5807(ctx: Ctx) -> Result:
    """`technical_documentation` in the EU AI Act and `documented` in SS1/23
    may well mean the same thing — but if they do, that is a decision. The
    case reports which terms are shared so a divergence is deliberate.
    """
    seen = {}
    for key, regime in REGIMES.items():
        mapping = getattr(regime.get("translation"), "mapping", {}) or {}
        for term in mapping:
            seen.setdefault(term, []).append(key)
    shared = {t: ks for t, ks in seen.items() if len(ks) > 1}
    for term, keys in shared.items():
        sources = set()
        for key in keys:
            predicate = REGIMES[key]["translation"].mapping[term]
            import inspect
            try:
                sources.add(" ".join(inspect.getsource(predicate).split()))
            except (OSError, TypeError):
                sources.add(repr(predicate))
        if len(sources) > 1:
            return FAIL, (f"'{term}' is used by {keys} with different "
                          f"predicates, so one regime's obligation is "
                          f"satisfied by a different fact from the other's")
    return PASS, (f"{len(shared)} term(s) shared across regimes, each with "
                  f"one meaning: {sorted(shared)[:5]}")
