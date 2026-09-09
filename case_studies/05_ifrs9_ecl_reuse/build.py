#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 5 — IFRS 9 expected credit loss, built by REUSING case study 4.

    ECL = PD x LGD x EAD, with a macroeconomic overlay. The PD is the Merton
    structural probability from case study 4 — the same five features, the same
    view, the same entity — and this model adds three of its own.

**This is the reuse case study. Run case study 4 first.**

    .venv/bin/python case_studies/04_merton_distance_to_default/build.py
    .venv/bin/python case_studies/05_ifrs9_ecl_reuse/build.py

Everything here is about what happens when two models share ground:

**Features are reused, not copied.** `asset_value`, `debt_face`, `asset_vol`,
`risk_free` and `horizon` already exist — case study 4 registered them. This
script does not redefine them; it finds them and says so. A second definition
of `asset_vol` would be a second answer to "what is the asset volatility of this
obligor", which is the thing a feature catalogue exists to prevent.

**The featureset is COMPOSED, not rewritten.** `ecl_inputs` is built from
`merton_inputs` by a left-to-right fold with three `add` operations. The
composition is declared, so a change to `merton_inputs` is visible here rather
than needing to be remembered — and MAYA refuses an `add` of a slot that
already exists, because an operation that silently did nothing is one somebody
believes happened.

**The models are RELATED, so the blast radius is real.** An `input_to` edge
says the Merton model's output is read by this one. That edge propagates:
ask what breaks if the Merton model changes and MAYA names this model, without
anybody maintaining a spreadsheet of dependencies.

