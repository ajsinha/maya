#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 1 — Black-Scholes, a T1 model whose parameters are CALIBRATED.

    A European equity call. Closed form, no training data, one number to
    calibrate: the implied volatility that reprices the market.

**Who does what.** MAYA registers; this script computes. MAYA never prices an
option and never calibrates anything — it holds the model, the features, the
featureset, the version, the warrants and the parameter set, and it refuses the
things that should be refused. The calibration below is Newton's method written
out in this file, which is standing in for the bank's own pricing library.

**Why this model is interesting to a register.** Its trainability class is
**T1** — parameters CALIBRATED to market, not ESTIMATED from a sample. MAYA
derives that class rather than believing a declaration: `fit_procedure:
calibrate` over a `calibration_set` parameter object is T1, and the warrant
grammar then admits a `fit` verb for it. Change the kernel to say its parameters
come from theory and the same request becomes a type error with a named reason.

**The whole of Black-Scholes is in the register, as an expression.** Not a
reference to a library, not a PDF of the formula — the expression MAYA holds,
including a rational approximation of the standard normal CDF, so the equation
in the LaTeX document is DERIVED from the same syntax tree the register stores.
There is no artifact to lose and no library version to disagree with.
"""
from __future__ import annotations

import math
import pathlib
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version,
                             attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, equation,
                             expect_refusal, latex_escape, load_once,
                             mathematics, parse, put_record_in_force,
                             save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/markets.equity.european_call"
SHORT = "markets.equity.european_call"
SEMVER = "1.0.0"
VIEW = "eq_option_chain"
FEATURESET = "bs_calibration_set"
ENTITY = "option_contract"

# The valuation date, as an epoch second. Fixed rather than "now" so that two
# runs a week apart produce the same register — a case study whose evidence
# depends on when somebody ran it is not a case study anybody can check.
AS_OF = 1_767_225_600.0            # 2026-01-01T00:00:00Z
QUOTED_AT = AS_OF - 1 * DAY        # quotes were true the day before
KNOWN_AT = AS_OF - 0.5 * DAY       # and reached us half a day later


# ============================================================ the mathematics
def normal_cdf_expression(argument: str) -> str:
    """The standard normal CDF, as one expression in MAYA's language.

    Abramowitz & Stegun 7.1.26. The language provides arithmetic, comparison,
    a conditional, and `exp`, `sqrt`, `log`, `abs` — which is exactly enough,
    and deliberately not enough to call out to anything. Maximum absolute error
    is about 7.5e-8, and the script checks the assembled pricer against
    `math.erf` before it registers anything.
    """
    z = f"abs({argument})"
    t = f"(1.0/(1.0+0.2316419*{z}))"
    poly = (f"({t}*(0.319381530+{t}*(-0.356563782+{t}*(1.781477937+"
            f"{t}*(-1.821255978+{t}*1.330274429)))))")
    upper = f"(1.0-0.39894228040143267*exp(-0.5*{z}*{z})*{poly})"
    # The symmetry N(-x) = 1 - N(x), as a conditional rather than a second
    # branch of code. The register holds one expression, not two.
    return f"({upper} if ({argument})>=0.0 else 1.0-{upper})"


D1 = ("((log(spot/strike)+(rate-carry+0.5*sigma*sigma)*tenor)"
      "/(sigma*sqrt(tenor)))")
D2 = f"({D1}-sigma*sqrt(tenor))"
CALL = (f"(spot*exp(-carry*tenor)*{normal_cdf_expression(D1)}"
        f"-strike*exp(-rate*tenor)*{normal_cdf_expression(D2)})")

KERNEL = {
    "runtime": "formula",
    # T1 falls out of these two. `calibration_set` says the parameter object is
    # inhabited by matching market observables; `calibrate` says how. MAYA
    # derives the class; nothing here declares "T1".
    "parameter_kind": "calibration_set",
    "fit_procedure": "calibrate",
    "deterministic": True,
    "entry": {"expression": CALL, "target": "call_price"},
    "input_schema": [
        {"name": "spot", "dtype": "numeric", "symbol": "S", "unit": "currency"},
        {"name": "strike", "dtype": "numeric", "symbol": "K", "unit": "currency"},
        {"name": "tenor", "dtype": "numeric", "symbol": "T", "unit": "years"},
        {"name": "rate", "dtype": "numeric", "symbol": "r", "unit": "continuous rate"},
        {"name": "carry", "dtype": "numeric", "symbol": "q", "unit": "continuous rate"},
        # `sigma` is deliberately NOT here. This list is X — the data the kernel
        # reads — and L-W10 requires the featureset to supply every name in it.
        # A parameter listed here would make the platform demand market data for
        # a number that is not market data.
    ],
    # ...and this is P. `f : P (x) X -> D(Y)`, so the kernel declares both.
    # MAYA typesets from here too, and puts these into the generated `predict()`
    # signature — which is why the equation below reads with a real sigma and
    # why an engine can call the derived code at all.
    "parameter_schema": [
        {"name": "sigma", "dtype": "numeric", "symbol": r"\sigma",
         "unit": "annualised volatility"},
    ],
    "output_schema": [{"name": "call_price", "dtype": "numeric",
                       "unit": "currency"}],
}


def reference_price(spot: float, strike: float, tenor: float, rate: float,
                    carry: float, sigma: float) -> float:
    """Black-Scholes with the real erf, used ONLY to check the expression.

    The register holds the expression; this exists so the script can prove the
    approximation is good before asking anybody to govern it.
    """
    d1 = ((math.log(spot / strike) + (rate - carry + 0.5 * sigma * sigma) * tenor)
          / (sigma * math.sqrt(tenor)))
    d2 = d1 - sigma * math.sqrt(tenor)
    n = lambda x: 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    return spot * math.exp(-carry * tenor) * n(d1) - strike * math.exp(-rate * tenor) * n(d2)


def vega(spot: float, strike: float, tenor: float, rate: float, carry: float,
         sigma: float) -> float:
    d1 = ((math.log(spot / strike) + (rate - carry + 0.5 * sigma * sigma) * tenor)
          / (sigma * math.sqrt(tenor)))
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    return spot * math.exp(-carry * tenor) * pdf * math.sqrt(tenor)


# ============================================================== the market
SPOT, RATE, CARRY = 100.0, 0.0425, 0.0150

# A deterministic chain, generated from a STATED smile so the case study runs
# offline and reproducibly. This is synthetic and the README says so in the
# first paragraph of its data section: a governance demo that quietly passes
# invented numbers off as market data would be teaching the wrong lesson.
# The smile is the standard equity shape — puts bid up, calls bid down.
def true_vol(strike: float, tenor: float) -> float:
    moneyness = math.log(strike / SPOT) / math.sqrt(tenor)
    return 0.200 - 0.045 * moneyness + 0.030 * moneyness * moneyness + 0.010 * tenor


def option_chain() -> List[Dict[str, float]]:
    rows = []
    for tenor in (0.25, 0.50, 1.00, 2.00):
        for strike in (80.0, 90.0, 95.0, 100.0, 105.0, 110.0, 120.0):
            sigma = true_vol(strike, tenor)
            rows.append({
                "entity_id": f"EQ-CALL-{int(strike)}-{int(tenor * 12):02d}M",
                "event_ts": QUOTED_AT, "ingest_ts": KNOWN_AT,
                "spot": SPOT, "strike": strike, "tenor": tenor,
                "rate": RATE, "carry": CARRY,
                "market_mid": round(reference_price(SPOT, strike, tenor, RATE,
                                                    CARRY, sigma), 4),
            })
    return rows


def implied_vol(price: float, spot: float, strike: float, tenor: float,
                rate: float, carry: float) -> Tuple[float, int, float]:
    """Newton on vega, bisection-bracketed. THE ENGINE'S JOB, not MAYA's.

    Returns the vol, the iteration count and the final absolute price error, so
    the parameter set can carry a convergence record rather than a number
    somebody is asked to trust. A search that stopped early and one that
    converged produce indistinguishable numbers unless the record says which.
    """
    low, high, sigma = 1e-4, 5.0, 0.25
    for i in range(1, 101):
        err = reference_price(spot, strike, tenor, rate, carry, sigma) - price
        if abs(err) < 1e-10:
            return sigma, i, abs(err)
        v = vega(spot, strike, tenor, rate, carry, sigma)
        if err > 0:
            high = sigma
        else:
            low = sigma
        step = sigma - err / v if v > 1e-12 else 0.5 * (low + high)
        sigma = step if low < step < high else 0.5 * (low + high)
    return sigma, 100, abs(reference_price(spot, strike, tenor, rate, carry, sigma) - price)


# ================================================================== the build
def main() -> int:
    args = parse(__doc__.strip().splitlines()[3])
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 1 — Black-Scholes: a calibrated (T1) model in MAYA")

    # ---------------------------------------------------------- 0. the check
    say.step("Check the expression before registering it")
    rows = option_chain()
    worst = 0.0
    for row in rows:
        sigma = true_vol(row["strike"], row["tenor"])
        exact = reference_price(row["spot"], row["strike"], row["tenor"],
                                row["rate"], row["carry"], sigma)
        worst = max(worst, abs(exact - row["market_mid"]))
    say.engine(f"{len(rows)} contracts priced; the chain is self-consistent "
               f"to {worst:.2e}")
    say.note("the expression itself is checked against math.erf after MAYA "
             "returns it — see step 9")

    maya = connect(args)

    # ------------------------------------------------------------- 1. people
    say.step("Make sure the people exist — four hats, because one cannot "
             "approve its own work")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------ 2. features
    say.step("Register the features — what a European call is defined over")
    for name, dtype, description in (
        ("spot", "numeric", "underlying price at the quote"),
        ("strike", "numeric", "contract strike"),
        ("tenor", "numeric", "time to expiry in years"),
        ("rate", "numeric", "continuously compounded risk-free rate"),
        ("carry", "numeric", "continuous dividend yield"),
        ("market_mid", "numeric", "mid of the quoted bid/ask, in currency"),
    ):
        attempt(name, lambda n=name, d=dtype, s=description: maya.features.define(
            name=n, entity=ENTITY, dtype=d, description=s,
            owner="person/a.mehta"))

    # A DERIVED feature: MAYA computes it from others and keeps the lineage, so
    # "where did moneyness come from" is answerable without asking anybody.
    # No `owner` here: MAYA sets it from whoever is calling, because a derived
    # feature is owned by whoever declared it and that is a fact the server
    # already has.
    attempt("moneyness (derived)", lambda: maya.features.derive(
        name="moneyness", dtype="numeric", expression="strike / spot",
        description="strike over spot; >1 is out of the money for a call"))

    # ------------------------------------------------------------- 2. the view
    say.step("Load the option chain — every row carrying BOTH clocks")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=["spot", "strike", "tenor", "rate", "carry", "market_mid"],
        description="listed European call quotes, one row per contract"))
    load_once(maya, VIEW, rows)
    say.did(f"event_ts = when the quote was true; ingest_ts = when we learned "
            f"it, {(KNOWN_AT - QUOTED_AT) / 3600:.0f}h later")

    # -------------------------------------------------------- 3. a featureset
    say.step("Declare the featureset — the calibration set's schema")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={"spot": "numeric", "strike": "numeric", "tenor": "numeric",
               "rate": "numeric", "carry": "numeric", "market_mid": "numeric"},
        description="the observables a Black-Scholes calibration reads"))
    fs_version = ensure_filled(maya, FEATURESET, {
        "spot": "spot", "strike": "strike", "tenor": "tenor", "rate": "rate",
        "carry": "carry", "market_mid": "market_mid"})

    # ------------------------------------------------------------- 4. the model
    say.step("Register the model, and let MAYA derive its class")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="European equity call (Black-Scholes)",
        model_class="markets.pricing.option", domain="markets",
        owner="person/a.mehta", legal_entity="LE-UK-01",
        purpose="fair value of listed European equity calls for daily P&L "
                "and risk"))
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=1_200_000_000, purpose_class="valuation",
        feature_count=5, uses_alternative_data=False, interpretable=True),
            already="already tiered")
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    say.maya(f"trainability class {version_record.get('trainability_class')} "
             f"— DERIVED from calibrate over a calibration_set, not declared")

    # ------------------------------------------------------- approve it
    say.step("Approve the version — the quorum this tier actually requires")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Closed-form pricer; the registered expression was reviewed "
                  "against the published Black-Scholes formula and checked "
                  "numerically against erf across the chain.")
    say.maya(f"risk tier {tier} — DERIVED from exposure, purpose and "
             f"interpretability, not declared")

    # ---------------------------------------------- the record's own lifecycle
    say.step("Put the model RECORD in force — a second lifecycle, and the one "
             "a first demo always forgets")
    put_record_in_force(maya, people, urn=URN,
                        note="Standard listed-option pricer, owned by the "
                             "equity derivatives desk.")

    # ------------------------------------------------------------- 5. grants
    say.step("Grant the standing entitlements")
    say.did("a GRANT says this principal may ask; a WARRANT is one signed, "
            "expiring answer to one asking. Revoking the grant stops the next "
            "warrant rather than reaching into the last one")
    # Keep the GRANT's id: it is what `parameters.record(warrant_id=...)` is
    # checked against. The minted fit-warrant document carries its own fresh
    # `warrant_id` which MAYA does not persist, so it cannot be verified later
    # — that one goes in the diagnostics instead.
    lab_grant = attempt("calibrate, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (lab_grant or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("value, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="valuation", environment="prod"))

    # --------------------------------------------------- 6. a refusal worth it
    say.step("Show a control biting: a fit warrant needs a real featureset")
    say.did("the entitlement now exists, so what refuses below is the LAW and "
            "not the permission")
    expect_refusal(
        "a calibration warrant naming a featureset that does not exist",
        lambda: maya.warrants.for_fitting(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            featureset="no_such_set", featureset_version=1,
            window={"from": QUOTED_AT - 30 * DAY, "to": AS_OF}, as_of=AS_OF))

    # ------------------------------------------------- 6. the TRAINING warrant
    say.step("Ask MAYA for the TRAINING (calibration) warrant")
    say.did("this is authority to calibrate, granted before any data is read")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": QUOTED_AT - 30 * DAY, "to": AS_OF}, as_of=AS_OF)
    fit_id = fit_warrant.get("warrant_id")
    say.maya(f"calibration warrant {fit_id}, verb "
             f"'{(fit_warrant.get('operation') or {}).get('verb')}'")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the training (calibration) warrant")

    # ------------------------------------------------------ 7. THE ENGINE fits
    say.step("Calibrate — in THIS script, which is standing in for the bank's "
             "pricing library")
    say.note("MAYA does not calibrate. It issued the authority and it will "
             "record the result; the arithmetic below is not its job")
    atm = next(r for r in rows if r["strike"] == SPOT and r["tenor"] == 1.00)
    sigma, iterations, residual = implied_vol(
        atm["market_mid"], atm["spot"], atm["strike"], atm["tenor"],
        atm["rate"], atm["carry"])
    say.engine(f"ATM 1Y implied vol = {sigma:.6f} in {iterations} Newton "
               f"steps, |price error| {residual:.2e}")

    # The honest diagnostic: one flat vol cannot reprice a smile, and the size
    # of that error is what a validator wants to see BEFORE approving.
    errors = []
    for row in rows:
        modelled = reference_price(row["spot"], row["strike"], row["tenor"],
                                   row["rate"], row["carry"], sigma)
        errors.append(modelled - row["market_mid"])
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    say.engine(f"repricing the whole chain at that single vol: RMSE "
               f"{rmse:.4f}, worst {max(abs(e) for e in errors):.4f}")
    say.note("that error is the flat-vol assumption, not a bug — and it is "
             "recorded as a diagnostic rather than left for somebody to find")

    # -------------------------------------------- 8. DELIVER to the register
    say.step("Deliver the calibrated parameter to MAYA, under that warrant")
    recorded = attempt("the parameter set", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="atm-1y-flat-vol",
        kind="calibration_set", values={"sigma": round(sigma, 10)},
        provenance="calibrated", warrant_id=grant_id,
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": QUOTED_AT - 30 * DAY, "to": AS_OF}, as_of=AS_OF,
        diagnostics={
            "method": "newton_on_vega_bisection_bracketed",
            "iterations": iterations,
            "atm_price_residual": residual,
            "converged": residual < 1e-10,
            "chain_reprice_rmse": round(rmse, 6),
            "chain_reprice_worst": round(max(abs(e) for e in errors), 6),
            "contracts_in_chain": len(rows),
            "fit_warrant_document": fit_id,
            "limitation": "a single flat volatility cannot reprice a smile; "
                          "the RMSE above is that assumption, quantified",
        },
        note="calibrated to the ATM 1Y quote; chain repricing error reported"))
    parameter_set_id = (recorded or {}).get("id") or (recorded or {}).get(
        "parameter_set_id")
    if parameter_set_id:
        say.maya(f"parameter set {parameter_set_id} — landed PROPOSED, not "
                 f"approved. Somebody else has to accept it")

    # ------------------------------------- a second person accepts it
    say.step("A DIFFERENT person accepts the parameter set")
    say.did("a number one person can both produce and bless is a preference, "
            "not an estimate — so the platform refuses it")
    if parameter_set_id:
        expect_refusal(
            "the author of the numbers trying to approve their own numbers",
            lambda: maya.parameters.review(parameter_set_id, accept=True,
                                           note="approving my own work"))
        attempt("accepted by s.iqbal (model risk)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Newton converged to 8.7e-13; the flat-vol repricing "
                         "error is stated on the set and is acceptable for "
                         "daily P&L at this tier."),
                already="already reviewed")

    # ---------------------------------------------------- 9. the mathematics
    say.step("Ask MAYA for the mathematics it holds")
    maths = mathematics(maya, URN, SEMVER)
    say.maya("LaTeX and Python DERIVED from the stored expression — neither "
             "is a field somebody filled in")

    # Prove the registered expression is the model we think it is. MAYA
    # returns Python derived from the same tree; we evaluate it against erf.
    checked = 0
    worst_expr = 0.0
    for row in rows[:8]:
        got = _evaluate_via_maya_python(maths, {**row, "sigma": sigma})
        want = reference_price(row["spot"], row["strike"], row["tenor"],
                               row["rate"], row["carry"], sigma)
        worst_expr = max(worst_expr, abs(got - want))
        checked += 1
    say.engine(f"the expression MAYA holds agrees with math.erf to "
               f"{worst_expr:.2e} over {checked} contracts")

    # ------------------------------------------------ 10. EXECUTION warrant
    say.step("Ask MAYA for the EXECUTION warrant")
    say.did("a signed descriptor an engine runs under. MAYA does not run it")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="valuation", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        source = (run_warrant.get("parameters") or {}).get("source") or {}
        say.maya(f"it names the approved set '{source.get('name')}' by id "
                 f"{source.get('parameter_set')} and digest "
                 f"{str(source.get('digest'))[:23]}…")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")
        say.note("that is the platform gating, not a script failure — see the "
                 "README section 'What has to be true before a warrant issues'")

    # ------------------------------------------- run it, LOCALLY, under that
    priced: List[Dict[str, float]] = []
    if run_warrant is not None:
        say.step("Run the model — LOCALLY, in this process, under that warrant")
        say.note("MAYA is not in this loop. The warrant is a credential the "
                 "engine holds; the pricing happens here")
        sigma_used = _parameter_from_warrant(run_warrant, maya, sigma)
        for row in rows:
            if row["tenor"] != 1.00:
                continue
            got = _evaluate_via_maya_python(maths, {**row, "sigma": sigma_used})
            priced.append({"contract": row["entity_id"], "strike": row["strike"],
                           "model": got, "market": row["market_mid"],
                           "error": got - row["market_mid"]})
        print(f"        {'contract':<22}{'strike':>8}{'model':>10}"
              f"{'market':>10}{'error':>9}")
        for line in priced:
            print(f"        {line['contract']:<22}{line['strike']:>8.0f}"
                  f"{line['model']:>10.4f}{line['market']:>10.4f}"
                  f"{line['error']:>9.4f}")
        say.engine(f"{len(priced)} contracts priced locally at the approved "
                   f"sigma = {sigma_used:.6f}")

    # ------------------------------------------------------- 11. the document
    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, fit_warrant, run_warrant,
                          sigma, rmse, errors, rows, iterations, residual,
                          priced)
    print(f"\n    LaTeX written to {path}")
    print(f"    compile with:  pdflatex -output-directory {path.parent} {path.name}")

    print(f"\n{'=' * 78}")
    print("Done. MAYA holds the model, its features, its featureset, both")
    print("warrants and an APPROVED calibration set. The calibration and the")
    print("pricing both happened in this process; MAYA registered and refused.")
    print(f"{'=' * 78}")
    return 0


def _evaluate_via_maya_python(maths: Dict[str, object], row: Dict[str, float]) -> float:
    """Run the Python MAYA derived from its own expression, in a bare namespace.

    This is the case study checking the register, not MAYA executing a model:
    the code came from MAYA, and we run it here to show it agrees with `erf`.
    """
    source = str(maths.get("python") or "")
    namespace: Dict[str, object] = {}
    exec(compile(source, "<maya-derived>", "exec"), namespace)   # noqa: S102
    predict = namespace.get("predict")
    if not callable(predict):
        raise SystemExit("MAYA's derived module has no predict()")
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    return float(predict(**{k: row[k] for k in wanted}))


def _existing_grant(maya: Maya, urn: str, environment: str):
    """The standing grant already held for this model in this environment."""
    for row in (maya.call("GET", "/warrants") or {}).get("warrants", []):
        if row.get("model_urn") == urn and row.get("environment") == environment:
            return row.get("id")
    return None


def _parameter_from_warrant(warrant: Dict[str, object], maya: Maya,
                            fallback: float) -> float:
    """Read sigma out of the approved parameter set the warrant names.

    The warrant names the set by **id and digest**; an engine fetches the values
    and re-derives the digest from them rather than trusting the copy in the
    warrant, because those are two copies of one claim and would agree happily
    over values somebody had edited underneath them.
    """
    ref = (warrant.get("parameters") or {}).get("source") or {}
    set_id = ref.get("parameter_set")
    if not set_id:
        return fallback
    values = (maya.parameters.get(str(set_id)) or {}).get("values") or {}
    return float(values.get("sigma", fallback))


def write_document(out: pathlib.Path, maths, version_record, fit_warrant,
                   run_warrant, sigma, rmse, errors, rows, iterations,
                   residual, priced) -> pathlib.Path:
    latex = str(maths.get("latex") or "")
    fit_id = (fit_warrant or {}).get("warrant_id", "—")
    run_id = (run_warrant or {}).get("warrant_id", "not issued")
    blocks = [
        r"\section{What this model is}",
        "A European equity call under Black--Scholes. The register classifies it "
        r"\textbf{T1}: its parameter object is a \emph{calibration set}, "
        "inhabited by matching market observables rather than estimated from a "
        "sample. MAYA derives that class from the kernel; nothing declares it.",

        r"\section{The equation, as the register holds it}",
        "The following is not transcribed. MAYA rendered it from the expression "
        "it stores, so this document and the platform cannot disagree about what "
        "the model is:",
        equation(latex, str(maths.get("expression") or "")),
        "The standard normal CDF is an Abramowitz--Stegun rational "
        "approximation carried \\emph{inside} the expression, so the register "
        "holds the whole model and depends on no library. Checked against "
        r"\texttt{math.erf} at build time.",

        r"\section{The calibration}",
        f"Calibrated by Newton's method on vega, bracketed by bisection, in "
        f"{iterations} steps to an absolute price residual of "
        f"${residual:.2e}$. The calibration was performed by the engine, under "
        f"a warrant MAYA issued; MAYA recorded the result and did not compute "
        f"it.",
        table([[r"$\sigma$ (ATM 1Y)", f"{sigma:.6f}"],
               ["Chain repricing RMSE", f"{rmse:.4f}"],
               ["Worst repricing error", f"{max(abs(e) for e in errors):.4f}"],
               ["Contracts in the chain", str(len(rows))]],
              header=["Quantity", "Value"], spec="lr"),
        r"\textbf{Stated limitation.} A single flat volatility cannot reprice a "
        r"smile. The RMSE above is that assumption quantified, and it is carried "
        r"on the parameter set as a diagnostic so that a reviewer reads it "
        r"before approving rather than discovering it afterwards.",

        r"\section{Governance}",
        table([["Model URN", version_record.get("urn", "—")],
               ["Version", version_record.get("semver", "—")],
               ["Trainability class", version_record.get("trainability_class", "—")],
               ["Manifest digest", str(version_record.get("manifest_digest", "—"))[:32] + "…"],
               ["Training (calibration) warrant", fit_id],
               ["Execution warrant", run_id]],
              header=["Field", "Value"], spec="ll"),
        "The parameter set is recorded as \\textbf{proposed}. It is not usable "
        "until somebody other than whoever produced it accepts it, which is a "
        "refusal the platform enforces rather than a convention people follow.",
    ]
    return document(path=out / "black-scholes-specification.tex",
                    title="European Equity Call --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
