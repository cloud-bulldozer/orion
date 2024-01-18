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
               if column not in ["uuid","timestamp"]}
    data = {column: merged_df[column]
            for column in merged_df.columns
            if column not in ["uuid","timestamp"]}
    attributes={column: merged_df[column] for column in merged_df.columns if column in ["uuid"]}
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


def get_metadata(test):
    """Gets metadata of the run from each test

    Args:
        test (dict): test dictionary

    Returns:
        dict: dictionary of the metadata
    """
    metadata_columns = [
        "platform",
        "masterNodesType",
        "masterNodesCount",
        "workerNodesType",
        "workerNodesCount",
        "benchmark",
        "ocpVersion",
        "networkType",
        "encrypted",
        "fips",
        "ipsec",
        "infraNodesCount"
    ]
    metadata = {key: test[key] for key in metadata_columns if key in test}
    metadata["ocpVersion"] = str(metadata["ocpVersion"])
    return metadata


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
