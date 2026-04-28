"""JSON output formatter."""

import json
import os
from typing import Any, Optional

from orion.pipeline.analysis_result import AnalysisResult
from orion.pipeline.formatters.base import BaseFormatter


class JsonFormatter(BaseFormatter):
    """Formats analysis results as JSON."""

    def format(self, data: AnalysisResult) -> dict:
        dataframe_json = json.loads(
            data.dataframe.to_json(orient="records")
        )
        collapsed_json = []

        for entry in dataframe_json:
            entry["metrics"] = {
                key: {
                    "value": entry.pop(key),
                    "percentage_change": 0,
                    "labels": value["labels"] if value["labels"] else [],
                }
                for key, value in data.metrics_config.items()
            }
            entry["is_changepoint"] = False

        github_client = BaseFormatter._get_github_client(data.github_repos)

        for key, value in data.change_points_by_metric.items():
            for change_point in value:
                index = change_point.index
                percentage_change = (
                    (change_point.stats.mean_2 - change_point.stats.mean_1)
                    / change_point.stats.mean_1
                ) * 100
                dataframe_json[index]["metrics"][key][
                    "percentage_change"
                ] = percentage_change
                dataframe_json[index]["is_changepoint"] = True
                if data.collapse:
                    if (
                        index > 0
                        and dataframe_json[index - 1] not in collapsed_json
                    ):
                        collapsed_json.append(dataframe_json[index - 1])
                    if dataframe_json[index] not in collapsed_json:
                        collapsed_json.append(dataframe_json[index])
                    if (
                        index < len(dataframe_json) - 1
                        and dataframe_json[index + 1] not in collapsed_json
                    ):
                        collapsed_json.append(dataframe_json[index + 1])

                if github_client and not dataframe_json[index].get(
                    "github_context"
                ):
                    previous_entry = (
                        dataframe_json[index - 1] if index > 0 else None
                    )
                    previous_version = (
                        previous_entry.get(data.version_field)
                        if previous_entry
                        else None
                    )
                    previous_timestamp = (
                        previous_entry.get("timestamp")
                        if previous_entry
                        else None
                    )
                    current_version = dataframe_json[index].get(
                        data.version_field
                    )
                    current_timestamp = dataframe_json[index].get("timestamp")
                    context = github_client.get_change_context(
                        previous_timestamp=previous_timestamp,
                        current_timestamp=current_timestamp,
                        previous_version=previous_version,
                        current_version=current_version,
                    )
                    if context:
                        dataframe_json[index]["github_context"] = context

        return_json = collapsed_json if data.collapse else dataframe_json
        return {data.test_name: json.dumps(return_json, indent=2)}

    def format_average(self, data: AnalysisResult) -> str:
        return data.avg_values.to_json()

    def save(self, test_name: str, formatted: Any,
             save_output_path: str) -> None:
        base = os.path.splitext(save_output_path)[0]
        output_file = f"{base}_{test_name}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(str(formatted))

    def print_output(self, test_name: str, formatted: Any,
                     data: AnalysisResult, pr: int = 0,
                     is_pull: bool = False) -> None:
        print(formatted)

    def print_and_save_pr(self, periodic: AnalysisResult,
                          pull: Optional[AnalysisResult],
                          save_output_path: str,
                          pr: int = 0) -> None:
        formatted_periodic = self.format(periodic)
        avg_formatted = self.format_average(periodic)
        results_json = {
            "periodic": json.loads(formatted_periodic[periodic.test_name]),
            "periodic_avg": json.loads(avg_formatted),
        }
        if pull:
            formatted_pull = self.format(pull)
            results_json["pull"] = json.loads(
                formatted_pull[pull.test_name]
            )
        combined = json.dumps(results_json, indent=2)
        print(combined)
        base = os.path.splitext(save_output_path)[0]
        output_file = f"{base}_{periodic.test_name}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(combined)
