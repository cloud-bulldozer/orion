"""
This is the cli file for orion, tool to detect regressions using hunter
"""

# pylint: disable = import-error, line-too-long, no-member
import logging
import sys
import warnings
from typing import Any, Dict, Tuple
import json
import xml.etree.ElementTree as ET
import xml.dom.minidom
import click
from orion.logger import SingletonLogger
from orion.run_test import run
from orion.utils import get_output_extension
from orion import constants as cnsts
from orion.config import load_config, load_ack

warnings.filterwarnings("ignore", message="Unverified HTTPS request.*")
warnings.filterwarnings(
    "ignore", category=UserWarning, message=".*Connecting to.*verify_certs=False.*"
)

class Dictionary(click.ParamType):
    """Class to define a custom click type for dictionaries

    Args:
        click (ParamType):
    """
    name = "dictionary"
    def convert(self, value: Any, param: Any, ctx: Any) -> dict:
        return json.loads(value)

class MutuallyExclusiveOption(click.Option):
    """Class to implement mutual exclusivity between options in click

    Args:
        click (Option): _description_
    """

    def __init__(self, *args: tuple, **kwargs: dict[str, dict]) -> None:
        self.mutually_exclusive = set(kwargs.pop("mutually_exclusive", []))
        help = kwargs.get("help", "")  # pylint: disable=redefined-builtin
        if self.mutually_exclusive:
            ex_str = ", ".join(self.mutually_exclusive)
            kwargs["help"] = help + (
                " NOTE: This argument is mutually exclusive with "
                " arguments: [" + ex_str + "]."
            )
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.mutually_exclusive.intersection(opts) and self.name in opts:
            raise click.UsageError(
                f"Illegal usage: `{self.name}` is mutually exclusive with "
                f"arguments `{', '.join(self.mutually_exclusive)}`."
            )
        return super().handle_parse_result(ctx, opts, args)


def validate_anomaly_options(ctx, param, value: Any) -> Any: # pylint: disable = W0613
    """ validate options so that can only be used with certain flags
    """
    if value or (
        ctx.params.get("anomaly_window") or ctx.params.get("min_anomaly_percent")
    ):
        if not ctx.params.get("anomaly_detection"):
            raise click.UsageError(
                "`--anomaly-window` and `--min-anomaly-percent` can only be used when `--anomaly-detection` is enabled."
            )
    return value

