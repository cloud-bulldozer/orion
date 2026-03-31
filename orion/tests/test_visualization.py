"""
Unit test file for visualization functionality
"""

# pylint: disable = missing-function-docstring
import logging
from types import SimpleNamespace

import pandas as pd

from orion.logger import SingletonLogger
from orion.visualization import VizData, _build_test_figure, generate_test_html


def _make_changepoint(index, mean_1, mean_2):
    return SimpleNamespace(
        index=index,
        stats=SimpleNamespace(mean_1=mean_1, mean_2=mean_2),
    )


def test_generate_test_html_writes_expected_file_and_injects_click_handler(
    tmp_path,
):
    SingletonLogger(debug=logging.INFO, name="Orion")

    dataframe = pd.DataFrame(
        {
            "timestamp": [
                "2026-03-01T00:00:00Z",
                "2026-03-02T00:00:00Z",
            ],
            "uuid": ["uuid-1", "uuid-2"],
            "ocpVersion": [
                "4.22.0-0.nightly-2026-03-01-000000",
                "4.22.0-0.nightly-2026-03-02-000000",
            ],
            "buildUrl": [
                "https://example.com/build/1",
                "https://example.com/build/2",
            ],
            "latency": [10.0, 12.5],
        }
    )
    viz_data = VizData(
        test_name="node-density",
        dataframe=dataframe,
        metrics_config={"latency": {"direction": 1}},
        change_points_by_metric={},
        uuid_field="uuid",
        version_field="ocpVersion",
    )

    output_base_path = str(tmp_path / "output_payload")
    output_file = generate_test_html(viz_data, output_base_path)
    expected_path = tmp_path / "output_payload_node-density_viz.html"

    assert output_file == str(expected_path)
    assert expected_path.is_file()

    html = expected_path.read_text(encoding="utf-8")
    assert "Orion: node-density" in html
    assert ".plotly-graph-div { width: 100% !important; }" in html
    assert "attachClickHandlers" in html
    assert "window.open(pt.customdata[0], '_blank');" in html


def test_build_test_figure_renders_changepoints_and_skips_out_of_range():
    dataframe = pd.DataFrame(
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
    viz_data = VizData(
        test_name="node-density",
        dataframe=dataframe,
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
    assert {trace.marker.color for trace in changepoint_traces} == {
        "#ff4444",
        "#39ff14",
    }


def test_build_test_figure_renders_only_matching_ack_markers():
    dataframe = pd.DataFrame(
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
        }
    )
    viz_data = VizData(
        test_name="node-density",
        dataframe=dataframe,
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
    assert ack_traces[0].marker.color == "#39ff14"
    assert ack_traces[0].customdata[0][0] == "https://example.com/build/2"
