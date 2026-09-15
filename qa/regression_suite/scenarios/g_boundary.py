"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the operating boundary, and the ways a contract can silently not
exist.

A guarantee is conditional on an assumption. Outside the assumption the
guarantee is void, so the boundary check is the one place the platform decides
whether a model's promise still applies to the thing it is about to be asked.

**A contract that does not parse is worse than no contract**, because the
version reads as governed and is not. `assumption` for `assumptions`, `min` for
`minimum`, a clause with no `key`, a minimum above a maximum — every one of
those leaves a clause that appears in the document and constrains nothing, so
every one is refused at REGISTRATION rather than discovered when the boundary
fails to fire.

And the boundary that held and the boundary that never applied are different
facts. An assumption whose key no input supplies is not a violation — but
`boundary_ok: true` alone cannot tell the two apart, and the second is exactly
what a silently unenforced contract looks like from outside.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
BOUNDED = {"assumptions": [{"key": "dscr", "minimum": 0, "maximum": 20}],
           "guarantees": [], "on_boundary_violation": "reject"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("bd")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER}, auth=ctx.people["owner"])
    return name


def _version(ctx: Ctx, name: str, contract, semver: str = "1.0.0"):
    return ctx.api.post(f"{M}/{name}/versions",
                        json={"semver": semver, "contract": contract},
                        auth=ctx.people["developer"])


def _contract_of(ctx: Ctx, contract):
    """Register a version carrying this contract, and return the response."""
    return _version(ctx, _model(ctx), contract)


@case("QA-FX-406", "A contract section spelled `assumption`")
def fx_406(ctx: Ctx) -> Result:
    """The whole section vanishes. `contract_of` reads `assumptions` with
    `.get`, so a singular spelling produces an empty contract that passes
    every check — refinement holds vacuously and the boundary never fires."""
    got = _contract_of(ctx, {"assumption": [{"key": "dscr", "minimum": 0}],
                             "guarantees": []})
    if got.status_code < 400:
        return FAIL, ("a contract whose section is spelled `assumption` was "
                      "accepted, so the version is governed by nothing and "
                      "reads as governed")
    if "assumption" not in got.text:
        return FAIL, f"the refusal does not name the misspelling: {got.text[:170]}"
    if "assumptions" not in got.text or "guarantees" not in got.text:
        return FAIL, (f"the refusal does not list the keys that ARE read: "
                      f"{got.text[:170]}")
    return PASS, f"refused '{code_of(got)}', naming the known keys"


@case("QA-FX-407", "`min` and `max` instead of `minimum` and `maximum`")
def fx_407(ctx: Ctx) -> Result:
    """The clause survives and the bound does not — it appears in the
    contract, is rendered on the page, and constrains nothing."""
    got = _contract_of(ctx, {"assumptions": [{"key": "dscr", "min": 0,
                                              "max": 20}],
                             "guarantees": []})
    if got.status_code < 400:
        return FAIL, ("a clause spelled `min`/`max` was accepted, leaving a "
                      "bound that appears in the contract and binds nothing")
    said = got.text
    if "minimum" not in said or "maximum" not in said:
        return FAIL, f"the refusal does not give the right spelling: {said[:170]}"
    if "dscr" not in said:
        return FAIL, f"the refusal does not name the clause: {said[:170]}"
    if "UNBOUNDED" not in said and "unbounded" not in said:
        return FAIL, "the refusal does not say what the misspelling costs"
    return PASS, "refused, naming the clause and the right spelling"


@case("QA-FX-409", "A clause with no `key`")
def fx_409(ctx: Ctx) -> Result:
    """Refused by name, not a 500. A clause with no key has nothing to
    constrain, and a raw `KeyError` reaching a caller is the shape this
    check exists to replace."""
    got = _contract_of(ctx, {"assumptions": [{"minimum": 0, "maximum": 20}],
                             "guarantees": []})
    if got.status_code >= 500:
        return FAIL, (f"a clause with no key answered {got.status_code}: "
                      f"{got.text[:150]}")
    if got.status_code < 400:
        return FAIL, "a clause constraining nothing was accepted"
    if "assumptions[0]" not in got.text:
        return FAIL, f"the refusal does not say which clause: {got.text[:170]}"
    if "key" not in got.text:
        return FAIL, f"the refusal does not say what is missing: {got.text[:170]}"
    return PASS, f"refused '{code_of(got)}' at {got.status_code}, naming the clause"


