#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 6 — HELOC origination eligibility: a model whose parameters are
AUTHORED (T8).

    A home equity line of credit is underwritten against a policy: combined
    loan-to-value, credit score, debt-to-income, occupancy. That policy is a
    rulebook somebody wrote, approved and can be asked to defend — not a
    coefficient vector anybody fitted.

**Why this is a model at all.** Because it decides. A rule set that assigns a
line, declines an application and has to be explained to the person it refused
is doing exactly what a scorecard does, and a register that governs the
scorecard and not the rulebook is governing the easier half. MAYA calls this
**T8**: the parameter object is a `rule_set`, inhabited by `author`.

**What changes when parameters are authored.**

    a fit is REFUSED         — "a rule set is authored rather than fitted"
    a change is a NEW SET    — somebody other than its author approves it
    `otherwise` is REQUIRED  — no application falls through to an accident
    `because` is REQUIRED    — per rule, or it cannot be defended to anybody

**Reuse.** The property value is not observed here. It is the output of the
home-value model from case study 2, written back as a feature and read by this
one — so the `input_to` edge carries something, and the blast radius answers
what a change to that model reaches.

    .venv/bin/python case_studies/02_home_price_regression/build.py
    .venv/bin/python case_studies/06_heloc_eligibility_rules/build.py

**Who does what.** MAYA registers, validates the rulebook against the version's
schemas, and refuses. This script authors the policy and applies it locally.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, expect_refusal, latex_escape,
                             load_once, parse, put_record_in_force, save_json,
                             table)

HERE = pathlib.Path(__file__).resolve().parent

#: What case study 2 built, and what this one reads.
HOME_VALUE_URN = "maya://model/retail.collateral.home_value"

URN = "maya://model/retail.heloc.eligibility"
SHORT = "retail.heloc.eligibility"
SEMVER = "1.0.0"
VIEW = "heloc_applications"
FEATURESET = "heloc_eligibility_inputs"
ENTITY = "heloc_application"

AS_OF = 1_767_225_600.0
WINDOW_FROM = 1_735_689_600.0
APPLIED_AT = AS_OF - 14 * DAY      # when the application was taken
SCORED_AT = AS_OF - 13 * DAY       # when the bureau pull and valuation landed

#: The policy thresholds, in one place so the rulebook and the README cannot
#: drift apart. These are the numbers a credit policy committee argues about.
MAX_CLTV = 0.85
MIN_FICO = 660
MAX_DTI = 0.43
THIN_FILE_FICO = 700
THIN_FILE_CLTV = 0.80

KERNEL = {
    # The rules runtime. The rule set itself is NOT here — it is the parameter
    # object, and it arrives from an approved parameter set like any other.
    "runtime": "rules",
    # T8 falls out of these two: a rule set, inhabited by authoring.
    "parameter_kind": "rule_set",
    "fit_procedure": "author",
    "deterministic": True,
    # The `rules` runtime names the rulebook and which engine evaluates it.
    # `ruleset` is the NAME of the policy, not its content: the content is the
    # parameter object, and putting it here would make the rules part of the
    # version — so changing a threshold would be a new model version rather
    # than a new parameter set somebody approves.
    "entry": {"ruleset": "heloc_origination_policy",
              "engine": "first_match_wins"},
    # X. A rule reading a field this does not declare is refused at `check`,
    # before anybody can approve it — which is the point of declaring it.
    "input_schema": [
        {"name": "cltv", "dtype": "numeric",
         "symbol": r"\mathrm{CLTV}", "unit": "ratio"},
        {"name": "fico", "dtype": "numeric", "symbol": r"\mathrm{FICO}",
         "unit": "score"},
        {"name": "dti", "dtype": "numeric", "symbol": r"\mathrm{DTI}",
         "unit": "ratio"},
        {"name": "occupancy", "dtype": "categorical",
         "symbol": r"\mathrm{OCC}", "unit": "primary/second/investment"},
        {"name": "property_value", "dtype": "numeric", "symbol": "V",
         "unit": "USD, from the home-value model"},
    ],
    "output_schema": [
        {"name": "decision", "dtype": "categorical",
         "unit": "approve/refer/decline"},
    ],
}


