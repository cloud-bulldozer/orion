# pylint: disable=missing-class-docstring,missing-function-docstring
"""Tests for confidence indicators module."""

import numpy as np
import pandas as pd
import pytest

from orion.confidence import (
    ConfidenceResult,
    _map_label,
    _get_segments,
    _compute_stats,
    compute_confidence,
)
import orion.constants as cnsts
from orion.tests.conftest import make_change_point as _make_cp


class TestMapLabel:
    def test_likely_real_large_shift(self):
        assert _map_label(0.01, 1.0) == "Likely real [1.00] (large shift [0.01])"

    def test_likely_real_moderate_shift(self):
        assert _map_label(0.01, 0.6) == "Likely real [0.60] (moderate shift [0.01])"

    def test_possible_small_shift(self):
        assert _map_label(0.01, 0.3) == "Possible [0.30] (small shift [0.01])"

    def test_significant_but_trivial(self):
        assert _map_label(0.01, 0.1) == "Statistically significant [0.10] but trivial [0.01]"

    def test_noise_high_p_value(self):
        assert _map_label(0.3, 1.5) == "Noise [1.50] (trivial shift [0.30])"

    def test_boundary_p_value_at_005(self):
        assert _map_label(0.05, 1.0) == "Noise [1.00] (trivial shift [0.05])"

    def test_boundary_cohens_d_at_08(self):
        assert _map_label(0.01, 0.8) == "Likely real [0.80] (large shift [0.01])"

    def test_boundary_cohens_d_at_05(self):
        assert _map_label(0.01, 0.5) == "Likely real [0.50] (moderate shift [0.01])"

    def test_boundary_cohens_d_at_02(self):
        assert _map_label(0.01, 0.2) == "Possible [0.20] (small shift [0.01])"

    def test_infinity_cohens_d(self):
        assert _map_label(0.001, float("inf")) == "Likely real [inf] (large shift [0.00])"


class TestConfidenceResult:
    def test_dataclass_fields(self):
        result = ConfidenceResult(
            p_value=0.01,
            cohens_d=1.2,
            confidence_label="Likely real (large shift)",
            sufficient_data=True,
            sample_size_before=10,
            sample_size_after=5,
        )
        assert result.p_value == 0.01
        assert result.cohens_d == 1.2
        assert result.sufficient_data is True

    def test_insufficient_data_result(self):
        result = ConfidenceResult(
            p_value=None,
            cohens_d=None,
            confidence_label="Insufficient data",
            sufficient_data=False,
            sample_size_before=5,
            sample_size_after=1,
        )
        assert result.sufficient_data is False
        assert result.p_value is None


class TestGetSegments:
    def test_edivisive_splits_at_index(self):
        data = np.array([1.0, 2.0, 3.0, 10.0, 11.0])
        before, after = _get_segments(cnsts.EDIVISIVE, data, 3)
        np.testing.assert_array_equal(before, [1.0, 2.0, 3.0])
        np.testing.assert_array_equal(after, [10.0, 11.0])

    def test_cmr_splits_all_previous_vs_last(self):
        data = np.array([1.0, 2.0, 3.0, 10.0])
        before, after = _get_segments(cnsts.CMR, data, 3)
        np.testing.assert_array_equal(before, [1.0, 2.0, 3.0])
        np.testing.assert_array_equal(after, [10.0])

    def test_isolation_forest_splits_at_index(self):
        data = np.array([1.0, 2.0, 3.0, 10.0, 11.0])
        before, after = _get_segments(cnsts.ISOLATION_FOREST, data, 3)
        np.testing.assert_array_equal(before, [1.0, 2.0, 3.0])
        np.testing.assert_array_equal(after, [10.0, 11.0])

    def test_edivisive_index_at_start(self):
        data = np.array([10.0, 1.0, 2.0])
        before, after = _get_segments(cnsts.EDIVISIVE, data, 0)
        assert len(before) == 0
        np.testing.assert_array_equal(after, [10.0, 1.0, 2.0])

    def test_edivisive_index_at_end(self):
        data = np.array([1.0, 2.0, 10.0])
        before, after = _get_segments(cnsts.EDIVISIVE, data, 2)
        np.testing.assert_array_equal(before, [1.0, 2.0])
        np.testing.assert_array_equal(after, [10.0])


