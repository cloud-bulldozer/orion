"""
Unit tests for orion/visualization.py
"""

# pylint: disable = redefined-outer-name
# pylint: disable = missing-function-docstring
# pylint: disable = import-error

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from otava.analysis import TTestStats
from otava.series import ChangePoint

from orion.logger import SingletonLogger
from orion.visualization import (
    VizData,
    _classify_changepoint,
    _prepare_timestamps,
    _short_version,
    _build_test_figure,
    generate_test_html,
)


@pytest.fixture
def sample_dataframe():
    """Shared dataframe used across visualization tests."""
    return pd.DataFrame(
        {
            "timestamp": [
                "2026-03-01T00:00:00Z",
                "2026-03-02T00:00:00Z",
                "2026-03-03T00:00:00Z",
            ],
            "uuid": ["uuid-1", "uuid-2", "uuid-3"],
            "ocpVersion": [
                "4.22.0-0.nightly-2026-03-01-000000",
                "4.22.0-0.nightly-2026-03-02-000000",
                "4.22.0-0.nightly-2026-03-03-000000",
            ],
            "buildUrl": [
                "https://example.com/build/1",
                "https://example.com/build/2",
                "https://example.com/build/3",
            ],
            "latency": [10.0, 20.0, 30.0],
            "cpu": [30.0, 20.0, 10.0],
        }
    )


def _make_changepoint(index, mean_1, mean_2):
    return SimpleNamespace(
        index=index,
        stats=SimpleNamespace(mean_1=mean_1, mean_2=mean_2),
    )


def test_generate_test_html_writes_expected_file_and_injects_click_handler(
    tmp_path, sample_dataframe,
):
    SingletonLogger(debug=logging.INFO, name="Orion")

    viz_data = VizData(
        test_name="node-density",
        dataframe=sample_dataframe,
        metrics_config={"latency": {"direction": 1}},
        change_points_by_metric={},
        uuid_field="uuid",
        version_field="ocpVersion",
    )

    output_file = str(tmp_path / "output_payload_node-density_viz.html")
    result = generate_test_html(viz_data, output_file)

    assert result == output_file
    assert (tmp_path / "output_payload_node-density_viz.html").is_file()

    html = (tmp_path / "output_payload_node-density_viz.html").read_text(encoding="utf-8")
    assert "Orion: node-density" in html
    assert ".plotly-graph-div { width: 100% !important; }" in html
    assert "attachClickHandlers" in html
    assert "window.open(pt.customdata[0], '_blank');" in html


def test_build_test_figure_renders_changepoints_and_skips_out_of_range(sample_dataframe):
    viz_data = VizData(
        test_name="node-density",
        dataframe=sample_dataframe,
        metrics_config={
            "latency": {"direction": 1},
            "cpu": {"direction": 1},
        },
        change_points_by_metric={
            "latency": [
                _make_changepoint(index=1, mean_1=10.0, mean_2=20.0),
                _make_changepoint(index=10, mean_1=20.0, mean_2=40.0),
            ],
            "cpu": [
                _make_changepoint(index=2, mean_1=20.0, mean_2=10.0),
            ],
        },
        uuid_field="uuid",
        version_field="ocpVersion",
    )

    fig = _build_test_figure(viz_data)
    changepoint_traces = [
        trace for trace in fig.data
        if isinstance(trace.hovertext, str) and "CHANGEPOINT" in trace.hovertext
    ]

    assert len(changepoint_traces) == 2
    assert {trace.x[0] for trace in changepoint_traces} == {1, 2}


