#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 12 — A climate transition risk scorecard: parameters from a panel,
and a dissent that is part of the number (T7).

    transition_score = sum_k  w_k * factor_k        w elicited, not estimated

**Why the weights cannot be estimated.** A transition risk model asks how badly
a sector is exposed to a decarbonising economy. The obvious approach — regress
sector defaults on emissions intensity — fails for a reason no amount of data
fixes: *the transition has not happened yet*. There is no history of a 2035
carbon price, because there has not been one. Estimating from 2015–2025
defaults produces a model of the world that is ending.

So the weights come from a **panel**. Five experts, each scoring how much each
factor should count, in a structured elicitation. MAYA derives **T7 — Expert
judgment** from `elicited_weights` inhabited by `elicit`.

**What T7's fibre asks for, and why it is exactly right.** Not a fit statistic
— there is nothing fitted. It asks for *"panel composition, the questions
asked, and the dissent"*. Without those an elicitation is an assertion with a
decimal point on it. So this case study carries:

  * every expert's individual weights, not just the mean;
  * Kendall's W, the concordance across the panel;
  * **the dissent, verbatim**, from the expert who disagreed and why.

**The refusal.** Recording these weights as `provenance="fitted"` is refused.
`fitted` means estimated from data under a warrant MAYA issued, and claiming it
for a judgment launders an opinion into a measurement — after which nobody
looks for the panel, the questions or the dissent, because the row says the
numbers came from data.

**Who does what.** MAYA registers the model, the panel's output and the
dissent. The elicitation happened in a room; the arithmetic is in this file.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, equation, expect_refusal,
                             latex_escape, load_once, mathematics, parse,
                             put_record_in_force, save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/climate.transition.sector_scorecard"
SHORT = "climate.transition.sector_scorecard"
SEMVER = "1.0.0"
VIEW = "sector_transition_factors"
FEATURESET = "transition_scorecard_inputs"
ENTITY = "sector"

AS_OF = 1_767_225_600.0
WINDOW_FROM = 1_735_689_600.0      # 2025-01-01

# ------------------------------------------------------------- the factors
#: Each scored 0–100, where 100 is the worst transition exposure. The scale is
#: stated here because a panel that has not agreed the DIRECTION of a scale has
#: not agreed anything — half the disagreement in a badly-run elicitation is
#: two people scoring the same sector at opposite ends of the same axis.
FACTORS: List[Tuple[str, str]] = [
    ("emissions_intensity",
     "scope 1 and 2 emissions per unit of revenue, against the sector median"),
    ("capex_alignment",
     "share of planned capital expenditure consistent with a 1.5C pathway, "
     "inverted so that 100 is least aligned"),
    ("policy_exposure",
     "share of revenue earned in jurisdictions with a legislated carbon price "
     "or a phase-out date"),
    ("technology_substitutability",
     "how readily a low-carbon substitute exists at scale today, inverted so "
     "that 100 is least substitutable"),
    ("contract_duration",
     "weighted average remaining life of revenue contracts — long contracts "
     "lock in an exposure a repricing cannot reach"),
]

# --------------------------------------------------------------- the panel
#: THE PANEL. Named by discipline, because a panel of five credit officers is
#: one opinion held five times, and the composition is the first thing a
#: reviewer should be able to interrogate.
PANEL: List[Tuple[str, str, str]] = [
    ("E1", "climate scientist", "physical and transition pathway modelling"),
    ("E2", "energy economist", "carbon pricing and stranded asset valuation"),
    ("E3", "credit risk", "wholesale obligor rating and loss estimation"),
    ("E4", "sector analyst", "utilities, materials and transport coverage"),
    ("E5", "policy and regulatory affairs", "EU and UK climate legislation"),
]

#: What each expert said, per factor, as a weight out of 100. These are the raw
#: elicitation returns — the thing an elicitation usually throws away and keeps
#: only the mean of.
ELICITED: Dict[str, Dict[str, float]] = {
    #                      emis  capex  policy  tech  duration
    "E1": dict(zip([f for f, _ in FACTORS], [30.0, 25.0, 15.0, 25.0, 5.0])),
    "E2": dict(zip([f for f, _ in FACTORS], [20.0, 30.0, 30.0, 10.0, 10.0])),
    "E3": dict(zip([f for f, _ in FACTORS], [15.0, 20.0, 20.0, 15.0, 30.0])),
    "E4": dict(zip([f for f, _ in FACTORS], [25.0, 25.0, 20.0, 20.0, 10.0])),
    "E5": dict(zip([f for f, _ in FACTORS], [15.0, 20.0, 40.0, 15.0, 10.0])),
}