# pylint: disable=too-many-locals
@click.command()
@click.option(
    "--cmr", 
    is_flag=True,
    help="Generate percent difference in comparison",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["anomaly_detection","hunter_analyze"],
)
@click.option("--filter", is_flag=True, help="Generate percent difference in comparison")
@click.option("--config", help="Path to the configuration file", required=True)
@click.option("--ack", default="", help="Optional ack YAML to ack known regressions")
@click.option(
    "--save-data-path", default="data.csv", help="Path to save the output file"
)
@click.option("--sippy-pr-search", is_flag=True, help="Search for PRs in sippy")
@click.option("--debug", default=False, is_flag=True, help="log level")
@click.option(
    "--hunter-analyze",
    is_flag=True,
    help="run hunter analyze",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["anomaly_detection","cmr"],
)
@click.option("--anomaly-window", type=int, callback=validate_anomaly_options, help="set window size for moving average for anomaly-detection")
@click.option("--min-anomaly-percent", type=int, callback=validate_anomaly_options, help="set minimum percentage difference from moving average for data point to be detected as anomaly")
@click.option(
    "--anomaly-detection",
    is_flag=True,
    help="run anomaly detection algorithm powered by isolation forest",
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["hunter_analyze","cmr"],
)
@click.option(
    "-o",
    "--output-format",
    type=click.Choice([cnsts.JSON, cnsts.TEXT, cnsts.JUNIT]),
    default=cnsts.TEXT,
    help="Choose output format (json, text or junit)",
)
@click.option("--save-output-path", default="output.txt", help="path to save output file with regressions")
@click.option("--uuid", default="", help="UUID to use as base for comparisons")
@click.option(
    "--baseline", default="", help="Baseline UUID(s) to to compare against uuid"
)
@click.option("--lookback", help="Get data from last X days and Y hours. Format in XdYh")
@click.option("--since", help="End date to bound the time range. When used with --lookback, creates a time window ending at this date. Format: YYYY-MM-DD")
@click.option("--convert-tinyurl", is_flag=True, help="Convert buildUrls to tiny url format for better formatting")
@click.option("--collapse", is_flag=True, help="Only outputs changepoints, previous and later runs in the xml format")
@click.option("--node-count", default=False, help="Match any node iterations count")
@click.option("--lookback-size", type=int, default=10000, help="Maximum number of entries to be looked back")
@click.option("--es-server", type=str, envvar="ES_SERVER", help="Elasticsearch endpoint where test data is stored, can be set via env var ES_SERVER", default="")
@click.option("--benchmark-index", type=str, envvar="es_benchmark_index",  help="Index where test data is stored, can be set via env var es_benchmark_index", default="")
@click.option("--metadata-index", type=str, envvar="es_metadata_index",  help="Index where metadata is stored, can be set via env var es_metadata_index", default="")
@click.option("--input-vars", type=Dictionary(), default="{}", help='Arbitrary input variables to use in the config template, for example: {"version": "4.18"}')
@click.option("--display", type=str, help="Add metadata field as a column in the output (e.g., ocpVirt, releaseStream)")
def main(**kwargs):
    """
    Orion runs on command line mode, and helps in detecting regressions
    """
    level = logging.DEBUG if kwargs["debug"] else logging.INFO
    if kwargs['output_format'] == cnsts.JSON :
        level = logging.ERROR
    logger = SingletonLogger(debug=level, name="Orion")
    logger.info("🏹 Starting Orion in command-line mode")
    if len(kwargs["ack"]) > 1 :
        kwargs["ackMap"] = load_ack(kwargs["ack"])
    kwargs["config"] = load_config(kwargs["config"], kwargs["input_vars"])
    if not kwargs["metadata_index"] or not kwargs["es_server"]:
        logger.error("metadata-index and es-server flags must be provided")
        sys.exit(1)
    results, results_pull = run(**kwargs)
    is_pull = False
    if results_pull[0]:
        is_pull = True
    if kwargs['output_format'] == cnsts.JSON:
        has_regression = print_json(logger, kwargs, results, results_pull, is_pull)
    elif kwargs['output_format'] == cnsts.JUNIT:
        has_regression = print_junit(logger, kwargs, results, results_pull, is_pull)
    else:
        has_regression = print_output(logger, kwargs, results, is_pull)
        if is_pull:
            print_output(logger, kwargs, results_pull, is_pull)
    if has_regression:
        sys.exit(2) ## regression detected

