#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 2 — Multiple linear regression on PUBLIC home-sale data (T2).

    Ames, Iowa: 2,930 residential sales, 82 columns, published by Dean De Cock
    in the Journal of Statistics Education. Sale price on five regressors,
    estimated by ordinary least squares.

**Who does what.** MAYA registers; this script computes. The regression below is
`numpy.linalg.lstsq` in this file — the bank's own modelling environment. MAYA
issues the training warrant, records the coefficients somebody else must
approve, issues the execution warrant, and never sees a design matrix.

**Why this case study exists.** The Black-Scholes one is a model with no
training data. This is the ordinary case: real data, from a real source, with a
real provenance problem. The interesting part is not the regression — it is
that the source carries **one clock** and MAYA requires **two**, so somebody has
to say where the second came from and own that assumption. That question is
usually answered by nobody, and its absence is invisible until a model is
re-fitted on data that had not been recorded when the decision was taken.
"""
from __future__ import annotations

import math
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version,
                             attempt, connect, document, ensure_cast,
                             ensure_filled, ensure_version, equation,
                             expect_refusal, latex_escape, load_once,
                             mathematics, parse, put_record_in_force,
                             save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/retail.collateral.home_value"
SHORT = "retail.collateral.home_value"
SEMVER = "1.0.0"
VIEW = "ames_home_sales"
FEATURESET = "home_value_inputs"
ENTITY = "property"

#: The authoritative source. De Cock's own file, from the paper that published
#: the data — not a mirror, not a repackaged copy on somebody's profile. A
#: governance demo that cites a convenient copy teaches the habit it should be
#: correcting.
SOURCE = "http://jse.amstat.org/v19n3/decock/AmesHousing.txt"
DOCUMENTATION = "http://jse.amstat.org/v19n3/decock/DataDocumentation.txt"
CACHE = HERE / "data" / "AmesHousing.txt"

#: What the model reads, mapped from the source's column names.
REGRESSORS = (
    ("gr_liv_area", "Gr Liv Area", "above-grade living area, square feet",
     r"A_{\mathrm{liv}}"),
    ("overall_qual", "Overall Qual", "overall material and finish, 1-10",
     r"Q"),
    ("year_built", "Year Built", "year of original construction", r"Y"),
    ("total_bsmt_sf", "Total Bsmt SF", "total basement area, square feet",
     r"A_{\mathrm{bsmt}}"),
    ("garage_cars", "Garage Cars", "garage capacity in cars", r"G"),
)
TARGET = ("sale_price", "SalePrice", "sale price in USD")

#: The recording lag. THE ASSUMPTION IN THIS CASE STUDY, stated here rather
#: than buried: the source gives the month and year of sale and says nothing
#: about when the assessor's office recorded it. Forty-five days is a plausible
#: county recording lag and it is an ASSUMPTION, not a fact from the data. It is
#: in the feature view's description, in the LaTeX document and in the README,
#: because a bitemporal claim resting on an invented clock is worse than no
#: bitemporal claim at all.
RECORDING_LAG_DAYS = 45.0

AS_OF = 1_767_225_600.0            # 2026-01-01T00:00:00Z, the fitting date
#: The lower bound of the training window. A real date rather than `0.0`: the
#: epoch is falsy, and a falsy bound reads as NO bound to anything that checks
#: whether one was given — which is precisely the L-W9 failure this window
#: exists to satisfy. The Ames sample runs 2006-2010.
WINDOW_FROM = 946_684_800.0        # 2000-01-01T00:00:00Z


# =========================================================== the source data
def fetch(offline: bool) -> Tuple[List[Dict[str, float]], str]:
    """The Ames data, cached beside this script after the first download."""
    if CACHE.is_file():
        return parse_ames(CACHE.read_text(encoding="utf8", errors="replace")), \
            f"cached copy of {SOURCE}"
    if offline:
        raise SystemExit(
            f"--offline was given and {CACHE} does not exist.\n"
            f"Run once without --offline, or download {SOURCE} to that path.")
    try:
        request = urllib.request.Request(
            SOURCE, headers={"User-Agent": "maya-case-study"})
        # S310: the URL is the module constant above, not caller input.
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            raw = response.read().decode("utf8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(
            f"could not fetch {SOURCE}: {exc}\n"
            f"Download it by hand to {CACHE} and re-run, or pass --offline "
            f"once the file is there. This case study deliberately has no "
            f"synthetic fallback: substituting invented numbers for a named "
            f"public source, silently, is the failure it is teaching "
            f"against.") from exc
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(raw, encoding="utf8")
    return parse_ames(raw), SOURCE


def parse_ames(raw: str) -> List[Dict[str, float]]:
    """Tab-delimited, 82 columns. Rows with a missing value are DROPPED, counted.

    Dropped rather than imputed, and the count is reported: a case study that
    quietly filled 490 basements with zero would be making the modelling
    decision that matters most and saying nothing about it.
    """
    lines = [line for line in raw.splitlines() if line.strip()]
    header = lines[0].split("\t")
    index = {name: i for i, name in enumerate(header)}
    wanted = [source for _, source, _, _ in REGRESSORS] + [TARGET[1]]
    for name in wanted:
        if name not in index:
            raise SystemExit(f"the source has no column '{name}'")

    rows: List[Dict[str, float]] = []
    for line in lines[1:]:
        cells = line.split("\t")
        try:
            values = {ours: float(cells[index[source]])
                      for ours, source, _, _ in REGRESSORS}
            values[TARGET[0]] = float(cells[index[TARGET[1]]])
            year = int(float(cells[index["Yr Sold"]]))
            month = int(float(cells[index["Mo Sold"]]))
        except (ValueError, IndexError, KeyError):
            continue                       # a missing or non-numeric cell
        sold = _epoch(year, month)
        values.update({
            "entity_id": f"AMES-{cells[index['PID']].strip()}",
            # Both clocks. `event_ts` is the month of sale, which the source
            # gives. `ingest_ts` is the assumed recording lag — see
            # RECORDING_LAG_DAYS above.
            "event_ts": sold,
            "ingest_ts": sold + RECORDING_LAG_DAYS * DAY,
        })
        rows.append(values)
    return rows


def _epoch(year: int, month: int) -> float:
    """Midnight UTC on the first of that month, without importing a calendar."""
    days = 0
    for y in range(1970, year):
        days += 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
    lengths = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
               else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    days += sum(lengths[:max(0, month - 1)])
    return float(days) * DAY


# ============================================================= the mathematics
def kernel_expression() -> str:
    """Sale price as a linear combination. Linear in parameters, by design.

    Written as one closed-form expression so that the register holds the model
    rather than a pointer to a fitting library — the same property the
    Black-Scholes case study has, for the same reason.
    """
    terms = " + ".join(f"b_{name} * {name}" for name, _, _, _ in REGRESSORS)
    return f"intercept + {terms}"


KERNEL = {
    "runtime": "formula",
    # T2: coefficients ESTIMATED from a sample. Not calibrated to observables
    # (T1) and not trained by an iterative learner (T3). MAYA derives it.
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "deterministic": True,
    "entry": {"expression": kernel_expression(), "target": TARGET[0]},
    # X — what the featureset must supply. L-W10 checks exactly this list.
    "input_schema": [
        {"name": name, "dtype": "numeric", "symbol": symbol,
         "unit": description}
        for name, _, description, symbol in REGRESSORS
    ],
    # P — the coefficients, which arrive from an approved parameter set.
    "parameter_schema": (
        [{"name": "intercept", "dtype": "numeric", "symbol": r"\beta_{0}",
          "unit": "USD"}]
        + [{"name": f"b_{name}", "dtype": "numeric",
            "symbol": rf"\beta_{{{i}}}", "unit": "USD per unit"}
           for i, (name, _, _, _) in enumerate(REGRESSORS, start=1)]
    ),
    "output_schema": [{"name": TARGET[0], "dtype": "numeric", "unit": "USD"}],
}


# ================================================== the fit, in this process
def ordinary_least_squares(rows: List[Dict[str, float]]) -> Dict[str, object]:
    """OLS by QR, with the diagnostics a validator asks for. NOT MAYA's job.

    Solved through `lstsq` rather than by inverting X'X: the normal equations
    square the condition number, and two correlated regressors is exactly where
    that stops being a textbook remark. The condition number is reported for
    the same reason — it is the number that says whether the coefficients mean
    anything individually.
    """
    import numpy as np

    names = [name for name, _, _, _ in REGRESSORS]
    y = np.asarray([r[TARGET[0]] for r in rows], dtype=float)
    X = np.column_stack([np.ones(len(rows))]
                        + [np.asarray([r[n] for r in rows], dtype=float)
                           for n in names])
    beta, _, rank, singular = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    residual = y - fitted
    n, k = X.shape
    ss_res = float(residual @ residual)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot
    return {
        "values": {"intercept": float(beta[0]),
                   **{f"b_{name}": float(b) for name, b in zip(names, beta[1:])}},
        "diagnostics": {
            "observations": int(n), "regressors": int(k - 1), "rank": int(rank),
            "r_squared": round(r2, 6),
            "adjusted_r_squared": round(1 - (1 - r2) * (n - 1) / (n - k), 6),
            "residual_standard_error": round(math.sqrt(ss_res / (n - k)), 4),
            "condition_number": round(float(singular.max() / singular.min()), 2),
            "solver": "numpy.linalg.lstsq (QR), not the normal equations",
            "full_rank": bool(rank == k),
        },
    }


# ================================================================== the build
def main() -> int:
    args = parse("Case study 2 — home price regression on public Ames data")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 2 — multiple linear regression, on public data (T2)")

    # -------------------------------------------------------- 0. the source
    say.step("Fetch the source data")
    rows, provenance = fetch(args.offline)
    say.engine(f"{len(rows):,} usable sales from {provenance}")
    say.note(f"event_ts is the month of sale, which the source gives. "
             f"ingest_ts is event_ts + {RECORDING_LAG_DAYS:.0f} days, which is "
             f"an ASSUMED county recording lag — the source has no ingest "
             f"clock, and this assumption is recorded everywhere it matters")

    maya = connect(args)

    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------ features
    say.step("Register the features and the label")
    for name, _, description, _ in REGRESSORS:
        attempt(name, lambda n=name, d=description: maya.features.define(
            name=n, entity=ENTITY, dtype="numeric", description=d,
            owner="person/a.mehta", source_system="Ames Assessor's Office"))
    attempt(TARGET[0], lambda: maya.features.define(
        name=TARGET[0], entity=ENTITY, dtype="numeric", description=TARGET[2],
        owner="person/a.mehta", source_system="Ames Assessor's Office"))

    say.step("Load the sales — both clocks on every row")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=[n for n, _, _, _ in REGRESSORS] + [TARGET[0]],
        description=(f"Ames residential sales from {SOURCE}. event_ts is the "
                     f"month of sale from the source; ingest_ts is event_ts + "
                     f"{RECORDING_LAG_DAYS:.0f} days, an ASSUMED recording "
                     f"lag — the source carries no ingest clock.")))
    load_once(maya, VIEW, rows)

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={**{n: "numeric" for n, _, _, _ in REGRESSORS},
               TARGET[0]: "numeric"},
        label_slot=TARGET[0], outcome_window_days=0,
        description="what the collateral valuation model reads, and its label"))
    fs_version = ensure_filled(maya, FEATURESET, {
        **{n: n for n, _, _, _ in REGRESSORS}, TARGET[0]: TARGET[0]})

    # --------------------------------------------------------------- model
    say.step("Register the model")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Residential collateral value (OLS)",
        model_class="retail.collateral.valuation", domain="retail_credit",
        owner="person/j.okafor", legal_entity="LE-US-01",
        purpose="indicative market value of residential collateral at "
                "origination and revaluation"))
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=850_000_000, purpose_class="credit_decision",
        feature_count=len(REGRESSORS), uses_alternative_data=False,
        interpretable=True), already="already tiered")
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    say.maya(f"trainability class {version_record.get('trainability_class')} "
             f"— DERIVED from estimate over estimated_coefficients")

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Five regressors, all interpretable, linear in parameters. "
                  "Condition number and rank reviewed with the fit.")
    say.maya(f"risk tier {tier}")

    say.step("Put the model record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Collateral valuation, owned by retail credit.")

    say.step("Grant the standing entitlements")
    # The GRANT's id is kept. `parameters.record(warrant_id=...)` is checked
    # against the standing entitlement in MAYA's `warrant` table, not against
    # the minted fit-warrant document — a fit warrant carries a freshly
    # generated `warrant_id` that is never persisted, so it cannot be looked up
    # later. Both ids end up on the record: the grant as the authority, the
    # minted document id in the diagnostics, so "which authorisation produced
    # these numbers" has an answer at both levels.
    lab_grant = attempt("estimate, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (lab_grant or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("value, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="credit_decision", environment="prod"))

    # ------------------------------------------------- a refusal worth doing
    say.step("Show a control biting: a read bounded in only one clock")
    say.did("L-W9 requires BOTH bounds. A window with no end is a window that "
            "will include tomorrow's data the next time it is opened")
    expect_refusal(
        "a training warrant whose window names no upper bound",
        lambda: maya.warrants.for_fitting(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            featureset=FEATURESET, featureset_version=fs_version,
            window={"from": WINDOW_FROM}, as_of=AS_OF))

    # ------------------------------------------------- the TRAINING warrant
    say.step("Ask MAYA for the TRAINING warrant")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF)
    fit_id = fit_warrant.get("warrant_id")
    say.maya(f"training warrant {fit_id}, verb "
             f"'{(fit_warrant.get('operation') or {}).get('verb')}'")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the training warrant")

    # ------------------------------------------------------- THE ENGINE FITS
    say.step("Estimate the coefficients — HERE, not in MAYA")
    say.note("this is numpy in this file. MAYA issued the authority and will "
             "record the result; it does not own a design matrix")
    fit = ordinary_least_squares(rows)
    values, diagnostics = fit["values"], fit["diagnostics"]
    say.engine(f"n={diagnostics['observations']:,}  "
               f"R²={diagnostics['r_squared']:.4f}  "
               f"adj R²={diagnostics['adjusted_r_squared']:.4f}")
    say.engine(f"condition number {diagnostics['condition_number']:,.0f}, "
               f"residual SE ${diagnostics['residual_standard_error']:,.0f}")
    for name, coefficient in values.items():
        print(f"        {name:<20} {coefficient:>14,.2f}")

    # ------------------------------------------------ DELIVER to the register
    say.step("Deliver the coefficients to MAYA, under that warrant")
    recorded = attempt("the parameter set", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="ames-ols-2010", kind="coefficients",
        values=values, provenance="fitted", warrant_id=grant_id,
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF,
        diagnostics={**diagnostics, "source": SOURCE,
                     "fit_warrant_document": fit_id,
                     "ingest_clock": f"assumed {RECORDING_LAG_DAYS:.0f}-day "
                                     f"recording lag; not from the source"},
        note="OLS on the full Ames sample; see diagnostics for rank and "
             "conditioning"))
    parameter_set_id = (recorded or {}).get("id") or \
        (recorded or {}).get("parameter_set_id")

    say.step("A different person accepts it")
    if parameter_set_id:
        attempt("accepted by s.iqbal (model risk)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Full rank, condition number reviewed, residual SE "
                         "acceptable for an indicative valuation."),
                already="already reviewed")

    # ---------------------------------------------------------- mathematics
    say.step("Ask MAYA for the mathematics it holds")
    maths = mathematics(maya, URN, SEMVER)
    say.maya("LaTeX and Python derived from the stored expression")

    # ------------------------------------------------------ EXECUTION warrant
    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="credit_decision", environment="prod", verb="score")
        source = (run_warrant.get("parameters") or {}).get("source") or {}
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}, naming "
                 f"'{source.get('name')}'")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    # ------------------------------------------------------ run it, LOCALLY
    scored: List[Dict[str, float]] = []
    if run_warrant is not None:
        say.step("Score properties — LOCALLY, under that warrant")
        coefficients = _coefficients_from_warrant(run_warrant, maya, values)
        for row in rows[:8]:
            got = _predict(maths, row, coefficients)
            scored.append({"id": row["entity_id"], "modelled": got,
                           "actual": row[TARGET[0]],
                           "error": got - row[TARGET[0]]})
        print(f"        {'property':<20}{'modelled':>13}{'actual':>13}"
              f"{'error':>13}")
        for line in scored:
            print(f"        {line['id']:<20}{line['modelled']:>13,.0f}"
                  f"{line['actual']:>13,.0f}{line['error']:>13,.0f}")
        say.engine(f"{len(scored)} properties valued locally; MAYA was not in "
                   f"this loop")

    # -------------------------------------------------------- the document
    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, fit_warrant, run_warrant,
                          values, diagnostics, scored, provenance, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. The regression ran here; MAYA holds the model, the data's")
    print("two clocks, both warrants and an APPROVED coefficient set.")
    print(f"{'=' * 78}")
    return 0


def _existing_grant(maya: Maya, urn: str, environment: str) -> Optional[str]:
    """The standing grant already held for this model in this environment."""
    for row in (maya.call("GET", "/warrants") or {}).get("warrants", []):
        if row.get("model_urn") == urn and row.get("environment") == environment:
            return row.get("id")
    return None


def _coefficients_from_warrant(warrant, maya: Maya,
                               fallback: Dict[str, float]) -> Dict[str, float]:
    ref = (warrant.get("parameters") or {}).get("source") or {}
    set_id = ref.get("parameter_set")
    if not set_id:
        return fallback
    return (maya.parameters.get(str(set_id)) or {}).get("values") or fallback


def _predict(maths, row: Dict[str, float],
             coefficients: Dict[str, float]) -> float:
    """Run MAYA's derived Python locally. The code came from the register."""
    namespace: Dict[str, object] = {}
    exec(compile(str(maths.get("python") or ""),                  # noqa: S102
                 "<maya-derived>", "exec"), namespace)
    predict = namespace["predict"]
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    supplied = {**row, **coefficients}
    return float(predict(**{k: supplied[k] for k in wanted}))     # type: ignore[operator]


