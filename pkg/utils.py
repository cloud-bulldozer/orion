# pylint: disable=cyclic-import
# pylint: disable = line-too-long, too-many-arguments, consider-using-enumerate, broad-exception-caught
"""
module for all utility functions orion uses
"""
# pylint: disable = import-error

from functools import reduce
import os
import re
import sys
import xml.etree.ElementTree as ET
import xml.dom.minidom
from datetime import datetime, timedelta, timezone
from typing import List, Any, Dict, Tuple
from tabulate import tabulate
from fmatch.matcher import Matcher
from fmatch.logrus import SingletonLogger
import pandas as pd
import pyshorteners


class Utils:
    """
    Helper utils class
    """

    def __init__(self, uuid_field: str ="uuid", version_field: str ="ocpVersion", match: Matcher = None):
        """Instanciates utils class with uuid and version fields 

        Args:
            uuid_field (str): key to find the uuid
            version_field (str): key to find the version
            match (Matcher): matcher instance
        """
        self.uuid_field = uuid_field
        self.version_field = version_field
        self.logger = SingletonLogger.getLogger("Orion")
        self.match = match

    def get_metric_data(
        self, uuids: List[str], metrics: Dict[str, Any], timestamp_field: str="timestamp"
    ) -> Tuple[List[pd.DataFrame], List[Dict[str, Any]]]:
        """
        Get metrics data from elasticsearch based on given uuids and metrics configuration.

        Args:
            uuids (List[str]): List of uuids to query the metric data for.
            metrics (Dict[str, Any]): Dictionary of metrics configuration.
            timestamp_field (str): Field name holding the timestamp. Defaults to "timestamp".

        Returns:
            Tuple[List[pd.DataFrame], List[Dict[str, Any]]]: List of dataframes for each metric, and a second list of dictionaries containing metrics configuration.
        """
        dataframe_list = []
        metrics_config = []
        for metric in metrics:
            context = metric.pop("context", 5)
            self.logger.info("Collecting %s", metric["name"])
            try:
                if "agg" in metric:
                    metric_df, metric_dataframe_name = self.process_aggregation_metric(uuids, metric, timestamp_field)
                else:
                    metric_df, metric_dataframe_name = self.process_standard_metric(uuids, metric["metric_of_interest"], metric["query"], timestamp_field)
                dataframe_list.append(metric_df)
                metrics_config.append(metric)
                self.logger.debug(metric_df)
            except Exception as e:
                self.logger.error(
                    "Couldn't get metrics %s, exception %s",
                    metric["name"],
                    e,
                )
        return dataframe_list, metrics_config


    def process_aggregation_metric(
        self, uuids: List[str], metric: Dict[str, Any], timestamp_field: str="timestamp"
    ) -> Tuple[pd.DataFrame, str]:
        """Processes aggregated metric data and returns a DataFrame with the specified aggregation type.

        Args:
            uuids (List[str]): List of UUIDs to query the metric data for.
            metric (Dict[str, Any]): Dictionary containing metric details including aggregation specifications.
            timestamp_field (str, optional): Field name holding the timestamp. Defaults to "timestamp".

        Returns:
            Tuple[pd.DataFrame, str]: A tuple containing the DataFrame of aggregated metrics and the name of the metric with aggregation type.
        """

        metric_data = self.match.get_agg_metric_query(uuids, metric, timestamp_field)
        aggregation_value = metric["agg"]["value"]
        aggregation_type = metric["agg"]["agg_type"]
        metric_name = f"{metric['name']}_{aggregation_type}"
        if len(metric_data) == 0:
            aggregated_df = pd.DataFrame(columns=[self.uuid_field, "timestamp", metric_name])
        else:
            aggregated_df = self.match.convert_to_df(
                metric_data, columns=[self.uuid_field, "timestamp", metric_name],
                timestamp_field=timestamp_field
            )
            aggregated_df[timestamp_field] = aggregated_df[timestamp_field].apply(self.standardize_timestamp)

        aggregated_df = aggregated_df.drop_duplicates(subset=[self.uuid_field], keep="first")
        return aggregated_df, metric_name

    def process_standard_metric(
        self,
        uuids: List[str],
        metric_name: str,
        query: Dict[str, Any],
        timestamp_field: str="timestamp"
    ) -> Tuple[pd.DataFrame, str]:
        """Method to get dataframe of standard metric

        Args:
            uuids (List[str]): list of uuids
            metric_name (str): arbitrary metric name
            query (Dict[str, Any]): query parameters
            timestamp_field (str, optional): field name holding timestamp. Defaults to "timestamp".

        Returns:
            Tuple[pd.DataFrame, str]: dataframe and metric name
        """
        metric_data = self.match.get_results("", uuids, query)
        if len(metric_data) == 0:
            standard_metric_df = pd.DataFrame(columns=[self.uuid_field, "timestamp", metric_name])
        else:
            standard_metric_df = self.match.convert_to_df(
                metric_data, columns=[self.uuid_field, "timestamp", metric_name],
                timestamp_field=timestamp_field
            )
            standard_metric_df[timestamp_field] = standard_metric_df[timestamp_field].apply(self.standardize)
        standard_metric_df = standard_metric_df.drop_duplicates()
        return standard_metric_df, metric_name

    def standardize_timestamp(self, timestamp: Any) -> str:
        """Method to standardize timestamp formats

        Args:
            timestamp (Any): timestamp object with various formats 

        Returns:
            str: standard timestamp in format %Y-%m-%dT%H:%M:%S
        """
        if timestamp is None:
            return timestamp
        if timestamp.isnumeric():
            dt = pd.to_datetime(timestamp, unit='s', utc=True)
        else:
            dt = pd.to_datetime(timestamp, utc=True)
        return dt.replace(tzinfo=None).isoformat(timespec="seconds")


    def filter_uuids_on_index(
        self,
        metadata: Dict[str, Any],
        benchmark_index: str,
        uuids: List[str],
        baseline: str,
        filter_node_count: bool,
    ) -> List[str]:
        """returns the index to be used and runs as uuids

        Args:
            metadata (_type_): metadata from config
            uuids (_type_): uuids collected

        Returns:
            str: index and uuids
        """
        if "jobConfig.name" in metadata:
            return uuids
        if "benchmark.keyword" in metadata:
            if metadata["benchmark.keyword"] in ["ingress-perf", "k8s-netperf"]:
                return uuids
            if baseline == "" and not filter_node_count and "kube-burner" in benchmark_index:
                runs = self.match.match_kube_burner(uuids)
                ids = self.match.filter_runs(runs, runs)
            else:
                ids = uuids
        else:
            ids = uuids
        return ids


    def get_build_urls(self, uuids: List[str]) -> Dict[str, str]:
        """Gets metadata of the run from each test
            to get the build url

        Args:
            uuids (list): str list of uuid to find build urls of


        Returns:
            dict: build urls
        """

        test = self.match.get_results("", uuids, {})
        build_urls = {run[self.uuid_field]: run["buildUrl"] for run in test}
        return build_urls


    def process_test(
        self,
        test_config: Dict[str, Any],
        options: Dict[str, Any],
        start_timestamp: datetime
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """returns the dataframe for the test given

        Args:
            test_config (Dict[str, Any]): test configuration
            options (Dict[str, Any]): options
            start_timestamp (datetime): start timestamp

        Returns:
            Tuple[pd.DataFrame, Dict[str, Any]]: test dataframe and metrics configuration
        """

        uuids = []
        build_urls = []
        self.logger.info("The test %s has started", test_config["name"])

        test_threshold = 0
        if "threshold" in test_config:
            test_threshold = test_config["threshold"]
        timestamp_field = "timestamp"
        if "timestamp" in test_config:
            timestamp_field = test_config["timestamp"]

        # get uuids if there is a baseline
        if options["baseline"]:
            uuids = [uuid for uuid in re.split(r" |,", options["baseline"]) if uuid]
            uuids.append(options["uuid"])
            build_urls = self.get_build_urls(uuids, self.match)
        else:
            # get uuids, buildUrls matching with the metadata
            uuids_and_build_urls = self.match.get_uuid_by_metadata(
                test_config["metadata"],
                lookback_date=start_timestamp,
                lookback_size=options["lookback_size"],
                timestamp_field=timestamp_field
            )
            for uuid_build_url in uuids_and_build_urls:
                uuids.append(uuid_build_url["uuid"])
                build_urls.append(uuid_build_url["buildUrl"])
        if not uuids:
            self.logger.error("No UUID found for given metadata")
            return None, None


        uuids = self.filter_uuids_on_index(
            test_config["metadata"],
            test_config["benchmark_index"],
            uuids,
            options["baseline"],
            options["node_count"],
        )
        # get metrics data and dataframe
        metrics = test_config["metrics"]
        dataframe_list, metrics_config = self.get_metric_data(
            uuids, metrics, timestamp_field
        )
        if not dataframe_list:
            return None, metrics_config

        uuid_timestamp_map = pd.DataFrame()
        for df in dataframe_list:
            if "timestamp" in df.columns:
                uuid_timestamp_map = pd.concat(
                    [uuid_timestamp_map, df[[self.uuid_field, "timestamp"]].drop_duplicates()]
                )
        uuid_timestamp_map = uuid_timestamp_map.drop_duplicates(subset=[self.uuid_field])

        for i, df in enumerate(dataframe_list):
            dataframe_list[i] = df.drop(columns=["timestamp"], errors="ignore")
        merged_df = reduce(
            lambda left, right: pd.merge(left, right, on=self.uuid_field, how="outer"),
            dataframe_list,
        )

        merged_df = merged_df.merge(uuid_timestamp_map, on=self.uuid_field, how="left")
        merged_df = merged_df.sort_values(by="timestamp")

        shortener = pyshorteners.Shortener(timeout=10)
        merged_df["buildUrl"] = merged_df[self.uuid_field].apply(
            lambda uuid: (
                self.shorten_url(shortener, build_urls[uuid])
                if options["convert_tinyurl"]
                else build_urls[uuid]
            )
            # pylint: disable = cell-var-from-loop
        )

        merged_df = merged_df.reset_index(drop=True)
        # save the dataframe
        output_file_path = f"{options['save_data_path'].split('.')[0]}-{test_config['name']}.csv"
        self.match.save_results(merged_df, csv_file_path=output_file_path)
        return merged_df, metrics_config


    def shorten_url(self, shortener: any, uuids: str) -> str:
        """Shorten url if there is a list of buildUrls

        Args:
            shortener (any): shortener object to use tinyrl.short on
            uuids (List[str]): List of uuids to shorten

        Returns:
            str: a combined string of shortened urls
        """
        short_url_list = []
        for buildUrl in uuids.split(","):
            short_url_list.append(shortener.tinyurl.short(buildUrl))
        short_url = ",".join(short_url_list)
        return short_url


# pylint: disable=too-many-locals
def json_to_junit(
    test_name: str, data_json: Dict[Any, Any], metrics_config: Dict[Any, Any]
) -> str:
    """
    Convert the json output of orion to junit format

    Args:
        test_name (str): Name of the test
        data_json (Dict[Any, Any]): dictionary of changepoint data
        metrics_config (Dict[Any, Any]): dictionary of metrics configuration

    Returns:
        str: a string of the junit formatted output
    """
    
    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(
        testsuites, "testsuite", name=f"{test_name} nightly compare"
    )
    failures_count = 0
    test_count = 0
    for metric, value in metrics_config.items():
        test_count += 1
        labels = value["labels"]
        label_string = " ".join(labels) if labels else ""
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            name=f"{label_string} {metric} regression detection",
            timestamp=str(int(datetime.now().timestamp())),
        )
        if [
            run
            for run in data_json
            if not run["metrics"][metric]["percentage_change"] == 0
        ]:
            failures_count += 1
            failure = ET.SubElement(testcase, "failure")
            failure.text = (
                "\n" + generate_tabular_output(data_json, metric_name=metric) + "\n"
            )

    testsuite.set("failures", str(failures_count))
    testsuite.set("tests", str(test_count))
    xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
    dom = xml.dom.minidom.parseString(xml_str)
    pretty_xml_as_string = dom.toprettyxml()
    return pretty_xml_as_string