def test_build_test_figure_renders_only_matching_ack_markers(sample_dataframe):
    viz_data = VizData(
        test_name="node-density",
        dataframe=sample_dataframe,
        metrics_config={"latency": {"direction": 1}},
        change_points_by_metric={},
        uuid_field="uuid",
        version_field="ocpVersion",
        acked_entries=[
            {"metric": "latency", "uuid": "uuid-2", "reason": "known issue"},
            {"metric": "cpu", "uuid": "uuid-2", "reason": "wrong metric"},
            {"metric": "latency", "uuid": "missing-uuid", "reason": "missing row"},
        ],
    )

    fig = _build_test_figure(viz_data)
    ack_traces = [
        trace for trace in fig.data
        if isinstance(trace.hovertext, str) and "ACKed" in trace.hovertext
    ]

    assert len(ack_traces) == 1
    assert ack_traces[0].x[0] == 1
    assert ack_traces[0].customdata[0][0] == "https://example.com/build/2"

@pytest.fixture(autouse=True)
def _init_logger():
    SingletonLogger(debug=logging.DEBUG, name="Orion")


def _make_stats(mean_1=100.0, mean_2=80.0):
    return TTestStats(mean_1=mean_1, mean_2=mean_2, std_1=5, std_2=5, pvalue=0.01)


def _make_dataframe(n=10, seed=42):
    rng = np.random.RandomState(seed)
    timestamps = [1704067200 + i * 86400 for i in range(n)]
    return pd.DataFrame({
        "uuid": [f"uuid-{i}" for i in range(n)],
        "timestamp": timestamps,
        "ocpVersion": ["4.14.0"] * n,
        "buildUrl": [f"http://build/{i}" for i in range(n)],
        "throughput": rng.normal(100, 5, n).tolist(),
    })


def _make_viz_data(n=10, change_points=None, acked=None, metrics_config=None):
    df = _make_dataframe(n=n)
    if metrics_config is None:
        metrics_config = {
            "throughput": {"direction": 1, "threshold": 5},
        }
    return VizData(
        test_name="test-bench",
        dataframe=df,
        metrics_config=metrics_config,
        change_points_by_metric=change_points or {},
        uuid_field="uuid",
        version_field="ocpVersion",
        acked_entries=acked,
    )


# ---------------------------------------------------------------------------
# _short_version
# ---------------------------------------------------------------------------

class TestShortVersion:
    def test_nightly_extraction(self):
        v = "4.22.0-0.nightly-2026-02-03-002928"
        assert _short_version(v) == "nightly-02-03"

    def test_non_nightly_truncated(self):
        assert _short_version("4.14.0") == "4.14.0"

    def test_long_non_nightly_truncated_to_20(self):
        v = "a" * 30
        assert _short_version(v) == "a" * 20

    def test_numeric_input(self):
        result = _short_version(4.14)
        assert isinstance(result, str)

    def test_nightly_different_date(self):
        v = "4.18.0-0.nightly-2025-11-22-123456"
        assert _short_version(v) == "nightly-11-22"


# ---------------------------------------------------------------------------
# _prepare_timestamps
# ---------------------------------------------------------------------------

