"""
This is the cli file for orion, tool to detect regressions using hunter
"""
# pylint: disable = import-error
import sys
from functools import reduce
import logging
import os

import click
import pandas as pd

from fmatch.matcher import Matcher
from utils.orion_funcs import run_hunter_analyze, get_metadata, \
                                set_logging, load_config, get_metric_data


@click.group()
# pylint: disable=unused-argument
def cli(max_content_width=120):
    """
    cli function to group commands
    """

# pylint: disable=too-many-locals
@click.command()
@click.option("--config", default="config.yaml", help="Path to the configuration file")
@click.option("--output", default="output.csv", help="Path to save the output csv file")
@click.option("--debug", is_flag=True, help="log level ")
@click.option("--hunter-analyze",is_flag=True, help="run hunter analyze")
def orion(config, debug, output,hunter_analyze):
    """
    Orion is the cli tool to detect regressions over the runs

    \b
    Args:
        config (str): path to the config file
        debug (bool): lets you log debug mode
        output (str): path to the output csv file
    """
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger("Orion")
    logger = set_logging(level, logger)
    data = load_config(config,logger)
    ES_URL=None

    if "ES_SERVER" in data.keys():
        ES_URL = data['ES_SERVER']
    else:
        if 'ES_SERVER' in os.environ:
            ES_URL=os.environ.get("ES_SERVER")
        else:
            logger.error("ES_SERVER environment variable/config variable not set")
            sys.exit(1)

    for test in data["tests"]:
        metadata = get_metadata(test, logger)
        logger.info("The test %s has started", test["name"])
        match = Matcher(index="perf_scale_ci", level=level, ES_URL=ES_URL)
        uuids = match.get_uuid_by_metadata(metadata)
        if len(uuids) == 0:
            print("No UUID present for given metadata")
            sys.exit()

        if metadata["benchmark.keyword"] == "k8s-netperf" :
            index = "k8s-netperf"
            ids = uuids
        elif metadata["benchmark.keyword"] == "ingress-perf" :
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
        match.save_results(merged_df, csv_file_path=output.split(".")[0]+"-"+test['name']+".csv")

        if hunter_analyze:
            run_hunter_analyze(merged_df,test)




if __name__ == "__main__":
    if len(sys.argv) <= 1:
        cli.main(['--help'])
    else:
        print(len(sys.argv))
        cli.add_command(orion)
        cli()
