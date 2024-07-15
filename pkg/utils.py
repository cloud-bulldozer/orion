# pylint: disable=cyclic-import
# pylint: disable = line-too-long, too-many-arguments
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
from tabulate import tabulate

import yaml
import pandas as pd

import pyshorteners

from fmatch.logrus import SingletonLogger


# pylint: disable=too-many-locals
def get_metric_data(ids, index, metrics, match, metrics_config):
    """Gets details metrics basked on metric yaml list

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
    for metric in metrics:
        labels = metric.pop("labels", None)
        direction = int(metric.pop("direction", 0))
        metric_name = metric["name"]
        logger_instance.info("Collecting %s", metric_name)
        metric_of_interest = metric["metric_of_interest"]

        if "agg" in metric.keys():
            try:
                cpu = match.get_agg_metric_query(ids, index, metric)
                agg_value = metric["agg"]["value"]
                agg_type = metric["agg"]["agg_type"]
                agg_name = agg_value + "_" + agg_type
                cpu_df = match.convert_to_df(
                    cpu, columns=["uuid", "timestamp", agg_name]
                )
                cpu_df = cpu_df.drop_duplicates(subset=["uuid"], keep="first")
                metric_dataframe_name = f"{metric_name}_{agg_type}"
                cpu_df = cpu_df.rename(columns={agg_name: metric_dataframe_name})
                metric["labels"] = labels
                metric["direction"] = direction
                metrics_config[metric_dataframe_name] = metric
                dataframe_list.append(cpu_df)
                logger_instance.debug(cpu_df)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger_instance.error(
                    "Couldn't get agg metrics %s, exception %s",
                    metric_name,
                    e,
                )
        else:
            try:
                podl = match.getResults("", ids, index, metric)
                podl_df = match.convert_to_df(
                    podl, columns=["uuid", "timestamp", metric_of_interest]
                )
                metric_dataframe_name = f"{metric_name}_{metric_of_interest}"
                podl_df = podl_df.rename(
                    columns={metric_of_interest: metric_dataframe_name}
                )
                metric["labels"] = labels
                metric["direction"] = direction
                metrics_config[metric_dataframe_name] = metric
                podl_df = podl_df.drop_duplicates()
                dataframe_list.append(podl_df)
                logger_instance.debug(podl_df)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger_instance.error(
                    "Couldn't get metrics %s, exception %s",
                    metric_name,
                    e,
                )
    return dataframe_list


def get_metadata(test):
    """Gets metadata of the run from each test

    Args:
        test (dict): test dictionary

    Returns:
        dict: dictionary of the metadata
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    metadata = test["metadata"]
    metadata["ocpVersion"] = str(metadata["ocpVersion"])
    logger_instance.debug("metadata" + str(metadata))
    return metadata


def load_config(config):
    """Loads config file

    Args:
        config (str): path to config file
        logger (Logger): logger

    Returns:
        dict: dictionary of the config file
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    try:
        with open(config, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
            logger_instance.debug("The %s file has successfully loaded", config)
    except FileNotFoundError as e:
        logger_instance.error("Config file not found: %s", e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger_instance.error("An error occurred: %s", e)
        sys.exit(1)
    return data


def get_es_url(data):
    """Gets es url from config or env

    Args:
        data (_type_): config file data
        logger (_type_): logger

    Returns:
        str: es url
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    if "ES_SERVER" in data.keys():
        return data["ES_SERVER"]
    if "ES_SERVER" in os.environ:
        return os.environ.get("ES_SERVER")
    logger_instance.error("ES_SERVER environment variable/config variable not set")
    sys.exit(1)


def get_ids_from_index(metadata, fingerprint_index, uuids, match, baseline):
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
    if baseline == "":
        runs = match.match_kube_burner(uuids, fingerprint_index)
        ids = match.filter_runs(runs, runs)
    else:
        ids = uuids
    return ids


