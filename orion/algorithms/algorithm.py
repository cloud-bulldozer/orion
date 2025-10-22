"""Module for Generic Algorithm class"""

from abc import ABC, abstractmethod
from itertools import groupby
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Union
import pandas as pd
from tabulate import tabulate
from hunter.report import Report, ReportType
from hunter.series import Series, Metric, ChangePoint, ChangePointGroup
import orion.constants as cnsts


from orion.utils import json_to_junit


class Algorithm(ABC): # pylint: disable = too-many-arguments, too-many-instance-attributes
    """Generic Algorithm class for algorithm factory"""

    def __init__(
        self,
        dataframe: pd.DataFrame,
        test: dict,
        options: dict,
        metrics_config: dict[str, dict],
        version_field: str = "ocpVersion",
        uuid_field: str = "uuid"
    ) -> None:
        self.dataframe = dataframe
        self.test = test
        self.version_field = version_field
        self.options = options
        self.metrics_config = metrics_config
        self.regression_flag = False
        self.uuid_field = uuid_field

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
        return_json = collapsed_json if self.options["collapse"] else dataframe_json

        return (
            self.test["name"],
            json.dumps(return_json, indent=2),
            self.regression_flag,
        )

    def output_text(self) -> Tuple[str, str, bool]:
        """Outputs the data in text/tabular format"""
        # If display field is specified, use our custom combined table
        display_field = self.options.get("display")
        if display_field:
            _, json_output, _ = self.output_json()
            data_json = json.loads(json_output)

            # Create a combined table with all metrics and the display field
            combined_output = self._generate_combined_table_with_display(
                data_json, display_field
            )
            return self.test["name"], combined_output, self.regression_flag

        # Use default Hunter report
        series, change_points_by_metric = self._analyze()
        change_points_by_time = self.group_change_points_by_time(
            series, change_points_by_metric
        )
        report = Report(series, change_points_by_time)
        output_table = report.produce_report(
            test_name=self.test["name"], report_type=ReportType.LOG
        )
        return self.test["name"], output_table, self.regression_flag

    def _generate_combined_table_with_display(
        self, data_json: List[Dict], display_fields: List[str]
    ) -> str:
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
            row.append(record[self.uuid_field])

            row.append(record.get(self.version_field, "N/A"))
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
        headers = ["time", self.uuid_field, self.version_field]
        headers.extend(self.metrics_config.keys())
        headers.extend(display_fields)

        # Create the table
        table = tabulate(table_data, headers=headers, tablefmt="simple")

        return table

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
            uuid_field=self.uuid_field,
            display_field=self.options.get("display")
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
        Returns hunter.Series
        """
        metrics = {
            column: Metric(value.get("direction", 1), 1.0)
            for column, value in self.metrics_config.items()
        }
        data = {column: self.dataframe[column] for column in self.metrics_config}
        attributes = {
            column: self.dataframe[column]
            for column in self.dataframe.columns
            if column in [self.uuid_field, self.version_field]
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