#: THE DISSENT, verbatim. E1 signed the elicitation and recorded a reservation.
#: A panel output that reports a mean and not this is a panel output that has
#: been rounded into agreement.
DISSENT = {
    "expert": "E1",
    "discipline": "climate scientist",
    "factor": "technology_substitutability",
    "position":
        "I weighted technology substitutability at 25 against a panel mean of "
        "17. The panel is anchoring on the cost of low-carbon substitutes "
        "TODAY. Every previous panel that did this — on solar, on batteries, "
        "on onshore wind — was wrong in the same direction, because learning "
        "curves are exponential and expert forecasts of them are linear. A "
        "sector I would call substitutable in eight years is being scored as "
        "locked in. I expect this weight to be revised upward at the first "
        "re-elicitation and I would rather the record showed I said so.",
    "effect_if_upheld":
        "raising technology_substitutability to 25 and renormalising moves "
        "the cement and steel scores up and the utilities score down",
}

#: The sectors scored. Factor values are illustrative and stated as such.
SECTORS: List[Tuple[str, str, List[float]]] = [
    ("SEC-OILGAS",   "Oil and gas extraction",        [95, 80, 70, 85, 60]),
    ("SEC-COALPOW",  "Coal-fired power generation",   [98, 90, 90, 70, 75]),
    ("SEC-CEMENT",   "Cement manufacturing",          [88, 70, 55, 90, 45]),
    ("SEC-STEEL",    "Primary steel",                 [85, 65, 60, 85, 50]),
    ("SEC-AIRLINE",  "Passenger aviation",            [75, 60, 45, 88, 35]),
    ("SEC-SHIPPING", "Deep-sea shipping",             [72, 55, 35, 80, 65]),
    ("SEC-AUTOMFG",  "Automotive manufacturing",      [55, 40, 65, 30, 30]),
    ("SEC-UTILREN",  "Renewable power generation",    [12, 10, 30, 15, 55]),
    ("SEC-SOFTWARE", "Enterprise software",           [ 5,  8, 10,  5, 20]),
]


# ============================================================ the arithmetic
def consensus() -> Dict[str, float]:
    """The panel mean, renormalised to sum to one. THE ENGINE'S JOB."""
    names = [f for f, _ in FACTORS]
    means = {f: sum(ELICITED[e][f] for e in ELICITED) / len(ELICITED)
             for f in names}
    total = sum(means.values())
    return {f: round(means[f] / total, 6) for f in names}


def spread() -> Dict[str, Dict[str, float]]:
    """Per factor: the lowest and highest weight any expert gave it.

    Reported because a mean of 17 built from {25, 10, 15, 20, 15} and a mean of
    17 built from {17, 17, 17, 17, 17} are the same number and not the same
    fact, and only one of them is a consensus.
    """
    out = {}
    for f, _ in FACTORS:
        values = [ELICITED[e][f] for e in ELICITED]
        out[f] = {"low": min(values), "high": max(values),
                  "range": round(max(values) - min(values), 4)}
    return out


def kendalls_w() -> Tuple[float, str]:
    """Kendall's W — how much the panel agreed on the ORDERING of the factors.

        W = 12 * S / (m^2 * (n^3 - n))

    where m raters rank n items, and S is the sum of squared deviations of each
    item's rank sum from the mean rank sum. W = 1 is unanimity on the order;
    W = 0 is no more agreement than chance.

    Ranks rather than weights, deliberately. Two experts who agree that policy
    matters most and duration least, but differ on the magnitudes, have agreed
    about the thing a scorecard is sensitive to.
    """
    names = [f for f, _ in FACTORS]
    m, n = len(ELICITED), len(names)
    rank_sums = {f: 0.0 for f in names}
    for expert in ELICITED:
        ordered = sorted(names, key=lambda f: ELICITED[expert][f])
        # Average ranks over ties, or a tie silently becomes an ordering.
        i = 0
        while i < len(ordered):
            j = i
            while (j + 1 < len(ordered)
                   and ELICITED[expert][ordered[j + 1]]
                   == ELICITED[expert][ordered[i]]):
                j += 1
            shared = sum(range(i + 1, j + 2)) / (j - i + 1)
            for k in range(i, j + 1):
                rank_sums[ordered[k]] += shared
            i = j + 1
    mean_rank_sum = m * (n + 1) / 2.0
    s = sum((rank_sums[f] - mean_rank_sum) ** 2 for f in names)
    w = 12.0 * s / (m ** 2 * (n ** 3 - n))
    reading = ("strong agreement on the ordering" if w >= 0.7 else
               "moderate agreement" if w >= 0.5 else
               "weak agreement — the mean is a compromise, not a consensus")
    return round(w, 4), reading


