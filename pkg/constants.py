"""
pkg.constants

Module for storing constants across orion.
"""

import re

EDIVISIVE="EDivisive"
ISOLATION_FOREST="IsolationForest"
JSON="json"
TEXT="text"
JUNIT="junit"
CMR="cmr"
# Matches ISO 8601 datetime strings with nanosecond precision
NANO_SECONDS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T"
                        r"\d{2}:\d{2}:\d{2}\."
                        r"\d{9}Z$")
# Matches Unix epoch timestamps in seconds
EPOCH_TIMESTAMP_PATTERN = re.compile(r"^\d{10}$")