def get_build_urls(index, uuids, match):
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
    test,
    match,
    output,
    uuid,
    baseline,
    metrics_config,
    start_timestamp,
    convert_tinyurl,
):
    """generate the dataframe for the test given

    Args:
        test (_type_): test from process test
        match (_type_): matcher object
        logger (_type_): logger object
        output (_type_): output file name

    Returns:
        _type_: merged dataframe
    """
    logger_instance = SingletonLogger.getLogger("Orion")
    benchmarkIndex = test["benchmarkIndex"]
    fingerprint_index = test["index"]
    if uuid in ("", None):
        metadata = get_metadata(test)
    else:
        metadata = filter_metadata(uuid, match)
    logger_instance.info("The test %s has started", test["name"])
    runs = match.get_uuid_by_metadata(metadata, lookback_date=start_timestamp)
    uuids = [run["uuid"] for run in runs]
    buildUrls = {run["uuid"]: run["buildUrl"] for run in runs}
    if baseline in ("", None):
        if len(uuids) == 0:
            logger_instance.error("No UUID present for given metadata")
            return None
    else:
        uuids = [uuid for uuid in re.split(" |,", baseline) if uuid]
        uuids.append(uuid)
        buildUrls = get_build_urls(fingerprint_index, uuids, match)
    fingerprint_index = benchmarkIndex
    ids = get_ids_from_index(metadata, fingerprint_index, uuids, match, baseline)

    metrics = test["metrics"]
    dataframe_list = get_metric_data(
        ids, fingerprint_index, metrics, match, metrics_config
    )

    for i, df in enumerate(dataframe_list):
        if i != 0 and ("timestamp" in df.columns):
            dataframe_list[i] = df.drop(columns=["timestamp"])

    merged_df = reduce(
        lambda left, right: pd.merge(left, right, on="uuid", how="inner"),
        dataframe_list,
    )
    shortener = pyshorteners.Shortener(timeout=10)
    merged_df["buildUrl"] = merged_df["uuid"].apply(
        lambda uuid: (
            shortener.tinyurl.short(buildUrls[uuid])
            if convert_tinyurl
            else buildUrls[uuid]
        )  # pylint: disable = cell-var-from-loop
    )
    output_file_path = output.split(".")[0] + "-" + test["name"] + ".csv"
    match.save_results(merged_df, csv_file_path=output_file_path)
    return merged_df


def filter_metadata(uuid, match):
    """Gets metadata of the run from each test

    Args:
        uuid (str): str of uuid ot find metadata of
        match: the fmatch instance


    Returns:
        dict: dictionary of the metadata
    """
    logger_instance = SingletonLogger.getLogger("Orion")
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


def json_to_junit(test_name, data_json, metrics_config):
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
        testcase = ET.SubElement(testsuite, "testcase", name=f"{label_string} {metric} regression detection", timestamp=str(int(datetime.now().timestamp())))
        if [run for run in data_json if not run["metrics"][metric]["percentage_change"] == 0]:
            failures_count +=1
            failure = ET.SubElement(testcase,"failure")
            failure.text = "\n"+generate_tabular_output(data_json, metric_name=metric)+"\n"

    testsuite.set("failures", str(failures_count))
    testsuite.set("tests", str(test_count))
    xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
    dom = xml.dom.minidom.parseString(xml_str)
    pretty_xml_as_string = dom.toprettyxml()
    return pretty_xml_as_string

def generate_tabular_output(data: dict, metric_name: str) -> str:
    """converts json to tabular format

    Args:
        data (dict):data in json format
        metric_name (str): metric name
    Returns:
        str: tabular form of data
    """
    records = []
    for record in data:
        records.append({
            "uuid": record["uuid"],
            "buildUrl": record["buildUrl"],
            metric_name: record["metrics"][metric_name]["value"],
            "percentage_change": record["metrics"][metric_name]["percentage_change"]
        })

    df = pd.DataFrame(records)
    return tabulate(df, headers='keys', tablefmt='grid')


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
