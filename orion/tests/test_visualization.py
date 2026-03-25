"""
Unit test file for visualization functionality
"""

# pylint: disable = missing-function-docstring
import logging

import pandas as pd

from orion.logger import SingletonLogger
from orion.visualization import VizData, generate_test_html


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
