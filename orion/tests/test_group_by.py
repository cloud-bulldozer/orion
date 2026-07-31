"""
Unit tests for group_by dynamic metric expansion
"""

# pylint: disable = missing-function-docstring

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError

from orion.config import expand_group_by, _replace_placeholders
from orion.matcher import Matcher
from orion.logger import SingletonLogger


@pytest.fixture(autouse=True)
def logger():
    SingletonLogger(debug=logging.INFO, name="Orion")
    return SingletonLogger.get_logger("Orion")


def _make_matcher(index="perf-scale-ci"):
    matcher = MagicMock(spec=Matcher)
    matcher.index = index
    matcher.uuid_field = "uuid"
    matcher.es = MagicMock()
    matcher.logger = MagicMock()
    return matcher


def _mock_agg_response(values):
    buckets = [SimpleNamespace(key=v) for v in values]
    aggs = SimpleNamespace(group_values=SimpleNamespace(buckets=buckets))
    resp = MagicMock()
    resp.aggregations = aggs
    return resp


class TestDottedPlaceholders:
    def test_dotted_field_name_substitution(self):
        result = _replace_placeholders(
            "${labels.namespace.keyword}CPU",
            {"labels.namespace.keyword": "etcd"}
        )
        assert result == "etcdCPU"

    def test_dotted_and_simple_mixed(self):
        result = _replace_placeholders(
            "${labels.namespace.keyword}-${name}",
            {"labels.namespace.keyword": "etcd", "name": "cpu"}
        )
        assert result == "etcd-cpu"

    def test_simple_placeholder_still_works(self):
        result = _replace_placeholders("${label}CPU", {"label": "apiserver"})
        assert result == "apiserverCPU"


class TestDiscoverFieldValues:
    @patch("orion.matcher.Search")
    def test_returns_sorted_values(self, mock_search_cls, logger):
        matcher = Matcher.__new__(Matcher)
        matcher.uuid_field = "uuid"
        matcher.es = MagicMock()
        matcher.index = "perf-scale-ci"
        matcher.logger = MagicMock()

        resp = _mock_agg_response(["openshift-multus", "openshift-etcd", "openshift-kube-apiserver"])
        mock_search_instance = MagicMock()
        mock_search_cls.return_value.query.return_value.extra.return_value = mock_search_instance
        mock_search_instance.aggs = MagicMock()
        mock_search_instance.execute.return_value = resp

        metric = {"name": "${labels.namespace.keyword}CPU", "metricName.keyword": "containerCPU"}
        values = matcher.discover_field_values(metric, "labels.namespace.keyword", ["uuid1", "uuid2"])

        assert values == ["openshift-etcd", "openshift-kube-apiserver", "openshift-multus"]

    @patch("orion.matcher.Search")
    def test_empty_response(self, mock_search_cls, logger):
        matcher = Matcher.__new__(Matcher)
        matcher.uuid_field = "uuid"
        matcher.es = MagicMock()
        matcher.index = "perf-scale-ci"
        matcher.logger = MagicMock()

        resp = MagicMock()
        resp.aggregations = SimpleNamespace(group_values=SimpleNamespace(buckets=[]))
        mock_search_instance = MagicMock()
        mock_search_cls.return_value.query.return_value.extra.return_value = mock_search_instance
        mock_search_instance.aggs = MagicMock()
        mock_search_instance.execute.return_value = resp

        metric = {"name": "test", "metricName.keyword": "containerCPU"}
        values = matcher.discover_field_values(metric, "labels.namespace.keyword", ["uuid1"])

        assert values == []

    @patch("orion.matcher.Search")
    def test_no_aggregations_attr(self, mock_search_cls, logger):
        matcher = Matcher.__new__(Matcher)
        matcher.uuid_field = "uuid"
        matcher.es = MagicMock()
        matcher.index = "perf-scale-ci"
        matcher.logger = MagicMock()

        resp = MagicMock(spec=[])
        mock_search_instance = MagicMock()
        mock_search_cls.return_value.query.return_value.extra.return_value = mock_search_instance
        mock_search_instance.aggs = MagicMock()
        mock_search_instance.execute.return_value = resp

        metric = {"name": "test", "metricName.keyword": "containerCPU"}
        values = matcher.discover_field_values(metric, "labels.namespace.keyword", ["uuid1"])

        assert values == []

    @patch("orion.matcher.Search")
    def test_connection_error_returns_empty(self, mock_search_cls, logger):
        matcher = Matcher.__new__(Matcher)
        matcher.uuid_field = "uuid"
        matcher.es = MagicMock()
        matcher.index = "perf-scale-ci"
        matcher.logger = MagicMock()

        mock_search_instance = MagicMock()
        mock_search_cls.return_value.query.return_value.extra.return_value = mock_search_instance
        mock_search_instance.aggs = MagicMock()
        mock_search_instance.execute.side_effect = OpenSearchConnectionError("connection refused")

        metric = {"name": "test", "metricName.keyword": "containerCPU"}
        values = matcher.discover_field_values(metric, "labels.namespace.keyword", ["uuid1"])

        assert values == []
        matcher.logger.warning.assert_called_once()


