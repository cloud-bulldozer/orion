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
import uuid
import xml.etree.ElementTree as ET
import xml.dom.minidom
from datetime import datetime, timedelta, timezone
from typing import List, Any, Dict, Tuple
from fmatch.splunk_matcher import SplunkMatcher
from fmatch.matcher import Matcher
from fmatch.logrus import SingletonLogger
from tabulate import tabulate
import pandas as pd
import pyshorteners




# pylint: disable=too-many-locals
def get_metric_data(
    uuids: List[str], index: str, metrics: Dict[str, Any], match: Matcher
) -> List[pd.DataFrame]:
    """Gets details metrics based on metric yaml list

    Args:
        ids (list): list of all uuids
        index (dict): index in es of where to find data
        metrics (dict): metrics to gather data on
        match (Matcher): current matcher instance
        logger (logger): log data to one output

    Returns:
        dataframe_list: dataframe of the all metrics
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    dataframe_list = []
    metrics_config = {}

    for metric in metrics:
        metric_name = metric["name"]
        metric_value_field = metric["metric_of_interest"]

        labels = metric.pop("labels", None)
        direction = int(metric.pop("direction", 0))

        logger_instance.info("Collecting %s", metric_name)
        try:
            if "agg" in metric:
                metric_df, metric_dataframe_name = process_aggregation_metric(uuids, index, metric, match)
            else:
                metric_df, metric_dataframe_name = process_standard_metric(uuids, index, metric, match, metric_value_field)

            metric["labels"] = labels
            metric["direction"] = direction
            metrics_config[metric_dataframe_name] = metric
            dataframe_list.append(metric_df)
            logger_instance.debug(metric_df)
        except Exception as e:
            logger_instance.error(
                "Couldn't get metrics %s, exception %s",
                metric_name,
                e,
            )
    return dataframe_list, metrics_config

def get_splunk_metrics(data: dict, metrics: dict) -> Tuple[pd.DataFrame, dict]:
    """gets metrics from splunk data

    Args:
        data (dict): data with all the metrics
        metrics (dict): metrics needed to extracted

    Returns:
        Tuple[pd.DataFrame, dict]: _description_
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    dataframe_rows = []
    metrics_config = {}

    for record in data:
        timestamp = int(record["timestamp"])
        record = record["data"]
        record_uuid = uuid.uuid4()
        row_data = {
            "uuid": record_uuid,
            "timestamp": timestamp
        }

        for metric in metrics:
            metric_name = metric["name"]
            metric_value_field = metric["metric_of_interest"]
            metric_value = get_nested_value(record, metric_value_field)
            row_data[metric_name] = metric_value
            metrics_config[metric_name] = metric

        dataframe_rows.append(row_data)

    df = pd.DataFrame(dataframe_rows)
    df.dropna(inplace=True)
    df.sort_values(by="timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    logger_instance.info(f"Generated DataFrame with {len(df)} rows")
    return df, metrics_config

def get_nested_value(record, keys, default=None):
    """Recursively traverse a nested dictionary/list to get a value based on dot-separated keys."""
    keys = keys.split(".")
    for key in keys:
        if isinstance(record, dict):
            record = record.get(key, default)
        elif isinstance(record, list):
            # For lists, we assume the user wants to filter based on some condition
            key_parts = key.split("==")
            if len(key_parts) == 2:
                filter_key, filter_value = key_parts[0], key_parts[1].strip('"')
                # Look for a matching dict in the list
                record = next((item for item in record if item.get(filter_key) == filter_value), default)
            else:
                return default  # Key format is incorrect, return default
        else:
            return default  # If it's neither dict nor list, return default
    return record

def process_aggregation_metric(
    uuids: List[str], index: str, metric: Dict[str, Any], match: Matcher
) -> pd.DataFrame:
    """Method to get aggregated dataframe

    Args:
        uuids (List[str]): _description_
        index (str): _description_
        metric (Dict[str, Any]): _description_
        match (Matcher): _description_

    Returns:
        pd.DataFrame: _description_
    """
    aggregated_metric_data = match.get_agg_metric_query(uuids, index, metric)
    aggregation_value = metric["agg"]["value"]
    aggregation_type = metric["agg"]["agg_type"]
    aggregation_name = f"{aggregation_value}_{aggregation_type}"
    aggregated_df = match.convert_to_df(aggregated_metric_data, columns=["uuid", "timestamp", aggregation_name])
    aggregated_df = aggregated_df.drop_duplicates(subset=["uuid"], keep="first")
    aggregated_metric_name = f"{metric['name']}_{aggregation_type}"
    aggregated_df = aggregated_df.rename(columns={aggregation_name: aggregated_metric_name})
    return aggregated_df, aggregated_metric_name

def process_standard_metric(uuids: List[str], index: str, metric: Dict[str, Any], match: Matcher, metric_value_field: str) -> pd.DataFrame:
    """Method to get dataframe of standard metric

    Args:
        uuids (List[str]): _description_
        index (str): _description_
        metric (Dict[str, Any]): _description_
        match (Matcher): _description_
        metric_value_field (str): _description_

    Returns:
        pd.DataFrame: _description_
    """
    standard_metric_data = match.getResults("",uuids, index, metric)
    standard_metric_df = match.convert_to_df(standard_metric_data, columns=["uuid", "timestamp", metric_value_field])
    standard_metric_name = f"{metric['name']}_{metric_value_field}"
    standard_metric_df = standard_metric_df.rename(columns={metric_value_field: standard_metric_name})
    standard_metric_df = standard_metric_df.drop_duplicates()
    return standard_metric_df, standard_metric_name

def extract_metadata_from_test(test: Dict[str, Any]) -> Dict[Any, Any]:
    """Gets metadata of the run from each test

    Args:
        test (dict): test dictionary

    Returns:
        dict: dictionary of the metadata
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    metadata = test["metadata"]
    metadata = {key: str(value) for key, value in metadata.items()}
    logger_instance.debug("metadata" + str(metadata))
    return metadata

def get_datasource(data: Dict[Any, Any]) -> dict:
    """Gets es url from config or env

    Args:
        data (_type_): config file data
        logger (_type_): logger

    Returns:
        str: es url
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    if data["datasource"]["type"].lower() == "splunk":
        datasource = data["datasource"]
        datasource_config = {"host": os.environ.get("SPLUNK_HOST", datasource.get("host","")),
                             "port": os.environ.get("SPLUNK_PORT", datasource.get("port","")),
                             "username": os.environ.get("SPLUNK_USERNAME", datasource.get("username","")),
                             "password": os.environ.get("SPLUNK_PASSWORD", datasource.get("password","")),
                             "indice": os.environ.get("SPLUNK_INDICE", datasource.get("indice",""))}
        datasource.update(datasource_config)
        return datasource
    if data["datasource"]["type"].lower() == "elasticsearch":
        if "ES_SERVER" in data["datasource"].keys():
            return data["datasource"]
        if "ES_SERVER" in os.environ:
            datasource = data["datasource"]
            datasource.update({"ES_SERVER":os.environ.get("ES_SERVER")})
            return datasource

    logger_instance.error("Datasurce variable/config variable not set")
    sys.exit(1)


def filter_uuids_on_index(
    metadata: Dict[str, Any],
    fingerprint_index: str,
    uuids: List[str],
    match: Matcher,
    baseline: str,
    filter_node_count: bool
) -> List[str]:
    """returns the index to be used and runs as uuids

    Args:
        metadata (_type_): metadata from config
        uuids (_type_): uuids collected
        match (_type_): Matcher object

    Returns:
        _type_: index and uuids
    """
    if metadata["benchmark.keyword"] in ["ingress-perf", "k8s-netperf"]:
        return uuids
    if baseline == "" and not filter_node_count:
        runs = match.match_kube_burner(uuids, fingerprint_index)
        ids = match.filter_runs(runs, runs)
    else:
        ids = uuids
    return ids


def get_build_urls(index: str, uuids: List[str], match: Matcher):
    """Gets metadata of the run from each test
        to get the build url

    Args:
        uuids (list): str list of uuid to find build urls of
        match: the fmatch instance


    Returns:
        dict: dictionary of the metadata
    """

    test = match.getResults("", uuids, index, {})
    buildUrls = {run["uuid"]: run["buildUrl"] for run in test}
    return buildUrls


def process_test(
    test: Dict[str, Any],
    match: Matcher,
    options: Dict[str, Any],
    start_timestamp: datetime,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """generate the dataframe for the test given

    Args:
        test (_type_): test from process test
        match (_type_): matcher object
        logger (_type_): logger object
        output (_type_): output file name

    Returns:
        _type_: merged dataframe
    """
    logger = SingletonLogger.getLogger("Orion")
    logger.info("The test %s has started", test["name"])
    fingerprint_index = test["index"]

    # getting metadata
    metadata = extract_metadata_from_test(test) if options["uuid"] in ("", None) else get_metadata_with_uuid(options["uuid"], match)
    # get uuids, buildUrls matching with the metadata
    runs = match.get_uuid_by_metadata(metadata, fingerprint_index, lookback_date=start_timestamp, lookback_size=options['lookback_size'])
    uuids = [run["uuid"] for run in runs]
    buildUrls = {run["uuid"]: run["buildUrl"] for run in runs}
    # get uuids if there is a baseline
    if options["baseline"] not in ("", None):
        uuids = [uuid for uuid in re.split(r" |,", options["baseline"]) if uuid]
        uuids.append(options["uuid"])
        buildUrls = get_build_urls(fingerprint_index, uuids, match)
    elif not uuids:
        logger.info("No UUID present for given metadata")
        return None, None

    benchmark_index = test["benchmarkIndex"]

    uuids = filter_uuids_on_index(
        metadata, benchmark_index, uuids, match, options["baseline"], options['node_count']
    )
    # get metrics data and dataframe
    metrics = test["metrics"]
    dataframe_list, metrics_config = get_metric_data(
        uuids, benchmark_index, metrics, match
    )
    # check and filter for multiple timestamp values for each run
    for i, df in enumerate(dataframe_list):
        if i != 0 and ("timestamp" in df.columns):
            dataframe_list[i] = df.drop(columns=["timestamp"])
    # merge the dataframe with all metrics
    if dataframe_list:
        merged_df = reduce(
            lambda left, right: pd.merge(left, right, on="uuid", how="inner"),
            dataframe_list,
        )
    else:
        return None, metrics_config
    shortener = pyshorteners.Shortener(timeout=10)
    merged_df["buildUrl"] = merged_df["uuid"].apply(
        lambda uuid: (
            shorten_url(shortener, buildUrls[uuid])
            if options["convert_tinyurl"]
            else buildUrls[uuid]
        )

        # pylint: disable = cell-var-from-loop
    )
    merged_df=merged_df.reset_index(drop=True)
    #save the dataframe
    output_file_path = f"{options['save_data_path'].split('.')[0]}-{test['name']}.csv"
    match.save_results(merged_df, csv_file_path=output_file_path)
    return merged_df, metrics_config

async def process_splunk_test(
    test: Dict[str, Any],
    match: SplunkMatcher,
    options: Dict[str, Any], # pylint: disable = W0613
    start_timestamp: datetime,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """processing splunk data

    Args:
        test (Dict[str, Any]): splunk test
        match (SplunkMatcher): splunk matcher
        options (Dict[str, Any]): options for further use

    Returns:
        Tuple[pd.DataFrame, Dict[str, Any]]: _description_
    """

    logger = SingletonLogger.getLogger("Orion")
    logger.info("The test %s has started", test["name"])
    metadata = extract_metadata_from_test(test)
    start_timestamp = datetime.strptime(start_timestamp, '%Y-%m-%d %H:%M:%S') if start_timestamp else datetime.now() - timedelta(days=30)
    searchList = ' AND '.join([f'{key}="{value}"' for key, value in metadata.items()])
    query = {
        "earliest_time": f"{start_timestamp.strftime('%Y-%m-%d')}T00:00:00",
        "latest_time": f"{datetime.now().strftime('%Y-%m-%d')}T23:59:59",
        "output_mode": "json"
    }
    data = await match.query(query=query, searchList=searchList, max_results=10000)
    metrics = test["metrics"]
    dataframe_list, metrics_config = get_splunk_metrics(data, metrics)

    return dataframe_list, metrics_config

def shorten_url(shortener: any, uuids: str) -> str:
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
    short_url = ','.join(short_url_list)
    return short_url

def get_metadata_with_uuid(uuid_gen: str, match: Matcher) -> Dict[Any, Any]:
    """Gets metadata of the run from each test

    Args:
        uuid (str): str of uuid ot find metadata of
        match: the fmatch instance


    Returns:
        dict: dictionary of the metadata
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    test = match.get_metadata_by_uuid(uuid_gen)
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
        "ocpVersion": "",
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
    metadata["benchmark.keyword"] = test["benchmark"]
    metadata["ocpVersion"] = str(metadata["ocpVersion"])

    # Remove any keys that have blank values
    no_blank_meta = {k: v for k, v in metadata.items() if v}
    logger_instance.debug("No blank metadata dict: " + str(no_blank_meta))
    return no_blank_meta


def json_to_junit(
    test_name: str,
    data_json: Dict[Any, Any],
    metrics_config: Dict[Any, Any],
    options: Dict[Any, Any],
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
                "\n"
                + generate_tabular_output(
                    data_json, metric_name=metric, collapse=options["collapse"]
                )
                + "\n"
            )

    testsuite.set("failures", str(failures_count))
    testsuite.set("tests", str(test_count))
    xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
    dom = xml.dom.minidom.parseString(xml_str)
    pretty_xml_as_string = dom.toprettyxml()
    return pretty_xml_as_string


def generate_tabular_output(data: list, metric_name: str, collapse: bool) -> str:
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
    if collapse:
        for i in range(1, len(data)):
            if data[i]["metrics"][metric_name]["percentage_change"] != 0:
                records.append(create_record(data[i - 1]))
                records.append(create_record(data[i]))
                if i + 1 < len(data):
                    records.append(create_record(data[i + 1]))
    else:
        for i in range(0, len(data)):
            records.append(create_record(data[i]))

    df = pd.DataFrame(records).drop_duplicates().reset_index(drop=True)
    table = tabulate(df, headers="keys", tablefmt="psql")
    lines = table.split("\n")
    highlighted_lines = []
    if lines:
        highlighted_lines += lines[0:3]
    for i, line in enumerate(lines[3:-1]):
        if df["percentage_change"][i]:  # Offset by 3 to account for header and separator
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
    logger_instance = SingletonLogger.getLogger("Orion")
    reg_ex = re.match(r"^(?:(\d+)d)?(?:(\d+)h)?$", time_duration)
    if not reg_ex:
        logger_instance.error("Wrong format for time duration, please provide in XdYh")
    days = int(reg_ex.group(1)) if reg_ex.group(1) else 0
    hours = int(reg_ex.group(2)) if reg_ex.group(2) else 0
    duration_to_subtract = timedelta(days=days, hours=hours)
    current_time = datetime.now(timezone.utc)
    timestamp_before = current_time - duration_to_subtract
    return timestamp_before
