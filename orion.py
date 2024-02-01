"""
This is the cli file for orion, tool to detect regressions using hunter
"""
# pylint: disable = import-error
import sys
from functools import reduce
import logging
import os

import click
import yaml
import pandas as pd
from fmatch.matcher import Matcher


@click.group()
def cli():
    """
    cli function to group commands
    """

# pylint: disable=too-many-locals
@click.command()
@click.option("--config", default="config.yaml", help="Path to the configuration file")
@click.option("--output", default="output.csv", help="Path to save the output csv file")
@click.option("--debug", is_flag=True, help="log level ")
def orion(config, debug, output):
    """Orion is the cli tool to detect regressions over the runs

    Args:
        config (str): path to the config file
        debug (bool): lets you log debug mode
        output (str): path to the output csv file
    """
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger("Orion")
    logger = set_logging(level, logger)

    if "ES_SERVER" not in os.environ:
        logger.error("ES_SERVER environment variable not set")
        sys.exit(1)

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
    for test in data["tests"]:
        metadata = get_metadata(test, logger)
        logger.info("The test %s has started", test["name"])
        match = Matcher(index="perf_scale_ci", level=level)
        uuids = match.get_uuid_by_metadata(metadata)
        if len(uuids) == 0:
            print("No UUID present for given metadata")
            sys.exit()

        if metadata["benchmark"] == "k8s-netperf" :
            index = "k8s-netperf"
            ids = uuids
        elif metadata["benchmark"] == "ingress-perf" :
            index = "ingress-performance"
            ids = uuids
        else:
            index = "ripsaw-kube-burner"
            runs = match.match_kube_burner(uuids)
            ids = match.filter_runs(runs, runs)

        metrics = test["metrics"]
        dataframe_list = get_metric_data(ids, index, metrics, match, logger)

        merged_df = reduce(
            lambda left, right: pd.merge(left, right, on="uuid", how="inner"),
            dataframe_list,
        )
        match.save_results(merged_df, csv_file_path=output)


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
                cpu_df = match.convert_to_df(cpu, columns=["uuid", agg_name])
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
    metadata = {}
    for k,v in test.items():
        if k in ["metrics","name"]:
            continue
        metadata[k] = v
    metadata["ocpVersion"] = str(metadata["ocpVersion"])
    logger.debug('metadata' + str(metadata))
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


if __name__ == "__main__":
    cli.add_command(orion)
    cli()
