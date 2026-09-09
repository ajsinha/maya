#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 10 — An SEIR epidemic model: a mechanistic model calibrated to an
outbreak, and a reporting delay that decides the answer (T1).

    dS/dt = -beta*S*I/N          S  susceptible
    dE/dt =  beta*S*I/N - a*E    E  exposed, not yet infectious
    dI/dt =  a*E - gamma*I       I  infectious
    dR/dt =  gamma*I             R  removed

    R0 = beta / gamma            the number one case infects in a naive
                                 population — the number that decides whether
                                 an outbreak grows or dies

**Why this is a governance case study and not an epidemiology one.** In 2020
this class of model set curfews, closed schools and allocated ventilators, and
the single most consequential technical fact about it was almost never on the
face of the output: **cases are reported days after they occur**, so a model
calibrated on "today's" data is calibrated on a week that is still filling in.

That is a bitemporal problem. It is exactly the problem MAYA's two clocks
exist for, and it is the same problem as a servicer's reporting lag in case
study 3 — with a public-health decision on the other end instead of a
prepayment forecast.

**T1, and why it matters here.** The structure comes from theory: the
compartments and the flows between them are not estimated, they are asserted by
the model's form. What is calibrated is `beta` and `gamma` — matched to
observed case counts. That is `calibration_set` inhabited by `calibrate`, and
MAYA derives T1.

