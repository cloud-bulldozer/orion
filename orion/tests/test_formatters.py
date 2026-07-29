# pylint: disable=missing-class-docstring,missing-function-docstring
"""Tests for formatter classes."""

import json
import xml.etree.ElementTree as ET

import pandas as pd
import pytest
from otava.series import Series, Metric

from orion.confidence import ConfidenceResult
from orion.pipeline.analysis_result import AnalysisResult
from orion.pipeline.formatters import FormatterFactory
from orion.pipeline.formatters.base import BaseFormatter
from orion.pipeline.formatters.json_formatter import JsonFormatter
from orion.pipeline.formatters.junit_formatter import JUnitFormatter
from orion.pipeline.formatters.text_formatter import (
    TextFormatter,
    _format_comparison_table,
    _format_confidence_table,
)
from orion.tests.conftest import make_change_point


def _make_analysis_result(change_points=None, regression_flag=True):
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
            def print_and_save_pr(self, periodic, pulls, save_output_path):
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
            def print_and_save_pr(self, periodic, pulls, save_output_path):
                pass

        formatter = ConcreteFormatter()
        regressions = formatter.extract_regression_data(data)

        assert len(regressions) == 0

    def test_extracts_benchmark_type(self):
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
            def print_and_save_pr(self, periodic, pulls, save_output_path):
                pass

        formatter = ConcreteFormatter()
        regressions = formatter.extract_regression_data(data)

        assert regressions[0]["benchmark_type"] == "node-density"


class TestJsonFormatter:
    def test_format_produces_valid_json(self):
        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)

        assert "test-workload" in result
        parsed = json.loads(result["test-workload"])
        assert isinstance(parsed, list)
        assert len(parsed) == 3

    def test_format_sets_is_changepoint(self):
        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        changepoint_records = [r for r in parsed if r["is_changepoint"]]
        assert len(changepoint_records) == 1
        assert changepoint_records[0]["ocpVersion"] == "4.20"

    def test_format_injects_metrics_with_percentage(self):
        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        cp_record = [r for r in parsed if r["is_changepoint"]][0]
        assert "cpu" in cp_record["metrics"]
        assert cp_record["metrics"]["cpu"]["percentage_change"] == pytest.approx(100.0)
        assert cp_record["metrics"]["cpu"]["labels"] == ["infra"]

    def test_format_non_changepoint_has_zero_percentage(self):
        data = _make_analysis_result()
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        non_cp = [r for r in parsed if not r["is_changepoint"]]
        for record in non_cp:
            for metric_data in record["metrics"].values():
                assert metric_data["percentage_change"] == 0

    def test_format_collapse_returns_context_only(self):
        data = _make_analysis_result()
        data.collapse = True
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        # Collapsed: changepoint at index 2, so context = indices 1,2 (no index 3)
        assert len(parsed) <= 3

    def test_format_no_changepoints(self):
        data = _make_analysis_result(change_points={"cpu": []}, regression_flag=False)
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])

        assert all(not r["is_changepoint"] for r in parsed)

    def test_format_average_returns_json_string(self):
        data = _make_analysis_result()
        formatter = JsonFormatter()
        avg = formatter.format_average(data)

        parsed = json.loads(avg)
        assert "cpu" in parsed
        assert parsed["cpu"] == pytest.approx(20.0)


class TestTextFormatter:
    def test_format_produces_string_output(self):
        data = _make_analysis_result()
        formatter = TextFormatter()
        result = formatter.format(data)

        assert "test-workload" in result
        assert isinstance(result["test-workload"], str)
        assert len(result["test-workload"]) > 0

    def test_format_average_produces_tabulated_string(self):
        data = _make_analysis_result()
        formatter = TextFormatter()
        avg = formatter.format_average(data)

        assert isinstance(avg, str)
        assert "cpu" in avg


class TestJUnitFormatter:
    def test_format_produces_xml_element(self):
        data = _make_analysis_result()
        formatter = JUnitFormatter()
        result = formatter.format(data)

        assert "test-workload" in result
        assert isinstance(result["test-workload"], ET.Element)

    def test_format_sets_failures_count(self):
        data = _make_analysis_result()
        formatter = JUnitFormatter()
        result = formatter.format(data)

        element = result["test-workload"]
        assert element.get("failures") == "1"

    def test_format_average_produces_xml_element(self):
        data = _make_analysis_result()
        formatter = JUnitFormatter()
        avg = formatter.format_average(data)

        assert isinstance(avg, ET.Element)


