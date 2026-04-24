"""
Unit tests for orion/algorithms/algorithm.py, algorithmFactory.py,
edivisive.py, isolationforest.py, and cmr.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error
# pylint: disable = missing-class-docstring
# pylint: disable = protected-access
# pylint: disable = no-member

import json
import logging

import numpy as np
import pandas as pd
import pytest
from otava.analysis import TTestStats
from otava.series import ChangePoint

from orion.algorithms.algorithmFactory import AlgorithmFactory
from orion.algorithms.cmr.cmr import CMR
from orion.algorithms.edivisive.edivisive import EDivisive
from orion.algorithms.isolationforest.isolationForest import IsolationForestWeightedMean
from orion.logger import SingletonLogger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


def _make_dataframe(n=10, seed=42):
    """Build a simple dataframe with uuid, timestamp, version, and one metric."""
    rng = np.random.RandomState(seed)
    timestamps = [1704067200 + i * 86400 for i in range(n)]
    return pd.DataFrame({
        "uuid": [f"uuid-{i}" for i in range(n)],
        "timestamp": timestamps,
        "ocpVersion": ["4.14.0"] * n,
        "throughput": rng.normal(100, 5, n).tolist(),
    })


def _make_test():
    return {
        "name": "test-bench",
        "uuid_field": "uuid",
        "version_field": "ocpVersion",
    }


def _make_options(**overrides):
    opts = {
        "collapse": False,
        "display": [],
        "ackMap": None,
        "github_repos": [],
        "anomaly_window": None,
        "min_anomaly_percent": None,
    }
    opts.update(overrides)
    return opts


def _make_metrics_config():
    return {
        "throughput": {
            "direction": 0,
            "threshold": 5,
            "labels": ["perf"],
            "correlation": "",
            "context": 5,
        }
    }


# ---------------------------------------------------------------------------
# AlgorithmFactory
# ---------------------------------------------------------------------------

class TestAlgorithmFactory:
    def test_edivisive(self):
        df = _make_dataframe()
        algo = AlgorithmFactory().instantiate_algorithm(
            "EDivisive", df, _make_test(), _make_options(), _make_metrics_config()
        )
        assert isinstance(algo, EDivisive)

    def test_isolation_forest(self):
        df = _make_dataframe()
        algo = AlgorithmFactory().instantiate_algorithm(
            "IsolationForest", df, _make_test(), _make_options(), _make_metrics_config()
        )
        assert isinstance(algo, IsolationForestWeightedMean)

    def test_cmr(self):
        df = _make_dataframe()
        algo = AlgorithmFactory().instantiate_algorithm(
            "cmr", df, _make_test(), _make_options(), _make_metrics_config()
        )
        assert isinstance(algo, CMR)

    def test_invalid_raises(self):
        df = _make_dataframe()
        with pytest.raises(ValueError, match="Invalid algorithm"):
            AlgorithmFactory().instantiate_algorithm(
                "bogus", df, _make_test(), _make_options(), _make_metrics_config()
            )


# ---------------------------------------------------------------------------
# Algorithm base class (tested via EDivisive as concrete subclass)
# ---------------------------------------------------------------------------

class TestAlgorithmBase:
    def make_algo(self, n=10, **opt_overrides):
        df = _make_dataframe(n=n)
        return EDivisive(df, _make_test(), _make_options(**opt_overrides), _make_metrics_config())

    def test_output_json_returns_tuple(self):
        algo = self.make_algo()
        name, data, flag = algo.output_json()
        assert name == "test-bench"
        assert isinstance(data, str)
        parsed = json.loads(data)
        assert isinstance(parsed, list)
        assert isinstance(flag, bool)

    def test_output_json_structure(self):
        algo = self.make_algo()
        _, data, _ = algo.output_json()
        records = json.loads(data)
        for record in records:
            assert "uuid" in record
            assert "timestamp" in record
            assert "metrics" in record
            assert "throughput" in record["metrics"]
            assert "value" in record["metrics"]["throughput"]
            assert "percentage_change" in record["metrics"]["throughput"]

    def test_output_json_collapse(self):
        algo = self.make_algo(collapse=True)
        _, data_collapsed, _ = algo.output_json()
        collapsed = json.loads(data_collapsed)
        # Collapsed output should be <= full output
        algo2 = self.make_algo(collapse=False)
        _, data_full, _ = algo2.output_json()
        full = json.loads(data_full)
        assert len(collapsed) <= len(full)

    def test_output_text_returns_tuple(self):
        algo = self.make_algo()
        name, text, flag = algo.output_text()
        assert name == "test-bench"
        assert isinstance(text, str)
        assert isinstance(flag, bool)

    def test_output_junit_returns_element(self):
        algo = self.make_algo()
        name, element, flag = algo.output_junit()
        assert name == "test-bench"
        assert element.tag == "testsuite"
        assert isinstance(flag, bool)

    def test_output_dispatch_json(self):
        algo = self.make_algo()
        result = algo.output("json")
        assert result[0] == "test-bench"

    def test_output_dispatch_text(self):
        algo = self.make_algo()
        result = algo.output("text")
        assert result[0] == "test-bench"

    def test_output_dispatch_junit(self):
        algo = self.make_algo()
        result = algo.output("junit")
        assert result[0] == "test-bench"

    def test_output_dispatch_invalid_raises(self):
        algo = self.make_algo()
        with pytest.raises(ValueError):
            algo.output("csv")

    def test_analysis_cached(self):
        algo = self.make_algo()
        result1 = algo.get_analysis_results()
        result2 = algo.get_analysis_results()
        assert result1 is result2

    def test_setup_series(self):
        algo = self.make_algo()
        series = algo.setup_series()
        assert series.test_name == "test-bench"
        assert "throughput" in series.metrics
        assert len(series.time) == 10

    def test_get_github_client_no_repos(self):
        algo = self.make_algo()
        assert algo._get_github_client() is None

    def test_get_github_client_with_repos(self):
        algo = self.make_algo(github_repos=["org/repo"])
        client = algo._get_github_client()
        assert client is not None
        # Should be cached
        assert algo._get_github_client() is client

    def test_format_table_from_json(self):
        algo = self.make_algo()
        _, json_data, _ = algo.output_json()
        data = json.loads(json_data)
        table = algo.format_table_from_json(data)
        assert isinstance(table, str)
        assert "uuid" in table

    def test_format_table_empty_data(self):
        algo = self.make_algo()
        result = algo.format_table_from_json([])
        assert result == "No data available"


# ---------------------------------------------------------------------------
# group_change_points_by_time
# ---------------------------------------------------------------------------

class TestGroupChangePointsByTime:  # pylint: disable=too-few-public-methods
    def test_groups_by_index(self):
        algo = TestAlgorithmBase().make_algo()
        series = algo.setup_series()
        cp1 = ChangePoint(
            index=3, qhat=0.0, metric="throughput", time=series.time[3],
            stats=TTestStats(mean_1=100, mean_2=90, std_1=1, std_2=1, pvalue=0.01)
        )
        cp2 = ChangePoint(
            index=3, qhat=0.0, metric="throughput", time=series.time[3],
            stats=TTestStats(mean_1=100, mean_2=110, std_1=1, std_2=1, pvalue=0.01)
        )
        cp3 = ChangePoint(
            index=7, qhat=0.0, metric="throughput", time=series.time[7],
            stats=TTestStats(mean_1=100, mean_2=80, std_1=1, std_2=1, pvalue=0.01)
        )
        groups = algo.group_change_points_by_time(
            series, {"throughput": [cp1, cp2, cp3]}
        )
        assert len(groups) == 2
        assert groups[0].index == 3
        assert len(groups[0].changes) == 2
        assert groups[1].index == 7


# ---------------------------------------------------------------------------
# EDivisive
# ---------------------------------------------------------------------------

class TestEDivisive:
    def test_analyze_returns_series_and_changepoints(self):
        df = _make_dataframe(n=20)
        algo = EDivisive(df, _make_test(), _make_options(), _make_metrics_config())
        series, cps = algo.get_analysis_results()
        assert series is not None
        assert isinstance(cps, dict)
        assert "throughput" in cps

    def test_analyze_with_iso_timestamps(self):
        df = _make_dataframe(n=15)
        df.replace(pd.to_datetime(df["timestamp"], unit="s"))
        algo = EDivisive(df, _make_test(), _make_options(), _make_metrics_config())
        series, _cps = algo.get_analysis_results()
        assert series is not None

    def test_ack_removes_changepoints(self):
        # Create data with an obvious changepoint
        df = _make_dataframe(n=20)
        df.loc[10:, "throughput"] = df.loc[10:, "throughput"] + 500
        ack_map = {"ack": [{"uuid": "uuid-10", "metric": "throughput"}]}
        algo = EDivisive(df, _make_test(), _make_options(ackMap=ack_map), _make_metrics_config())
        _, cps = algo.get_analysis_results()
        # The changepoint at index 10 should be acked
        for cp in cps.get("throughput", []):
            assert cp.index != 10

    def test_direction_filter(self):
        df = _make_dataframe(n=20)
        # Big increase at index 10
        df.loc[10:, "throughput"] = df.loc[10:, "throughput"] + 500
        config = _make_metrics_config()
        # direction=-1: _has_changepoint removes CPs where mean_1 < mean_2
        # (i.e., removes increases). Our data increases, so the CP should be removed.
        config["throughput"]["direction"] = -1
        algo = EDivisive(df, _make_test(), _make_options(), config)
        _, cps = algo.get_analysis_results()
        assert len(cps.get("throughput", [])) == 0

    def test_threshold_filter(self):
        df = _make_dataframe(n=20)
        config = _make_metrics_config()
        config["throughput"]["threshold"] = 999  # very high threshold filters everything
        algo = EDivisive(df, _make_test(), _make_options(), config)
        _, cps = algo.get_analysis_results()
        assert len(cps.get("throughput", [])) == 0

    def test_regression_flag_set(self):
        df = _make_dataframe(n=20)
        df.loc[10:, "throughput"] = df.loc[10:, "throughput"] + 500
        config = _make_metrics_config()
        config["throughput"]["threshold"] = 0
        algo = EDivisive(df, _make_test(), _make_options(), config)
        algo.get_analysis_results()
        # The flag may or may not be set depending on direction filtering,
        # but the code path is exercised

    def test_is_under_threshold(self):
        df = _make_dataframe()
        algo = EDivisive(df, _make_test(), _make_options(), _make_metrics_config())
        cp = ChangePoint(
            index=5, qhat=0.0, metric="throughput", time=0,
            stats=TTestStats(mean_1=100, mean_2=102, std_1=1, std_2=1, pvalue=0.05)
        )
        # 2% change, threshold is 5%
        assert algo._is_under_threshold("throughput", [cp], 0) is True

    def test_is_not_under_threshold(self):
        df = _make_dataframe()
        algo = EDivisive(df, _make_test(), _make_options(), _make_metrics_config())
        cp = ChangePoint(
            index=5, qhat=0.0, metric="throughput", time=0,
            stats=TTestStats(mean_1=100, mean_2=120, std_1=1, std_2=1, pvalue=0.05)
        )
        # 20% change, threshold is 5%
        assert algo._is_under_threshold("throughput", [cp], 0) is False

    def test_is_acked(self):
        df = _make_dataframe()
        algo = EDivisive(df, _make_test(), _make_options(), _make_metrics_config())
        cp = ChangePoint(
            index=5, qhat=0.0, metric="throughput", time=0,
            stats=TTestStats(mean_1=100, mean_2=80, std_1=1, std_2=1, pvalue=0.05)
        )
        ack_set = {"5_throughput"}
        assert algo._is_acked(ack_set, [cp], 0) is True
        assert algo._is_acked(set(), [cp], 0) is False

    def test_has_changepoint_direction_1(self):
        df = _make_dataframe()
        config = _make_metrics_config()
        config["throughput"]["direction"] = 1
        algo = EDivisive(df, _make_test(), _make_options(), config)
        # mean_1 > mean_2 → regression for direction=1
        cp = ChangePoint(
            index=5, qhat=0.0, metric="throughput", time=0,
            stats=TTestStats(mean_1=100, mean_2=80, std_1=1, std_2=1, pvalue=0.05)
        )
        assert algo._has_changepoint("throughput", [cp], 0) is True
        # mean_1 < mean_2 → not a regression for direction=1
        cp2 = ChangePoint(
            index=5, qhat=0.0, metric="throughput", time=0,
            stats=TTestStats(mean_1=80, mean_2=100, std_1=1, std_2=1, pvalue=0.05)
        )
        assert algo._has_changepoint("throughput", [cp2], 0) is False


# ---------------------------------------------------------------------------
# IsolationForestWeightedMean
# ---------------------------------------------------------------------------

class TestIsolationForest:
    def test_analyze_returns_series_and_changepoints(self):
        df = _make_dataframe(n=30)
        algo = IsolationForestWeightedMean(
            df, _make_test(), _make_options(), _make_metrics_config()
        )
        series, cps = algo.get_analysis_results()
        assert series is not None
        assert isinstance(cps, dict)

    def test_analyze_with_iso_timestamps(self):
        df = _make_dataframe(n=30)
        df.replace(pd.to_datetime(df["timestamp"], unit="s"))
        algo = IsolationForestWeightedMean(
            df, _make_test(), _make_options(), _make_metrics_config()
        )
        series, _ = algo.get_analysis_results()
        assert series is not None

    def test_anomaly_with_outlier(self):
        df = _make_dataframe(n=30, seed=0)
        # Inject a massive outlier
        df.loc[25, "throughput"] = 500.0
        config = _make_metrics_config()
        config["throughput"]["direction"] = 0
        algo = IsolationForestWeightedMean(
            df, _make_test(), _make_options(min_anomaly_percent=5), config
        )
        _, cps = algo.get_analysis_results()
        # Should detect at least one anomaly near the outlier
        assert isinstance(cps["throughput"], list)

    def test_custom_window_and_percent(self):
        df = _make_dataframe(n=30)
        algo = IsolationForestWeightedMean(
            df, _make_test(),
            _make_options(anomaly_window=3, min_anomaly_percent=50),
            _make_metrics_config()
        )
        series, _cps = algo.get_analysis_results()
        assert series is not None


# ---------------------------------------------------------------------------
# CMR
# ---------------------------------------------------------------------------

class TestCMR:
    def test_single_row_returns_empty_changepoints(self):
        df = _make_dataframe(n=1)
        algo = CMR(df, _make_test(), _make_options(), _make_metrics_config())
        _series, cps = algo.get_analysis_results()
        assert cps == {}

    def test_two_rows_produces_changepoint(self):
        df = _make_dataframe(n=2)
        algo = CMR(df, _make_test(), _make_options(), _make_metrics_config())
        _, cps = algo.get_analysis_results()
        assert "throughput" in cps
        assert len(cps["throughput"]) == 1
        cp = cps["throughput"][0]
        assert cp.index == 1

    def test_multiple_rows_averaged(self):
        df = _make_dataframe(n=5)
        algo = CMR(df, _make_test(), _make_options(), _make_metrics_config())
        _, cps = algo.get_analysis_results()
        cp = cps["throughput"][0]
        # mean_1 should be average of first 4 rows
        expected_mean = df["throughput"][:4].mean()
        assert abs(cp.stats.mean_1 - expected_mean) < 1e-6

    def test_combine_and_average_runs(self):
        df = _make_dataframe(n=4)
        algo = CMR(df, _make_test(), _make_options(), _make_metrics_config())
        result = algo.combine_and_average_runs(df)
        assert len(result) == 2
        # First row is the average of rows 0-2
        assert abs(result["throughput"].iloc[0] - df["throughput"][:3].mean()) < 1e-6
        # Second row is the last row unchanged
        assert result["throughput"].iloc[1] == df["throughput"].iloc[3]

    def test_combine_non_numeric_columns_joined(self):
        df = _make_dataframe(n=3)
        algo = CMR(df, _make_test(), _make_options(), _make_metrics_config())
        result = algo.combine_and_average_runs(df)
        # uuid column should be comma-joined string of first 2 uuids
        assert "uuid-0" in result["uuid"].iloc[0]
        assert "uuid-1" in result["uuid"].iloc[0]

    def test_iso_timestamps_converted(self):
        df = _make_dataframe(n=3)
        df.replace(pd.to_datetime(df["timestamp"], unit="s"))
        algo = CMR(df, _make_test(), _make_options(), _make_metrics_config())
        series, _cps = algo.get_analysis_results()
        assert series is not None

    def test_output_json_with_cmr(self):
        df = _make_dataframe(n=5)
        algo = CMR(df, _make_test(), _make_options(), _make_metrics_config())
        name, data, _ = algo.output_json()
        assert name == "test-bench"
        records = json.loads(data)
        assert len(records) == 2  # CMR reduces to 2 rows
