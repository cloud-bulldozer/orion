"""
Unit tests for batched metric dispatch in orion/utils.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error
# pylint: disable = missing-class-docstring
# pylint: disable = protected-access

import copy
import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from orion.logger import SingletonLogger
from orion.utils import Utils


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


def _make_match_mock():
    """Create a MagicMock that behaves like Matcher."""
    match = MagicMock()
    match.uuid_field = "uuid"

    def _convert_to_df(data, columns=None, timestamp_field="timestamp"):
        df = pd.json_normalize(data)
        df = df.sort_values(by=[timestamp_field])
        if columns is not None:
            df = pd.DataFrame(df, columns=columns)
        return df

    match.convert_to_df.side_effect = _convert_to_df
    return match


@pytest.fixture
def match_mock():
    return _make_match_mock()


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

def _agg_metric(name, metric_of_interest="cpu", agg_type="avg"):
    """Return a metric config dict with agg key."""
    return {
        "name": name,
        "metricName": "containerCPU",
        "metric_of_interest": metric_of_interest,
        "labels": ["ns=kube-system"],
        "direction": 1,
        "threshold": 10,
        "correlation": "",
        "context": 5,
        "agg": {"value": metric_of_interest, "agg_type": agg_type},
    }


def _std_metric(name, metric_of_interest="value"):
    """Return a standard metric config dict (no agg)."""
    return {
        "name": name,
        "metricName": "podLatency",
        "metric_of_interest": metric_of_interest,
        "labels": ["ns=default"],
        "direction": -1,
        "threshold": 5,
        "correlation": "corr",
        "context": 3,
    }


def _agg_batch_data(metric_of_interest="cpu", agg_type="avg"):
    """Return sample batch agg result list (one row per UUID)."""
    col = f"{metric_of_interest}_{agg_type}"
    return [
        {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z", col: 0.5},
        {"uuid": "u2", "timestamp": "2024-01-02T00:00:00Z", col: 0.7},
    ]


def _std_batch_data(metric_of_interest="value"):
    """Return sample batch standard result list (one row per UUID)."""
    return [
        {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z", metric_of_interest: 100},
        {"uuid": "u2", "timestamp": "2024-01-02T00:00:00Z", metric_of_interest: 200},
    ]


UUIDS = ["u1", "u2"]


# ---------------------------------------------------------------------------
# Tests: aggregation metrics dispatched via batch
# ---------------------------------------------------------------------------

class TestAggBatchDispatch:

    def test_single_agg_metric_uses_batch(self, utils, match_mock):
        metric = _agg_metric("apiserverCPU")
        metrics = [copy.deepcopy(metric)]

        match_mock.get_agg_metrics_batch.return_value = {
            "apiserverCPU": _agg_batch_data(),
        }

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        match_mock.get_agg_metrics_batch.assert_called_once()
        match_mock.get_agg_metric_query.assert_not_called()
        assert len(df_list) == 1
        assert "apiserverCPU_avg" in config

    def test_multiple_agg_metrics_single_batch_call(self, utils, match_mock):
        m1 = _agg_metric("cpuMetric1")
        m2 = _agg_metric("cpuMetric2", metric_of_interest="mem", agg_type="sum")
        metrics = [copy.deepcopy(m1), copy.deepcopy(m2)]

        match_mock.get_agg_metrics_batch.return_value = {
            "cpuMetric1": _agg_batch_data(),
            "cpuMetric2": _agg_batch_data(metric_of_interest="mem", agg_type="sum"),
        }

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        # Only one batch call for both agg metrics
        assert match_mock.get_agg_metrics_batch.call_count == 1
        assert len(df_list) == 2
        assert "cpuMetric1_avg" in config
        assert "cpuMetric2_sum" in config


# ---------------------------------------------------------------------------
# Tests: standard metrics dispatched via batch
# ---------------------------------------------------------------------------

class TestStdBatchDispatch:

    def test_single_std_metric_uses_batch(self, utils, match_mock):
        metric = _std_metric("podLatencyMetric")
        metrics = [copy.deepcopy(metric)]

        match_mock.get_results_batch.return_value = {
            "podLatencyMetric": _std_batch_data(),
        }

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        match_mock.get_results_batch.assert_called_once()
        match_mock.get_results.assert_not_called()
        assert len(df_list) == 1
        assert "podLatencyMetric_value" in config

    def test_multiple_std_metrics_single_batch_call(self, utils, match_mock):
        m1 = _std_metric("latency1")
        m2 = _std_metric("latency2", metric_of_interest="ms")
        metrics = [copy.deepcopy(m1), copy.deepcopy(m2)]

        match_mock.get_results_batch.return_value = {
            "latency1": _std_batch_data(),
            "latency2": _std_batch_data(metric_of_interest="ms"),
        }

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert match_mock.get_results_batch.call_count == 1
        assert len(df_list) == 2
        assert "latency1_value" in config
        assert "latency2_ms" in config


# ---------------------------------------------------------------------------
# Tests: fallback to single-query methods
# ---------------------------------------------------------------------------

class TestBatchFallback:

    def test_agg_batch_failure_falls_back(self, utils, match_mock):
        metric = _agg_metric("cpuFallback")
        metrics = [copy.deepcopy(metric)]

        match_mock.get_agg_metrics_batch.side_effect = RuntimeError("batch fail")
        match_mock.get_agg_metric_query.return_value = _agg_batch_data()

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        match_mock.get_agg_metrics_batch.assert_called_once()
        match_mock.get_agg_metric_query.assert_called_once()
        assert len(df_list) == 1
        assert "cpuFallback_avg" in config

    def test_std_batch_failure_falls_back(self, utils, match_mock):
        metric = _std_metric("latFallback")
        metrics = [copy.deepcopy(metric)]

        match_mock.get_results_batch.side_effect = RuntimeError("batch fail")
        match_mock.get_results.return_value = _std_batch_data()

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        match_mock.get_results_batch.assert_called_once()
        match_mock.get_results.assert_called_once()
        assert len(df_list) == 1
        assert "latFallback_value" in config


# ---------------------------------------------------------------------------
# Tests: mixed metrics (agg + standard)
# ---------------------------------------------------------------------------

class TestMixedMetrics:

    def test_mixed_metrics_dispatch_separately(self, utils, match_mock):
        agg = _agg_metric("aggMetric")
        std = _std_metric("stdMetric")
        metrics = [copy.deepcopy(agg), copy.deepcopy(std)]

        match_mock.get_agg_metrics_batch.return_value = {
            "aggMetric": _agg_batch_data(),
        }
        match_mock.get_results_batch.return_value = {
            "stdMetric": _std_batch_data(),
        }

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        # Each batch method called exactly once
        match_mock.get_agg_metrics_batch.assert_called_once()
        match_mock.get_results_batch.assert_called_once()
        assert len(df_list) == 2
        assert "aggMetric_avg" in config
        assert "stdMetric_value" in config

    def test_metadata_restored_after_batch(self, utils, match_mock):
        """Verify popped metadata fields are restored on the metric dicts."""
        agg = _agg_metric("aggRestore")
        std = _std_metric("stdRestore")
        metrics = [copy.deepcopy(agg), copy.deepcopy(std)]

        match_mock.get_agg_metrics_batch.return_value = {
            "aggRestore": _agg_batch_data(),
        }
        match_mock.get_results_batch.return_value = {
            "stdRestore": _std_batch_data(),
        }

        utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        # Check the metric dicts have their metadata restored
        for metric in metrics:
            assert "labels" in metric
            assert "direction" in metric
            assert "threshold" in metric
            assert "correlation" in metric
            assert "context" in metric


# ---------------------------------------------------------------------------
# Tests: _build_agg_dataframe helper
# ---------------------------------------------------------------------------

class TestBuildAggDataframe:

    def test_empty_data_returns_empty_df(self, utils, match_mock):
        metric = {
            "name": "testMetric",
            "metric_of_interest": "cpu",
            "agg": {"agg_type": "avg"},
        }
        df, names = utils._build_agg_dataframe([], metric, match_mock)
        assert df.empty
        assert names == ["testMetric_avg"]

    def test_avg_aggregation(self, utils, match_mock):
        metric = {
            "name": "cpuAvg",
            "metric_of_interest": "cpu",
            "agg": {"agg_type": "avg"},
        }
        data = [
            {"uuid": "u1", "timestamp": "2024-01-01T00:00:00Z", "cpu_avg": 0.5},
        ]
        df, names = utils._build_agg_dataframe(data, metric, match_mock)
        assert not df.empty
        assert "cpuAvg_avg" in df.columns
        assert names == ["cpuAvg_avg"]

    def test_percentile_aggregation(self, utils, match_mock):
        metric = {
            "name": "latP99",
            "metric_of_interest": "latency",
            "agg": {"agg_type": "percentiles"},
        }
        data = [
            {
                "uuid": "u1",
                "timestamp": "2024-01-01T00:00:00Z",
                "latency_percentiles_50.0": 10,
                "latency_percentiles_99.0": 50,
            },
        ]
        df, names = utils._build_agg_dataframe(data, metric, match_mock)
        assert "latP99_percentiles_50.0" in df.columns
        assert "latP99_percentiles_99.0" in df.columns
        assert len(names) == 2


# ---------------------------------------------------------------------------
# Tests: process_standard_metric with preloaded_data
# ---------------------------------------------------------------------------

class TestProcessStandardMetricPreloaded:

    def test_preloaded_skips_es_call(self, utils, match_mock):
        metric = {"name": "podLat", "metric_of_interest": "value", "metricName": "podLatency"}
        data = _std_batch_data()

        result_df, name = utils.process_standard_metric(
            UUIDS, metric, match_mock, "value",
            preloaded_data=data,
        )

        match_mock.get_results.assert_not_called()
        assert name == "podLat_value"
        assert not result_df.empty

    def test_no_preloaded_calls_es(self, utils, match_mock):
        metric = {"name": "podLat", "metric_of_interest": "value", "metricName": "podLatency"}
        match_mock.get_results.return_value = _std_batch_data()

        _, name = utils.process_standard_metric(
            UUIDS, metric, match_mock, "value",
        )

        match_mock.get_results.assert_called_once()
        assert name == "podLat_value"


# ---------------------------------------------------------------------------
# Tests: metadata fields popped before batch call
# ---------------------------------------------------------------------------

class TestMetadataPopBeforeBatch:

    def test_agg_metrics_have_no_metadata_keys_during_batch(self, utils, match_mock):
        """Labels/direction/etc must be popped before metrics hit the batch call."""
        metric = _agg_metric("checkPop")
        metrics = [copy.deepcopy(metric)]

        def capture_batch_args(_uuids, metrics_list, _ts_field):
            # At batch call time, metrics should NOT have popped keys
            for m in metrics_list:
                assert "labels" not in m, "labels should be popped"
                assert "direction" not in m, "direction should be popped"
                assert "threshold" not in m, "threshold should be popped"
                assert "correlation" not in m, "correlation should be popped"
                assert "context" not in m, "context should be popped"
            return {"checkPop": _agg_batch_data()}

        match_mock.get_agg_metrics_batch.side_effect = capture_batch_args

        utils.get_metric_data(UUIDS, metrics, match_mock, test_threshold=0)

    def test_std_metrics_have_no_metadata_keys_during_batch(self, utils, match_mock):
        """Labels/direction/etc must be popped before metrics hit the batch call."""
        metric = _std_metric("checkPopStd")
        metrics = [copy.deepcopy(metric)]

        def capture_batch_args(_uuids, metrics_list, _ts_field):
            for m in metrics_list:
                assert "labels" not in m, "labels should be popped"
                assert "direction" not in m, "direction should be popped"
                assert "threshold" not in m, "threshold should be popped"
                assert "correlation" not in m, "correlation should be popped"
                assert "context" not in m, "context should be popped"
            return {"checkPopStd": _std_batch_data()}

        match_mock.get_results_batch.side_effect = capture_batch_args

        utils.get_metric_data(UUIDS, metrics, match_mock, test_threshold=0)


# ---------------------------------------------------------------------------
# Tests: chunked batching when metrics exceed BATCH_METRIC_CHUNK_SIZE
# ---------------------------------------------------------------------------

class TestChunkedBatching:

    @patch("orion.utils.BATCH_METRIC_CHUNK_SIZE", 3)
    def test_agg_metrics_split_into_chunks(self, utils, match_mock):
        metrics = [copy.deepcopy(_agg_metric(f"agg_{i}")) for i in range(7)]

        def batch_side_effect(_uuids, chunk, _ts):
            return {m["name"]: _agg_batch_data() for m in chunk}

        match_mock.get_agg_metrics_batch.side_effect = batch_side_effect

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert match_mock.get_agg_metrics_batch.call_count == 3  # ceil(7/3)
        assert len(df_list) == 7
        for i in range(7):
            assert f"agg_{i}_avg" in config

    @patch("orion.utils.BATCH_METRIC_CHUNK_SIZE", 3)
    def test_std_metrics_split_into_chunks(self, utils, match_mock):
        metrics = [copy.deepcopy(_std_metric(f"std_{i}")) for i in range(5)]

        def batch_side_effect(_uuids, chunk, _ts):
            return {m["name"]: _std_batch_data() for m in chunk}

        match_mock.get_results_batch.side_effect = batch_side_effect

        df_list, config, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert match_mock.get_results_batch.call_count == 2  # ceil(5/3)
        assert len(df_list) == 5
        for i in range(5):
            assert f"std_{i}_value" in config

    @patch("orion.utils.BATCH_METRIC_CHUNK_SIZE", 2)
    def test_chunk_fallback_only_retries_failed_chunk(self, utils, match_mock):
        metrics = [copy.deepcopy(_agg_metric(f"m_{i}")) for i in range(4)]

        call_count = {"n": 0}

        def batch_side_effect(_uuids, chunk, _ts):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("chunk 2 failed")
            return {m["name"]: _agg_batch_data() for m in chunk}

        match_mock.get_agg_metrics_batch.side_effect = batch_side_effect
        match_mock.get_agg_metric_query.return_value = _agg_batch_data()

        df_list, _, _meta = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert match_mock.get_agg_metrics_batch.call_count == 2
        assert match_mock.get_agg_metric_query.call_count == 2
        assert len(df_list) == 4

    @patch("orion.utils.BATCH_METRIC_CHUNK_SIZE", 5)
    def test_fewer_metrics_than_chunk_size_single_call(self, utils, match_mock):
        metrics = [copy.deepcopy(_agg_metric(f"small_{i}")) for i in range(3)]

        match_mock.get_agg_metrics_batch.return_value = {
            m["name"]: _agg_batch_data() for m in metrics
        }

        df_list, _, _meta = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert match_mock.get_agg_metrics_batch.call_count == 1
        assert len(df_list) == 3


# ---------------------------------------------------------------------------
# Tests: metadata type metrics
# ---------------------------------------------------------------------------

def _agg_metadata_metric(name, metric_of_interest="version", agg_type="avg"):
    m = _agg_metric(name, metric_of_interest, agg_type)
    m["type"] = "metadata"
    return m


def _std_metadata_metric(name, metric_of_interest="value"):
    m = _std_metric(name, metric_of_interest)
    m["type"] = "metadata"
    return m


class TestMetadataTypeAgg:

    def test_agg_metadata_excluded_from_metrics_config(self, utils, match_mock):
        metrics = [copy.deepcopy(_agg_metadata_metric("k8sVersion"))]
        match_mock.get_agg_metrics_batch.return_value = {
            "k8sVersion": _agg_batch_data(metric_of_interest="version"),
        }

        _, config, meta_cols = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert len(config) == 0
        assert "k8sVersion_avg" in meta_cols

    def test_agg_metadata_dataframe_still_collected(self, utils, match_mock):
        metrics = [copy.deepcopy(_agg_metadata_metric("k8sVersion"))]
        match_mock.get_agg_metrics_batch.return_value = {
            "k8sVersion": _agg_batch_data(metric_of_interest="version"),
        }

        df_list, _, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert len(df_list) == 1


class TestMetadataTypeStd:

    def test_std_metadata_excluded_from_metrics_config(self, utils, match_mock):
        metrics = [copy.deepcopy(_std_metadata_metric("clusterVersion"))]
        match_mock.get_results_batch.return_value = {
            "clusterVersion": _std_batch_data(),
        }

        _, config, meta_cols = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert len(config) == 0
        assert "clusterVersion_value" in meta_cols

    def test_std_metadata_dataframe_still_collected(self, utils, match_mock):
        metrics = [copy.deepcopy(_std_metadata_metric("clusterVersion"))]
        match_mock.get_results_batch.return_value = {
            "clusterVersion": _std_batch_data(),
        }

        df_list, _, _ = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert len(df_list) == 1


class TestMetadataTypeMixed:

    def test_mixed_normal_and_metadata_routed_correctly(self, utils, match_mock):
        normal = copy.deepcopy(_agg_metric("cpuUsage"))
        meta = copy.deepcopy(_agg_metadata_metric("k8sVersion"))
        metrics = [normal, meta]

        match_mock.get_agg_metrics_batch.return_value = {
            "cpuUsage": _agg_batch_data(),
            "k8sVersion": _agg_batch_data(metric_of_interest="version"),
        }

        df_list, config, meta_cols = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert len(df_list) == 2
        assert "cpuUsage_avg" in config
        assert "k8sVersion_avg" not in config
        assert "k8sVersion_avg" in meta_cols
        assert "cpuUsage_avg" not in meta_cols

    def test_mixed_std_normal_and_metadata(self, utils, match_mock):
        normal = copy.deepcopy(_std_metric("podLatency"))
        meta = copy.deepcopy(_std_metadata_metric("clusterVersion"))
        metrics = [normal, meta]

        match_mock.get_results_batch.return_value = {
            "podLatency": _std_batch_data(),
            "clusterVersion": _std_batch_data(),
        }

        df_list, config, meta_cols = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert len(df_list) == 2
        assert "podLatency_value" in config
        assert "clusterVersion_value" not in config
        assert "clusterVersion_value" in meta_cols
        assert "podLatency_value" not in meta_cols

    def test_no_metadata_returns_empty_metadata_columns(self, utils, match_mock):
        metrics = [copy.deepcopy(_agg_metric("cpuUsage"))]
        match_mock.get_agg_metrics_batch.return_value = {
            "cpuUsage": _agg_batch_data(),
        }

        _, config, meta_cols = utils.get_metric_data(
            UUIDS, metrics, match_mock, test_threshold=0
        )

        assert len(meta_cols) == 0
        assert "cpuUsage_avg" in config
