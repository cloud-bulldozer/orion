# pylint: disable = R0903, E0211, R0914, R0913, W0718
"""
Perfscale datasource
"""
from functools import reduce
import re
from typing import Dict, Any, List
from fmatch.matcher import Matcher
from fmatch.logrus import SingletonLogger
import pandas as pd
import pyshorteners
from pkg.datasources.datasource import Datasource
from pkg.utils import extract_metadata_from_test

class PerfscaleDatasource(Datasource):
    """Perfscale workflow intended datasource

    Args:
        Datasource (_type_): _description_
    """
    def process_test(self):
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
        logger.info("The test %s has started", self.test["name"])
        fingerprint_index = self.test["index"]

        # getting metadata
        metadata = (
            extract_metadata_from_test(self.test)
            if self.options["uuid"] in ("", None)
            else get_metadata_with_uuid(self.options["uuid"], self.match)
        )
        # get uuids, buildUrls matching with the metadata
        print(fingerprint_index)
        runs = self.match.get_uuid_by_metadata(
            metadata,
            fingerprint_index,
            lookback_date=self.start_timestamp,
            lookback_size=self.options["lookback_size"],
        )
        uuids = [run["uuid"] for run in runs]
        buildUrls = {run["uuid"]: run["buildUrl"] for run in runs}
        # get uuids if there is a baseline
        if self.options["baseline"] not in ("", None):
            uuids = [
                uuid for uuid in re.split(r" |,", self.options["baseline"]) if uuid
            ]
            uuids.append(self.options["uuid"])
            buildUrls = get_build_urls(fingerprint_index, uuids, self.match)
        elif not uuids:
            logger.info("No UUID present for given metadata")
            return None, None

        benchmark_index = self.test["benchmarkIndex"]

        uuids = filter_uuids_on_index(
            metadata,
            benchmark_index,
            uuids,
            self.match,
            self.options["baseline"],
            self.options["node_count"],
        )
        # get metrics data and dataframe
        metrics = self.test["metrics"]
        dataframe_list, metrics_config = get_metric_data(
            uuids, benchmark_index, metrics, self.match
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
                if self.options["convert_tinyurl"]
                else buildUrls[uuid]
            )
            # pylint: disable = cell-var-from-loop
        )
        merged_df = merged_df.reset_index(drop=True)
        # save the dataframe
        output_file_path = (
            f"{self.options['save_data_path'].split('.')[0]}-{self.test['name']}.csv"
        )
        self.match.save_results(merged_df, csv_file_path=output_file_path)
        return merged_df, metrics_config


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


def filter_uuids_on_index(
    metadata: Dict[str, Any],
    fingerprint_index: str,
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
    if metadata["benchmark.keyword"] in ["ingress-perf", "k8s-netperf"]:
        return uuids
    if baseline == "" and not filter_node_count:
        runs = match.match_kube_burner(uuids, fingerprint_index)
        ids = match.filter_runs(runs, runs)
    else:
        ids = uuids
    return ids


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
                metric_df, metric_dataframe_name = process_aggregation_metric(
                    uuids, index, metric, match
                )
            else:
                metric_df, metric_dataframe_name = process_standard_metric(
                    uuids, index, metric, match, metric_value_field
                )

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
    short_url = ",".join(short_url_list)
    return short_url


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
    aggregated_df = match.convert_to_df(
        aggregated_metric_data, columns=["uuid", "timestamp", aggregation_name]
    )
    aggregated_df = aggregated_df.drop_duplicates(subset=["uuid"], keep="first")
    aggregated_metric_name = f"{metric['name']}_{aggregation_type}"
    aggregated_df = aggregated_df.rename(
        columns={aggregation_name: aggregated_metric_name}
    )
    return aggregated_df, aggregated_metric_name


def process_standard_metric(
    uuids: List[str],
    index: str,
    metric: Dict[str, Any],
    match: Matcher,
    metric_value_field: str,
) -> pd.DataFrame:
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
    standard_metric_data = match.getResults("", uuids, index, metric)
    standard_metric_df = match.convert_to_df(
        standard_metric_data, columns=["uuid", "timestamp", metric_value_field]
    )
    standard_metric_name = f"{metric['name']}_{metric_value_field}"
    standard_metric_df = standard_metric_df.rename(
        columns={metric_value_field: standard_metric_name}
    )
    standard_metric_df = standard_metric_df.drop_duplicates()
    return standard_metric_df, standard_metric_name
