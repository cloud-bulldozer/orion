"""
Unit tests for orion/run_test.py

Focused on the Prow CI JSON file-writing behaviour fixed in PR #367:
  - file is written *after* window expansion using json.dumps (not str())
  - file is only written when output_format != JSON and PROW_JOB_ID is present
  - file is not written when there is no regression
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error
# pylint: disable = missing-class-docstring

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from orion.logger import SingletonLogger
import orion.constants as cnsts
from orion.run_test import analyze


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _init_logger():
    """Ensure the singleton logger exists for every test."""
    SingletonLogger(debug=logging.DEBUG, name="Orion")


SAMPLE_TEST = {
    "name": "test-workload",
    "metadata_index": "perf-scale-ci",
    "uuid_field": "uuid",
    "version_field": "ocpVersion",
}

BASE_KWARGS = {
    "metadata_index": None,
    "es_server": "https://es-server:9200",
    "output_format": cnsts.TEXT,
    "hunter_analyze": True,
    "anomaly_detection": False,
    "cmr": False,
    "lookback": "7d",
    "lookback_size": None,
    "since": None,
    "save_output_path": None,   # overridden per-test using tmp_path
    "sippy_pr_search": False,
    "display": [],
}

# Changepoint is at index 5 (not within CHANGEPOINT_BUFFER=5), so window expansion
# is NOT triggered for the basic positive tests.
SAMPLE_RESULT_DATA_JSON = [
    {"uuid": f"uuid-{i}", "ocpVersion": "4.14.0", "is_changepoint": False,
     "metrics": {"cpu_avg": {"value": 9.0, "percentage_change": 0.0}}}
    for i in range(5)
] + [
    {"uuid": "abc123", "ocpVersion": "4.15.0", "is_changepoint": True,
     "metrics": {"cpu_avg": {"value": 10.5, "percentage_change": 15.0}}}
]


def _make_mock_algorithm(result_data_json, *, text_flag=True, json_flag=True):
    """Return a mock algorithm whose output() mimics the real signature."""
    mock = MagicMock()

    def _output(fmt):
        if fmt == cnsts.JSON:
            return ("test-workload", json.dumps(result_data_json), json_flag)
        return ("test-workload", "formatted text output", text_flag)

    mock.output.side_effect = _output
    return mock


@pytest.fixture
def patched_analyze(tmp_path):
    """Patch all external I/O dependencies inside analyze() and yield helpers."""
    sample_df = pd.DataFrame(
        [{"uuid": f"uuid-{i}", "ocpVersion": "4.14.0", "cpu_avg": 9.0} for i in range(5)]
        + [{"uuid": "abc123", "ocpVersion": "4.15.0", "cpu_avg": 10.5}]
    )
    metrics_config = {"cpu_avg": {"metric_of_interest": True}}

    with (
        patch("orion.run_test.Matcher"),
        patch("orion.run_test.get_start_timestamp", return_value=""),
        patch("orion.run_test.Utils") as mock_utils_cls,
        patch("orion.run_test.AlgorithmFactory") as mock_factory_cls,
    ):
        mock_utils = MagicMock()
        mock_utils.process_test.return_value = (sample_df, metrics_config)
        mock_utils_cls.return_value = mock_utils

        mock_factory = MagicMock()
        mock_factory_cls.return_value = mock_factory

        yield {
            "tmp_path": tmp_path,
            "mock_factory": mock_factory,
            "mock_utils": mock_utils,
        }


def _kwargs(tmp_path, **overrides):
    """Build a kwargs dict with save_output_path rooted in tmp_path."""
    output_path = str(tmp_path / "output.txt")
    return {**BASE_KWARGS, "save_output_path": output_path, **overrides}


def _expected_json_file(tmp_path):
    """Return the path where analyze() should write the Prow JSON sidecar."""
    return tmp_path / "output_test-workload.json"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProwJsonFileWriting:
    def test_file_written_with_proper_json_format(self, patched_analyze, tmp_path):
        """When output_format != JSON and PROW_JOB_ID is set, the sidecar file
        must exist and contain valid, indented JSON — not a Python str() dump."""
        patched_analyze["mock_factory"].instantiate_algorithm.return_value = (
            _make_mock_algorithm(SAMPLE_RESULT_DATA_JSON)
        )

        with patch.dict(os.environ, {"PROW_JOB_ID": "12345"}):
            analyze(SAMPLE_TEST, _kwargs(tmp_path, output_format=cnsts.TEXT))

        json_file = _expected_json_file(tmp_path)
        assert json_file.exists(), "Prow JSON sidecar file was not created"
        content = json.loads(json_file.read_text())
        assert content == SAMPLE_RESULT_DATA_JSON

    def test_file_not_written_when_output_format_is_json(self, patched_analyze, tmp_path):
        """No sidecar file should be created when the requested output is already JSON."""
        patched_analyze["mock_factory"].instantiate_algorithm.return_value = (
            _make_mock_algorithm(SAMPLE_RESULT_DATA_JSON)
        )

        with patch.dict(os.environ, {"PROW_JOB_ID": "12345"}):
            analyze(SAMPLE_TEST, _kwargs(tmp_path, output_format=cnsts.JSON))

        assert not _expected_json_file(tmp_path).exists()

    def test_file_not_written_without_prow_job_id(self, patched_analyze, tmp_path):
        """No sidecar file when PROW_JOB_ID env var is absent."""
        patched_analyze["mock_factory"].instantiate_algorithm.return_value = (
            _make_mock_algorithm(SAMPLE_RESULT_DATA_JSON)
        )

        env = {k: v for k, v in os.environ.items() if k != "PROW_JOB_ID"}
        with patch.dict(os.environ, env, clear=True):
            analyze(SAMPLE_TEST, _kwargs(tmp_path, output_format=cnsts.TEXT))

        assert not _expected_json_file(tmp_path).exists()

    def test_file_not_written_when_prow_job_id_is_blank(self, patched_analyze, tmp_path):
        """A whitespace-only PROW_JOB_ID should be treated as absent."""
        patched_analyze["mock_factory"].instantiate_algorithm.return_value = (
            _make_mock_algorithm(SAMPLE_RESULT_DATA_JSON)
        )

        with patch.dict(os.environ, {"PROW_JOB_ID": "   "}):
            analyze(SAMPLE_TEST, _kwargs(tmp_path, output_format=cnsts.TEXT))

        assert not _expected_json_file(tmp_path).exists()

    def test_file_not_written_when_no_regression(self, patched_analyze, tmp_path):
        """No sidecar file when the algorithm reports no regression (test_flag=False),
        because the file-write block lives inside the 'if test_flag' branch."""
        patched_analyze["mock_factory"].instantiate_algorithm.return_value = (
            _make_mock_algorithm(SAMPLE_RESULT_DATA_JSON, text_flag=False, json_flag=False)
        )

        with patch.dict(os.environ, {"PROW_JOB_ID": "12345"}):
            analyze(SAMPLE_TEST, _kwargs(tmp_path, output_format=cnsts.TEXT))

        assert not _expected_json_file(tmp_path).exists()

    def test_file_content_reflects_post_expansion_data(self, patched_analyze, tmp_path):
        """The sidecar file must contain the *final* result_data_json, which may
        have been updated by the window-expansion logic after the initial analysis.

        The mock returns an early changepoint on the first JSON call, triggering
        expansion.  The expanded algorithm returns different data with no
        changepoint; we verify the written file holds the expanded data.
        """
        initial_data = [
            {"uuid": "abc123", "ocpVersion": "4.15", "is_changepoint": True,
             "metrics": {"cpu_avg": {"value": 10.5, "percentage_change": 20.0}}},
        ]
        expanded_data = [
            {"uuid": "abc123", "ocpVersion": "4.15", "is_changepoint": False,
             "metrics": {"cpu_avg": {"value": 10.5, "percentage_change": 0.0}}},
        ]

        initial_algorithm = _make_mock_algorithm(initial_data, text_flag=True, json_flag=True)
        expanded_algorithm = _make_mock_algorithm(expanded_data, text_flag=False, json_flag=False)

        patched_analyze["mock_factory"].instantiate_algorithm.side_effect = [
            initial_algorithm,
            expanded_algorithm,
        ]

        # Expanded process_test returns a bigger DataFrame (2 rows > 1 original)
        expanded_df = pd.DataFrame([
            {"uuid": "abc123", "ocpVersion": "4.14", "cpu_avg": 9.0},
            {"uuid": "abc123", "ocpVersion": "4.15", "cpu_avg": 10.5},
        ])
        metrics_config = {"cpu_avg": {"metric_of_interest": True}}
        patched_analyze["mock_utils"].process_test.side_effect = [
            (pd.DataFrame([{"uuid": "abc123", "ocpVersion": "4.15", "cpu_avg": 10.5}]),
             metrics_config),
            (expanded_df, metrics_config),
        ]

        with patch.dict(os.environ, {"PROW_JOB_ID": "12345"}):
            analyze(SAMPLE_TEST, _kwargs(tmp_path, output_format=cnsts.TEXT))

        json_file = _expected_json_file(tmp_path)
        assert json_file.exists(), "Prow JSON sidecar file was not created"
        content = json.loads(json_file.read_text())
        assert content == expanded_data, (
            "Sidecar file should reflect post-expansion result_data_json, not the initial one"
        )
