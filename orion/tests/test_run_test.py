"""
Unit tests for run_test analyze behavior.
"""

import json
import logging
from types import SimpleNamespace

import pandas as pd

import orion.constants as cnsts
import orion.run_test as run_test
from orion.logger import SingletonLogger


class FakeAlgorithm:
    def __init__(self, test_name, json_payload, formatted_output, regression_flag):
        self.test_name = test_name
        self.json_payload = json_payload
        self.formatted_output = formatted_output
        self.regression_flag = regression_flag
        self.options = {}
        self.dataframe = pd.DataFrame()

    def output(self, output_format):
        if output_format == cnsts.JSON:
            return (
                self.test_name,
                json.dumps(self.json_payload, indent=2),
                self.regression_flag,
            )
        return self.test_name, self.formatted_output, self.regression_flag


def test_analyze_writes_sidecar_json_after_window_expansion(tmp_path, monkeypatch):
    SingletonLogger(debug=logging.INFO, name="Orion")

    original_df = pd.DataFrame(
        {
            "timestamp": [1, 2, 3],
            "uuid": ["uuid-1", "uuid-2", "uuid-3"],
            "ocpVersion": ["4.22.0-a", "4.22.0-b", "4.22.0-c"],
            "latency": [10.0, 20.0, 30.0],
        }
    )
    expanded_df = pd.DataFrame(
        {
            "timestamp": [1, 2, 3, 4, 5, 6],
            "uuid": ["uuid-1", "uuid-2", "uuid-3", "uuid-4", "uuid-5", "uuid-6"],
            "ocpVersion": [
                "4.22.0-a",
                "4.22.0-b",
                "4.22.0-c",
                "4.22.0-d",
                "4.22.0-e",
                "4.22.0-f",
            ],
            "latency": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        }
    )
    metrics_config = {"latency": {"direction": 1}}
    original_json = [
        {
            "timestamp": 1,
            "uuid": "uuid-1",
            "ocpVersion": "4.22.0-a",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 10.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
        {
            "timestamp": 2,
            "uuid": "uuid-2",
            "ocpVersion": "4.22.0-b",
            "is_changepoint": True,
            "metrics": {
                "latency": {
                    "value": 20.0,
                    "percentage_change": 100.0,
                    "labels": "",
                }
            },
        },
        {
            "timestamp": 3,
            "uuid": "uuid-3",
            "ocpVersion": "4.22.0-c",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 30.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
    ]
    expanded_json = [
        {
            "timestamp": 1,
            "uuid": "uuid-1",
            "ocpVersion": "4.22.0-a",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 10.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
        {
            "timestamp": 2,
            "uuid": "uuid-2",
            "ocpVersion": "4.22.0-b",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 20.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
        {
            "timestamp": 3,
            "uuid": "uuid-3",
            "ocpVersion": "4.22.0-c",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 30.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
        {
            "timestamp": 4,
            "uuid": "uuid-4",
            "ocpVersion": "4.22.0-d",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 40.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
        {
            "timestamp": 5,
            "uuid": "uuid-5",
            "ocpVersion": "4.22.0-e",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 50.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
        {
            "timestamp": 6,
            "uuid": "uuid-6",
            "ocpVersion": "4.22.0-f",
            "is_changepoint": False,
            "metrics": {
                "latency": {
                    "value": 60.0,
                    "percentage_change": 0,
                    "labels": "",
                }
            },
        },
    ]

    class FakeUtils:
        def __init__(self, *_args, **_kwargs):
            self.calls = 0

        def process_test(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return original_df, metrics_config
            return expanded_df, metrics_config

    original_algorithm = FakeAlgorithm(
        test_name="node-density",
        json_payload=original_json,
        formatted_output="original report",
        regression_flag=True,
    )
    expanded_algorithm = FakeAlgorithm(
        test_name="node-density",
        json_payload=expanded_json,
        formatted_output="expanded report",
        regression_flag=False,
    )

    class FakeAlgorithmFactory:
        def __init__(self):
            self.calls = 0

        def instantiate_algorithm(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return original_algorithm
            return expanded_algorithm

    monkeypatch.setattr(
        run_test,
        "Matcher",
        lambda **kwargs: SimpleNamespace(index=kwargs["index"]),
    )
    monkeypatch.setattr(run_test, "Utils", FakeUtils)
    monkeypatch.setattr(run_test, "AlgorithmFactory", FakeAlgorithmFactory)
    monkeypatch.setenv("PROW_JOB_ID", "12345")

    result = run_test.analyze(
        test={
            "name": "node-density",
            "metadata_index": "metadata-index",
            "version_field": "ocpVersion",
            "uuid_field": "uuid",
        },
        kwargs={
            "metadata_index": None,
            "es_server": "https://example.com",
            "sippy_pr_search": False,
            "since": "",
            "lookback": "",
            "hunter_analyze": True,
            "anomaly_detection": False,
            "cmr": False,
            "output_format": cnsts.TEXT,
            "save_output_path": str(tmp_path / "orion-output.txt"),
            "display": [],
            "viz": False,
        },
    )

    sidecar_path = tmp_path / "orion-output_node-density.json"

    assert result.output["node-density"] == "expanded report"
    assert result.regression_flag is False
    assert sidecar_path.is_file()
    assert json.loads(sidecar_path.read_text(encoding="utf-8")) == expanded_json