def write_document(out, maths, version_record, fit_warrant, run_warrant,
                   values, diagnostics, scored, provenance, tier):
    coefficient_rows = [[latex_escape(name), f"{value:,.4f}"]
                        for name, value in values.items()]
    blocks = [
        r"\section{What this model is}",
        "An ordinary least squares regression of residential sale price on five "
        "interpretable regressors. MAYA classifies it \\textbf{T2}: coefficients "
        "\\emph{estimated} from a sample, as against calibrated to observables "
        "(T1) or trained by an iterative learner (T3). The class is derived from "
        "the kernel, not declared.",

        r"\section{The data, and the clock that was not in it}",
        f"Source: \\texttt{{{latex_escape(provenance)}}}, "
        f"{diagnostics['observations']:,} usable sales. "
        "The source gives the month and year of each sale and says nothing "
        "about when the assessor's office recorded it. MAYA requires two "
        "clocks on every row --- \\emph{when it was true} and \\emph{when we "
        "learned it} --- so the second had to come from somewhere.",
        rf"\textbf{{The assumption.}} \texttt{{ingest\_ts}} is the sale month "
        rf"plus {RECORDING_LAG_DAYS:.0f} days, a plausible county recording "
        r"lag. It is an assumption and not a fact from the source, it is "
        r"recorded on the feature view, on the parameter set and here, and it "
        r"is the kind of thing that is normally decided by nobody and written "
        r"down nowhere.",

        r"\section{The equation, as the register holds it}",
        equation(str(maths.get("latex") or ""),
                 str(maths.get("expression") or "")),

        r"\section{The estimate}",
        "Fitted in the bank's own environment by \\texttt{numpy.linalg.lstsq} "
        "(QR), under a training warrant MAYA issued, and delivered back to the "
        "register. MAYA did not perform the regression.",
        table(coefficient_rows, header=["Parameter", "Estimate"], spec="lr"),
        table([["Observations", f"{diagnostics['observations']:,}"],
               ["Regressors", str(diagnostics["regressors"])],
               ["Rank", f"{diagnostics['rank']} (full: {diagnostics['full_rank']})"],
               ["$R^2$", f"{diagnostics['r_squared']:.4f}"],
               ["Adjusted $R^2$", f"{diagnostics['adjusted_r_squared']:.4f}"],
               ["Residual standard error", f"{diagnostics['residual_standard_error']:,.0f}"],
               ["Condition number", f"{diagnostics['condition_number']:,.0f}"]],
              header=["Diagnostic", "Value"], spec="lr"),
        r"The condition number is reported because it is the number that says "
        r"whether the coefficients mean anything \emph{individually}. A "
        r"well-fitting regression on collinear regressors has a good $R^2$ and "
        r"coefficients nobody should interpret.",

        r"\section{Governance}",
        table([["Model URN", version_record.get("urn", "—")],
               ["Version", version_record.get("semver", "—")],
               ["Trainability class", version_record.get("trainability_class", "—")],
               ["Risk tier", str(tier)],
               ["Training warrant", (fit_warrant or {}).get("warrant_id", "—")],
               ["Execution warrant", (run_warrant or {}).get("warrant_id", "not issued")]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "home-price-specification.tex",
                    title="Residential Collateral Value --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