def generate_tabular_output(data: list, metric_name: str) -> str:
    """converts json to tabular format

    Args:
        data (list):data in json format
        metric_name (str): metric name
    Returns:
        str: tabular form of data
    """
    records = []
    create_record = lambda record: {  # pylint: disable = C3001
        "uuid": record["uuid"],
        "timestamp": datetime.fromtimestamp(record["timestamp"], timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "buildUrl": record["buildUrl"],
        metric_name: record["metrics"][metric_name]["value"],
        "is_changepoint": bool(record["metrics"][metric_name]["percentage_change"]),
        "percentage_change": record["metrics"][metric_name]["percentage_change"],
    }
    for i in range(0, len(data)):
        records.append(create_record(data[i]))

    df = pd.DataFrame(records).drop_duplicates().reset_index(drop=True)
    table = tabulate(df, headers="keys", tablefmt="psql")
    lines = table.split("\n")
    highlighted_lines = []
    if lines:
        highlighted_lines += lines[0:3]
    for i, line in enumerate(lines[3:-1]):
        if df["percentage_change"][
            i
        ]:  # Offset by 3 to account for header and separator
            highlighted_line = f"{lines[i+3]} -- changepoint"
            highlighted_lines.append(highlighted_line)
        else:
            highlighted_lines.append(line)
    highlighted_lines.append(lines[-1])

    # Join the lines back into a single string
    highlighted_table = "\n".join(highlighted_lines)

    return highlighted_table


def get_subtracted_timestamp(time_duration: str) -> datetime:
    """Get subtracted datetime from now

    Args:
        time_duration (str): time_gap in XdYh format

    Returns:
        datetime: return datetime of given timegap from now
    """
    logger = SingletonLogger.getLogger("Orion")
    reg_ex = re.match(r"^(?:(\d+)d)?(?:(\d+)h)?$", time_duration)
    if not reg_ex:
        logger.error("Wrong format for time duration, please provide in XdYh")
    days = int(reg_ex.group(1)) if reg_ex.group(1) else 0
    hours = int(reg_ex.group(2)) if reg_ex.group(2) else 0
    duration_to_subtract = timedelta(days=days, hours=hours)
    current_time = datetime.now(timezone.utc)
    timestamp_before = current_time - duration_to_subtract
    return timestamp_before