def _make_pull_analysis(cpu_values, test_name="test-workload"):
    """Build a minimal pull AnalysisResult with given cpu values."""
    n = len(cpu_values)
    df = pd.DataFrame({
        "uuid": [f"pr-uuid-{i}" for i in range(n)],
        "ocpVersion": ["4.18"] * n,
        "timestamp": [1700000000 + i * 100000 for i in range(n)],
        "buildUrl": [f"http://pr-b{i}" for i in range(n)],
        "prs": [None] * n,
        "cpu": cpu_values,
    })
    series = Series(
        test_name="test",
        branch=None,
        time=list(df["timestamp"]),
        metrics={"cpu": Metric(1, 1.0)},
        data={"cpu": df["cpu"]},
        attributes={
            "uuid": df["uuid"],
            "ocpVersion": df["ocpVersion"],
        },
    )
    return AnalysisResult(
        test_name=test_name,
        test={"name": test_name, "uuid_field": "uuid",
              "version_field": "ocpVersion", "metadata": {}},
        dataframe=df,
        metrics_config={
            "cpu": {"direction": 1, "labels": ["infra"], "threshold": 0,
                    "correlation": "", "context": None},
        },
        change_points_by_metric={"cpu": []},
        series=series,
        regression_flag=False,
        avg_values=pd.Series({"cpu": sum(cpu_values) / len(cpu_values)}),
        collapse=False,
        display_fields=[],
        column_group_size=5,
        uuid_field="uuid",
        version_field="ocpVersion",
        sippy_pr_search=False,
        github_repos=[],
    )


class TestMultiPrJson:
    def test_json_pr_output_has_pulls_list(self, tmp_path):
        periodic = _make_analysis_result()
        pull_a = _make_pull_analysis([15.0, 25.0])
        pull_b = _make_pull_analysis([12.0, 22.0])
        pulls = [(1111, pull_a), (2222, pull_b)]

        formatter = JsonFormatter()
        save_path = str(tmp_path / "output.json")
        formatter.print_and_save_pr(periodic, pulls, save_path)

        with open(str(tmp_path / "output_test-workload.json"),
                  encoding="utf-8") as f:
            result = json.loads(f.read())

        assert "pulls" in result
        assert isinstance(result["pulls"], list)
        assert len(result["pulls"]) == 2
        assert result["pulls"][0]["pr"] == 1111
        assert result["pulls"][1]["pr"] == 2222
        assert isinstance(result["pulls"][0]["data"], list)
        assert isinstance(result["pulls"][1]["data"], list)

    def test_json_pr_output_with_none_pull(self, tmp_path):
        periodic = _make_analysis_result()
        pull_a = _make_pull_analysis([15.0])
        pulls = [(1111, pull_a), (2222, None)]

        formatter = JsonFormatter()
        save_path = str(tmp_path / "output.json")
        formatter.print_and_save_pr(periodic, pulls, save_path)

        with open(str(tmp_path / "output_test-workload.json"),
                  encoding="utf-8") as f:
            result = json.loads(f.read())

        assert len(result["pulls"]) == 2
        assert result["pulls"][1]["pr"] == 2222
        assert result["pulls"][1]["data"] == []

    def test_json_single_pr_backward_compat(self, tmp_path):
        periodic = _make_analysis_result()
        pull = _make_pull_analysis([18.0, 28.0])
        pulls = [(3333, pull)]

        formatter = JsonFormatter()
        save_path = str(tmp_path / "output.json")
        formatter.print_and_save_pr(periodic, pulls, save_path)

        with open(str(tmp_path / "output_test-workload.json"),
                  encoding="utf-8") as f:
            result = json.loads(f.read())

        assert len(result["pulls"]) == 1
        assert result["pulls"][0]["pr"] == 3333
        assert "periodic" in result
        assert "periodic_avg" in result


