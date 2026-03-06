"""
Unit tests for fan_out metric expansion in config.py
"""

# pylint: disable = missing-function-docstring

import logging
import pytest

from orion.config import expand_fan_out, _substitute_vars, _replace_placeholders
from orion.logger import SingletonLogger


@pytest.fixture(autouse=True)
def logger():
    SingletonLogger(debug=logging.INFO, name="Orion")
    return SingletonLogger.get_logger("Orion")


class TestReplacePlaceholders:
    def test_single_placeholder(self):
        assert _replace_placeholders("${name}CPU", {"name": "apiserver"}) == "apiserverCPU"

    def test_multiple_placeholders(self):
        result = _replace_placeholders("${prefix}-${suffix}", {"prefix": "ovn", "suffix": "cpu"})
        assert result == "ovn-cpu"

    def test_unmatched_placeholder_left_as_is(self):
        assert _replace_placeholders("${missing}", {"other": "val"}) == "${missing}"

    def test_no_placeholders(self):
        assert _replace_placeholders("plain string", {"name": "val"}) == "plain string"

    def test_placeholder_in_middle(self):
        result = _replace_placeholders("[Jira: ${label}]", {"label": "etcd"})
        assert result == "[Jira: etcd]"

    def test_numeric_value(self):
        assert _replace_placeholders("threshold-${val}", {"val": 10}) == "threshold-10"


class TestSubstituteVars:
    def test_dict_values(self):
        obj = {"name": "${n}", "other": "fixed"}
        _substitute_vars(obj, {"n": "test"})
        assert obj == {"name": "test", "other": "fixed"}

    def test_nested_dict(self):
        obj = {"agg": {"value": "${field}", "agg_type": "avg"}}
        _substitute_vars(obj, {"field": "cpu"})
        assert obj == {"agg": {"value": "cpu", "agg_type": "avg"}}

    def test_list_values(self):
        obj = {"labels": ["[Jira: ${label}]"]}
        _substitute_vars(obj, {"label": "etcd"})
        assert obj == {"labels": ["[Jira: etcd]"]}

    def test_list_of_dicts(self):
        obj = [{"name": "${n}"}]
        _substitute_vars(obj, {"n": "test"})
        assert obj == [{"name": "test"}]

    def test_non_string_values_unchanged(self):
        obj = {"direction": 1, "threshold": 10}
        _substitute_vars(obj, {"direction": "99"})
        assert obj == {"direction": 1, "threshold": 10}


