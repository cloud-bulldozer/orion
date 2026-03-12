"""
Unit Test file for matcher telco-specific functionality
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error, duplicate-code
import pytest

# Import shared fixtures and helpers from test_matcher
from orion.tests.test_matcher import make_matcher_fixture, FakeHit


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
def test_dotDictFind_success(telco_matcher_instance, data, find_path, expected):
    """Test dotDictFind with valid paths that should succeed."""
    result = telco_matcher_instance.dotDictFind(data, find_path)
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
def test_dotDictFind_key_error(telco_matcher_instance, data, find_path):
    """Test dotDictFind with invalid paths that should raise KeyError."""
    with pytest.raises(KeyError):
        telco_matcher_instance.dotDictFind(data, find_path)


def test_dotDictFind_empty_dict(telco_matcher_instance):
    """Test dotDictFind with empty dictionary."""
    with pytest.raises(KeyError):
        telco_matcher_instance.dotDictFind({}, "any.key")


def test_dotDictFind_complex_nested_structure(telco_matcher_instance):
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

    assert telco_matcher_instance.dotDictFind(data,
        "tags.sw_version") == "4.18.17"
    assert telco_matcher_instance.dotDictFind(data,
        "tags.kernel_version") == "5.14.0-427.72.1.el9_4.x86_64+rt"
    assert telco_matcher_instance.dotDictFind(data,
        "metadata.ocpVersion") == "4.15.0-0.nightly-2024-01-15-022811"
    assert telco_matcher_instance.dotDictFind(data,
         "tags") == data["tags"]
    assert telco_matcher_instance.dotDictFind(data,
         "metadata") == data["metadata"]
