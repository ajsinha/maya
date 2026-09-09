#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 8 — A vendor bureau score: governing what you cannot see (T6).

    The bank buys a credit score. It arrives as a number between 300 and 850.
    The bank does not have the coefficients, cannot inspect the model, and
    could not reproduce the score if it wanted to — and it uses it to decline
    people.

**T6 is the honest class.** The parameter object EXISTS — somebody at the
bureau has it — but the governing party cannot reach it. That is different from
T0, where there are no parameters at all, and MAYA refuses a fit for both with
different reasons:

    T0   "its parameters come from theory, not from data — nothing to fit"
    T6   "its parameters exist but are not ours to see"

**What governance looks like when inspection is impossible.** Everything that
depends on reading the model is off the table: no coefficient review, no
recomputation, no independent implementation. What remains is the outside of
the model, and it is more than nothing:

    the CONTRACT      what the vendor asserts it does, recorded as assumptions
                      and guarantees somebody can be held to
    MONITORING        the score's distribution over the bank's own book, which
                      the bank can observe without seeing inside
    the DEPENDENCY    what breaks here if the vendor changes their model, which
                      is answerable from the graph
    the REFUSALS      what the platform will not let anybody pretend

**Who does what.** MAYA registers. The scores come from the bureau. This script
plays the bank's decisioning platform, which receives them.
"""
from __future__ import annotations

import math
import pathlib
import sys
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, expect_refusal, latex_escape,
                             load_once, parse, put_record_in_force, save_json,
                             table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/retail.credit.bureau_score"
SHORT = "retail.credit.bureau_score"
SEMVER = "3.2.0"                    # the VENDOR's version, not ours
VIEW = "bureau_score_pulls"
FEATURESET = "bureau_score_inputs"
ENTITY = "applicant"

AS_OF = 1_767_225_600.0
WINDOW_FROM = 1_735_689_600.0
PULLED_AT = AS_OF - 7 * DAY
RECEIVED_AT = AS_OF - 7 * DAY + 3600.0     # the bureau responds within the hour

KERNEL = {
    # `descriptor_only`: MAYA holds the governance and does not locate the
    # artifact. There is no expression, no file, and nothing to digest —
    # because the bank has none of those things and saying otherwise would be
    # the fiction this class exists to avoid.
    "runtime": "descriptor_only",
    # T6 falls out of `opaque`. The parameters EXIST; they are not ours.
    "parameter_kind": "opaque",
    "fit_procedure": "none",
    "deterministic": True,
    "descriptor_only": True,
    # X is still declarable. The bank knows what it SENDS, even though it does
    # not know what happens next — and declaring it is what makes the
    # dependency on those inputs visible.
    "input_schema": [
        {"name": "applicant_ref", "dtype": "categorical",
         "symbol": r"\mathrm{ref}", "unit": "bureau reference"},
        {"name": "pull_purpose", "dtype": "categorical",
         "symbol": r"\mathrm{purpose}", "unit": "permissible purpose"},
    ],
    "output_schema": [
        {"name": "bureau_score", "dtype": "numeric", "unit": "300-850"},
    ],
}

#: The contract: what the vendor ASSERTS. Not what the bank verified — the
#: distinction is the whole governance content of a T6 registration, and the
#: assumptions are written so that a monitor can test each one.
CONTRACT = {
    "assumptions": [
        {"key": "bureau_score", "minimum": 300, "maximum": 850},
    ],
    "guarantees": [
        {"key": "gini", "minimum": 0.55,
         "note": "vendor-asserted discrimination on their development sample, "
                 "not measured on this bank's book"},
        {"key": "population_stability_index", "maximum": 0.25,
         "note": "vendor-asserted stability quarter on quarter"},
    ],
}

#: Scores as received. Synthetic, and the README says so — a real bureau file
#: is licensed and cannot be redistributed, which is itself part of the point.
APPLICANTS = [
    ("APP-0001", 812), ("APP-0002", 744), ("APP-0003", 690), ("APP-0004", 651),
    ("APP-0005", 705), ("APP-0006", 588), ("APP-0007", 769), ("APP-0008", 623),
    ("APP-0009", 731), ("APP-0010", 802), ("APP-0011", 664), ("APP-0012", 597),
]


def rows() -> List[Dict[str, object]]:
    return [{"entity_id": ref, "event_ts": PULLED_AT, "ingest_ts": RECEIVED_AT,
             "bureau_score": float(score), "applicant_ref": ref,
             "pull_purpose": "credit_application"}
            for ref, score in APPLICANTS]


def distribution(scores: List[float]) -> Dict[str, float]:
    """What the bank CAN measure: the shape of the output over its own book.

    Not a validation of the model — a validation of a model you cannot see is
    not a thing — but a description of what it is doing to this population,
    which is the only handle the bank has and is a real one.
    """
    n = len(scores)
    mean = sum(scores) / n
    sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / (n - 1))
    ordered = sorted(scores)
    return {"n": n, "mean": round(mean, 2), "sd": round(sd, 2),
            "min": ordered[0], "p50": ordered[n // 2], "max": ordered[-1],
            "below_660": sum(1 for s in scores if s < 660)}


# ================================================================== the build
def main() -> int:
    args = parse("Case study 8 — a vendor bureau score, T6")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 8 — a vendor score: governing what you cannot see (T6)")

    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------ features
    say.step("Register what the bank sends, and what it gets back")
    for name, dtype, description in (
        ("applicant_ref", "categorical", "the bureau's reference for the applicant"),
        ("pull_purpose", "categorical", "permissible purpose declared on the pull"),
        ("bureau_score", "numeric", "the score as received, 300-850. NOT computed here"),
    ):
        attempt(name, lambda n=name, d=dtype, s=description:
                maya.features.define(name=n, entity=ENTITY, dtype=d,
                                     description=s, owner="person/a.mehta",
                                     source_system="credit bureau (vendor)"))
    say.did("`bureau_score` is a feature whose SOURCE SYSTEM is a vendor. That "
            "is the honest description: it is data to this bank, and a model "
            "output to somebody else")

    say.step("Load the pulls — both clocks, and they are genuinely different")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=["applicant_ref", "pull_purpose", "bureau_score"],
        description="bureau pulls. event_ts is when the score was pulled; "
                    "ingest_ts is when the bureau responded, about an hour "
                    "later. A score re-pulled tomorrow is a DIFFERENT score."))
    load_once(maya, VIEW, rows())

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={"applicant_ref": "categorical", "pull_purpose": "categorical"},
        description="what the bank sends to the bureau"))
    fs_version = ensure_filled(maya, FEATURESET, {
        "applicant_ref": "applicant_ref", "pull_purpose": "pull_purpose"})

    # --------------------------------------------------------------- model
    say.step("Register the model — the VENDOR's version number")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Bureau credit score (vendor, v3.2)",
        model_class="retail.credit.bureau", domain="retail_credit",
        owner="person/j.okafor", legal_entity="LE-US-01",
        purpose="third-party credit score used in origination decisioning"))
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=2_800_000_000, purpose_class="credit_decision",
        feature_count=2, uses_alternative_data=True,
        # The one that matters here: it is not interpretable, and saying
        # otherwise to get a friendlier tier would be the lie.
        interpretable=False), already="already tiered")
    say.maya(f"trainability class {version_record.get('trainability_class')} "
             f"— DERIVED from an 'opaque' parameter object")
    say.did(f"the semver is {SEMVER} because that is what the VENDOR calls it. "
            f"A bank that renumbers a vendor's model has lost the only "
            f"identifier both parties share")

    # ------------------------------------------------ what CAN be governed
    say.step("Approve the version — the contract is what is being approved")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Third-party score. The coefficients are not available and "
                  "were not reviewed; what was reviewed is the vendor's "
                  "asserted contract and the monitoring that will test it.")
    say.maya(f"risk tier {tier} — and note `interpretable=False` was declared "
             f"honestly, which RAISES the tier")

    say.step("Put the record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Vendor bureau score, owned by retail credit.")

    # ===================================================== the T6 refusals
    say.step("Grant the lab entitlement FIRST")
    say.did("otherwise the next refusal is `no_entitlement` and proves nothing "
            "about T6 — a control that refuses for the wrong reason is a "
            "demonstration of the wrong control")
    attempt("develop, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))

    say.step("Ask for a TRAINING warrant — refused, and for a different reason "
             "than a T0 model's")
    refusal = expect_refusal(
        "a fit warrant for a model whose parameters are not ours",
        lambda: maya.warrants.for_fitting(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            featureset=FEATURESET, featureset_version=fs_version,
            window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF))
    if refusal is not None:
        save_json(out / "refusal-training.json",
                  {"code": refusal.code, "detail": refusal.detail,
                   "remediation": getattr(refusal, "remediation", None)},
                  what="the refusal, kept as evidence")
    say.did("T0 has NO parameters; T6 has parameters somebody else holds. Two "
            "different sentences, and the platform says the right one")

    say.step("Try to record the coefficients anyway")
    expect_refusal(
        "a parameter set for a model whose parameters nobody here can see",
        lambda: maya.parameters.record(
            urn=URN, semver=SEMVER, name="reverse-engineered",
            kind="coefficients", values={"intercept": -3.1, "b_utilisation": 0.8},
            provenance="fitted", warrant_id="none"))
    say.did("reverse-engineering a vendor score and recording the result as "
            "THE model's parameters would be recording a fiction — the numbers "
            "would be a different model that happens to correlate")

    say.step("Grant, and take an EXECUTION warrant")
    attempt("decide, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="credit_decision", environment="prod"))
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="credit_decision", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        realisation = (run_warrant.get("realisation") or {})
        say.maya(f"realisation runtime: '{realisation.get('runtime')}' — MAYA "
                 f"carries the governance and does not locate an artifact")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    # ---------------------------------------- monitoring, the real control
    say.step("Monitor the OUTSIDE of the model — the only handle there is")
    scores = [float(s) for _ref, s in APPLICANTS]
    shape = distribution(scores)
    say.engine(f"n={shape['n']}  mean={shape['mean']}  sd={shape['sd']}  "
               f"min={shape['min']}  median={shape['p50']}  max={shape['max']}")
    say.engine(f"{shape['below_660']} of {shape['n']} below the 660 policy "
               f"floor")
    within = all(300 <= s <= 850 for s in scores)
    say.maya(f"the contract's stated range 300-850 holds on this book: {within}")
    say.did("this is not a validation of the model — a validation of a model "
            "you cannot see is not a thing. It is a description of what the "
            "model is doing to THIS population, which is the handle the bank "
            "actually has, and it is a real one")
    save_json(out / "monitoring.json",
              {"distribution": shape, "contract_range_holds": within,
               "detail": "the vendor asserts gini >= 0.55 on THEIR development "
                         "sample; nothing here measures it on this book"},
              what="the monitoring record")

    say.step("Write the LaTeX specification")
    path = write_document(out, version_record, run_warrant, refusal, shape,
                          tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. A model nobody here can inspect, governed by its contract,")
    print("its monitoring and its refusals — and honest about which is which.")
    print(f"{'=' * 78}")
    return 0


def write_document(out, version_record, run_warrant, refusal, shape, tier):
    blocks = [
        r"\section{What this model is}",
        "A credit score bought from a bureau. It arrives as a number between "
        "300 and 850; the bank does not hold the coefficients, cannot inspect "
        "the model, could not reproduce the score --- and declines people with "
        "it.",
        r"MAYA classifies it \textbf{T6}: the parameter object \emph{exists} "
        r"and is not ours to see. That is a different thing from T0, where "
        r"there are no parameters at all, and the platform refuses a fit for "
        r"both with different reasons.",

        r"\section{The refusal}",
        r"\begin{quote}\ttfamily " +
        latex_escape(str(refusal.detail if refusal else "—")) +
        r"\end{quote}",
        "A second door is shut too: recording reverse-engineered coefficients "
        "as this model's parameters is refused. Numbers fitted to reproduce a "
        "vendor score are a \\emph{different model that happens to correlate}, "
        "and filing them here would be filing a fiction.",

        r"\section{What can still be governed}",
        table([["The contract",
                "What the vendor asserts: a 300--850 range, a gini floor and a "
                "stability ceiling. Recorded as assertions, not findings"],
               ["Monitoring",
                "The score's distribution over this bank's own book --- "
                "observable without seeing inside"],
               ["The dependency",
                "What breaks here when the vendor reversions, answerable from "
                "the graph rather than from a supplier list"],
               ["The tier",
                r"\texttt{interpretable=False} declared honestly, which RAISES "
                r"the tier. Declaring otherwise for a friendlier number is the "
                r"lie this class exists to prevent"]],
              header=["What", "How"], spec=r"lp{92mm}"),

        r"\section{The book, as observed}",
        table([["Observations", str(shape["n"])],
               ["Mean", f"{shape['mean']}"],
               ["Standard deviation", f"{shape['sd']}"],
               ["Minimum / median / maximum",
                f"{shape['min']:.0f} / {shape['p50']:.0f} / {shape['max']:.0f}"],
               ["Below the 660 policy floor", str(shape["below_660"])]],
              header=["Statistic", "Value"], spec="lr"),
        r"\textbf{This is not a validation.} A validation of a model you cannot "
        r"see is not a thing. It is a description of what the model does to "
        r"this population --- and the vendor's asserted gini is measured on "
        r"\emph{their} development sample, not on this book, which the record "
        r"says rather than implies.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(str(version_record.get("urn", "—")))],
               ["Version", latex_escape(str(version_record.get("semver", "—")))
                + " --- the vendor's number, not ours"],
               ["Trainability class",
                latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["Runtime", "descriptor\\_only --- no artifact is located"],
               ["Training warrant", "REFUSED --- the parameters are not ours"],
               ["Execution warrant",
                latex_escape(str((run_warrant or {}).get("warrant_id", "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "bureau-score-specification.tex",
                    title="Vendor Bureau Score --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