class TestMultiPrText:
    def test_comparison_table_has_multiple_pr_columns(self):
        periodic = _make_analysis_result()
        pull_a = _make_pull_analysis([15.0, 25.0])
        pull_b = _make_pull_analysis([12.0, 22.0])
        pulls = [(1111, pull_a), (2222, pull_b)]

        table = _format_comparison_table(periodic, pulls)

        assert "PR#1111" in table
        assert "PR#2222" in table
        assert "cpu" in table

    def test_comparison_table_single_pr(self):
        periodic = _make_analysis_result()
        pull = _make_pull_analysis([18.0])
        pulls = [(5555, pull)]

        table = _format_comparison_table(periodic, pulls)

        assert "PR#5555" in table

    def test_comparison_table_with_none_pull(self):
        periodic = _make_analysis_result()
        pull_a = _make_pull_analysis([15.0])
        pulls = [(1111, pull_a), (2222, None)]

        table = _format_comparison_table(periodic, pulls)

        assert "PR#1111" in table
        assert "PR#2222" in table
        lines = table.strip().split("\n")
        data_line = [line for line in lines if "cpu" in line][0]
        assert "-" in data_line

    def test_comparison_table_empty_pulls_list(self):
        periodic = _make_analysis_result()

        table = _format_comparison_table(periodic, [])

        assert "PR" not in table
        assert "cpu" in table

    def test_comparison_table_header_says_baseline_avg(self):
        periodic = _make_analysis_result()

        table = _format_comparison_table(periodic, [])

        assert "Baseline AVG" in table

    def test_baseline_avg_excludes_post_changepoint(self):
        df = pd.DataFrame({
            "uuid": ["u1", "u2", "u3", "u4"],
            "ocpVersion": ["4.17", "4.18", "4.19", "4.20"],
            "timestamp": [1700000000, 1700100000, 1700200000, 1700300000],
            "buildUrl": ["http://b1", "http://b2", "http://b3", "http://b4"],
            "prs": [None, None, None, None],
            "cpu": [10.0, 20.0, 100.0, 200.0],
        })
        series = Series(
            test_name="test",
            branch=None,
            time=list(df["timestamp"]),
            metrics={"cpu": Metric(1, 1.0)},
            data={"cpu": df["cpu"]},
            attributes={
                "uuid": df["uuid"],
                "ocpVersion": df["ocpVersion"],
            },
        )
        # Changepoint at index 2 — baseline avg should be (10+20)/2 = 15
        data = AnalysisResult(
            test_name="test-workload",
            test={"name": "test-workload", "uuid_field": "uuid",
                  "version_field": "ocpVersion",
                  "metadata": {"benchmark.keyword": "test"}},
            dataframe=df,
            metrics_config={
                "cpu": {"direction": 1, "labels": [], "threshold": 0,
                        "correlation": "", "context": None},
            },
            change_points_by_metric={"cpu": [make_change_point("cpu", index=2)]},
            series=series,
            regression_flag=True,
            avg_values=pd.Series({"cpu": 15.0}),
            collapse=False,
            display_fields=[],
            column_group_size=5,
            uuid_field="uuid",
            version_field="ocpVersion",
            sippy_pr_search=False,
            github_repos=[],
        )

        table = _format_comparison_table(data, [])

        lines = table.strip().split("\n")
        cpu_line = [line for line in lines if "cpu" in line][0]
        assert "15" in cpu_line
        assert "100" not in cpu_line or "Pre-CP" in table

    def test_baseline_avg_uses_all_when_no_changepoints(self):
        data = _make_analysis_result(
            change_points={"cpu": []}, regression_flag=False
        )
        # _make_analysis_result sets avg_values to 20.0 (mean of 10,20,30)

        table = _format_comparison_table(data, [])

        lines = table.strip().split("\n")
        cpu_line = [line for line in lines if "cpu" in line][0]
        assert "20" in cpu_line


class TestMultiPrJUnit:
    def test_junit_pr_output_has_multiple_pull_elements(self, tmp_path):
        periodic = _make_analysis_result()
        pull_a = _make_pull_analysis([15.0, 25.0])
        pull_b = _make_pull_analysis([12.0, 22.0])
        pulls = [(1111, pull_a), (2222, pull_b)]

        formatter = JUnitFormatter()
        save_path = str(tmp_path / "output.xml")
        formatter.print_and_save_pr(periodic, pulls, save_path)

        with open(str(tmp_path / "output_test-workload.xml"),
                  encoding="utf-8") as f:
            tree = ET.parse(f)

        root = tree.getroot()
        pull_elements = root.findall(".//pull")
        assert len(pull_elements) == 2
        assert pull_elements[0].get("pr") == "1111"
        assert pull_elements[1].get("pr") == "2222"

    def test_junit_pr_output_skips_none_pulls(self, tmp_path):
        periodic = _make_analysis_result()
        pull_a = _make_pull_analysis([15.0])
        pulls = [(1111, pull_a), (2222, None)]

        formatter = JUnitFormatter()
        save_path = str(tmp_path / "output.xml")
        formatter.print_and_save_pr(periodic, pulls, save_path)

        with open(str(tmp_path / "output_test-workload.xml"),
                  encoding="utf-8") as f:
            tree = ET.parse(f)

        root = tree.getroot()
        pull_elements = root.findall(".//pull")
        assert len(pull_elements) == 1
        assert pull_elements[0].get("pr") == "1111"


