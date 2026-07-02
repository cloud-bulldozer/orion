"""
Unit tests for config validation in orion/config.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error
# pylint: disable = missing-class-docstring

import tempfile
import os

import logging
from unittest.mock import patch

import pytest
import yaml

from orion.config import (
    collect_pull_numbers,
    load_ack,
    load_config,
    load_config_file,
    load_read_file,
    merge_ack_files,
    merge_configs,
    merge_lists,
    render_template,
)
from orion.logger import SingletonLogger


def _write_config(tmp_dir, config_dict, filename="config.yaml"):
    """Write a config dict as YAML to a temp file and return its path."""
    path = os.path.join(tmp_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f)
    return path


def _minimal_config(metrics):
    """Return a minimal valid config dict with the given metrics list."""
    return {
        "tests": [
            {
                "name": "test1",
                "metadata": {
                    "platform": "AWS",
                    "benchmark.keyword": "test-bench",
                    "ocpVersion": "4.17",
                },
                "metrics": metrics,
            }
        ]
    }


class TestPercentileValidation:
    """Tests for percentile agg_type requiring percents in config."""

    def test_percentile_without_percents_exits(self):
        metric = {
            "name": "latency_p95",
            "metricName": "api_latency",
            "metric_of_interest": "response_time_ms",
            "agg": {
                "value": "response_time_ms",
                "agg_type": "percentiles",
            },
            "threshold": 10,
            "direction": 1,
        }
        config = _minimal_config([metric])

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_config(tmp_dir, config)
            with pytest.raises(SystemExit):
                load_config(path, {})

    def test_percentile_with_percents_passes(self):
        metric = {
            "name": "latency_p95",
            "metricName": "api_latency",
            "metric_of_interest": "response_time_ms",
            "agg": {
                "value": "response_time_ms",
                "agg_type": "percentiles",
                "percents": [50, 95, 99],
            },
            "threshold": 10,
            "direction": 1,
        }
        config = _minimal_config([metric])

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_config(tmp_dir, config)
            result = load_config(path, {})
            assert result is not None
            assert len(result["tests"]) == 1

    def test_non_percentile_agg_without_percents_passes(self):
        metric = {
            "name": "avg_cpu",
            "metricName": "containerCPU",
            "metric_of_interest": "cpu",
            "agg": {
                "value": "cpu",
                "agg_type": "avg",
            },
            "threshold": 10,
            "direction": 1,
        }
        config = _minimal_config([metric])

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_config(tmp_dir, config)
            result = load_config(path, {})
            assert result is not None
            assert len(result["tests"]) == 1


class TestCollectPullNumbers:  # pylint: disable=missing-class-docstring

    def test_single_pull_number_from_input_vars(self):
        result = collect_pull_numbers({}, {"pull_number": "1234"})
        assert result == [1234]

    def test_multiple_from_cli_flag(self):
        result = collect_pull_numbers(
            {"pull_number": (1234, 5678)}, {}
        )
        assert result == [1234, 5678]

    def test_pull_numbers_list_from_input_vars(self):
        result = collect_pull_numbers(
            {}, {"pull_numbers": [1111, 2222, 3333]}
        )
        assert result == [1111, 2222, 3333]

    def test_pull_numbers_csv_string_from_input_vars(self):
        result = collect_pull_numbers(
            {}, {"pull_numbers": "100,200,300"}
        )
        assert result == [100, 200, 300]

    def test_pull_number_csv_string_from_input_vars(self):
        result = collect_pull_numbers(
            {}, {"pull_number": "100,200"}
        )
        assert result == [100, 200]

    def test_merge_cli_and_input_vars_deduplicated(self):
        result = collect_pull_numbers(
            {"pull_number": (1234, 5678)},
            {"pull_number": "5678", "pull_numbers": [9999]},
        )
        assert result == [1234, 5678, 9999]

    def test_empty_when_nothing_provided(self):
        result = collect_pull_numbers({}, {})
        assert result == []

    def test_returns_sorted(self):
        result = collect_pull_numbers(
            {"pull_number": (9000, 100, 5000)}, {}
        )
        assert result == [100, 5000, 9000]

    def test_ignores_zero_in_cli_flag(self):
        result = collect_pull_numbers(
            {"pull_number": (0, 1234)}, {}
        )
        assert result == [1234]

    def test_integer_value_in_input_vars(self):
        result = collect_pull_numbers({}, {"pull_number": 4567})
        assert result == [4567]

    def test_ignores_zero_in_string_input_var(self):
        result = collect_pull_numbers({}, {"pull_number": "0"})
        assert result == []

    def test_ignores_zero_in_csv_string(self):
        result = collect_pull_numbers(
            {}, {"pull_number": "0,1234,0"}
        )
        assert result == [1234]

    def test_ignores_zero_in_list(self):
        result = collect_pull_numbers(
            {}, {"pull_numbers": [0, 1234, 0]}
        )
        assert result == [1234]

    def test_ignores_zero_integer_input_var(self):
        result = collect_pull_numbers({}, {"pull_number": 0})
        assert result == []

    def test_rejects_non_numeric_string(self):
        with pytest.raises(ValueError, match="invalid pull number"):
            collect_pull_numbers({}, {"pull_number": "abc"})

    def test_rejects_non_numeric_csv_token(self):
        with pytest.raises(ValueError, match="invalid pull number"):
            collect_pull_numbers({}, {"pull_number": "123,abc"})

    def test_rejects_negative_number(self):
        with pytest.raises(ValueError, match="invalid pull number"):
            collect_pull_numbers({}, {"pull_number": -1})

    def test_rejects_negative_in_csv(self):
        with pytest.raises(ValueError, match="invalid pull number"):
            collect_pull_numbers({}, {"pull_number": "-2,3"})

    def test_rejects_negative_in_list(self):
        with pytest.raises(ValueError, match="invalid pull number"):
            collect_pull_numbers({}, {"pull_numbers": [100, -5]})
# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    """Ensure the singleton logger exists for every test."""
    SingletonLogger(debug=logging.DEBUG, name="Orion")


@pytest.fixture
def tmp_yaml(tmp_path):
    """Helper to write a YAML file and return its path."""
    def _write(content, filename="test.yaml"):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return str(path)
    return _write


# ---------------------------------------------------------------------------
# merge_configs
# ---------------------------------------------------------------------------

class TestMergeConfigs:
    def test_config_takes_precedence(self):
        config = {"platform": "aws", "version": "4.14"}
        inherited = {"platform": "gcp", "network": "OVN"}
        result = merge_configs(config, inherited)
        assert result["platform"] == "aws"
        assert result["version"] == "4.14"
        assert result["network"] == "OVN"

    def test_inherited_only_keys_included(self):
        config = {"a": 1}
        inherited = {"b": 2, "c": 3}
        result = merge_configs(config, inherited)
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_none_inherited(self):
        result = merge_configs({"x": 1}, None)
        assert result == {"x": 1}

    def test_none_config(self):
        result = merge_configs(None, {"y": 2})
        assert result == {"y": 2}

    def test_both_none(self):
        result = merge_configs(None, None)
        assert result == {}

    def test_empty_dicts(self):
        assert not merge_configs({}, {})

    def test_nested_values_not_deep_merged(self):
        config = {"meta": {"a": 1}}
        inherited = {"meta": {"b": 2}}
        result = merge_configs(config, inherited)
        # Shallow merge: config's "meta" wins entirely
        assert result["meta"] == {"a": 1}


# ---------------------------------------------------------------------------
# merge_lists
# ---------------------------------------------------------------------------

class TestMergeLists:
    def test_inherited_metrics_appended(self):
        metrics = [{"name": "cpu", "metric_of_interest": "value"}]
        inherited = [{"name": "mem", "metric_of_interest": "rss"}]
        result = merge_lists(metrics, inherited)
        names = [m["name"] for m in result]
        assert "cpu" in names
        assert "mem" in names

    def test_duplicate_name_with_metricName_suppressed(self):
        metrics = [{"name": "lat", "metricName": "p99", "x": 1}]
        inherited = [{"name": "lat", "metricName": "p99", "x": 2}]
        result = merge_lists(metrics, inherited)
        # inherited entry suppressed, only local kept
        assert len(result) == 1
        assert result[0]["x"] == 1

    def test_duplicate_name_with_metricName_keyword_suppressed(self):
        metrics = [{"name": "lat", "metricName.keyword": "p99", "x": 1}]
        inherited = [{"name": "lat", "metricName.keyword": "p99", "x": 2}]
        result = merge_lists(metrics, inherited)
        assert len(result) == 1
        assert result[0]["x"] == 1

    def test_same_name_different_metricName_kept(self):
        metrics = [{"name": "lat", "metricName": "p99"}]
        inherited = [{"name": "lat", "metricName": "p50"}]
        result = merge_lists(metrics, inherited)
        assert len(result) == 2

    def test_none_metrics(self):
        result = merge_lists(None, [{"name": "a"}])
        assert len(result) == 1

    def test_none_inherited(self):
        result = merge_lists([{"name": "a"}], None)
        assert len(result) == 1

    def test_both_none(self):
        assert not merge_lists(None, None)

    def test_ordering_inherited_first_then_local(self):
        metrics = [{"name": "local"}]
        inherited = [{"name": "inherited"}]
        result = merge_lists(metrics, inherited)
        assert result[0]["name"] == "inherited"
        assert result[1]["name"] == "local"


# ---------------------------------------------------------------------------
# render_template
# ---------------------------------------------------------------------------

class TestRenderTemplate:
    def test_simple_substitution(self):
        template = "platform: {{ platform }}"
        result = render_template(template, {"platform": "aws"}, SingletonLogger.get_logger("Orion"))
        assert result == {"platform": "aws"}

    def test_yaml_parses_numeric_looking_values(self):
        # BEHAVIOR GUARD: Jinja renders "4.14" as a bare string into YAML,
        # and yaml.safe_load parses it as float 4.14, not str "4.14".
        # Callers that need string versions must quote them in the template.
        template = "version: {{ version }}"
        result = render_template(template, {"version": "4.14"}, SingletonLogger.get_logger("Orion"))
        assert result["version"] == 4.14
        assert isinstance(result["version"], float)

    def test_undefined_var_exits(self):
        template = "value: {{ missing_var }}"
        with pytest.raises(SystemExit):
            render_template(template, {}, SingletonLogger.get_logger("Orion"))

    def test_complex_yaml(self):
        template = """