@case("QA-FX-408", "A minimum above the maximum")
def fx_408(ctx: Ctx) -> Result:
    """An admissible region no input can be inside. Every call is outside
    the assumption, so under `reject` the model can never run and under any
    other policy the guarantee can never apply."""
    got = _contract_of(ctx, {"assumptions": [{"key": "dscr", "minimum": 20,
                                              "maximum": 0}],
                             "guarantees": []})
    if got.status_code < 400:
        return FAIL, "a bound admitting nothing at all was accepted"
    if "20" not in got.text or "0" not in got.text:
        return FAIL, f"the refusal does not name the two values: {got.text[:170]}"
    if "admits nothing" not in got.text:
        return FAIL, f"the refusal does not say what the region is: {got.text[:170]}"
    return PASS, "refused, naming the inverted bound and what it admits"


@case("QA-FX-410", "An unknown `on_boundary_violation` value")
def fx_410(ctx: Ctx) -> Result:
    """The policy decides what happens when a model is asked something
    outside its assumption. An unrecognised value falling back to a default
    would make the strictest and the loosest setting render identically."""
    from core.registry.versions import VersionService
    got = _contract_of(ctx, {"assumptions": [{"key": "dscr", "minimum": 0}],
                             "guarantees": [],
                             "on_boundary_violation": "warn"})
    if got.status_code < 400:
        return FAIL, ("an unrecognised boundary policy was accepted; "
                      "whatever it now does is not what was written")
    policies = sorted(VersionService.BOUNDARY_POLICIES)
    missing = [p for p in policies if p not in got.text]
    if missing:
        return FAIL, (f"the refusal does not name {missing}: {got.text[:170]}")
    return PASS, f"refused, naming all {len(policies)} policies: {policies}"


@case("QA-FX-402", "Exactly at the minimum and exactly at the maximum")
def fx_402(ctx: Ctx) -> Result:
    """The bounds are inclusive. An exclusive maximum would refuse the
    highest value anybody tested the model at, which is the value most
    likely to be sent."""
    from core.domain.contracts import Bound
    bound = Bound("dscr", minimum=0.0, maximum=20.0)
    for value in (0, 0.0, 20, 20.0):
        if not bound.contains(value):
            return FAIL, (f"{value!r} is outside an inclusive [0, 20]; a "
                          f"boundary that excludes its own endpoints refuses "
                          f"the values the model was tested at")
    if bound.contains(-1e-9):
        return FAIL, "a value below the minimum is inside the bound"
    if bound.contains(20 + 1e-9):
        return FAIL, "a value above the maximum is inside the bound"
    return PASS, "0 and 20 are inside; one epsilon either side is not"


@case("QA-FX-403", "One epsilon below the minimum", isolated=True)
def fx_403(ctx: Ctx) -> Result:
    """The other side of the boundary, driven through the engine rather
    than the bound: what matters is that a violation under `reject` refuses
    before an artifact is touched."""
    from core.domain.contracts import Bound, Contract
    from core.execution.errors import WarrantError
    engine = ctx.ui.app.state.ctx.get("engine")
    if engine is None:
        return BLOCKED, "no execution engine is wired"
    contract = Contract((Bound("dscr", minimum=0.0, maximum=20.0),))
    violations = contract.check_inputs({"dscr": -1e-9})
    if not violations:
        return FAIL, ("a value one epsilon below the minimum is not a "
                      "violation")
    if "dscr" not in " ".join(violations):
        return FAIL, f"the violation does not name the key: {violations}"
    inside = contract.check_inputs({"dscr": 0})
    if inside:
        return FAIL, f"the minimum itself is a violation: {inside}"
    from routes.base import STATUS
    if STATUS.get("boundary_violation") != 422:
        return FAIL, (f"'boundary_violation' maps to "
                      f"{STATUS.get('boundary_violation')} rather than 422")
    del WarrantError
    return PASS, ("-1e-9 violates and 0 does not; the refusal maps to 422")


@case("QA-FX-404", "An `allowed` list with the value present, then absent")
def fx_404(ctx: Ctx) -> Result:
    """A categorical bound is a different kind of constraint from a band,
    and `contains` has to treat it as one rather than trying to make a
    number of it."""
    from core.domain.contracts import Bound
    bound = Bound("product", allowed=("mtg", "btl"))
    if not bound.contains("mtg") or not bound.contains("btl"):
        return FAIL, "a listed category is outside its own allowed list"
    if bound.contains("card"):
        return FAIL, "an unlisted category is inside the allowed list"
    if bound.contains(0):
        return FAIL, ("a number is inside a categorical bound, so a numeric "
                      "input against a category list is not caught")
    numeric = Bound("dscr", minimum=0.0, maximum=20.0)
    if numeric.contains("mtg"):
        return FAIL, ("a non-numeric value is inside a numeric bound; outside "
                      "the assumption is the safe answer and it was not given")
    return PASS, ("categories match by membership and numbers are not coerced "
                  "into them, either way round")


