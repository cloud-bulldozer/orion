"""
Unit tests for orion/run_test.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error
# pylint: disable = missing-class-docstring
# pylint: disable = import-outside-toplevel

import logging
from unittest.mock import MagicMock, patch

import pytest

from orion.logger import SingletonLogger
from otava.series import ChangePoint

from orion.run_test import (
    TestResults,
    clear_early_changepoints_raw,
    get_algorithm_type,
    get_start_timestamp,
    has_early_changepoint_raw,
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
# has_early_changepoint_raw
# ---------------------------------------------------------------------------

def _cp(index, metric="cpu"):
    return ChangePoint(index=index, qhat=1.0, stats=None, metric=metric, time=0)


class TestHasEarlyChangepoint:
    def test_no_changepoints(self):
        assert has_early_changepoint_raw({"cpu": []}) is False

    def test_changepoint_at_index_0(self):
        assert has_early_changepoint_raw({"cpu": [_cp(0)]}) is True

    def test_changepoint_at_index_4(self):
        assert has_early_changepoint_raw({"cpu": [_cp(4)]}) is True

    def test_changepoint_at_index_5_not_early(self):
        assert has_early_changepoint_raw({"cpu": [_cp(5)]}) is False

    def test_custom_buffer(self):
        data = {"cpu": [_cp(2)]}
        assert has_early_changepoint_raw(data, max_early_index=2) is False
        assert has_early_changepoint_raw(data, max_early_index=3) is True

    def test_multiple_metrics(self):
        data = {"cpu": [_cp(10)], "mem": [_cp(1)]}
        assert has_early_changepoint_raw(data) is True

    def test_empty_dict(self):
        assert has_early_changepoint_raw({}) is False


# ---------------------------------------------------------------------------
# clear_early_changepoints_raw
# ---------------------------------------------------------------------------

class TestClearEarlyChangepoints:
    def test_clears_early_changepoints(self):
        data = {"cpu": [_cp(1), _cp(6)]}
        result = clear_early_changepoints_raw(data, max_early_index=5)
        assert len(result["cpu"]) == 1
        assert result["cpu"][0].index == 6

    def test_does_not_clear_beyond_buffer(self):
        data = {"cpu": [_cp(5), _cp(7)]}
        result = clear_early_changepoints_raw(data, max_early_index=5)
        assert len(result["cpu"]) == 2

    def test_clears_all_early(self):
        data = {"cpu": [_cp(0), _cp(2), _cp(4)]}
        result = clear_early_changepoints_raw(data, max_early_index=5)
        assert len(result["cpu"]) == 0

    def test_empty_dict(self):
        result = clear_early_changepoints_raw({}, max_early_index=5)
        assert result == {}


# ---------------------------------------------------------------------------
# get_start_timestamp
# ---------------------------------------------------------------------------

class TestGetStartTimestamp:
    def test_unbounded_lookback(self):
        kwargs = {"_unbounded_lookback": True, "lookback": "30d", "since": ""}
        result = get_start_timestamp(kwargs, {}, is_pull=False)
        assert result == ""

    def test_lookback_only(self):
        kwargs = {"lookback": "5d", "since": None}
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
# NamedTuple structure tests
# ---------------------------------------------------------------------------

class TestNamedTuples:
    def test_test_results(self):
        r = TestResults(
            analyses=[],
            regression_flag=False,
            prs=[],
            viz_data=[],
        )
        assert r.prs == []
        assert r.regression_flag is False
        assert r.analyses == []