tests:
  - name: {{ test_name }}
    count: {{ count }}
"""
        result = render_template(
            template, {"test_name": "my-test", "count": "5"},
            SingletonLogger.get_logger("Orion")
        )
        assert result["tests"][0]["name"] == "my-test"
        assert result["tests"][0]["count"] == 5


# ---------------------------------------------------------------------------
# load_read_file
# ---------------------------------------------------------------------------

class TestLoadReadFile:
    def test_reads_file_content(self, tmp_yaml):
        path = tmp_yaml("hello: world")
        content = load_read_file(path, SingletonLogger.get_logger("Orion"))
        assert "hello: world" in content

    def test_missing_file_exits(self):
        with pytest.raises(SystemExit):
            load_read_file("/nonexistent/path.yaml", SingletonLogger.get_logger("Orion"))


# ---------------------------------------------------------------------------
# load_config_file
# ---------------------------------------------------------------------------

class TestLoadConfigFile:
    def test_absolute_path(self, tmp_yaml):
        path = tmp_yaml("metadata:\n  platform: aws")
        result = load_config_file(path, "/unused", {}, SingletonLogger.get_logger("Orion"))
        assert result["metadata"]["platform"] == "aws"

    def test_relative_path(self, tmp_path):
        cfg = tmp_path / "sub.yaml"
        cfg.write_text("metadata:\n  network: OVN", encoding="utf-8")
        result = load_config_file("sub.yaml", str(tmp_path), {}, SingletonLogger.get_logger("Orion"))
        assert result["metadata"]["network"] == "OVN"

    def test_jinja_rendering(self, tmp_yaml):
        path = tmp_yaml("metadata:\n  platform: {{ platform }}")
        result = load_config_file(path, "/unused", {"platform": "gcp"}, SingletonLogger.get_logger("Orion"))
        assert result["metadata"]["platform"] == "gcp"


# ---------------------------------------------------------------------------
# load_ack
# ---------------------------------------------------------------------------

class TestLoadAck:
    def test_basic_load(self, tmp_yaml):
        content = yaml.dump({"ack": [
            {"uuid": "u1", "metric": "cpu"},
            {"uuid": "u2", "metric": "mem"},
        ]})
        path = tmp_yaml(content)
        result = load_ack(path)
        assert len(result["ack"]) == 2

    def test_filter_by_version(self, tmp_yaml):
        content = yaml.dump({"ack": [
            {"uuid": "u1", "metric": "cpu", "version": "4.14"},
            {"uuid": "u2", "metric": "mem", "version": "4.15"},
            {"uuid": "u3", "metric": "net"},  # no version — included
        ]})
        path = tmp_yaml(content)
        result = load_ack(path, version="4.14")
        uuids = [e["uuid"] for e in result["ack"]]
        assert "u1" in uuids
        assert "u3" in uuids  # no version means matches any
        assert "u2" not in uuids

    def test_filter_by_test_type(self, tmp_yaml):
        content = yaml.dump({"ack": [
            {"uuid": "u1", "metric": "cpu", "test": "node-density"},
            {"uuid": "u2", "metric": "mem", "test": "cluster-density"},
            {"uuid": "u3", "metric": "net"},  # no test — included
        ]})
        path = tmp_yaml(content)
        result = load_ack(path, test_type="node-density")
        uuids = [e["uuid"] for e in result["ack"]]
        assert "u1" in uuids
        assert "u3" in uuids
        assert "u2" not in uuids

    def test_filter_by_both(self, tmp_yaml):
        content = yaml.dump({"ack": [
            {"uuid": "u1", "metric": "cpu", "version": "4.14", "test": "nd"},
            {"uuid": "u2", "metric": "mem", "version": "4.14", "test": "cd"},
            {"uuid": "u3", "metric": "net", "version": "4.15", "test": "nd"},
        ]})
        path = tmp_yaml(content)
        result = load_ack(path, version="4.14", test_type="nd")
        assert len(result["ack"]) == 1
        assert result["ack"][0]["uuid"] == "u1"

    def test_empty_ack_file(self, tmp_yaml):
        path = tmp_yaml("")
        result = load_ack(path)
        assert result is None

    def test_missing_ack_key_exits(self, tmp_yaml):
        content = yaml.dump({"not_ack": []})
        path = tmp_yaml(content)
        with pytest.raises(SystemExit):
            load_ack(path)

    def test_no_filter_returns_all(self, tmp_yaml):
        content = yaml.dump({"ack": [
            {"uuid": "u1", "metric": "cpu", "version": "4.14"},
            {"uuid": "u2", "metric": "mem", "version": "4.15"},
        ]})
        path = tmp_yaml(content)
        result = load_ack(path)
        assert len(result["ack"]) == 2


# ---------------------------------------------------------------------------
# merge_ack_files
# ---------------------------------------------------------------------------

class TestMergeAckFiles:
    def test_merges_multiple(self):
        ack1 = {"ack": [{"uuid": "u1", "metric": "cpu"}]}
        ack2 = {"ack": [{"uuid": "u2", "metric": "mem"}]}
        result = merge_ack_files([ack1, ack2])
        assert len(result["ack"]) == 2

    def test_deduplicates(self):
        ack1 = {"ack": [{"uuid": "u1", "metric": "cpu"}]}
        ack2 = {"ack": [{"uuid": "u1", "metric": "cpu"}]}
        result = merge_ack_files([ack1, ack2])
        assert len(result["ack"]) == 1

    def test_same_uuid_different_metric_kept(self):
        ack1 = {"ack": [{"uuid": "u1", "metric": "cpu"}]}
        ack2 = {"ack": [{"uuid": "u1", "metric": "mem"}]}
        result = merge_ack_files([ack1, ack2])
        assert len(result["ack"]) == 2

    def test_none_entries_skipped(self):
        ack1 = {"ack": [{"uuid": "u1", "metric": "cpu"}]}
        result = merge_ack_files([ack1, None, {}])
        assert len(result["ack"]) == 1

    def test_empty_list(self):
        result = merge_ack_files([])
        assert result == {"ack": []}


# ---------------------------------------------------------------------------
# load_config (integration-ish: uses real files, no network)
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_minimal_config(self, tmp_yaml):
        content = yaml.dump({
            "tests": [{
                "name": "test1",
                "metadata": {"platform": "aws"},
                "metrics": [{"name": "cpu", "metric_of_interest": "value"}],
            }]
        })
        path = tmp_yaml(content)
        result = load_config(path, {})
        assert result["tests"][0]["name"] == "test1"
        assert result["tests"][0]["uuid_field"] == "uuid"
        assert result["tests"][0]["version_field"] == "ocpVersion"

    def test_jinja_vars_substituted(self, tmp_yaml):
        content = """
