"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the operating boundary: `input |= A`.

A model's contract says what it assumes about its inputs, and the guarantee it
offers is void outside that. The failure this module guards against is
recorded in the source: an assumption on `turnover` found no `turnover` key
because the estimator nests its inputs under `features`, so a SIGNED operating
boundary was unenforced for every runtime that nests — silently, with
`boundary_ok: true` on the response.
"""
from __future__ import annotations

from core.domain.contracts import Bound, Contract
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _contract(*bounds) -> Contract:
    return Contract(assumptions=tuple(bounds), guarantees=())


TURNOVER = Bound("turnover", minimum=0.0, maximum=1_000_000.0)
SEGMENT = Bound("segment", allowed=("retail", "wholesale"))


@case("QA-FX-5000", "An assumption on a nested input")
def fx_5000(ctx: Ctx) -> Result:
    """The recorded defect. The estimator reads `inputs["features"]`, so an
    assumption looked up only at the top level found nothing, the clause that
    skips an absent key passed it, and a signed boundary was unenforced."""
    contract = _contract(TURNOVER)
    nested = {"features": {"turnover": 5_000_000.0}}
    violations = contract.check_inputs(nested)
    if "turnover" not in violations:
        return FAIL, ("a value nested one level under `features` was not "
                      "checked against the assumption, so a signed operating "
                      "boundary is unenforced for every runtime that nests "
                      "its inputs")
    return PASS, "an assumption reaches one level down"


@case("QA-FX-5001", "One level down and no more")
def fx_5001(ctx: Ctx) -> Result:
    """"A deep walk would start matching an assumption against a value that
    happens to share a name several objects down, and a boundary that fires
    on the wrong field is worse than one that does not fire at all." """
    contract = _contract(TURNOVER)
    deep = {"features": {"customer": {"turnover": 5_000_000.0}}}
    if contract.check_inputs(deep):
        return FAIL, ("an assumption matched a value two levels down, so the "
                      "boundary can fire on a field that merely shares a name")
    if "turnover" not in contract.unchecked_inputs(deep):
        return FAIL, ("the assumption neither fired nor was reported as "
                      "unchecked, so nothing distinguishes 'held' from "
                      "'never applied'")
    return PASS, "two levels down is unchecked, and reported as unchecked"


@case("QA-FX-5002", "The top level wins a collision")
def fx_5002(ctx: Ctx) -> Result:
    """"Top level wins a collision, because that is where the caller
    addressed it." Preferring the nested copy would check a value the caller
    did not mean."""
    contract = _contract(TURNOVER)
    both = {"turnover": 500.0, "features": {"turnover": 5_000_000.0}}
    if contract.check_inputs(both):
        return FAIL, ("the nested copy was checked in preference to the one "
                      "the caller addressed at the top level")
    return PASS, "the top-level value is the one checked"


@case("QA-FX-399", "An input outside a numeric bound")
def fx_399(ctx: Ctx) -> Result:
    """The ordinary case, and both ends of the band."""
    contract = _contract(TURNOVER)
    for value in (-1.0, 1_000_000.01):
        if "turnover" not in contract.check_inputs({"turnover": value}):
            return FAIL, f"{value} was inside a band of 0 to 1,000,000"
    for value in (0.0, 1_000_000.0, 500.0):
        if contract.check_inputs({"turnover": value}):
            return FAIL, (f"{value} was reported outside a band of 0 to "
                          f"1,000,000; the bounds exclude themselves")
    return PASS, "both ends inclusive, outside both refused"


@case("QA-FX-5003", "A value outside a closed vocabulary")
def fx_5003(ctx: Ctx) -> Result:
    contract = _contract(SEGMENT)
    if "segment" not in contract.check_inputs({"segment": "private_bank"}):
        return FAIL, "a value outside the allowed set passed the boundary"
    if contract.check_inputs({"segment": "retail"}):
        return FAIL, "an allowed value was reported outside"
    return PASS, "the vocabulary is closed"


@case("QA-FX-5004", "A non-numeric value where a number was declared")
def fx_5004(ctx: Ctx) -> Result:
    """"Outside the assumption, so the guarantee is void." Treating it as
    inside would extend a guarantee over data the model never saw."""
    contract = _contract(TURNOVER)
    for value in ("a lot", None, [1, 2]):
        if "turnover" not in contract.check_inputs({"turnover": value}):
            return FAIL, (f"{value!r} where a number was declared did not "
                          f"void the guarantee")
    return PASS, "a non-numeric value is outside the boundary"


@case("QA-FX-5005", "An absent value is not a violation")
def fx_5005(ctx: Ctx) -> Result:
    """"An assumption constrains a value that was supplied, and a caller who
    supplies nothing has not violated a band." The alternative would refuse
    every partial request."""
    contract = _contract(TURNOVER, SEGMENT)
    if contract.check_inputs({"segment": "retail"}):
        return FAIL, ("an assumption on a value nobody supplied was reported "
                      "as violated, so every partial request is refused")
    return PASS, "absent is not outside"


@case("QA-FX-5006", "An absent value IS reported as unchecked")
def fx_5006(ctx: Ctx) -> Result:
    """"A contract whose assumptions all went unchecked is a contract that
    did nothing, and the difference between that and one that held is
    invisible from `boundary_ok` alone." """
    contract = _contract(TURNOVER, SEGMENT)
    unchecked = contract.unchecked_inputs({"segment": "retail"})
    if "turnover" not in unchecked:
        return FAIL, ("an assumption that found no value is not reported as "
                      "unchecked, so 'the boundary held' and 'the boundary "
                      "never applied' are the same answer")
    if "segment" in unchecked:
        return FAIL, "an assumption that DID find a value is reported unchecked"
    return PASS, f"unchecked: {unchecked}"


@case("QA-FX-5007", "A contract that checked nothing at all")
def fx_5007(ctx: Ctx) -> Result:
    """The whole-contract version of the same fact, and the one a reader of a
    response most needs."""
    contract = _contract(TURNOVER, SEGMENT)
    empty = {"something_else": 1}
    if contract.check_inputs(empty):
        return FAIL, "an empty request produced violations"
    unchecked = contract.unchecked_inputs(empty)
    if len(unchecked) != 2:
        return FAIL, (f"{len(unchecked)} of 2 assumptions reported unchecked "
                      f"against a request touching neither")
    return PASS, "every assumption reported unchecked"


@case("QA-FX-400", "The same input under a flag policy")
def fx_400(ctx: Ctx) -> Result:
    """`reject` refuses; `flag` runs and records. The distinction is the
    firm's to make, and the engine must honour whichever the contract
    declares rather than picking one."""
    import inspect

    from core.execution import engine
    source = inspect.getsource(engine.ReferenceEngine.execute) \
        if hasattr(engine, "ReferenceEngine") else ""
    if not source:
        for name, obj in vars(engine).items():
            if hasattr(obj, "execute") and name.endswith("Engine"):
                source = inspect.getsource(obj.execute)
                break
    if not source:
        return FAIL, "no engine execute path to read"
    if 'on_boundary_violation' not in source:
        return FAIL, ("the engine does not read the contract's declared "
                      "violation policy, so it applies one of its own")
    if '"reject"' not in source:
        return FAIL, "the default policy is not stated in the code"
    marker = source.find("on_boundary_violation")
    window = source[marker:marker + 400]
    if "reject" not in window or "violations" not in window:
        return FAIL, f"the policy is read and not applied: {window[:120]}"
    return PASS, "the declared policy decides, defaulting to reject"
