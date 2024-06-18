#pylint: disable = too-many-locals, line-too-long
"""The implementation module for Isolation forest and weighted mean"""
import json
import logging
import xml.etree.ElementTree as ET
import xml.dom.minidom
from typing import List
from sklearn.ensemble import IsolationForest
import pandas as pd
from tabulate import tabulate
from pkg.algorithm import Algorithm
from pkg.logrus import SingletonLogger
from pkg.types import OptionMap
from pkg.utils import Metrics


class IsolationForestWeightedMean(Algorithm):
    """Isolation forest with weighted mean

    Args:
        Algorithm (Algorithm): _description_
    """

    def output_json(self):
        dataframe = self.dataframe
        dataframe, anomalies_df = self.analyze(dataframe)
        metric_columns = [
            column
            for column in dataframe.columns
            if column not in ["uuid", "buildUrl", "timestamp"]
        ]
        dataframe_json = dataframe.to_json(orient="records")
        dataframe_json = json.loads(dataframe_json)

        for _, entry in enumerate(dataframe_json):
            uuid = entry["uuid"]
            entry["metrics"] = {
                key: {"value": entry.pop(key), "percentage_change": 0}
                for key in entry.keys() - {"uuid", "timestamp", "buildUrl"}
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
        return self.test["name"], dataframe_json

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
        data_junit = self._json_to_junit(test_name=test_name, data_json=data_json)
        return test_name, data_junit
    
    def _json_to_junit(self, test_name, data_json):
        testsuites = ET.Element("testsuites")
        testsuite = ET.SubElement(testsuites, "testsuite", name=f"{test_name} nightly compare")
        for run in data_json:
            run_data = {str(key): str(value).lower() for key, value in run.items() if key in ["uuid","timestamp", "buildUrl"]}
            for metric, value in run["metrics"].items():
                failure = "false"
                if not value["percentage_change"] == 0:
                    failure = "true"
                testcase = ET.SubElement(testsuite, "testcase", 
                                         name=f"{test_name} {' '.join(Metrics.metrics[metric]['labels'])} {metric} regression detection",
                                         attrib=run_data, failure=failure)
                if failure=="true":
                    properties=ET.SubElement(testcase, "properties")
                    value={str(k):str(v) for k,v in value.items()}
                    ET.SubElement(properties, "property", name=metric, attrib=value)
        xml_str = ET.tostring(testsuites, encoding='utf8', method='xml').decode()
        dom = xml.dom.minidom.parseString(xml_str)
        pretty_xml_as_string = dom.toprettyxml()
        return pretty_xml_as_string

    def analyze(self, dataframe: pd.DataFrame):
        """Analyzing the data

        Args:
            dataframe (pd.DataFrame): _description_

        Returns:
            pd.Dataframe, pd.Dataframe: _description_
        """
        logger_instance = SingletonLogger(debug=logging.INFO).logger
        logger_instance.info("Starting analysis using Isolation Forest")
        metric_columns = [
            column
            for column in dataframe.columns
            if column not in ["uuid", "buildUrl", "timestamp"]
        ]
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
        options=OptionMap.get_map()
        window_size = (5 if options.get("anomaly_window",None) is None else int(OptionMap.get_option("anomaly_window")))
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
                    if abs(pct_change) > (10 if options.get("min_anomaly_percent",None) is None else int(OptionMap.get_option("min_anomaly_percent"))):
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
