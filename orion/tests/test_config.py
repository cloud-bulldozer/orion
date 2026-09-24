"""
Unit tests for config validation in orion/config.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring

import tempfile
import os

import pytest
import yaml

from orion.config import load_config, collect_pull_numbers


def _write_config(tmp_dir, config_dict, filename="config.yaml"):
    """Write a config dict as YAML to a temp file and return its path."""
    path = os.path.join(tmp_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f)
    return path


_METRIC = {
    "name": "m1",
    "metricName": "test",
    "metric_of_interest": "value",
    "threshold": 10,
    "direction": 1,
}


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


class TestWildcardKeywordValidation:
    """Tests that leading '*' on .keyword wildcard fields triggers a warning."""

    def test_leading_star_keyword_warns_but_passes(self):
        config = { "tests": [ {
                    "name": "test1",
                    "metadata": {
                        "platform": "AWS",
                        "wildcard": { "upstreamJob.keyword": "*some-job*", },
                    },
                    "metrics": [ {
                            "name": "m1",
                            "metricName": "test",
                            "metric_of_interest": "value",
                            "threshold": 10,
                            "direction": 1,
                        } ], } ] }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_config(tmp_dir, config)
            result = load_config(path, {})
            assert result is not None
            assert len(result["tests"]) == 1

    def test_trailing_star_keyword_passes(self):
        config = { "tests": [ {
                    "name": "test1",
                    "metadata": {
                        "platform": "AWS",
                        "wildcard": { "upstreamJob.keyword": "some-job*", },
                    },
                    "metrics": [ {
                            "name": "m1",
                            "metricName": "test",
                            "metric_of_interest": "value",
                            "threshold": 10,
                            "direction": 1,
                        } ], } ] }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_config(tmp_dir, config)
            result = load_config(path, {})
            assert result is not None
            assert len(result["tests"]) == 1

    def test_non_keyword_wildcard_field_passes(self):
        config = {
            "tests": [
                {
                    "name": "test1",
                    "metadata": {
                        "platform": "AWS",
                        "wildcard": {
                            "ocpVersion": "4.17*",
                        },
                    },
                    "metrics": [
                        {
                            "name": "m1",
                            "metricName": "test",
                            "metric_of_interest": "value",
                            "threshold": 10,
                            "direction": 1,
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = _write_config(tmp_dir, config)
            result = load_config(path, {})
            assert result is not None
            assert len(result["tests"]) == 1


class TestParentConfigMerge:
    """Tests for parentConfig / metricsFile inheritance."""

    @staticmethod
    def _child(metadata=None, **extra):
        test = {"name": "test1", "metrics": [_METRIC]}
        if metadata is not None:
            test["metadata"] = metadata
        test.update(extra)
        return {"parentConfig": "parent.yaml", "tests": [test]}

    def _load_with_parent(self, tmp_dir, child, parent):
        _write_config(tmp_dir, parent, filename="parent.yaml")
        path = _write_config(tmp_dir, child)
        return load_config(path, {})["tests"][0]

    def test_parent_metadata_inherited_when_child_has_none(self):
        parent = {"platform": "AWS", "benchmark.keyword": "test-bench"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load_with_parent(tmp_dir, self._child(), parent)
            assert test["metadata"]["platform"] == "AWS"
            assert test["metadata"]["benchmark.keyword"] == "test-bench"

    def test_child_metadata_takes_precedence(self):
        parent = {"platform": "AWS", "workerNodesType": "m6i.2xlarge"}
        child = self._child({"workerNodesType": "m6i.4xlarge"})
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load_with_parent(tmp_dir, child, parent)
            assert test["metadata"]["workerNodesType"] == "m6i.4xlarge"
            assert test["metadata"]["platform"] == "AWS"

    def test_child_wildcard_replaces_parent_wildcard_wholesale(self):
        # merge_configs is a shallow merge, so a child that defines `wildcard`
        # drops every key the parent had under it. A config narrowing on
        # upstreamJob must therefore restate ocpVersion or it silently widens
        # its query to every OCP version.
        parent = {"platform": "AWS", "wildcard": {"ocpVersion": "4.17*"}}
        child = self._child({"wildcard": {"upstreamJob.keyword": "*my-job*"}})
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load_with_parent(tmp_dir, child, parent)
            assert test["metadata"]["wildcard"] == {"upstreamJob.keyword": "*my-job*"}
            assert "ocpVersion" not in test["metadata"]["wildcard"]

    def test_child_wildcard_may_restate_inherited_keys(self):
        parent = {"platform": "AWS", "wildcard": {"ocpVersion": "4.17*"}}
        child = self._child(
            {"wildcard": {"ocpVersion": "4.17*", "upstreamJob.keyword": "*my-job*"}}
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load_with_parent(tmp_dir, child, parent)
            assert test["metadata"]["wildcard"] == {
                "ocpVersion": "4.17*",
                "upstreamJob.keyword": "*my-job*",
            }

    def test_ignore_global_skips_parent_metadata(self):
        parent = {"platform": "AWS"}
        child = self._child({"platform": "GCP"}, IgnoreGlobal=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load_with_parent(tmp_dir, child, parent)
            assert test["metadata"] == {"platform": "GCP"}


class TestMetricsFileMerge:
    """Tests for metrics inherited through metricsFile."""

    @staticmethod
    def _child(metrics=None, **extra):
        test = {"name": "test1", "metadata": {"platform": "AWS"}}
        if metrics is not None:
            test["metrics"] = metrics
        test.update(extra)
        return {"metricsFile": "metrics.yaml", "tests": [test]}

    def _load(self, tmp_dir, child, shared_metrics):
        path = os.path.join(tmp_dir, "metrics.yaml")
        with open(path, "w", encoding="utf-8") as handle:
            yaml.dump(shared_metrics, handle)
        return load_config(_write_config(tmp_dir, child), {})["tests"][0]

    def test_shared_metrics_are_inherited(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load(tmp_dir, self._child(), [_METRIC])
            assert [m["name"] for m in test["metrics"]] == ["m1"]

    def test_ignore_global_metrics_skips_shared_list(self):
        local = dict(_METRIC, name="local-only")
        child = self._child([local], IgnoreGlobalMetrics=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load(tmp_dir, child, [_METRIC])
            assert [m["name"] for m in test["metrics"]] == ["local-only"]

    def test_shared_metrics_expand_fan_out(self):
        shared = [
            {
                "name": "${job}-latency",
                "metricName": "test",
                "jobName": "${job}",
                "metric_of_interest": "value",
                "direction": 1,
                "threshold": 10,
                "fan_out": [{"job": "job-a"}, {"job": "job-b"}],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            test = self._load(tmp_dir, self._child(), shared)
            assert [m["name"] for m in test["metrics"]] == ["job-a-latency", "job-b-latency"]
            assert [m["jobName"] for m in test["metrics"]] == ["job-a", "job-b"]

    def test_fan_out_template_with_constant_name_exits(self):
        # A fan_out template whose `name` omits the varying placeholder expands
        # to duplicates; the loader rejects that rather than silently
        # collapsing the series.
        shared = [
            {
                "name": "constant-name",
                "metricName": "test",
                "jobName": "${job}",
                "metric_of_interest": "value",
                "direction": 1,
                "threshold": 10,
                "fan_out": [{"job": "job-a"}, {"job": "job-b"}],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(SystemExit):
                self._load(tmp_dir, self._child(), shared)


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