**Who does what.** MAYA registers. The ODE integration and the calibration are
arithmetic in this file — a public health agency's own modelling code.
"""
from __future__ import annotations

import math
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, equation, latex_escape, load_once, mathematics, parse,
                             put_record_in_force, save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/publichealth.epidemic.seir"
SHORT = "publichealth.epidemic.seir"
SEMVER = "1.0.0"
VIEW = "outbreak_daily_counts"
FEATURESET = "seir_calibration_set"
ENTITY = "region_day"

AS_OF = 1_767_225_600.0            # the day the advice is given
WINDOW_FROM = 1_764_547_200.0      # 2025-12-01
DAY_ZERO = AS_OF - 60 * DAY

POPULATION = 1_000_000.0
LATENT_DAYS = 3.0                  # 1/a — incubation before infectiousness
INFECTIOUS_DAYS = 5.0              # 1/gamma
GAMMA = 1.0 / INFECTIOUS_DAYS
ALPHA = 1.0 / LATENT_DAYS

#: The truth used to generate the outbreak, so the calibration can be checked.
TRUE_R0 = 2.40
TRUE_BETA = TRUE_R0 * GAMMA

#: THE REPORTING DELAY. A case that occurs on day t is reported on day t+5, and
#: the most recent days are only PARTIALLY reported. This is the whole point of
#: the case study and it is a real property of every notifiable-disease system.
REPORT_DELAY_DAYS = 5
REPORTED_FRACTION = [0.10, 0.35, 0.62, 0.83, 0.95, 1.00]   # by age of the case


# ============================================================= the mechanism
def integrate(beta: float, days: int, seed: float = 20.0,
              step: float = 0.25) -> List[float]:
    """Forward Euler on the SEIR system. Returns daily NEW infections.

    Euler at a quarter-day rather than anything cleverer, because the point of
    this case study is the clock rather than the integrator, and a scheme
    somebody has to trust is worse for a demonstration than one they can read.
    """
    s, e, i, _r = POPULATION - seed, seed, 0.0, 0.0
    incidence, carry = [], 0.0
    for _day in range(days):
        new_today = 0.0
        for _ in range(int(1 / step)):
            infections = beta * s * i / POPULATION * step
            progression = ALPHA * e * step
            recovery = GAMMA * i * step
            s -= infections
            e += infections - progression
            i += progression - recovery
            new_today += progression          # E -> I is a "case"
        carry += new_today
        incidence.append(carry - sum(incidence))
    return incidence


def as_reported(incidence: List[float], today: int) -> List[Tuple[int, float]]:
    """What the surveillance system SHOWS on `today`, not what happened.

    A case occurring on day t is reported over the following days, and the most
    recent days are visibly incomplete. Anybody calibrating on this without
    accounting for it is calibrating on an epidemic that appears to be slowing.
    """
    shown = []
    for t, cases in enumerate(incidence[:today + 1]):
        age = today - t
        fraction = (REPORTED_FRACTION[age] if age < len(REPORTED_FRACTION)
                    else 1.0)
        shown.append((t, cases * fraction))
    return shown


# ============================================================ the calibration
def calibrate_r0(observed: List[Tuple[int, float]], *,
                 drop_recent: int) -> Tuple[float, Dict[str, object]]:
    """R0 from the exponential growth rate of the early curve. THE ENGINE'S JOB.

    In the exponential phase, incidence grows as exp(r*t), and for an SEIR
    system the Euler-Lotka relation gives

        R0 = (1 + r/alpha) * (1 + r/gamma)

    which is exact for exponentially distributed latent and infectious periods.
    `drop_recent` is the knob this whole case study is about: how many of the
    most recent, still-filling-in days to exclude.
    """
    usable = observed[:len(observed) - drop_recent] if drop_recent else observed
    points = [(t, c) for t, c in usable if c > 0][2:]      # skip the seed
    if len(points) < 5:
        raise SystemExit("not enough of the curve to fit a growth rate")
    n = len(points)
    xs = [float(t) for t, _c in points]
    ys = [math.log(c) for _t, c in points]
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    var = sum((x - mx) ** 2 for x in xs)
    r = cov / var
    fitted = [my + r * (x - mx) for x in xs]
    ss_res = sum((y - f) ** 2 for y, f in zip(ys, fitted))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r0 = (1.0 + r / ALPHA) * (1.0 + r / GAMMA)
    return r0, {"growth_rate_per_day": round(r, 6),
                "days_used": n, "days_dropped": drop_recent,
                "r_squared_on_log_incidence": round(1 - ss_res / ss_tot, 6),
                "relation": "R0 = (1 + r/alpha)(1 + r/gamma), Euler-Lotka for "
                            "exponentially distributed latent and infectious "
                            "periods",
                "latent_days": LATENT_DAYS, "infectious_days": INFECTIOUS_DAYS}


# ============================================================== the kernel
#: The next-generation number, as one expression the register holds. The ODE
#: system is the model's STRUCTURE and is not expressible here; what is
#: expressible — and what the decision actually turns on — is the relation
#: between the calibrated rates and the number people act on.
KERNEL = {
    "runtime": "formula",
    "parameter_kind": "calibration_set",
    "fit_procedure": "calibrate",
    "deterministic": True,
    "entry": {"expression": "beta / gamma * susceptible_fraction",
              "target": "r_effective"},
    "input_schema": [
        {"name": "susceptible_fraction", "dtype": "numeric",
         "symbol": "s", "unit": "fraction of the population still susceptible"},
    ],
    "parameter_schema": [
        {"name": "beta", "dtype": "numeric", "symbol": r"\beta",
         "unit": "effective contacts per infectious person per day"},
        {"name": "gamma", "dtype": "numeric", "symbol": r"\gamma",
         "unit": "recovery rate per day"},
    ],
    "output_schema": [{"name": "r_effective", "dtype": "numeric",
                       "unit": "expected secondary cases"}],
}


def rows(observed: List[Tuple[int, float]]) -> List[Dict[str, object]]:
    """One row per day, with BOTH clocks and the reporting delay in the gap."""
    out = []
    for t, cases in observed:
        occurred = DAY_ZERO + t * DAY
        out.append({
            "entity_id": f"REGION-A-D{t:03d}",
            "event_ts": occurred,
            # The case was REPORTED five days after it occurred. This single
            # line is what makes the point-in-time read possible at all.
            "ingest_ts": occurred + REPORT_DELAY_DAYS * DAY,
            "new_cases": round(cases, 3),
            "susceptible_fraction": 1.0,
        })
    return out


# ================================================================== the build
def main() -> int:
    args = parse("Case study 10 — an SEIR epidemic model")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 10 — SEIR: a mechanistic model, and a reporting delay")

    # ------------------------------------------------- 0. the two answers
    say.step("Generate the outbreak, and see it as the surveillance system does")
    today = 30
    truth = integrate(TRUE_BETA, days=today + 1)
    observed = as_reported(truth, today)
    say.engine(f"true R0 = {TRUE_R0:.2f}; {today + 1} days simulated")
    print(f"        {'day':>5}{'occurred':>11}{'reported':>11}   as seen today")
    for t in range(today - 6, today + 1):
        pct = 100.0 * observed[t][1] / truth[t] if truth[t] else 0.0
        print(f"        {t:>5}{truth[t]:>11.1f}{observed[t][1]:>11.1f}   "
              f"{pct:>5.0f}% reported")
    say.note("the last five days look like a slowdown and are not one. They "
             "are the reporting delay, and this is the single most "
             "consequential fact about the output")

    # --------------------------------- the calibration, done twice on purpose
    say.step("Calibrate R0 — twice, and the difference is the case study")
    naive, _naive_diag = calibrate_r0(observed, drop_recent=0)
    correct, correct_diag = calibrate_r0(observed,
                                         drop_recent=REPORT_DELAY_DAYS)
    say.engine(f"using ALL days:              R0 = {naive:.3f}   "
               f"(truth {TRUE_R0:.2f}, error {100 * (naive / TRUE_R0 - 1):+.1f}%)")
    say.engine(f"dropping the last {REPORT_DELAY_DAYS} days:    R0 = "
               f"{correct:.3f}   "
               f"(truth {TRUE_R0:.2f}, error {100 * (correct / TRUE_R0 - 1):+.1f}%)")
    say.note("both are defensible-looking numbers from the same data on the "
             "same day. One of them closes schools and one does not")

    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------ features
    say.step("Register the features")
    for name, description in (
        ("new_cases", "newly reported cases on this day for this region"),
        ("susceptible_fraction", "fraction of the population still susceptible"),
    ):
        attempt(name, lambda n=name, d=description: maya.features.define(
            name=n, entity=ENTITY, dtype="numeric", description=d,
            owner="person/a.mehta", source_system="notifiable disease "
                                                  "surveillance"))

    say.step("Load the curve — the reporting delay IS the second clock")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=["new_cases", "susceptible_fraction"],
        description=(f"daily counts. event_ts is when the case OCCURRED; "
                     f"ingest_ts is {REPORT_DELAY_DAYS} days later, when it "
                     f"was reported. A model calibrated as of a date must see "
                     f"only what had been reported by then.")))
    load_once(maya, VIEW, rows(observed))
    say.did("with both clocks recorded, 'what did we know on the day we gave "
            "the advice' is a query rather than an argument")

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={"new_cases": "numeric", "susceptible_fraction": "numeric"},
        description="the daily curve an SEIR calibration reads"))
    fs_version = ensure_filled(maya, FEATURESET, {
        "new_cases": "new_cases",
        "susceptible_fraction": "susceptible_fraction"})

    # --------------------------------------------------------------- model
    say.step("Register the model")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="SEIR epidemic transmission model",
        model_class="publichealth.transmission", domain="public_health",
        owner="person/j.okafor", legal_entity="LE-UK-01",
        purpose="estimating the effective reproduction number to inform "
                "non-pharmaceutical intervention advice"))
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=0, purpose_class="policy_decision",
        feature_count=2, uses_alternative_data=False, interpretable=True),
            already="already tiered")
    say.maya(f"trainability class {version_record.get('trainability_class')} "
             f"— the STRUCTURE comes from theory; beta and gamma are "
             f"calibrated")

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="SEIR with exponentially distributed latent and infectious "
                  "periods. The reporting-delay treatment was the substance of "
                  "the review.")
    say.maya(f"risk tier {tier}")

    say.step("Put the record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Transmission model, owned by the modelling cell.")

    say.step("Grant the standing entitlements")
    lab_grant = attempt("calibrate, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (lab_grant or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("advise, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="policy_decision", environment="prod"))

    # ------------------------------------------------- the training warrant
    say.step("Ask MAYA for the CALIBRATION warrant")
    say.did("the window bounds BOTH clocks — which is what makes 'as of the "
            "day we advised' reproducible a year later, in a public inquiry")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF)
    fit_id = fit_warrant.get("warrant_id")
    say.maya(f"calibration warrant {fit_id}")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the calibration warrant")

    # ---------------------------------------------------- deliver, honestly
    say.step("Deliver the calibrated rates — the CORRECTED one")
    beta = correct * GAMMA
    values = {"beta": round(beta, 8), "gamma": round(GAMMA, 8)}
    say.engine(f"beta = {values['beta']:.4f}, gamma = {values['gamma']:.4f}, "
               f"R0 = beta/gamma = {correct:.3f}")
    recorded = attempt("the parameter set", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="region-a-wave-1", kind="calibration_set",
        values=values, provenance="calibrated", warrant_id=grant_id,
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF,
        diagnostics={
            **correct_diag,
            "r0": round(correct, 4),
            "fit_warrant_document": fit_id,
            # The number that would have been produced by the obvious mistake,
            # ON THE RECORD, so a reviewer can see the size of the effect
            # rather than being told it matters.
            "r0_if_recent_days_not_dropped": round(naive, 4),
            "reporting_delay_days": REPORT_DELAY_DAYS,
            "limitation":
                "The most recent days are incompletely reported and are "
                "excluded. Including them biases R0 DOWNWARD — here to "
                f"{naive:.2f} against {correct:.2f} — because a partially "
                "reported week looks like a slowing epidemic. This is a "
                "property of the surveillance system, not of the disease.",
            "not_modelled": "age structure, spatial heterogeneity, "
                            "superspreading, and any intervention effect",
        },
        note="R0 calibrated on the completely-reported window only"))
    parameter_set_id = (recorded or {}).get("id") or \
        (recorded or {}).get("parameter_set_id")

    say.step("A different person accepts it")
    if parameter_set_id:
        attempt("accepted by s.iqbal (second line)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Accepted. The excluded-days treatment is documented "
                         "and the counterfactual R0 is on the record, which is "
                         "what makes the choice reviewable rather than "
                         "invisible."),
                already="already reviewed")

    # ------------------------------------------------------- run it locally
    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="policy_decision", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    maths = mathematics(maya, URN, SEMVER)
    projection: List[Dict[str, float]] = []
    if run_warrant is not None:
        say.step("Project R_effective as immunity accumulates — LOCALLY")
        coefficients = _coefficients(run_warrant, maya, values)
        print(f"        {'susceptible':>12}{'R_eff':>9}   interpretation")
        for s_frac in (1.00, 0.80, 0.60, 1.0 / correct, 0.30):
            r_eff = _predict(maths, s_frac, coefficients)
            note = ("epidemic grows" if r_eff > 1.02 else
                    "HERD IMMUNITY THRESHOLD" if abs(r_eff - 1.0) <= 0.02 else
                    "epidemic shrinks")
            projection.append({"susceptible": s_frac, "r_eff": r_eff})
            print(f"        {s_frac:>12.3f}{r_eff:>9.3f}   {note}")
        say.engine(f"the herd immunity threshold is 1 - 1/R0 = "
                   f"{1 - 1 / correct:.1%} of the population")

    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, fit_warrant, run_warrant,
                          correct, naive, correct_diag, projection, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. Two defensible R0s from the same data on the same day, and")
    print("the register records which one was used and what the other was.")
    print(f"{'=' * 78}")
    return 0


def _existing_grant(maya: Maya, urn: str, environment: str) -> Optional[str]:
    for row in (maya.call("GET", "/warrants") or {}).get("warrants", []):
        if row.get("model_urn") == urn and row.get("environment") == environment:
            return row.get("id")
    return None


def _coefficients(warrant, maya: Maya, fallback):
    ref = (warrant.get("parameters") or {}).get("source") or {}
    set_id = ref.get("parameter_set")
    if not set_id:
        return fallback
    return (maya.parameters.get(str(set_id)) or {}).get("values") or fallback


def _predict(maths, susceptible_fraction: float, coefficients) -> float:
    namespace: Dict[str, object] = {}
    exec(compile(str(maths.get("python") or ""),                  # noqa: S102
                 "<maya-derived>", "exec"), namespace)
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    supplied = {"susceptible_fraction": susceptible_fraction, **coefficients}
    return float(namespace["predict"](**{k: supplied[k] for k in wanted}))


def write_document(out, maths, version_record, fit_warrant, run_warrant,
                   r0, naive_r0, diag, projection, tier):
    blocks = [
        r"\section{What this model is}",
        r"A four-compartment SEIR transmission model. Susceptible individuals "
        r"become Exposed at a rate proportional to contact with the Infectious; "
        r"the Exposed become infectious after a latent period; the Infectious "
        r"are Removed after an infectious period.",
        r"\begin{equation}"
        r"\frac{dS}{dt}=-\beta\frac{SI}{N},\quad"
        r"\frac{dE}{dt}=\beta\frac{SI}{N}-\alpha E,\quad"
        r"\frac{dI}{dt}=\alpha E-\gamma I,\quad"
        r"\frac{dR}{dt}=\gamma I"
        r"\end{equation}",
        r"MAYA classifies it \textbf{T1}. The \emph{structure} --- which "
        r"compartments exist and how they connect --- comes from theory and is "
        r"not estimated. What is calibrated is $\beta$ and $\gamma$, matched to "
        r"an observed curve, which is `calibration\_set` inhabited by "
        r"`calibrate`.",

        r"\section{The quantity people act on}",
        equation(str(maths.get("latex") or ""),
                 str(maths.get("expression") or "")),
        r"$R_0=\beta/\gamma$ is the number of secondary cases one case produces "
        r"in a fully susceptible population; $R_{\text{eff}}$ multiplies it by "
        r"the susceptible fraction. Above one the epidemic grows and below one "
        r"it shrinks, which is why a difference in the second decimal place is "
        r"a policy difference.",

        r"\section{The reporting delay, which decides the answer}",
        "A case occurring on day $t$ is reported over the following days, and "
        "the most recent days are visibly incomplete. Calibrating on all "
        "available data therefore fits a curve whose right-hand end is bending "
        "downward for an administrative reason:",
        table([["Calibrated on all days", f"{naive_r0:.3f}",
                f"{100 * (naive_r0 / TRUE_R0 - 1):+.1f}\\% against the truth"],
               ["Dropping the incomplete days", f"{r0:.3f}",
                f"{100 * (r0 / TRUE_R0 - 1):+.1f}\\% against the truth"]],
              header=["Treatment", "$R_0$", "Error"], spec="lrr"),
        r"\textbf{Both are defensible-looking numbers from the same data on the "
        r"same day.} One of them closes schools and one does not. The "
        r"counterfactual is recorded as a diagnostic on the parameter set, so "
        r"the choice is reviewable rather than invisible --- which is the "
        r"difference between a modelling decision and a modelling accident.",
        r"This is a \emph{bitemporal} problem: `event\_ts` is when the case "
        r"occurred and `ingest\_ts` is when it was reported, and with both "
        r"recorded, \emph{what did we know on the day we gave the advice} is a "
        r"query rather than an argument in a public inquiry two years later.",

        r"\section{The projection}",
        table([[f"{p['susceptible']:.3f}", f"{p['r_eff']:.3f}"]
               for p in projection],
              header=["Susceptible fraction", "$R_{\\text{eff}}$"], spec="rr"),
        # NOTE: never format a percentage into LaTeX with `:.1%` — the emitted
        # `%` is a comment character and silently eats the rest of the line.
        rf"The herd immunity threshold --- the susceptible fraction that must "
        rf"be removed before $R_{{\text{{eff}}}}$ falls below one --- is "
        rf"$1-1/R_0 = {100 * (1 - 1 / r0):.1f}\%$ of the population.",

        r"\section{What is not modelled}",
        r"Named, because a compartmental model's omissions are the reason its "
        r"projections and its reality diverge: age structure, spatial "
        r"heterogeneity, superspreading (the model assumes homogeneous mixing, "
        r"and real transmission is heavily overdispersed), and any intervention "
        r"effect. Latent and infectious periods are exponentially distributed, "
        r"which is analytically convenient and biologically wrong.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(str(version_record.get("urn", "—")))],
               ["Version", latex_escape(str(version_record.get("semver", "—")))],
               ["Trainability class",
                latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["$R^2$ on log incidence",
                f"{diag['r_squared_on_log_incidence']:.4f}"],
               ["Days used / dropped",
                f"{diag['days_used']} / {diag['days_dropped']}"],
               ["Calibration warrant",
                latex_escape(str((fit_warrant or {}).get("warrant_id", "—")))],
               ["Execution warrant",
                latex_escape(str((run_warrant or {}).get("warrant_id", "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "seir-specification.tex",
                    title="SEIR Transmission Model --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
