"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The nine fibres MAYA ships.

Read out of `docs/02 §5`, which had written the whole thing in prose — what
conceptual soundness rests on, what outcomes analysis is, what monitoring
answers, class by class — and then said the fibration was not built. It was
built; it was just written in a table nothing could read.

The prose is carried verbatim rather than paraphrased, because two statements of
one rule disagree eventually, and the direction they disagree in is whichever
one the reader happened to open.
"""
from __future__ import annotations

from typing import Dict

from core.docs.common import ANNEX_IV, MODEL_CARD, MODEL_DEVELOPMENT, VALIDATION_REPORT
from core.fibres.fibre import Fibre
from core.lifecycle import STATES
from core.monitoring import CALIBRATION, INPUT_DRIFT, PERFORMANCE, SCORE_DRIFT

# Attachment kinds, from `core/attachments/common.py`.
DEV_DOC = "model_development_document"
VAL_REPORT = "validation_report"
INDEPENDENT = "independent_review"
VENDOR_DOC = "vendor_documentation"
COMMITTEE = "committee_minute"
CONTROL = "evidence_of_control"

# Every class admits every lifecycle state. That is stated once, here, rather
# than nine times: a facet that does not vary is worth naming as invariant, and
# inventing variation to make a table look richer is how a fibre stops
# describing anything. It is still a facet, because a class that could not be
# retired, or could not be baselined from an import, would be a real difference
# and `L-15` should have somewhere to record it.
ALL_STATES = STATES

_LIBRARY: Dict[str, Fibre] = {f.trainability_class: f for f in (

    Fibre("T0", "Analytical",
          evidence=(DEV_DOC, CONTROL),
          lifecycle=ALL_STATES,
          # No parameters and no fitted relationship, so discrimination and
          # calibration are not questions about this model. What can move is
          # the input distribution it was benchmarked over.
          metrics=(INPUT_DRIFT,),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="derivation against the published mathematics; conventions "
                    "read against the term sheet",
          outcomes="benchmarking, instrument by instrument, against an "
                   "independent implementation, plus boundary behaviour — zero "
                   "rates, negative rates, expiry today",
          answers="are the inputs still in the range this was benchmarked over "
                  "— a breach is a finding against the use, not against the "
                  "mathematics"),

    Fibre("T1", "Market-calibrated",
          evidence=(DEV_DOC, VAL_REPORT),
          lifecycle=ALL_STATES,
          metrics=(INPUT_DRIFT, CALIBRATION),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="the choice of dynamics, and the instrument set the "
                    "calibration is solved against",
          outcomes="repricing error on the calibration set, and on instruments "
                   "held out of it; arbitrage-free checks",
          answers="calibration residual, and parameter stability — mean "
                  "reversion jumping 40% overnight is a different local "
                  "minimum, not new information"),

    Fibre("T2", "Statistically estimated",
          evidence=(DEV_DOC, VAL_REPORT),
          lifecycle=ALL_STATES,
          metrics=(INPUT_DRIFT, SCORE_DRIFT, PERFORMANCE, CALIBRATION),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="the specification: which regressors, which functional "
                    "form, what was rejected",
          outcomes="discrimination and calibration against realised outcomes, "
                   "out of sample and out of time",
          answers="drift in the inputs, decay in discrimination, and the "
                  "calibration holding"),

    Fibre("T3", "Machine-learned",
          # The independent review is where the opacity is justified. Without
          # it a T3 model is an unexplained choice to be harder to explain.
          evidence=(DEV_DOC, VAL_REPORT, INDEPENDENT),
          lifecycle=ALL_STATES,
          metrics=(INPUT_DRIFT, SCORE_DRIFT, PERFORMANCE, CALIBRATION),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="why the opacity was worth it, evidenced by a benchmark "
                    "against a simpler incumbent",
          outcomes="held-out replay; stability under perturbation; subgroup "
                   "performance",
          answers="score drift as the leading indicator, because the labels "
                  "arrive late"),

    Fibre("T4", "Adaptive",
          evidence=(DEV_DOC, VAL_REPORT, INDEPENDENT, CONTROL),
          lifecycle=ALL_STATES,
          metrics=(INPUT_DRIFT, SCORE_DRIFT, PERFORMANCE, CALIBRATION),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="as T3, plus the change process itself: what may move "
                    "autonomously and how far",
          outcomes="parallel outcomes analysis across the change, comparing "
                   "pre and post against actuals",
          answers="the magnitude and frequency of autonomous change, with the "
                  "parameter trajectory retained"),

    Fibre("T5", "Configured",
          evidence=(DEV_DOC, VAL_REPORT, CONTROL),
          lifecycle=ALL_STATES,
          # A frozen evaluation set gives a performance question. Calibration
          # does not apply to generated text, and pretending it did would put a
          # number on a page that means nothing.
          metrics=(SCORE_DRIFT, PERFORMANCE),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="the assembly: what the model was told, what it may "
                    "retrieve, what it may call",
          outcomes="a frozen evaluation set, scored on it",
          answers="regression against that evaluation set, on a schedule and "
                  "on every provider version change"),

    Fibre("T6", "Vendor black box",
          # No development document: somebody else developed it, and asking the
          # bank for one produces a document about a model nobody here built.
          evidence=(VENDOR_DOC, VAL_REPORT, INDEPENDENT),
          lifecycle=ALL_STATES,
          metrics=(INPUT_DRIFT, SCORE_DRIFT, PERFORMANCE),
          templates=(VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="the vendor's own validation, obtained and assessed rather "
                    "than assumed",
          outcomes="your own outcomes, on your own portfolio — the only "
                   "evidence you control",
          answers="divergence from your benchmark, and detection of a version "
                  "change you were not told about"),

    Fibre("T7", "Expert judgment",
          # The minute is the evidence: panel composition, the questions asked,
          # and the dissent. Without it an elicitation is an assertion.
          evidence=(DEV_DOC, VAL_REPORT, COMMITTEE),
          lifecycle=ALL_STATES,
          metrics=(SCORE_DRIFT, PERFORMANCE),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="panel composition, the questions asked, and the dissent",
          outcomes="outcome analysis against the judgment, and inter-rater "
                   "consistency",
          answers="override rate, and whether the judgment is being overridden "
                  "in one direction"),

    Fibre("T8", "Deterministic rule",
          evidence=(DEV_DOC, VAL_REPORT),
          lifecycle=ALL_STATES,
          metrics=(INPUT_DRIFT, SCORE_DRIFT),
          templates=(MODEL_DEVELOPMENT, VALIDATION_REPORT, MODEL_CARD, ANNEX_IV),
          soundness="the rule read against the policy it implements",
          outcomes="above-the-line and below-the-line testing",
          answers="rule-fire distribution and exception rate"),
)}


def library() -> Dict[str, Fibre]:
    """The shipped fibres, as a fresh mapping — the registry owns the copy."""
    return dict(_LIBRARY)