class TestPrepareTimestamps:
    def test_numeric_epochs(self):
        df = pd.DataFrame({"timestamp": [1704067200, 1704153600]})
        result = _prepare_timestamps(df)
        assert result.iloc[0].year == 2024
        assert result.iloc[0].month == 1

    def test_string_timestamps(self):
        df = pd.DataFrame({"timestamp": ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"]})
        result = _prepare_timestamps(df)
        assert result.iloc[0].year == 2024


# ---------------------------------------------------------------------------
# _classify_changepoint
# ---------------------------------------------------------------------------

class TestClassifyChangepoint:
    def test_regression_direction_1_increase(self):
        """BEHAVIOR GUARD: direction=1 means an INCREASE (positive pct) is a
        regression.  This is the *opposite* of the EDivisive convention where
        direction=1 means "higher is better".  The formula is:
            is_regression = (pct_change * direction > 0) or direction == 0
        so direction=1 + positive pct → regression.
        If this test fails, the visualization regression coloring has changed."""
        stats = _make_stats(mean_1=100, mean_2=120)
        pct, is_reg = _classify_changepoint(stats, direction=1)
        assert pct == pytest.approx(20.0)
        assert is_reg is True, (
            "direction=1 with positive pct_change should be classified as regression. "
            "If this changed, check _classify_changepoint and update callers."
        )

    def test_improvement_direction_1_decrease(self):
        """direction=1: decrease is NOT a regression."""
        stats = _make_stats(mean_1=100, mean_2=80)
        pct, is_reg = _classify_changepoint(stats, direction=1)
        assert pct == pytest.approx(-20.0)
        assert is_reg is False

    def test_regression_direction_neg1_decrease(self):
        """direction=-1: decrease (negative pct) is a regression."""
        stats = _make_stats(mean_1=100, mean_2=80)
        pct, is_reg = _classify_changepoint(stats, direction=-1)
        assert pct == pytest.approx(-20.0)
        assert is_reg is True

    def test_improvement_direction_neg1_increase(self):
        """direction=-1: increase is NOT a regression."""
        stats = _make_stats(mean_1=100, mean_2=120)
        pct, is_reg = _classify_changepoint(stats, direction=-1)
        assert pct == pytest.approx(20.0)
        assert is_reg is False

    def test_direction_0_always_regression(self):
        """direction=0: any change is flagged as regression."""
        stats = _make_stats(mean_1=100, mean_2=120)
        _, is_reg = _classify_changepoint(stats, direction=0)
        assert is_reg is True

    def test_zero_mean_1(self):
        """When mean_1 is 0, pct_change should be 0."""
        stats = _make_stats(mean_1=0, mean_2=50)
        pct, _ = _classify_changepoint(stats, direction=1)
        assert pct == 0.0

    def test_no_change(self):
        stats = _make_stats(mean_1=100, mean_2=100)
        pct, _ = _classify_changepoint(stats, direction=1)
        assert pct == 0.0


# ---------------------------------------------------------------------------
# VizData
# ---------------------------------------------------------------------------

class TestVizData:
    def test_defaults(self):
        df = _make_dataframe()
        vd = VizData(
            test_name="t1",
            dataframe=df,
            metrics_config={},
            change_points_by_metric={},
            uuid_field="uuid",
            version_field="ocpVersion",
        )
        assert vd.acked_entries == []
        assert vd.test_name == "t1"

    def test_with_acked(self):
        df = _make_dataframe()
        acked = [{"uuid": "u1", "metric": "cpu", "reason": "known"}]
        vd = VizData(
            test_name="t1",
            dataframe=df,
            metrics_config={},
            change_points_by_metric={},
            uuid_field="uuid",
            version_field="ocpVersion",
            acked_entries=acked,
        )
        assert len(vd.acked_entries) == 1


# ---------------------------------------------------------------------------
# _build_test_figure
# ---------------------------------------------------------------------------

class TestBuildTestFigure:
    def test_no_metrics_returns_empty_figure(self):
        vd = _make_viz_data(metrics_config={})
        fig = _build_test_figure(vd)
        assert "no metrics" in fig.layout.title.text

    def test_basic_figure_structure(self):
        vd = _make_viz_data()
        fig = _build_test_figure(vd)
        assert fig.layout.title.text is not None
        assert "test-bench" in fig.layout.title.text
        assert len(fig.data) >= 1  # at least the main trace

    def test_figure_with_changepoint(self):
        df = _make_dataframe(n=10)
        cp = ChangePoint(
            index=5, qhat=0.0, metric="throughput",
            time=df["timestamp"].iloc[5],
            stats=_make_stats(mean_1=100, mean_2=80),
        )
        vd = _make_viz_data(change_points={"throughput": [cp]})
        fig = _build_test_figure(vd)
        # Should have main trace + changepoint marker
        assert len(fig.data) >= 2

    def test_figure_with_acked_entry(self):
        acked = [{"uuid": "uuid-3", "metric": "throughput", "reason": "known issue"}]
        vd = _make_viz_data(acked=acked)
        fig = _build_test_figure(vd)
        # Should have main trace + ack marker
        assert len(fig.data) >= 2

    def test_multiple_metrics(self):
        df = _make_dataframe(n=10)
        rng = np.random.RandomState(99)
        df["latency"] = rng.normal(50, 3, 10).tolist()
        config = {
            "throughput": {"direction": 1, "threshold": 5},
            "latency": {"direction": -1, "threshold": 5},
        }
        vd = VizData(
            test_name="multi",
            dataframe=df,
            metrics_config=config,
            change_points_by_metric={},
            uuid_field="uuid",
            version_field="ocpVersion",
        )
        fig = _build_test_figure(vd)
        assert fig.layout.height == 400 * 2 + 100

    def test_changepoint_out_of_bounds_skipped(self):
        """Changepoint with index >= len(df) is safely skipped."""
        cp = ChangePoint(
            index=999, qhat=0.0, metric="throughput", time=0,
            stats=_make_stats(),
        )
        vd = _make_viz_data(n=5, change_points={"throughput": [cp]})
        fig = _build_test_figure(vd)
        # Should not crash, just skip the out-of-bounds CP
        assert fig is not None

    def test_version_change_markers(self):
        """Version changes between consecutive rows add vertical lines."""
        df = _make_dataframe(n=6)
        df.loc[3:, "ocpVersion"] = "4.15.0"
        vd = VizData(
            test_name="ver-change",
            dataframe=df,
            metrics_config={"throughput": {"direction": 1}},
            change_points_by_metric={},
            uuid_field="uuid",
            version_field="ocpVersion",
        )
        fig = _build_test_figure(vd)
        # Should have at least one shape for the version boundary
        assert len(fig.layout.shapes) >= 1

    def test_regression_sorted_first(self):
        """Metrics with regressions appear before stable metrics."""
        df = _make_dataframe(n=10)
        rng = np.random.RandomState(99)
        df["stable_metric"] = rng.normal(50, 1, 10).tolist()
        cp = ChangePoint(
            index=5, qhat=0.0, metric="throughput",
            time=df["timestamp"].iloc[5],
            stats=_make_stats(mean_1=100, mean_2=80),
        )
        config = {
            "stable_metric": {"direction": 1},
            "throughput": {"direction": 1},
        }
        vd = VizData(
            test_name="sorted",
            dataframe=df,
            metrics_config=config,
            change_points_by_metric={"throughput": [cp]},
            uuid_field="uuid",
            version_field="ocpVersion",
        )
        fig = _build_test_figure(vd)
        # throughput (with regression) should sort before stable_metric
        subplot_titles = [a.text for a in fig.layout.annotations if hasattr(a, "text") and a.text in config]
        if len(subplot_titles) >= 2:
            assert subplot_titles[0] == "throughput"


# ---------------------------------------------------------------------------
# generate_test_html
# ---------------------------------------------------------------------------

class TestGenerateTestHtml:
    def test_generates_html_file(self, tmp_path):
        vd = _make_viz_data()
        output_file = str(tmp_path / "output_test-bench_viz.html")
        result = generate_test_html(vd, output_file)
        assert result == output_file
        with open(result, encoding="utf-8") as f:
            html = f.read()
        assert "<html>" in html.lower() or "<!doctype" in html.lower() or "plotly" in html.lower()

    def test_html_contains_click_handler(self, tmp_path):
        vd = _make_viz_data()
        output_file = str(tmp_path / "output_test-bench_viz.html")
        result = generate_test_html(vd, output_file)
        with open(result, encoding="utf-8") as f:
            html = f.read()
        assert "plotly_click" in html

    def test_html_contains_style_injection(self, tmp_path):
        vd = _make_viz_data()
        output_file = str(tmp_path / "output_test-bench_viz.html")
        result = generate_test_html(vd, output_file)
        with open(result, encoding="utf-8") as f:
            html = f.read()
        assert "width: 100%" in html

    def test_returns_output_path(self, tmp_path):
        vd = _make_viz_data()
        output_file = str(tmp_path / "report_viz.html")
        result = generate_test_html(vd, output_file)
        assert result == output_file
