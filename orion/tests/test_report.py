"""
Unit tests for orion/reporting/report.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error

import json
import logging

import pytest
from otava.analysis import TTestStats
from otava.series import ChangePoint, ChangePointGroup, Metric, Series

from orion.logger import SingletonLogger
from orion.reporting.report import Report, ReportType


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


def _make_series(n=10, metrics_names=None):
    """Build a simple Series for testing."""
    if metrics_names is None:
        metrics_names = ["throughput"]
    timestamps = [1704067200 + i * 86400 for i in range(n)]
    data = {}
    metrics = {}
    for name in metrics_names:
        data[name] = [100.0 + i for i in range(n)]
        metrics[name] = Metric(direction=1, scale=1)
    return Series(
        test_name="test-bench",
        branch=None,
        time=timestamps,
        data=data,
        metrics=metrics,
        attributes={"uuid": [f"uuid-{i}" for i in range(n)]},
    )


def _make_stats(mean_1=100.0, mean_2=80.0):
    return TTestStats(mean_1=mean_1, mean_2=mean_2, std_1=5, std_2=5, pvalue=0.01)


def _make_changepoint_group(index=5, metric="throughput", mean_1=100.0, mean_2=80.0, time=0):
    cp = ChangePoint(
        index=index, qhat=0.0, metric=metric, time=time,
        stats=_make_stats(mean_1=mean_1, mean_2=mean_2),
    )
    return ChangePointGroup(
        index=index, time=time, prev_time=0,
        attributes={}, prev_attributes={}, changes=[cp],
    )


# ---------------------------------------------------------------------------
# ReportType
# ---------------------------------------------------------------------------

class TestReportType:
    def test_log_str(self):
        assert str(ReportType.LOG) == "log"

    def test_json_str(self):
        assert str(ReportType.JSON) == "json"

    def test_regressions_only_str(self):
        assert str(ReportType.REGRESSIONS_ONLY) == "regressions_only"

    def test_enum_values(self):
        assert ReportType.LOG.value == "log"
        assert ReportType.JSON.value == "json"
        assert ReportType.REGRESSIONS_ONLY.value == "regressions_only"


# ---------------------------------------------------------------------------
# Report — produce_report dispatching
# ---------------------------------------------------------------------------

class TestProduceReport:
    def test_log_report(self):
        series = _make_series()
        report = Report(series, [])
        result = report.produce_report("test-bench", ReportType.LOG)
        assert isinstance(result, str)
        assert "time" in result

    def test_json_report_no_changepoints(self):
        series = _make_series()
        report = Report(series, [])
        result = report.produce_report("test-bench", ReportType.JSON)
        parsed = json.loads(result)
        assert "test-bench" in parsed
        assert parsed["test-bench"] == []

    def test_json_report_with_changepoints(self):
        series = _make_series()
        cpg = _make_changepoint_group(index=5, time=series.time[5])
        report = Report(series, [cpg])
        result = report.produce_report("test-bench", ReportType.JSON)
        parsed = json.loads(result)
        assert len(parsed["test-bench"]) == 1

    def test_regressions_only_no_regressions(self):
        series = _make_series()
        report = Report(series, [])
        result = report.produce_report("test-bench", ReportType.REGRESSIONS_ONLY)
        assert "No regressions" in result

    def test_regressions_only_with_regression(self):
        series = _make_series()
        # direction=1 and mean_1 > mean_2 → forward_change is negative → regression
        cpg = _make_changepoint_group(index=5, time=series.time[5], mean_1=100, mean_2=80)
        report = Report(series, [cpg])
        result = report.produce_report("test-bench", ReportType.REGRESSIONS_ONLY)
        assert "Regressions in test-bench" in result
        assert "throughput" in result


# ---------------------------------------------------------------------------
# Report — LOG format details
# ---------------------------------------------------------------------------

class TestLogFormat:
    def test_log_contains_timestamps(self):
        series = _make_series()
        report = Report(series, [])
        result = report.produce_report("test-bench", ReportType.LOG)
        assert "2024" in result

    def test_log_contains_metric_values(self):
        series = _make_series()
        report = Report(series, [])
        result = report.produce_report("test-bench", ReportType.LOG)
        assert "100" in result

    def test_log_with_changepoint_annotation(self):
        series = _make_series()
        cpg = _make_changepoint_group(index=5, time=series.time[5])
        report = Report(series, [cpg])
        result = report.produce_report("test-bench", ReportType.LOG)
        # Annotated log should have separator lines with percentage
        assert "%" in result

    def test_log_multiple_metrics(self):
        series = _make_series(metrics_names=["throughput", "latency"])
        report = Report(series, [])
        result = report.produce_report("test-bench", ReportType.LOG)
        assert "throughput" in result
        assert "latency" in result

    def test_column_group_size(self):
        """Custom column_group_size splits metrics into groups."""
        names = [f"metric_{i}" for i in range(8)]
        series = _make_series(metrics_names=names)
        report = Report(series, [], column_group_size=3)
        result = report.produce_report("test-bench", ReportType.LOG)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Report — regressions_only format details
# ---------------------------------------------------------------------------

class TestRegressionsOnlyFormat:
    def test_no_regression_when_direction_matches(self):
        """If change is in the "good" direction, it's not a regression."""
        series = _make_series()
        # direction=1 and mean_1 < mean_2 → increase → not a regression
        cpg = _make_changepoint_group(index=5, time=series.time[5], mean_1=80, mean_2=100)
        report = Report(series, [cpg])
        result = report.produce_report("test-bench", ReportType.REGRESSIONS_ONLY)
        assert "No regressions" in result

    def test_multiple_changepoints(self):
        series = _make_series()
        cpg1 = _make_changepoint_group(index=3, time=series.time[3], mean_1=100, mean_2=80)
        cpg2 = _make_changepoint_group(index=7, time=series.time[7], mean_1=90, mean_2=70)
        report = Report(series, [cpg1, cpg2])
        result = report.produce_report("test-bench", ReportType.REGRESSIONS_ONLY)
        assert "Regressions" in result
        # Should have two timestamp lines
        assert result.count("2024") >= 2


