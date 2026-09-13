"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the warrant grammar.

A warrant is the document an engine acts on, so a defect in the grammar is a
defect in everything downstream. The cases here mutate a REAL issued warrant
rather than hand-building one: a document assembled by the case would agree
with the case's own idea of the shape, which is the one thing a grammar test
must not do.
"""
from __future__ import annotations

import copy

from core.execution.grammar.vocabulary import (REQUIRED_SECTIONS, VERBS,
                                               WARRANT_VERSION)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)
from qa.regression_suite.scenarios.g_execution import governed

G = "/api/v1/grammar"


def _issued(ctx: Ctx) -> dict:
    """A warrant document the platform itself produced and sealed."""
    made = governed(ctx)
    ctx.api.post("/api/v1/warrants",
                 json={"urn": made["urn"], "principal": "svc-pricing",
                       "environment": "prod",
                       "declared_use": "credit_decision"})
    got = ctx.api.post("/api/v1/resolve",
                       json={"urn": made["urn"], "principal": "svc-pricing",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code >= 400:
        return {}
    # The resolve response IS the warrant document — `maya_warrant` sits at
    # the top level, not under a `warrant` or `document` key.
    return got.json() or {}


def _validate(ctx: Ctx, doc: dict):
    # The document is the body. Wrapping it in {"document": ...} validates an
    # object with one key and no sections, which fails for reasons that have
    # nothing to do with what the case is asking.
    return ctx.api.post(f"{G}/validate", json=doc, auth=ctx.people["risk"])


def _problems(response) -> list:
    body = response.json() if response.status_code < 500 else {}
    if isinstance(body, dict):
        return body.get("problems") or (body.get("detail") or {}).get(
            "problems") or []
    return []


@case("QA-FX-2000", "A warrant the platform issued conforms to its own grammar")
def fx_2000(ctx: Ctx) -> Result:
    """The base case every mutation below rests on. If this fails, nothing
    else in the module means anything."""
    doc = _issued(ctx)
    if not doc:
        return BLOCKED, "no warrant could be resolved"
    got = _validate(ctx, doc)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    if not (got.json() or {}).get("valid"):
        return FAIL, (f"the platform issued a warrant that does not conform to "
                      f"its own grammar: {_problems(got)}")
    return PASS, "issued and conforming"


@case("QA-FX-320", "A warrant missing one of the ten sections")
def fx_320(ctx: Ctx) -> Result:
    """Every section, one at a time — a grammar that catches nine of ten is
    a grammar with a hole somebody will find."""
    doc = _issued(ctx)
    if not doc:
        return BLOCKED, "no warrant could be resolved"
    if not _validate(ctx, doc).json().get("valid"):
        return BLOCKED, "the base document does not validate"
    missed = []
    for section in REQUIRED_SECTIONS:
        cut = copy.deepcopy(doc)
        cut.pop(section, None)
        got = _validate(ctx, cut)
        problems = _problems(got)
        if (got.json() or {}).get("valid"):
            missed.append(section)
        elif not any(section in str(p.get("where") or p) for p in problems):
            missed.append(f"{section}(unnamed)")
    if missed:
        return FAIL, (f"removing these sections was not caught, or was caught "
                      f"without naming the section: {missed}")
    return PASS, f"all {len(REQUIRED_SECTIONS)} sections required and named"


@case("QA-FX-321", "A wrong warrant grammar version")
def fx_321(ctx: Ctx) -> Result:
    """Validation stops there: nothing below can be trusted to mean what this
    validator thinks it means."""
    doc = _issued(ctx)
    if not doc:
        return BLOCKED, "no warrant could be resolved"
    wrong = copy.deepcopy(doc)
    wrong["maya_warrant"] = "0.9"
    got = _validate(ctx, wrong)
    if (got.json() or {}).get("valid"):
        return FAIL, "a document of an unknown grammar version validated"
    problems = _problems(got)
    if not any("maya_warrant" in str(p.get("where") or p) for p in problems):
        return FAIL, f"the version problem is not named: {problems}"
    if WARRANT_VERSION not in str(problems):
        return FAIL, "the refusal does not say which version was expected"
    return PASS, f"refused, naming v{WARRANT_VERSION} as expected"


@case("QA-FX-322", "Two shape errors at once")
def fx_322(ctx: Ctx) -> Result:
    """Reported together. A validator that stops at the first makes fixing a
    document a sequence of round trips."""
    doc = _issued(ctx)
    if not doc:
        return BLOCKED, "no warrant could be resolved"
    broken = copy.deepcopy(doc)
    broken.pop("data", None)
    broken.pop("constraints", None)
    got = _validate(ctx, broken)
    if (got.json() or {}).get("valid"):
        return FAIL, "a document missing two sections validated"
    problems = _problems(got)
    if len(problems) < 2:
        return FAIL, (f"two shape errors produced {len(problems)} problem(s), "
                      f"so fixing a document means one round trip per error")
    return PASS, f"{len(problems)} problems reported together"


@case("QA-FX-2001", "A verb that is not a warrant verb")
def fx_2001(ctx: Ctx) -> Result:
    doc = _issued(ctx)
    if not doc:
        return BLOCKED, "no warrant could be resolved"
    wrong = copy.deepcopy(doc)
    wrong.setdefault("operation", {})["verb"] = "ponder"
    got = _validate(ctx, wrong)
    if (got.json() or {}).get("valid"):
        return FAIL, "a warrant authorising a verb that is not one validated"
    if not any(v in str(_problems(got)) for v in VERBS):
        return FAIL, "the refusal does not name the verbs"
    return PASS, f"refused, naming the {len(VERBS)} verbs"


@case("QA-FX-324", "A trainability class with a trailing space")
def fx_324(ctx: Ctx) -> Result:
    """`"T6 "` is not `"T6"`. A grammar that strips whitespace before
    comparing would accept a document no other reader agrees with."""
    doc = _issued(ctx)
    if not doc:
        return BLOCKED, "no warrant could be resolved"
    wrong = copy.deepcopy(doc)
    held = (wrong.get("subject") or {}).get("trainability_class")
    if not held:
        return BLOCKED, "the warrant declares no trainability class"
    wrong["subject"]["trainability_class"] = f"{held} "
    got = _validate(ctx, wrong)
    if (got.json() or {}).get("valid"):
        return FAIL, (f"'{held} ' with a trailing space validated as "
                      f"'{held}'; the vocabulary is not closed against "
                      f"whitespace")
    return PASS, f"'{held} ' refused"


@case("QA-FX-349", "The grammar is checked before the signature")
def fx_349(ctx: Ctx) -> Result:
    """A signature over a document that does not conform would be an
    assurance that the document is authentic and not that it is usable, and
    engines would reasonably read it as both. Asserted against the source,
    because the ordering of two internal steps has no response body.
    """
    import inspect

    from core.execution import builder
    source = inspect.getsource(builder.WarrantBuilder._seal)
    # The CALLS, not the words. `signature` appears first because the seal
    # builds the envelope with an empty value before validating — which is
    # correct and is exactly what a `find("sign")` scan misreads as signing
    # early. Assert on the construct, never on the token.
    validate_at = source.find("self.validator.validate(")
    sign_at = source.find("self.signer.sign(")
    if validate_at < 0 or sign_at < 0:
        return FAIL, "the seal does not both validate and sign"
    if validate_at > sign_at:
        return FAIL, ("the document is signed before it is validated, so a "
                      "non-conforming warrant can carry a valid signature")
    return PASS, "validated, then signed — asserted on the calls, not the words"


@case("QA-FX-350", "The published schema agrees with the enforced vocabulary")
def fx_350(ctx: Ctx) -> Result:
    """The schema is what an engine builder reads. A value the vocabulary
    accepts and the schema forbids is a document MAYA issues and a conforming
    engine rejects."""
    got = ctx.api.get(f"{G}/schema", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = got.text
    missing = [v for v in VERBS if f'"{v}"' not in text]
    if missing:
        return FAIL, (f"the published schema does not admit these verbs the "
                      f"grammar accepts: {missing}")
    absent = [s for s in REQUIRED_SECTIONS if s not in text]
    if absent:
        return FAIL, f"the schema does not mention these sections: {absent}"
    return PASS, f"{len(VERBS)} verbs and {len(REQUIRED_SECTIONS)} sections present"


@case("QA-FX-2002", "The grammar is published for a reader")
def fx_2002(ctx: Ctx) -> Result:
    """An engine builder outside this firm has to be able to read what a
    warrant means without reading this source."""
    got = ctx.api.get(G, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    text = str(body)
    if WARRANT_VERSION not in text:
        return FAIL, "the published grammar does not state its own version"
    unexplained = [v for v in VERBS if v not in text]
    if unexplained:
        return FAIL, f"verbs published without meaning: {unexplained}"
    return PASS, f"v{WARRANT_VERSION} published with every verb"


@case("QA-FX-2003", "Validate a document that is not a document")
def fx_2003(ctx: Ctx) -> Result:
    got = _validate(ctx, {})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} — an empty document crashed validation"
    if (got.json() or {}).get("valid"):
        return FAIL, "an empty object validated as a warrant"
    return PASS, f"{len(_problems(got))} problem(s) on an empty document"


@case("QA-FX-2004", "A tampered document is still measured against the grammar")
def fx_2004(ctx: Ctx) -> Result:
    """Changing a field the signature covers must not make the grammar
    report the document as conforming — the two checks answer different
    questions and neither stands in for the other."""
    doc = _issued(ctx)
    if not doc:
        return BLOCKED, "no warrant could be resolved"
    tampered = copy.deepcopy(doc)
    boundary = (tampered.get("constraints") or {}).get("resources") or {}
    boundary["max_seconds"] = 999_999
    got = _validate(ctx, tampered)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    body = got.json() or {}
    if body.get("valid") is None:
        return FAIL, "the grammar returned no verdict on a tampered document"
    return PASS, (f"the grammar answers on shape alone (valid="
                  f"{body.get('valid')}); the signature is a separate question")
