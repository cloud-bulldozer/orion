# pylint: disable=missing-class-docstring,missing-function-docstring
"""Tests for dry_run metric support."""

import logging
from unittest.mock import MagicMock

import pytest

from main import auto_create_jira_issues
from orion.logger import SingletonLogger
from orion.run_test import all_changepoints_dry_run
from orion.tests.conftest import make_change_point
from orion.utils import Utils


class Testdry_runRegressionFlag:
    """Verify the production dry-run regression-suppression helper."""

    def test_all_dry_run_suppresses_regression(self):
        cps = {"cpu": [make_change_point("cpu", 2)]}
        config = {"cpu": {"dry_run": True, "direction": 1}}
        assert all_changepoints_dry_run(cps, config) is True

    def test_mixed_dry_run_does_not_suppress(self):
        cps = {
            "cpu": [make_change_point("cpu", 2)],
            "mem": [make_change_point("mem", 2)],
        }
        config = {
            "cpu": {"dry_run": True, "direction": 1},
            "mem": {"dry_run": False, "direction": 1},
        }
        assert all_changepoints_dry_run(cps, config) is False

    def test_no_dry_run_does_not_suppress(self):
        cps = {"cpu": [make_change_point("cpu", 2)]}
        config = {"cpu": {"dry_run": False, "direction": 1}}
        assert all_changepoints_dry_run(cps, config) is False

    def test_dry_run_default_false(self):
        cps = {"cpu": [make_change_point("cpu", 2)]}
        config = {"cpu": {"direction": 1}}
        assert all_changepoints_dry_run(cps, config) is False

    def test_empty_changepoints_not_affected(self):
        cps = {"cpu": []}
        config = {"cpu": {"dry_run": True, "direction": 1}}
        # No metrics with changepoints, so all() on empty is True,
        # but regression_flag would be False anyway (no changepoints)
        assert all_changepoints_dry_run(cps, config) is True


def _regression_with_metrics(metrics):
    """Build a regression_data entry with the given metrics_with_change."""
    return {
        "test_name": "node-density",
        "uuid": "uuid-dryrun",
        "bad_ver": "4.18",
        "prev_ver": "4.17",
        "metrics_with_change": metrics,
    }


class Testdry_runJiraSkip:
    """Verify the production Jira path skips dry-run metrics."""

    def test_dry_run_metric_skipped(self):
        provider = MagicMock()
        provider.create_ack.return_value = "PERF-1"
        regression_data = [_regression_with_metrics([
            {"name": "cpu", "percentage_change": 10.0, "dry_run": True},
            {"name": "mem", "percentage_change": 5.0, "dry_run": False},
        ])]
        created, _ = auto_create_jira_issues(regression_data, provider, MagicMock())
        # Only the non-dry-run metric should create a Jira issue.
        assert created == 1
        assert provider.create_ack.call_count == 1
        assert provider.create_ack.call_args.kwargs["metric"] == "mem"

    def test_all_dry_run_metrics_skipped(self):
        provider = MagicMock()
        provider.create_ack.return_value = "PERF-1"
        regression_data = [_regression_with_metrics([
            {"name": "cpu", "percentage_change": 10.0, "dry_run": True},
        ])]
        created, _ = auto_create_jira_issues(regression_data, provider, MagicMock())
        assert created == 0
        assert provider.create_ack.call_count == 0


class Testdry_runCorrelationValidation:
    """Dry-run metrics cannot be used as correlation targets."""

    @pytest.fixture(autouse=True)
    def _init_logger(self):
        SingletonLogger(debug=logging.DEBUG, name="Orion")

    def test_correlation_to_dry_run_metric_raises(self):
        utils = Utils()
        metrics = [
            {"name": "latency", "metricName": "p99",
             "metric_of_interest": "value", "direction": -1,
             "threshold": 5, "correlation": "cpu", "context": 3},
            {"name": "cpu", "metricName": "cpuUsage",
             "metric_of_interest": "value", "direction": 1,
             "threshold": 5, "correlation": "", "context": 3,
             "dry_run": True},
        ]
        match = MagicMock()
        with pytest.raises(ValueError, match="Dry-run metrics cannot be used as correlation targets"):
            utils.get_metric_data(["uuid1"], metrics, match, 5)

    def test_correlation_to_non_dry_run_metric_ok(self):
        utils = Utils()
        metrics = [
            {"name": "latency", "metricName": "p99",
             "metric_of_interest": "value", "direction": -1,
             "threshold": 5, "correlation": "cpu", "context": 3},
            {"name": "cpu", "metricName": "cpuUsage",
             "metric_of_interest": "value", "direction": 1,
             "threshold": 5, "correlation": "", "context": 3,
             "dry_run": False},
        ]
        match = MagicMock()
        match.get_results_batch.return_value = []
        utils.get_metric_data(["uuid1"], metrics, match, 5)

    def test_multiple_errors_reported_at_once(self):
        utils = Utils()
        metrics = [
            {"name": "latency", "metricName": "p99",
             "metric_of_interest": "value", "direction": -1,
             "threshold": 5, "correlation": "cpu", "context": 3},
            {"name": "throughput", "metricName": "rps",
             "metric_of_interest": "value", "direction": 1,
             "threshold": 5, "correlation": "cpu", "context": 3},
            {"name": "cpu", "metricName": "cpuUsage",
             "metric_of_interest": "value", "direction": 1,
             "threshold": 5, "correlation": "", "context": 3,
             "dry_run": True},
        ]
        match = MagicMock()
        with pytest.raises(ValueError, match="Metric configuration errors") as exc_info:
            utils.get_metric_data(["uuid1"], metrics, match, 5)
        assert "latency" in str(exc_info.value)
        assert "throughput" in str(exc_info.value)

    def test_dry_run_non_bool_raises(self):
        utils = Utils()
        metrics = [
            {"name": "cpu", "metricName": "cpuUsage",
             "metric_of_interest": "value", "direction": 1,
             "threshold": 5, "correlation": "", "context": 3,
             "dry_run": "yes"},
        ]
        match = MagicMock()
        with pytest.raises(ValueError, match="expected a boolean"):
            utils.get_metric_data(["uuid1"], metrics, match, 5)

    def test_dry_run_int_raises(self):
        utils = Utils()
        metrics = [
            {"name": "cpu", "metricName": "cpuUsage",
             "metric_of_interest": "value", "direction": 1,
             "threshold": 5, "correlation": "", "context": 3,
             "dry_run": 1},
        ]
        match = MagicMock()
        with pytest.raises(ValueError, match="expected a boolean"):
            utils.get_metric_data(["uuid1"], metrics, match, 5)