# ---------------------------------------------------------------------------
# Report — __column_widths (static method, tested via annotated log)
# ---------------------------------------------------------------------------

class TestColumnWidths:
    def test_column_widths_from_log(self):
        """Verify __column_widths parses table headers correctly."""
        lines = [
            "",
            "time  uuid  throughput",
            "----  ----  ----------",
            "2024  u1    100",
        ]
        width_groups, time_indexes = Report._Report__column_widths(lines)
        assert len(width_groups) == 1
        assert time_indexes == [1]
        assert len(width_groups[0]) == 3

    def test_no_tables(self):
        lines = ["no tables here", "just text"]
        width_groups, time_indexes = Report._Report__column_widths(lines)
        assert width_groups == []
        assert time_indexes == []

    def test_multiple_tables(self):
        lines = [
            "",
            "time  uuid  metric_a",
            "----  ----  --------",
            "2024  u1    100",
            "",
            "time  uuid  metric_b",
            "----  ----  --------",
            "2024  u1    200",
        ]
        width_groups, time_indexes = Report._Report__column_widths(lines)
        assert len(width_groups) == 2
        assert len(time_indexes) == 2


# ---------------------------------------------------------------------------
# Report — __increment_time_indexes_after
# ---------------------------------------------------------------------------

class TestIncrementTimeIndexes:
    def test_increments_after_group(self):
        indexes = [0, 5, 10, 15]
        Report._Report__increment_time_indexes_after(indexes, 1, amount=3)
        assert indexes == [0, 5, 13, 18]

    def test_no_increment_on_last(self):
        indexes = [0, 5]
        Report._Report__increment_time_indexes_after(indexes, 1, amount=1)
        assert indexes == [0, 5]

    def test_increment_from_first(self):
        indexes = [0, 5, 10]
        Report._Report__increment_time_indexes_after(indexes, 0, amount=2)
        assert indexes == [0, 7, 12]
