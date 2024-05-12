# pylint: disable=cyclic-import
"""
module for all utility functions orion uses
"""
# pylint: disable = import-error

import logging
import sys

import yaml
import pandas as pd

from hunter.report import Report, ReportType
from hunter.series import Metric, Series


def run_hunter_analyze(merged_df,test):
    """Start hunter analyze function

    Args:
        merged_df (Dataframe): merged dataframe of all the metrics
        test (dict): test dictionary with the each test information
    """
    merged_df["timestamp"] = pd.to_datetime(merged_df["timestamp"])
    merged_df["timestamp"] = merged_df["timestamp"].astype(int) // 10**9
    metrics = {column: Metric(1, 1.0)
               for column in merged_df.columns
               if column not in ["uuid","timestamp","buildUrl"]}
    data = {column: merged_df[column]
            for column in merged_df.columns
            if column not in ["uuid","timestamp","buildUrl"]}
    attributes={column: merged_df[column]
                for column in merged_df.columns if column in ["uuid","buildUrl"]}
    series=Series(
        test_name=test["name"],
        branch=None,
        time=list(merged_df["timestamp"]),
        metrics=metrics,
        data=data,
        attributes=attributes
    )
    change_points=series.analyze().change_points_by_time
    report=Report(series,change_points)
    output = report.produce_report(test_name="test",report_type=ReportType.LOG)
    print(output)
    return change_points

# pylint: disable=too-many-locals
def get_metric_data(ids, index, metrics, match, logger):
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
    dataframe_list = []
    for metric in metrics:
        metric_name = metric['name']
        logger.info("Collecting %s", metric_name)
        metric_of_interest = metric['metric_of_interest']

        if "agg" in metric.keys():
            try:
                cpu = match.get_agg_metric_query(
                    ids, index, metric
                )
                agg_value = metric['agg']['value']
                agg_type = metric['agg']['agg_type']
                agg_name = agg_value + "_" + agg_type
                cpu_df = match.convert_to_df(cpu, columns=["uuid","timestamp", agg_name])
                cpu_df = cpu_df.rename(
                    columns={agg_name: metric_name+ "_" +  agg_name}
                )
                dataframe_list.append(cpu_df)
                logger.debug(cpu_df)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(
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
                dataframe_list.append(podl_df)
                logger.debug(podl_df)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(
                    "Couldn't get metrics %s, exception %s",
                    metric_name,
                    e,
                )
    return dataframe_list


def get_metadata(test,logger):
    """Gets metadata of the run from each test

    Args:
        test (dict): test dictionary

    Returns:
        dict: dictionary of the metadata
    """
    metadata=test['metadata']
    metadata["ocpVersion"] = str(metadata["ocpVersion"])
    logger.debug('metadata' + str(metadata))
    return metadata


def filter_metadata(uuid,match,logger):
    """Gets metadata of the run from each test

    Args:
        uuid (str): str of uuid ot find metadata of
        match: the fmatch instance
        

    Returns:
        dict: dictionary of the metadata
    """

    test = match.get_metadata_by_uuid(uuid)
    metadata = {
        'platform': '', 
        'clusterType': '', 
        'masterNodesCount': 0,
        'workerNodesCount': 0,
        'infraNodesCount': 0,
        'masterNodesType': '',
        'workerNodesType': '',
        'infraNodesType': '',
        'totalNodesCount': 0,
        'ocpVersion': '',
        'networkType': '',
        'ipsec': '',
        'fips': '',
        'encrypted': '',
        'publish': '',
        'computeArch': '', 
        'controlPlaneArch': ''
    }
    for k,v in test.items():
        if k not in metadata:
            continue
        metadata[k] = v
    metadata['benchmark.keyword'] = test['benchmark']
    metadata["ocpVersion"] = str(metadata["ocpVersion"])

    #Remove any keys that have blank values
    no_blank_meta = {k: v for k, v in metadata.items() if v}
    logger.debug('No blank metadata dict: ' + str(no_blank_meta))
    return no_blank_meta



def set_logging(level, logger):
    """sets log level and format

    Args:
        level (_type_): level of the log
        logger (_type_): logger object

    Returns:
        logging.Logger: a formatted and level set logger
    """
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def load_config(config,logger):
    """Loads config file

    Args:
        config (str): path to config file
        logger (Logger): logger

    Returns:
        dict: dictionary of the config file
    """
    try:
        with open(config, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
            logger.debug("The %s file has successfully loaded", config)
    except FileNotFoundError as e:
        logger.error("Config file not found: %s", e)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("An error occurred: %s", e)
        sys.exit(1)
    return data
