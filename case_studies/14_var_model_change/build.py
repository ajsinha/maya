#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 14 — A VaR model swapped mid-crisis: the one case study in this
suite that was NOT designed to fit MAYA (T2).

    VaR_99,1d  =  quantile_1%( sum_i  w_i * r_i )     r from a historical window

**Every other case study here was designed by the author of the platform.** That
is the weakness the accompanying research paper names as its principal missing
evidence: a demonstration built by the person who built the thing it
demonstrates shows sufficiency and not much else.

So this one is taken from the public record instead. It reconstructs the model
governance failure at the centre of the 2012 JPMorgan Chief Investment Office
losses --- the "London Whale" --- as documented by the firm's own Management
Task Force report and the US Senate Permanent Subcommittee on Investigations.
The sequence is theirs. The controls it walks into are MAYA's. Nothing about
the shape of the failure was chosen to make the platform look good, and
**§2 of this file lists the parts MAYA would not have caught**, which is
the half a demonstration usually omits.

**What actually happened, in the order it happened.** A synthetic credit
portfolio breached its VaR limit in January 2012. A new VaR model was already
in development. The new model was put into production days later; reported VaR
fell by roughly half and the breach disappeared. The model had been approved by
the firm's model review group subject to further work that was not completed.
It was implemented as a chain of spreadsheets with manual copy-and-paste
between them, and one of those spreadsheets divided by the *sum* of two rates
where it should have divided by their *average*, understating volatility. The
portfolio lost about $6.2bn. Regulators subsequently required remediation under
consent orders with dates the firm committed to.

**Six governance questions, and MAYA answers five.**

  1. Is replacing a VaR model a material change?  --  computed, not asked.
  2. May the production alias move to the new version without revalidation?
     --  refused.
  3. Does swapping the model close the breach the old model reported?
     --  no, and the finding survives the swap. This is the sharpest one.
  4. Does an approval "subject to further work" bind anything?
     --  it does, and it expires.
  5. Does a spreadsheet reimplementation agree with the model it reimplements?
     --  answerable, by a recode harness, if somebody runs it.
  6. Is the arithmetic inside the spreadsheet right?
     --  **MAYA cannot see this and does not claim to.**

**And a seventh the script did not plan for.** MAYA refuses to add a version to
an attested model at all: the replacement cannot appear beside the incumbent
without somebody opening an *amendment*, which is an act with a name on it and
a stated scope. That refusal was not in the design of this case study --- it
happened while it was being written, and it is a stronger control than the one
this file set out to demonstrate.

**The numbers.** The qualitative sequence is from the public reports and is
cited in the README. The specific figures in this script are a *reconstruction*
sized to be realistic and are not the firm's data --- MAYA is being shown a
shape of failure, not audited against a balance sheet. The reconstruction
produces a 52% fall in reported VaR on the same book on the same day, which is
about the halving the public reports describe.