class TestConfidenceTable:
    def test_table_contains_confidence_labels(self):
        data = _make_analysis_result()
        data.confidence_by_metric = {
            "cpu": [ConfidenceResult(
                p_value=0.01, cohens_d=1.2,
                confidence_label="Likely real (large shift)",
                sufficient_data=True,
                sample_size_before=10, sample_size_after=5,
            )],
        }
        table = _format_confidence_table(data)
        assert "Likely real (large shift)" in table
        assert "cpu" in table
        assert "CP#1" in table

    def test_table_shows_percentage_change(self):
        data = _make_analysis_result()
        data.confidence_by_metric = {
            "cpu": [ConfidenceResult(
                p_value=0.01, cohens_d=1.2,
                confidence_label="Likely real (large shift)",
                sufficient_data=True,
                sample_size_before=10, sample_size_after=5,
            )],
        }
        table = _format_confidence_table(data)
        assert "100" in table  # 100% change (mean_1=100, mean_2=200)

    def test_table_empty_when_no_confidence(self):
        data = _make_analysis_result(
            change_points={"cpu": []}, regression_flag=False
        )
        data.confidence_by_metric = {}
        table = _format_confidence_table(data)
        assert table == ""

    def test_table_shows_insufficient_data(self):
        data = _make_analysis_result()
        data.confidence_by_metric = {
            "cpu": [ConfidenceResult(
                p_value=None, cohens_d=None,
                confidence_label="Insufficient data",
                sufficient_data=False,
                sample_size_before=5, sample_size_after=1,
            )],
        }
        table = _format_confidence_table(data)
        assert "Insufficient data" in table

    def test_table_multiple_metrics_multiple_cps(self):
        _mk = make_change_point
        df = pd.DataFrame({
            "uuid": [f"u{i}" for i in range(5)],
            "ocpVersion": [f"4.{i}" for i in range(5)],
            "timestamp": [1700000000 + i * 100000 for i in range(5)],
            "buildUrl": [f"http://b{i}" for i in range(5)],
            "prs": [None] * 5,
            "cpu": [10.0, 10.5, 20.0, 20.5, 21.0],
            "mem": [50.0, 51.0, 50.5, 100.0, 101.0],
        })
        series = Series(
            test_name="test", branch=None,
            time=list(df["timestamp"]),
            metrics={"cpu": Metric(1, 1.0), "mem": Metric(1, 1.0)},
            data={"cpu": df["cpu"], "mem": df["mem"]},
            attributes={"uuid": df["uuid"], "ocpVersion": df["ocpVersion"]},
        )
        data = AnalysisResult(
            test_name="test-workload",
            test={"name": "test-workload", "uuid_field": "uuid",
                  "version_field": "ocpVersion", "metadata": {}},
            dataframe=df,
            metrics_config={
                "cpu": {"direction": 1, "labels": [], "threshold": 0,
                        "correlation": "", "context": None},
                "mem": {"direction": 1, "labels": [], "threshold": 0,
                        "correlation": "", "context": None},
            },
            change_points_by_metric={
                "cpu": [_mk("cpu", index=2)],
                "mem": [_mk("mem", index=3)],
            },
            series=series,
            regression_flag=True,
            avg_values=pd.Series({"cpu": 10.25, "mem": 50.5}),
            collapse=False, display_fields=[], column_group_size=5,
            uuid_field="uuid", version_field="ocpVersion",
            sippy_pr_search=False, github_repos=[],
            confidence_by_metric={
                "cpu": [ConfidenceResult(
                    p_value=0.01, cohens_d=1.0,
                    confidence_label="Likely real (large shift)",
                    sufficient_data=True,
                    sample_size_before=2, sample_size_after=3,
                )],
                "mem": [ConfidenceResult(
                    p_value=0.2, cohens_d=0.5,
                    confidence_label="Noise (trivial shift)",
                    sufficient_data=True,
                    sample_size_before=3, sample_size_after=2,
                )],
            },
        )
        table = _format_confidence_table(data)
        assert "cpu" in table
        assert "mem" in table
        assert "Likely real (large shift)" in table
        assert "Noise (trivial shift)" in table