def score(weights: Dict[str, float], factors: List[float]) -> float:
    """The scorecard, run locally."""
    names = [f for f, _ in FACTORS]
    return sum(weights[n] * v for n, v in zip(names, factors))


# ============================================================== the kernel
KERNEL = {
    "runtime": "formula",
    "parameter_kind": "elicited_weights",
    "fit_procedure": "elicit",
    "deterministic": True,
    "entry": {
        "expression":
            "w_emissions * emissions_intensity + w_capex * capex_alignment + "
            "w_policy * policy_exposure + w_tech * technology_substitutability "
            "+ w_duration * contract_duration",
        "target": "transition_score"},
    "input_schema": [
        {"name": name, "dtype": "numeric", "unit": "0-100, 100 worst"}
        for name, _ in FACTORS
    ],
    "parameter_schema": [
        {"name": "w_emissions", "dtype": "numeric", "symbol": "w_1"},
        {"name": "w_capex", "dtype": "numeric", "symbol": "w_2"},
        {"name": "w_policy", "dtype": "numeric", "symbol": "w_3"},
        {"name": "w_tech", "dtype": "numeric", "symbol": "w_4"},
        {"name": "w_duration", "dtype": "numeric", "symbol": "w_5"},
    ],
    "output_schema": [{"name": "transition_score", "dtype": "numeric",
                       "unit": "0-100, 100 worst"}],
}

#: The kernel's parameter names and the factor names are deliberately not the
#: same strings: one is a weight and the other is what it weighs.
PARAM_OF = {"emissions_intensity": "w_emissions",
            "capex_alignment": "w_capex",
            "policy_exposure": "w_policy",
            "technology_substitutability": "w_tech",
            "contract_duration": "w_duration"}


def rows() -> List[Dict[str, object]]:
    """Both clocks. Sector factor data is published on a lag that varies by
    factor — emissions disclosures annually and late, policy the day it is
    legislated — so `ingest_ts` is not one offset from `event_ts`."""
    out = []
    for i, (sector_id, _name, values) in enumerate(SECTORS):
        measured = WINDOW_FROM + i * DAY
        out.append({
            "entity_id": sector_id,
            "event_ts": measured,
            # Disclosure lag: emissions data reaches the bank roughly nine
            # months after the year it describes.
            "ingest_ts": measured + 270 * DAY,
            **{name: float(v) for (name, _d), v in zip(FACTORS, values)},
        })
    return out


