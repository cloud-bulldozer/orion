"""EDivisive Algorithm from hunter"""

import json
import pandas as pd
from hunter.report import Report, ReportType
from hunter.series import Metric, Series
from pkg.algorithm import Algorithm


class EDivisive(Algorithm):
    """Implementation of the EDivisive algorithm using hunter

    Args:
        Algorithm (Algorithm): Inherits
    """
    def output_json(self):
        _, series = self._analyze()
        change_points_by_metric = series.analyze().change_points
        dataframe_json = self.dataframe.to_json(orient="records")
        dataframe_json = json.loads(dataframe_json)

        for index, entry in enumerate(dataframe_json):
            entry["metrics"] = {
                key: {"value": entry.pop(key), "percentage_change": 0}
                for key in entry.keys() - {"uuid", "timestamp", "buildUrl"}
            }
            entry["is_changepoint"] = False

        for key, value in change_points_by_metric.items():
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

        return self.test["name"], dataframe_json

    def output_text(self):
        report, _ = self._analyze()
        output_table = report.produce_report(
            test_name=self.test["name"], report_type=ReportType.LOG
        )
        return self.test["name"], output_table

    def _analyze(self):
        self.dataframe["timestamp"] = pd.to_datetime(self.dataframe["timestamp"])
        self.dataframe["timestamp"] = self.dataframe["timestamp"].astype(int) // 10**9
        metrics = {
            column: Metric(1, 1.0)
            for column in self.dataframe.columns
            if column not in ["uuid", "timestamp", "buildUrl"]
        }
        data = {
            column: self.dataframe[column]
            for column in self.dataframe.columns
            if column not in ["uuid", "timestamp", "buildUrl"]
        }
        attributes = {
            column: self.dataframe[column]
            for column in self.dataframe.columns
            if column in ["uuid", "buildUrl"]
        }
        series = Series(
            test_name=self.test["name"],
            branch=None,
            time=list(self.dataframe["timestamp"]),
            metrics=metrics,
            data=data,
            attributes=attributes,
        )
        change_points = series.analyze().change_points_by_time
        report = Report(series, change_points)
        return report, series
