"""
Unit Test file for batched queries in Matcher (aggregation and standard).
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error, duplicate-code

from unittest.mock import patch, MagicMock

import pytest
from opensearch_dsl import Search
from opensearch_dsl.response import Response

from orion.tests.test_matcher import make_matcher_fixture


@pytest.fixture
def matcher_instance():
    return make_matcher_fixture(index="ripsaw-kube-burner-*")


@pytest.fixture
def uuid_matcher_instance():
    return make_matcher_fixture(
        index="krkn-telemetry",
        uuid_field="run_uuid",
        version_field="cluster_version",
    )


def _make_metrics():
    return [
        {
            "name": "apiserverCPU",
            "metricName": "containerCPU",
            "labels.namespace.keyword": "openshift-kube-apiserver",
            "metric_of_interest": "cpu",
            "agg": {"value": "cpu", "agg_type": "avg"},
        },
        {
            "name": "etcdCPU",
            "metricName": "containerCPU",
            "labels.namespace.keyword": "openshift-etcd",
            "metric_of_interest": "cpu",
            "agg": {"value": "cpu", "agg_type": "avg"},
        },
        {
            "name": "ovsMemory-Workers",
            "metricName": "containerMemory",
            "labels.namespace.keyword": "openshift-ovs",
            "metric_of_interest": "memory",
            "agg": {"value": "memory", "agg_type": "max"},
        },
    ]


class TestGetAggMetricsBatch:
    """Tests for Matcher.get_agg_metrics_batch."""

    def test_returns_empty_for_no_metrics(self, matcher_instance):
        result = matcher_instance.get_agg_metrics_batch(["uuid1"], [])
        assert result == {}

    def test_builds_single_query_with_multiple_aggs(self, matcher_instance):
        metrics_list = _make_metrics()
        data_dict = {
            "aggregations": {
                "uuid": {
                    "buckets": [
                        {
                            "key": "uuid1",
                            "time": {"value_as_string": "2024-02-09T12:00:00"},
                            "apiserverCPU": {"doc_count": 5, "cpu": {"value": 0.42}},
                            "etcdCPU": {"doc_count": 5, "cpu": {"value": 0.31}},
                            "ovsMemory-Workers": {"doc_count": 5, "memory": {"value": 1024}},
                        },
                        {
                            "key": "uuid2",
                            "time": {"value_as_string": "2024-02-09T13:00:00"},
                            "apiserverCPU": {"doc_count": 5, "cpu": {"value": 0.55}},
                            "etcdCPU": {"doc_count": 5, "cpu": {"value": 0.38}},
                            "ovsMemory-Workers": {"doc_count": 5, "memory": {"value": 2048}},
                        },
                    ]
                }
            }
        }

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = matcher_instance.get_agg_metrics_batch(
                ["uuid1", "uuid2"], metrics_list
            )

        assert isinstance(result, dict)
        assert len(result) == 3
        for m in metrics_list:
            assert m["name"] in result

        assert result["apiserverCPU"] == [
            {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "cpu_avg": 0.42},
            {"uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "cpu_avg": 0.55},
        ]
        assert result["etcdCPU"] == [
            {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "cpu_avg": 0.31},
            {"uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "cpu_avg": 0.38},
        ]
        assert result["ovsMemory-Workers"] == [
            {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "memory_max": 1024},
            {"uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "memory_max": 2048},
        ]

    def test_empty_buckets_returns_empty_lists(self, matcher_instance):
        metrics_list = _make_metrics()
        data_dict = {"aggregations": {"uuid": {"buckets": []}}}

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = matcher_instance.get_agg_metrics_batch(
                ["uuid1"], metrics_list
            )

        for m in metrics_list:
            assert result[m["name"]] == []

    def test_no_aggregations_key_returns_empty_lists(self, matcher_instance):
        metrics_list = _make_metrics()
        data_dict = {"hits": {"hits": []}}

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = matcher_instance.get_agg_metrics_batch(
                ["uuid1"], metrics_list
            )

        for m in metrics_list:
            assert result[m["name"]] == []

    def test_custom_uuid_field(self, uuid_matcher_instance):
        metrics_list = [
            {
                "name": "apiserverCPU",
                "metricName": "containerCPU",
                "metric_of_interest": "cpu",
                "agg": {"value": "cpu", "agg_type": "avg"},
            },
        ]
        data_dict = {
            "aggregations": {
                "uuid": {
                    "buckets": [
                        {
                            "key": "uuid1",
                            "time": {"value_as_string": "2024-02-09T12:00:00"},
                            "apiserverCPU": {"doc_count": 5, "cpu": {"value": 0.42}},
                        },
                    ]
                }
            }
        }

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = uuid_matcher_instance.get_agg_metrics_batch(
                ["uuid1"], metrics_list
            )

        assert result["apiserverCPU"] == [
            {"run_uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "cpu_avg": 0.42},
        ]


class TestGetAggMetricsBatchPercentiles:
    """Tests for percentile aggregations in batch mode."""

    def test_percentile_with_target(self, matcher_instance):
        metrics_list = [
            {
                "name": "api_latency_p99",
                "metricName": "api_latency",
                "metric_of_interest": "response_time_ms",
                "agg": {
                    "value": "response_time_ms",
                    "agg_type": "percentiles",
                    "percents": [50, 95, 99],
                    "target_percentile": 99,
                },
            },
        ]
        data_dict = {
            "aggregations": {
                "uuid": {
                    "buckets": [
                        {
                            "key": "uuid1",
                            "time": {"value_as_string": "2024-02-09T12:00:00"},
                            "api_latency_p99": {
                                "doc_count": 10,
                                "response_time_ms": {
                                    "values": {
                                        "50.0": 100.5,
                                        "95.0": 250.3,
                                        "99.0": 350.7,
                                    }
                                },
                            },
                        },
                    ]
                }
            }
        }

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = matcher_instance.get_agg_metrics_batch(
                ["uuid1"], metrics_list
            )

        assert result["api_latency_p99"] == [
            {
                "uuid": "uuid1",
                "timestamp": "2024-02-09T12:00:00",
                "response_time_ms_percentiles_99.0": 350.7,
            },
        ]

    def test_percentile_without_target(self, matcher_instance):
        metrics_list = [
            {
                "name": "api_latency_all",
                "metricName": "api_latency",
                "metric_of_interest": "response_time_ms",
                "agg": {
                    "value": "response_time_ms",
                    "agg_type": "percentiles",
                    "percents": [50, 95, 99],
                },
            },
        ]
        data_dict = {
            "aggregations": {
                "uuid": {
                    "buckets": [
                        {
                            "key": "uuid1",
                            "time": {"value_as_string": "2024-02-09T12:00:00"},
                            "api_latency_all": {
                                "doc_count": 10,
                                "response_time_ms": {
                                    "values": {
                                        "50.0": 100.5,
                                        "95.0": 250.3,
                                        "99.0": 350.7,
                                    }
                                },
                            },
                        },
                    ]
                }
            }
        }

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = matcher_instance.get_agg_metrics_batch(
                ["uuid1"], metrics_list
            )

        assert result["api_latency_all"] == [
            {
                "uuid": "uuid1",
                "timestamp": "2024-02-09T12:00:00",
                "response_time_ms_percentiles_50.0": 100.5,
                "response_time_ms_percentiles_95.0": 250.3,
                "response_time_ms_percentiles_99.0": 350.7,
            },
        ]


class TestGetAggMetricsBatchCount:
    """Tests for count aggregation in batch mode."""

    def test_count_aggregation(self, matcher_instance):
        metrics_list = [
            {
                "name": "api_requests",
                "metricName": "apiCalls",
                "metric_of_interest": "request_id",
                "agg": {"value": "request_id", "agg_type": "count"},
            },
        ]
        data_dict = {
            "aggregations": {
                "uuid": {
                    "buckets": [
                        {
                            "key": "uuid1",
                            "time": {"value_as_string": "2024-02-09T12:00:00"},
                            "api_requests": {
                                "doc_count": 10,
                                "request_id": {"value": 1250},
                            },
                        },
                    ]
                }
            }
        }

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = matcher_instance.get_agg_metrics_batch(
                ["uuid1"], metrics_list
            )

        assert result["api_requests"] == [
            {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "request_id_count": 1250},
        ]

    def test_count_aggregation_multiple_uuids(self, matcher_instance):
        metrics_list = [
            {
                "name": "api_requests",
                "metricName": "apiCalls",
                "metric_of_interest": "request_id",
                "agg": {"value": "request_id", "agg_type": "count"},
            },
        ]
        data_dict = {
            "aggregations": {
                "uuid": {
                    "buckets": [
                        {
                            "key": "uuid1",
                            "time": {"value_as_string": "2024-02-09T12:00:00"},
                            "api_requests": {
                                "doc_count": 10,
                                "request_id": {"value": 1250},
                            },
                        },
                        {
                            "key": "uuid2",
                            "time": {"value_as_string": "2024-02-09T13:00:00"},
                            "api_requests": {
                                "doc_count": 15,
                                "request_id": {"value": 1520},
                            },
                        },
                    ]
                }
            }
        }

        def mock_execute(self):
            return Response(response=data_dict, search=self)

        with patch.object(Search, "execute", mock_execute):
            result = matcher_instance.get_agg_metrics_batch(
                ["uuid1", "uuid2"], metrics_list
            )

        assert result["api_requests"] == [
            {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "request_id_count": 1250},
            {"uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "request_id_count": 1520},
        ]


def _make_fake_hit(source_dict):
    """Build a MagicMock that behaves like an opensearch-dsl hit."""
    hit = MagicMock()
    hit.to_dict.return_value = {"_source": source_dict}
    return hit


def _make_standard_metrics():
    """Two standard metrics with different metricName values."""
    return [
        {
            "name": "podReadyLatency",
            "metricName": "podLatencyQuantilesMeasurement",
            "quantileName": "Ready",
            "metric_of_interest": "P99",
            "not": {"jobName.keyword": "garbage-collection"},
        },
        {
            "name": "apiserverCPU",
            "metricName": "containerCPU",
            "labels.namespace.keyword": "openshift-kube-apiserver",
            "metric_of_interest": "cpu",
        },
    ]


class TestGetResultsBatch:
    """Tests for Matcher.get_results_batch."""

    def test_returns_empty_for_no_metrics(self, matcher_instance):
        result = matcher_instance.get_results_batch(["uuid1"], [])
        assert result == {}

    def test_partitioned_results_two_metrics(self, matcher_instance, monkeypatch):
        metrics_list = _make_standard_metrics()

        fake_hits = [
            _make_fake_hit({
                "uuid": "uuid1",
                "metricName": "podLatencyQuantilesMeasurement",
                "quantileName": "Ready",
                "P99": 4500,
                "timestamp": "2024-02-09T12:00:00",
            }),
            _make_fake_hit({
                "uuid": "uuid2",
                "metricName": "podLatencyQuantilesMeasurement",
                "quantileName": "Ready",
                "P99": 5200,
                "timestamp": "2024-02-09T13:00:00",
            }),
            _make_fake_hit({
                "uuid": "uuid1",
                "metricName": "containerCPU",
                "labels.namespace": "openshift-kube-apiserver",
                "cpu": 0.42,
                "timestamp": "2024-02-09T12:00:00",
            }),
            _make_fake_hit({
                "uuid": "uuid2",
                "metricName": "containerCPU",
                "labels.namespace": "openshift-kube-apiserver",
                "cpu": 0.55,
                "timestamp": "2024-02-09T13:00:00",
            }),
        ]

        monkeypatch.setattr(matcher_instance, "query_index",
                            lambda *a, **k: fake_hits)

        result = matcher_instance.get_results_batch(
            ["uuid1", "uuid2"], metrics_list
        )

        assert isinstance(result, dict)
        assert len(result) == 2

        assert result["podReadyLatency"] == [
            {
                "uuid": "uuid1",
                "metricName": "podLatencyQuantilesMeasurement",
                "quantileName": "Ready",
                "P99": 4500,
                "timestamp": "2024-02-09T12:00:00",
            },
            {
                "uuid": "uuid2",
                "metricName": "podLatencyQuantilesMeasurement",
                "quantileName": "Ready",
                "P99": 5200,
                "timestamp": "2024-02-09T13:00:00",
            },
        ]
        assert result["apiserverCPU"] == [
            {
                "uuid": "uuid1",
                "metricName": "containerCPU",
                "labels.namespace": "openshift-kube-apiserver",
                "cpu": 0.42,
                "timestamp": "2024-02-09T12:00:00",
            },
            {
                "uuid": "uuid2",
                "metricName": "containerCPU",
                "labels.namespace": "openshift-kube-apiserver",
                "cpu": 0.55,
                "timestamp": "2024-02-09T13:00:00",
            },
        ]

    def test_no_hits_returns_empty_lists(self, matcher_instance, monkeypatch):
        metrics_list = _make_standard_metrics()
        monkeypatch.setattr(matcher_instance, "query_index",
                            lambda *a, **k: [])

        result = matcher_instance.get_results_batch(
            ["uuid1"], metrics_list
        )

        for m in metrics_list:
            assert result[m["name"]] == []

    def test_custom_uuid_field(self, uuid_matcher_instance, monkeypatch):
        metrics_list = [
            {
                "name": "nodeCPU",
                "metricName": "nodeCPUSeconds-Infra",
                "mode": "iowait",
                "metric_of_interest": "value",
            },
        ]

        fake_hits = [
            _make_fake_hit({
                "run_uuid": "uuid1",
                "metricName": "nodeCPUSeconds-Infra",
                "mode": "iowait",
                "value": 3.14,
                "timestamp": "2024-02-09T12:00:00",
            }),
        ]

        monkeypatch.setattr(uuid_matcher_instance, "query_index",
                            lambda *a, **k: fake_hits)

        result = uuid_matcher_instance.get_results_batch(
            ["uuid1"], metrics_list
        )

        assert result["nodeCPU"] == [
            {
                "run_uuid": "uuid1",
                "metricName": "nodeCPUSeconds-Infra",
                "mode": "iowait",
                "value": 3.14,
                "timestamp": "2024-02-09T12:00:00",
            },
        ]

    def test_unmatched_metric_name_skipped(self, matcher_instance, monkeypatch):
        """Hits with a metricName not in the metrics list are dropped."""
        metrics_list = [
            {
                "name": "apiserverCPU",
                "metricName": "containerCPU",
                "metric_of_interest": "cpu",
            },
        ]

        fake_hits = [
            _make_fake_hit({
                "uuid": "uuid1",
                "metricName": "containerCPU",
                "cpu": 0.42,
            }),
            _make_fake_hit({
                "uuid": "uuid1",
                "metricName": "unknownMetric",
                "foo": "bar",
            }),
        ]

        monkeypatch.setattr(matcher_instance, "query_index",
                            lambda *a, **k: fake_hits)

        result = matcher_instance.get_results_batch(
            ["uuid1"], metrics_list
        )

        assert len(result["apiserverCPU"]) == 1
        assert result["apiserverCPU"][0]["metricName"] == "containerCPU"
