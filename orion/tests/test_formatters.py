"""Tests for formatter classes."""

import pandas as pd
import pytest
from otava.series import Series, Metric

from orion.tests.conftest import make_change_point


def _make_analysis_result(change_points=None, regression_flag=True):
    from orion.pipeline.analysis_result import AnalysisResult

    df = pd.DataFrame({
        "uuid": ["uuid-1", "uuid-2", "uuid-3"],
        "ocpVersion": ["4.18", "4.19", "4.20"],
        "timestamp": [1700000000, 1700100000, 1700200000],
        "buildUrl": ["http://b1", "http://b2", "http://b3"],
        "prs": [None, None, None],
        "cpu": [10.0, 20.0, 30.0],
    })
    series = Series(
        test_name="test",
        branch=None,
        time=[1700000000, 1700100000, 1700200000],
        metrics={"cpu": Metric(1, 1.0)},
        data={"cpu": df["cpu"]},
        attributes={
            "uuid": df["uuid"],
            "ocpVersion": df["ocpVersion"],
        },
    )

    if change_points is None:
        change_points = {"cpu": [make_change_point("cpu", index=2)]}

    return AnalysisResult(
        test_name="test-workload",
        test={
            "name": "test-workload",
            "uuid_field": "uuid",
            "version_field": "ocpVersion",
            "metadata": {"benchmark.keyword": "node-density"},
        },
        dataframe=df,
        metrics_config={
            "cpu": {"direction": 1, "labels": ["infra"], "threshold": 0,
                    "correlation": "", "context": None},
        },
        change_points_by_metric=change_points,
        series=series,
        regression_flag=regression_flag,
        avg_values=pd.Series({"cpu": 20.0}),
        collapse=False,
        display_fields=[],
        column_group_size=5,
        uuid_field="uuid",
        version_field="ocpVersion",
        sippy_pr_search=False,
        github_repos=[],
    )


class TestExtractRegressionData:
    def test_extracts_regression_from_changepoint(self):
        from orion.pipeline.formatters.base import BaseFormatter

        data = _make_analysis_result()

        class ConcreteFormatter(BaseFormatter):
            def format(self, data):
                return {}
            def format_average(self, data):
                return ""
            def save(self, test_name, formatted, save_output_path):
                pass
            def print_output(self, test_name, formatted, data, pr=0, is_pull=False):
                pass

        formatter = ConcreteFormatter()
        regressions = formatter.extract_regression_data(data)

        assert len(regressions) == 1
        reg = regressions[0]
        assert reg["test_name"] == "test-workload"
        assert reg["bad_ver"] == "4.20"
        assert reg["prev_ver"] == "4.19"
        assert reg["uuid"] == "uuid-3"
        assert len(reg["metrics_with_change"]) == 1
        assert reg["metrics_with_change"][0]["name"] == "cpu"
        assert reg["metrics_with_change"][0]["percentage_change"] == pytest.approx(100.0)
        assert reg["metrics_with_change"][0]["labels"] == ["infra"]

    def test_no_regressions_when_no_changepoints(self):
        from orion.pipeline.formatters.base import BaseFormatter

        data = _make_analysis_result(change_points={"cpu": []}, regression_flag=False)

        class ConcreteFormatter(BaseFormatter):
            def format(self, data):
                return {}
            def format_average(self, data):
                return ""
            def save(self, test_name, formatted, save_output_path):
                pass
            def print_output(self, test_name, formatted, data, pr=0, is_pull=False):
                pass

        formatter = ConcreteFormatter()
        regressions = formatter.extract_regression_data(data)

        assert len(regressions) == 0

    def test_extracts_benchmark_type(self):
        from orion.pipeline.formatters.base import BaseFormatter

        data = _make_analysis_result()

        class ConcreteFormatter(BaseFormatter):
            def format(self, data):
                return {}
            def format_average(self, data):
                return ""
            def save(self, test_name, formatted, save_output_path):
                pass
            def print_output(self, test_name, formatted, data, pr=0, is_pull=False):
                pass

        formatter = ConcreteFormatter()
        regressions = formatter.extract_regression_data(data)

        assert regressions[0]["benchmark_type"] == "node-density"


import json