class TestExpandFanOut:
    def test_no_fan_out_passthrough(self, logger):
        metrics = [
            {"name": "cpuMetric", "metricName.keyword": "containerCPU", "direction": 1}
        ]
        result = expand_fan_out(metrics, logger)
        assert len(result) == 1
        assert result[0]["name"] == "cpuMetric"

    def test_basic_fan_out(self, logger):
        metrics = [{
            "name": "${label}CPU",
            "metricName.keyword": "containerCPU",
            "labels.namespace.keyword": "${namespace}",
            "metric_of_interest": "value",
            "direction": 1,
            "threshold": 10,
            "fan_out": [
                {"label": "apiserver", "namespace": "openshift-kube-apiserver"},
                {"label": "multus", "namespace": "openshift-multus"},
            ]
        }]
        result = expand_fan_out(metrics, logger)
        assert len(result) == 2
        assert result[0]["name"] == "apiserverCPU"
        assert result[0]["labels.namespace.keyword"] == "openshift-kube-apiserver"
        assert result[1]["name"] == "multusCPU"
        assert result[1]["labels.namespace.keyword"] == "openshift-multus"
        # fan_out key should be removed
        assert "fan_out" not in result[0]
        assert "fan_out" not in result[1]

    def test_field_override(self, logger):
        metrics = [{
            "name": "ovnCPU-${container}",
            "metricName.keyword": "containerCPU",
            "labels.container.keyword": "${container}",
            "direction": 1,
            "fan_out": [
                {"container": "northd"},
                {"container": "ovncontroller", "labels.container.keyword": "ovn-controller"},
            ]
        }]
        result = expand_fan_out(metrics, logger)
        assert len(result) == 2
        # First entry: no override, substitution applies
        assert result[0]["name"] == "ovnCPU-northd"
        assert result[0]["labels.container.keyword"] == "northd"
        # Second entry: override takes precedence
        assert result[1]["name"] == "ovnCPU-ovncontroller"
        assert result[1]["labels.container.keyword"] == "ovn-controller"

    def test_nested_substitution_in_agg(self, logger):
        metrics = [{
            "name": "${label}-${agg_type}",
            "metricName.keyword": "containerCPU",
            "metric_of_interest": "value",
            "agg": {"value": "${resource}", "agg_type": "${agg_type}"},
            "direction": 1,
            "fan_out": [
                {"label": "apiserverCPU", "resource": "cpu", "agg_type": "avg"},
                {"label": "apiserverMem", "resource": "mem", "agg_type": "max"},
            ]
        }]
        result = expand_fan_out(metrics, logger)
        assert len(result) == 2
        assert result[0]["agg"] == {"value": "cpu", "agg_type": "avg"}
        assert result[1]["agg"] == {"value": "mem", "agg_type": "max"}

    def test_substitution_in_labels_list(self, logger):
        metrics = [{
            "name": "${name}",
            "metricName.keyword": "containerCPU",
            "direction": 1,
            "labels": ["[Jira: ${jira}]"],
            "fan_out": [
                {"name": "apiserverCPU", "jira": "kube-apiserver"},
            ]
        }]
        result = expand_fan_out(metrics, logger)
        assert result[0]["labels"] == ["[Jira: kube-apiserver]"]

    def test_mixed_metrics_with_and_without_fan_out(self, logger):
        metrics = [
            {"name": "standalone", "metricName.keyword": "podLatency", "direction": 1},
            {
                "name": "${label}CPU",
                "metricName.keyword": "containerCPU",
                "direction": 1,
                "fan_out": [
                    {"label": "apiserver"},
                    {"label": "multus"},
                ]
            },
            {"name": "anotherStandalone", "metricName.keyword": "kubeletCPU", "direction": 1},
        ]
        result = expand_fan_out(metrics, logger)
        assert len(result) == 4
        assert result[0]["name"] == "standalone"
        assert result[1]["name"] == "apiserverCPU"
        assert result[2]["name"] == "multusCPU"
        assert result[3]["name"] == "anotherStandalone"

    def test_empty_fan_out_produces_no_metrics(self, logger):
        metrics = [{
            "name": "${label}CPU",
            "metricName.keyword": "containerCPU",
            "direction": 1,
            "fan_out": []
        }]
        result = expand_fan_out(metrics, logger)
        assert len(result) == 0

    def test_unmatched_placeholders_preserved(self, logger):
        metrics = [{
            "name": "${defined}-${undefined}",
            "metricName.keyword": "containerCPU",
            "direction": 1,
            "fan_out": [
                {"defined": "test"},
            ]
        }]
        result = expand_fan_out(metrics, logger)
        assert result[0]["name"] == "test-${undefined}"

    def test_fan_out_entries_are_independent(self, logger):
        """Verify that modifying one expanded metric doesn't affect others."""
        metrics = [{
            "name": "${label}CPU",
            "metricName.keyword": "containerCPU",
            "agg": {"value": "cpu", "agg_type": "avg"},
            "direction": 1,
            "fan_out": [
                {"label": "apiserver"},
                {"label": "multus"},
            ]
        }]
        result = expand_fan_out(metrics, logger)
        # Mutate one result's nested dict
        result[0]["agg"]["value"] = "mem"
        # Other result should be unaffected (deep copy)
        assert result[1]["agg"]["value"] == "cpu"

    def test_substitution_in_not_dict(self, logger):
        metrics = [{
            "name": "${label}",
            "metricName.keyword": "containerCPU",
            "direction": 1,
            "not": {"jobConfig.name": "${exclude}"},
            "fan_out": [
                {"label": "test", "exclude": "garbage-collection"},
            ]
        }]
        result = expand_fan_out(metrics, logger)
        assert result[0]["not"] == {"jobConfig.name": "garbage-collection"}