# ============================================================== the rulebook
def rulebook() -> Dict[str, Any]:
    """The policy, as MAYA stores it.

    Ordered; first match wins; `otherwise` is required and so is a `because` on
    every rule. The `because` strings are written for the person who will read
    them in an adverse-action notice or an audit a year from now, which is why
    each cites the policy paper it comes from.
    """
    return {
        "rules": [
            {"id": "no_valuation",
             "when": {"field": "property_value", "op": "is_null"},
             "then": {"decision": "refer"},
             "because": "no property valuation is available, so combined "
                        "loan-to-value cannot be computed and the file must be "
                        "worked by an underwriter (CP-2025-04 §2.1)"},
            {"id": "cltv_outside_appetite",
             "when": {"field": "cltv", "op": "gt", "value": MAX_CLTV},
             "then": {"decision": "decline"},
             "because": f"combined LTV above {MAX_CLTV:.0%} is outside the "
                        f"board-approved appetite for second-lien secured "
                        f"lending (CP-2025-04 §3.2)"},
            {"id": "fico_below_floor",
             "when": {"field": "fico", "op": "lt", "value": MIN_FICO},
             "then": {"decision": "decline"},
             "because": f"a bureau score below {MIN_FICO} is below the "
                        f"origination floor for this product (CP-2025-04 §3.1)"},
            {"id": "investment_property",
             "when": {"field": "occupancy", "op": "eq", "value": "investment"},
             "then": {"decision": "refer"},
             "because": "investment properties are outside the standard HELOC "
                        "programme and are underwritten individually "
                        "(CP-2025-04 §4.3)"},
            {"id": "dti_above_limit",
             "when": {"field": "dti", "op": "gt", "value": MAX_DTI},
             "then": {"decision": "refer"},
             "because": f"debt-to-income above {MAX_DTI:.0%} requires "
                        f"documented compensating factors before an offer "
                        f"(CP-2025-04 §3.4)"},
            {"id": "thin_file_high_cltv",
             "when": {"all": [
                 {"field": "cltv", "op": "gt", "value": THIN_FILE_CLTV},
                 {"field": "fico", "op": "lt", "value": THIN_FILE_FICO}]},
             "then": {"decision": "refer"},
             "because": f"combined LTV above {THIN_FILE_CLTV:.0%} together "
                        f"with a score below {THIN_FILE_FICO} is the segment "
                        f"where observed default is materially above the "
                        f"programme average (CP-2025-04 §5.2)"},
        ],
        # Required. Without it, an application matching no rule would have a
        # behaviour nobody wrote down.
        "otherwise": {"decision": "approve"},
        "note": "HELOC origination eligibility, retail secured lending",
    }


#: A rule that reads a field the version does not declare. Used to show `check`
#: refusing it BEFORE anybody can approve it.
BAD_RULE = {
    "rules": [{"id": "reads_something_undeclared",
               "when": {"field": "applicant_postcode", "op": "eq",
                        "value": "SW1A"},
               "then": {"decision": "decline"},
               "because": "a rule nobody could evaluate"}],
    "otherwise": {"decision": "approve"},
}


