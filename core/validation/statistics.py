"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The validation statistics, implemented from their definitions.

Written out rather than imported for two reasons that matter in this setting.
A validation result has to be reproducible years later, when the version of
whatever library computed it is long gone — so the computation is here, pinned,
and its ties and edge cases are decided explicitly rather than inherited.

And a validator has to be able to answer "how was this number arrived at" to an
examiner. Every function below is short enough to read in full, which is the
only form of that answer worth giving.

Ties are handled by average ranks throughout. Degenerate inputs (one class,
empty samples, zero-width bins) return None rather than raising or silently
producing a number, because "not computable on this sample" is a real answer and
0.0 is a lie.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple


def _ranks(values: Sequence[float]) -> List[float]:
    """Average ranks, 1-based. Ties share the mean of the positions they span."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0            # mean of 1-based positions i..j
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def _split(y_true: Sequence[int], y_score: Sequence[float]) -> Tuple[List[float], List[float]]:
    pos = [s for y, s in zip(y_true, y_score) if y == 1]
    neg = [s for y, s in zip(y_true, y_score) if y != 1]
    return pos, neg


def auc(y_true: Sequence[int], y_score: Sequence[float]) -> Optional[float]:
    """Area under the ROC curve, by the Mann-Whitney U identity.

    AUC is the probability that a randomly chosen positive outranks a randomly
    chosen negative, with ties counting a half. Undefined when either class is
    absent — there is nothing to discriminate between.
    """
    pos, neg = _split(y_true, y_score)
    if not pos or not neg:
        return None
    ranks = _ranks(list(y_score))
    rank_sum = sum(r for r, y in zip(ranks, y_true) if y == 1)
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def gini(y_true: Sequence[int], y_score: Sequence[float]) -> Optional[float]:
    """Gini = 2 x AUC - 1. The scale credit risk states its discrimination on."""
    a = auc(y_true, y_score)
    return None if a is None else 2.0 * a - 1.0


def ks(y_true: Sequence[int], y_score: Sequence[float]) -> Optional[float]:
    """Kolmogorov-Smirnov: the widest gap between the two cumulative curves."""
    pos, neg = _split(y_true, y_score)
    if not pos or not neg:
        return None
    best = 0.0
    for threshold in sorted(set(y_score)):
        cp = sum(s <= threshold for s in pos) / len(pos)
        cn = sum(s <= threshold for s in neg) / len(neg)
        best = max(best, abs(cp - cn))
    return best


def brier(y_true: Sequence[int], y_score: Sequence[float]) -> Optional[float]:
    """Mean squared error of a probability forecast. Lower is better."""
    if not y_true:
        return None
    return sum((s - y) ** 2 for y, s in zip(y_true, y_score)) / len(y_true)


def expected_vs_actual(y_true: Sequence[int], y_score: Sequence[float]) -> Optional[float]:
    """Predicted rate over observed rate. 1.0 is calibrated; >1 over-predicts."""
    if not y_true:
        return None
    observed = sum(y_true) / len(y_true)
    if observed == 0:
        return None
    return (sum(y_score) / len(y_score)) / observed


def psi(expected: Sequence[float], actual: Sequence[float], bins: int = 10) -> Optional[float]:
    """Population Stability Index between two samples.

    Bin edges come from the EXPECTED sample's quantiles, which is the direction
    that makes the number comparable over time: the development distribution is
    the fixed reference, and today's data is measured against it.

    Empty bins are floored rather than dropped. Dropping them understates
    movement precisely when the movement is total, and the floor is what makes
    the logarithm finite.
    """
    if len(expected) < bins or not actual:
        return None
    ordered = sorted(expected)
    edges = [ordered[int(round(q * (len(ordered) - 1) / bins))] for q in range(1, bins)]
    floor = 1.0 / (bins * 10.0)

    def shares(sample: Sequence[float]) -> List[float]:
        counts = [0] * bins
        for v in sample:
            slot = 0
            while slot < len(edges) and v > edges[slot]:
                slot += 1
            counts[slot] += 1
        return [max(c / len(sample), floor) for c in counts]

    e, a = shares(ordered), shares(actual)
    return sum((ai - ei) * math.log(ai / ei) for ei, ai in zip(e, a))


def rmse(y_true: Sequence[float], y_pred: Sequence[float]) -> Optional[float]:
    if not y_true:
        return None
    return math.sqrt(sum((p - t) ** 2 for t, p in zip(y_true, y_pred)) / len(y_true))


def mae(y_true: Sequence[float], y_pred: Sequence[float]) -> Optional[float]:
    if not y_true:
        return None
    return sum(abs(p - t) for t, p in zip(y_true, y_pred)) / len(y_true)
