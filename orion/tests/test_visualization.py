"""
Unit test file for visualization functionality
"""

# pylint: disable = missing-function-docstring, redefined-outer-name
import logging
from types import SimpleNamespace

import pandas as pd
import pytest

from orion.logger import SingletonLogger
from orion.visualization import (
    VizData, _build_test_figure, _classify_changepoints, generate_test_html,
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
    assert "attachHandlers" in html
    assert "repairProwUrl" in html
    assert "window.open(repairProwUrl(pt.customdata[0]), '_blank');" in html
    assert "plotly_hover" in html
    assert "plotly_unhover" in html
    assert "contextmenu" in html
    assert "clipboard" in html
    assert "orion-toast" in html
    assert "right-click" in html
    assert "stopPropagation" in html


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
        if isinstance(trace.hovertemplate, str) and "CHANGEPOINT" in trace.hovertemplate
    ]

    assert len(changepoint_traces) == 2
    assert {trace.x[0] for trace in changepoint_traces} == {1, 2}

    for trace in changepoint_traces:
        cd = trace.customdata[0]
        assert len(cd) == 2, "customdata should contain [build_url, uuid]"
        assert cd[1].startswith("uuid-"), "second element should be the UUID"


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
        if isinstance(trace.hovertemplate, str) and "ACKed" in trace.hovertemplate
    ]

    assert len(ack_traces) == 1
    assert ack_traces[0].x[0] == 1
    assert ack_traces[0].customdata[0][0] == "https://example.com/build/2"
    assert ack_traces[0].customdata[0][1] == "uuid-2"


def test_classify_changepoints_precomputes_direction_and_color():
    metrics_config = {
        "latency": {"direction": 1},
        "throughput": {"direction": -1},
        "any_change": {"direction": 0},
    }
    change_points_by_metric = {
        "latency": [
            _make_changepoint(index=1, mean_1=10.0, mean_2=20.0),
        ],
        "throughput": [
            _make_changepoint(index=2, mean_1=100.0, mean_2=80.0),
            _make_changepoint(index=3, mean_1=80.0, mean_2=90.0),
        ],
        "any_change": [
            _make_changepoint(index=0, mean_1=50.0, mean_2=55.0),
            _make_changepoint(index=1, mean_1=55.0, mean_2=50.0),
        ],
    }

    result = _classify_changepoints(change_points_by_metric, metrics_config)

    # latency: +100% with direction=1 → regression (red)
    assert len(result["latency"]) == 1
    cc = result["latency"][0]
    assert cc.index == 1
    assert cc.pct_change == pytest.approx(100.0)
    assert cc.is_regression is True
    assert cc.color == "#ff4444"

    # throughput: -20% with direction=-1 → regression (red)
    assert len(result["throughput"]) == 2
    cc_drop = result["throughput"][0]
    assert cc_drop.pct_change == pytest.approx(-20.0)
    assert cc_drop.is_regression is True
    assert cc_drop.color == "#ff4444"
    # throughput: +12.5% with direction=-1 → improvement (green)
    cc_rise = result["throughput"][1]
    assert cc_rise.pct_change == pytest.approx(12.5)
    assert cc_rise.is_regression is False
    assert cc_rise.color == "#39ff14"

    # any_change: direction=0 → always regression regardless of sign
    cc_any_pos = result["any_change"][0]
    assert cc_any_pos.pct_change == pytest.approx(10.0)
    assert cc_any_pos.is_regression is True
    assert cc_any_pos.color == "#ff4444"

    cc_any_neg = result["any_change"][1]
    assert cc_any_neg.pct_change == pytest.approx(-9.09, rel=1e-2)
    assert cc_any_neg.is_regression is True
    assert cc_any_neg.color == "#ff4444"


def test_classify_changepoints_defaults_direction_to_1():
    metrics_config = {"metric_a": {}}
    change_points_by_metric = {
        "metric_a": [_make_changepoint(index=0, mean_1=10.0, mean_2=5.0)],
    }

    result = _classify_changepoints(change_points_by_metric, metrics_config)

    # -50% with default direction=1 → improvement (green)
    cc = result["metric_a"][0]
    assert cc.pct_change == pytest.approx(-50.0)
    assert cc.is_regression is False
    assert cc.color == "#39ff14"