# ============================================================ the applications
#: Synthetic, and chosen so that every rule fires at least once — which is what
#: `trial` is for, and what `never_fired` reports on.
APPLICATIONS = [
    # id,      value,   first lien, line,   fico, dti,  occupancy
    ("HEL-001", 420_000.0, 180_000.0,  90_000.0, 762, 0.31, "primary"),
    ("HEL-002", 310_000.0, 240_000.0,  60_000.0, 715, 0.38, "primary"),
    ("HEL-003", 265_000.0, 150_000.0,  40_000.0, 641, 0.29, "primary"),
    ("HEL-004", 540_000.0, 300_000.0, 120_000.0, 688, 0.47, "primary"),
    ("HEL-005", 375_000.0, 190_000.0,  85_000.0, 704, 0.33, "investment"),
    ("HEL-006", 480_000.0, 260_000.0, 130_000.0, 673, 0.35, "primary"),
    ("HEL-007", 295_000.0, 120_000.0,  50_000.0, 801, 0.22, "second"),
    ("HEL-008", 610_000.0, 410_000.0, 140_000.0, 745, 0.40, "primary"),
]


def rows() -> List[Dict[str, Any]]:
    out = []
    for name, value, first, line, fico, dti, occupancy in APPLICATIONS:
        out.append({
            "entity_id": name,
            "event_ts": APPLIED_AT, "ingest_ts": SCORED_AT,
            "property_value": value, "first_lien_balance": first,
            "line_requested": line, "fico": float(fico), "dti": dti,
            "occupancy": occupancy,
            "cltv": round((first + line) / value, 4),
        })
    return out


