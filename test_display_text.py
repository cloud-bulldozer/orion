#!/usr/bin/env python3
"""
Simple test to verify the --display feature is correctly implemented
"""

from orion.utils import generate_tabular_output


def test_display_feature():
    """Test that the display feature works as expected"""

    # Sample data with metadata field
    test_data = [
        {
            "uuid": "test-uuid-1",
            "timestamp": 1640995200,
            "buildUrl": "http://example.com/build1",
            "ocpVirt": "enabled",  # This is our metadata field
            "metrics": {
                "testMetric": {
                    "value": 100.5,
                    "percentage_change": 0,
                    "labels": ["test"]
                }
            }
        },
        {
            "uuid": "test-uuid-2",
            "timestamp": 1641081600,
            "buildUrl": "http://example.com/build2",
            "ocpVirt": "disabled",  # This is our metadata field
            "metrics": {
                "testMetric": {
                    "value": 120.8,
                    "percentage_change": 5.2,
                    "labels": ["test"]
                }
            }
        }
    ]

    print("Testing generate_tabular_output with display field...")

    # Test with display field
    output_with_display = generate_tabular_output(test_data, "testMetric", "uuid", "ocpVirt")

    print("Output with ocpVirt display field:")
    print(output_with_display)
    print()

    # Verify that the metadata field is included
    assert "ocpVirt" in output_with_display, "ocpVirt column should be present in output"
    assert "enabled" in output_with_display, "enabled value should be present in output"
    assert "disabled" in output_with_display, "disabled value should be present in output"

    print("✓ Display feature test passed!")
    print("✓ The --display option should now work correctly in Orion!")


if __name__ == "__main__":
    test_display_feature()