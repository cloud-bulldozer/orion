"""Text/table output formatter."""

import json
import os
from typing import Any

import pandas as pd
from tabulate import tabulate

from orion.pipeline.analysis_result import AnalysisResult, group_change_points_by_time
from orion.pipeline.formatters.base import BaseFormatter
from orion.pipeline.formatters.json_formatter import JsonFormatter
from orion.reporting import Report, ReportType


class TextFormatter(BaseFormatter):
    """Formats analysis results as text tables using apache_otava Report."""

    def format(self, data: AnalysisResult) -> dict:
        display_data = {}
        if data.display_fields:
            json_formatter = JsonFormatter()
            json_result = json_formatter.format(data)
            data_json = json.loads(json_result[data.test_name])
            for display_field in data.display_fields:
                display_data[display_field] = []
                for record in data_json:
                    display_data[display_field].append(
                        str(record.get(display_field, "N/A"))
                    )

        series = data.series

        if display_data and data.display_fields:
            for display_field in data.display_fields:
                if display_field in data.dataframe.columns:
                    series.data[display_field] = data.dataframe[display_field]
                elif display_field in display_data:
                    values_list = display_data[display_field]
                    if len(values_list) == len(data.dataframe):
                        series.data[display_field] = pd.Series(
                            values_list, index=data.dataframe.index
                        )
                    else:
                        series_length = len(data.dataframe)
                        series_values = ["N/A"] * series_length
                        for i, value in enumerate(values_list):
                            if i < series_length:
                                series_values[i] = value
                        series.data[display_field] = pd.Series(
                            series_values, index=data.dataframe.index
                        )

        change_points_by_time = group_change_points_by_time(
            series, data.change_points_by_metric
        )

        report = Report(
            series, change_points_by_time,
            column_group_size=data.column_group_size,
        )
        output_table = report.produce_report(
            test_name=data.test_name, report_type=ReportType.LOG
        )
        return {data.test_name: output_table}

    def format_average(self, data: AnalysisResult) -> str:
        if len(data.dataframe) == 0:
            return ""
        last_row = data.dataframe.iloc[-1]
        return tabulate_average_values(
            data.avg_values,
            last_row,
            data.version_field,
            data.uuid_field,
            data.display_fields,
        )

    def save(self, test_name: str, formatted: Any,
             save_output_path: str) -> None:
        base = os.path.splitext(save_output_path)[0]
        output_file = f"{base}_table_{test_name}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(str(formatted))

    def print_output(self, test_name: str, formatted: Any,
                     data: AnalysisResult, pr: int = 0,
                     is_pull: bool = False) -> None:
        if not data.collapse:
            text = test_name
            if pr > 0:
                text = test_name + " | Pull Request #" + str(pr)
            print(text)
            print("=" * len(text))
            print(formatted)


def tabulate_average_values(
    avg_data,
    last_row,
    version_field="ocpVersion",
    uuid_field="uuid",
    display_fields=None,
) -> str:
    """Tabulate the average values."""
    headers = ["time", uuid_field, version_field]
    if version_field in last_row:
        data = [
            "0000-00-00 00:00:00 +0000",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "x" * len(last_row[version_field]),
        ]
    else:
        data = [
            "0000-00-00 00:00:00 +0000",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "x" * len("No Version"),
        ]
    for metric, value in avg_data.items():
        headers.append(metric)
        data.append(value)
    if display_fields:
        for display_field in display_fields:
            headers.append(display_field)
            data.append("x" * len(last_row[display_field]))
    return tabulate(
        [data],
        headers=headers,
        tablefmt="simple",
        floatfmt=[".2f", ".5f", ".6f", ".5f", ".5f", ".4f"],
    )
