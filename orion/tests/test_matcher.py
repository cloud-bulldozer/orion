"""
Unit Test file for fmatch.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error, duplicate-code
import os
from unittest.mock import patch
import datetime
import logging

from opensearch_dsl import Search
from opensearch_dsl.response import Response
import pytest
import pandas as pd

# pylint: disable = import-error
from orion.matcher import Matcher
from orion.logger import SingletonLogger


class FakeHit:
    """
    A mock hit object simulating Elasticsearch/OpenSearch search results.

    This class is used in tests to mimic the structure of a document hit
    returned by the search index. It provides access to the underlying
    document via `to_dict` and dictionary-like access via `__getitem__`.
    """
    def __init__(self, doc):
        self._doc = doc

    def to_dict(self):
        """Return the document wrapped in a '_source' key, like a real hit."""
        return {"_source": self._doc["_source"]}

    def __getitem__(self, key):
        """Allow dictionary-like access to the underlying document."""
        return self._doc[key]


def make_matcher_fixture(index, uuid_field="uuid", version_field=None):
    """Factory for building matcher fixtures with different uuid fields."""
    sample_output = {
        "hits": {
            "hits": [
                {"_source": {uuid_field: "uuid1", "field1": "value1"}},
                {"_source": {uuid_field: "uuid2", "field1": "value2"}},
            ]
        }
    }
    with patch("orion.matcher.OpenSearch") as mock_es:
        mock_es_instance = mock_es.return_value
        mock_es_instance.search.return_value = Response(
            search=Search(), response=sample_output
        )
        # Ensure logger initialized
        SingletonLogger(debug=logging.INFO, name="Orion")

        kwargs = {"index": index}
        if uuid_field != "uuid":  # only override when it's custom
            kwargs["uuid_field"] = uuid_field
        if version_field:
            kwargs["version_field"] = version_field

        return Matcher(**kwargs)


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


def test_get_metadata_by_uuid_found(matcher_instance, monkeypatch):
    uuid = "test_uuid"
    fake_hit = FakeHit({"_source": {"uuid": "uuid1", "field1": "value1"}})

    monkeypatch.setattr(matcher_instance, "query_index", lambda *a, **k: [fake_hit])

    result = [hit.to_dict()["_source"] for hit in matcher_instance.query_index(uuid)]
    expected = [{"uuid": "uuid1", "field1": "value1"}]
    assert result == expected


@pytest.mark.parametrize("fixture_name", ["matcher_instance", "uuid_matcher_instance"])
def test_query_index(request, fixture_name, monkeypatch):
    instance = request.getfixturevalue(fixture_name)

    fake_hits = [
        FakeHit({"_source": {"run_uuid": "uuid1", "field1": "value1"}}),
        FakeHit({"_source": {"run_uuid": "uuid2", "field1": "value2"}}),
    ]

    monkeypatch.setattr(instance, "query_index", lambda *a, **k: fake_hits)

    hits = instance.query_index(None)
    result = [hit.to_dict()["_source"] for hit in hits]
    expected = [
        {"run_uuid": "uuid1", "field1": "value1"},
        {"run_uuid": "uuid2", "field1": "value2"},
    ]

    assert result == expected


@pytest.mark.parametrize(
    "sample_hits,metadata,lookback_date,lookback_size,expected",
    [
        # Plain metadata match
        (
            [
                {"_source": {"uuid": "uuid1", "buildUrl": "buildUrl1", "ocpVersion": "4.15"}},
                {"_source": {"uuid": "uuid2", "buildUrl": "buildUrl1", "ocpVersion": "4.15"}},
            ],
            {"field1": "value1", "ocpVersion": "4.15"},
            None,
            None,
            [
                {"uuid": "uuid1", "buildUrl": "buildUrl1", "ocpVersion": "4.15"},
                {"uuid": "uuid2", "buildUrl": "buildUrl1", "ocpVersion": "4.15"},
            ],
        ),
        # Lookback date filter
        (
            [
                {
                    "_source": {
                        "uuid": "uuid1",
                        "buildUrl": "buildUrl1",
                        "ocpVersion": "4.15",
                        "timestamp": "2024-07-10T13:46:24Z",
                    }
                },
                {
                    "_source": {
                        "uuid": "uuid2",
                        "buildUrl": "buildUrl1",
                        "ocpVersion": "4.15",
                        "timestamp": "2024-07-08T13:46:24Z",
                    }
                },
            ],
            {"field1": "value1", "ocpVersion": "4.15"},
            datetime.datetime.strptime("2024-07-07T13:46:24Z", "%Y-%m-%dT%H:%M:%SZ"),
            None,
            [
                {"uuid": "uuid1", "buildUrl": "buildUrl1", "ocpVersion": "4.15"},
                {"uuid": "uuid2", "buildUrl": "buildUrl1", "ocpVersion": "4.15"},
            ],
        ),
        # Lookback date + size limit
        (
            [
                {
                    "_source": {
                        "uuid": "uuid1",
                        "buildUrl": "buildUrl1",
                        "ocpVersion": "4.15",
                        "timestamp": "2024-07-10T13:46:24Z",
                    }
                },
                {
                    "_source": {
                        "uuid": "uuid2",
                        "buildUrl": "buildUrl1",
                        "ocpVersion": "4.15",
                        "timestamp": "2024-07-08T13:46:24Z",
                    }
                },
            ],
            {"field1": "value1", "ocpVersion": "4.15"},
            datetime.datetime.strptime("2024-07-07T13:46:24Z", "%Y-%m-%dT%H:%M:%SZ"),
            2,
            [
                {"uuid": "uuid1", "buildUrl": "buildUrl1", "ocpVersion": "4.15"},
                {"uuid": "uuid2", "buildUrl": "buildUrl1", "ocpVersion": "4.15"},
            ],
        ),
    ],
)
def test_get_uuid_by_metadata_variants(matcher_instance,
                                       monkeypatch,
                                       sample_hits,
                                       metadata,
                                       lookback_date,
                                       lookback_size,
                                       expected):
    fake_hits = [FakeHit(doc) for doc in sample_hits]
    monkeypatch.setattr(matcher_instance, "query_index", lambda *a, **k: fake_hits)

    result = matcher_instance.get_uuid_by_metadata(
        metadata=metadata,
        lookback_date=lookback_date,
        lookback_size=lookback_size,
    )
    assert result == expected


def test_match_kube_burner(matcher_instance, monkeypatch):
    sample_hits = [
        {"_source": {"uuid": "uuid1", "field1": "value1"}},
        {"_source": {"uuid": "uuid2", "field1": "value2"}},
    ]
    fake_hits = [FakeHit(doc) for doc in sample_hits]
    monkeypatch.setattr(matcher_instance, "query_index", lambda *a, **k: fake_hits)
    result = matcher_instance.match_kube_burner(["uuid1"])
    assert result == [
        {"uuid": "uuid1", "field1": "value1"},
        {"uuid": "uuid2", "field1": "value2"},
    ]


def test_filter_runs(matcher_instance, monkeypatch):
    sample_hits = [
        {
            "timestamp": "2024-01-15T20:00:46.307453873Z",
            "endTimestamp": "2024-01-15T20:30:57.853708171Z",
            "elapsedTime": 1812,
            "uuid": "90189fbf-7181-4129-8ca5-3cc8d656b595",
            "metricName": "jobSummary",
            "jobConfig": {
                "jobIterations": 216,
                "name": "cluster-density-v2",
                "jobType": "create",
                "qps": 20,
                "burst": 20,
                "namespace": "cluster-density-v2",
                "maxWaitTimeout": 14400000000000,
                "waitForDeletion": True,
                "waitWhenFinished": True,
                "cleanup": True,
                "namespacedIterations": True,
                "iterationsPerNamespace": 1,
                "verifyObjects": True,
                "errorOnVerify": True,
                "preLoadImages": True,
                "preLoadPeriod": 15000000000,
                "churn": True,
                "churnPercent": 10,
                "churnDuration": 1200000000000,
                "churnDelay": 120000000000,
            },
            "metadata": {
                "k8sVersion": "v1.28.5+c84a6b8",
                "ocpMajorVersion": "4.15",
                "ocpVersion": "4.15.0-0.nightly-2024-01-15-022811",
                "platform": "AWS",
                "sdnType": "OVNKubernetes",
                "totalNodes": 30,
            },
            "version": "1.7.12@f0b89ccdbeb2a7d65512f5970d5a25a82ec386b2",
        },
        {
            "timestamp": "2024-01-15T20:32:11.681417765Z",
            "endTimestamp": "2024-01-15T20:37:24.591361376Z",
            "elapsedTime": 313,
            "uuid": "90189fbf-7181-4129-8ca5-3cc8d656b595",
            "metricName": "jobSummary",
            "jobConfig": {"name": "garbage-collection"},
            "metadata": {
                "k8sVersion": "v1.28.5+c84a6b8",
                "ocpMajorVersion": "4.15",
                "ocpVersion": "4.15.0-0.nightly-2024-01-15-022811",
                "platform": "AWS",
                "sdnType": "OVNKubernetes",
                "totalNodes": 30,
            },
            "version": "1.7.12@f0b89ccdbeb2a7d65512f5970d5a25a82ec386b2",
        },
    ]
    fake_hits = [FakeHit(doc) for doc in sample_hits]
    monkeypatch.setattr(matcher_instance, "query_index", lambda *a, **k: fake_hits)
    result = matcher_instance.filter_runs(sample_hits, sample_hits)
    expected = ["90189fbf-7181-4129-8ca5-3cc8d656b595"]
    assert result == expected


@pytest.mark.parametrize(
    "fixture_name,test_uuid,test_uuids,test_metrics,fake_hits,expected",
    [
        # matcher_instance case
        (
            "matcher_instance",
            "uuid1",
            ["uuid1", "uuid2"],
            {
                "name": "podReadyLatency",
                "metricName": "podLatencyQuantilesMeasurement",
                "quantileName": "Ready",
                "metric_of_interest": "P99",
                "not": {"jobConfig.name": "garbage-collection"},
            },
            [
                FakeHit({"_source": {"uuid": "uuid1", "field1": "value1"}}),
                FakeHit({"_source": {"uuid": "uuid2", "field1": "value2"}}),
            ],
            [
                {"uuid": "uuid1", "field1": "value1"},
                {"uuid": "uuid2", "field1": "value2"},
            ],
        ),
        # uuid_matcher_instance case
        (
            "uuid_matcher_instance",
            "uuid1",
            ["uuid1", "uuid2"],
            {
                "metricName": "nodeCPUSeconds-Infra",
                "mode": "iowait",
            },
            [
                FakeHit({"_source": {"run_uuid": "uuid1", "field1": "value1"}}),
                FakeHit({"_source": {"run_uuid": "uuid2", "field1": "value2"}}),
            ],
            [
                {"run_uuid": "uuid1", "field1": "value1"},
                {"run_uuid": "uuid2", "field1": "value2"},
            ],
        ),
    ],
)
def test_get_results_variants(request,
                              monkeypatch,
                              fixture_name,
                              test_uuid,
                              test_uuids,
                              test_metrics,
                              fake_hits,
                              expected):
    matcher = request.getfixturevalue(fixture_name)
    monkeypatch.setattr(matcher, "query_index", lambda *a, **k: fake_hits)

    result = matcher.get_results(test_uuid, test_uuids, test_metrics)
    assert result == expected


@pytest.mark.parametrize(
    "fixture_name,test_uuid,test_uuids,exists_fields,\
    timestamp_field,test_metrics,fake_hits,expected",
    [
        # withCustom timestamp field
        (
            "matcher_instance",
            "uuid1",
            ["uuid1", "uuid2"],
            [],
            "happenedAt",
            {
                "name": "podReadyLatency",
                "metricName": "podLatencyQuantilesMeasurement",
                "quantileName": "Ready",
                "metric_of_interest": "P99",
                "not": {"jobConfig.name": "garbage-collection"},
            },
            [
                FakeHit({"_source": {"uuid": "uuid1", "field1": "value1",
                        "happenedAt": "2024-02-09T12:00:00"}}),
                FakeHit({"_source": {"uuid": "uuid2", "field1": "value2",
                        "happenedAt": "2024-02-09T13:00:00"}}),
            ],
            [
                {"uuid": "uuid1", "field1": "value1", "happenedAt": "2024-02-09T12:00:00"},
                {"uuid": "uuid2", "field1": "value2", "happenedAt": "2024-02-09T13:00:00"},
            ],
        ),
        # with exists fields
        (
            "matcher_instance",
            "uuid1",
            ["uuid1", "uuid2"],
            ["buildUrl"],
            "",
            {
                "metricName": "nodeCPUSeconds-Infra",
                "mode": "iowait",
            },
            [
                FakeHit({"_source": {"run_uuid": "uuid1", "field1": "value1",
                        "buildUrl": "https://build-url-1"}}),
                FakeHit({"_source": {"run_uuid": "uuid2", "field1": "value2",
                        "buildUrl": "https://build-url-2"}}),
            ],
            [
                {"run_uuid": "uuid1", "field1": "value1", "buildUrl": "https://build-url-1"},
                {"run_uuid": "uuid2", "field1": "value2", "buildUrl": "https://build-url-2"},
            ],
        ),
        # with both fields
        (
            "matcher_instance",
            "uuid1",
            ["uuid1", "uuid2"],
            ["buildUrl"],
            "happenedAt",
            {
                "metricName": "nodeCPUSeconds-Infra",
                "mode": "iowait",
            },
            [
                FakeHit({"_source": {"run_uuid": "uuid1", "field1": "value1",
                        "buildUrl": "https://build-url-1", "happenedAt": "2024-02-09T12:00:00"}}),
                FakeHit({"_source": {"run_uuid": "uuid2", "field1": "value2",
                        "buildUrl": "https://build-url-2", "happenedAt": "2024-02-09T13:00:00"}}),
            ],
            [
                {"run_uuid": "uuid1", "field1": "value1",
                 "buildUrl": "https://build-url-1", "happenedAt": "2024-02-09T12:00:00"},
                {"run_uuid": "uuid2", "field1": "value2",
                 "buildUrl": "https://build-url-2", "happenedAt": "2024-02-09T13:00:00"},
            ],
        ),
    ],
)
def test_get_results_with_exists_fields_and_timestamp_field(request,
                              monkeypatch,
                              fixture_name,
                              test_uuid,
                              test_uuids,
                              exists_fields,
                              timestamp_field,
                              test_metrics,
                              fake_hits,
                              expected):
    matcher = request.getfixturevalue(fixture_name)
    monkeypatch.setattr(matcher, "query_index", lambda *a, **k: fake_hits)

    result = matcher.get_results(test_uuid, test_uuids, test_metrics,
                                exists_fields, timestamp_field)
    assert result == expected


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
    "test_type",
    ["convert_to_df", "save_results"]
)
def test_data_operations(matcher_instance, tmp_path, test_type):
    mock_data = [
        {
            "uuid": "90189fbf-7181-4129-8ca5-3cc8d656b595",
            "timestamp": "2024-01-15T20:19:04.941Z",
            "cpu_avg": 10.818089329872935,
        }
    ]
    columns = ["uuid", "timestamp", "cpu_avg"]

    if test_type == "convert_to_df":
        expected_df = pd.json_normalize(mock_data).sort_values(by=["timestamp"])
        result_df = matcher_instance.convert_to_df(mock_data, columns=columns)
        assert result_df.equals(expected_df)

    elif test_type == "save_results":
        mock_df = pd.json_normalize(mock_data)
        csv_file = tmp_path / "test_output.csv"
        matcher_instance.save_results(mock_df, csv_file_path=str(csv_file), columns=columns)
        assert os.path.isfile(csv_file)


# Telco-specific tests for long_int integer timestamps and nested tag structure
@pytest.fixture
def telco_matcher_instance():
    """Create a matcher for telco CPU utilization data."""
    return make_matcher_fixture(
        index="svc_telco_cpu_util",
        uuid_field="uuid",
        version_field="tags.sw_version"
    )


@pytest.mark.parametrize(
    "test_uuids,test_metrics,fake_hits,expected_tags",
    [
        # Telco data with long_int integer timestamps and nested tags
        (
            ["2ef518fe-64de-46c9-a571-efbf7cc7a5a0", "32007076-22e4-4500-8d41-d1779d9ece65"],
            {"component": "infra_pods"},
            [
                FakeHit({
                    "_source": {
                        "resource_type": "mem",
                        "component": "infra_pods",
                        "test_phase": "steadyworkload",
                        "result_type": "avg",
                        "value": 2.52936192E8,
                        "tags": {
                            "pipeline": "ci",
                            "rc": "0",
                            "cluster": "cnfdf35",
                            "cpu_type": "Intel(R) Xeon(R) Gold 6330N CPU @ 2.20GHz",
                            "hyperthread": "2",
                            "kernel_realtime": "true",
                            "kernel_version": "5.14.0-427.72.1.el9_4.x86_64+rt",
                            "power_mode": "performance",
                            "sw_version": "4.18.17",
                            "duration": "1m",
                            "baseline": "false",
                            "namespace": "openshift-sriov-network-operator",
                            "pod": "sriov-network-config-daemon-"
                        },
                        "timestamp": 1750007825,
                        "uuid": "2ef518fe-64de-46c9-a571-efbf7cc7a5a0"
                    }
                }),
                FakeHit({
                    "_source": {
                        "resource_type": "cpu",
                        "component": "infra_pods",
                        "test_phase": "steadyworkload",
                        "result_type": "max",
                        "value": 0.7213862,
                        "tags": {
                            "pipeline": "ci",
                            "rc": "0",
                            "cluster": "ci-op-2r4mgm0g",
                            "cpu_type": "Intel(R) Xeon(R) Gold 6433N",
                            "hyperthread": "2",
                            "kernel_realtime": "true",
                            "kernel_version": "5.14.0-570.52.1.el9_6.x86_64+rt",
                            "power_mode": "performance",
                            "sw_version": "4.20.0-0.nightly-2025-10-13-053645",
                            "duration": "1h",
                            "baseline": "false"
                        },
                        "timestamp": 1760356258,
                        "uuid": "32007076-22e4-4500-8d41-d1779d9ece65"
                    }
                }),
            ],
            {
                "sw_version": "4.18.17",
                "kernel_version": "5.14.0-427.72.1.el9_4.x86_64+rt",
                "namespace": "openshift-sriov-network-operator",
                "pod": "sriov-network-config-daemon-"
            },
        ),
    ],
)
def test_telco_data_with_long_int_timestamps_and_nested_tags(
    telco_matcher_instance,
    monkeypatch,
    test_uuids,
    test_metrics,
    fake_hits,
    expected_tags
):
    """Test telco data with long_int integer timestamps and nested tags structure."""
    monkeypatch.setattr(telco_matcher_instance, "query_index", lambda *a, **k: fake_hits)
    result = telco_matcher_instance.get_results("", test_uuids, test_metrics)

    # Verify long_int integer timestamps
    assert len(result) == 2
    assert all("timestamp" in doc for doc in result)
    assert all(isinstance(doc["timestamp"], int) for doc in result)
    assert result[0]["timestamp"] == 1750007825
    assert result[1]["timestamp"] == 1760356258

    # Verify nested tags structure
    for field, expected_value in expected_tags.items():
        assert result[0]["tags"][field] == expected_value


@pytest.mark.parametrize(
    "data,find_path,expected",
    [
        # Simple single-level key access
        (
            {"key": "value"},
            "key",
            "value"
        ),
        # Multi-level nested dictionary access
        (
            {"level1": {"level2": {"level3": "deep_value"}}},
            "level1.level2.level3",
            "deep_value"
        ),
        # Path ending in a non-dict value (string)
        (
            {"tags": {"sw_version": "4.18.17"}},
            "tags.sw_version",
            "4.18.17"
        ),
        # Path ending in a non-dict value (number)
        (
            {"metadata": {"count": 42}},
            "metadata.count",
            42
        ),
        # Path ending in a non-dict value (list)
        (
            {"data": {"items": [1, 2, 3]}},
            "data.items",
            [1, 2, 3]
        ),
        # Path ending in a dict (should return the dict)
        (
            {"level1": {"level2": {"nested": "value"}}},
            "level1.level2",
            {"nested": "value"}
        ),
        # Two-level nested access
        (
            {"tags": {"sw_version": "4.20.0", "kernel_version": "5.14.0"}},
            "tags.sw_version",
            "4.20.0"
        ),
        # Path with single character keys
        (
            {"a": {"b": {"c": "abc"}}},
            "a.b.c",
            "abc"
        ),
        # Path with numeric string keys
        (
            {"1": {"2": {"3": "numeric"}}},
            "1.2.3",
            "numeric"
        ),
        # Path ending at root level dict
        (
            {"root": {"nested": "value"}},
            "root",
            {"nested": "value"}
        ),
    ],
)
def test_dotDictFind_success(matcher_instance, data, find_path, expected):
    """Test dotDictFind with valid paths that should succeed."""
    result = matcher_instance.dotDictFind(data, find_path)
    assert result == expected


@pytest.mark.parametrize(
    "data,find_path",
    [
        # Missing key at root level
        (
            {"key": "value"},
            "missing_key"
        ),
        # Missing key at nested level
        (
            {"level1": {"level2": "value"}},
            "level1.missing_key"
        ),
        # Missing key in deep nested structure
        (
            {"level1": {"level2": {"level3": "value"}}},
            "level1.level2.missing_key"
        ),
        # Empty path
        (
            {"key": "value"},
            ""
        ),
        # Path with only dots
        (
            {"key": "value"},
            "..."
        ),
    ],
)
def test_dotDictFind_key_error(matcher_instance, data, find_path):
    """Test dotDictFind with invalid paths that should raise KeyError."""
    with pytest.raises(KeyError):
        matcher_instance.dotDictFind(data, find_path)


def test_dotDictFind_empty_dict(matcher_instance):
    """Test dotDictFind with empty dictionary."""
    with pytest.raises(KeyError):
        matcher_instance.dotDictFind({}, "any.key")


def test_dotDictFind_complex_nested_structure(matcher_instance):
    """Test dotDictFind with complex nested structure similar to telco data."""
    data = {
        "tags": {
            "pipeline": "ci",
            "rc": "0",
            "cluster": "cnfdf35",
            "cpu_type": "Intel(R) Xeon(R) Gold 6330N CPU @ 2.20GHz",
            "sw_version": "4.18.17",
            "kernel_version": "5.14.0-427.72.1.el9_4.x86_64+rt",
            "power_mode": "performance",
            "namespace": "openshift-sriov-network-operator",
            "pod": "sriov-network-config-daemon-"
        },
        "metadata": {
            "ocpVersion": "4.15.0-0.nightly-2024-01-15-022811",
            "platform": "AWS"
        }
    }

    assert matcher_instance.dotDictFind(data,
        "tags.sw_version") == "4.18.17"
    assert matcher_instance.dotDictFind(data,
        "tags.kernel_version") == "5.14.0-427.72.1.el9_4.x86_64+rt"
    assert matcher_instance.dotDictFind(data,
        "metadata.ocpVersion") == "4.15.0-0.nightly-2024-01-15-022811"
    assert matcher_instance.dotDictFind(data,
         "tags") == data["tags"]
    assert matcher_instance.dotDictFind(data,
         "metadata") == data["metadata"]
