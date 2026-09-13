"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — rule sets, which are what a T8 model's parameter object is.

A rule set is authored rather than fitted, so the register's job is to refuse
the ones nobody can review: too many rules, too deep, contradictory, or
unreachable. Every limit here exists because past it "first-match-wins" stops
being something a person is actually checking.
"""
from __future__ import annotations

from core.rules.common import MAX_DEPTH, MAX_RULES
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

R = "/api/v1/rulesets"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: The schemas live inside the KERNEL, as lists of field specs. `VersionIn`
#: has no `input_schema` field and `Body` forbids extras, so sending one is a
#: 422 and no version is created — after which every case here is refused
#: `not_found`, which is a refusal, which scores as a pass.
#: A T8 kernel: the parameter object IS the rule set, so `parameter_kind` is
#: `rule_set` and the fit procedure is `author`. `coefficients` is not a
#: member of the vocabulary — the members are none, calibration_set,
#: estimated_coefficients, learned_weights, llm_configuration, rule_set,
#: elicited_weights and opaque — and a version that fails to register leaves
#: every case here answering `not_found`.
KERNEL = {
    "parameter_kind": "rule_set",
    "fit_procedure": "author",
    "runtime": "rules",
    "input_schema": [{"name": "score", "dtype": "float"},
                     {"name": "segment", "dtype": "string"}],
    "output_schema": [{"name": "decision", "dtype": "string"}],
}


def _version(ctx: Ctx) -> tuple:
    name = ctx.unique("rs")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    made = ctx.api.post(f"{M}/{name}/versions",
                        json={"semver": "1.0.0", "kernel": KERNEL},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        raise AssertionError(f"could not create the version: {made.text[:200]}")
    return urn, "1.0.0"


def _rule(rid: str, threshold: float = 650.0, decision: str = "approve"):
    return {"id": rid,
            "when": {"all": [{"field": "score", "op": "ge",
                              "value": threshold}]},
            "then": {"decision": decision},
            "because": "score at or above the cut"}


def _check(ctx: Ctx, document: dict, urn=None, semver=None):
    if urn is None:
        urn, semver = _version(ctx)
    return ctx.api.post(f"{R}/check",
                        json={"urn": urn, "semver": semver,
                              "document": document},
                        auth=ctx.people["developer"])


def _doc(*rules, otherwise=None):
    return {"rules": list(rules),
            "otherwise": {"decision": "refer"} if otherwise is None
            else otherwise}


@case("QA-FX-286", "A rule set with no otherwise")
def fx_286(ctx: Ctx) -> Result:
    """First-match-wins with no catch-all is a rule set that decides
    confidently on the inputs somebody thought of and silently on the rest."""
    got = _check(ctx, {"rules": [_rule("r1")]})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("a rule set with no catch-all was accepted; the inputs "
                      "nobody thought of get no decision and no refusal")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-287", "A rule with no because")
def fx_287(ctx: Ctx) -> Result:
    """The whole claim of a rule set over a fitted model is that every
    decision can be explained back to the rule that made it."""
    rule = _rule("r1")
    rule.pop("because")
    got = _check(ctx, _doc(rule))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("a rule with no reason was accepted, so a decision it "
                      "makes cannot be explained back to anything")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-288", "Exactly the rule limit, then one more")
def fx_288(ctx: Ctx) -> Result:
    """Past the limit the ordering is not something a person is checking, and
    the honest answer is that it wants to be a model."""
    urn, semver = _version(ctx)
    # DESCENDING thresholds. With `ge` ascending, rule 0 at >=100 already
    # covers everything rule 1 at >=101 would match, so the set is refused
    # `rule_unreachable` and the case reports the rule LIMIT as excluding
    # itself. Each descending rule opens a band the ones above it did not.
    def band(n):
        return _rule(f"r{n}", 100.0 + (MAX_RULES - n))

    at = _check(ctx, _doc(*[band(n) for n in range(MAX_RULES)]), urn, semver)
    if at.status_code >= 400:
        return FAIL, (f"exactly {MAX_RULES} rules was refused "
                      f"'{code_of(at)}'; the limit excludes itself")
    over = _check(ctx, _doc(*[_rule(f"r{n}", 100.0 + (MAX_RULES + 1 - n))
                              for n in range(MAX_RULES + 1)]), urn, semver)
    if over.status_code < 400:
        return FAIL, f"{MAX_RULES + 1} rules was accepted"
    return PASS, f"{MAX_RULES} accepted, {MAX_RULES + 1} refused"


@case("QA-FX-289", "Nesting exactly the depth limit, then one deeper")
def fx_289(ctx: Ctx) -> Result:
    """A condition tree deeper than this is not being reviewed by anybody,
    which is the only reason rule sets are worth holding."""
    def nest(depth: int):
        node = {"field": "score", "op": "ge", "value": 650.0}
        for _ in range(depth):
            node = {"all": [node]}
        return node

    urn, semver = _version(ctx)
    at = _check(ctx, _doc({"id": "r1", "when": nest(MAX_DEPTH - 1),
                           "then": {"decision": "approve"},
                           "because": "deep but reviewable"}), urn, semver)
    over = _check(ctx, _doc({"id": "r1", "when": nest(MAX_DEPTH + 2),
                             "then": {"decision": "approve"},
                             "because": "too deep"}), urn, semver)
    if over.status_code < 400:
        return FAIL, f"nesting past {MAX_DEPTH} levels was accepted"
    if at.status_code >= 400:
        return FAIL, (f"nesting within {MAX_DEPTH} levels was refused "
                      f"'{code_of(at)}'")
    return PASS, f"within {MAX_DEPTH} accepted, past it refused '{code_of(over)}'"


@case("QA-FX-290", "Two rules with one id")
def fx_290(ctx: Ctx) -> Result:
    """A decision cites the rule that made it. Two rules under one id makes
    that citation ambiguous."""
    got = _check(ctx, _doc(_rule("r1", 650.0), _rule("r1", 700.0)))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, "two rules share one id, so a citation names both"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-291", "Two rules with the same condition and different outcomes")
def fx_291(ctx: Ctx) -> Result:
    """First-match would silently pick one. The set contradicts itself and
    saying so is more useful than resolving it."""
    got = _check(ctx, _doc(_rule("r1", 650.0, "approve"),
                           _rule("r2", 650.0, "decline")))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("a rule set contradicting itself was accepted; "
                      "first-match silently picks one of two answers")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-292", "A rule shadowed by one earlier rule")
def fx_292(ctx: Ctx) -> Result:
    """A rule that can never fire is a rule somebody believes is running."""
    got = _check(ctx, _doc(_rule("r1", 600.0, "approve"),
                           _rule("r2", 700.0, "decline")))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("a rule covered entirely by an earlier one was "
                      "accepted; it can never fire and nobody is told")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-295", "A between with the bounds the wrong way round")
def fx_295(ctx: Ctx) -> Result:
    """An empty range matches nothing for ever, which is a rule nobody wrote
    on purpose."""
    got = _check(ctx, _doc({"id": "r1",
                            "when": {"all": [{"field": "score",
                                              "op": "between",
                                              "value": [700.0, 600.0]}]},
                            "then": {"decision": "approve"},
                            "because": "an impossible range"}))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, "a range that matches nothing was accepted"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-297", "An ordered operator on a categorical field")
def fx_297(ctx: Ctx) -> Result:
    """Asking whether one product code is less than another is a question
    with no answer."""
    got = _check(ctx, _doc({"id": "r1",
                            "when": {"all": [{"field": "segment", "op": "gt",
                                              "value": "retail"}]},
                            "then": {"decision": "approve"},
                            "because": "an unordered comparison"}))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("a greater-than was accepted on a string field, so the "
                      "rule asks a question with no answer")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-298", "A numeric field compared against text")
def fx_298(ctx: Ctx) -> Result:
    got = _check(ctx, _doc({"id": "r1",
                            "when": {"all": [{"field": "score", "op": "ge",
                                              "value": "high"}]},
                            "then": {"decision": "approve"},
                            "because": "a type error"}))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, "a number was compared against text"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-300", "A field the version's input schema does not declare")
def fx_300(ctx: Ctx) -> Result:
    """A rule on a field that never arrives is a rule that never fires, and
    the schema is the only place to catch it."""
    got = _check(ctx, _doc({"id": "r1",
                            "when": {"all": [{"field": "moon_phase",
                                              "op": "eq", "value": "full"}]},
                            "then": {"decision": "approve"},
                            "because": "a field nobody sends"}))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("a rule was accepted on a field the input schema does "
                      "not declare, so it can never fire")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-302", "is_null carrying a value")
def fx_302(ctx: Ctx) -> Result:
    """A value on an operator that takes none is a value nobody reads, and a
    reader would reasonably think it was being used."""
    got = _check(ctx, _doc({"id": "r1",
                            "when": {"all": [{"field": "score",
                                              "op": "is_null",
                                              "value": 650.0}]},
                            "then": {"decision": "approve"},
                            "because": "a value nobody reads"}))
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if code_of(got) in DENIAL + ("not_found",):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("is_null was accepted carrying a value, which a reader "
                      "would take to be part of the condition")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-307", "Checking a draft needs only model:read")
def fx_307(ctx: Ctx) -> Result:
    """Checking a draft changes nothing, and requiring the recording
    permission to LOOK at whether a document is valid would push authors to
    skip the step."""
    urn, semver = _version(ctx)
    got = ctx.api.post(f"{R}/check",
                       json={"urn": urn, "semver": semver,
                             "document": _doc(_rule("r1"))},
                       auth=ctx.people["auditor"])
    if got.status_code >= 400 and code_of(got) in ("forbidden",
                                                   "unauthorised"):
        return FAIL, ("a reader cannot check a draft, so an author must hold "
                      "the recording permission to find out whether their "
                      "document is valid")
    return PASS, f"a reader may check ({got.status_code})"


@case("QA-FX-312", "A trial row that matches no rule")
def fx_312(ctx: Ctx) -> Result:
    """The catch-all is what answers, and the report has to say that no rule
    matched rather than reporting the catch-all as a match."""
    urn, semver = _version(ctx)
    got = ctx.api.post(f"{R}/trial",
                       json={"urn": urn, "semver": semver,
                             "document": _doc(_rule("r1", 650.0)),
                             "rows": [{"score": 100.0, "segment": "retail"}]},
                       auth=ctx.people["developer"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    # `outcomes`, one per row, each carrying `matched_rule` and `because`.
    rows = body.get("outcomes") or []
    if not rows:
        return BLOCKED, f"the trial reported no rows: {str(body)[:130]}"
    matched = rows[0].get("matched_rule", "missing")
    if matched not in (None, "missing"):
        return FAIL, (f"a row matching no rule reports matched_rule "
                      f"{matched!r}; the catch-all is reported as a match")
    if matched == "missing":
        return FAIL, "the trial does not say which rule matched"
    return PASS, "matched_rule is null and the otherwise answered"


@case("QA-FX-306", "A trial records nothing")
def fx_306(ctx: Ctx) -> Result:
    """Deliberately not `/execute`: there is no warrant and no entitlement,
    so it must leave the register byte-identical."""
    urn, semver = _version(ctx)
    before = ctx.api.get(f"{M}/{urn.rsplit('/', 1)[-1]}").text
    ctx.api.post(f"{R}/trial",
                 json={"urn": urn, "semver": semver,
                       "document": _doc(_rule("r1")),
                       "rows": [{"score": 900.0, "segment": "retail"}]},
                 auth=ctx.people["developer"])
    after = ctx.api.get(f"{M}/{urn.rsplit('/', 1)[-1]}").text
    if before != after:
        return FAIL, "a trial changed the model's record"
    listed = ctx.api.get(f"{R}/{urn}", auth=ctx.people["developer"])
    if listed.status_code < 400 and "r1" in listed.text:
        return FAIL, "a trial published the draft it was given"
    return PASS, "the register is unchanged"
