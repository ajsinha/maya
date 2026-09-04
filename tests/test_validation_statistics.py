"""
MAYA — the validation statistics.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

These are the numbers a validation report rests on, so they are tested against
their definitions and against the properties that must hold for any sample —
not against values copied from a run of the code they are testing.
"""
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.validation.statistics import (_ranks, auc, brier, expected_vs_actual, gini,
                                        ks, mae, psi, rmse)


class TestRanks:
    def test_distinct_values_get_consecutive_ranks(self):
        assert _ranks([10, 20, 30]) == [1.0, 2.0, 3.0]

    def test_order_is_by_value_not_position(self):
        assert _ranks([30, 10, 20]) == [3.0, 1.0, 2.0]

    def test_ties_share_the_mean_of_the_positions_they_span(self):
        # positions 2 and 3 -> both get 2.5
        assert _ranks([1, 5, 5, 9]) == [1.0, 2.5, 2.5, 4.0]

    def test_all_tied_values_all_get_the_midpoint(self):
        assert _ranks([7, 7, 7, 7]) == [2.5] * 4

    @given(st.lists(st.floats(-100, 100, allow_nan=False), min_size=1, max_size=40))
    def test_ranks_always_sum_to_n_times_n_plus_one_over_two(self, values):
        """True however the ties fall — that is what makes average ranks correct."""
        assert math.isclose(sum(_ranks(values)), len(values) * (len(values) + 1) / 2)


class TestAuc:
    def test_perfect_separation_is_one(self):
        assert auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0

    def test_perfectly_inverted_is_zero(self):
        assert auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == 0.0

    def test_no_information_is_one_half(self):
        assert auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5

    def test_a_single_class_is_not_computable(self):
        """Nothing to discriminate between. None, not 0.5 and not a crash."""
        assert auc([1, 1, 1], [0.1, 0.2, 0.3]) is None
        assert auc([0, 0, 0], [0.1, 0.2, 0.3]) is None

    def test_empty_sample_is_not_computable(self):
        assert auc([], []) is None

    def test_matches_the_mann_whitney_definition_by_brute_force(self, scored):
        """AUC is P(positive outranks negative), ties counting a half. Compute
        that directly over every pair and require agreement."""
        labels, scores = scored
        pos = [s for y, s in zip(labels, scores) if y == 1]
        neg = [s for y, s in zip(labels, scores) if y == 0]
        wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
        assert math.isclose(auc(labels, scores), wins / (len(pos) * len(neg)))

    @given(st.lists(st.tuples(st.sampled_from([0, 1]), st.floats(0, 1)),
                    min_size=2, max_size=40))
    @settings(max_examples=200)
    def test_auc_is_always_a_probability(self, pairs):
        labels = [p[0] for p in pairs]
        scores = [p[1] for p in pairs]
        value = auc(labels, scores)
        assert value is None or 0.0 <= value <= 1.0

    def test_is_invariant_under_a_monotone_rescaling_of_scores(self, scored):
        """AUC depends on order alone, so any increasing transform leaves it be."""
        labels, scores = scored
        rescaled = [math.log(s + 1) * 37 + 4 for s in scores]
        assert math.isclose(auc(labels, scores), auc(labels, rescaled))


class TestGini:
    def test_is_two_auc_minus_one(self, scored):
        labels, scores = scored
        assert math.isclose(gini(labels, scores), 2 * auc(labels, scores) - 1)

    def test_perfect_is_one_and_inverted_is_minus_one(self):
        assert gini([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
        assert gini([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == -1.0

    def test_propagates_not_computable(self):
        assert gini([1, 1], [0.3, 0.4]) is None


class TestKs:
    def test_perfect_separation_is_one(self):
        assert ks([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0

    def test_identical_distributions_are_zero(self):
        assert ks([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.0

    def test_is_bounded_in_the_unit_interval(self, scored):
        assert 0.0 <= ks(*scored) <= 1.0

    def test_a_single_class_is_not_computable(self):
        assert ks([0, 0], [0.2, 0.4]) is None


class TestBrier:
    def test_a_perfect_confident_forecast_scores_zero(self):
        assert brier([0, 0, 1, 1], [0.0, 0.0, 1.0, 1.0]) == 0.0

    def test_a_confidently_wrong_forecast_scores_one(self):
        assert brier([0, 1], [1.0, 0.0]) == 1.0

    def test_a_coin_flip_forecast_scores_a_quarter(self):
        assert brier([0, 1, 0, 1], [0.5] * 4) == 0.25

    def test_empty_is_not_computable(self):
        assert brier([], []) is None


class TestExpectedVsActual:
    def test_a_calibrated_forecast_is_one(self):
        assert expected_vs_actual([0, 0, 1, 1], [0.5] * 4) == 1.0

    def test_over_prediction_is_above_one(self):
        assert expected_vs_actual([0, 0, 0, 1], [0.5] * 4) == 2.0

    def test_under_prediction_is_below_one(self):
        assert expected_vs_actual([0, 1, 1, 1], [0.375] * 4) == 0.5

    def test_no_observed_events_is_not_computable(self):
        """Dividing by a zero base rate. None rather than an infinity."""
        assert expected_vs_actual([0, 0, 0], [0.1, 0.2, 0.3]) is None


class TestPsi:
    def test_identical_samples_score_zero(self):
        sample = list(range(100))
        assert math.isclose(psi(sample, sample), 0.0, abs_tol=1e-12)

    def test_a_fully_displaced_sample_scores_large(self):
        shifted = psi(list(range(100)), [x + 1000 for x in range(100)])
        assert shifted > 1.0, "a distribution that moved off its support must be flagged"

    def test_a_mild_shift_scores_between(self):
        mild = psi(list(range(100)), [x + 5 for x in range(100)])
        big = psi(list(range(100)), [x + 1000 for x in range(100)])
        assert 0.0 < mild < big

    def test_is_never_negative(self, ):
        """PSI is a sum of (a-e)ln(a/e) terms, each non-negative."""
        assert psi(list(range(100)), [x * 1.3 + 2 for x in range(100)]) >= 0.0

    def test_too_few_reference_points_for_the_requested_bins(self):
        assert psi([1, 2, 3], [1, 2, 3], bins=10) is None

    def test_an_empty_current_sample_is_not_computable(self):
        assert psi(list(range(100)), []) is None

    def test_empty_bins_are_floored_rather_than_dropped(self):
        """A bin nothing landed in is the strongest evidence of movement; if it
        were dropped the score would fall exactly when it should rise."""
        value = psi(list(range(100)), [99.0] * 100)
        assert value is not None and value > 1.0


class TestRegressionMetrics:
    def test_rmse_of_an_exact_prediction_is_zero(self):
        assert rmse([1, 2, 3], [1, 2, 3]) == 0.0

    def test_rmse_is_the_root_of_the_mean_square(self):
        assert math.isclose(rmse([0, 0], [3, 4]), math.sqrt((9 + 16) / 2))

    def test_mae_is_the_mean_absolute_deviation(self):
        assert mae([0, 0], [3, 4]) == 3.5

    def test_rmse_is_never_below_mae(self):
        """Jensen's inequality, and a useful sanity check on both at once."""
        truth, pred = [1, 2, 3, 4], [1.5, 1.0, 4.0, 3.0]
        assert rmse(truth, pred) >= mae(truth, pred)

    def test_empty_is_not_computable(self):
        assert rmse([], []) is None and mae([], []) is None
