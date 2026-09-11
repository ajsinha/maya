#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 15 — A benefit fraud risk model that used nationality: the second
case study in this suite NOT designed to fit MAYA (T2).

    p(select for review)  =  sigma( b0 + sum_j b_j * x_j )

**The second one taken from somebody else's failure.** Case study 14 walked a
bank's model-change failure into the register. This one walks a government's
discrimination failure into it, and it is here because the two fail in
different places: 14 is about a change nobody was made to justify, and this is
about a **fact the register can see and cannot act on**.

It reconstructs the Dutch childcare benefits affair --- the `toeslagenaffaire`
--- in which the Tax and Customs Administration used a self-learning risk
classification model to select childcare benefit applications for manual
review, and nationality was among the indicators. Roughly twenty-six thousand
families were wrongly treated as fraudulent. The Dutch Data Protection
Authority found the processing unlawful, discriminatory and improper, and fined
the administration EUR 2.75 million. A parliamentary inquiry titled
*Ongekend onrecht* --- "unprecedented injustice" --- reported in December 2020
and the government resigned in January 2021.

**Sources for the sequence**, all public:

  - Autoriteit Persoonsgegevens, *Belastingdienst/Toeslagen: de verwerking van
    de nationaliteit van aanvragers van kinderopvangtoeslag*, 17 July 2020.
  - Autoriteit Persoonsgegevens, fining decision, 7 December 2021 (EUR 2.75m).
  - Parlementaire ondervragingscommissie Kinderopvangtoeslag, *Ongekend
    onrecht*, 17 December 2020.
  - District Court of The Hague, *NJCM and others v. the State of the
    Netherlands* (the SyRI judgment), 5 February 2020,
    ECLI:NL:RBDHA:2020:865.

**The numbers here are a reconstruction.** No real applicant data is used or
reproduced, and none of the coefficients is the administration's. The
reconstruction is sized so that the mechanism is visible and deterministic:
MAYA is being shown a shape of failure, not audited against a case file.

**Seven governance questions, and MAYA answers four and a half.**

  1. Does the register KNOW the model reads a protected characteristic?
     --  yes, computed from the contract rather than declared.
  2. Does anything REFUSE on that?  --  **only if the firm wrote the rule**,
     and this is the sharpest and least comfortable answer in the suite.
  3. Does deleting the column fix it?  --  no, and the script computes by how
     little. `binds_proxy_risk` is a separate fact for exactly this reason.
  4. What control depth does a model that decides a household's income owe?
     --  derived from the purpose it is put to, not from who is asking.
  5. Is the version that runs the version that was approved?
     --  yes, and a self-learning model is where that question bites.
  6. May a fit on this data happen here, for this purpose?
     --  the authority is refused; the execution is not observed.
  7. Was the household treated fairly?  --  **MAYA cannot see this.**