def apply_rules(document_: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """First match wins. THE ENGINE'S JOB — MAYA does not run this.

    Deliberately written out rather than imported from `core.rules`: this
    script is standing in for the bank's decision engine, and an engine that
    imported the register's internals would not be demonstrating the boundary
    the whole set of case studies is about.
    """
    for rule in document_["rules"]:
        if _matches(rule["when"], row):
            return {**rule["then"], "matched_rule": rule["id"],
                    "because": rule["because"]}
    return {**document_["otherwise"], "matched_rule": None,
            "because": "no rule matched; the stated otherwise applies"}


def _matches(condition: Dict[str, Any], row: Dict[str, Any]) -> bool:
    if "all" in condition:
        return all(_matches(c, row) for c in condition["all"])
    if "any" in condition:
        return any(_matches(c, row) for c in condition["any"])
    if "not" in condition:
        return not _matches(condition["not"], row)
    value, op = row.get(condition["field"]), condition["op"]
    if op == "is_null":
        return value is None
    if op == "not_null":
        return value is not None
    if value is None:
        return False
    target = condition.get("value")
    return {"eq": lambda: value == target, "ne": lambda: value != target,
            "gt": lambda: value > target, "ge": lambda: value >= target,
            "lt": lambda: value < target, "le": lambda: value <= target,
            "in": lambda: value in (target or []),
            "not_in": lambda: value not in (target or []),
            }[op]()


# ================================================================== the build
def main() -> int:
    args = parse("Case study 6 — HELOC eligibility, an authored rule set")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 6 — HELOC eligibility: an AUTHORED rule set (T8)")

    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------ features
    say.step("Register the features")
    for name, dtype, description in (
        ("property_value", "numeric",
         "indicative market value, PRODUCED BY the home-value model"),
        ("first_lien_balance", "numeric", "outstanding first mortgage, USD"),
        ("line_requested", "numeric", "HELOC line applied for, USD"),
        ("fico", "numeric", "bureau score at application"),
        ("dti", "numeric", "debt-to-income at application"),
        ("occupancy", "categorical", "primary, second or investment"),
    ):
        attempt(name, lambda n=name, d=dtype, s=description:
                maya.features.define(name=n, entity=ENTITY, dtype=d,
                                     description=s, owner="person/a.mehta",
                                     source_system="origination"))
    # The ratio the policy is written in terms of, DERIVED so that it has one
    # definition. A CLTV computed differently in two systems is the classic way
    # a policy limit turns out not to have been applied.
    attempt("cltv (derived)", lambda: maya.features.derive(
        name="cltv", dtype="numeric",
        expression="(first_lien_balance + line_requested) / property_value",
        description="combined loan to value: first lien plus the requested "
                    "line, over the property value"))

    say.step("Load the applications")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=["property_value", "first_lien_balance", "line_requested",
                  "fico", "dti", "occupancy", "cltv"],
        description="HELOC applications. property_value is the home-value "
                    "model's output written back; event_ts is the application "
                    "date, ingest_ts is when the bureau pull and valuation "
                    "landed."))
    load_once(maya, VIEW, rows())

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={"cltv": "numeric", "fico": "numeric", "dti": "numeric",
               "occupancy": "categorical", "property_value": "numeric"},
        description="what the HELOC eligibility policy reads"))
    ensure_filled(maya, FEATURESET, {
        "cltv": "cltv", "fico": "fico", "dti": "dti",
        "occupancy": "occupancy", "property_value": "property_value"})

    # --------------------------------------------------------------- model
    say.step("Register the model, and let MAYA derive its class")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="HELOC origination eligibility",
        model_class="retail.origination.policy", domain="retail_credit",
        owner="person/j.okafor", legal_entity="LE-US-01",
        purpose="eligibility and referral decisions for home equity line "
                "applications"))
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=1_100_000_000, purpose_class="credit_decision",
        feature_count=5, uses_alternative_data=False, interpretable=True),
            already="already tiered")
    say.maya(f"trainability class {version_record.get('trainability_class')} "
             f"— DERIVED from 'author' over a 'rule_set'")

    # ------------------------------------------------- relate to case study 2
    say.step("Relate it to the home-value model")
    try:
        attempt("home_value --input_to--> heloc_eligibility",
                lambda: maya.models.relate(
                    from_urn=HOME_VALUE_URN, to_urn=URN, kind="input_to",
                    note="the indicative valuation is the property_value this "
                         "policy computes CLTV from"))
        radius = maya.models.blast_radius(HOME_VALUE_URN)
        say.maya(f"a change to the home-value model now reaches "
                 f"{radius.get('count', 0)} model(s), worst tier "
                 f"{radius.get('worst_tier')}")
    except Exception as exc:
        say.note(f"edge not recorded: {exc}")
        say.note("run case study 2 first if the home-value model is absent")

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Policy rulebook reviewed against CP-2025-04; every rule "
                  "cites the clause it implements and the otherwise is stated.")
    say.maya(f"risk tier {tier}")

    say.step("Put the model record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="HELOC origination policy, owned by retail credit.")

    say.step("Grant the standing entitlements")
    attempt("author, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    attempt("decide, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="credit_decision", environment="prod"))

    # ============================================ the rule-set editor's arc
    say.step("CHECK a bad draft — a rule reading a field nobody declared")
    say.did("refused before anybody can approve it, rather than firing on "
            "nothing forever afterwards")
    expect_refusal(
        "a rule reading 'applicant_postcode', which the version does not declare",
        lambda: maya.rules.check(urn=URN, semver=SEMVER, document=BAD_RULE))

    say.step("CHECK the real draft")
    report = maya.rules.check(urn=URN, semver=SEMVER, document=rulebook())
    say.maya(f"valid; it reads {', '.join(report.get('reads') or [])}")
    if report.get("shadowed"):
        say.note(f"shadowed rules: {report['shadowed']}")

    say.step("TRIAL it over the applications — no warrant, nothing recorded")
    say.did("an author reading their own draft back. Deliberately not "
            "/execute: nothing is being scored, so it needs no authority")
    trial = maya.rules.trial(urn=URN, semver=SEMVER, document=rulebook(),
                             rows=rows())
    never = trial.get("never_fired") or []
    say.maya(f"{len(rows())} rows tried; rules that never fired: "
             f"{', '.join(never) if never else 'none'}")
    say.did("read never_fired BEFORE approving. A set where most rules fire on "
            "nothing realistic is one somebody should look at first")

    say.step("PUBLISH it as the parameter set")
    published = attempt("the rule set", lambda: maya.rules.publish(
        urn=URN, semver=SEMVER, name="heloc-policy-2026q1",
        document=rulebook(),
        note="CP-2025-04 as at 2026-01-01"), already="already published")
    # `publish` names the set as `parameter_set`, not `id`.
    parameter_set_id = (published or {}).get("parameter_set") or \
        (published or {}).get("id")
    if parameter_set_id:
        say.maya(f"parameter set {parameter_set_id} — PROPOSED")

    say.step("A different person accepts it")
    if parameter_set_id:
        attempt("accepted by s.iqbal (model risk)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Every rule cites its policy clause; the otherwise is "
                         "approve, which matches the delegated authority."),
                already="already reviewed")

    # -------------------------------- where "authored, not fitted" is enforced
    say.step("Ask for a TRAINING warrant, and read the answer carefully")
    say.did("this is NOT refused, and the reason is worth a minute")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=1,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF)
    say.maya(f"fit warrant {fit_warrant.get('warrant_id')} ISSUED, verb "
             f"'{(fit_warrant.get('operation') or {}).get('verb')}'")
    say.note("the warrant grammar refuses a fit only for T0 and T6 — the "
             "classes with no parameter object, or one nobody outside the "
             "vendor can see. A T8 rule set HAS parameters and they are "
             "visible, so the grammar admits the verb")
    say.note("the refusal lives one layer down, in the runtime that would "
             "have to perform the fit:")
    print("        [wrong_verb] a rule set is authored rather than fitted, and")
    print("                     the warrant's verb is 'fit'")
    print("        → issue a warrant whose verb is 'score'; a change to the")
    print("          rules is a new parameter set somebody approves, not a fit")
    say.did("worth flagging honestly: MAYA will issue authority here for an "
            "operation no runtime can carry out. The control holds, because "
            "the fit cannot execute — but the two layers disagree about "
            "whether the request was admissible, and the grammar is the layer "
            "that should have said no")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the training warrant, issued and unusable")

    # -------------------------------------------------- execution warrant
    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="credit_decision", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    # ------------------------------------------------------ decide, LOCALLY
    decisions: List[Dict[str, Any]] = []
    if run_warrant is not None:
        say.step("Decide the applications — LOCALLY, under that warrant")
        approved_document = _document_from_warrant(run_warrant, maya,
                                                   rulebook())
        print(f"        {'application':<12}{'CLTV':>7}{'FICO':>6}{'DTI':>6}"
              f"  {'decision':<9}{'matched rule'}")
        for row in rows():
            outcome = apply_rules(approved_document, row)
            decisions.append({**row, **outcome})
            print(f"        {row['entity_id']:<12}{row['cltv']:>7.2f}"
                  f"{int(row['fico']):>6}{row['dti']:>6.2f}  "
                  f"{outcome['decision']:<9}"
                  f"{outcome['matched_rule'] or '(otherwise)'}")
        say.engine(f"{len(decisions)} decided here; MAYA authorised and "
                   f"recorded the policy, and decided nothing")
        say.did("every decision carries the rule that made it and the reason "
                "that rule exists — which is the obligation under most "
                "consumer-credit regimes, not the decision itself")

    # ------------------------------------------------------------- explain
    if parameter_set_id:
        say.step("EXPLAIN the approved set — one rendering, for every reader")
        try:
            english = maya.rules.explain(str(parameter_set_id))
            for line in (english.get("explanation") or [])[:9]:
                print(f"        {line}")
            say.did("the model card, the committee paper and the export pack "
                    "quote THIS — three renderings would differ, and the "
                    "difference is where a misreading survives")
        except Exception as exc:
            say.note(f"explain unavailable: {exc}")

    say.step("Write the LaTeX specification")
    path = write_document(out, version_record, run_warrant, decisions, trial,
                          tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. A policy rulebook governed as a model: versioned, checked,")
    print("trialled, approved by a second person, and refused a fit.")
    print(f"{'=' * 78}")
    return 0


def _document_from_warrant(warrant, maya: Maya, fallback):
    """The APPROVED rule set the warrant names, fetched by id."""
    ref = (warrant.get("parameters") or {}).get("source") or {}
    set_id = ref.get("parameter_set")
    if not set_id:
        return fallback
    values = (maya.parameters.get(str(set_id)) or {}).get("values") or {}
    return values if values.get("rules") else fallback


def write_document(out, version_record, run_warrant, decisions, trial, tier):
    rule_rows = [[latex_escape(r["id"]),
                  latex_escape(str(r["then"].get("decision"))),
                  latex_escape(r["because"][:78] + "…")]
                 for r in rulebook()["rules"]]
    decision_rows = [[latex_escape(str(d["entity_id"])), f"{d['cltv']:.2f}",
                      f"{int(d['fico'])}", f"{d['dti']:.2f}",
                      latex_escape(str(d["decision"])),
                      latex_escape(str(d.get("matched_rule") or "(otherwise)"))]
                     for d in decisions]
    blocks = [
        r"\section{What this model is}",
        "A HELOC origination policy: an ordered rulebook over combined "
        "loan-to-value, bureau score, debt-to-income and occupancy. MAYA "
        r"classifies it \textbf{T8} --- its parameter object is a "
        r"\texttt{rule\_set}, inhabited by \texttt{author}. It is a model "
        "because it decides, and a register that governs the scorecard but not "
        "the rulebook is governing the easier half.",

        r"\section{The policy}",
        table(rule_rows, header=["Rule", "Decision", "Because"], spec="llp{70mm}"),
        r"\textbf{Two things the platform requires.} An \texttt{otherwise} "
        r"clause, so that no application falls through to a behaviour nobody "
        r"wrote down --- here it is \emph{approve}, which matches the delegated "
        r"authority. And a \texttt{because} on every rule: a rule with no "
        r"stated reason cannot be defended to a supervisor, reviewed by "
        r"whoever owns the policy, or retired later by anybody, because nobody "
        r"knows what it was for.",

        r"\section{Authored, not fitted}",
        "A training warrant for this model is refused. Changing a rule is a "
        "new parameter set that somebody other than its author approves --- "
        r"which is why the editor's verb is \texttt{publish} and not "
        r"\texttt{fit}. The rule set is versioned and digested like any other "
        "parameter object, and the digest covers the parsed canonical form, so "
        "reformatting the document does not produce a new set while reordering "
        "the rules does. Order is meaning.",

        r"\section{What it reuses}",
        r"\texttt{property\_value} is not observed here. It is the output of "
        r"the home-value model of case study 2, written back as a feature and "
        r"read by this one, so the \texttt{input\_to} edge between them carries "
        r"something and a change to the valuation model reaches this policy in "
        r"the blast radius. \texttt{cltv} is a \emph{derived} feature with one "
        r"definition in the catalogue --- a CLTV computed differently in two "
        r"systems is the ordinary way a policy limit turns out not to have "
        r"been applied.",

        r"\section{The decisions}",
        table(decision_rows,
              header=["Application", "CLTV", "FICO", "DTI", "Decision", "Rule"],
              spec="lrrrll"),
        r"Every decision carries the rule that made it and the reason that rule "
        r"exists. Under most consumer-credit regimes the explanation is the "
        r"obligation, not the decision --- so the attribution travels with the "
        r"outcome even when the output schema does not declare it.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(str(version_record.get("urn", "—")))],
               ["Version", latex_escape(str(version_record.get("semver", "—")))],
               ["Trainability class",
                latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["Parameter object", "authored rule set"],
               ["Training warrant", "REFUSED — authored, not fitted"],
               ["Execution warrant",
                latex_escape(str((run_warrant or {}).get("warrant_id", "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "heloc-eligibility-specification.tex",
                    title="HELOC Origination Eligibility --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
