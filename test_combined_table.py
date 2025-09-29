#!/usr/bin/env python3
"""
Test the combined table functionality for the --display feature
"""

import json
from orion.algorithms.algorithm import Algorithm


class MockAlgorithm(Algorithm):
    """Mock algorithm for testing the combined table functionality"""

    def _analyze(self):
        """Mock implementation - not used in this test"""
        return {}, {}

    def test_combined_table(self, data_json, display_field):
        """Test method to access the private method"""
        return self._generate_combined_table_with_display(data_json, display_field)


def test_combined_table_functionality():
    """Test that the combined table includes all metrics and the display field"""

    # Sample data with multiple metrics and display field
    test_data = [
        {
            "uuid": "test-uuid-1",
            "timestamp": 1640995200,  # 2022-01-01 00:00:00 UTC
            "buildUrl": "http://example.com/build1",
            "ocpVersion": "4.19.0",
            "ocpVirtVersion": "4.19.9-10",  # This is our display field
            "metrics": {
                "vmiReadyLatency_P99": {"value": 134895, "percentage_change": 0},
                "apiserverCPU_avg": {"value": 36.1569, "percentage_change": 0},
                "multusCPU_avg": {"value": 1.01203, "percentage_change": 0}
            }
        },
        {
            "uuid": "test-uuid-2",
            "timestamp": 1641081600,  # 2022-01-02 00:00:00 UTC
            "buildUrl": "http://example.com/build2",
            "ocpVersion": "4.19.0",
            "ocpVirtVersion": "4.19.9-12",  # This is our display field
            "metrics": {
                "vmiReadyLatency_P99": {"value": 110728, "percentage_change": 5.2},
                "apiserverCPU_avg": {"value": 32.0316, "percentage_change": 0},
                "multusCPU_avg": {"value": 1.01451, "percentage_change": 0}
            }
        }
    ]

    # Mock metrics config
    metrics_config = {
        "vmiReadyLatency_P99": {"labels": ["test"]},
        "apiserverCPU_avg": {"labels": ["test"]},
        "multusCPU_avg": {"labels": ["test"]}
    }

    # Create mock algorithm instance
    algorithm = MockAlgorithm(
        matcher=None,
        dataframe=None,
        test={"name": "test"},
        options={"display": "ocpVirtVersion"},
        metrics_config=metrics_config,
        version_field="ocpVersion",
        uuid_field="uuid"
    )

    print("Testing combined table with display field...")

    # Test the combined table
    combined_table = algorithm.test_combined_table(test_data, "ocpVirtVersion")

    print("Combined table output:")
    print(combined_table)
    print()

    # Verify the output contains expected elements
    assert "ocpVirtVersion" in combined_table, "Display field should be in the table header"
    assert "4.19.9-10" in combined_table, "Display field value should be in the table"
    assert "4.19.9-12" in combined_table, "Display field value should be in the table"
    assert "vmiReadyLatency_P99" in combined_table, "First metric should be in the table"
    assert "apiserverCPU_avg" in combined_table, "Second metric should be in the table"
    assert "multusCPU_avg" in combined_table, "Third metric should be in the table"
    assert "134895" in combined_table, "First metric value should be in the table"
    assert "36.1569" in combined_table, "Second metric value should be in the table"

    print("✓ Combined table test passed!")
    print("✓ The --display option should now show a single table with all metrics plus the display field!")


if __name__ == "__main__":
    test_combined_table_functionality()