**Who does what.** MAYA registers, classifies the change, refuses the promotion,
holds the finding open and records the supervisory matter. Every number is
computed in this file, in numpy, outside the register.
"""
from __future__ import annotations

import math
import pathlib
import sys
import time
from typing import Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, equation, expect_refusal,
                             load_once, parse,
                             put_record_in_force, save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/market.var.synthetic_credit"
SHORT = "market.var.synthetic_credit"
INCUMBENT = "1.0.0"          # the model that reported the breach
REPLACEMENT = "2.0.0"        # the model that made it disappear
VIEW = "scp_position_returns"
FEATURESET = "scp_var_inputs"
ENTITY = "portfolio"

AS_OF = 1_767_225_600.0
WINDOW_FROM = 1_735_689_600.0

#: The synthetic credit positions, reconstructed. Weights are notional shares
#: of the portfolio and the daily return series below is generated from them.
POSITIONS: List[Tuple[str, str, float, float]] = [
    ("cdx_ig9_10y",  "investment grade index, 10 year",  0.34, 0.0042),
    ("cdx_ig9_5y",   "investment grade index, 5 year",  -0.28, 0.0038),
    ("cdx_hy_5y",    "high yield index, 5 year",         0.19, 0.0091),
    ("itx_main_5y",  "European main index, 5 year",      0.12, 0.0047),
    ("itx_xo_5y",    "European crossover, 5 year",       0.07, 0.0104),
]

#: 260 observation days. Deterministic — a case study whose numbers move
#: between runs is one nobody can check twice.
LOOKBACK = 260


def _returns() -> Dict[str, List[float]]:
    """A deterministic return series per position. No randomness anywhere."""
    out: Dict[str, List[float]] = {}
    for index, (name, _label, _w, sigma) in enumerate(POSITIONS):
        series = []
        for day in range(LOOKBACK):
            # A fixed oscillation with a fat left tail in the last quarter,
            # which is the shape a credit index actually made in early 2012.
            base = math.sin((day + index * 17) * 0.31) * sigma
            # The stress sits in the FIRST half of the window and the recent
            # months are calm. That ordering is the whole mechanism: a model
            # weighting recent observations more heavily reports a smaller
            # number not because it is wrong but because the recent past was
            # quiet — and a quiet recent past is exactly when a limit gets
            # inconvenient.
            stress = -abs(math.sin(day * 0.07)) * sigma * 0.30 \
                if day < LOOKBACK - 130 else 0.0
            series.append(round(base + stress, 8))
        out[name] = series
    return out


def _portfolio(returns: Dict[str, List[float]]) -> List[float]:
    """Weighted portfolio return per day. The engine's arithmetic, not MAYA's."""
    return [round(sum(w * returns[name][day]
                      for name, _l, w, _s in POSITIONS), 8)
            for day in range(LOOKBACK)]


def _var(series: List[float], *, confidence: float = 0.99,
         notional: float = 100_000_000_000.0) -> float:
    """Historical-simulation VaR: the loss quantile of the observed series."""
    ordered = sorted(series)
    index = max(0, math.floor((1.0 - confidence) * len(ordered)) - 1)
    return abs(ordered[index]) * notional


def _var_new_model(series: List[float], *, confidence: float = 0.99,
                   notional: float = 100_000_000_000.0) -> float:
    """The replacement model, which reports roughly half.

    The reduction here comes from a shorter effective lookback --- the
    replacement weighted recent observations more heavily and the recent
    observations were calm. That is a legitimate modelling choice, which is the
    point: **the failure was not that the new model was wrong.** It was that
    the change was made without the revalidation that would have asked why the
    answer halved.
    """
    recent = series[-120:]
    return _var(recent, confidence=confidence, notional=notional)


def _volatility_correct(rate_a: float, rate_b: float) -> float:
    """The volatility term as it should be computed: divided by the AVERAGE."""
    return abs(rate_b - rate_a) / ((rate_a + rate_b) / 2.0)


def _volatility_as_built(rate_a: float, rate_b: float) -> float:
    """The volatility term as the spreadsheet computed it: divided by the SUM.

    This is the operational error the Task Force report identified. It is
    reproduced here for one reason: to show exactly where MAYA's sight ends.
    The register does not run the model and cannot see inside a spreadsheet
    cell. What it CAN do is hold the reimplementation to a standard, which
    §6 does.
    """
    return abs(rate_b - rate_a) / (rate_a + rate_b)


def main() -> int:
    args = parse("Case study 14 — a VaR model swapped mid-crisis")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 14 — The model change that made a breach disappear")

    # ------------------------------------------------- 0. the two answers
    say.step("Two VaR models, one portfolio, one day")
    returns = _returns()
    portfolio = _portfolio(returns)
    var_old = _var(portfolio)
    var_new = _var_new_model(portfolio)
    say.engine(f"incumbent model  VaR(99%, 1d) = ${var_old/1e6:,.1f}m")
    say.engine(f"replacement model VaR(99%, 1d) = ${var_new/1e6:,.1f}m")
    say.engine(f"the reported number falls by {100*(1-var_new/var_old):.0f}% "
               f"on the same positions, on the same day")
    say.note("neither number is wrong. A shorter effective lookback is a "
             "defensible modelling choice, and that is exactly what makes this "
             "case study worth running: the failure was not a bad model, it "
             "was a change nobody was made to justify")

    # Between the two answers, which is the only place a limit
    # is interesting: above it the incumbent breaches, below it
    # the replacement does not, and nothing about the book moved.
    limit = (var_old + var_new) / 2.0
    say.engine(f"the desk's VaR limit is ${limit/1e6:,.1f}m — breached by the "
               f"incumbent, comfortably met by the replacement")

    # ------------------------------------------------------- 1. the cast
    say.step("Make sure the people exist")
    maya = connect(args)
    people = ensure_cast(maya, args.url)
    owner, mrm, validator = people["j.okafor"], people["s.iqbal"], people["v.chen"]

    # ------------------------------------------------ 2. register the model
    say.step("Register the model and its inputs")
    for name, label, _w, _s in POSITIONS:
        attempt(f"feature {name}",
                lambda n=name, la=label: maya.features.define(
                    name=n, entity=ENTITY, dtype="numeric",
                    description=f"daily return, {la}",
                    owner="person/a.mehta",
                    source_system="market data, end of day"))
    attempt("view " + VIEW,
            lambda: maya.features.create_view(
                name=VIEW, entity=ENTITY, owner="person/a.mehta",
                features=[n for n, _l, _w, _s in POSITIONS],
                description="daily position returns for the synthetic credit "
                            "portfolio. event_ts is the trading day; ingest_ts "
                            "is when the mark was struck."))

    # One row per DAY carrying every position, because a VaR reads them
    # together: a row per position would be five entities that have to be
    # joined back into one portfolio, and the join is where a lookback
    # silently becomes ragged.
    rows = [{"entity_id": "SCP", "event_ts": WINDOW_FROM + day * DAY,
             # Marks are struck the same evening, so the two clocks are close
             # here — which is worth noticing rather than glossing: this is one
             # of the few places in the suite where they nearly coincide, and
             # the discipline still applies.
             "ingest_ts": WINDOW_FROM + day * DAY + 0.75 * DAY,
             **{name: returns[name][day] for name, _l, _w, _s in POSITIONS}}
            for day in range(LOOKBACK)]
    loaded = load_once(maya, VIEW, rows)
    say.maya(f"{loaded} bitemporal rows")

    attempt("featureset " + FEATURESET,
            lambda: maya.featuresets.define(
                name=FEATURESET, entity=ENTITY,
                slots={n: "numeric" for n, _l, _w, _s in POSITIONS},
                description="the return series a historical-simulation VaR "
                            "reads"))
    ensure_filled(maya, FEATURESET, {n: n for n, _l, _w, _s in POSITIONS})

    attempt("model " + SHORT,
            lambda: maya.models.register(
                urn=URN, name="Synthetic credit portfolio VaR",
                model_class="market.var.historical_simulation",
                domain="markets", owner="person/j.okafor",
                legal_entity="LE-US-01",
                purpose="one-day 99% value at risk for the synthetic credit "
                        "portfolio, against a desk limit"),
            already="already registered")
    attempt("risk assessment",
            lambda: owner.models.assess(
                SHORT, exposure=100_000_000_000.0,
                purpose_class="risk_management",
                feature_count=len(POSITIONS), uses_alternative_data=False,
                interpretable=True),
            already="already assessed")

    # -------------------------------------------- 3. the incumbent version
    say.step("Register the INCUMBENT VaR model — the one that reported the breach")
    kernel = {
        "parameter_kind": "estimated_coefficients",
        "fit_procedure": "estimate",
        "input_schema": [{"name": n, "dtype": "float"}
                         for n, _l, _w, _s in POSITIONS],
        "output_schema": [{"name": "var_99_1d", "dtype": "float"}],
    }
    contract = {
        "assumptions": [{"key": n, "minimum": -0.25, "maximum": 0.25}
                        for n, _l, _w, _s in POSITIONS],
        "guarantees": [{"key": "lookback_days", "minimum": 250.0}],
        "on_boundary_violation": "reject",
    }
    ensure_version(maya, SHORT, semver=INCUMBENT, kernel=kernel,
                   contract=contract)
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=INCUMBENT,
        statement="historical simulation over a 260-day window; back-tested "
                  "against 2011 exceptions")
    say.maya(f"risk tier {tier}")
    put_record_in_force(maya, people, urn=URN,
                        note="VaR model in force for the synthetic credit book")

    say.step("Grant the entitlements")
    for principal, use in (("service/risk-engine", "limit_monitoring"),
                           ("person/a.mehta", "model_development")):
        # The OWNER issues, not the model risk manager. `warrant:issue` sits
        # with the first line — the second line revokes and never grants, and
        # this script found that out by being refused.
        attempt(f"{principal} — {use}",
                lambda p=principal, u=use: owner.warrants.grant(
                    urn=URN, environment="prod", principal=p,
                    declared_use=u),
                already="already granted")

    # --------------------------------------------- 4. the breach, recorded
    say.step("The incumbent reports a breach — and MAYA turns it into a finding")
    attempt(
        "VaR limit monitor",
        lambda: owner.monitors.define(
            urn=URN, name="VaR against desk limit", kind="score_drift",
            test_key="stability.psi", threshold={"max": 0.25},
            owner="person/j.okafor", cadence_days=1.0,
            breach_severity="High", escalate_after=1),
        already="already defined")
    say.note("a real VaR limit monitor compares a number to a limit; the "
             "monitor kinds this platform admits for a T2 model are "
             "distribution tests, so the breach is registered as a FINDING "
             "directly. That MAYA constrains which questions a class may be "
             "asked is the same control as everywhere else, and it is worth "
             "seeing it bite in a case study rather than reading about it")

    attempt(
        "breach finding",
        lambda: mrm.findings.raise_finding(
            urn=URN, severity="High",
            title="VaR limit breached on the synthetic credit portfolio",
            owner="person/j.okafor",
            description=(
                f"The incumbent model reports VaR of ${var_old/1e6:,.1f}m "
                f"against a limit of ${limit/1e6:,.1f}m. The breach is a fact "
                f"about the PORTFOLIO. Any model change made while it is open "
                f"has to explain itself against it."),
            category="limit_breach", source="monitoring", blocking=True),
        already="already raised")
    say.maya("a BLOCKING finding — which is the whole point of what follows")

    # --------------------------------- 5. the replacement, and the refusals
    say.step("QUESTION 0 — may the replacement even be registered?")
    say.did("this step was not in the plan for this case study. It is here "
            "because the platform refused something the author did not expect "
            "it to refuse, which is the only reason a case study taken from "
            "somebody else's failure is worth more than one designed to fit")
    kernel_new = dict(kernel)
    contract_new = {
        "assumptions": [{"key": n, "minimum": -0.25, "maximum": 0.25}
                        for n, _l, _w, _s in POSITIONS],
        # The guarantee LOOSENS: the new model needs only 120 days.
        "guarantees": [{"key": "lookback_days", "minimum": 120.0}],
        "on_boundary_violation": "reject",
    }
    blocked = expect_refusal(
        "add version 2.0.0 to an attested model",
        lambda: maya.versions.create(SHORT, semver=REPLACEMENT,
                                     kernel=kernel_new,
                                     contract=contract_new))
    if blocked:
        say.did("**an attested record is immutable.** The replacement cannot "
                "simply appear beside the incumbent — somebody has to open an "
                "AMENDMENT, which is an act with a name on it and a stated "
                "scope. In the failure this case study reconstructs, the new "
                "model went into production days after the breach and the "
                "question of what was being amended was never put")

    say.step("So open the amendment, on the record")
    attempt("amendment", lambda: owner.lifecycle.amend(
        SHORT,
        reason="replacing the VaR model for the synthetic credit portfolio "
               "while a limit breach is open against the incumbent",
        scope=["version", "contract", "parameters"]),
        already="already amending")
    ensure_version(maya, SHORT, semver=REPLACEMENT, kernel=kernel_new,
                   contract=contract_new)
    say.maya("version 2.0.0 exists — and the reason it exists is on the chain")

    say.step("QUESTION 1 — is this a material change? MAYA computes it")
    verdict = attempt(
        "classify the change",
        lambda: maya.models.change_classification(
            SHORT, from_semver=INCUMBENT, to_semver=REPLACEMENT))
    if verdict:
        say.maya(f"verdict: {verdict.get('verdict')}")
        for reason in (verdict.get("reasons") or [])[:4]:
            say.note(reason if isinstance(reason, str)
                     else reason.get("why") or str(reason))
        say.did("computed from the two versions rather than asked of the "
                "person proposing the change. That person is looking at a "
                "deadline and has an opinion about how much work revalidation "
                "is, and over a career that opinion drifts one way")

    say.step("QUESTION 2 — may the alias move to it? (no revalidation yet)")
    refused = expect_refusal(
        "promote 2.0.0 to prod/champion",
        lambda: mrm.versions.promote(
            SHORT, semver=REPLACEMENT, environment="prod", alias="champion",
            justification="the replacement reports a smaller number on the "
                          "same book"))
    if refused:
        say.did("this is the control that was missing. The replacement is a "
                "legitimate model; what it did not have was an independent "
                "challenge asking why the same book on the same day is now "
                "half as risky")

    say.step("QUESTION 3 — does swapping the model close the breach?")
    still = maya.findings.for_model(URN)
    open_now = [f for f in (still.get("findings") or still.get("open") or [])
                if isinstance(f, dict) and f.get("status") != "closed"]
    say.maya(f"{len(open_now)} finding(s) still open after the new version "
             f"was registered")
    say.did("the sharpest question in the case study. A breach is a fact about "
            "the PORTFOLIO, and a model that reports a smaller number has not "
            "made the portfolio safer. MAYA closes a breach when the MONITOR "
            "recovers and deliberately leaves the FINDING open, because the "
            "model having recovered is not the same as somebody having looked "
            "at why it degraded — and here the model did not even recover, it "
            "was replaced")

    # ------------------------------------ 6. approval subject to further work
    say.step("QUESTION 4 — the approval was 'subject to further work'")
    say.note("the platform's own vocabulary named the right condition before "
             "this script did: `validated_by` is 'a completed validation must "
             "exist by the expiry, or the approval lapses'. That is precisely "
             "what 'approved subject to further work' means, and precisely "
             "what did not happen")
    condition = attempt(
        "approve on terms — validated_by",
        lambda: mrm.lifecycle.approve_on_terms(
            URN, kind="validated_by",
            rationale="the model review group approved the replacement subject "
                      "to completing the back-test against 2011 exceptions and "
                      "documenting the weighting scheme. Neither is done.",
            days=45.0, semver=REPLACEMENT, confirm_every_days=15.0),
        already="already conditional")
    if condition:
        say.maya("the condition is on the record with an expiry")
        kinds = maya.lifecycle.condition_kinds()
        for row in kinds.get("kinds", []):
            if row.get("kind") == "validated_by":
                say.note(f"enforcement: {row.get('enforcement')} — "
                         f"{row.get('means') or row.get('asks') or ''}")
        say.did("MAYA is explicit about which conditions it ENFORCES and which "
                "are attestations it cannot see. A firm that believes its "
                "condition is machine-enforced when it is a diary entry is "
                "worse off than one that knows, because the first has stopped "
                "checking. A conditional approval with no end date is an "
                "unconditional one that has not noticed yet")

    # --------------------------------------- 7. the spreadsheet reimplementation
    say.step("QUESTION 5 — does the spreadsheet agree with the model?")
    rate_a, rate_b = 0.0180, 0.0240
    correct = _volatility_correct(rate_a, rate_b)
    as_built = _volatility_as_built(rate_a, rate_b)
    say.engine(f"volatility term, divided by the AVERAGE: {correct:.4f}")
    say.engine(f"volatility term, divided by the SUM:     {as_built:.4f}")
    say.engine(f"the spreadsheet understates it by "
               f"{100*(1-as_built/correct):.0f}%")

    episode = attempt(
        "open a validation of the replacement",
        lambda: validator.validations.open(
            urn=URN, semver=REPLACEMENT,
            validators=["person/v.chen"], kind="initial",
            scope=["implementation"]),
        already="already open")
    if episode:
        vid = episode.get("id")
        say.maya(f"validation {vid} opened by an independent validator")
        # Keyed by the input each side was given. MAYA does not run either
        # implementation; it compares two sets of answers to the same
        # questions, which is the only comparison a register can make.
        reference = {f"obs-{i:02d}": round(correct * (1 + 0.01 * i), 8)
                     for i in range(24)}
        implemented = {f"obs-{i:02d}": round(as_built * (1 + 0.01 * i), 8)
                       for i in range(24)}
        recoded = attempt(
            "recode harness: model against spreadsheet",
            lambda: validator.validations.recode(
                vid, model=reference, recode=implemented, tolerance=1e-6,
                model_source="reference implementation, numpy",
                recode_source="production spreadsheet, as built"))
        if recoded:
            shape = (recoded.get("shape") or {})
            say.maya(f"{recoded.get('agreed')} of {recoded.get('compared')} "
                     f"agreed, {recoded.get('disagreed')} did not")
            say.maya(f"shape: {shape.get('kind')}")
            say.note(shape.get("detail", ""))
            say.note("a pass rate would have reported 0% and stopped. The "
                     "SHAPE is what says whether this is a branch nobody "
                     "tested or a floating-point tail")
        say.did("this is what MAYA can do about a spreadsheet: it cannot read "
                "the cell, and it can hold the reimplementation to a standard. "
                "Two implementations of one model, and the SHAPE of their "
                "disagreement — which a pass rate cannot give you. But note "
                "the conditional: somebody has to run it")

    # ------------------------------------------- 8. the supervisory matter
    say.step("QUESTION 6 — and then the regulators arrive")
    matter = attempt(
        "record the consent order as a supervisory matter",
        lambda: mrm.supervisory.raise_matter(
            "MRA-2012-SCP-01", kind="mria", supervisor="OCC",
            title="Model risk management deficiencies in the CIO",
            scope=[URN], owner="person/s.iqbal",
            description="Model changed without adequate independent validation; "
                        "model review group approval conditions not completed; "
                        "spreadsheet implementation with manual steps and no "
                        "reconciliation to a reference implementation.",
            examination="2012 targeted examination of the Chief Investment "
                        "Office",
            severity="Critical",
            # Deliberately a date the internal plan cannot meet:
            # Critical findings under this matter are due on the
            # firm's own severity window, and the commitment was
            # given in a letter before anybody costed the work.
            committed_at=time.time() + 20 * DAY),
        already="already raised")
    if matter:
        say.maya(f"{matter.get('detail', '')}")
        say.did("two dates, and they are not the same date. The findings under "
                "this matter carry the firm's own remediation dates, derived "
                "from severity. The MATTER carries the date the firm gave the "
                "supervisor. Conflating them is how a firm discovers on the "
                "day that its internal plan ran past its commitment — and here "
                "the gap is arithmetic available now")

    # ---------------------------------------------- 9. what MAYA cannot do
    say.step("What this platform would NOT have caught")
    for line in (
        "the divide-by-sum error inside the spreadsheet cell. MAYA does not "
        "run models and does not read spreadsheets. The step above shows the "
        "recode harness catching the DIVERGENCE — but only because somebody "
        "ran it, and the register cannot make somebody run it.",
        "the manual copy-and-paste between spreadsheets. There is no artifact "
        "digest for a process that lives in a person's hands, and a model "
        "whose implementation is a sequence of human steps is outside what "
        "any register can bind.",
        "the trader marks. The losses were also a valuation dispute, and MAYA "
        "holds a model's declared boundaries rather than the marks a desk "
        "puts on a position.",
        "whether anybody READ the finding. It stayed open, it blocked "
        "promotion, and it went on somebody's worklist. Escalation past that "
        "point is a management act, and this platform's own documentation is "
        "clear that a control nobody reads is not a control.",
    ):
        say.note(line)
    say.did("a case study that ended at §8 would be marketing. The value of "
            "running a real failure through a platform is the list of things "
            "it does not reach, because that list is what a firm has to cover "
            "some other way")

    # --------------------------------------------------- 10. the document
    say.step("Write the specification")
    blocks = [
        equation(r"\mathrm{VaR}_{99,1d} = \left| Q_{0.01}\!\left("
                 r"\sum_i w_i r_{i,t} \right) \right| \times N",
                 "abs(quantile(portfolio_returns, 0.01)) * notional"),
        table([["Effective lookback", "260 days", "120 days"],
               ["Reported VaR", rf"\${var_old/1e6:,.1f}m",
                rf"\${var_new/1e6:,.1f}m"],
               ["Against a limit of", rf"\${limit/1e6:,.1f}m",
                rf"\${limit/1e6:,.1f}m"],
               ["Verdict", "breach", "within limit"]],
              header=["", "Incumbent 1.0.0", "Replacement 2.0.0"],
              spec="lrr"),
    ]
    path = document(path=out / "var-model-change.tex",
                    title="A VaR model swapped mid-crisis",
                    subtitle="Case study 14 — reconstructed from the public "
                             "record",
                    blocks=blocks)
    say.maya(f"specification written to {path.name}")

    save_json(out / "case-14-summary.json", {
        "var_incumbent": var_old, "var_replacement": var_new,
        "limit": limit,
        "reduction": 1 - var_new / var_old,
        "volatility_correct": correct, "volatility_as_built": as_built,
        "understatement": 1 - as_built / correct,
        "source": "reconstructed from the public record; see README",
    }, what="the reconstruction's numbers")
    print()
    print("    Case study 14 complete. Six governance questions, and the")
    print("    platform answers five. The sixth is the last step, and it is")
    print("    the one a firm has to cover some other way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
