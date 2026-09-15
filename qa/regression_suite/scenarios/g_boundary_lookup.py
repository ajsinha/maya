"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — where an operating boundary LOOKS for the value it constrains.

`g_contracts.py` covers the lattice: refinement, composition, the order. This
covers the humbler question underneath it, which is the one that was actually
wrong: given a signed assumption on `turnover` and a call that supplied
`{"features": {"turnover": ...}}`, does the boundary apply?

It did not. The estimator runtime puts its inputs one level down, so the
assumption found no `turnover` at the top level and the clause that skips an
absent key passed it. **A signed operating boundary was unenforced for every
runtime that nests its inputs, silently, with `boundary_ok: true` on the
response** — which is this codebase's worst defect shape arriving in the one
control that stands between a model and a value it was never fitted on.

The cases either side of the fix matter as much as the fix: one level and no
more, because a deep walk starts matching a name several objects down and a
boundary that fires on the WRONG field is worse than one that does not fire;
and an absent value stays a pass, because an assumption constrains a value that
was supplied.
"""
from __future__ import annotations

from core.domain.contracts import Bound, Contract
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _c(*assumptions) -> Contract:
    return Contract(assumptions=tuple(assumptions))


@case("QA-FX-5000", "An assumption on a nested input")
def fx_5000(ctx: Ctx) -> Result:
    """The defect itself. `{"features": {"turnover": 9e9}}` against an
    assumption of `turnover <= 1e6`."""
    contract = _c(Bound("turnover", minimum=0.0, maximum=1_000_000.0))
    nested = {"features": {"turnover": 9_000_000_000.0}}
    failed = contract.check_inputs(nested)
    if "turnover" not in failed:
        return FAIL, ("a value nine thousand times outside its signed "
                      "assumption passed the boundary because the runtime "
                      "nests its inputs one level down, and the response "
                      "would carry `boundary_ok: true`")
    flat = contract.check_inputs({"turnover": 9_000_000_000.0})
    if flat != failed:
        return FAIL, (f"the same value nested and flat give different answers: "
                      f"{failed} against {flat}")
    return PASS, "the nested value is checked exactly as the flat one is"


@case("QA-FX-5001", "One level down and no more")
def fx_5001(ctx: Ctx) -> Result:
    """The bound on the fix. Two levels down, `turnover` is a field of
    something else — a nested object the caller passed for another reason —
    and a boundary that fired on it would refuse a call over a value the model
    was never asked about. That is worse than not firing, because it is wrong
    in a direction nobody can debug."""
    contract = _c(Bound("turnover", minimum=0.0, maximum=1_000_000.0))
    deep = {"request": {"counterparty": {"turnover": 9_000_000_000.0}}}
    failed = contract.check_inputs(deep)
    if failed:
        return FAIL, (f"a value two levels down was matched against the "
                      f"assumption ({failed}), so the boundary fires on a "
                      f"field that happens to share a name")
    unchecked = contract.unchecked_inputs(deep)
    if "turnover" not in unchecked:
        return FAIL, ("the assumption found no value and is not reported as "
                      "unchecked, so 'the boundary held' and 'the boundary "
                      "never applied' look identical")
    return PASS, "not matched two levels down, and reported as unchecked"


@case("QA-FX-5002", "The top level wins a collision")
def fx_5002(ctx: Ctx) -> Result:
    """When the same key appears at the top and one level down, the top level
    is what the caller addressed. Taking the nested one would check a value the
    caller did not mean to offer."""
    contract = _c(Bound("dscr", minimum=1.0, maximum=3.0))
    both = {"dscr": 2.0, "features": {"dscr": 99.0}}
    if contract.check_inputs(both):
        return FAIL, ("the nested value won the collision, so the boundary "
                      "checked a value the caller did not address")
    inverted = {"dscr": 99.0, "features": {"dscr": 2.0}}
    if "dscr" not in contract.check_inputs(inverted):
        return FAIL, ("the nested value won the collision in the other "
                      "direction too, so the top level is never checked when "
                      "a nested key shares its name")
    return PASS, "the top-level value decides, in both directions"


@case("QA-FX-5003", "A value outside a closed vocabulary")
def fx_5003(ctx: Ctx) -> Result:
    """A categorical bound has no band, so `contains` is membership. It also
    has no nearest edge, which is why `clamp` cannot act on one — there is no
    value between `mtg` and `btl`, and guessing a category would be the engine
    choosing what the model was asked about."""
    contract = _c(Bound("product", allowed=("mtg", "btl")))
    if "product" not in contract.check_inputs({"product": "personal_loan"}):
        return FAIL, "a value outside the closed vocabulary passed"
    if contract.check_inputs({"product": "mtg"}):
        return FAIL, "a value inside the vocabulary was refused"
    _values, changes = contract.clamp_inputs({"product": "personal_loan"})
    if changes:
        return FAIL, (f"a categorical violation was CLAMPED to {changes}, so "
                      f"the engine chose which product the model was asked "
                      f"about")
    return PASS, "refused, and not clamped — there is no nearest category"


@case("QA-FX-5004", "A non-numeric value where a number was declared")
def fx_5004(ctx: Ctx) -> Result:
    """Outside the assumption, so the guarantee is void — and NOT an exception.
    A contract that raised here would turn a governance answer into a 500, and
    the caller would learn nothing about the boundary."""
    contract = _c(Bound("dscr", minimum=1.0, maximum=3.0))
    try:
        failed = contract.check_inputs({"dscr": "not a number"})
    except Exception as exc:
        return FAIL, (f"a non-numeric value raised {type(exc).__name__} rather "
                      f"than being reported outside the boundary")
    if "dscr" not in failed:
        return FAIL, ("a non-numeric value where a number was declared passed "
                      "the numeric band, so the guarantee stands over a value "
                      "that is not a number")
    _values, changes = contract.clamp_inputs({"dscr": "not a number"})
    if changes:
        return FAIL, f"a non-numeric value was clamped to {changes}"
    return PASS, "outside the boundary, not raised, and not clamped"


@case("QA-FX-5005", "An absent value is not a violation")
def fx_5005(ctx: Ctx) -> Result:
    """Deliberate, and it is the half that makes the nesting fix safe. An
    assumption constrains a value that was SUPPLIED; a caller who supplies
    nothing has not violated a band, and refusing them would refuse every
    partial call the contract was never written about."""
    contract = _c(Bound("ltv", minimum=0.0, maximum=0.95),
                  Bound("dscr", minimum=1.0, maximum=3.0))
    failed = contract.check_inputs({"dscr": 2.0})
    if failed:
        return FAIL, (f"an assumption on a key nobody supplied was counted as "
                      f"violated: {failed}")
    return PASS, "the supplied value is checked and the absent one is not"


@case("QA-FX-5006", "An absent value IS reported as unchecked")
def fx_5006(ctx: Ctx) -> Result:
    """The other half, and the reason the first is not a hole. If absence were
    only a pass, *the boundary held* and *the boundary did not apply* would be
    the same answer — and a contract silently constraining nothing would look
    exactly like a model operating inside every band it declared."""
    contract = _c(Bound("ltv", minimum=0.0, maximum=0.95),
                  Bound("dscr", minimum=1.0, maximum=3.0))
    unchecked = contract.unchecked_inputs({"dscr": 2.0})
    if unchecked != ["ltv"]:
        return FAIL, (f"the assumption that found no value is reported as "
                      f"{unchecked}, so a boundary that applied to nothing "
                      f"cannot be told from one that held")
    if contract.unchecked_inputs({"dscr": 2.0, "ltv": 0.5}):
        return FAIL, "an assumption that DID find a value is reported unchecked"
    return PASS, "the assumption that found no value is named"


@case("QA-FX-5007", "A contract that checked nothing at all")
def fx_5007(ctx: Ctx) -> Result:
    """The end state of the two rules above, and the one worth refusing to
    print as success: every assumption found no value, so the boundary passed
    without applying to anything. `boundary_ok` alone cannot say this, which
    is why `unchecked` travels beside it."""
    contract = _c(Bound("ltv", minimum=0.0, maximum=0.95),
                  Bound("dscr", minimum=1.0, maximum=3.0))
    values = {"something_else": 1.0}
    if contract.check_inputs(values):
        return FAIL, "a contract that found no values reported a violation"
    unchecked = contract.unchecked_inputs(values)
    if sorted(unchecked) != ["dscr", "ltv"]:
        return FAIL, (f"a contract that applied to NOTHING reports only "
                      f"{unchecked} as unchecked, so a caller reading "
                      f"`boundary_ok: true` cannot tell that the boundary was "
                      f"never exercised")
    return PASS, ("every assumption is named as unchecked, so a boundary that "
                  "applied to nothing says so")