class TestComputeStats:
    def test_clear_regression_produces_low_p_high_d(self):
        before = np.array([100.0, 101.0, 99.0, 100.5, 100.2,
                           99.8, 100.1, 99.9, 100.3, 99.7])
        after = np.array([200.0, 201.0, 199.0, 200.5, 200.2,
                          199.8, 200.1, 199.9, 200.3, 199.7])
        result = _compute_stats(before, after)
        assert result.sufficient_data is True
        assert result.p_value < 0.05
        assert result.cohens_d > 0.8
        assert "Likely real" in result.confidence_label
        assert "large shift" in result.confidence_label
        assert result.mean_before == pytest.approx(np.mean(before))
        assert result.mean_after == pytest.approx(np.mean(after))
        assert result.std_before == pytest.approx(np.std(before, ddof=1))
        assert result.std_after == pytest.approx(np.std(after, ddof=1))

    def test_identical_data_produces_noise(self):
        before = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
        after = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
        result = _compute_stats(before, after)
        assert result.sufficient_data is True
        assert result.cohens_d == 0.0
        assert "Noise" in result.confidence_label
        assert "trivial shift" in result.confidence_label

    def test_insufficient_data_one_point_after(self):
        before = np.array([100.0, 101.0, 99.0])
        after = np.array([200.0])
        result = _compute_stats(before, after)
        assert result.sufficient_data is False
        assert result.p_value is None
        assert result.cohens_d is None
        assert result.confidence_label == "Insufficient data"
        assert result.mean_before == pytest.approx(100.0)
        assert result.mean_after == pytest.approx(200.0)
        assert result.std_before is not None
        assert result.std_after is None

    def test_insufficient_data_empty_before(self):
        before = np.array([])
        after = np.array([200.0, 201.0])
        result = _compute_stats(before, after)
        assert result.sufficient_data is False

    def test_zero_std_different_means(self):
        before = np.array([100.0, 100.0, 100.0])
        after = np.array([200.0, 200.0, 200.0])
        result = _compute_stats(before, after)
        assert result.sufficient_data is True
        assert result.cohens_d == float("inf")
        assert result.p_value is not None

    def test_sample_sizes_recorded(self):
        before = np.array([1.0, 2.0, 3.0])
        after = np.array([10.0, 11.0])
        result = _compute_stats(before, after)
        assert result.sample_size_before == 3
        assert result.sample_size_after == 2


class TestComputeConfidence:
    def test_returns_dict_keyed_by_metric(self):
        df = pd.DataFrame({
            "cpu": [10.0, 10.5, 9.8, 10.2, 10.1,
                    20.0, 20.5, 19.8, 20.2, 20.1],
        })
        cps = {"cpu": [_make_cp("cpu", 5)]}
        result = compute_confidence(cnsts.EDIVISIVE, df, cps)
        assert "cpu" in result
        assert len(result["cpu"]) == 1
        assert isinstance(result["cpu"][0], ConfidenceResult)

    def test_index_aligned_with_changepoints(self):
        df = pd.DataFrame({
            "cpu": [10.0, 10.5, 9.8, 20.0, 20.5,
                    30.0, 30.5, 29.8, 30.2, 30.1],
        })
        cps = {"cpu": [_make_cp("cpu", 3), _make_cp("cpu", 5)]}
        result = compute_confidence(cnsts.EDIVISIVE, df, cps)
        assert len(result["cpu"]) == 2
        assert [
            (item.sample_size_before, item.sample_size_after)
            for item in result["cpu"]
        ] == [(3, 7), (5, 5)]
    def test_empty_changepoints_returns_empty(self):
        df = pd.DataFrame({"cpu": [10.0, 11.0, 12.0]})
        cps = {"cpu": []}
        result = compute_confidence(cnsts.EDIVISIVE, df, cps)
        assert result["cpu"] == []

    def test_multiple_metrics(self):
        df = pd.DataFrame({
            "cpu": [10.0, 10.5, 20.0, 20.5],
            "mem": [50.0, 51.0, 100.0, 101.0],
        })
        cps = {
            "cpu": [_make_cp("cpu", 2)],
            "mem": [_make_cp("mem", 2)],
        }
        result = compute_confidence(cnsts.EDIVISIVE, df, cps)
        assert "cpu" in result
        assert "mem" in result
        assert len(result["cpu"]) == 1
        assert len(result["mem"]) == 1

    def test_same_index_different_metrics_get_different_confidence(self):
        np.random.seed(99)
        cpu_vals = np.concatenate([
            np.random.normal(0.5, 0.05, 8),
            np.random.normal(0.9, 0.05, 4),
        ])
        lat_vals = np.concatenate([
            np.random.normal(40000, 4000, 8),
            np.random.normal(70000, 4000, 4),
        ])
        df = pd.DataFrame({"cpu": cpu_vals, "latency": lat_vals})
        cps = {
            "cpu": [_make_cp("cpu", 8, mean_1=0.5, mean_2=0.9)],
            "latency": [_make_cp("latency", 8,
                                 mean_1=40000, mean_2=70000)],
        }
        result = compute_confidence(cnsts.EDIVISIVE, df, cps)
        cpu_conf = result["cpu"][0]
        lat_conf = result["latency"][0]
        assert cpu_conf.cohens_d != lat_conf.cohens_d
        assert cpu_conf.p_value != lat_conf.p_value

    def test_cmr_single_point_after_insufficient(self):
        df = pd.DataFrame({
            "cpu": [10.0, 10.5, 9.8, 20.0],
        })
        cps = {"cpu": [_make_cp("cpu", 3)]}
        result = compute_confidence(cnsts.CMR, df, cps)
        assert result["cpu"][0].sufficient_data is False
        assert result["cpu"][0].confidence_label == "Insufficient data"

    def test_nan_before_changepoint_preserves_alignment(self):
        df = pd.DataFrame({
            "cpu": [1.0, np.nan, 2.0, 10.0, 11.0],
        })
        cps = {"cpu": [_make_cp("cpu", 3)]}
        result = compute_confidence(cnsts.EDIVISIVE, df, cps)
        assert result["cpu"][0].sufficient_data is True
        assert result["cpu"][0].sample_size_before == 2
        assert result["cpu"][0].sample_size_after == 2
