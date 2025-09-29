#!/usr/bin/env python3
"""
Test script for the new --display feature
"""

import json
from orion.utils import generate_tabular_output, json_to_junit


def test_generate_tabular_output_with_display():
    """Test that generate_tabular_output includes metadata field when display_field is provided"""

    # Sample data with metadata field
    test_data = [
        {
            "uuid": "test-uuid-1",
            "timestamp": 1640995200,  # 2022-01-01 00:00:00 UTC
            "buildUrl": "http://example.com/build1",
            "ocpVirt": "enabled",  # This is our metadata field
            "metrics": {
                "podReadyLatency": {
                    "value": 100.5,
                    "percentage_change": 0,
                    "labels": ["test"]
                }
            }
        },
        {
            "uuid": "test-uuid-2",
            "timestamp": 1641081600,  # 2022-01-02 00:00:00 UTC
            "buildUrl": "http://example.com/build2",
            "ocpVirt": "disabled",  # This is our metadata field
            "metrics": {
                "podReadyLatency": {
                    "value": 120.8,
                    "percentage_change": 5.2,
                    "labels": ["test"]
                }
            }
        }
    ]

    # Test without display field
    output_without = generate_tabular_output(test_data, "podReadyLatency", "uuid")
    print("=== Output WITHOUT display field ===")
    print(output_without)
    print()

    # Test with display field
    output_with = generate_tabular_output(test_data, "podReadyLatency", "uuid", "ocpVirt")
    print("=== Output WITH display field (ocpVirt) ===")
    print(output_with)
    print()

    # Verify that the metadata field is included
    assert "ocpVirt" in output_with, "ocpVirt column should be present in output"
    assert "enabled" in output_with, "enabled value should be present in output"
    assert "disabled" in output_with, "disabled value should be present in output"

    print("✓ generate_tabular_output test passed!")


def test_json_to_junit_with_display():
    """Test that json_to_junit includes metadata field when display_field is provided"""

    test_data = [
        {
            "uuid": "test-uuid-1",
            "timestamp": 1640995200,
            "buildUrl": "http://example.com/build1",
            "releaseStream": "4.12.1",  # This is our metadata field
            "metrics": {
                "podReadyLatency": {
                    "value": 100.5,
                    "percentage_change": 5.0,  # This will trigger a failure
                    "labels": ["test"]
                }
            }
        }
    ]

    metrics_config = {
        "podReadyLatency": {
            "labels": ["test"],
            "direction": 1
        }
    }

    # Test with display field
    junit_output = json_to_junit("test_case", test_data, metrics_config, "uuid", "releaseStream")
    print("=== JUnit output WITH display field (releaseStream) ===")
    print(junit_output[:500] + "..." if len(junit_output) > 500 else junit_output)
    print()

    # Verify that the metadata field is included in the JUnit output
    assert "releaseStream" in junit_output, "releaseStream column should be present in JUnit output"
    assert "4.12.1" in junit_output, "4.12.1 value should be present in JUnit output"

    print("✓ json_to_junit test passed!")


if __name__ == "__main__":
    print("Testing new --display feature functionality...\n")

    try:
        test_generate_tabular_output_with_display()
        test_json_to_junit_with_display()
        print("\n🎉 All tests passed! The --display feature is working correctly.")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()