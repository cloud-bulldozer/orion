"""EDivisive Algorithm from hunter"""
#pylint: disable = line-too-long
import json
import pandas as pd
from hunter.report import Report, ReportType
from hunter.series import Metric, Series
from pkg.algorithm import Algorithm
from pkg.utils import json_to_junit

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
                for key in self.metrics_config
            }
            entry["is_changepoint"] = False

        for key, value in change_points_by_metric.items():
            for change_point in value:
                index = change_point.index
                percentage_change = (
                    (change_point.stats.mean_2 - change_point.stats.mean_1)
                    / change_point.stats.mean_1
                ) * 100
                if percentage_change * self.metrics_config[key]["direction"] > 0 or self.metrics_config[key]["direction"]==0:
                    dataframe_json[index]["metrics"][key][
                        "percentage_change"
                    ] = percentage_change
                    dataframe_json[index]["is_changepoint"] = True

        return self.test["name"], json.dumps(dataframe_json, indent=2)

    def output_text(self):
        report, _ = self._analyze()
        output_table = report.produce_report(
            test_name=self.test["name"], report_type=ReportType.LOG
        )
        return self.test["name"], output_table

    def output_junit(self):
        test_name, data_json = self.output_json()
        data_json=json.loads(data_json)
        data_junit = json_to_junit(test_name=test_name, data_json=data_json, metrics_config=self.metrics_config)
        return test_name, data_junit

    def _analyze(self):
        self.dataframe["timestamp"] = pd.to_datetime(self.dataframe["timestamp"])
        self.dataframe["timestamp"] = self.dataframe["timestamp"].astype(int) // 10**9
        metrics = {column: Metric(value.get("direction",1), 1.0) for column,value in self.metrics_config.items()}
        data = {column: self.dataframe[column] for column in self.metrics_config}
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
        # filter by direction
        for change_point_group in change_points:
            change_point_group.changes = [
                change for change in change_point_group.changes
                if not (
                    (self.metrics_config[change.metric]["direction"] == 1 and change.stats.mean_1 > change.stats.mean_2) or
                    (self.metrics_config[change.metric]["direction"] == -1 and change.stats.mean_1 < change.stats.mean_2)
                )
            ]

        for i in range(len(change_points)-1,-1,-1):
            if len(change_points[i].changes) == 0:
                del change_points[i]


        report = Report(series, change_points)
        return report, series
