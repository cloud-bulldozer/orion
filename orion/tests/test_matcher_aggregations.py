"""
Unit Test file for matcher aggregation functionality
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error, duplicate-code
import pytest
from opensearch_dsl.response import Response

# Import shared fixtures and helpers from test_matcher
from orion.tests.test_matcher import make_matcher_fixture


@pytest.fixture
def matcher_instance():
    return make_matcher_fixture(index="perf-scale-ci")


@pytest.fixture
def uuid_matcher_instance():
    return make_matcher_fixture(
        index="krkn-telemetry",
        uuid_field="run_uuid",
        version_field="cluster_version",
    )


@pytest.mark.parametrize(
    "fixture_name,test_uuids,test_metrics,data_dict,expected",
    [
        # matcher_instance with values
        (
            "matcher_instance",
            ["uuid1", "uuid2"],
            {
                "name": "apiserverCPU",
                "metricName": "containerCPU",
                "labels.namespace": "openshift-kube-apiserver",
                "metric_of_interest": "value",
                "agg": {"value": "cpu", "agg_type": "avg"},
            },
            {
                "aggregations": {
                    "time": {
                        "buckets": [
                            {"key": "uuid1", "time": {"value_as_string": "2024-02-09T12:00:00"}},
                            {"key": "uuid2", "time": {"value_as_string": "2024-02-09T13:00:00"}},
                        ]
                    },
                    "uuid": {
                        "buckets": [
                            {"key": "uuid1", "cpu": {"value": 42}},
                            {"key": "uuid2", "cpu": {"value": 56}},
                        ]
                    },
                }
            },
            [
                {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "cpu_avg": 42},
                {"uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "cpu_avg": 56},
            ],
        ),
        # uuid_matcher_instance with values
        (
            "uuid_matcher_instance",
            ["uuid1", "uuid2"],
            {
                "name": "apiserverCPU",
                "metricName": "containerCPU",
                "labels.namespace": "openshift-kube-apiserver",
                "metric_of_interest": "value",
                "agg": {"value": "cpu", "agg_type": "avg"},
            },
            {
                "aggregations": {
                    "time": {
                        "buckets": [
                            {"key": "uuid1", "time": {"value_as_string": "2024-02-09T12:00:00"}},
                            {"key": "uuid2", "time": {"value_as_string": "2024-02-09T13:00:00"}},
                        ]
                    },
                    "uuid": {
                        "buckets": [
                            {"key": "uuid1", "cpu": {"value": 42}},
                            {"key": "uuid2", "cpu": {"value": 56}},
                        ]
                    },
                }
            },
            [
                {"run_uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "cpu_avg": 42},
                {"run_uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "cpu_avg": 56},
            ],
        ),
        # matcher_instance with no agg values
        (
            "matcher_instance",
            ["uuid1", "uuid2"],
            {
                "name": "apiserverCPU",
                "metricName": "containerCPU",
                "labels.namespace": "openshift-kube-apiserver",
                "metric_of_interest": "value",
                "agg": {"value": "cpu", "agg_type": "avg"},
            },
            {
                "aggregations": {
                    "time": {
                        "buckets": [
                            {"key": "uuid1", "time": {"value_as_string": "2024-02-09T12:00:00"}},
                            {"key": "uuid2", "time": {"value_as_string": "2024-02-09T13:00:00"}},
                        ]
                    },
                    "uuid": {"buckets": []},
                }
            },
            [
                {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "cpu_avg": None},
                {"uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "cpu_avg": None},
            ],
        ),
        # matcher_instance with count aggregation
        (
            "matcher_instance",
            ["uuid1", "uuid2"],
            {
                "name": "api_requests",
                "metricName": "apiCalls",
                "metric_of_interest": "request_id",
                "agg": {"value": "request_id", "agg_type": "count"},
            },
            {
                "aggregations": {
                    "time": {
                        "buckets": [
                            {"key": "uuid1", "time": {"value_as_string": "2024-02-09T12:00:00"}},
                            {"key": "uuid2", "time": {"value_as_string": "2024-02-09T13:00:00"}},
                        ]
                    },
                    "uuid": {
                        "buckets": [
                            {"key": "uuid1", "request_id": {"value": 1250}},
                            {"key": "uuid2", "request_id": {"value": 1520}},
                        ]
                    },
                }
            },
            [
                {"uuid": "uuid1", "timestamp": "2024-02-09T12:00:00", "request_id_count": 1250},
                {"uuid": "uuid2", "timestamp": "2024-02-09T13:00:00", "request_id_count": 1520},
            ],
        ),
    ],
)
def test_get_agg_metric_query_variants(request,
                                       fixture_name,
                                       test_uuids,
                                       test_metrics,
                                       data_dict,
                                       expected):
    matcher = request.getfixturevalue(fixture_name)
    matcher.query_index = lambda *args, **kwargs: Response(response=data_dict, search=data_dict)

    result = matcher.get_agg_metric_query(test_uuids, test_metrics)
    assert result == expected


@pytest.mark.parametrize(
    "fixture_name,test_uuids,test_metrics,data_dict,expected",
    [
        # Test percentile aggregation with default target (95th percentile)
        (
            "matcher_instance",
            ["uuid1", "uuid2"],
            {
                "name": "api_latency_p95",
                "metricName": "api_latency",
                "metric_of_interest": "response_time_ms",
                "agg": {
                    "value": "response_time_ms",
                    "agg_type": "percentiles",
                    "percents": [50, 95, 99],
                },
            },
            {
                "aggregations": {
                    "time": {
                        "buckets": [
                            {"key": "uuid1", "time": {"value_as_string": "2024-02-09T12:00:00"}},
                            {"key": "uuid2", "time": {"value_as_string": "2024-02-09T13:00:00"}},
                        ]
                    },
                    "uuid": {
                        "buckets": [
                            {
                                "key": "uuid1",
                                "response_time_ms": {
                                    "values": {"50.0": 100.5, "95.0": 250.3, "99.0": 350.7}
                                }
                            },
                            {
                                "key": "uuid2",
                                "response_time_ms": {
                                    "values": {"50.0": 105.2, "95.0": 260.8, "99.0": 360.1}
                                }
                            },
                        ]
                    },
                }
            },
            [
                {
                    "uuid": "uuid1",
                    "timestamp": "2024-02-09T12:00:00",
                    "response_time_ms_percentiles": 250.3
                },
                {
                    "uuid": "uuid2",
                    "timestamp": "2024-02-09T13:00:00",
                    "response_time_ms_percentiles": 260.8
                },
            ],
        ),
        # Test percentile aggregation with custom target (99th percentile)
        (
            "matcher_instance",
            ["uuid1", "uuid2"],
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
            {
                "aggregations": {
                    "time": {
                        "buckets": [
                            {"key": "uuid1", "time": {"value_as_string": "2024-02-09T12:00:00"}},
                            {"key": "uuid2", "time": {"value_as_string": "2024-02-09T13:00:00"}},
                        ]
                    },
                    "uuid": {
                        "buckets": [
                            {
                                "key": "uuid1",
                                "response_time_ms": {
                                    "values": {"50.0": 100.5, "95.0": 250.3, "99.0": 350.7}
                                }
                            },
                            {
                                "key": "uuid2",
                                "response_time_ms": {
                                    "values": {"50.0": 105.2, "95.0": 260.8, "99.0": 360.1}
                                }
                            },
                        ]
                    },
                }
            },
            [
                {
                    "uuid": "uuid1",
                    "timestamp": "2024-02-09T12:00:00",
                    "response_time_ms_percentiles": 350.7
                },
                {
                    "uuid": "uuid2",
                    "timestamp": "2024-02-09T13:00:00",
                    "response_time_ms_percentiles": 360.1
                },
            ],
        ),
        # Test percentile aggregation with uuid_matcher_instance
        (
            "uuid_matcher_instance",
            ["uuid1", "uuid2"],
            {
                "name": "latency_p95",
                "metricName": "latency",
                "metric_of_interest": "value_ms",
                "agg": {
                    "value": "value_ms",
                    "agg_type": "percentiles",
                    "percents": [95, 99],
                    "target_percentile": 95,
                },
            },
            {
                "aggregations": {
                    "time": {
                        "buckets": [
                            {"key": "uuid1", "time": {"value_as_string": "2024-02-09T12:00:00"}},
                            {"key": "uuid2", "time": {"value_as_string": "2024-02-09T13:00:00"}},
                        ]
                    },
                    "uuid": {
                        "buckets": [
                            {
                                "key": "uuid1",
                                "value_ms": {"values": {"95.0": 150.2, "99.0": 200.5}}
                            },
                            {
                                "key": "uuid2",
                                "value_ms": {"values": {"95.0": 155.8, "99.0": 205.3}}
                            },
                        ]
                    },
                }
            },
            [
                {
                    "run_uuid": "uuid1",
                    "timestamp": "2024-02-09T12:00:00",
                    "value_ms_percentiles": 150.2
                },
                {
                    "run_uuid": "uuid2",
                    "timestamp": "2024-02-09T13:00:00",
                    "value_ms_percentiles": 155.8
                },
            ],
        ),
    ],
)
def test_percentile_agg_metric_query(request,
                                      fixture_name,
                                      test_uuids,
                                      test_metrics,
                                      data_dict,
                                      expected):
    """Test percentile aggregation queries."""
    matcher = request.getfixturevalue(fixture_name)
    matcher.query_index = lambda *args, **kwargs: Response(response=data_dict, search=data_dict)

    result = matcher.get_agg_metric_query(test_uuids, test_metrics)
    assert result == expected