class TestExpandGroupBy:
    def test_no_group_by_passthrough(self, logger):
        metrics = [{"name": "cpuMetric", "metricName.keyword": "containerCPU"}]
        matcher = _make_matcher()
        result = expand_group_by(metrics, matcher, ["uuid1"], logger)
        assert len(result) == 1
        assert result[0]["name"] == "cpuMetric"

    def test_single_field_expansion(self, logger):
        matcher = _make_matcher()
        matcher.discover_field_values.return_value = ["openshift-etcd", "openshift-kube-apiserver"]
        metrics = [{
            "name": "${labels.namespace.keyword}CPU",
            "metricName.keyword": "containerCPU",
            "metric_of_interest": "value",
            "group_by": ["labels.namespace.keyword"],
        }]
        result = expand_group_by(metrics, matcher, ["uuid1"], logger)

        assert len(result) == 2
        assert result[0]["name"] == "openshift-etcdCPU"
        assert result[0]["labels.namespace.keyword"] == "openshift-etcd"
        assert result[1]["name"] == "openshift-kube-apiserverCPU"
        assert result[1]["labels.namespace.keyword"] == "openshift-kube-apiserver"

    def test_group_by_key_stripped(self, logger):
        matcher = _make_matcher()
        matcher.discover_field_values.return_value = ["val1"]
        metrics = [{
            "name": "${labels.namespace.keyword}",
            "metricName.keyword": "containerCPU",
            "group_by": ["labels.namespace.keyword"],
        }]
        result = expand_group_by(metrics, matcher, ["uuid1"], logger)

        assert len(result) == 1
        assert "group_by" not in result[0]

    def test_no_values_skips_metric(self, logger):
        matcher = _make_matcher()
        matcher.discover_field_values.return_value = []
        metrics = [{
            "name": "${labels.namespace.keyword}CPU",
            "metricName.keyword": "containerCPU",
            "group_by": ["labels.namespace.keyword"],
        }]
        result = expand_group_by(metrics, matcher, ["uuid1"], logger)

        assert len(result) == 0

    def test_mixed_metrics(self, logger):
        matcher = _make_matcher()
        matcher.discover_field_values.return_value = ["ns1", "ns2"]
        metrics = [
            {"name": "standalone", "metricName.keyword": "podLatency"},
            {
                "name": "${labels.namespace.keyword}CPU",
                "metricName.keyword": "containerCPU",
                "group_by": ["labels.namespace.keyword"],
            },
            {"name": "anotherStandalone", "metricName.keyword": "kubeletCPU"},
        ]
        result = expand_group_by(metrics, matcher, ["uuid1"], logger)

        assert len(result) == 4
        assert result[0]["name"] == "standalone"
        assert result[1]["name"] == "ns1CPU"
        assert result[2]["name"] == "ns2CPU"
        assert result[3]["name"] == "anotherStandalone"

    def test_entries_are_independent(self, logger):
        matcher = _make_matcher()
        matcher.discover_field_values.return_value = ["ns1", "ns2"]
        metrics = [{
            "name": "${labels.namespace.keyword}",
            "metricName.keyword": "containerCPU",
            "agg": {"value": "cpu", "agg_type": "avg"},
            "group_by": ["labels.namespace.keyword"],
        }]
        result = expand_group_by(metrics, matcher, ["uuid1"], logger)

        result[0]["agg"]["value"] = "mem"
        assert result[1]["agg"]["value"] == "cpu"

    def test_string_group_by_coerced_to_list(self, logger):
        matcher = _make_matcher()
        matcher.discover_field_values.return_value = ["val1"]
        metrics = [{
            "name": "${labels.namespace.keyword}",
            "metricName.keyword": "containerCPU",
            "group_by": "labels.namespace.keyword",
        }]
        result = expand_group_by(metrics, matcher, ["uuid1"], logger)

        assert len(result) == 1
        assert result[0]["name"] == "val1"

    def test_multiple_fields_errors(self, logger):
        metrics = [{
            "name": "test",
            "group_by": ["field1", "field2"],
        }]
        matcher = _make_matcher()
        with pytest.raises(SystemExit):
            expand_group_by(metrics, matcher, ["uuid1"], logger)
