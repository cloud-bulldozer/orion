# pylint: disable=protected-access
"""Tests for Isolation Forest moving average excluding detected anomalies."""

import pandas as pd
from orion.algorithms.isolationforest.isolationForest import IsolationForestWeightedMean


def _make_test_config():
    return {
        "name": "test-anomaly",
        "uuid_field": "uuid",
        "version_field": "version",
    }


def _make_metrics_config():
    return {
        "rps": {
            "direction": -1,
            "labels": [],
            "threshold": 0,
            "correlation": "",
            "context": None,
        },
    }


def test_single_anomaly_does_not_poison_window_for_next_run():
    df = pd.DataFrame({
        "uuid": [f"uuid-{i}" for i in range(10)],
        "version": [f"v{i}" for i in range(10)],
        "timestamp": list(range(1700000000, 1700000000 + 10 * 100000, 100000)),
        "buildUrl": [f"http://build{i}" for i in range(10)],
        "rps": [690.0, 710.0, 700.0, 720.0, 710.0, 705.0,
                0.0,
                500.0,
                700.0, 710.0],
    })

    algorithm = IsolationForestWeightedMean(
        dataframe=df,
        test=_make_test_config(),
        options={"ackMap": None, "anomaly_window": 3, "min_anomaly_percent": 10},
        metrics_config=_make_metrics_config(),
    )

    _, change_points = algorithm._analyze()

    flagged_indices = {cp.index for cp in change_points.get("rps", [])}

    assert 7 in flagged_indices, (
        "Run 8 (index 7, rps=500) should be detected as a regression; "
        "the anomalous run 7 (rps=0) must not drag down the moving average"
    )