class TestJsonConfidence:
    def test_changepoint_has_confidence_object(self):
        data = _make_analysis_result()
        data.confidence_by_metric = {
            "cpu": [ConfidenceResult(
                p_value=0.003, cohens_d=1.2,
                confidence_label="Likely real (large shift)",
                sufficient_data=True,
                sample_size_before=10, sample_size_after=5,
            )],
        }
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])
        cp_record = [r for r in parsed if r["is_changepoint"]][0]
        conf = cp_record["metrics"]["cpu"]["confidence"]
        assert conf["p_value"] == pytest.approx(0.003)
        assert conf["cohens_d"] == pytest.approx(1.2)
        assert conf["label"] == "Likely real (large shift)"
        assert conf["sufficient_data"] is True
        assert conf["sample_size_before"] == 10
        assert conf["sample_size_after"] == 5

    def test_non_changepoint_has_no_confidence(self):
        data = _make_analysis_result()
        data.confidence_by_metric = {
            "cpu": [ConfidenceResult(
                p_value=0.003, cohens_d=1.2,
                confidence_label="Likely real (large shift)",
                sufficient_data=True,
                sample_size_before=10, sample_size_after=5,
            )],
        }
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])
        non_cp = [r for r in parsed if not r["is_changepoint"]]
        for record in non_cp:
            assert "confidence" not in record["metrics"]["cpu"]

    def test_no_confidence_data_no_key(self):
        data = _make_analysis_result()
        # No confidence_by_metric set (default {})
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])
        cp_record = [r for r in parsed if r["is_changepoint"]][0]
        assert "confidence" not in cp_record["metrics"]["cpu"]

    def test_insufficient_data_in_json(self):
        data = _make_analysis_result()
        data.confidence_by_metric = {
            "cpu": [ConfidenceResult(
                p_value=None, cohens_d=None,
                confidence_label="Insufficient data",
                sufficient_data=False,
                sample_size_before=5, sample_size_after=1,
            )],
        }
        formatter = JsonFormatter()
        result = formatter.format(data)
        parsed = json.loads(result["test-workload"])
        cp_record = [r for r in parsed if r["is_changepoint"]][0]
        conf = cp_record["metrics"]["cpu"]["confidence"]
        assert conf["p_value"] is None
        assert conf["cohens_d"] is None
        assert conf["sufficient_data"] is False


class TestRegressionDataConfidence:
    def test_regression_data_includes_confidence(self):
        data = _make_analysis_result()
        data.confidence_by_metric = {
            "cpu": [ConfidenceResult(
                p_value=0.003, cohens_d=1.2,
                confidence_label="Likely real (large shift)",
                sufficient_data=True,
                sample_size_before=10, sample_size_after=5,
            )],
        }

        class ConcreteFormatter(BaseFormatter):
            def format(self, data):
                return {}
            def format_average(self, data):
                return ""
            def save(self, test_name, formatted, save_output_path):
                pass
            def print_output(self, test_name, formatted, data,
                             pr=0, is_pull=False):
                pass
            def print_and_save_pr(self, periodic, pulls, save_output_path):
                pass

        formatter = ConcreteFormatter()
        regressions = formatter.extract_regression_data(data)
        metric_entry = regressions[0]["metrics_with_change"][0]
        assert "confidence" in metric_entry
        assert metric_entry["confidence"]["p_value"] == pytest.approx(0.003)
        assert metric_entry["confidence"]["label"] == "Likely real (large shift)"

    def test_regression_data_no_confidence_when_empty(self):
        data = _make_analysis_result()
        # default confidence_by_metric = {}

        class ConcreteFormatter(BaseFormatter):
            def format(self, data):
                return {}
            def format_average(self, data):
                return ""
            def save(self, test_name, formatted, save_output_path):
                pass
            def print_output(self, test_name, formatted, data,
                             pr=0, is_pull=False):
                pass
            def print_and_save_pr(self, periodic, pulls, save_output_path):
                pass

        formatter = ConcreteFormatter()
        regressions = formatter.extract_regression_data(data)
        metric_entry = regressions[0]["metrics_with_change"][0]
        assert "confidence" not in metric_entry


class TestFormatterFactory:
    def test_get_json_formatter(self):
        formatter = FormatterFactory.get_formatter("json")
        assert isinstance(formatter, JsonFormatter)

    def test_get_text_formatter(self):
        formatter = FormatterFactory.get_formatter("text")
        assert isinstance(formatter, TextFormatter)

    def test_get_junit_formatter(self):
        formatter = FormatterFactory.get_formatter("junit")
        assert isinstance(formatter, JUnitFormatter)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Unsupported output format"):
            FormatterFactory.get_formatter("csv")
