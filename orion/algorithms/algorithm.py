"""Module for Generic Algorithm class"""

from abc import ABC, abstractmethod
from itertools import groupby
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd
from tabulate import tabulate
from otava.report import Report, ReportType
from otava.series import Series, Metric, ChangePoint, ChangePointGroup
import orion.constants as cnsts


from orion.utils import json_to_junit
from orion.github_client import GitHubClient


class Algorithm(ABC): # pylint: disable = too-many-arguments, too-many-instance-attributes
    """Generic Algorithm class for algorithm factory"""

    def __init__(
        self,
        dataframe: pd.DataFrame,
        test: dict,
        options: dict,
        metrics_config: dict[str, dict],
    ) -> None:
        self.dataframe = dataframe
        self.test = test
        self.options = options
        self.metrics_config = metrics_config
        self.regression_flag = False
        self._github_client: Optional[GitHubClient] = None

    def output_json(self) -> Tuple[str, str, bool]:
        """Method to output json output

        Returns:
            Tuple[str, str, bool]: returns test_name, json output and regression flag
        """
        _, change_points_by_metric = self._analyze()
        dataframe_json = self.dataframe.to_json(orient="records")
        dataframe_json = json.loads(dataframe_json)
        collapsed_json = []

        for index, entry in enumerate(dataframe_json):
            entry["metrics"] = {
                key: {"value": entry.pop(key),
                      "percentage_change": 0,
                      "labels": " ".join(value["labels"]) if value["labels"] else ""}
                for key, value in self.metrics_config.items()
            }
            entry["is_changepoint"] = False

            # Display field data is already in the dataframe if requested

        for key, value in change_points_by_metric.items():
            for change_point in value:
                index = change_point.index
                percentage_change = (
                    (change_point.stats.mean_2 - change_point.stats.mean_1)
                    / change_point.stats.mean_1
                ) * 100
                if (
                    percentage_change * self.metrics_config[key]["direction"] > 0
                    or self.metrics_config[key]["direction"] == 0
                ):
                    dataframe_json[index]["metrics"][key]["percentage_change"] = (
                        percentage_change
                    )
                    dataframe_json[index]["is_changepoint"] = True
                    if self.options["collapse"]:
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
                github_client = self._get_github_client()
                if github_client and not dataframe_json[index].get("github_context"):
                    previous_entry = dataframe_json[index - 1] if index > 0 else None
                    previous_version = (
                        previous_entry.get(self.test["version_field"]) if previous_entry else None
                    )
                    previous_timestamp = (
                        previous_entry.get("timestamp") if previous_entry else None
                    )
                    current_version = dataframe_json[index].get(self.test["version_field"])
                    current_timestamp = dataframe_json[index].get("timestamp")
                    context = github_client.get_change_context(
                        previous_timestamp=previous_timestamp,
                        current_timestamp=current_timestamp,
                        previous_version=previous_version,
                        current_version=current_version,
                    )
                    if context:
                        dataframe_json[index]["github_context"] = context
        return_json = collapsed_json if self.options["collapse"] else dataframe_json

        return (
            self.test["name"],
            json.dumps(return_json, indent=2),
            self.regression_flag,
        )

    def output_text(self) -> Tuple[str, str, bool]:
        """Outputs the data in text/tabular format"""
        # If display field is specified, extract the data from the json output
        display_fields = self.options.get("display")
        display_data = {}
        if display_fields:
            _, json_output, _ = self.output_json()
            data_json = json.loads(json_output)
            for display_field in display_fields:
                display_data[display_field] = []
                for record in data_json:
                    display_data[display_field].append(str(record.get(display_field, "N/A")))

        # Use default apache_otava report
        series, change_points_by_metric = self._analyze()

        # Append display_data to series.data in the same format
        if display_data and display_fields:
            for display_field in display_fields:
                if display_field in self.dataframe.columns:
                    # If display field exists in dataframe, use it directly
                    series.data[display_field] = self.dataframe[display_field]
                elif display_field in display_data:
                    # Otherwise, use the display_data and convert list to pandas Series
                    values_list = display_data[display_field]
                    # Convert list to pandas Series to match the format of series.data
                    # The length should match the dataframe length
                    if len(values_list) == len(self.dataframe):
                        series.data[display_field] = pd.Series(
                            values_list, index=self.dataframe.index
                            )
                    else:
                        # If lengths don't match,
                        # create a Series with N/A for positions not in data_json
                        series_length = len(self.dataframe)
                        series_values = ["N/A"] * series_length
                        # Map values from data_json back to dataframe indices
                        # This assumes data_json maintains the original order
                        for i, value in enumerate(values_list):
                            if i < series_length:
                                series_values[i] = value
                        series.data[display_field] = pd.Series(
                            series_values, index=self.dataframe.index
                            )

        change_points_by_time = self.group_change_points_by_time(
            series, change_points_by_metric
        )

        report = Report(series, change_points_by_time)
        output_table = report.produce_report(
            test_name=self.test["name"], report_type=ReportType.LOG
        )
        return self.test["name"], output_table, self.regression_flag

    def _generate_combined_table_with_display(self,
                                              data_json: List[Dict],
                                              display_fields: List[str]) -> str:
        """Generate a combined table with all metrics and display field."""

        if not data_json:
            return "No data available"

        # Prepare data for the combined table
        table_data = []
        for record in data_json:
            row = []

            # Add timestamp
            timestamp = datetime.fromtimestamp(
                record["timestamp"], timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S +0000")
            row.append(timestamp)

            # Add UUID
            row.append(record[self.test["uuid_field"]])

            row.append(record.get(self.test["version_field"], "N/A"))
            # Add all metric values
            for metric_name in self.metrics_config.keys():
                if "metrics" in record and metric_name in record["metrics"]:
                    value = record["metrics"][metric_name]["value"]
                    # Check if this metric has a changepoint
                    percentage_change = record["metrics"][metric_name].get("percentage_change", 0)
                    if percentage_change != 0:
                        row.append(f"{value}")  # We'll handle changepoint marking later
                    else:
                        row.append(str(value))
                else:
                    row.append("N/A")

            # Add display field value
            for display_field in display_fields:
                row.append(str(record.get(display_field, "N/A")))

            table_data.append(row)

        # Prepare headers
        headers = ["time", self.test["uuid_field"], self.test["version_field"]]
        headers.extend(self.metrics_config.keys())
        headers.extend(display_fields)

        # Create the table
        table = tabulate(table_data, headers=headers, tablefmt="simple")

        return table

    def format_table_from_json(self, data_json: List[Dict]) -> str:
        """Produce table string from result JSON without changepoint markers.

        Used when an early changepoint was skipped so the table should not
        show the dotted line or percentage change.
        """
        display_fields = self.options.get("display") or []
        return self._generate_combined_table_with_display(data_json, display_fields)

    def output_junit(self) -> Tuple[str, str, bool]:
        """Output junit format

        Returns:
            _type_: return
        """
        test_name, data_json, _ = self.output_json()
        data_json = json.loads(data_json)
        data_junit = json_to_junit(
            test_name=test_name,
            data_json=data_json,
            metrics_config=self.metrics_config,
            uuid_field=self.test["uuid_field"],
            display_fields=self.options.get("display")
        )
        return test_name, data_junit, self.regression_flag

    @abstractmethod
    def _analyze(self):
        """Analyze algorithm"""

    def group_change_points_by_time(
        self, series: Series, change_points: Dict[str, List[ChangePoint]]
    ) -> List[ChangePointGroup]:
        """Return changepoint by time

        Args:
            series (Series): Series of data
            change_points (Dict[str, List[ChangePoint]]): Group of changepoints wrt time

        Returns:
            List[ChangePointGroup]: _description_
        """
        changes: List[ChangePoint] = []
        for metric in change_points.keys():
            changes += change_points[metric]

        changes.sort(key=lambda c: c.index)
        points = []
        for k, g in groupby(changes, key=lambda c: c.index):
            cp = ChangePointGroup(
                index=k,
                time=series.time[k],
                prev_time=series.time[k - 1],
                attributes=series.attributes_at(k),
                prev_attributes=series.attributes_at(k - 1),
                changes=list(g),
            )
            points.append(cp)

        return points

    def setup_series(self) -> Series:
        """
        Returns apache_otava.Series
        """
        metrics = {
            column: Metric(value.get("direction", 1), 1.0)
            for column, value in self.metrics_config.items()
        }
        data = {column: self.dataframe[column] for column in self.metrics_config}
        attributes = {
            column: self.dataframe[column]
            for column in self.dataframe.columns
            if column in [self.test["uuid_field"], self.test["version_field"]]
        }
        series = Series(
            test_name=self.test["name"],
            branch=None,
            time=list(self.dataframe["timestamp"]),
            metrics=metrics,
            data=data,
            attributes=attributes,
        )

        return series

    def output(self, output_format) -> Union[Any, None]:
        """Method to select output method

        Args:
            output_format (str): format of the output

        Raises:
            ValueError: In case of unmatched output

        Returns:
            method: return method to be used
        """
        if output_format == cnsts.JSON:
            return self.output_json()
        if output_format == cnsts.TEXT:
            return self.output_text()
        if output_format == cnsts.JUNIT:
            return self.output_junit()
        raise ValueError("Unsupported output format {output_format} selected")

    def _get_github_client(self) -> Optional[GitHubClient]:
        if self._github_client is not None:
            return self._github_client
        repositories = self.options.get("github_repos") or []
        if not repositories:
            self._github_client = None
            return None
        if not isinstance(repositories, (list, tuple)):
            repositories = [str(repositories)]
        self._github_client = GitHubClient(list(repositories))
        return self._github_client
