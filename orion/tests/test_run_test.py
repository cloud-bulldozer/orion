"""
Unit tests for orion/run_test.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error

import json
import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from orion.logger import SingletonLogger
from orion.run_test import (
    AnalyzeResult,
    TestResults,
    clear_early_changepoints,
    get_algorithm_type,
    get_start_timestamp,
    has_early_changepoint,
    tabulate_average_values,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


# ---------------------------------------------------------------------------
# get_algorithm_type
# ---------------------------------------------------------------------------

class TestGetAlgorithmType:
    def test_hunter_analyze(self):
        assert get_algorithm_type({
            "hunter_analyze": True,
            "anomaly_detection": False,
            "cmr": False,
        }) == "EDivisive"

    def test_anomaly_detection(self):
        assert get_algorithm_type({
            "hunter_analyze": False,
            "anomaly_detection": True,
            "cmr": False,
        }) == "IsolationForest"

    def test_cmr(self):
        assert get_algorithm_type({
            "hunter_analyze": False,
            "anomaly_detection": False,
            "cmr": True,
        }) == "cmr"

    def test_none_when_all_false(self):
        assert get_algorithm_type({
            "hunter_analyze": False,
            "anomaly_detection": False,
            "cmr": False,
        }) is None

    def test_priority_hunter_over_anomaly(self):
        # hunter_analyze checked first
        assert get_algorithm_type({
            "hunter_analyze": True,
            "anomaly_detection": True,
            "cmr": True,
        }) == "EDivisive"


# ---------------------------------------------------------------------------
# has_early_changepoint
# ---------------------------------------------------------------------------

class TestHasEarlyChangepoint:
    def test_no_changepoints(self):
        data = [{"is_changepoint": False}] * 10
        assert has_early_changepoint(data) is False

    def test_changepoint_at_index_0(self):
        data = [{"is_changepoint": True}] + [{"is_changepoint": False}] * 9
        assert has_early_changepoint(data) is True

    def test_changepoint_at_index_4(self):
        data = [{"is_changepoint": False}] * 4 + [{"is_changepoint": True}] + [{"is_changepoint": False}] * 5
        assert has_early_changepoint(data) is True

    def test_changepoint_at_index_5_not_early(self):
        data = [{"is_changepoint": False}] * 5 + [{"is_changepoint": True}] + [{"is_changepoint": False}] * 4
        assert has_early_changepoint(data) is False

    def test_custom_buffer(self):
        data = [{"is_changepoint": False}] * 2 + [{"is_changepoint": True}]
        assert has_early_changepoint(data, max_early_index=2) is False
        assert has_early_changepoint(data, max_early_index=3) is True

    def test_missing_is_changepoint_key(self):
        data = [{"other_key": "value"}] * 5
        assert has_early_changepoint(data) is False

    def test_empty_list(self):
        assert has_early_changepoint([]) is False


# ---------------------------------------------------------------------------
# clear_early_changepoints
# ---------------------------------------------------------------------------

class TestClearEarlyChangepoints:
    def test_clears_early_changepoints(self):
        data = [
            {
                "is_changepoint": True,
                "metrics": {
                    "cpu": {"percentage_change": 15.0},
                    "mem": {"percentage_change": -5.0},
                },
            },
            {"is_changepoint": False, "metrics": {"cpu": {"percentage_change": 0}}},
        ]
        clear_early_changepoints(data, max_early_index=5)
        assert data[0]["is_changepoint"] is False
        assert data[0]["metrics"]["cpu"]["percentage_change"] == 0
        assert data[0]["metrics"]["mem"]["percentage_change"] == 0

    def test_does_not_clear_beyond_buffer(self):
        data = [{"is_changepoint": False}] * 5 + [
            {
                "is_changepoint": True,
                "metrics": {"cpu": {"percentage_change": 10.0}},
            }
        ]
        clear_early_changepoints(data, max_early_index=5)
        assert data[5]["is_changepoint"] is True
        assert data[5]["metrics"]["cpu"]["percentage_change"] == 10.0

    def test_no_metrics_key(self):
        data = [{"is_changepoint": True}]
        # Should not raise
        clear_early_changepoints(data, max_early_index=5)
        assert data[0]["is_changepoint"] is False

    def test_empty_list(self):
        data = []
        clear_early_changepoints(data, max_early_index=5)
        assert data == []


# ---------------------------------------------------------------------------
# get_start_timestamp
# ---------------------------------------------------------------------------

class TestGetStartTimestamp:
    def test_unbounded_lookback(self):
        kwargs = {"_unbounded_lookback": True, "lookback": "30d", "since": ""}
        result = get_start_timestamp(kwargs, {}, is_pull=False)
        assert result == ""

    def test_lookback_only(self):
        kwargs = {"lookback": "5d", "since": "", "since": None}
        result = get_start_timestamp(kwargs, {}, is_pull=False)
        assert result != ""  # Should be a datetime

    def test_no_lookback(self):
        kwargs = {"lookback": "", "since": None}
        result = get_start_timestamp(kwargs, {}, is_pull=False)
        assert result == ""

    def test_since_with_lookback(self):
        kwargs = {"lookback": "5d", "since": "2024-06-15"}
        result = get_start_timestamp(kwargs, {}, is_pull=False)
        assert result != ""

    def test_since_without_lookback(self):
        kwargs = {"since": "2024-06-15"}
        result = get_start_timestamp(kwargs, {}, is_pull=False)
        assert result == ""

    @patch("orion.run_test.GitHubClient")
    def test_pull_request_creation_date(self, mock_client_cls):
        from datetime import datetime, timezone
        mock_client = MagicMock()
        mock_client.get_pr_creation_date.return_value = datetime(
            2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc
        )
        mock_client_cls.return_value = mock_client
        kwargs = {"lookback": "30d", "since": None}
        test = {
            "metadata": {
                "organization": "org",
                "repository": "repo",
                "pullNumber": 42,
            }
        }
        result = get_start_timestamp(kwargs, test, is_pull=True)
        assert "2024-06-01" in result

    @patch("orion.run_test.GitHubClient")
    def test_pull_request_creation_date_none_falls_through(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get_pr_creation_date.return_value = None
        mock_client_cls.return_value = mock_client
        kwargs = {"lookback": "5d", "since": None}
        test = {
            "metadata": {
                "organization": "org",
                "repository": "repo",
                "pullNumber": 42,
            }
        }
        result = get_start_timestamp(kwargs, test, is_pull=True)
        # Falls through to lookback logic
        assert result != ""


# ---------------------------------------------------------------------------
# tabulate_average_values
# ---------------------------------------------------------------------------

class TestTabulateAverageValues:
    def test_basic_output(self):
        avg_data = pd.Series({"throughput": 95.5, "latency": 12.3})
        last_row = pd.Series({
            "uuid": "abc-123",
            "ocpVersion": "4.14.0",
            "timestamp": "2024-01-01T00:00:00",
            "throughput": 100.0,
            "latency": 10.0,
        })
        result = tabulate_average_values(avg_data, last_row)
        assert "throughput" in result
        assert "latency" in result
        assert isinstance(result, str)

    def test_with_display_fields(self):
        avg_data = pd.Series({"throughput": 95.5})
        last_row = pd.Series({
            "uuid": "abc-123",
            "ocpVersion": "4.14.0",
            "build_tag": "nightly-123",
            "throughput": 100.0,
        })
        result = tabulate_average_values(
            avg_data, last_row, display_fields=["build_tag"]
        )
        assert "build_tag" in result

    def test_no_version_field(self):
        avg_data = pd.Series({"throughput": 95.5})
        last_row = pd.Series({
            "uuid": "abc-123",
            "throughput": 100.0,
        })
        result = tabulate_average_values(avg_data, last_row)
        assert isinstance(result, str)

    def test_custom_fields(self):
        avg_data = pd.Series({"metric_a": 50.0})
        last_row = pd.Series({
            "run_uuid": "u1",
            "cluster_version": "4.16",
            "metric_a": 55.0,
        })
        result = tabulate_average_values(
            avg_data, last_row,
            version_field="cluster_version",
            uuid_field="run_uuid",
        )
        assert "run_uuid" in result
        assert "cluster_version" in result


# ---------------------------------------------------------------------------
# NamedTuple structure tests
# ---------------------------------------------------------------------------

class TestNamedTuples:
    def test_analyze_result(self):
        r = AnalyzeResult(
            output={"test": "data"},
            regression_flag=True,
            regression_data=[{"metric": "cpu"}],
            average_values="avg",
            viz_data=None,
        )
        assert r.output == {"test": "data"}
        assert r.regression_flag is True
        assert len(r.regression_data) == 1

    def test_test_results(self):
        r = TestResults(
            output={"test": "data"},
            regression_flag=False,
            regression_data=[],
            average_values="",
            pr=0,
            viz_data=[],
        )
        assert r.pr == 0
        assert r.regression_flag is False