tests:
  - name: {{ test_name }}
    metadata:
      platform: aws
    metrics:
      - name: cpu
        metric_of_interest: value
"""
        path = tmp_yaml(content)
        result = load_config(path, {"test_name": "my-test"})
        assert result["tests"][0]["name"] == "my-test"

    def test_duplicate_metrics_exits(self, tmp_yaml):
        content = yaml.dump({
            "tests": [{
                "name": "t1",
                "metadata": {},
                "metrics": [
                    {"name": "cpu", "metric_of_interest": "value"},
                    {"name": "cpu", "metric_of_interest": "value"},
                ],
            }]
        })
        path = tmp_yaml(content)
        with pytest.raises(SystemExit):
            load_config(path, {})

    def test_parent_config_merged(self, tmp_path):
        parent = tmp_path / "parent.yaml"
        parent.write_text(yaml.dump({"network": "OVN"}), encoding="utf-8")
        child_content = yaml.dump({
            "parentConfig": str(parent),
            "tests": [{
                "name": "t1",
                "metadata": {"platform": "aws"},
                "metrics": [{"name": "m1", "metric_of_interest": "v"}],
            }]
        })
        child = tmp_path / "child.yaml"
        child.write_text(child_content, encoding="utf-8")
        result = load_config(str(child), {})
        # Parent's network merged, child's platform kept
        assert result["tests"][0]["metadata"]["platform"] == "aws"
        assert result["tests"][0]["metadata"]["network"] == "OVN"

    def test_ignore_global_skips_parent(self, tmp_path):
        parent = tmp_path / "parent.yaml"
        parent.write_text(yaml.dump({"network": "OVN"}), encoding="utf-8")
        child_content = yaml.dump({
            "parentConfig": str(parent),
            "tests": [{
                "name": "t1",
                "IgnoreGlobal": True,
                "metadata": {"platform": "aws"},
                "metrics": [{"name": "m1", "metric_of_interest": "v"}],
            }]
        })
        child = tmp_path / "child.yaml"
        child.write_text(child_content, encoding="utf-8")
        result = load_config(str(child), {})
        assert "network" not in result["tests"][0]["metadata"]

    def test_metrics_file_merged(self, tmp_path):
        metrics_file = tmp_path / "metrics.yaml"
        metrics_file.write_text(yaml.dump([
            {"name": "inherited_metric", "metric_of_interest": "val"},
        ]), encoding="utf-8")
        child_content = yaml.dump({
            "metricsFile": str(metrics_file),
            "tests": [{
                "name": "t1",
                "metadata": {},
                "metrics": [{"name": "local_metric", "metric_of_interest": "v"}],
            }]
        })
        child = tmp_path / "child.yaml"
        child.write_text(child_content, encoding="utf-8")
        result = load_config(str(child), {})
        metric_names = [m["name"] for m in result["tests"][0]["metrics"]]
        assert "inherited_metric" in metric_names
        assert "local_metric" in metric_names

    def test_ignore_global_metrics_skips_metrics_file(self, tmp_path):
        metrics_file = tmp_path / "metrics.yaml"
        metrics_file.write_text(yaml.dump([
            {"name": "inherited_metric", "metric_of_interest": "val"},
        ]), encoding="utf-8")
        child_content = yaml.dump({
            "metricsFile": str(metrics_file),
            "tests": [{
                "name": "t1",
                "IgnoreGlobalMetrics": True,
                "metadata": {},
                "metrics": [{"name": "local_metric", "metric_of_interest": "v"}],
            }]
        })
        child = tmp_path / "child.yaml"
        child.write_text(child_content, encoding="utf-8")
        result = load_config(str(child), {})
        metric_names = [m["name"] for m in result["tests"][0]["metrics"]]
        assert "inherited_metric" not in metric_names
        assert "local_metric" in metric_names

    def test_agg_metric_name_format(self, tmp_yaml):
        content = yaml.dump({
            "tests": [{
                "name": "t1",
                "metadata": {},
                "metrics": [
                    {"name": "cpu", "metric_of_interest": "v",
                     "agg": {"agg_type": "avg", "value": "cpu_pct"}},
                ],
            }]
        })
        path = tmp_yaml(content)
        # Should not raise (no duplicate)
        result = load_config(path, {})
        assert result is not None