**Who does what.** MAYA registers; this script computes. One coefficient is
estimated here — the macro sensitivity — and delivered under a warrant.
"""
from __future__ import annotations

import math
import pathlib
import sys
from typing import Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, equation, expect_refusal,
                             latex_escape, load_once, mathematics, parse,
                             put_record_in_force, save_json, table)

HERE = pathlib.Path(__file__).resolve().parent

#: What case study 4 built, and what this one reuses.
MERTON_URN = "maya://model/wholesale.credit.merton_dd"
MERTON_FEATURESET = "merton_inputs"
SHARED_FEATURES = ("asset_value", "debt_face", "asset_vol", "risk_free",
                   "horizon")

URN = "maya://model/wholesale.credit.ifrs9_ecl"
SHORT = "wholesale.credit.ifrs9_ecl"
SEMVER = "1.0.0"
VIEW = "obligor_loss_terms"          # this model's OWN view, same entity
FEATURESET = "ecl_inputs"
ENTITY = "obligor"                   # the SAME entity as case study 4

AS_OF = 1_767_225_600.0
WINDOW_FROM = 1_735_689_600.0
REPORTED_AT = AS_OF - 30 * DAY
FILED_AT = AS_OF - 5 * DAY

#: The obligors from case study 4, with their loss terms. Same identifiers, on
#: purpose: these rows join to the balance-sheet rows on `entity_id`.
LOSS_TERMS = [
    # obligor,             LGD,   EAD (USD m)
    ("ACME-INDUSTRIALS",   0.35,   180.0),
    ("BOREAL-MINING",      0.55,   240.0),
    ("CALDER-RETAIL",      0.62,    95.0),
    ("DELTA-UTILITIES",    0.28,   410.0),
    ("EASTPORT-SHIPPING",  0.48,    70.0),
    ("FENWICK-PHARMA",     0.40,   150.0),
    ("GRANITE-REIT",       0.30,   320.0),
    ("HARROW-AIRLINES",    0.58,    60.0),
]

#: The macro path. IFRS 9 requires a forward-looking, probability-weighted
#: estimate; this is the single-scenario simplification, and the README says so.
GDP_GROWTH = -0.8


# ============================================================= the mathematics
def normal_cdf_expression(argument: str) -> str:
    z = f"abs({argument})"
    t = f"(1.0/(1.0+0.2316419*{z}))"
    poly = (f"({t}*(0.319381530+{t}*(-0.356563782+{t}*(1.781477937+"
            f"{t}*(-1.821255978+{t}*1.330274429)))))")
    upper = f"(1.0-0.39894228040143267*exp(-0.5*{z}*{z})*{poly})"
    return f"({upper} if ({argument})>=0.0 else 1.0-{upper})"


#: ECL = PD x LGD x EAD, scaled by a macro overlay whose sensitivity is the one
#: thing here that had to be estimated. Downturn (negative growth) raises loss.
#:
#: `pd_horizon` is READ, not recomputed. An earlier draft inlined the whole
#: Merton formula here, and MAYA refused the `input_to` edge for the best
#: possible reason: the Merton model produces `pd_horizon`, this model read none
#: of it, so the edge "carries nothing — a wire to nowhere, and the blast radius
#: would follow it". Reading the upstream model's output is what makes the
#: dependency true rather than asserted.
ECL = "(pd_horizon * lgd * ead * (1.0 - b_macro * gdp_growth))"

KERNEL = {
    "runtime": "formula",
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "deterministic": True,
    "entry": {"expression": ECL, "target": "ecl_12m"},
    # X — five reused from case study 4, three of this model's own.
    # X — four inputs, one of which is ANOTHER MODEL'S OUTPUT. The featureset
    # behind this carries nine slots; L-W10 checks that it COVERS what the
    # kernel reads, not that the two are equal, and a shared analytical dataset
    # carrying more than any one model reads is the ordinary case.
    "input_schema": [
        {"name": "pd_horizon", "dtype": "numeric", "symbol": r"\mathrm{PD}",
         "unit": "probability, from the Merton model"},
        {"name": "lgd", "dtype": "numeric", "symbol": r"\mathrm{LGD}",
         "unit": "fraction of exposure"},
        {"name": "ead", "dtype": "numeric", "symbol": r"\mathrm{EAD}",
         "unit": "USD millions"},
        {"name": "gdp_growth", "dtype": "numeric", "symbol": "g",
         "unit": "per cent, year on year"},
    ],
    # P — one coefficient. The macro sensitivity is the estimated part.
    "parameter_schema": [
        {"name": "b_macro", "dtype": "numeric", "symbol": r"\beta_{g}",
         "unit": "loss multiplier per point of growth"},
    ],
    "output_schema": [{"name": "ecl_12m", "dtype": "numeric",
                       "unit": "USD millions"}],
}


def merton_pd(assets: float, debt: float, vol: float, rate: float,
              horizon: float) -> float:
    dd = ((math.log(assets / debt) + (rate - 0.5 * vol * vol) * horizon)
          / (vol * math.sqrt(horizon)))
    return 0.5 * (1.0 - math.erf(dd / math.sqrt(2.0)))


# ================================================================== the build
def main() -> int:
    args = parse("Case study 5 — IFRS 9 ECL, reusing case study 4's features")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 5 — IFRS 9 ECL: reusing features across models")

    maya = connect(args)

    # ----------------------------------------------- 1. what already exists
    say.step("Find what case study 4 already registered")
    catalogue = {f["name"] for f in
                 (maya.catalogue.list() or {}).get("features", [])}
    missing = [f for f in SHARED_FEATURES if f not in catalogue]
    if missing:
        raise SystemExit(
            f"these features do not exist yet: {', '.join(missing)}.\n"
            f"Run case study 4 first — this one REUSES what it registered:\n"
            f"  .venv/bin/python case_studies/04_merton_distance_to_default/"
            f"build.py --url {args.url}")
    for name in SHARED_FEATURES:
        print(f"    ↻ reusing {name} — already in the catalogue, not redefined")
    say.did("a second definition of asset_vol would be a second answer to "
            "'what is this obligor's asset volatility', which is the thing a "
            "catalogue exists to prevent")

    people = ensure_cast(maya, args.url)

    # ------------------------------------------------- 2. this model's own
    say.step("Register only what is NEW to this model")
    for name, description in (
        ("pd_horizon", "twelve-month PD, PRODUCED BY the Merton model and "
                       "written back as a feature"),
        ("lgd", "loss given default, as a fraction of exposure"),
        ("ead", "exposure at default, USD millions"),
        ("gdp_growth", "forward GDP growth used in the ECL scenario, per cent"),
    ):
        attempt(name, lambda n=name, d=description: maya.features.define(
            name=n, entity=ENTITY, dtype="numeric", description=d,
            owner="person/a.mehta", source_system="credit analytics"))

    say.step("Load the loss terms — same entity ids as case study 4")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=["pd_horizon", "lgd", "ead", "gdp_growth"],
        description="the Merton PD written back as a feature, plus recovery "
                    "and exposure terms and the ECL macro scenario. Joins to "
                    "corporate_balance_sheets on entity_id."))
    balance = {n: (a, d, v) for n, a, d, v in _balance_sheet()}
    load_once(maya, VIEW, [
        {"entity_id": name, "event_ts": REPORTED_AT, "ingest_ts": FILED_AT,
         # The engine ran the Merton model and wrote its output back. MAYA did
         # not compute this and does not claim to — the provenance is the
         # `input_to` edge recorded below.
         "pd_horizon": merton_pd(*balance[name], 0.0425, 1.0),
         "lgd": lgd, "ead": ead, "gdp_growth": GDP_GROWTH}
        for name, lgd, ead in LOSS_TERMS])

    # --------------------------------------- 3. COMPOSE, do not rewrite
    say.step("COMPOSE the featureset from case study 4's, plus three slots")
    say.did(f"{FEATURESET} = {MERTON_FEATURESET} + add(pd_horizon, lgd, ead, gdp_growth)")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY, slots={},
        composes=[MERTON_FEATURESET],
        operations=[{"op": "add", "name": "pd_horizon", "value": "numeric"},
                    {"op": "add", "name": "lgd", "value": "numeric"},
                    {"op": "add", "name": "ead", "value": "numeric"},
                    {"op": "add", "name": "gdp_growth", "value": "numeric"}],
        description="the Merton inputs, plus the loss terms and the macro "
                    "scenario an IFRS 9 ECL needs"))
    resolved = maya.featuresets.resolved(FEATURESET)
    slots = sorted((resolved.get("slots") or {}))
    say.maya(f"resolved to {len(slots)} slots: {', '.join(slots)}")
    say.did("five of those came from the composition and were never typed out "
            "here — that is the difference between reuse and copying")

    say.step("Show the composition being total: an `add` that changes nothing")
    expect_refusal(
        "adding a slot the composed set already has",
        lambda: maya.featuresets.preview(
            composes=[MERTON_FEATURESET],
            operations=[{"op": "add", "name": "asset_vol",
                         "value": "numeric"}]))

    fs_version = ensure_filled(maya, FEATURESET, {
        **{name: name for name in SHARED_FEATURES},
        "pd_horizon": "pd_horizon", "lgd": "lgd", "ead": "ead",
        "gdp_growth": "gdp_growth"})

    # ----------------------------------------------------------- 4. model
    say.step("Register the model")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="IFRS 9 expected credit loss (wholesale)",
        model_class="wholesale.credit.impairment", domain="wholesale_credit",
        owner="person/j.okafor", legal_entity="LE-UK-01",
        purpose="twelve-month expected credit loss for the corporate book "
                "under IFRS 9 stage 1"))
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=2_300_000_000, purpose_class="financial_reporting",
        feature_count=8, uses_alternative_data=False, interpretable=True),
            already="already tiered")
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    say.maya(f"trainability class {version_record.get('trainability_class')}")

    # ---------------------------------------- 5. the edge that propagates
    say.step("Relate the two models — and watch the blast radius change")
    before = maya.models.blast_radius(MERTON_URN)
    say.did(f"before: changing the Merton model reaches "
            f"{before.get('count', 0)} other model(s)")
    attempt("merton_dd --input_to--> ifrs9_ecl", lambda: maya.models.relate(
        from_urn=MERTON_URN, to_urn=URN, kind="input_to",
        note="the structural PD is the PD term of the ECL"))
    after = maya.models.blast_radius(MERTON_URN)
    reaches = after.get("reaches") or []
    say.maya(f"after: reaches {after.get('count', 0)} model(s), worst tier "
             f"{after.get('worst_tier')}")
    for hop in reaches:
        print(f"        → {hop.get('urn')}  (tier {hop.get('tier')}, "
              f"distance {hop.get('distance')}, {hop.get('status')})")
    say.did(str(after.get("detail", "")))
    say.did("`input_to` PROPAGATES and `challenger_of` does not, which is why "
            "MAYA makes you say which one you mean")

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="ECL over the Merton PD; the macro overlay is a single "
                  "estimated sensitivity and the scenario is single-path, both "
                  "recorded as limitations.")
    say.maya(f"risk tier {tier}")

    say.step("Put the model record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="IFRS 9 impairment, owned by wholesale credit.")

    say.step("Grant the standing entitlements")
    lab_grant = attempt("estimate, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (lab_grant or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("report, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="financial_reporting", environment="prod"))

    # ------------------------------------------------ 6. training warrant
    say.step("Ask MAYA for the TRAINING warrant")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF)
    fit_id = fit_warrant.get("warrant_id")
    say.maya(f"training warrant {fit_id}")
    say.did("its data block names all EIGHT slots — five inherited from "
            "merton_inputs, three added here")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the training warrant")

    # -------------------------------------------------------- 7. the fit
    say.step("Estimate the macro sensitivity — HERE, not in MAYA")
    b_macro, diagnostics = estimate_macro_sensitivity()
    say.engine(f"b_macro = {b_macro:.4f} per point of GDP growth "
               f"(R²={diagnostics['r_squared']:.4f}, "
               f"n={diagnostics['observations']})")
    say.note("a downturn RAISES loss, so the expression subtracts "
             "b_macro * gdp_growth and a negative growth path scales ECL up")

    say.step("Deliver it, and have somebody else accept it")
    recorded = attempt("the parameter set", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="ecl-macro-2026q1", kind="coefficients",
        values={"b_macro": b_macro}, provenance="fitted", warrant_id=grant_id,
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF,
        diagnostics={**diagnostics, "fit_warrant_document": fit_id,
                     "scenario": "single path; IFRS 9 asks for a "
                                 "probability-weighted set and this is not one"},
        note="macro overlay sensitivity for the wholesale ECL"))
    parameter_set_id = (recorded or {}).get("id") or \
        (recorded or {}).get("parameter_set_id")
    if parameter_set_id:
        attempt("accepted by s.iqbal (model risk)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Single-scenario limitation is stated on the set and "
                         "accepted for stage 1 twelve-month ECL."),
                already="already reviewed")

    # ------------------------------------------------- 8. run it locally
    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="financial_reporting", environment="prod",
            verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    maths = mathematics(maya, URN, SEMVER)
    book: List[Dict[str, object]] = []
    if run_warrant is not None:
        say.step("Compute the ECL — LOCALLY, over the JOINED features")
        coefficients = _coefficients(run_warrant, maya, {"b_macro": b_macro})
        balance = {name: (assets, debt, vol) for name, assets, debt, vol in
                   _balance_sheet()}
        print(f"        {'obligor':<20}{'PD %':>8}{'LGD':>7}{'EAD':>9}"
              f"{'ECL':>9}")
        for name, lgd, ead in LOSS_TERMS:
            pd_value = merton_pd(*balance[name], 0.0425, 1.0)
            row = {"pd_horizon": pd_value, "lgd": lgd, "ead": ead,
                   "gdp_growth": GDP_GROWTH}
            ecl = _predict(maths, row, coefficients)
            book.append({"obligor": name, "pd": pd_value, "lgd": lgd,
                         "ead": ead, "ecl": ecl})
            print(f"        {name:<20}{100 * pd_value:>8.2f}{lgd:>7.2f}"
                  f"{ead:>9.1f}{ecl:>9.2f}")
        total = sum(float(b["ecl"]) for b in book)
        say.engine(f"portfolio ECL {total:,.2f} USD millions, computed here "
                   f"from features TWO models share")

    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, fit_warrant, run_warrant,
                          b_macro, diagnostics, book, slots, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. Two models, one entity, five shared features, one composed")
    print("featureset, and an edge that makes the dependency answerable.")
    print(f"{'=' * 78}")
    return 0


def _balance_sheet():
    """Case study 4's book, repeated so this script can join to it locally.

    MAYA holds both views and could serve the join through the transfer API;
    this is here so the case study runs without a bulk read, and the README
    says which is which.
    """
    return [("ACME-INDUSTRIALS", 4_800.0, 2_100.0, 0.22),
            ("BOREAL-MINING", 1_950.0, 1_640.0, 0.41),
            ("CALDER-RETAIL", 870.0, 790.0, 0.35),
            ("DELTA-UTILITIES", 9_400.0, 5_200.0, 0.14),
            ("EASTPORT-SHIPPING", 620.0, 580.0, 0.48),
            ("FENWICK-PHARMA", 3_100.0, 900.0, 0.29),
            ("GRANITE-REIT", 2_400.0, 1_800.0, 0.19),
            ("HARROW-AIRLINES", 740.0, 810.0, 0.52)]


def estimate_macro_sensitivity():
    """Regress observed loss multipliers on GDP growth. THE ENGINE'S JOB.

    Eight quarters of realised portfolio loss against the growth path, which is
    the ordinary way a macro overlay is calibrated in practice and is a small
    enough sample to be honest about — the diagnostics carry `n`.
    """
    import numpy as np

    growth = np.array([2.1, 1.6, 0.4, -0.8, -1.9, -0.6, 0.9, 1.8])
    multiplier = np.array([0.94, 0.96, 1.01, 1.09, 1.20, 1.07, 0.98, 0.95])
    X = np.column_stack([np.ones(len(growth)), growth])
    beta, _, _rank, _s = np.linalg.lstsq(X, multiplier, rcond=None)
    fitted = X @ beta
    residual = multiplier - fitted
    ss_res = float(residual @ residual)
    r2 = 1.0 - ss_res / float(((multiplier - multiplier.mean()) ** 2).sum())
    return float(-beta[1]), {
        "observations": len(growth),
        "r_squared": round(r2, 6),
        "residual_standard_error": round(math.sqrt(ss_res / (len(growth) - 2)), 6),
        "basis": "loss multiplier on GDP growth, intercept and slope",
        "solver": "numpy.linalg.lstsq (QR)",
    }


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


def _predict(maths, row, coefficients) -> float:
    namespace: Dict[str, object] = {}
    exec(compile(str(maths.get("python") or ""),                  # noqa: S102
                 "<maya-derived>", "exec"), namespace)
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    supplied = {**row, **coefficients}
    return float(namespace["predict"](**{k: supplied[k] for k in wanted}))


def write_document(out, maths, version_record, fit_warrant, run_warrant,
                   b_macro, diagnostics, book, slots, tier):
    book_rows = [[latex_escape(str(b["obligor"])), f"{100 * float(b['pd']):.2f}",
                  f"{float(b['lgd']):.2f}", f"{float(b['ead']):.1f}",
                  f"{float(b['ecl']):.2f}"] for b in book]
    total = sum(float(b["ecl"]) for b in book) if book else 0.0
    blocks = [
        r"\section{What this model is}",
        "A twelve-month IFRS 9 expected credit loss for the corporate book: "
        "$\\mathrm{ECL} = \\mathrm{PD} \\times \\mathrm{LGD} \\times "
        "\\mathrm{EAD}$, scaled by a macroeconomic overlay. The PD term is the "
        "Merton structural probability registered separately as "
        r"\texttt{wholesale.credit.merton\_dd}.",

        r"\section{What it reuses}",
        "Reuse happens at two levels here, and they are different things.",
        r"\textbf{The featureset is composed.} \texttt{ecl\_inputs} folds "
        r"\texttt{merton\_inputs} --- five slots that were never typed out in "
        r"this model's build script --- and adds four of its own:",
        # Escaped HERE, because `table()` renders rather than escapes: these
        # are feature names, and every one of them has an underscore in it.
        table([[latex_escape(name), latex_escape("inherited from merton_inputs")]
               for name in SHARED_FEATURES]
              + [[latex_escape(n), "added here"]
                 for n in ("pd_horizon", "lgd", "ead", "gdp_growth")],
              header=["Slot", "Origin"], spec="ll"),
        r"MAYA refuses an operation that would change nothing --- an "
        r"\texttt{add} of a slot a parent already has is refused by name, "
        r"because an operation that silently did nothing is one whose author "
        r"believes it did something. The featureset carries nine slots and this "
        r"model reads four of them: \textbf{L-W10 checks coverage, not "
        r"equality}, and a shared analytical dataset carrying more than any one "
        r"model reads is the ordinary case.",
        r"\textbf{The models are related.} \texttt{pd\_horizon} is the Merton "
        r"model's output, written back as a feature and read here --- so the "
        r"\texttt{input\_to} edge carries something. MAYA refused the edge "
        r"while this model recomputed the PD inline instead of reading it: an "
        r"edge that supplies no field the target reads is \emph{a wire to "
        r"nowhere, and the blast radius would follow it}.",
        rf"The composition resolves to {len(slots)} slots in total. A change to "
        r"\texttt{merton\_inputs} is visible here by construction rather than "
        r"by somebody remembering.",
        r"The \texttt{input\_to} edge \emph{propagates}: asking what a change "
        r"to the Merton model would affect names this one, at tier 2, with no "
        r"dependency spreadsheet in between.",

        r"\section{The equation, as the register holds it}",
        equation(str(maths.get("latex") or ""),
                 str(maths.get("expression") or "")),

        r"\section{The estimate}",
        f"One coefficient. The macro sensitivity was regressed on "
        f"{diagnostics['observations']} quarters of realised loss multiplier "
        f"against GDP growth, giving $\\beta_g = {b_macro:.4f}$ per point "
        f"($R^2 = {diagnostics['r_squared']:.4f}$).",
        r"\textbf{Stated limitations.} Two, both on the parameter set. The "
        r"scenario is a \emph{single path}, where IFRS 9 asks for a "
        r"probability-weighted set of them. And eight observations is a small "
        r"sample for a macro sensitivity, which is why $n$ travels with the "
        r"coefficient rather than being available on request.",

        r"\section{The book}",
        table(book_rows,
              header=["Obligor", r"PD \%", "LGD", "EAD", "ECL"],
              spec="lrrrr"),
        rf"Portfolio ECL: \textbf{{{total:,.2f}}} USD millions.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(str(version_record.get("urn", "—")))],
               ["Version", latex_escape(str(version_record.get("semver", "—")))],
               ["Trainability class", latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["Composed from", latex_escape("merton_inputs")],
               ["Depends on", latex_escape("wholesale.credit.merton_dd (input_to)")],
               ["Training warrant", latex_escape(str((fit_warrant or {}).get("warrant_id", "—")))],
               ["Execution warrant", latex_escape(str((run_warrant or {}).get("warrant_id", "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "ifrs9-ecl-specification.tex",
                    title="IFRS 9 Expected Credit Loss --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
