# pylint: disable=cyclic-import
# pylint: disable = line-too-long, too-many-arguments, consider-using-enumerate, broad-exception-caught
"""
module for all utility functions orion uses
"""
# pylint: disable = import-error

import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import xml.dom.minidom
from datetime import datetime, timedelta, timezone
from functools import reduce
from typing import List, Any, Dict, Tuple
import pandas as pd
import pyshorteners
import requests
from tabulate import tabulate

from orion.matcher import Matcher
from orion.logger import SingletonLogger


class Utils:
    """
    Helper utils class
    """

    def __init__(self, uuid_field: str ="uuid", version_field: str ="ocpVersion"):
        """Instanciates utils class with uuid and version fields 

        Args:
            uuid_field (str): key to find the uuid
            version_field (str): key to find the version
        """
        self.uuid_field = uuid_field
        self.version_field = version_field
        self.logger = SingletonLogger.get_logger("Orion")

    # pylint: disable=too-many-locals
    def get_metric_data(
        self, uuids: List[str], metrics: Dict[str, Any], match: Matcher, test_threshold: int, timestamp_field: str="timestamp"
    ) -> List[pd.DataFrame]:
        """Gets details metrics based on metric yaml list

        Args:
            ids (list): list of all uuids
            metrics (dict): metrics to gather data on
            match (Matcher): current matcher instance
            logger (logger): log data to one output

        Returns:
            dataframe_list: dataframe of the all metrics
        """
        dataframe_list = []
        metrics_config = {}

        for metric in metrics:
            metric_name = metric["name"]
            metric_value_field = metric["metric_of_interest"]

            labels = metric.pop("labels", None)
            direction = int(metric.pop("direction", 0))
            threshold = abs(int(metric.pop("threshold", test_threshold)))
            timestamp_field = metric.pop("timestamp", timestamp_field)
            correlation = metric.pop("correlation", "")
            context = metric.pop("context", 5)
            self.logger.info("Collecting %s", metric_name)
            try:
                if "agg" in metric:
                    metric_df, metric_dataframe_name = self.process_aggregation_metric(
                        uuids, metric, match, timestamp_field
                    )
                else:
                    metric_df, metric_dataframe_name = self.process_standard_metric(
                        uuids, metric, match, metric_value_field, timestamp_field
                    )
                metric["labels"] = labels
                metric["direction"] = direction
                metric["threshold"] = threshold
                metric["correlation"] = correlation
                metric["context"] = context
                metrics_config[metric_dataframe_name] = metric
                dataframe_list.append(metric_df)
                self.logger.debug(metric_df)
            except Exception as e:
                self.logger.error(
                    "Couldn't get metrics %s, exception %s",
                    metric_name,
                    e,
                )
        return dataframe_list, metrics_config


    def process_aggregation_metric(
        self, uuids: List[str],  metric: Dict[str, Any], match: Matcher, timestamp_field: str="timestamp"
    ) -> pd.DataFrame:
        """Method to get aggregated dataframe

        Args:
            uuids (List[str]): _description_
            metric (Dict[str, Any]): _description_
            match (Matcher): _description_

        Returns:
            pd.DataFrame: _description_
        """
        aggregated_metric_data = match.get_agg_metric_query(uuids, metric, timestamp_field)
        aggregation_value = metric["agg"]["value"]
        aggregation_type = metric["agg"]["agg_type"]
        aggregation_name = f"{aggregation_value}_{aggregation_type}"
        if len(aggregated_metric_data) == 0:
            aggregated_df = pd.DataFrame(columns=[self.uuid_field, timestamp_field, aggregation_name])
        else:
            aggregated_df = match.convert_to_df(
                aggregated_metric_data, columns=[self.uuid_field, timestamp_field, aggregation_name],
                timestamp_field=timestamp_field
            )
            aggregated_df[timestamp_field] = aggregated_df[timestamp_field].apply(self.standardize_timestamp)

        aggregated_df = aggregated_df.drop_duplicates(subset=[self.uuid_field], keep="first")
        aggregated_metric_name = f"{metric['name']}_{aggregation_type}"
        aggregated_df = aggregated_df.rename(
            columns={aggregation_name: aggregated_metric_name}
        )
        if timestamp_field != "timestamp":
            aggregated_df = aggregated_df.rename(
                columns={timestamp_field: "timestamp"}
            )
        return aggregated_df, aggregated_metric_name

    def standardize_timestamp(self, timestamp: Any) -> str:
        """Method to standardize timestamp formats

        Args:
            timestamp Any: timestamp object with various formats 

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

    def process_standard_metric(
        self,
        uuids: List[str],
        metric: Dict[str, Any],
        match: Matcher,
        metric_value_field: str,
        timestamp_field: str="timestamp"
    ) -> pd.DataFrame:
        """Method to get dataframe of standard metric

        Args:
            uuids (List[str]): _description_
            metric (Dict[str, Any]): _description_
            match (Matcher): _description_
            metric_value_field (str): _description_

        Returns:
            pd.DataFrame: _description_
        """
        standard_metric_data = match.get_results("", uuids, metric)
        if len(standard_metric_data) == 0:
            standard_metric_df = pd.DataFrame(columns=[self.uuid_field, timestamp_field, metric_value_field])
        else:
            standard_metric_df = match.convert_to_df(
                standard_metric_data, columns=[self.uuid_field, timestamp_field, metric_value_field],
                timestamp_field=timestamp_field
            )
            standard_metric_df[timestamp_field] = standard_metric_df[timestamp_field].apply(self.standardize_timestamp)
        standard_metric_name = f"{metric['name']}_{metric_value_field}"
        standard_metric_df = standard_metric_df.rename(
            columns={metric_value_field: standard_metric_name}
        )
        if timestamp_field != "timestamp":
            standard_metric_df = standard_metric_df.rename(
                columns={timestamp_field: "timestamp"}
            )

        standard_metric_df = standard_metric_df.drop_duplicates()
        return standard_metric_df, standard_metric_name


    def extract_metadata_from_test(self, test: Dict[str, Any]) -> Dict[Any, Any]:
        """Gets metadata of the run from each test

        Args:
            test (dict): test dictionary

        Returns:
            dict: dictionary of the metadata
        """
        metadata = test["metadata"]
        metadata[self.version_field] = str(metadata[self.version_field])
        self.logger.debug("metadata" + str(metadata))
        return metadata


    def filter_uuids_on_index(
        self,
        metadata: Dict[str, Any],
        benchmark_index: str,
        uuids: List[str],
        match: Matcher,
        baseline: str,
        filter_node_count: bool,
    ) -> List[str]:
        """returns the index to be used and runs as uuids

        Args:
            metadata (_type_): metadata from config
            uuids (_type_): uuids collected
            match (_type_): Matcher object

        Returns:
            _type_: index and uuids
        """
        if "jobConfig.name" in metadata:
            return uuids
        if "benchmark.keyword" in metadata:
            if metadata["benchmark.keyword"] in ["ingress-perf", "k8s-netperf"]:
                return uuids
            if baseline == "" and not filter_node_count and "kube-burner" in benchmark_index:
                runs = match.match_kube_burner(uuids)
                ids = match.filter_runs(runs, runs)
            else:
                ids = uuids
        else:
            ids = uuids
        return ids

    def get_version(self, uuids: List[str], match: Matcher) -> dict:
        """Gets the version of the run from each test

        Args:
            uuids (List[str]): list of uuids to find version of
            match (Matcher): the fmatch instance
        """
        test = match.get_results("", uuids, {})
        if len(test) == 0:
            return {}

        # Fingerprint / metadata index code path
        if self.version_field in test[0]:
            return {run[self.uuid_field]: run[self.version_field] for run in test}

        # No Fingerprint / Metatdata index used. Benchmark result index path
        result = {}
        for uuid in uuids:
            test = match.get_results("", [uuid], {})
            result[uuid] = test[0]["metadata"][self.version_field]
        return result

    def get_build_urls(self, uuids: List[str], match: Matcher):
        """Gets metadata of the run from each test
            to get the build url

        Args:
            uuids (list): str list of uuid to find build urls of
            match: the fmatch instance


        Returns:
            dict: dictionary of the metadata
        """

        test = match.get_results("", uuids, {})
        buildUrls = {run[self.uuid_field]: run["buildUrl"] for run in test}
        return buildUrls


    def process_test(
        self,
        test: Dict[str, Any],
        match: Matcher,
        options: Dict[str, Any],
        start_timestamp: datetime
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Process a test and get the data for the test

        Args:
            test (dict): test configuration
            match (Matcher): the matcher object
            options (dict): options for the run
            start_timestamp (datetime): start time for the run

        Returns:
            tuple: A tuple of a dataframe and a dictionary of metrics
        """
        self.logger.info("The test %s has started", test["name"])

        test_threshold=0
        if "threshold" in test:
            test_threshold=test["threshold"]
        timestamp_field = "timestamp"
        if "timestamp" in test:
            timestamp_field=test["timestamp"]

        # getting metadata
        metadata = (
            self.extract_metadata_from_test(test)
            if options["uuid"] in ("", None)
            else self.get_metadata_with_uuid(options["uuid"], match)
        )
        # get uuids, buildUrls matching with the metadata
        runs = match.get_uuid_by_metadata(
            metadata,
            lookback_date=start_timestamp,
            lookback_size=options["lookback_size"],
            timestamp_field=timestamp_field
        )
        uuids = [run[self.uuid_field] for run in runs]
        buildUrls = {run[self.uuid_field]: run["buildUrl"] for run in runs}
        versions = self.get_version(uuids, match)
        prs = {uuid : self.sippy_pr_search(version) for uuid, version in versions.items()}
        # get uuids if there is a baseline
        if options["baseline"] not in ("", None):
            uuids = [uuid for uuid in re.split(r" |,", options["baseline"]) if uuid]
            uuids.append(options["uuid"])
            buildUrls = self.get_build_urls(uuids, match)
            versions = self.get_version( uuids, match)
        elif not uuids:
            self.logger.info("No UUID present for given metadata")
            return None, None
        match.index = options["benchmark_index"]

        uuids = self.filter_uuids_on_index(
            metadata,
            options["benchmark_index"],
            uuids,
            match,
            options["baseline"],
            options["node_count"],
        )
        # get metrics data and dataframe
        metrics = test["metrics"]
        dataframe_list, metrics_config = self.get_metric_data(
            uuids, metrics, match, test_threshold, timestamp_field
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

        merged_df[self.version_field] = merged_df[self.uuid_field].apply(
            lambda uuid: versions[uuid]
        )
        merged_df["prs"] = merged_df[self.uuid_field].apply(lambda uuid: prs[uuid])

        shortener = pyshorteners.Shortener(timeout=10)
        merged_df["buildUrl"] = merged_df[self.uuid_field].apply(
            lambda uuid: (
                self.shorten_url(shortener, buildUrls[uuid])
                if options["convert_tinyurl"]
                else buildUrls[uuid]
            )
            # pylint: disable = cell-var-from-loop
        )
        merged_df = merged_df.reset_index(drop=True)
        # save the dataframe
        output_file_path = f"{options['save_data_path'].split('.')[0]}-{test['name']}.csv"
        match.save_results(merged_df, csv_file_path=output_file_path)
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


    def get_metadata_with_uuid(self, uuid: str, match: Matcher) -> Dict[Any, Any]:
        """Gets metadata of the run from each test

        Args:
            uuid (str): str of uuid ot find metadata of
            match: the fmatch instance


        Returns:
            dict: dictionary of the metadata
        """
        test = match.get_metadata_by_uuid(uuid)
        metadata = {
            "platform": "",
            "clusterType": "",
            "masterNodesCount": 0,
            "workerNodesCount": 0,
            "infraNodesCount": 0,
            "masterNodesType": "",
            "workerNodesType": "",
            "infraNodesType": "",
            "totalNodesCount": 0,
            self.version_field: "",
            "networkType": "",
            "ipsec": "",
            "fips": "",
            "encrypted": "",
            "publish": "",
            "computeArch": "",
            "controlPlaneArch": "",
        }
        for k, v in test.items():
            if k not in metadata:
                continue
            metadata[k] = v
        if "benchmark" in test:
            metadata["benchmark.keyword"] = test["benchmark"]
        if self.version_field in metadata:
            metadata[self.version_field] = str(metadata[self.version_field])

        # Remove any keys that have blank values
        no_blank_meta = {k: v for k, v in metadata.items() if v}
        self.logger.debug("No blank metadata dict: " + str(no_blank_meta))
        return no_blank_meta

    def sippy_pr_diff(self, base_version: str, new_version: str) -> List[str]:
        """Get diff between two versions in sippy
        Args:
            base_version (str): base version
            new_version (str): diff version
        Returns:
            list: list of PRs
        """
        base_url = "https://sippy.dptools.openshift.org/api/payloads/"
        filter_url = f"diff?fromPayload={base_version}&toPayload={new_version}"
        url = base_url + filter_url
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            self.logger.error("Failed to get diff between %s and %s in sippy", base_version, new_version)
            return []
        return self.process_sippy_pr_list(response.json())

    def process_sippy_pr_list(self, pr_list: List[Dict[Any, Any]]) -> List[str]:
        """Process the list of PRs
        Args:
            pr_list (List[Dict[Any, Any]]): list of PRs
        Returns:
            List[str]: list of PR URLs
        """
        prs = []
        for pr in pr_list:
            prs.append(pr['url'])
        return prs

    def sippy_pr_search(self, version: str) -> List[str]:
        """Search for PRs in sippy

        Args:
            version (str): version to search for
        Returns:
            List[str]: list of PRs
        """
        base_url = "https://sippy.dptools.openshift.org/api/releases/pull_requests"
        filter_dict = {
            "items": [
                {
                    "columnField": "release_tag",
                    "operatorValue": "equals",
                    "value": version
                }
            ]
        }
        params = {
            "filter": json.dumps(filter_dict),
            "sortField": "pull_request_id",
            "sort": "asc"
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            self.logger.error("Failed to search for PRs in sippy for version %s", version)
            return []
        return self.process_sippy_pr_list(response.json())

# pylint: disable=too-many-locals
def json_to_junit(
    test_name: str, data_json: Dict[Any, Any], metrics_config: Dict[Any, Any], uuid_field: str
) -> str:
    """Convert json to junit format

    Args:
        test_name (_type_): _description_
        data_json (_type_): _description_

    Returns:
        _type_: _description_
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
                "\n" + generate_tabular_output(data_json, metric_name=metric, uuid_field=uuid_field) + "\n"
            )

    testsuite.set("failures", str(failures_count))
    testsuite.set("tests", str(test_count))
    xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
    dom = xml.dom.minidom.parseString(xml_str)
    pretty_xml_as_string = dom.toprettyxml()
    return pretty_xml_as_string


def generate_tabular_output(data: list, metric_name: str, uuid_field: str = "uuid") -> str:
    """converts json to tabular format

    Args:
        data (list):data in json format
        metric_name (str): metric name
    Returns:
        str: tabular form of data
    """
    records = []
    create_record = lambda record: {  # pylint: disable = C3001
        uuid_field: record[uuid_field],
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
    logger = SingletonLogger.get_logger("Orion")
    reg_ex = re.match(r"^(?:(\d+)d)?(?:(\d+)h)?$", time_duration)
    if not reg_ex:
        logger.error("Wrong format for time duration, please provide in XdYh")
    days = int(reg_ex.group(1)) if reg_ex.group(1) else 0
    hours = int(reg_ex.group(2)) if reg_ex.group(2) else 0
    duration_to_subtract = timedelta(days=days, hours=hours)
    current_time = datetime.now(timezone.utc)
    timestamp_before = current_time - duration_to_subtract
    return timestamp_before