@case("QA-FX-405", "An assumption whose key no input supplies")
def fx_405(ctx: Ctx) -> Result:
    """Not a violation — but "the boundary held" and "the boundary never
    applied" look identical from `boundary_ok` alone, and the second is
    what a silently unenforced contract looks like from outside."""
    from core.domain.contracts import Bound, Contract
    contract = Contract((Bound("dscr", minimum=0.0, maximum=20.0),
                         Bound("ltv", minimum=0.0, maximum=1.0)))
    inputs = {"dscr": 5}
    violations = contract.check_inputs(inputs)
    if violations:
        return FAIL, (f"an assumption with no value supplied is a violation: "
                      f"{violations}")
    unchecked = contract.unchecked_inputs(inputs)
    if "ltv" not in unchecked:
        return FAIL, (f"the contract does not report the unchecked assumption: "
                      f"{unchecked}")
    if "dscr" in unchecked:
        return FAIL, "a checked assumption is reported as unchecked"
    import inspect

    from core.execution.engine import CaptiveEngine
    source = inspect.getsource(CaptiveEngine.execute)
    if "unchecked" not in source:
        return FAIL, "the engine does not consult the unchecked assumptions"
    from core.execution.engine import ExecutionResult
    fields = set(getattr(ExecutionResult, "__dataclass_fields__", {}))
    if any("unchecked" in f for f in fields):
        return PASS, (f"the unchecked assumptions are carried on the result: "
                      f"{sorted(f for f in fields if 'unchecked' in f)}")
    # Read the block that follows `if unchecked:` rather than one line, which
    # is where a multi-line logger call hides from a per-line search.
    at = source.index("if unchecked:")
    block = source[at:at + 600]
    if "logger" not in block:
        return FAIL, "an unchecked assumption is neither logged nor reported"
    return FAIL, (
        f"a contract clause whose key no input supplies is correctly not a "
        f"violation, and `Contract.unchecked_inputs` names it — {sorted(unchecked)} "
        f"— but the engine only LOGS it. `ExecutionResult` carries "
        f"`boundary_ok` and `boundary_violations` and nothing about what was "
        f"never checked, so a caller cannot tell a boundary that held from one "
        f"that never applied. A contract on `ltv` against a runtime that is "
        f"never sent `ltv` reports `boundary_ok: true` on every call, which is "
        f"exactly what a silently unenforced contract looks like from outside "
        f"— and the code comment beside the log line says so")


@case("QA-FX-401", "The same input under `clamp`", isolated=True)
def fx_401(ctx: Ctx) -> Result:
    """`clamp` is one of the declared policies. Whatever it does has to be
    what it says — a policy that is accepted at registration and then
    behaves like another one is a contract nobody can read off the
    document."""
    import inspect

    from core.execution.engine import CaptiveEngine
    from core.registry.versions import VersionService
    policies = sorted(VersionService.BOUNDARY_POLICIES)
    if "clamp" not in policies:
        return PASS, f"clamp is not a declared policy: {policies}"
    source = inspect.getsource(CaptiveEngine)
    if "clamp" in source:
        return PASS, "the engine acts on clamp"
    accepted = _contract_of(ctx, {"assumptions": [{"key": "dscr", "minimum": 0,
                                                   "maximum": 20}],
                                  "guarantees": [],
                                  "on_boundary_violation": "clamp"})
    if accepted.status_code >= 400:
        return PASS, (f"a clamp contract is refused at registration: "
                      f"{code_of(accepted)}")
    return FAIL, (
        f"`clamp` is one of the {len(policies)} policies a version may declare "
        f"({policies}) and it is accepted at registration, and the word does "
        f"not appear anywhere in the execution engine. The boundary check "
        f"refuses only when the policy is `reject`, so a version declaring "
        f"`clamp` runs the model on the value it was sent — unclamped and "
        f"unrefused — and reports `boundary_ok: false` afterwards. A caller "
        f"reading the contract sees a value that will be brought inside the "
        f"assumption; what happens is that the assumption is ignored")