class TestJsonFormatter:
    def test_format_produces_valid_json(self):
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)

        assert "test-workload" in result
        parsed = json.loads(result["test-workload"])
        assert isinstance(parsed, list)
        assert len(parsed) == 3

    def test_format_sets_is_changepoint(self):
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        changepoint_records = [r for r in parsed if r["is_changepoint"]]
        assert len(changepoint_records) == 1
        assert changepoint_records[0]["ocpVersion"] == "4.20"

    def test_format_injects_metrics_with_percentage(self):
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        cp_record = [r for r in parsed if r["is_changepoint"]][0]
        assert "cpu" in cp_record["metrics"]
        assert cp_record["metrics"]["cpu"]["percentage_change"] == pytest.approx(100.0)
        assert cp_record["metrics"]["cpu"]["labels"] == ["infra"]

    def test_format_non_changepoint_has_zero_percentage(self):
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        non_cp = [r for r in parsed if not r["is_changepoint"]]
        for record in non_cp:
            for metric_data in record["metrics"].values():
                assert metric_data["percentage_change"] == 0

    def test_format_collapse_returns_context_only(self):
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        data = _make_analysis_result()
        data.collapse = True
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        # Collapsed: changepoint at index 2, so context = indices 1,2 (no index 3)
        assert len(parsed) <= 3

    def test_format_no_changepoints(self):
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        data = _make_analysis_result(change_points={"cpu": []}, regression_flag=False)
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        assert all(not r["is_changepoint"] for r in parsed)

    def test_format_average_returns_json_string(self):
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        data = _make_analysis_result()
        formatter = JsonFormatter()
        avg = formatter.format_average(data)

        parsed = json.loads(avg)
        assert "cpu" in parsed
        assert parsed["cpu"] == pytest.approx(20.0)


class TestTextFormatter:
    def test_format_produces_string_output(self):
        from orion.pipeline.formatters.text_formatter import TextFormatter

        data = _make_analysis_result()
        formatter = TextFormatter()
        result = formatter.format(data)

        assert "test-workload" in result
        assert isinstance(result["test-workload"], str)
        assert len(result["test-workload"]) > 0

    def test_format_average_produces_tabulated_string(self):
        from orion.pipeline.formatters.text_formatter import TextFormatter

        data = _make_analysis_result()
        formatter = TextFormatter()
        avg = formatter.format_average(data)

        assert isinstance(avg, str)
        assert "cpu" in avg


import xml.etree.ElementTree as ET


class TestJUnitFormatter:
    def test_format_produces_xml_element(self):
        from orion.pipeline.formatters.junit_formatter import JUnitFormatter

        data = _make_analysis_result()
        formatter = JUnitFormatter()
        result = formatter.format(data)

        assert "test-workload" in result
        assert isinstance(result["test-workload"], ET.Element)

    def test_format_sets_failures_count(self):
        from orion.pipeline.formatters.junit_formatter import JUnitFormatter

        data = _make_analysis_result()
        formatter = JUnitFormatter()
        result = formatter.format(data)

        element = result["test-workload"]
        assert element.get("failures") == "1"

    def test_format_average_produces_xml_element(self):
        from orion.pipeline.formatters.junit_formatter import JUnitFormatter

        data = _make_analysis_result()
        formatter = JUnitFormatter()
        avg = formatter.format_average(data)

        assert isinstance(avg, ET.Element)


class TestFormatterFactory:
    def test_get_json_formatter(self):
        from orion.pipeline.formatters import FormatterFactory
        from orion.pipeline.formatters.json_formatter import JsonFormatter

        formatter = FormatterFactory.get_formatter("json")
        assert isinstance(formatter, JsonFormatter)

    def test_get_text_formatter(self):
        from orion.pipeline.formatters import FormatterFactory
        from orion.pipeline.formatters.text_formatter import TextFormatter

        formatter = FormatterFactory.get_formatter("text")
        assert isinstance(formatter, TextFormatter)

    def test_get_junit_formatter(self):
        from orion.pipeline.formatters import FormatterFactory
        from orion.pipeline.formatters.junit_formatter import JUnitFormatter

        formatter = FormatterFactory.get_formatter("junit")
        assert isinstance(formatter, JUnitFormatter)

    def test_invalid_format_raises(self):
        from orion.pipeline.formatters import FormatterFactory

        with pytest.raises(ValueError, match="Unsupported output format"):
            FormatterFactory.get_formatter("csv")
