#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 3 — A NON-LINEAR banking model: exponential seasoning, polynomial
refinancing incentive (T2).

    Mortgage prepayment. The conditional prepayment rate of a pool rises along
    an exponential seasoning ramp as the loans age, and responds to refinancing
    incentive along an S-shaped curve. Both effects in one closed form.

        CPR = b0
            + b_season * (1 - exp(-age/24))          <- exponential
            + b1*i + b2*i^2 + b3*i^3                 <- cubic polynomial in i

**Non-linear in the inputs, linear in the parameters.** That is the whole trick
and it is worth a minute of any demo: the model's *response* to age and to
incentive is a curve, while the thing being estimated is still a coefficient
vector, so ordinary least squares fits it and every coefficient keeps an
interpretation. A bank reaches for this shape constantly — seasoning ramps,
S-curves, decay of recovery, deposit runoff — and it is the honest middle
ground between a straight line that cannot describe the behaviour and a
gradient-boosted machine nobody can explain to a supervisor.

**Who does what.** MAYA registers; this script computes. The design matrix, the
QR solve and the diagnostics are in this file. MAYA issues the training warrant
before any data is read, records coefficients that somebody other than their
author must accept, issues the execution warrant, and never fits or runs
anything.
"""
from __future__ import annotations

import hashlib
import math
import pathlib
import sys
from typing import Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version,
                             attempt, connect, document, ensure_cast,
                             ensure_filled, ensure_version, equation,
                             expect_refusal, latex_escape, load_once,
                             mathematics, parse, put_record_in_force,
                             save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/alm.prepayment.cpr"
SHORT = "alm.prepayment.cpr"
SEMVER = "1.0.0"
VIEW = "mortgage_pool_months"
FEATURESET = "cpr_inputs"
ENTITY = "mortgage_pool"

AS_OF = 1_767_225_600.0            # 2026-01-01T00:00:00Z
WINDOW_FROM = 1_577_836_800.0      # 2020-01-01T00:00:00Z
SEASONING_MONTHS = 24.0            # the ramp's time constant, in months

#: Where the two clocks come from here, and it is not an assumption this time.
#: A pool's prepayment for a month is TRUE at the end of that month
#: (`event_ts`) and is REPORTED by the servicer partway through the next one
#: (`ingest_ts`). The reporting lag is the ordinary reason a model fitted "as
#: of" a date must not see the month that had not been reported yet.
SERVICER_LAG_DAYS = 21.0


# ============================================================= the mathematics
def kernel_expression() -> str:
    """CPR as one closed form: an exponential ramp plus a cubic in incentive.

    Written out here rather than assembled from derived features so that the
    REGISTER holds the non-linearity. A kernel whose expression is
    `b0 + b1*x1 + b2*x2` over columns somebody else computed is a linear model
    on paper and a non-linear one in practice, and the curve — the part a
    supervisor asks about — lives in a pipeline nobody governs.
    """
    ramp = f"(1.0 - exp(-age_months / {SEASONING_MONTHS}))"
    return ("b0"
            f" + b_season * {ramp}"
            " + b_inc1 * rate_incentive"
            " + b_inc2 * rate_incentive * rate_incentive"
            " + b_inc3 * rate_incentive * rate_incentive * rate_incentive")


KERNEL = {
    "runtime": "formula",
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "deterministic": True,
    "entry": {"expression": kernel_expression(), "target": "cpr"},
    # X: two observables. The curve is in the expression, not in the columns.
    "input_schema": [
        {"name": "age_months", "dtype": "numeric", "symbol": "a",
         "unit": "months since origination"},
        {"name": "rate_incentive", "dtype": "numeric", "symbol": "i",
         "unit": "percentage points, WAC less market rate"},
    ],
    # P: five coefficients.
    "parameter_schema": [
        {"name": "b0", "dtype": "numeric", "symbol": r"\beta_{0}", "unit": "CPR %"},
        {"name": "b_season", "dtype": "numeric", "symbol": r"\beta_{s}",
         "unit": "CPR % at full seasoning"},
        {"name": "b_inc1", "dtype": "numeric", "symbol": r"\beta_{1}",
         "unit": "CPR % per point"},
        {"name": "b_inc2", "dtype": "numeric", "symbol": r"\beta_{2}",
         "unit": "CPR % per point squared"},
        {"name": "b_inc3", "dtype": "numeric", "symbol": r"\beta_{3}",
         "unit": "CPR % per point cubed"},
    ],
    "output_schema": [{"name": "cpr", "dtype": "numeric",
                       "unit": "annualised prepayment rate, per cent"}],
}


# ================================================================== the panel
#: The data-generating process, STATED. There is no freely redistributable
#: loan-level prepayment panel, so this case study builds one from coefficients
#: written down here — which means the fit can be checked against the truth,
#: something no real panel allows. It is synthetic and the README says so in
#: its first data paragraph.
TRUE = {"b0": 5.5, "b_season": 21.0, "b_inc1": 7.5, "b_inc2": 2.4,
        "b_inc3": -1.1}
NOISE_CPR = 1.6                    # SCALE of the observation noise, not its
#: standard deviation: the jitter is uniform on [-1, 1], so the noise has
#: standard deviation 1.6/sqrt(3) = 0.924. The fit reports 0.931, which is the
#: check — and the reason to write this down is that "the residual matches the
#: noise" is a sentence people nod at without doing the arithmetic.


def _jitter(key: str) -> float:
    """Deterministic pseudo-noise in roughly [-1, 1], from a digest.

    A seeded RNG would do, but a digest of the row's own identity is
    reproducible across Python versions and platforms without anybody having to
    remember which seed was used — and a case study whose numbers move between
    machines is one nobody can check against the README.
    """
    digest = hashlib.sha256(key.encode()).digest()
    scaled = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return 2.0 * scaled - 1.0


def true_cpr(age: float, incentive: float) -> float:
    ramp = 1.0 - math.exp(-age / SEASONING_MONTHS)
    return (TRUE["b0"] + TRUE["b_season"] * ramp
            + TRUE["b_inc1"] * incentive
            + TRUE["b_inc2"] * incentive ** 2
            + TRUE["b_inc3"] * incentive ** 3)


def panel() -> List[Dict[str, float]]:
    """Sixty pools observed monthly, each with its own incentive path."""
    rows: List[Dict[str, float]] = []
    for pool in range(60):
        # A pool's coupon relative to the market, drifting slowly.
        base = -1.2 + 0.06 * pool
        for month in range(1, 25):
            age = float(pool % 18 + month)
            incentive = round(base + 0.35 * math.sin(month / 3.0), 4)
            key = f"POOL-{pool:03d}-{month:02d}"
            observed = true_cpr(age, incentive) + NOISE_CPR * _jitter(key)
            event = WINDOW_FROM + month * 30.0 * DAY
            rows.append({
                "entity_id": f"POOL-{pool:03d}",
                "event_ts": event,
                "ingest_ts": event + SERVICER_LAG_DAYS * DAY,
                "age_months": age,
                "rate_incentive": incentive,
                "cpr": round(max(0.0, observed), 4),
            })
    return rows


# ============================================ the fit, in the bank's own engine
def fit_curve(rows: List[Dict[str, float]]) -> Dict[str, object]:
    """OLS on the non-linear basis. THE ENGINE'S JOB, not MAYA's.

    The design matrix is where the non-linearity lives: column one is the
    exponential seasoning ramp, columns two to four are powers of the incentive.
    The SOLVE is ordinary least squares, which is exactly why this shape is
    worth reaching for — the response is a curve and the estimate is still a
    coefficient vector with standard errors and a condition number.
    """
    import numpy as np

    y = np.asarray([r["cpr"] for r in rows], dtype=float)
    age = np.asarray([r["age_months"] for r in rows], dtype=float)
    inc = np.asarray([r["rate_incentive"] for r in rows], dtype=float)
    ramp = 1.0 - np.exp(-age / SEASONING_MONTHS)
    X = np.column_stack([np.ones(len(rows)), ramp, inc, inc ** 2, inc ** 3])
    names = ["b0", "b_season", "b_inc1", "b_inc2", "b_inc3"]

    beta, _, rank, singular = np.linalg.lstsq(X, y, rcond=None)
    residual = y - X @ beta
    n, k = X.shape
    ss_res = float(residual @ residual)
    r2 = 1.0 - ss_res / float(((y - y.mean()) ** 2).sum())
    sigma2 = ss_res / (n - k)
    # Standard errors, so a reviewer can see which coefficients are real. The
    # cubic term is the one that usually is not, and saying so is the point.
    covariance = sigma2 * np.linalg.inv(X.T @ X)
    errors = np.sqrt(np.diag(covariance))
    return {
        "values": {name: float(b) for name, b in zip(names, beta)},
        "standard_errors": {name: float(e) for name, e in zip(names, errors)},
        "t_statistics": {name: float(b / e) for name, b, e
                         in zip(names, beta, errors)},
        "diagnostics": {
            "observations": int(n), "parameters": int(k), "rank": int(rank),
            "r_squared": round(r2, 6),
            "residual_standard_error": round(math.sqrt(sigma2), 4),
            "condition_number": round(float(singular.max() / singular.min()), 2),
            "basis": "1, 1-exp(-age/24), i, i^2, i^3",
            "solver": "numpy.linalg.lstsq (QR)",
            "seasoning_months": SEASONING_MONTHS,
            "note": "non-linear in the inputs, linear in the parameters",
        },
    }


# ================================================================== the build
def main() -> int:
    args = parse("Case study 3 — a non-linear prepayment model")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 3 — exponential + polynomial, fitted by OLS (T2)")

    say.step("Build the panel")
    rows = panel()
    say.engine(f"{len(rows):,} pool-months across "
               f"{len({r['entity_id'] for r in rows})} pools")
    say.note("SYNTHETIC, from coefficients stated in this file — which is why "
             "the fit can be checked against the truth at the end. There is no "
             "freely redistributable loan-level prepayment panel")

    maya = connect(args)

    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------- features
    say.step("Register the features")
    for name, description in (
        ("age_months", "months since origination"),
        ("rate_incentive", "WAC less prevailing market rate, in points"),
        ("cpr", "annualised conditional prepayment rate, per cent"),
    ):
        attempt(name, lambda n=name, d=description: maya.features.define(
            name=n, entity=ENTITY, dtype="numeric", description=d,
            owner="person/a.mehta", source_system="servicer tape"))

    # Derived features: the two shapes, named and given lineage in the register
    # even though the kernel carries the whole curve. A reviewer asking "what is
    # seasoning here" gets an expression rather than a paragraph.
    say.did("two DERIVED features, so the shapes have names and lineage")
    attempt("seasoning (derived)", lambda: maya.features.derive(
        name="seasoning", dtype="numeric",
        expression=f"1.0 - exp(-age_months / {SEASONING_MONTHS})",
        description="exponential seasoning ramp, 0 at origination -> 1"))
    attempt("incentive_sq (derived)", lambda: maya.features.derive(
        name="incentive_sq", dtype="numeric",
        expression="rate_incentive * rate_incentive",
        description="squared refinancing incentive, the curvature term"))

    say.step("Load the panel — both clocks on every row")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=["age_months", "rate_incentive", "cpr"],
        description=(f"monthly servicer tape. event_ts is month end; "
                     f"ingest_ts is {SERVICER_LAG_DAYS:.0f} days later, when "
                     f"the servicer reported it — a real lag, not an "
                     f"assumption.")))
    load_once(maya, VIEW, rows)

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={"age_months": "numeric", "rate_incentive": "numeric",
               "cpr": "numeric"},
        label_slot="cpr", outcome_window_days=30,
        description="what the prepayment model reads, and its label"))
    fs_version = ensure_filled(maya, FEATURESET, {
        "age_months": "age_months", "rate_incentive": "rate_incentive",
        "cpr": "cpr"})

    # ---------------------------------------------------------------- model
    say.step("Register the model")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Mortgage prepayment (CPR) curve",
        model_class="alm.prepayment", domain="treasury",
        owner="person/j.okafor", legal_entity="LE-US-01",
        purpose="prepayment speeds for balance sheet projection, IRRBB and "
                "MSR valuation"))
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=4_500_000_000, purpose_class="valuation",
        feature_count=2, uses_alternative_data=False, interpretable=True),
            already="already tiered")
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    say.maya(f"trainability class {version_record.get('trainability_class')}")

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Seasoning ramp and cubic incentive response reviewed; the "
                  "form is non-linear in the inputs and linear in the "
                  "parameters, so the coefficients remain interpretable.")
    say.maya(f"risk tier {tier}")

    say.step("Put the model record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Prepayment curve, owned by treasury ALM.")

    say.step("Grant the standing entitlements")
    lab_grant = attempt("estimate, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (lab_grant or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("project, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="valuation", environment="prod"))

    # -------------------------------------------------- a refusal worth doing
    say.step("Show a control biting: L-W10, the featureset must cover the kernel")
    say.did("adding a regressor is a MODEL change, not a data change — so a "
            "featureset that does not carry what the kernel reads is refused")
    expect_refusal(
        "a training warrant against a featureset that lacks a regressor",
        lambda: maya.warrants.for_fitting(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            featureset="bs_calibration_set", featureset_version=1,
            window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF))

    # ---------------------------------------------------- the TRAINING warrant
    say.step("Ask MAYA for the TRAINING warrant")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF)
    fit_id = fit_warrant.get("warrant_id")
    say.maya(f"training warrant {fit_id}")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the training warrant")

    # --------------------------------------------------------- THE ENGINE FITS
    say.step("Fit the curve — HERE, in this process")
    say.note("numpy in this file. MAYA authorised it and will record it")
    fit = fit_curve(rows)
    values = fit["values"]
    diagnostics = fit["diagnostics"]
    say.engine(f"n={diagnostics['observations']:,}  "
               f"R²={diagnostics['r_squared']:.4f}  "
               f"residual SE {diagnostics['residual_standard_error']:.3f} CPR")
    print(f"        {'parameter':<12}{'estimate':>11}{'std err':>10}"
          f"{'t':>8}{'truth':>9}")
    for name, value in values.items():
        print(f"        {name:<12}{value:>11.4f}"
              f"{fit['standard_errors'][name]:>10.4f}"
              f"{fit['t_statistics'][name]:>8.1f}{TRUE[name]:>9.2f}")
    say.engine("the 'truth' column is only knowable because the panel is "
               "synthetic — it is the check a real panel cannot give you")

    # ------------------------------------------------ DELIVER to the register
    say.step("Deliver the coefficients to MAYA, under that warrant")
    recorded = attempt("the parameter set", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="cpr-curve-2026q1", kind="coefficients",
        values=values, provenance="fitted", warrant_id=grant_id,
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF,
        diagnostics={**diagnostics,
                     "fit_warrant_document": fit_id,
                     "standard_errors": fit["standard_errors"],
                     "t_statistics": fit["t_statistics"]},
        note="OLS on the seasoning/incentive basis; standard errors included "
             "so the cubic term can be judged rather than assumed"))
    parameter_set_id = (recorded or {}).get("id") or \
        (recorded or {}).get("parameter_set_id")

    say.step("A different person accepts it")
    if parameter_set_id:
        attempt("accepted by s.iqbal (model risk)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Seasoning and linear incentive terms are strongly "
                         "significant; the cubic is retained on economic "
                         "grounds with its t-statistic on the record."),
                already="already reviewed")

    # ------------------------------------------------------------ mathematics
    say.step("Ask MAYA for the mathematics it holds")
    maths = mathematics(maya, URN, SEMVER)
    say.maya("the curve, typeset from the expression the register stores")

    # -------------------------------------------------------- EXECUTION warrant
    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="valuation", environment="prod", verb="score")
        source = (run_warrant.get("parameters") or {}).get("source") or {}
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}, naming "
                 f"'{source.get('name')}'")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    # ------------------------------------------------------- run it, LOCALLY
    curve: List[Dict[str, float]] = []
    if run_warrant is not None:
        say.step("Project the curve — LOCALLY, under that warrant")
        coefficients = _coefficients(run_warrant, maya, values)
        print(f"        {'age':>5}{'incentive':>11}{'CPR %':>9}"
              f"{'truth':>9}")
        for age in (3.0, 12.0, 24.0, 60.0, 120.0):
            for incentive in (-0.5, 0.5, 1.5):
                got = _predict(maths, {"age_months": age,
                                       "rate_incentive": incentive},
                               coefficients)
                curve.append({"age": age, "incentive": incentive, "cpr": got,
                              "truth": true_cpr(age, incentive)})
        for line in curve:
            print(f"        {line['age']:>5.0f}{line['incentive']:>11.2f}"
                  f"{line['cpr']:>9.3f}{line['truth']:>9.3f}")
        worst = max(abs(c["cpr"] - c["truth"]) for c in curve)
        say.engine(f"{len(curve)} points projected locally; worst deviation "
                   f"from the generating curve {worst:.3f} CPR")

    # ---------------------------------------------------------- the document
    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, fit_warrant, run_warrant,
                          fit, curve, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. A curve fitted here, governed there. MAYA holds the")
    print("non-linear form itself — not a pointer to the pipeline that made it.")
    print(f"{'=' * 78}")
    return 0


def _existing_grant(maya: Maya, urn: str, environment: str) -> Optional[str]:
    for row in (maya.call("GET", "/warrants") or {}).get("warrants", []):
        if row.get("model_urn") == urn and row.get("environment") == environment:
            return row.get("id")
    return None


def _coefficients(warrant, maya: Maya,
                  fallback: Dict[str, float]) -> Dict[str, float]:
    ref = (warrant.get("parameters") or {}).get("source") or {}
    set_id = ref.get("parameter_set")
    if not set_id:
        return fallback
    return (maya.parameters.get(str(set_id)) or {}).get("values") or fallback


def _predict(maths, row: Dict[str, float],
             coefficients: Dict[str, float]) -> float:
    namespace: Dict[str, object] = {}
    exec(compile(str(maths.get("python") or ""),                  # noqa: S102
                 "<maya-derived>", "exec"), namespace)
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    supplied = {**row, **coefficients}
    return float(namespace["predict"](**{k: supplied[k] for k in wanted}))


def write_document(out, maths, version_record, fit_warrant, run_warrant, fit,
                   curve, tier):
    values, errors = fit["values"], fit["standard_errors"]
    tstats, diagnostics = fit["t_statistics"], fit["diagnostics"]
    estimate_rows = [[latex_escape(name), f"{values[name]:.4f}",
                      f"{errors[name]:.4f}", f"{tstats[name]:.1f}",
                      f"{TRUE[name]:.2f}"] for name in values]
    blocks = [
        r"\section{What this model is}",
        "The conditional prepayment rate of a mortgage pool, as a function of "
        "how far the pool has seasoned and how much incentive its borrowers "
        "have to refinance. Both responses are curves; the estimate is still a "
        "coefficient vector.",
        r"\textbf{Non-linear in the inputs, linear in the parameters.} That is "
        r"why ordinary least squares fits it and why every coefficient keeps an "
        r"interpretation --- the honest middle ground between a straight line "
        r"that cannot describe prepayment and a boosted machine that cannot be "
        r"explained to a supervisor.",

        r"\section{The equation, as the register holds it}",
        "Derived by MAYA from the expression it stores. The exponential ramp "
        "and the cubic are \\emph{inside} the registered model, not in a "
        "feature pipeline beside it --- so the curve a supervisor asks about is "
        "the curve the register can show them:",
        equation(str(maths.get("latex") or ""),
                 str(maths.get("expression") or "")),

        r"\section{The estimate}",
        "Fitted in the bank's own environment by QR least squares on the basis "
        rf"$\{{1,\; 1-e^{{-a/{SEASONING_MONTHS:.0f}}},\; i,\; i^2,\; i^3\}}$, "
        "under a training warrant MAYA issued.",
        table(estimate_rows,
              header=["Parameter", "Estimate", "Std. error", "$t$", "True"],
              spec="lrrrr"),
        r"The \emph{True} column exists only because this panel is synthetic, "
        r"generated from coefficients stated in the build script. It is the "
        r"check a real servicer tape cannot give you, and it is here so that "
        r"the case study can demonstrate the estimator recovering a known "
        r"answer rather than asserting that it does.",
        table([["Observations", f"{diagnostics['observations']:,}"],
               ["Parameters", str(diagnostics["parameters"])],
               ["$R^2$", f"{diagnostics['r_squared']:.4f}"],
               ["Residual standard error", f"{diagnostics['residual_standard_error']:.3f} CPR"],
               ["Condition number", f"{diagnostics['condition_number']:,.1f}"],
               ["Seasoning time constant", f"{SEASONING_MONTHS:.0f} months"]],
              header=["Diagnostic", "Value"], spec="lr"),

        r"\section{Governance}",
        table([["Model URN", version_record.get("urn", "—")],
               ["Version", version_record.get("semver", "—")],
               ["Trainability class", version_record.get("trainability_class", "—")],
               ["Risk tier", str(tier)],
               ["Training warrant", (fit_warrant or {}).get("warrant_id", "—")],
               ["Execution warrant", (run_warrant or {}).get("warrant_id", "not issued")]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "prepayment-specification.tex",
                    title="Mortgage Prepayment Curve --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
