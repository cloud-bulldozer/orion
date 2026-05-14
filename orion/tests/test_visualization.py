"""
Unit test file for visualization functionality
"""

# pylint: disable = missing-function-docstring, redefined-outer-name
import logging
from types import SimpleNamespace

import pandas as pd
import pytest

from orion.logger import SingletonLogger
from orion.visualization import VizData, _build_test_figure, generate_test_html


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
    assert "right-click to copy UUID" in html
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
        if isinstance(trace.hovertext, str) and "CHANGEPOINT" in trace.hovertext
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
        if isinstance(trace.hovertext, str) and "ACKed" in trace.hovertext
    ]

    assert len(ack_traces) == 1
    assert ack_traces[0].x[0] == 1
    assert ack_traces[0].customdata[0][0] == "https://example.com/build/2"
    assert ack_traces[0].customdata[0][1] == "uuid-2"
