"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — parameter sets: what inhabits P, and where it came from.

The word `fitted` on a row is a claim that data produced these numbers under a
warrant MAYA issued. Claiming it for a judgement launders an opinion into a
measurement, and the diagnostics that make an elicitation reviewable — the
panel, the questions, the dissent — are exactly what nobody looks for once the
row says `fitted`. Most of these cases are that sentence.
"""
from __future__ import annotations

from core.parameters.common import (CALIBRATED, DECLARED, FITTED,
                                    MAX_INLINE_VALUES, NOT_FROM_DATA)
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

P = "/api/v1/parameters"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _kernel(parameter_kind: str, fit_procedure: str, runtime: str) -> dict:
    return {"parameter_kind": parameter_kind, "fit_procedure": fit_procedure,
            "runtime": runtime,
            "input_schema": [{"name": "score", "dtype": "float"}],
            "output_schema": [{"name": "decision", "dtype": "string"}]}


#: A kernel whose parameters ARE from data, and one whose parameters are not.
FROM_DATA = _kernel("estimated_coefficients", "estimate", "estimator")
AUTHORED = _kernel("rule_set", "author", "rules")


def _version(ctx: Ctx, kernel=None) -> str:
    name = ctx.unique("ps")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    made = ctx.api.post(f"{M}/{name}/versions",
                        json={"semver": "1.0.0", "kernel": kernel or FROM_DATA},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        raise AssertionError(f"could not create the version: {made.text[:200]}")
    return urn


def _record(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "semver": "1.0.0", "name": ctx.unique("set"),
            "kind": "estimated_coefficients",
            "values": {"intercept": -3.1, "score": 0.004},
            "provenance": DECLARED, "note": "QA"}
    body.update(over)
    return ctx.api.post(P, json=body, auth=ctx.people["developer"])


def _reached(got) -> bool:
    """Whether the call got past the doors and the lookups."""
    return code_of(got) not in DENIAL + ("not_found", "registry_refused")


@case("QA-FX-242", "An empty parameter set")
def fx_242(ctx: Ctx) -> Result:
    """A set with nothing in it is a governed object measuring nothing."""
    got = _record(ctx, _version(ctx), values={})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, "an empty parameter set was recorded"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-234", "A fitted set against a kernel data does not produce")
def fx_234(ctx: Ctx) -> Result:
    """Every member of NOT_FROM_DATA, not a sample. `fitted` on a rule set
    launders an opinion into a measurement, and the row then reads as
    evidence."""
    laundered = []
    for kind in sorted(NOT_FROM_DATA):
        urn = _version(ctx, _kernel(kind, "author", "rules"))
        for provenance in (FITTED, CALIBRATED):
            got = _record(ctx, urn, kind=kind, provenance=provenance,
                          values={"a": 1})
            if got.status_code >= 500:
                return FAIL, f"{kind}/{provenance}: {got.status_code}"
            if got.status_code < 400:
                laundered.append(f"{kind} as {provenance}")
            elif not _reached(got):
                return BLOCKED, f"{kind}: '{code_of(got)}' — not reached"
    if laundered:
        return FAIL, ("these were recorded as though data produced them: "
                      + ", ".join(laundered))
    return PASS, (f"all {len(NOT_FROM_DATA)} authored kinds refused as fitted "
                  f"and as calibrated")


@case("QA-FX-2400", "The same kinds are accepted as declared")
def fx_2400(ctx: Ctx) -> Result:
    """`declared` is the honest word for parameters a person asserted, so the
    refusal has to leave that door open or a rule set can never be recorded."""
    for kind in sorted(NOT_FROM_DATA):
        urn = _version(ctx, _kernel(kind, "author", "rules"))
        got = _record(ctx, urn, kind=kind, provenance=DECLARED,
                      values={"rules": [], "otherwise": {}})
        if got.status_code >= 400 and _reached(got):
            return FAIL, (f"'{kind}' as declared was refused "
                          f"'{code_of(got)}': {got.text[:120]}")
    return PASS, f"all {len(NOT_FROM_DATA)} authored kinds accepted as declared"


@case("QA-FX-228", "A fitted set with no warrant")
def fx_228(ctx: Ctx) -> Result:
    """`fitted` means "under a fit warrant MAYA issued". With no warrant
    named the claim has nothing behind it."""
    got = _record(ctx, _version(ctx), provenance=FITTED, warrant_id=None)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — the check was not reached"
    if got.status_code < 400:
        return FAIL, ("a set was recorded as fitted with no warrant, so the "
                      "word rests on nothing")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-2401", "A fitted set naming a warrant that does not exist")
def fx_2401(ctx: Ctx) -> Result:
    got = _record(ctx, _version(ctx), provenance=FITTED,
                  warrant_id="qa-no-such-warrant")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a set cited a warrant nobody issued"
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-239", "Exactly the inline cap, then one more")
def fx_239(ctx: Ctx) -> Result:
    """Past the cap the values are an artifact rather than a record, and the
    register says so instead of storing a blob in a column."""
    urn = _version(ctx)
    at = _record(ctx, urn, values={f"c{n}": float(n)
                                   for n in range(MAX_INLINE_VALUES)})
    if at.status_code >= 400:
        if not _reached(at):
            return BLOCKED, f"'{code_of(at)}' — the check was not reached"
        return FAIL, (f"exactly {MAX_INLINE_VALUES} values was refused "
                      f"'{code_of(at)}'; the cap excludes itself")
    over = _record(ctx, urn, values={f"c{n}": float(n)
                                     for n in range(MAX_INLINE_VALUES + 1)})
    if over.status_code < 400:
        return FAIL, f"{MAX_INLINE_VALUES + 1} values was stored inline"
    if "values_uri" not in over.text:
        return FAIL, "the refusal does not name the way to store them"
    return PASS, (f"{MAX_INLINE_VALUES} inline, {MAX_INLINE_VALUES + 1} "
                  f"refused naming values_uri")


@case("QA-FX-240", "Past the cap, supplied out of line")
def fx_240(ctx: Ctx) -> Result:
    """The cap is about what belongs in a column, not about how many
    parameters a model may have."""
    got = _record(ctx, _version(ctx), values={},
                  values_uri="artifact://qa/big-parameter-set")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400 and _reached(got):
        return FAIL, (f"an out-of-line parameter set was refused "
                      f"'{code_of(got)}', so a large model cannot be "
                      f"recorded at all")
    return PASS, "held out of line"


@case("QA-FX-243", "The recorder approving their own set")
def fx_243(ctx: Ctx) -> Result:
    """A parameter set changes behaviour, so it is approved like a version —
    which means not by the person who wrote it."""
    made = _record(ctx, _version(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    pid = (made.json() or {}).get("id")
    if not pid:
        return BLOCKED, f"the set carries no id: {made.text[:130]}"
    parameters = ctx.ui.app.state.ctx.get("parameters")
    if parameters is None:
        return BLOCKED, "no parameter register reachable from this run"
    from core.parameters.common import ParameterError
    try:
        parameters.approve(pid, "developer", "looks fine to me")
    except ParameterError as exc:
        if exc.code != "self_approval":
            return FAIL, f"refused '{exc.code}', not self_approval"
        return PASS, "the recorder cannot approve their own set"
    return FAIL, ("the person who recorded a parameter set approved it, so "
                  "one person changed a model's behaviour alone")


@case("QA-FX-244", "Rejecting a set with no reason")
def fx_244(ctx: Ctx) -> Result:
    made = _record(ctx, _version(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    pid = (made.json() or {}).get("id")
    got = ctx.api.post(f"/api/v1/parameter-sets/{pid}/review",
                       json={"accept": False, "note": "   "},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a parameter set was rejected with no reason, so the "
                      "author is told no and not why")
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-245", "Reviewing a set that was already reviewed")
def fx_245(ctx: Ctx) -> Result:
    """A second verdict on one set is two answers on the record."""
    made = _record(ctx, _version(ctx))
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    pid = (made.json() or {}).get("id")
    first = ctx.api.post(f"/api/v1/parameter-sets/{pid}/review",
                         json={"accept": True, "note": "approved"},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = ctx.api.post(f"/api/v1/parameter-sets/{pid}/review",
                         json={"accept": False, "note": "changed my mind"},
                         auth=ctx.people["risk"])
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, ("a reviewed set was reviewed again with the opposite "
                      "verdict; the record now holds two answers")
    return PASS, f"refused '{code_of(again)}'"


@case("QA-FX-249", "A parameter set does not create a model version")
def fx_249(ctx: Ctx) -> Result:
    """New numbers under an approved procedure are not a new model. If every
    daily calibration minted a version, the version history would stop being
    a record of change."""
    urn = _version(ctx)
    name = urn.rsplit("/", 1)[-1]
    before = len((ctx.api.get(f"{M}/{name}").json() or {}).get("versions") or [])
    if _record(ctx, urn).status_code >= 400:
        return BLOCKED, "the set could not be recorded"
    after = len((ctx.api.get(f"{M}/{name}").json() or {}).get("versions") or [])
    if after != before:
        return FAIL, (f"recording a parameter set moved the version count "
                      f"from {before} to {after}")
    return PASS, f"{before} version(s) before and after"
