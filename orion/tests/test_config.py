"""
Unit tests for config validation in orion/config.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring

import tempfile
import os

import pytest
import yaml

from orion.config import load_config


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