# ================================================================== the build
def main() -> int:
    args = parse("Case study 12 — an elicited climate transition scorecard")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 12 — Elicited weights, and a dissent on the record")

    # --------------------------------------------------- 0. the elicitation
    say.step("The panel, and what each expert actually said")
    print(f"        {'':<32}" + "".join(f"{e:>7}" for e in ELICITED)
          + f"{'mean':>8}{'range':>8}")
    weights, sp = consensus(), spread()
    for name, _description in FACTORS:
        row = "".join(f"{ELICITED[e][name]:>7.0f}" for e in ELICITED)
        print(f"        {name:<32}{row}"
              f"{100 * weights[name]:>8.1f}{sp[name]['range']:>8.0f}")
    w, reading = kendalls_w()
    say.engine(f"Kendall's W = {w:.3f} — {reading}")
    say.note(f"the widest disagreement is on "
             f"{max(sp, key=lambda f: sp[f]['range'])} "
             f"({sp[max(sp, key=lambda f: sp[f]['range'])]['range']:.0f} points "
             f"between the lowest and highest expert). A mean hides that, and "
             f"the mean is what usually gets recorded")

    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------ features
    say.step("Register the factors as features")
    for name, description in FACTORS:
        attempt(name, lambda n=name, d=description: maya.features.define(
            name=n, entity=ENTITY, dtype="numeric", description=d,
            owner="person/a.mehta",
            source_system="sector transition data, assembled from disclosures "
                          "and legislation trackers"))

    say.step("Load the sector factors — with a nine-month disclosure lag")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=[f for f, _ in FACTORS],
        description="sector transition factors. event_ts is the period the "
                    "figure describes; ingest_ts is when it was disclosed, "
                    "roughly nine months later. A score computed 'as of' a "
                    "date must not use a disclosure that had not been made."))
    load_once(maya, VIEW, rows())

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={f: "numeric" for f, _ in FACTORS},
        description="the five factors the transition scorecard weighs"))
    fs_version = ensure_filled(maya, FEATURESET,
                               {f: f for f, _ in FACTORS})

    # --------------------------------------------------------------- model
    say.step("Register the model")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Sector transition risk scorecard",
        model_class="climate.transition.scorecard", domain="climate_risk",
        owner="person/j.okafor", legal_entity="LE-UK-01",
        purpose="scoring wholesale sectors for transition risk, to inform "
                "concentration limits and pricing"))
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    say.maya(f"trainability class "
             f"{version_record.get('trainability_class')} — elicited_weights "
             f"inhabited by elicit. Nothing here was estimated from data, "
             f"because the transition has not happened yet")
    assessed = attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=8.5e8, purpose_class="risk_management",
        feature_count=len(FACTORS), uses_alternative_data=False,
        interpretable=True), already="already tiered")
    if assessed:
        say.maya(str(assessed.get("rationale") or assessed.get("tier")))

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="A weighted scorecard over five declared factors. The "
                  "review was of the elicitation protocol and the panel's "
                  "composition, because those are the model's evidence.")
    say.maya(f"risk tier {tier}")

    say.step("Put the record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Climate transition scorecard, owned by "
                             "wholesale credit risk.")

    say.step("Grant the standing entitlements")
    lab = attempt("elicit, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (lab or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("score, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="risk_management", environment="prod"))

    # ------------------------------------------------- the refusal that matters
    say.step("Try to record the panel's weights as FITTED")
    say.did("this is the tempting one. The numbers look like coefficients, the "
            "column accepts them, and the row reads the same on every screen "
            "downstream")
    values = {PARAM_OF[name]: weights[name] for name, _ in FACTORS}
    # Everything ELSE the register wants is supplied — the featureset, its
    # version, the window, the as-of — so that the refusal is the one being
    # demonstrated and not an easier one arriving first. A control that
    # refuses for the wrong reason demonstrates the wrong control.
    refusal = expect_refusal(
        "a judgment claiming to have come from data",
        lambda: maya.parameters.record(
            urn=URN, semver=SEMVER, name="panel-2026-q1-WRONG",
            kind="elicited_weights", values=values, provenance="fitted",
            warrant_id=grant_id, featureset=FEATURESET,
            featureset_version=fs_version,
            window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF))
    say.did("once a row says 'fitted', nobody goes looking for the panel, the "
            "questions or the dissent — because the record already told them "
            "the numbers came from data")
    if refusal is not None:
        save_json(out / "refusal-provenance.json",
                  {"code": refusal.code, "detail": refusal.detail,
                   "remediation": getattr(refusal, "remediation", None)},
                  what="the refusal, kept as evidence")

    # --------------------------------------------- deliver it honestly
    say.step("Record the weights as DECLARED, with the panel on them")
    recorded = attempt("the elicited weight set", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="panel-2026-q1", kind="elicited_weights",
        values=values, provenance="declared",
        # No warrant, and the word for that is "none" rather than the lab
        # grant. A warrant answers "which data produced these numbers", and
        # for a panel's judgment the answer is that no data did.
        warrant_id="none",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF,
        diagnostics={
            # What T7's fibre asks for, in the order it asks for it.
            "panel": [{"id": e, "discipline": d, "coverage": c}
                      for e, d, c in PANEL],
            "panel_size": len(PANEL),
            "elicitation_protocol":
                "Two rounds. Each expert allocated 100 points across the five "
                "factors independently; the anonymised distribution was shown; "
                "each expert then revised or confirmed. No consensus was "
                "required and none was reached.",
            "individual_returns": ELICITED,
            "weight_spread": sp,
            "kendalls_w": w,
            "kendalls_w_reading": reading,
            # THE DISSENT. Recorded because a panel output that reports a mean
            # and not this has been rounded into agreement.
            "dissent": DISSENT,
            "limitation":
                "These weights are a judgment, not an estimate. They cannot be "
                "back-tested against transition outcomes because the "
                "transition has not happened — which is why the model is T7 "
                "and not T2. The only outcome evidence available is the "
                "override rate: how often a credit officer disagrees with the "
                "score, and whether the disagreements run one way.",
            "re_elicitation_due": "2027-01-01, or on any legislated carbon "
                                  "price change in a covered jurisdiction",
        },
        note="panel mean over five experts, with the dissent recorded"))
    parameter_set_id = ((recorded or {}).get("id")
                        or (recorded or {}).get("parameter_set_id"))

    say.step("A different person accepts it — and reads the dissent")
    if parameter_set_id:
        attempt("accepted by s.iqbal (second line)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Accepted for concentration limits and pricing "
                         "guidance, NOT for individual obligor ratings. "
                         "E1's dissent on technology substitutability is "
                         "noted and is the reason the re-elicitation date is "
                         "twelve months rather than the usual three years."),
                already="already reviewed")
        say.did("the acceptance names what the set is accepted FOR, and cites "
                "the dissent as the reason for a shorter re-elicitation cycle. "
                "A dissent nobody acts on is a dissent that was recorded to "
                "be ignored")

    # ------------------------------------------------------- run it locally
    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="risk_management", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    maths = mathematics(maya, URN, SEMVER)
    scored: List[Tuple[str, str, float, float]] = []
    if run_warrant is not None:
        say.step("Score the sectors — LOCALLY, and under the dissent too")
        dissenting = _under_dissent()
        print(f"        {'sector':<32}{'score':>8}{'if E1 upheld':>14}"
              f"{'move':>7}")
        for sector_id, name, factors in SECTORS:
            base = _predict(maths, factors, values)
            alt = score(dissenting, factors)
            scored.append((sector_id, name, base, alt))
            print(f"        {name:<32}{base:>8.1f}{alt:>14.1f}"
                  f"{alt - base:>+7.1f}")
        say.did("the second column is the dissent, priced. E1's position is "
                "not a footnote — it is a number, and the record carries "
                "enough to compute it")

    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, weights, sp, w, reading,
                          refusal, run_warrant, scored, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. Five experts, one mean, and a dissent that is part of the")
    print("parameter set rather than a line in a minute nobody reads.")
    print(f"{'=' * 78}")
    return 0


