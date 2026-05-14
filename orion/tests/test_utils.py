"""
Unit tests for orion/utils.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error
# pylint: disable = missing-class-docstring

import logging

import pandas as pd
import pytest

from orion.logger import SingletonLogger
from orion.utils import (
    Utils,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    """Ensure the singleton logger exists for every test."""
    SingletonLogger(debug=logging.DEBUG, name="Orion")


@pytest.fixture
def utils():
    return Utils()


@pytest.fixture
def utils_custom_fields():
    return Utils(uuid_field="run_uuid", version_field="cluster_version")


# ---------------------------------------------------------------------------
# standardize_timestamp
# ---------------------------------------------------------------------------

class TestStandardizeTimestamp:
    def test_none_returns_none(self, utils):
        assert utils.standardize_timestamp(None) is None

    def test_integer_epoch_seconds(self, utils):
        # 2024-01-01 00:00:00 UTC
        result = utils.standardize_timestamp(1704067200)
        assert result == "2024-01-01T00:00:00"

    def test_numeric_string_epoch_seconds(self, utils):
        result = utils.standardize_timestamp("1704067200")
        assert result == "2024-01-01T00:00:00"

    def test_iso_string(self, utils):
        result = utils.standardize_timestamp("2024-06-15T12:30:45Z")
        assert result == "2024-06-15T12:30:45"

    def test_iso_string_with_offset(self, utils):
        result = utils.standardize_timestamp("2024-06-15T12:30:45+00:00")
        assert result == "2024-06-15T12:30:45"

    def test_float_epoch_not_treated_as_seconds(self, utils):
        # BEHAVIOR GUARD: floats take the else branch in standardize_timestamp,
        # where pd.to_datetime interprets them as nanoseconds, NOT seconds.
        # A float like 1.7e9 (valid epoch seconds for 2024) gets interpreted
        # as ~1.7 seconds after 1970-01-01.
        #
        # If this test fails it means the float handling changed — callers
        # that rely on passing int/str for epoch-seconds may now silently
        # get wrong results from floats, or vice-versa. Either way, audit
        # all call sites before accepting the new behavior.
        ts = 1704067200.123  # 2024-01-01 as epoch seconds
        result = utils.standardize_timestamp(ts)
        assert result.startswith("1970-01-01"), (
            f"Float timestamp handling changed! Got {result} — expected 1970 "
            f"(float treated as nanoseconds). If this is intentional, update "
            f"this test and audit callers of standardize_timestamp."
        )

    def test_pandas_timestamp(self, utils):
        ts = pd.Timestamp("2024-03-15 08:00:00", tz="UTC")
        result = utils.standardize_timestamp(ts)
        assert result == "2024-03-15T08:00:00"
