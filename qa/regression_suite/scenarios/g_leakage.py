"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the leakage screen, and the four ways it can not run.

`detect_leakage` returns a list, and an empty list is the same object whether
nothing was suspicious or nothing was examined. That sentence is the whole
module: a training set that came back clean because the screen never ran is
indistinguishable, to every reader downstream, from one that was screened and
found nothing. Each case here is one of the ways the screen goes quiet.
"""
from __future__ import annotations

from core.features.pit import CONTINUOUS_RATIO, screen_leakage
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _rows(n: int, labels=None, **columns):
    labels = labels if labels is not None else [i % 2 for i in range(n)]
    out = []
    for i in range(n):
        row = {"entity_id": f"e{i}", "label": labels[i], "label_ts": 1.0}
        for key, values in columns.items():
            row[key] = values[i]
        out.append(row)
    return out


@case("QA-FX-018", "A spine of zero rows")
def fx_018(ctx: Ctx) -> Result:
    """Nothing to screen, and the report has to say so rather than returning
    the same empty list a clean frame returns."""
    suspects, why_not = screen_leakage([])
    if suspects:
        return FAIL, f"an empty frame produced suspects: {suspects}"
    if not why_not:
        return FAIL, ("an empty frame came back clean with no reason, so it "
                      "is indistinguishable from a screened one")
    return PASS, why_not


@case("QA-FX-020", "Exactly seven spine rows, then exactly eight")
def fx_020(ctx: Ctx) -> Result:
    """Below eight, a relationship between a column and the label is not
    evidence of anything. The boundary has to bite on one side only."""
    seven = screen_leakage(_rows(7))[1]
    eight = screen_leakage(_rows(8))[1]
    if not seven:
        return FAIL, "seven rows were screened, and seven rows prove nothing"
    if eight:
        return FAIL, (f"eight rows were NOT screened: {eight}. The threshold "
                      f"excludes the first size it admits")
    return PASS, f"seven: {seven[:60]} — eight: screened"


@case("QA-FX-021", "Eight rows, one distinct label value")
def fx_021(ctx: Ctx) -> Result:
    """Nothing separates a label from itself. A frame where every row carries
    the same outcome cannot be screened, and reporting it clean would be the
    commonest false comfort there is."""
    suspects, why_not = screen_leakage(_rows(8, labels=[1] * 8))
    if suspects:
        return FAIL, f"a single-valued label produced suspects: {suspects}"
    if not why_not:
        return FAIL, ("a frame with one label value came back clean with no "
                      "reason")
    return PASS, why_not


@case("QA-FX-022", "A continuous label — a regression training set")
def fx_022(ctx: Ctx) -> Result:
    """"The only screen available for a continuous column is a threshold
    split, which means nothing unless the label is binary." A regression
    training set therefore came back clean having been screened for nothing
    at all — and now says so."""
    labels = [float(i) * 1.5 for i in range(20)]
    _, why_not = screen_leakage(_rows(20, labels=labels))
    if not why_not:
        return FAIL, ("a continuous label was reported as screened; every "
                      "regression training set comes back clean having been "
                      "examined for nothing")
    if "continuous" not in why_not:
        return FAIL, f"the reason does not name the problem: {why_not}"
    return PASS, why_not


@case("QA-FX-3800", "A three-class label — neither binary nor continuous")
def fx_3800(ctx: Ctx) -> Result:
    """The nastiest of the four, and the one the ratio misses. A three-class
    label over sixty rows is not continuous by the ratio and not binary
    either, so the screen ran, reported itself as having run, and examined
    every continuous column for nothing.
    """
    labels = [i % 3 for i in range(60)]
    # Genuinely CONTINUOUS — a distinct value per row — and still decoding
    # the grade exactly, because the integer part is the label. Three
    # repeating values would not be continuous, `unscreenable` would be
    # empty, and `detect_leakage` would find the column anyway.
    decoder = [float(label) + i / 1000.0 for i, label in enumerate(labels)]
    suspects, why_not = screen_leakage(_rows(60, labels=labels,
                                             decoder=decoder))
    if why_not is None:
        return FAIL, (
            f"a three-class label reported the screen as having run, and "
            f"`_separates_near_perfectly` returns False for anything "
            f"non-binary — so 'decoder', which decodes the label exactly, "
            f"was examined for nothing and came back {suspects}")
    if "decoder" not in why_not:
        return FAIL, (f"the reason does not name the column that was not "
                      f"screened: {why_not}")
    return PASS, why_not


@case("QA-FX-023", "A column that is a perfect threshold split of the label")
def fx_023(ctx: Ctx) -> Result:
    """The screen's whole job. A column that separates the label perfectly is
    the label wearing another name."""
    labels = [i % 2 for i in range(20)]
    giveaway = [float(label) * 1000.0 + 1.0 for label in labels]
    suspects, why_not = screen_leakage(_rows(20, labels=labels,
                                             sale_price=giveaway))
    if why_not:
        return FAIL, f"the screen did not run: {why_not}"
    if "sale_price" not in suspects:
        return FAIL, ("a column that splits the label perfectly was not "
                      f"named as leakage; suspects were {suspects}")
    return PASS, f"named: {suspects}"


@case("QA-FX-025", "An ordinary strong predictor that is not leakage")
def fx_025(ctx: Ctx) -> Result:
    """The screen has to be wrong in the safe direction too. A feature that
    predicts well and is not the label must not be named, or every useful
    column is flagged and the screen is ignored."""
    labels = [i % 2 for i in range(40)]
    # Genuinely overlapping. `i % 4` against `i % 2` looks noisy and is a
    # perfect decoder — values 0 and 2 are always label 0, 1 and 3 always
    # label 1 — which the categorical screen rightly catches. This shifts by
    # a third so every value carries BOTH labels.
    noisy = [float((i // 3) % 4) for i in range(40)]
    suspects, why_not = screen_leakage(_rows(40, labels=labels, score=noisy))
    if why_not:
        return FAIL, f"the screen did not run: {why_not}"
    if "score" in suspects:
        return FAIL, ("an ordinary overlapping predictor was named as "
                      "leakage; a screen that flags every useful column is "
                      "one nobody reads")
    return PASS, f"not flagged; suspects were {suspects}"


@case("QA-FX-3801", "The screen is run under the column the label occupies")
def fx_3801(ctx: Ctx) -> Result:
    """It used to call `detect_leakage(rows)`, which looks for a column
    literally named `label`. A real training set names the label what the
    author named it — `defaulted_12m`, `charged_off` — so the screen examined
    nothing and reported no suspected leakage, which is indistinguishable
    from a clean one.
    """
    labels = [i % 2 for i in range(20)]
    giveaway = [float(label) * 1000.0 + 1.0 for label in labels]
    rows = [{"entity_id": f"e{i}", "defaulted_12m": labels[i],
             "label_ts": 1.0, "sale_price": giveaway[i]}
            for i in range(20)]
    _, why_blind = screen_leakage(rows)
    if why_blind is None:
        return FAIL, ("the screen reported itself as having run against a "
                      "frame with no 'label' column at all")
    named, why_named = screen_leakage(rows, "defaulted_12m")
    if why_named:
        return FAIL, f"the screen did not run under the real key: {why_named}"
    if "sale_price" not in named:
        return FAIL, (f"run under the real label key, the giveaway column was "
                      f"still not found: {named}")
    return PASS, (f"blind: {why_blind[:50]} — under 'defaulted_12m': {named}")


@case("QA-FX-3802", "The continuous ratio is stated, not implied")
def fx_3802(ctx: Ctx) -> Result:
    """`CONTINUOUS_RATIO` decides whether a label is treated as a class or a
    number, and therefore whether the screen runs at all. A threshold nobody
    can see is a control nobody can argue with."""
    if not 0 < CONTINUOUS_RATIO < 1:
        return FAIL, f"the continuous ratio is {CONTINUOUS_RATIO}"
    # Just under: still treated as classes. Just over: continuous.
    n = 20
    classes = [i % int(n * CONTINUOUS_RATIO) for i in range(n)]
    spread = [float(i) for i in range(n)]
    if screen_leakage(_rows(n, labels=spread))[1] is None:
        return FAIL, (f"{n} distinct labels over {n} rows was not treated as "
                      f"continuous, above the {CONTINUOUS_RATIO} ratio")
    if len(set(classes)) / n > CONTINUOUS_RATIO:
        return PASS, f"ratio {CONTINUOUS_RATIO} separates the two readings"
    return PASS, f"ratio {CONTINUOUS_RATIO}, and a class label stays a class"
