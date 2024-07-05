# pylint: disable = too-many-locals, line-too-long
"""The implementation module for Isolation forest and weighted mean"""
import json
import logging
from typing import List
from sklearn.ensemble import IsolationForest
import pandas as pd
from tabulate import tabulate
from pkg.algorithm import Algorithm
from fmatch.logrus import SingletonLogger
from pkg.utils import json_to_junit


class IsolationForestWeightedMean(Algorithm):
    """Isolation forest with weighted mean

    Args:
        Algorithm (Algorithm): _description_
    """

    def output_json(self):
        dataframe = self.dataframe
        dataframe['timestamp'] = dataframe['timestamp'].apply(lambda x: int(pd.to_datetime(x).timestamp()))
        dataframe, anomalies_df = self.analyze(dataframe)
        metric_columns = self.metrics_config.keys()
        dataframe_json = dataframe.to_json(orient="records")
        dataframe_json = json.loads(dataframe_json)
        for _, entry in enumerate(dataframe_json):
            uuid = entry["uuid"]
            entry["metrics"] = {
                key: {"value": entry.pop(key), "percentage_change": 0}
                for key in self.metrics_config
            }
            entry["is_anomalypoint"] = False

            row = anomalies_df[anomalies_df["uuid"] == uuid]
            for metric in metric_columns:
                if f"{metric}_pct_change" in anomalies_df.columns:
                    entry["metrics"][metric]["percentage_change"] = float(
                        row[f"{metric}_pct_change"].iloc[0]
                    )
                    if int(row["is_anomaly"].iloc[0]) == -1:
                        entry["is_anomalypoint"] = True
        return self.test["name"], json.dumps(dataframe_json, indent=2)

    def output_text(self):
        dataframe = self.dataframe
        dataframe, anomalies_df = self.analyze(dataframe)
        data_list = dataframe.values.tolist()
        column_names = dataframe.columns.tolist()
        tabulated_df = tabulate(data_list, headers=column_names)
        formatted_table = self.format_dataframe(tabulated_df, anomalies_df, dataframe)
        return self.test["name"], formatted_table

    def output_junit(self):
        test_name, data_json = self.output_json()
        data_json=json.loads(data_json)
        data_junit = json_to_junit(test_name=test_name, data_json=data_json)
        return test_name, data_junit

    def output_junit(self):
        test_name, data_json = self.output_json()
        data_json=json.loads(data_json)
        data_junit = json_to_junit(test_name=test_name, data_json=data_json, metrics_config=self.metrics_config)
        return test_name, data_junit

    def analyze(self, dataframe: pd.DataFrame):
        """Analyzing the data

        Args:
            dataframe (pd.DataFrame): _description_

        Returns:
            pd.Dataframe, pd.Dataframe: _description_
        """
        logger_instance = SingletonLogger.getLogger("Orion")
        logger_instance.info("Starting analysis using Isolation Forest")
        metric_columns = self.metrics_config.keys()
        model = IsolationForest(contamination="auto", random_state=42)
        dataframe_with_metrics = dataframe[metric_columns]
        model = IsolationForest(contamination="auto", random_state=42)
        model.fit(dataframe_with_metrics)
        predictions = model.predict(dataframe_with_metrics)
        dataframe["is_anomaly"] = predictions
        anomaly_scores = model.decision_function(dataframe_with_metrics)

        # Add anomaly scores to the DataFrame
        dataframe["anomaly_score"] = anomaly_scores

        # Calculate moving average for each metric
        window_size = (5 if self.options.get("anomaly_window",None) is None else int(self.options.get("anomaly_window",None)))
        moving_averages = dataframe_with_metrics.rolling(window=window_size).mean()

        # Initialize percentage change columns for all metrics
        for feature in dataframe_with_metrics.columns:
            dataframe[f"{feature}_pct_change"] = 0.0

        # Update DataFrame with percentage changes for anomalies exceeding 5%
        for idx, row in dataframe.iterrows():
            anomaly_check_flag = 0
            if row["is_anomaly"] == -1:
                for feature in dataframe_with_metrics.columns:
                    pct_change = (
                        (row[feature] - moving_averages.at[idx, feature])
                        / moving_averages.at[idx, feature]
                    ) * 100
                    if abs(pct_change) > (10 if self.options.get("min_anomaly_percent",None) is None else int(self.options.get("min_anomaly_percent",None))):
                        if (pct_change * self.metrics_config[feature]["direction"] > 0) or self.metrics_config[feature]["direction"]==0:
                            anomaly_check_flag = 1
                            dataframe.at[idx, f"{feature}_pct_change"] = pct_change
                if anomaly_check_flag == 1:
                    dataframe.at[idx, "is_anomaly"] = -1
                else:
                    dataframe.at[idx, "is_anomaly"] = 1
        anomaly_dataframe = dataframe[
            ["uuid", "is_anomaly", "anomaly_score"]
            + [f"{feature}_pct_change" for feature in dataframe_with_metrics.columns]
        ]
        dataframe = dataframe.drop(
            columns=["is_anomaly", "anomaly_score"]
            + [f"{feature}_pct_change" for feature in dataframe_with_metrics.columns]
        )
        return dataframe, anomaly_dataframe

    def format_dataframe(
        self, tabulated_text: str, anomalies_df: pd.DataFrame, dataframe: pd.DataFrame
    ):
        """Formatting function for text output

        Args:
            tabulated_text (str): _description_
            anomalies_df (pd.DataFrame): _description_
            dataframe (pd.DataFrame): _description_

        Returns:
            str: string output
        """
        lines = tabulated_text.split("\n")
        col_widths = self.__column_widths(lines)
        indexes = anomalies_df.index[anomalies_df["is_anomaly"] == -1].tolist()
        separators = []
        columns = dataframe.columns
        for _, tup in anomalies_df.iterrows():
            if tup["is_anomaly"] == -1:
                separator = ""
                info = ""
                for col_index, col_name in enumerate(columns):
                    col_width = col_widths[col_index]
                    anomaly = (
                        {
                            "metric_name": col_name,
                            "pct_change": tup[col_name + "_pct_change"],
                        }
                        if col_name + "_pct_change" in tup.keys()
                        and abs(tup[col_name + "_pct_change"]) > 0
                        else None
                    )
                    if anomaly:
                        separator += "·" * col_width + "  "
                        info += f"{anomaly['pct_change']:+.1f}%".rjust(col_width) + "  "
                    else:
                        separator += " " * (col_width + 2)
                        info += " " * (col_width + 2)

                separators.append(f"{separator}\n{info}\n{separator}")
        lines = lines[:2] + self.insert_multiple(lines[2:], separators, indexes)
        return "\n".join(lines)

    def __column_widths(self, log: List[str]) -> List[int]:
        ls = [len(c) for c in log[1].split(None)]
        return ls

    def insert_multiple(
        self, col: List[str], new_items: List[str], positions: List[int]
    ) -> List[str]:
        """Inserts an item into a collection at given positions"""
        result = []
        positions = set(positions)
        new_items_iter = iter(new_items)
        for i, x in enumerate(col):
            if i in positions:
                result.append(next(new_items_iter))
            result.append(x)
        return result