**The honest headline, stated before the script runs rather than after.** MAYA
would have made the nationality binding VISIBLE. It would not, by itself, have
stopped it --- and a register that refused on the tag alone would also refuse
the fairness testing the same regulation requires. Section 9 is the list of
what it does not reach, which in this failure is most of the harm.
"""
from __future__ import annotations

import math
import pathlib
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (Say, approve_version, attempt, connect,
                             document, ensure_cast, ensure_filled,
                             ensure_version, expect_refusal, latex_escape,
                             load_once, parse, put_record_in_force, save_json,
                             table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/benefits.fraud.childcare_selection"
SHORT = "benefits.fraud.childcare_selection"
SEMVER = "1.0.0"
VIEW = "childcare_claim_attributes"
FEATURESET = "childcare_selection_inputs"
ENTITY = "household"

EVENT_TS = 1_735_689_600.0
INGEST_TS = EVENT_TS + 86_400.0

#: The reconstructed scorer. `name, protected, proxy_risk, pii, beta, centre,
#: what` — the continuous inputs are CENTRED, because a logistic model whose
#: inputs are not is one whose intercept has to absorb the means, and a
#: reconstruction where every household scores 1.0 demonstrates nothing. The
#: first version of this file got that wrong and selected 100% of both cohorts.
#:
#: The two flags are the whole case study. `second_nationality` is the one the
#: Data Protection Authority found unlawful. `postcode_deprivation` is the one
#: that still carries the signal after the first is deleted, which is why the
#: platform records a proxy SEPARATELY from a protected characteristic: a model
#: built on a proxy is discriminating without any column saying so.
FEATURES: Tuple[Tuple[str, bool, str, bool, float, float, str], ...] = (
    # 0.30 rather than something larger, and the size is a judgement worth
    # stating: a coefficient big enough to fill the queue with one cohort makes
    # a vivid chart and an incredible reconstruction. At this weight the column
    # is one factor among several — which is both the realistic case and the
    # harder one, because it is the version nobody can point at.
    ("second_nationality", True, "none", True, 0.30, 0.0,
     "whether the applicant holds a nationality besides the national one"),
    ("postcode_deprivation", False, "high", False, 0.28, 5.5,
     "deprivation decile of the household's postcode district, 1-10"),
    ("claim_amount_monthly", False, "none", False, 0.10, 9.0,
     "monthly childcare allowance claimed, in hundreds"),
    ("hours_claimed_weekly", False, "none", False, 0.04, 30.0,
     "childcare hours claimed per week"),
    ("prior_corrections", False, "moderate", False, 0.45, 0.0,
     "how many previous claims were corrected. A correction is not a finding "
     "of fraud, and treating it as one is how an administrative error becomes "
     "a permanent mark"),
    ("partner_present", False, "none", False, -0.35, 0.0,
     "whether a second adult is on the claim"),
)

BIAS = -2.70

#: The review CAPACITY, as a share of all claims. Not a probability threshold:
#: a fraud-selection system does not review everyone the model scores above a
#: half, it reviews as many as it has people for, taking them highest-score
#: first. Modelling it as a threshold made the first version of this file
#: select either everybody or almost nobody depending on the intercept, which
#: is a fact about the intercept and not about the failure.
#:
#: It also puts the question where the harm was: not *what did the model
#: predict* but **who ended up in the queue**, and in the failure this
#: reconstructs the queue was met by a policy that treated an error as fraud.
CAPACITY = 0.15

#: Two reconstructed cohorts, identical in everything the scorer is entitled to
#: look at and different in the two things it is not. Deterministic: a case
#: study whose numbers move between runs is one nobody can check twice.
COHORT = 400


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _households() -> List[Dict[str, Any]]:
    """Two cohorts, built so the confound is explicit rather than hidden.

    Both cohorts claim the same amounts for the same hours with the same
    correction history. They differ in `second_nationality`, and --- because
    housing in this reconstruction is segregated, as it is in most places ---
    they differ in the DISTRIBUTION of `postcode_deprivation` too.

    That second difference is not an accident of the data. It is the mechanism
    by which deleting the first column fails to fix anything, and it is put
    here deliberately so the arithmetic in section 4 can show it.
    """
    rows: List[Dict[str, Any]] = []
    for index in range(COHORT * 2):
        second = 1 if index >= COHORT else 0
        # A deterministic spread, shifted by two deciles between cohorts.
        deprivation = (index % 10) + 1
        if second:
            deprivation = min(10, deprivation + 2)
        rows.append({
            "entity_id": f"H{index:05d}",
            "event_ts": EVENT_TS, "ingest_ts": INGEST_TS,
            "second_nationality": float(second),
            "postcode_deprivation": float(deprivation),
            "claim_amount_monthly": float(6 + (index % 7)),
            "hours_claimed_weekly": float(20 + (index % 21)),
            "prior_corrections": float(index % 3),
            "partner_present": float((index + 1) % 2),
        })
    return rows


def _score(row: Dict[str, Any], *, drop: Tuple[str, ...] = ()) -> float:
    """The scorer, computed in this file. MAYA does not run models."""
    z = BIAS
    for name, _p, _x, _pii, beta, centre, _what in FEATURES:
        if name in drop:
            continue
        z += beta * (float(row[name]) - centre)
    return _sigmoid(z)


def _selection_rates(rows: List[Dict[str, Any]],
                     *, drop: Tuple[str, ...] = ()) -> Dict[str, float]:
    """What share of each cohort ends up in a review queue of fixed size.

    Ranked, then cut at the capacity. Every household is scored, the list is
    sorted, and the top `CAPACITY` share goes to a person — which is what a
    review function with a fixed headcount actually does.
    """
    scored = sorted(((_score(r, drop=drop), r) for r in rows),
                    key=lambda pair: pair[0], reverse=True)
    picked = {id(r) for _p, r in scored[:max(1, int(len(scored) * CAPACITY))]}
    out: Dict[str, float] = {}
    for label, want in (("single nationality", 0.0), ("second nationality", 1.0)):
        cohort = [r for r in rows if r["second_nationality"] == want]
        chosen = [r for r in cohort if id(r) in picked]
        out[label] = len(chosen) / len(cohort)
    out["ratio"] = (out["second nationality"] / out["single nationality"]
                    if out["single nationality"] else float("inf"))
    return out


def _removed_share(before: Dict[str, float], after: Dict[str, float]) -> float:
    """How much of the EXCESS the deletion removed, as a percentage.

    Of the excess rather than of the ratio: a ratio of 1.0 is parity, so the
    quantity that matters is how far above 1.0 each sits. Guarded, because a
    reconstruction that produced no disparity at all would divide by zero here
    — which is exactly what the first version of this file did.
    """
    excess = before["ratio"] - 1.0
    if excess <= 0:
        return 0.0
    return 100.0 * (1.0 - (after["ratio"] - 1.0) / excess)


KERNEL = {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "deterministic": True,
    "input_schema": [{"name": n, "dtype": "float"} for n, *_ in FEATURES],
    "parameter_schema": [{"name": f"beta_{n}", "dtype": "float"}
                         for n, *_ in FEATURES],
    "output_schema": [{"name": "p_review", "dtype": "float"}],
}

CONTRACT = {
    "assumptions": [{"key": "postcode_deprivation", "minimum": 1, "maximum": 10},
                    {"key": "hours_claimed_weekly", "minimum": 0, "maximum": 80}],
    "guarantees": [{"key": "auc", "minimum": 0.60}],
    "on_boundary_violation": "reject",
}


def main() -> int:
    args = parse("Case study 15 — a benefit risk model that used nationality")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 15 — The column the register could see "
              "and could not act on")

    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------- 1. the arithmetic
    say.step("Score two cohorts that differ in one thing the model may not use")
    rows = _households()
    with_all = _selection_rates(rows)
    say.engine(f"selected for review — single nationality: "
               f"{100*with_all['single nationality']:.1f}%")
    say.engine(f"selected for review — second nationality: "
               f"{100*with_all['second nationality']:.1f}%")
    say.engine(f"disparate selection ratio {with_all['ratio']:.2f}x")
    say.note("this is the failure the Data Protection Authority found: "
             "nationality was an indicator, and the people it selected were "
             "then met by a recovery policy that treated an error as fraud")

    # ------------------------------------------- 2. deleting the column
    say.step("Delete the nationality column and score again")
    without = _selection_rates(rows, drop=("second_nationality",))
    say.engine(f"single nationality: {100*without['single nationality']:.1f}%")
    say.engine(f"second nationality: {100*without['second nationality']:.1f}%")
    say.engine(f"disparate selection ratio {without['ratio']:.2f}x "
               f"— down from {with_all['ratio']:.2f}x, and not gone")
    say.note(f"removing the protected column removed "
             f"{_removed_share(with_all, without):.0f}% of "
             f"the disparity and left the rest, because postcode carries it. "
             f"That is why MAYA records a PROXY as a fact of its own: a model "
             f"built on one discriminates with no column saying so")

    # ------------------------------------------------------- 3. features
    say.step("Register the features — and say what each of them is")
    for name, protected, proxy, pii, _beta, _centre, what in FEATURES:
        attempt(f"{name}"
                + (" [protected]" if protected else "")
                + (f" [proxy:{proxy}]" if proxy != "none" else ""),
                lambda n=name, p=protected, x=proxy, i=pii, w=what:
                maya.features.define(
                    name=n, entity=ENTITY, dtype="numeric", description=w,
                    owner="person/a.mehta", source_system="benefits intake",
                    sensitivity="restricted" if p or i else "internal",
                    pii=i, protected_basis=p, proxy_risk=x))
    say.did("two flags carry this whole case study: `protected_basis` on "
            "nationality, and `proxy_risk` on postcode. The second is the "
            "harder one and the reason the platform keeps it separate")

    say.step("Load the claims and declare the featureset")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=[n for n, *_ in FEATURES],
        description="attributes read by the childcare benefit selection model"))
    load_once(maya, VIEW, rows)
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={n: "numeric" for n, *_ in FEATURES},
        description="the attributes the selection model reads"))
    ensure_filled(maya, FEATURESET, {n: n for n, *_ in FEATURES})

    # ---------------------------------------------------------- 4. model
    say.step("Register the model and bind what it reads")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Childcare benefit selection model",
        model_class="benefits.fraud.selection", domain="benefits",
        owner="person/j.okafor", legal_entity="LE-NL-01",
        purpose="selecting childcare benefit claims for manual review"))
    version = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL,
                             contract=CONTRACT)
    attempt("the feature contract",
            lambda: maya.contracts.bind(model_version_id=version["id"],
                                        items=[{"view": VIEW, "version": 1}]),
            already="already bound")
    say.did("the contract is what makes the next question answerable. Without "
            "it the register holds a model and a catalogue and no link between "
            "them")

    # --------------------------------------------- 5. question 1: does it know
    say.step("QUESTION 1 — does the register know what this model reads?")
    screening = maya.call("GET", "/contract-screening/version",
                          params={"urn": URN, "semver": SEMVER})
    facts = screening.get("facts") or screening
    say.maya(f"binds_protected_basis = {facts.get('binds_protected_basis')}")
    say.maya(f"binds_proxy_risk      = {facts.get('binds_proxy_risk')}")
    say.maya(f"binds_pii             = {facts.get('binds_pii')}")
    say.maya(f"lowest_certification  = {facts.get('lowest_certification')}")
    say.did(str(screening.get("detail", ""))[:400])
    say.note("computed by walking the contract to the PINNED view version, not "
             "declared by anybody. A model cannot be described as not reading "
             "a column it reads")

    # ------------------------------- 6. question 2: does anything refuse
    say.step("QUESTION 2 — does anything refuse on it?")
    estate = maya.call("GET", "/contract-screening/estate")
    say.maya(str(estate.get("detail", ""))[:500])
    enforced = estate.get("enforced_by") or {}
    say.maya(f"rules in force reading these facts: {enforced or 'none'}")
    say.note("THIS is the uncomfortable answer, and it is the point of running "
             "somebody else's failure. MAYA publishes the facts at the "
             "approval and alias-move gates and does not write the rule. A "
             "platform that refused on `protected_basis` alone would refuse "
             "the fairness testing the same regulation requires — so the "
             "estate view reports whether a rule exists, which is the part a "
             "vocabulary-and-nothing-else would leave out")

    # ------------------------------------------ 7. question 4: the depth
    say.step("QUESTION 4 — what control depth does this model owe?")
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=0, purpose_class="policy_decision",
        feature_count=len(FEATURES), uses_alternative_data=False,
        interpretable=True), already="already tiered")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Selection model for childcare benefit review. The binding "
                  "of nationality and of a high-risk proxy was the substance "
                  "of the review.")
    say.maya(f"risk tier {tier} — from what the model is used FOR, not from "
             f"how much money is attached to it")
    say.note("a model that decides nothing but WHO GETS LOOKED AT still "
             "decides a household's income, because of what the looking led "
             "to. The tier follows the purpose class and the purpose class is "
             "a sourced fact, not the requester's word for it")
    if tier is not None and tier > 1:
        say.note(f"AND THIS IS THE THING THE SCRIPT DID NOT EXPECT. The "
                 f"purpose class is the highest MAYA has — `policy_decision` "
                 f"— and the model still tiers at {tier}, because the other "
                 f"axis of the lattice is EXPOSURE and exposure here is "
                 f"denominated in money. This model's exposure is twenty-six "
                 f"thousand households. MAYA's tiering was built for an "
                 f"estate where consequence is measured in currency, and a "
                 f"model that ruins people without moving a balance sheet "
                 f"sits below a mid-sized pricing model. That is a real "
                 f"limitation of the platform, found by running somebody "
                 f"else's failure, and it is in the README rather than "
                 f"quietly absent from it")

    put_record_in_force(maya, people, urn=URN,
                        note="Benefit selection model, owned by the benefits "
                             "directorate.")

    # -------------------------------------- 8. question 5: which version runs
    say.step("QUESTION 5 — is the version that runs the version approved?")
    attempt("the production alias", lambda: people["s.iqbal"].versions.promote(
        URN, semver=SEMVER, environment="prod", alias="champion"),
        already="already promoted")
    say.maya("the alias names one approved version, and a self-learning model "
             "is exactly where that matters: a model that updates itself in "
             "production is a model whose running parameters were approved by "
             "nobody")
    refusal = expect_refusal(
        "move the alias to a version that does not exist",
        lambda: people["s.iqbal"].versions.promote(
            URN, semver="9.9.9", environment="prod", alias="champion"))
    if refusal is not None:
        say.maya(f"refused: {refusal.code}")

    # ---------------------------------------- 9. what it does not reach
    say.step("QUESTION 7 — was the household treated fairly?")
    say.note("MAYA cannot see this, and section 9 of the README lists the "
             "rest. The recovery policy that turned a selection into a debt "
             "was not a model. The blacklist was a list. Whether anybody read "
             "the finding is a management act. Most of the harm in this "
             "failure is outside what any register holds")

    # ------------------------------------------------------------- output
    say.step("Write the case document")
    summary = {
        "case": 15,
        "subject": "childcare benefit selection model (reconstruction)",
        "with_nationality": with_all,
        "without_nationality": without,
        "review_capacity": CAPACITY,
        "screening": facts,
        "rules_in_force_on_these_facts": enforced,
        "tier": tier,
        "tier_limitation": (
            "the purpose class is the highest the platform has and the model "
            "still tiers below 1, because the second axis of the lattice is "
            "exposure denominated in money. Harm to households is not a "
            "currency amount and MAYA has nowhere to put it"),
        "not_reached": NOT_REACHED,
    }
    save_json(out / "case-15-summary.json", summary,
              what="the reconstruction's numbers")
    document(
        path=out / "benefit-risk-scoring.tex",
        title="A benefit risk model that used nationality",
        subtitle="MAYA case study 15 — reconstructed from the public record",
        blocks=[
            r"\section*{What this reconstructs}",
            latex_escape(
                "The Dutch childcare benefits affair. A self-learning risk "
                "classification model selected childcare benefit claims for "
                "manual review and nationality was among its indicators. "
                "Roughly 26,000 families were wrongly treated as fraudulent. "
                "The numbers below are a reconstruction; no applicant data is "
                "used."),
            r"\section*{The mechanism}",
            table([["with nationality",
                    f"{100*with_all['single nationality']:.1f}\\%",
                    f"{100*with_all['second nationality']:.1f}\\%",
                    f"{with_all['ratio']:.2f}"],
                   ["column deleted",
                    f"{100*without['single nationality']:.1f}\\%",
                    f"{100*without['second nationality']:.1f}\\%",
                    f"{without['ratio']:.2f}"]],
                  header=["model", "single nationality", "second nationality",
                          "ratio"], spec="lrrr"),
            latex_escape(
                "Deleting the protected column reduces the disparity and does "
                "not remove it, because the postcode feature carries the same "
                "signal. That is why MAYA records a proxy as a fact of its "
                "own."),
            r"\section*{What MAYA answered}",
            table([[latex_escape(k), latex_escape(str(v))]
                   for k, v in sorted(facts.items())],
                  header=["fact", "value"], spec="ll"),
            r"\section*{What MAYA does not reach}",
            "\n\n".join(latex_escape(f"— {line}") for line in NOT_REACHED),
        ])
    say.maya("benefit-risk-scoring.tex and case-15-summary.json")
    print()
    return 0


#: The section a demonstration usually omits, and the reason to run somebody
#: else's failure rather than one's own.
NOT_REACHED: Tuple[str, ...] = (
    "The recovery policy. The harm was not mainly that claims were selected — "
    "it was that selection met an all-or-nothing repayment rule that treated "
    "an administrative error as fraud. That rule was policy, not a model, and "
    "a model register does not hold it.",
    "The blacklist. A separate fraud signalling facility held names. A list "
    "is not a model, nothing in a model register makes anybody register one, "
    "and `core/discovery/` produces CANDIDATES that somebody still has to act "
    "on.",
    "Whether anybody read the finding. MAYA can put a fact on a screen, a "
    "worklist and an evidence chain. It cannot make an institution look at "
    "it, and this platform's own documentation says a control nobody reads is "
    "not a control.",
    "The absence of an impact assessment. MAYA records that one is required "
    "and holds the document if somebody compiles it. It is not a data "
    "protection impact assessment and does not write one.",
    "The harm. Twenty-six thousand families, children removed from homes, and "
    "years of recovery proceedings are not a governance artefact. Nothing in "
    "this file should be read as suggesting that a register would have "
    "prevented them.",
)


if __name__ == "__main__":
    raise SystemExit(main())
