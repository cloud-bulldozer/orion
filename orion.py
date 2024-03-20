"""
This is the cli file for orion, tool to detect regressions using hunter
"""
# pylint: disable = import-error
import sys
from functools import reduce
import logging
import os
import re

import click
import pandas as pd

from fmatch.matcher import Matcher
from utils import orion_funcs


@click.group()
# pylint: disable=unused-argument
def cli(max_content_width=120):
    """
    cli function to group commands
    """

# pylint: disable=too-many-locals
@click.command()
@click.option("--uuid", default="", help="UUID to use as base for comparisons")
@click.option("--baseline", default="", help="Baseline UUID(s) to to compare against uuid")
@click.option("--config", default="config.yaml", help="Path to the configuration file")
@click.option("--output", default="output.csv", help="Path to save the output csv file")
@click.option("--debug", is_flag=True, help="log level ")
@click.option("--hunter-analyze",is_flag=True, help="run hunter analyze")
def orion(**kwargs):
    """Orion is the cli tool to detect regressions over the runs

    \b
    Args:
        uuid (str): gather metrics based on uuid
        baseline (str): baseline uuid to compare against uuid (uuid must be set when using baseline)
        config (str): path to the config file
        debug (bool): lets you log debug mode
        output (str): path to the output csv file
        hunter_analyze (bool): turns on hunter analysis of gathered uuid(s) data
    """

    level = logging.DEBUG if kwargs["debug"] else logging.INFO
    logger = logging.getLogger("Orion")
    logger = orion_funcs.set_logging(level, logger)
    data = orion_funcs.load_config(kwargs["config"],logger)
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
        uuid = kwargs["uuid"]
        baseline = kwargs["baseline"]
        match = Matcher(index="perf_scale_ci", level=level, ES_URL=ES_URL)
        if uuid == "":
            metadata = orion_funcs.get_metadata(test, logger)
        else:
            metadata = orion_funcs.filter_metadata(uuid,match,logger)

        logger.info("The test %s has started", test["name"])
        if baseline == "":
            uuids = match.get_uuid_by_metadata(metadata)
            if len(uuids) == 0:
                logging.info("No UUID present for given metadata")
                sys.exit()
        else:
            uuids = re.split(' |,',baseline)
            uuids.append(uuid)
        if metadata["benchmark.keyword"] == "k8s-netperf" :
            index = "k8s-netperf"
            ids = uuids
        elif metadata["benchmark.keyword"] == "ingress-perf" :
            index = "ingress-performance"
            ids = uuids
        else:
            index = "ripsaw-kube-burner"
            if baseline == "":
                runs = match.match_kube_burner(uuids)
                ids = match.filter_runs(runs, runs)
            else:
                ids = uuids

        metrics = test["metrics"]
        dataframe_list = orion_funcs.get_metric_data(ids, index, metrics, match, logger)

        merged_df = reduce(
            lambda left, right: pd.merge(left, right, on="uuid", how="inner"),
            dataframe_list,
        )

        csv_name = kwargs["output"].split(".")[0]+"-"+test['name']+".csv"
        match.save_results(
            merged_df, csv_file_path=csv_name
        )

        if kwargs["hunter_analyze"]:
            orion_funcs.run_hunter_analyze(merged_df,test)


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        cli.main(['--help'])
    else:
        print(len(sys.argv))
        cli.add_command(orion)
        cli()
