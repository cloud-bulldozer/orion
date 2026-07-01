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