def _under_dissent() -> Dict[str, float]:
    """The consensus, with E1's position on technology substitutability upheld
    and the rest renormalised. Computed rather than asserted, so the number in
    the output is the dissent's actual consequence."""
    raw = {name: 100 * consensus()[name] for name, _ in FACTORS}
    raw["technology_substitutability"] = ELICITED["E1"][
        "technology_substitutability"]
    total = sum(raw.values())
    return {name: raw[name] / total for name, _ in FACTORS}


def _existing_grant(maya: Maya, urn: str, environment: str) -> Optional[str]:
    for row in (maya.call("GET", "/warrants") or {}).get("warrants", []):
        if row.get("model_urn") == urn and row.get("environment") == environment:
            return row.get("id")
    return None


def _predict(maths, factors: List[float], coefficients) -> float:
    namespace: Dict[str, object] = {}
    exec(compile(str(maths.get("python") or ""),                  # noqa: S102
                 "<maya-derived>", "exec"), namespace)
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    supplied = {name: float(v) for (name, _d), v in zip(FACTORS, factors)}
    supplied.update(coefficients)
    return float(namespace["predict"](**{k: supplied[k] for k in wanted}))


def write_document(out, maths, version_record, weights, sp, w, reading,
                   refusal, run_warrant, scored, tier):
    blocks = [
        r"\section{Why these parameters cannot be estimated}",
        r"A transition risk model asks how badly a sector is exposed to a "
        r"decarbonising economy. The obvious approach --- regress sector "
        r"defaults on emissions intensity --- fails for a reason no quantity of "
        r"data repairs: \textbf{the transition has not happened yet}. There is "
        r"no history of a 2035 carbon price because there has not been one, and "
        r"estimating from the last decade's defaults produces a careful model "
        r"of the world that is ending.",
        r"So the weights are \emph{elicited} from a panel. MAYA derives "
        r"\textbf{T7 --- Expert judgment} from `elicited\_weights` inhabited by "
        r"`elicit`, and asks for what a judgment actually owes: panel "
        r"composition, the questions asked, and the dissent.",
        equation(str(maths.get("latex") or ""),
                 str(maths.get("expression") or "")),

        r"\section{The panel, and what it did not agree about}",
        table([[latex_escape(name.replace("_", " ")),
                f"{100 * weights[name]:.1f}\\%",
                f"{sp[name]['low']:.0f}--{sp[name]['high']:.0f}",
                f"{sp[name]['range']:.0f}"]
               for name, _d in FACTORS],
              header=["Factor", "Panel mean", "Range", "Spread"], spec="lrrr"),
        rf"Kendall's $W = {w:.3f}$ --- {latex_escape(reading)}. $W$ measures "
        rf"agreement on the \emph{{ordering}} of the factors rather than on "
        rf"their magnitudes, which is the right question for a scorecard: two "
        rf"experts who agree that policy matters most and duration least have "
        rf"agreed about what the score is sensitive to.",
        r"The spread column is reported because a mean of 17 built from "
        r"$\{25, 10, 15, 20, 15\}$ and a mean of 17 built from "
        r"$\{17,17,17,17,17\}$ are the same number and not the same fact --- "
        r"and only one of them is a consensus.",

        r"\section{The dissent}",
        r"E1, the panel's climate scientist, signed the elicitation and "
        r"recorded a reservation, which is carried on the parameter set "
        r"verbatim rather than summarised:",
        r"\begin{quote}\small " + latex_escape(DISSENT["position"]) +
        r"\end{quote}",
        r"The second-line acceptance cites it, and shortens the re-elicitation "
        r"cycle from three years to twelve months because of it. \textbf{A "
        r"dissent nobody acts on is a dissent that was recorded in order to be "
        r"ignored.} The specification prices it: the table below scores every "
        r"sector twice, once under the panel mean and once with E1's weight "
        r"upheld and the rest renormalised.",

        r"\section{The sectors, scored twice}",
        table([[latex_escape(name), f"{base:.1f}", f"{alt:.1f}",
                f"{alt - base:+.1f}"]
               for _sid, name, base, alt in scored],
              header=["Sector", "Panel mean", "Dissent upheld", "Move"],
              spec="lrrr"),

        r"\section{What the platform refused}",
        r"Recording these weights with `provenance = fitted` is refused:",
        r"\begin{quote}\small \texttt{[" +
        latex_escape(str(getattr(refusal, "code", "not_obtained_from_data"))) +
        r"]} " +
        latex_escape(str(getattr(refusal, "detail", ""))) + r"\end{quote}",
        r"`fitted` is the strongest claim the register offers --- estimated "
        r"from data, under a warrant MAYA issued --- and claiming it for a "
        r"judgment launders an opinion into a measurement. After which nobody "
        r"looks for the panel, the questions or the dissent, because the row "
        r"already said the numbers came from data. The honest word is "
        r"`declared`, and it costs nothing except the pretence.",

        r"\section{What can and cannot be monitored}",
        r"There is no back-test. Transition outcomes are not observable yet, "
        r"which is the same fact that made the weights elicited in the first "
        r"place. What \emph{is} observable is the \textbf{override rate}: how "
        r"often a credit officer departs from the score, and --- the question "
        r"that matters --- whether the departures run in one direction. A "
        r"scorecard overridden downward four times in five is not being used; "
        r"it is being worked around, and that is measurable long before any "
        r"outcome arrives.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(URN)],
               ["Version", latex_escape(str(version_record.get("semver", "—")))],
               ["Trainability class",
                latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["Panel size", str(len(PANEL))],
               ["Kendall's $W$", f"{w:.3f}"],
               ["Dissents recorded", "1"],
               ["Re-elicitation due", "2027-01-01, or on a legislated carbon "
                                      "price change"],
               ["Execution warrant",
                latex_escape(str((run_warrant or {}).get("warrant_id",
                                                         "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "transition-scorecard-specification.tex",
                    title="Sector Transition Risk Scorecard --- Model "
                          "Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
