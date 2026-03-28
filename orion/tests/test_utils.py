"""
Unit tests for orion/utils.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error
# pylint: disable = missing-class-docstring

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from orion.logger import SingletonLogger
from orion.utils import (
    Utils,
    generate_tabular_output,
    get_output_extension,
    get_subtracted_timestamp,
    json_to_junit,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    """Ensure the singleton logger exists for every test."""
    SingletonLogger(debug=logging.DEBUG, name="Orion")


@pytest.fixture
def utils():
    return Utils()


@pytest.fixture
def utils_custom_fields():
    return Utils(uuid_field="run_uuid", version_field="cluster_version")


# ---------------------------------------------------------------------------
# standardize_timestamp
# ---------------------------------------------------------------------------

class TestStandardizeTimestamp:
    def test_none_returns_none(self, utils):
        assert utils.standardize_timestamp(None) is None

    def test_integer_epoch_seconds(self, utils):
        # 2024-01-01 00:00:00 UTC
        result = utils.standardize_timestamp(1704067200)
        assert result == "2024-01-01T00:00:00"

    def test_numeric_string_epoch_seconds(self, utils):
        result = utils.standardize_timestamp("1704067200")
        assert result == "2024-01-01T00:00:00"

    def test_iso_string(self, utils):
        result = utils.standardize_timestamp("2024-06-15T12:30:45Z")
        assert result == "2024-06-15T12:30:45"

    def test_iso_string_with_offset(self, utils):
        result = utils.standardize_timestamp("2024-06-15T12:30:45+00:00")
        assert result == "2024-06-15T12:30:45"

    def test_float_epoch_not_treated_as_seconds(self, utils):
        # BEHAVIOR GUARD: floats take the else branch in standardize_timestamp,
        # where pd.to_datetime interprets them as nanoseconds, NOT seconds.
        # A float like 1.7e9 (valid epoch seconds for 2024) gets interpreted
        # as ~1.7 seconds after 1970-01-01.
        #
        # If this test fails it means the float handling changed — callers
        # that rely on passing int/str for epoch-seconds may now silently
        # get wrong results from floats, or vice-versa. Either way, audit
        # all call sites before accepting the new behavior.
        ts = 1704067200.123  # 2024-01-01 as epoch seconds
        result = utils.standardize_timestamp(ts)
        assert result.startswith("1970-01-01"), (
            f"Float timestamp handling changed! Got {result} — expected 1970 "
            f"(float treated as nanoseconds). If this is intentional, update "
            f"this test and audit callers of standardize_timestamp."
        )

    def test_pandas_timestamp(self, utils):
        ts = pd.Timestamp("2024-03-15 08:00:00", tz="UTC")
        result = utils.standardize_timestamp(ts)
        assert result == "2024-03-15T08:00:00"


# ---------------------------------------------------------------------------
# extract_metadata_from_test
# ---------------------------------------------------------------------------

class TestExtractMetadataFromTest:
    def test_basic_extraction(self, utils):
        test = {"metadata": {"platform": "aws", "ocpVersion": "4.14"}}
        meta = utils.extract_metadata_from_test(test)
        assert meta["platform"] == "aws"
        assert meta["ocpVersion"] == "4.14"

    def test_version_field_cast_to_string(self, utils):
        test = {"metadata": {"ocpVersion": 4.14}}
        meta = utils.extract_metadata_from_test(test)
        assert isinstance(meta["ocpVersion"], str)

    def test_empty_organization_removed(self, utils):
        test = {"metadata": {"organization": "", "platform": "aws"}}
        meta = utils.extract_metadata_from_test(test)
        assert "organization" not in meta

    def test_nonempty_organization_kept(self, utils):
        test = {"metadata": {"organization": "redhat", "platform": "aws"}}
        meta = utils.extract_metadata_from_test(test)
        assert meta["organization"] == "redhat"

    def test_empty_repository_removed(self, utils):
        test = {"metadata": {"repository": ""}}
        meta = utils.extract_metadata_from_test(test)
        assert "repository" not in meta

    def test_nonempty_repository_kept(self, utils):
        test = {"metadata": {"repository": "my-repo"}}
        meta = utils.extract_metadata_from_test(test)
        assert meta["repository"] == "my-repo"

    def test_custom_version_field(self, utils_custom_fields):
        test = {"metadata": {"cluster_version": 4.16}}
        meta = utils_custom_fields.extract_metadata_from_test(test)
        assert meta["cluster_version"] == "4.16"


# ---------------------------------------------------------------------------
# filter_uuids_on_index
# ---------------------------------------------------------------------------

class TestFilterUuidsOnIndex:
    def test_jobconfig_name_returns_uuids_unchanged(self, utils):
        metadata = {"jobConfig.name": "some-job"}
        uuids = ["u1", "u2"]
        result = utils.filter_uuids_on_index(
            metadata, "some-index", uuids, MagicMock(), "", False
        )
        assert result == uuids

    def test_ingress_perf_returns_uuids_unchanged(self, utils):
        metadata = {"benchmark.keyword": "ingress-perf"}
        uuids = ["u1", "u2"]
        result = utils.filter_uuids_on_index(
            metadata, "some-index", uuids, MagicMock(), "", False
        )
        assert result == uuids

    def test_k8s_netperf_returns_uuids_unchanged(self, utils):
        metadata = {"benchmark.keyword": "k8s-netperf"}
        uuids = ["u1"]
        result = utils.filter_uuids_on_index(
            metadata, "some-index", uuids, MagicMock(), "", False
        )
        assert result == uuids

    def test_kube_burner_no_baseline_calls_filter(self, utils):
        metadata = {"benchmark.keyword": "cluster-density-v2"}
        uuids = ["u1", "u2"]
        mock_match = MagicMock()
        mock_match.match_kube_burner.return_value = ["run1", "run2"]
        mock_match.filter_runs.return_value = ["u1"]
        result = utils.filter_uuids_on_index(
            metadata, "kube-burner-index", uuids, mock_match, "", False
        )
        mock_match.match_kube_burner.assert_called_once_with(uuids)
        assert result == ["u1"]

    def test_kube_burner_with_baseline_skips_filter(self, utils):
        metadata = {"benchmark.keyword": "cluster-density-v2"}
        uuids = ["u1", "u2"]
        mock_match = MagicMock()
        result = utils.filter_uuids_on_index(
            metadata, "kube-burner-index", uuids, mock_match, "baseline-uuid", False
        )
        mock_match.match_kube_burner.assert_not_called()
        assert result == uuids

    def test_no_benchmark_keyword_returns_uuids(self, utils):
        metadata = {"platform": "aws"}
        uuids = ["u1"]
        result = utils.filter_uuids_on_index(
            metadata, "some-index", uuids, MagicMock(), "", False
        )
        assert result == uuids


# ---------------------------------------------------------------------------
# get_metadata_with_uuid
# ---------------------------------------------------------------------------

class TestGetMetadataWithUuid:
    def test_filters_to_known_keys(self, utils):
        mock_match = MagicMock()
        mock_match.get_metadata_by_uuid.return_value = {
            "platform": "aws",
            "clusterType": "rosa",
            "unknownField": "should_be_dropped",
        }
        meta = utils.get_metadata_with_uuid("some-uuid", mock_match)
        assert meta["platform"] == "aws"
        assert meta["clusterType"] == "rosa"
        assert "unknownField" not in meta

    def test_blank_values_removed(self, utils):
        mock_match = MagicMock()
        mock_match.get_metadata_by_uuid.return_value = {
            "platform": "aws",
            "networkType": "",
            "masterNodesCount": 0,
        }
        meta = utils.get_metadata_with_uuid("some-uuid", mock_match)
        assert "platform" in meta
        assert "networkType" not in meta
        assert "masterNodesCount" not in meta

    def test_benchmark_mapped_to_keyword(self, utils):
        mock_match = MagicMock()
        mock_match.get_metadata_by_uuid.return_value = {
            "platform": "gcp",
            "benchmark": "cluster-density-v2",
        }
        meta = utils.get_metadata_with_uuid("some-uuid", mock_match)
        assert meta["benchmark.keyword"] == "cluster-density-v2"

    def test_version_field_cast_to_str(self, utils):
        mock_match = MagicMock()
        mock_match.get_metadata_by_uuid.return_value = {
            "platform": "aws",
            "ocpVersion": 4.14,
        }
        meta = utils.get_metadata_with_uuid("some-uuid", mock_match)
        assert meta["ocpVersion"] == "4.14"


# ---------------------------------------------------------------------------
# process_sippy_pr_list
# ---------------------------------------------------------------------------

class TestProcessSippyPrList:
    def test_extracts_urls(self, utils):
        pr_list = [
            {"url": "https://github.com/org/repo/pull/1", "other": "data"},
            {"url": "https://github.com/org/repo/pull/2", "other": "data2"},
        ]
        result = utils.process_sippy_pr_list(pr_list)
        assert result == [
            "https://github.com/org/repo/pull/1",
            "https://github.com/org/repo/pull/2",
        ]

    def test_empty_list(self, utils):
        assert utils.process_sippy_pr_list([]) == []


# ---------------------------------------------------------------------------
# shorten_url
# ---------------------------------------------------------------------------

class TestShortenUrl:
    def test_single_url(self, utils):
        mock_shortener = MagicMock()
        mock_shortener.tinyurl.short.return_value = "https://tinyurl.com/abc"
        result = utils.shorten_url(mock_shortener, "https://example.com/long")
        assert result == "https://tinyurl.com/abc"

    def test_multiple_comma_separated(self, utils):
        mock_shortener = MagicMock()
        mock_shortener.tinyurl.short.side_effect = [
            "https://tinyurl.com/a",
            "https://tinyurl.com/b",
        ]
        result = utils.shorten_url(
            mock_shortener, "https://example.com/1,https://example.com/2"
        )
        assert result == "https://tinyurl.com/a,https://tinyurl.com/b"


# ---------------------------------------------------------------------------
# get_subtracted_timestamp (module-level function)
# ---------------------------------------------------------------------------

class TestGetSubtractedTimestamp:
    def test_days_only(self):
        start = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = get_subtracted_timestamp("5d", start_timestamp=start)
        assert result == start - timedelta(days=5)

    def test_hours_only(self):
        start = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = get_subtracted_timestamp("8h", start_timestamp=start)
        assert result == start - timedelta(hours=8)

    def test_days_and_hours(self):
        start = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = get_subtracted_timestamp("3d12h", start_timestamp=start)
        assert result == start - timedelta(days=3, hours=12)

    def test_string_timestamp(self):
        result = get_subtracted_timestamp("1d", start_timestamp="2024-06-15")
        expected = datetime(2024, 6, 14, 0, 0, 0)
        assert result == expected

    def test_zero_duration(self):
        start = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = get_subtracted_timestamp("0d0h", start_timestamp=start)
        assert result == start


# ---------------------------------------------------------------------------
# get_output_extension (module-level function)
# ---------------------------------------------------------------------------

class TestGetOutputExtension:
    def test_json(self):
        assert get_output_extension("json") == "json"

    def test_junit(self):
        assert get_output_extension("junit") == "xml"

    def test_text(self):
        assert get_output_extension("text") == "txt"

    def test_unknown_defaults_to_txt(self):
        assert get_output_extension("whatever") == "txt"


# ---------------------------------------------------------------------------
# generate_tabular_output (module-level function)
# ---------------------------------------------------------------------------

class TestGenerateTabularOutput:
    @pytest.fixture
    def sample_data(self):
        return [
            {
                "uuid": "uuid-1",
                "timestamp": 1704067200,
                "metrics": {
                    "cpu_usage": {
                        "value": 75.0,
                        "percentage_change": 0,
                    }
                },
            },
            {
                "uuid": "uuid-2",
                "timestamp": 1704153600,
                "metrics": {
                    "cpu_usage": {
                        "value": 90.0,
                        "percentage_change": 20.0,
                    }
                },
            },
        ]

    def test_output_contains_metric_name(self, sample_data):
        output = generate_tabular_output(sample_data, "cpu_usage", display_fields=[])
        assert "cpu_usage" in output

    def test_changepoint_marked(self, sample_data):
        output = generate_tabular_output(sample_data, "cpu_usage", display_fields=[])
        assert "changepoint" in output

    def test_non_changepoint_not_marked(self, sample_data):
        # The first row has percentage_change=0, so it should NOT have "changepoint"
        output = generate_tabular_output(sample_data, "cpu_usage", display_fields=[])
        lines = output.split("\n")
        # Find data lines (skip header/separator)
        data_lines = [l for l in lines[3:-1] if "uuid-1" in l]
        for line in data_lines:
            assert "changepoint" not in line

    def test_display_field_included(self):
        data = [
            {
                "uuid": "uuid-1",
                "timestamp": 1704067200,
                "build_tag": "nightly-123",
                "metrics": {
                    "latency": {"value": 10.0, "percentage_change": 0}
                },
            },
        ]
        output = generate_tabular_output(
            data, "latency", display_fields=["build_tag"]
        )
        assert "build_tag" in output
        assert "nightly-123" in output


# ---------------------------------------------------------------------------
# json_to_junit (module-level function)
# ---------------------------------------------------------------------------

class TestJsonToJunit:
    @pytest.fixture
    def metrics_config(self):
        return {
            "throughput": {"labels": ["network", "tcp"]},
            "latency_p99": {"labels": None},
        }

    @pytest.fixture
    def data_with_regression(self):
        return [
            {
                "uuid": "u1",
                "timestamp": 1704067200,
                "metrics": {
                    "throughput": {"value": 100, "percentage_change": -15.0},
                    "latency_p99": {"value": 5, "percentage_change": 0},
                },
            },
        ]

    @pytest.fixture
    def data_no_regression(self):
        return [
            {
                "uuid": "u1",
                "timestamp": 1704067200,
                "metrics": {
                    "throughput": {"value": 100, "percentage_change": 0},
                    "latency_p99": {"value": 5, "percentage_change": 0},
                },
            },
        ]

    def test_testsuite_name(self, data_no_regression, metrics_config):
        suite = json_to_junit("my-test", data_no_regression, metrics_config, "uuid", display_fields=[])
        assert suite.get("name") == "my-test nightly compare"

    def test_counts_failures(self, data_with_regression, metrics_config):
        suite = json_to_junit("my-test", data_with_regression, metrics_config, "uuid", display_fields=[])
        assert suite.get("failures") == "1"
        assert suite.get("tests") == "2"

    def test_no_failures_when_clean(self, data_no_regression, metrics_config):
        suite = json_to_junit("my-test", data_no_regression, metrics_config, "uuid", display_fields=[])
        assert suite.get("failures") == "0"

    def test_failure_element_contains_table(self, data_with_regression, metrics_config):
        suite = json_to_junit("my-test", data_with_regression, metrics_config, "uuid", display_fields=[])
        failures = suite.findall(".//failure")
        assert len(failures) == 1
        assert "throughput" in failures[0].text

    def test_labels_in_testcase_name(self, data_no_regression, metrics_config):
        suite = json_to_junit("my-test", data_no_regression, metrics_config, "uuid", display_fields=[])
        names = [tc.get("name") for tc in suite.findall("testcase")]
        assert any("network tcp" in n for n in names)

    def test_average_mode(self):
        import json
        avg_data = json.dumps({"throughput": 95.5, "latency_p99": 4.2})
        config = {"throughput": {}, "latency_p99": {}}
        suite = json_to_junit("avg-test", avg_data, config, "uuid", average=True, display_fields=[])
        testcases = suite.findall("testcase")
        assert len(testcases) == 2
        values = {tc.get("name"): tc.get("value") for tc in testcases}
        assert values[" throughput average"] == "95.5"

    def test_valid_xml_output(self, data_no_regression, metrics_config):
        suite = json_to_junit("xml-test", data_no_regression, metrics_config, "uuid", display_fields=[])
        # Should be serializable to valid XML string
        xml_str = ET.tostring(suite, encoding="unicode")
        assert xml_str.startswith("<testsuite")


# ---------------------------------------------------------------------------
# process_aggregation_metric
# ---------------------------------------------------------------------------

class TestProcessAggregationMetric:
    def test_empty_data_returns_empty_df(self, utils):
        mock_match = MagicMock()
        mock_match.get_agg_metric_query.return_value = []
        metric = {
            "name": "cpu",
            "metric_of_interest": "value",
            "agg": {"value": "cpu_usage", "agg_type": "avg"},
        }
        df, name = utils.process_aggregation_metric(["u1"], metric, mock_match)
        assert name == "cpu_avg"
        assert len(df) == 0
        assert "cpu_avg" in df.columns

    def test_with_data_renames_columns(self, utils):
        mock_match = MagicMock()
        mock_match.get_agg_metric_query.return_value = [
            {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z", "cpu_usage_avg": 85.0}
        ]
        result_df = pd.DataFrame({
            "uuid": ["u1"],
            "timestamp": ["2024-01-01T00:00:00Z"],
            "cpu_usage_avg": [85.0],
        })
        mock_match.convert_to_df.return_value = result_df
        metric = {
            "name": "cpu",
            "metric_of_interest": "value",
            "agg": {"value": "cpu_usage", "agg_type": "avg"},
        }
        df, name = utils.process_aggregation_metric(["u1"], metric, mock_match)
        assert name == "cpu_avg"
        assert "cpu_avg" in df.columns
        assert "cpu_usage_avg" not in df.columns

    def test_custom_timestamp_renamed(self, utils):
        mock_match = MagicMock()
        mock_match.get_agg_metric_query.return_value = [
            {"uuid": "u1", "start_time": "2024-01-01T00:00:00Z", "mem_max": 1024}
        ]
        result_df = pd.DataFrame({
            "uuid": ["u1"],
            "start_time": ["2024-01-01T00:00:00Z"],
            "mem_max": [1024],
        })
        mock_match.convert_to_df.return_value = result_df
        metric = {
            "name": "memory",
            "metric_of_interest": "value",
            "agg": {"value": "mem", "agg_type": "max"},
        }
        df, _ = utils.process_aggregation_metric(
            ["u1"], metric, mock_match, timestamp_field="start_time"
        )
        assert "timestamp" in df.columns
        assert "start_time" not in df.columns


# ---------------------------------------------------------------------------
# process_standard_metric
# ---------------------------------------------------------------------------

class TestProcessStandardMetric:
    def test_empty_data_returns_empty_df(self, utils):
        mock_match = MagicMock()
        mock_match.get_results.return_value = []
        metric = {"name": "throughput", "metric_of_interest": "value"}
        df, name = utils.process_standard_metric(
            ["u1"], metric, mock_match, "value"
        )
        assert name == "throughput_value"
        assert len(df) == 0

    def test_with_data_renames_and_deduplicates(self, utils):
        mock_match = MagicMock()
        mock_match.get_results.return_value = [
            {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z", "value": 100},
            {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z", "value": 100},
        ]
        result_df = pd.DataFrame({
            "uuid": ["u1", "u1"],
            "timestamp": ["2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"],
            "value": [100, 100],
        })
        mock_match.convert_to_df.return_value = result_df
        metric = {"name": "throughput", "metric_of_interest": "value"}
        df, name = utils.process_standard_metric(
            ["u1"], metric, mock_match, "value"
        )
        assert name == "throughput_value"
        assert "throughput_value" in df.columns
        assert len(df) == 1  # deduplicated

    def test_custom_timestamp_renamed(self, utils):
        mock_match = MagicMock()
        mock_match.get_results.return_value = [
            {"uuid": "u1", "run_time": "2024-01-01T00:00:00Z", "value": 50}
        ]
        result_df = pd.DataFrame({
            "uuid": ["u1"],
            "run_time": ["2024-01-01T00:00:00Z"],
            "value": [50],
        })
        mock_match.convert_to_df.return_value = result_df
        metric = {"name": "lat", "metric_of_interest": "value"}
        df, _ = utils.process_standard_metric(
            ["u1"], metric, mock_match, "value", timestamp_field="run_time"
        )
        assert "timestamp" in df.columns
        assert "run_time" not in df.columns


# ---------------------------------------------------------------------------
# get_metric_data
# ---------------------------------------------------------------------------

class TestGetMetricData:
    def test_aggregation_metric_path(self, utils):
        mock_match = MagicMock()
        mock_match.get_agg_metric_query.return_value = []
        metrics = [
            {
                "name": "cpu",
                "metric_of_interest": "value",
                "agg": {"value": "cpu_usage", "agg_type": "avg"},
            }
        ]
        df_list, config = utils.get_metric_data(
            ["u1"], metrics, mock_match, test_threshold=5
        )
        assert len(df_list) == 1
        assert "cpu_avg" in config

    def test_standard_metric_path(self, utils):
        mock_match = MagicMock()
        mock_match.get_results.return_value = []
        metrics = [
            {"name": "throughput", "metric_of_interest": "value"}
        ]
        df_list, config = utils.get_metric_data(
            ["u1"], metrics, mock_match, test_threshold=10
        )
        assert len(df_list) == 1
        assert "throughput_value" in config

    def test_exception_in_metric_skips_it(self, utils):
        mock_match = MagicMock()
        mock_match.get_results.side_effect = RuntimeError("connection failed")
        metrics = [
            {"name": "broken", "metric_of_interest": "value"}
        ]
        df_list, config = utils.get_metric_data(
            ["u1"], metrics, mock_match, test_threshold=5
        )
        assert len(df_list) == 0
        assert "broken_value" not in config

    def test_metric_config_preserves_direction_and_threshold(self, utils):
        mock_match = MagicMock()
        mock_match.get_results.return_value = []
        metrics = [
            {
                "name": "latency",
                "metric_of_interest": "p99",
                "direction": "1",
                "threshold": "20",
            }
        ]
        _, config = utils.get_metric_data(
            ["u1"], metrics, mock_match, test_threshold=5
        )
        assert config["latency_p99"]["direction"] == 1
        assert config["latency_p99"]["threshold"] == 20

    def test_labels_popped_and_restored(self, utils):
        mock_match = MagicMock()
        mock_match.get_results.return_value = []
        metrics = [
            {
                "name": "net",
                "metric_of_interest": "bps",
                "labels": ["tcp", "ingress"],
            }
        ]
        _, config = utils.get_metric_data(
            ["u1"], metrics, mock_match, test_threshold=5
        )
        assert config["net_bps"]["labels"] == ["tcp", "ingress"]


# ---------------------------------------------------------------------------
# sippy_pr_diff (HTTP call mocked)
# ---------------------------------------------------------------------------

class TestSippyPrDiff:
    @patch("orion.utils.requests.get")
    def test_successful_diff(self, mock_get, utils):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"url": "https://github.com/org/repo/pull/10"},
        ]
        mock_get.return_value = mock_response
        result = utils.sippy_pr_diff("4.14.0-rc.1", "4.14.0-rc.2")
        assert result == ["https://github.com/org/repo/pull/10"]

    @patch("orion.utils.requests.get")
    def test_failed_request_returns_empty(self, mock_get, utils):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        result = utils.sippy_pr_diff("4.14.0-rc.1", "4.14.0-rc.2")
        assert result == []


# ---------------------------------------------------------------------------
# sippy_pr_search (HTTP call mocked)
# ---------------------------------------------------------------------------

class TestSippyPrSearch:
    @patch("orion.utils.requests.get")
    def test_successful_search(self, mock_get, utils):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"url": "https://github.com/org/repo/pull/42"},
        ]
        mock_get.return_value = mock_response
        result = utils.sippy_pr_search("4.14.0-rc.3")
        assert result == ["https://github.com/org/repo/pull/42"]

    @patch("orion.utils.requests.get")
    def test_failed_search_returns_empty(self, mock_get, utils):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        result = utils.sippy_pr_search("4.14.0-rc.3")
        assert result == []