def print_output(
        logger,
        kwargs,
        results: Tuple[Dict[str, Any], bool, Any, str, int],
        is_pull: bool = False) -> bool:
    """
    Print the output of the tests

    Args:
        logger: logger object
        kwargs: keyword arguments
        results: results of the tests
        is_pull: whether the tests are pull requests
    """
    output = results[0]
    regression_flag = results[1]
    regression_data = results[2]
    average_values = results[3]
    pr = 0
    if is_pull and len(results) > 4:
        pr = results[4]
    if not output:
        logger.error("Terminating test")
        sys.exit(0)
    for test_name, result_table in output.items():
        if kwargs['output_format'] != cnsts.JSON :
            text = test_name
            if pr > 0:
                text = test_name + " | Pull Request #" + str(pr)
            print(text)
            print("=" * len(text))
        print(result_table)
        if is_pull and pr < 1:
            if kwargs['output_format'] != cnsts.JSON :
                text = test_name + " | Average of above Periodic runs"
                print("\n" + text)
                print("=" * len(text))
            print(average_values)
            output_file_name = f"{kwargs['save_output_path'].split('.')[0]}_{test_name}.{get_output_extension(kwargs['output_format'])}"
        else:
            output_file_name = f"{kwargs['save_output_path'].split('.')[0]}_{test_name}_pull.{get_output_extension(kwargs['output_format'])}"
        with open(output_file_name, 'w', encoding="utf-8") as file:
            file.write(str(result_table))
    if regression_flag:
        if kwargs['output_format'] != cnsts.JSON :
            print("Regression(s) found :")
            for regression in regression_data:
                if "prs" in regression:
                    formatted_prs = "\n".join([f"- {pr}" for pr in regression["prs"]])
                else:
                    formatted_prs = "N/A - Payload tests have not completed yet"
                print("-" * 50)
                print(f"{'Previous Version:':<20} {regression['prev_ver']}")
                print(f"{'Bad Version:':<20} {regression['bad_ver']}")
                if kwargs["sippy_pr_search"]:
                    print("PR diff:")
                    print(formatted_prs)

                print("-" * 50)
            if not is_pull:
                return True
        else :
            if not is_pull:
                return True
    return False


def print_json(logger, kwargs, results, results_pull, is_pull):
    """
    Print the output of the tests in json format
    """
    logger.info("Printing json output")
    output = results[0]
    regression_flag = results[1]
    average_values = results[3]
    output_pull = []
    if not output:
        logger.error("Terminating test")
        sys.exit(0)
    if is_pull and len(results_pull) > 4:
        output_pull = results_pull[0]
    for test_name, result_table in output.items():
        if not is_pull:
            print(result_table)
            output_file_name = f"{kwargs['save_output_path'].split('.')[0]}_{test_name}.{get_output_extension(kwargs['output_format'])}"
        else:
            results_json = {
                "periodic": json.loads(result_table),
                "periodic_avg": json.loads(average_values),
                "pull": json.loads(output_pull.get(test_name)),
            }
            output_file_name = f"{kwargs['save_output_path'].split('.')[0]}_{test_name}.{get_output_extension(kwargs['output_format'])}"
            output_file_name_pull = f"{kwargs['save_output_path'].split('.')[0]}_{test_name}_pull.{get_output_extension(kwargs['output_format'])}"
            print(json.dumps(results_json))
            with open(output_file_name_pull, 'w', encoding="utf-8") as file:
                file.write(str(output_pull.get(test_name)))
        with open(output_file_name, 'w', encoding="utf-8") as file:
            file.write(str(result_table))
        if regression_flag:
            return True
    return False

def print_junit(logger, kwargs, results, results_pull, is_pull):
    """
    Print the output of the tests in junit format
    """
    logger.info("Printing junit output")
    output = results[0]
    regression_flag = results[1]
    average_values = results[3]
    output_pull = []
    if not output:
        logger.error("Terminating test")
        sys.exit(0)
    if is_pull and len(results_pull) > 4:
        output_pull = results_pull[0]
    testsuites = ET.Element("testsuites")
    for test_name, result_table in output.items():
        if not is_pull:
            testsuites.append(result_table)
        else:
            testsuites.append(result_table)
            average_values.tag = "periodic_avg"
            testsuites.append(average_values)
            output_pull.get(test_name).tag = "pull"
            testsuites.append(output_pull.get(test_name))
        xml_str = ET.tostring(testsuites, encoding="utf8", method="xml").decode()
        dom = xml.dom.minidom.parseString(xml_str)
        pretty_xml_as_string = dom.toprettyxml()
        print(pretty_xml_as_string)
        output_file_name = f"{kwargs['save_output_path'].split('.')[0]}.{get_output_extension(kwargs['output_format'])}"
        with open(output_file_name, 'w', encoding="utf-8") as file:
            file.write(str(pretty_xml_as_string))
        if regression_flag:
            return True
    return False
