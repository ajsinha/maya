#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 4 — Merton distance to default: a model with NO parameters (T0).

    A firm defaults when the value of its assets falls below what it owes. Under
    the Merton structural model that probability is a closed form in the firm's
    asset value, its debt, its asset volatility, the risk-free rate and the
    horizon. There is nothing to fit and nothing to calibrate.

**Why this one matters to a register.** Every other case study here has a
parameter object somebody had to produce and somebody else had to approve. This
one does not. `P = I`, the terminal object — the model is fully determined by
theory — and MAYA calls that **T0**.

The demonstration is a REFUSAL. Asking for a training warrant on a T0 model is
not a permissions problem to be escalated; it is a **type error**, and MAYA
says so by name:

    its parameters come from theory, not from data — there is nothing to fit

A platform that let you request one, ran it, and stored a "fitted" parameter set
for a model that has no parameters would be recording a fiction. This is the
case study for showing that the taxonomy is load-bearing rather than decorative.

**Who does what.** MAYA registers; this script computes. Every distance to
default below is arithmetic in this file.
"""
from __future__ import annotations

import math
import pathlib
import sys
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, equation, expect_refusal,
                             latex_escape, load_once, mathematics, parse,
                             put_record_in_force, save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/wholesale.credit.merton_dd"
SHORT = "wholesale.credit.merton_dd"
SEMVER = "1.0.0"
VIEW = "corporate_balance_sheets"
FEATURESET = "merton_inputs"
ENTITY = "obligor"

AS_OF = 1_767_225_600.0            # 2026-01-01T00:00:00Z
WINDOW_FROM = 1_735_689_600.0      # 2025-01-01T00:00:00Z
REPORTED_AT = AS_OF - 30 * DAY     # the quarter end these figures describe
FILED_AT = AS_OF - 5 * DAY         # when the filing reached us


# ============================================================= the mathematics
def normal_cdf_expression(argument: str) -> str:
    """Abramowitz & Stegun 7.1.26, in MAYA's expression language.

    The same construction case study 1 uses. Repeated here rather than shared,
    because these two models are independent objects in the register and a
    shared helper between case studies would imply a coupling that does not
    exist in the estate.
    """
    z = f"abs({argument})"
    t = f"(1.0/(1.0+0.2316419*{z}))"
    poly = (f"({t}*(0.319381530+{t}*(-0.356563782+{t}*(1.781477937+"
            f"{t}*(-1.821255978+{t}*1.330274429)))))")
    upper = f"(1.0-0.39894228040143267*exp(-0.5*{z}*{z})*{poly})"
    return f"({upper} if ({argument})>=0.0 else 1.0-{upper})"


#: Distance to default: how many standard deviations of asset value the firm is
#: from the point where assets equal debt, at the horizon.
DD = ("((log(asset_value/debt_face)+(risk_free-0.5*asset_vol*asset_vol)*horizon)"
      "/(asset_vol*sqrt(horizon)))")

#: The risk-neutral default probability is N(-DD). Written as `1 - N(DD)` by
#: the symmetry of the normal, which keeps one CDF in the expression.
PD = f"(1.0-{normal_cdf_expression(DD)})"

KERNEL = {
    "runtime": "formula",
    # T0 falls out of these two, and nothing else in the kernel matters to it.
    # `none` means P is the terminal object: there is no parameter to inhabit.
    "parameter_kind": "none",
    "fit_procedure": "none",
    "deterministic": True,
    "entry": {"expression": PD, "target": "pd_horizon"},
    # Everything the model reads is an OBSERVABLE. That is what makes it T0:
    # there is no residual quantity that had to be learned from a sample.
    "input_schema": [
        {"name": "asset_value", "dtype": "numeric", "symbol": "V",
         "unit": "USD millions"},
        {"name": "debt_face", "dtype": "numeric", "symbol": "D",
         "unit": "USD millions"},
        {"name": "asset_vol", "dtype": "numeric", "symbol": r"\sigma_{V}",
         "unit": "annualised"},
        {"name": "risk_free", "dtype": "numeric", "symbol": "r",
         "unit": "continuous rate"},
        {"name": "horizon", "dtype": "numeric", "symbol": "T", "unit": "years"},
    ],
    # No parameter_schema. There is no P.
    "output_schema": [{"name": "pd_horizon", "dtype": "numeric",
                       "unit": "probability"}],
}


def reference_pd(asset_value: float, debt_face: float, asset_vol: float,
                 risk_free: float, horizon: float) -> float:
    """The same thing with the real erf, to check the registered expression."""
    dd = ((math.log(asset_value / debt_face)
           + (risk_free - 0.5 * asset_vol * asset_vol) * horizon)
          / (asset_vol * math.sqrt(horizon)))
    return 0.5 * (1.0 - math.erf(dd / math.sqrt(2.0)))


def distance_to_default(asset_value: float, debt_face: float, asset_vol: float,
                        risk_free: float, horizon: float) -> float:
    return ((math.log(asset_value / debt_face)
             + (risk_free - 0.5 * asset_vol * asset_vol) * horizon)
            / (asset_vol * math.sqrt(horizon)))


# ================================================================ the obligors
RISK_FREE, HORIZON = 0.0425, 1.0

#: A small wholesale book. Synthetic, and the README says so — asset value and
#: asset volatility are not observable anyway (they are inferred from equity),
#: which is itself the honest limitation of this model and is recorded as one.
OBLIGORS = [
    # name,               assets,   debt,  asset vol,  sector
    ("ACME-INDUSTRIALS",  4_800.0, 2_100.0, 0.22, "industrials"),
    ("BOREAL-MINING",     1_950.0, 1_640.0, 0.41, "materials"),
    ("CALDER-RETAIL",       870.0,   790.0, 0.35, "retail"),
    ("DELTA-UTILITIES",   9_400.0, 5_200.0, 0.14, "utilities"),
    ("EASTPORT-SHIPPING",   620.0,   580.0, 0.48, "transport"),
    ("FENWICK-PHARMA",    3_100.0,   900.0, 0.29, "healthcare"),
    ("GRANITE-REIT",      2_400.0, 1_800.0, 0.19, "real estate"),
    ("HARROW-AIRLINES",     740.0,   810.0, 0.52, "transport"),
]


def rows() -> List[Dict[str, float]]:
    return [{
        "entity_id": name,
        "event_ts": REPORTED_AT, "ingest_ts": FILED_AT,
        "asset_value": assets, "debt_face": debt, "asset_vol": vol,
        "risk_free": RISK_FREE, "horizon": HORIZON,
    } for name, assets, debt, vol, _ in OBLIGORS]


# ================================================================== the build
def main() -> int:
    args = parse("Case study 4 — Merton distance to default, a T0 model")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 4 — Merton distance to default: nothing to fit (T0)")

    say.step("Sanity-check the book before registering anything")
    # Deliberately NOT a comparison of `reference_pd` against itself. An earlier
    # draft of this line did exactly that, computed a difference that is zero by
    # construction, and printed a reassuring number — a check that cannot fail,
    # which is the defect this whole platform is named for. The real check on
    # the expression happens at step 13, against `math.erf`, on the expression
    # MAYA hands back rather than on the one this file holds.
    levered = sum(1 for _n, assets, debt, _v, _s in OBLIGORS if assets < debt)
    say.engine(f"{len(OBLIGORS)} obligors, of which {levered} already have "
               f"assets below debt face — those should price near or above 50% "
               f"and are the ones to look at in the output")

    maya = connect(args)

    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    say.step("Register the features — all five are OBSERVABLES")
    for name, description in (
        ("asset_value", "market value of the firm's assets, USD millions"),
        ("debt_face", "face value of debt due at the horizon, USD millions"),
        ("asset_vol", "annualised volatility of asset value"),
        ("risk_free", "continuously compounded risk-free rate"),
        ("horizon", "years to the debt maturity being modelled"),
    ):
        attempt(name, lambda n=name, d=description: maya.features.define(
            name=n, entity=ENTITY, dtype="numeric", description=d,
            owner="person/a.mehta", source_system="credit analytics"))
    say.did("there is no sixth feature that had to be LEARNED — that absence is "
            "exactly what makes this model T0")

    say.step("Load the book")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=["asset_value", "debt_face", "asset_vol", "risk_free",
                  "horizon"],
        description="quarterly balance-sheet inputs; event_ts is the quarter "
                    "end, ingest_ts is when the filing reached us"))
    load_once(maya, VIEW, rows())

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={"asset_value": "numeric", "debt_face": "numeric",
               "asset_vol": "numeric", "risk_free": "numeric",
               "horizon": "numeric"},
        description="what a Merton distance-to-default reads"))
    fs_version = ensure_filled(maya, FEATURESET, {
        "asset_value": "asset_value", "debt_face": "debt_face",
        "asset_vol": "asset_vol", "risk_free": "risk_free",
        "horizon": "horizon"})

    say.step("Register the model, and let MAYA derive its class")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Merton distance to default",
        model_class="wholesale.credit.structural", domain="wholesale_credit",
        owner="person/j.okafor", legal_entity="LE-UK-01",
        purpose="structural default probability for large corporate obligors, "
                "as a challenger to the internal rating"))
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=2_300_000_000, purpose_class="credit_decision",
        feature_count=5, uses_alternative_data=False, interpretable=True),
            already="already tiered")
    say.maya(f"trainability class {version_record.get('trainability_class')} "
             f"— DERIVED from 'none' over 'none'. P is the terminal object")

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Closed-form structural model; the registered expression was "
                  "checked against the published Merton formulation and "
                  "numerically against erf.")
    say.maya(f"risk tier {tier}")

    say.step("Put the model record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Structural challenger model, owned by wholesale "
                             "credit risk.")

    say.step("Grant the standing entitlements")
    attempt("develop, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    attempt("assess, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="credit_decision", environment="prod"))

    # ================================================== THE POINT OF CASE 4
    say.step("Ask for a TRAINING warrant — which should be a TYPE ERROR")
    say.did("not 'you are not allowed to fit this'. There is nothing to fit, "
            "and MAYA distinguishes the two")
    refusal = expect_refusal(
        "a training warrant for a model whose parameters come from theory",
        lambda: maya.warrants.for_fitting(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            featureset=FEATURESET, featureset_version=fs_version,
            window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF))
    if refusal is not None:
        save_json(out / "refusal-training.json",
                  {"code": refusal.code, "detail": refusal.detail,
                   "remediation": getattr(refusal, "remediation", None)},
                  what="the refusal, kept as the evidence it is")

    say.step("Try to record a parameter set anyway")
    say.did("the second door into the same mistake, and it is shut too")
    expect_refusal(
        "a 'fitted' parameter set for a model with no parameter object",
        lambda: maya.parameters.record(
            urn=URN, semver=SEMVER, name="invented", kind="coefficients",
            values={"alpha": 1.0}, provenance="fitted",
            warrant_id="does-not-exist"))

    # ------------------------------------------------------ EXECUTION warrant
    say.step("Ask MAYA for the EXECUTION warrant")
    say.did("this one issues immediately: a T0 model needs no approved "
            "parameter set, because it has no parameter object to inhabit")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="credit_decision", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        binding = (run_warrant.get("parameters") or {}).get("source") or {}
        say.maya(f"its parameter binding is "
                 f"'{binding.get('binding', 'none')}' — nothing to name")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    # ---------------------------------------------------------- mathematics
    say.step("Ask MAYA for the mathematics it holds")
    maths = mathematics(maya, URN, SEMVER)
    checked = 0
    worst_expr = 0.0
    for row in rows():
        got = _predict(maths, row)
        want = reference_pd(row["asset_value"], row["debt_face"],
                            row["asset_vol"], row["risk_free"], row["horizon"])
        worst_expr = max(worst_expr, abs(got - want))
        checked += 1
    say.engine(f"the expression MAYA holds agrees with math.erf to "
               f"{worst_expr:.2e} over {checked} obligors")

    # ------------------------------------------------------- run it, LOCALLY
    scored: List[Dict[str, object]] = []
    if run_warrant is not None:
        say.step("Score the book — LOCALLY, under that warrant")
        print(f"        {'obligor':<20}{'V/D':>7}{'σ_V':>7}{'DD':>8}"
              f"{'PD %':>9}")
        for (name, assets, debt, vol, _sector), row in zip(OBLIGORS, rows()):
            pd_value = _predict(maths, row)
            dd = distance_to_default(assets, debt, vol, RISK_FREE, HORIZON)
            scored.append({"obligor": name, "leverage": assets / debt,
                           "vol": vol, "dd": dd, "pd": pd_value})
            print(f"        {name:<20}{assets / debt:>7.2f}{vol:>7.2f}"
                  f"{dd:>8.2f}{100 * pd_value:>9.2f}")
        say.engine("no parameter set was fetched, because there is none — the "
                   "warrant authorises, the arithmetic is the model")

    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, run_warrant, scored,
                          refusal, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. A model with no parameters, governed anyway — approved,")
    print("attested, warranted — and a fit request refused as a type error.")
    print(f"{'=' * 78}")
    return 0


def _predict(maths, row: Dict[str, float]) -> float:
    namespace: Dict[str, object] = {}
    exec(compile(str(maths.get("python") or ""),                  # noqa: S102
                 "<maya-derived>", "exec"), namespace)
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    return float(namespace["predict"](**{k: row[k] for k in wanted}))


def write_document(out, maths, version_record, run_warrant, scored, refusal,
                   tier):
    rows_out = [[latex_escape(str(s["obligor"])), f"{s['leverage']:.2f}",
                 f"{s['vol']:.2f}", f"{s['dd']:.2f}",
                 f"{100 * float(s['pd']):.2f}"] for s in scored]
    blocks = [
        r"\section{What this model is}",
        "The Merton structural model: a firm defaults when the value of its "
        "assets falls below what it owes at the horizon. MAYA classifies it "
        r"\textbf{T0} --- its parameter object is the terminal object, $P = I$. "
        "There is nothing to fit and nothing to calibrate, and the class is "
        "derived from the kernel rather than declared.",

        r"\section{The equation, as the register holds it}",
        equation(str(maths.get("latex") or ""),
                 str(maths.get("expression") or "")),

        r"\section{The refusal}",
        "Asking this model for a training warrant is not a permissions problem. "
        "It is a type error, and the platform answers as one:",
        r"\begin{quote}\ttfamily " +
        latex_escape(str((refusal.detail if refusal else "—"))) +
        r"\end{quote}",
        "A platform that issued the warrant, ran a fit and stored a parameter "
        "set for a model with no parameter object would be recording a fiction "
        "--- and would do it silently, since every step would have returned "
        "success.",

        r"\section{The book}",
        table(rows_out,
              header=["Obligor", r"$V/D$", r"$\sigma_V$", "DD", r"PD \%"],
              spec="lrrrr"),
        r"\textbf{Stated limitation.} Asset value and asset volatility are not "
        r"observable. In practice both are inferred from equity value and equity "
        r"volatility by solving the Merton system, which makes the inputs "
        r"themselves model output. This case study takes them as given so that "
        r"the T0 point is not obscured; a production registration would carry "
        r"that inference as its own model, related by an \texttt{input\_to} "
        r"edge.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(str(version_record.get("urn", "—")))],
               ["Version", latex_escape(str(version_record.get("semver", "—")))],
               ["Trainability class", latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["Parameter object", "none (terminal)"],
               ["Training warrant", "REFUSED — nothing to fit"],
               ["Execution warrant", latex_escape(str((run_warrant or {}).get("warrant_id", "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "merton-specification.tex",
                    title="Merton Distance to Default --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
